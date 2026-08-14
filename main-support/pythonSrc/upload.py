# -*- coding: utf-8 -*-
"""
pythonSrc/upload.py

pythonSrc/download.py（data/ をローカルへコピー）の逆方向。
ローカルの任意フォルダ（以前ダウンロードしたもの・別環境で編集したものなど）
を、サーバーの data/ に対してアップロード（反映）するための機能。

- アップロード元フォルダ以下を再帰的に走査し、data/ 内の対応ファイルと
  比較して new（新規）/ modified（変更あり）/ unchanged（変更なし）に分類する。
- テキスト系ファイルは Python標準の difflib.unified_diff で
  git diff 風の差分を生成する。バイナリファイルは行差分を取れないため、
  ファイルサイズの比較のみを返す。
- 実際のアップロード（コピー）は、選択されたファイルのみ行う。
- users.json 等の機微ファイルは常に対象外にする（download.pyと同じ方針）。
"""
import difflib
import os
import shutil

from flask import jsonify, request

_DATA_DIR = None

# テキストとして差分表示する拡張子（要望: テキスト系全般 .cs/.json/.txt等）
_TEXT_EXTENSIONS = {
    ".cs", ".json", ".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".css", ".html", ".xml", ".yml", ".yaml", ".csproj", ".sln", ".config",
    ".shader", ".cginc", ".asmdef", ".editorconfig", ".gitignore",
}

_SENSITIVE_FILENAMES = {"users.json", ".flask_secret", "local_settings.json"}
_EXCLUDE_TOP_DIRS = {"logs"}

_MAX_DIFF_BYTES = 5 * 1024 * 1024  # 5MBを超えるテキストファイルはdiff対象外（重すぎるため）


def _is_text_file(path):
    return os.path.splitext(path)[1].lower() in _TEXT_EXTENSIONS


def _read_text(path):
    """テキストとして読み込む。デコードできなければNoneを返す。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except (UnicodeDecodeError, OSError):
        return None


def _rel_posix(base_dir, full_path):
    return os.path.relpath(full_path, base_dir).replace("\\", "/")


def scan(source_dir, data_dir):
    """source_dir以下のファイルを走査し、data_dir内の対応ファイルと比較して
    状態(new/modified/unchanged)を判定した一覧を返す。"""
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"アップロード元フォルダが見つかりません: {source_dir}")
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"データフォルダが見つかりません: {data_dir}")

    results = []
    for root, dirs, files in os.walk(source_dir):
        rel_folder = os.path.relpath(root, source_dir)
        rel_parts = [] if rel_folder == "." else rel_folder.replace("\\", "/").split("/")
        if rel_parts and rel_parts[0] in _EXCLUDE_TOP_DIRS:
            dirs[:] = []
            continue
        for fname in files:
            if fname in _SENSITIVE_FILENAMES:
                continue
            src_path = os.path.join(root, fname)
            rel_path = _rel_posix(source_dir, src_path)
            dest_path = os.path.join(data_dir, *rel_path.split("/"))

            is_text = _is_text_file(src_path)
            src_size = os.path.getsize(src_path)

            if not os.path.exists(dest_path):
                status = "new"
                dest_size = None
            else:
                dest_size = os.path.getsize(dest_path)
                if is_text:
                    src_text = _read_text(src_path)
                    dest_text = _read_text(dest_path)
                    if src_text is not None and dest_text is not None:
                        status = "unchanged" if src_text == dest_text else "modified"
                    else:
                        # デコードできない場合はバイト単位で比較する
                        with open(src_path, "rb") as f:
                            src_bytes = f.read()
                        with open(dest_path, "rb") as f:
                            dest_bytes = f.read()
                        status = "unchanged" if src_bytes == dest_bytes else "modified"
                else:
                    with open(src_path, "rb") as f:
                        src_bytes = f.read()
                    with open(dest_path, "rb") as f:
                        dest_bytes = f.read()
                    status = "unchanged" if src_bytes == dest_bytes else "modified"

            results.append({
                "relativePath": rel_path,
                "status": status,
                "isText": is_text,
                "sourceSize": src_size,
                "destSize": dest_size,
            })

    # 表示上は new/modified を先に、unchanged を後ろに（かつパス昇順）
    order = {"new": 0, "modified": 1, "unchanged": 2}
    results.sort(key=lambda r: (order.get(r["status"], 9), r["relativePath"].lower()))
    return results


def get_diff(source_dir, data_dir, relative_path):
    """1ファイル分のunified diff（gitのdiff風）を返す。
    バイナリ、または大きすぎるファイルの場合はテキスト差分の代わりに
    サマリ情報を返す。"""
    src_path = os.path.join(source_dir, *relative_path.split("/"))
    dest_path = os.path.join(data_dir, *relative_path.split("/"))

    if not os.path.isfile(src_path):
        raise FileNotFoundError(f"アップロード元にファイルが見つかりません: {relative_path}")

    src_size = os.path.getsize(src_path)
    dest_exists = os.path.isfile(dest_path)
    dest_size = os.path.getsize(dest_path) if dest_exists else None

    if not _is_text_file(src_path):
        return {
            "isText": False,
            "diffText": None,
            "summary": "バイナリファイルのため差分は表示できません。"
                       + (f"（サイズ: {dest_size} → {src_size} bytes）" if dest_exists else f"（新規、サイズ: {src_size} bytes）"),
        }

    if src_size > _MAX_DIFF_BYTES or (dest_exists and dest_size > _MAX_DIFF_BYTES):
        return {
            "isText": True,
            "diffText": None,
            "summary": f"ファイルが大きすぎるため差分表示は省略します（サイズ: {src_size} bytes）。",
        }

    src_text = _read_text(src_path)
    if src_text is None:
        return {
            "isText": False,
            "diffText": None,
            "summary": "テキストとして読み込めなかったため差分は表示できません。",
        }

    if dest_exists:
        dest_text = _read_text(dest_path)
        if dest_text is None:
            dest_text = ""
    else:
        dest_text = ""

    diff_lines = list(difflib.unified_diff(
        dest_text.splitlines(keepends=True),
        src_text.splitlines(keepends=True),
        fromfile=f"data/{relative_path}" if dest_exists else "/dev/null",
        tofile=f"upload/{relative_path}",
    ))

    if not diff_lines:
        return {"isText": True, "diffText": "", "summary": "差分はありません（内容は同一です）。"}

    return {"isText": True, "diffText": "".join(diff_lines), "summary": None}


def apply_upload(source_dir, data_dir, selected_relative_paths):
    copied = 0
    skipped = 0
    for rel_path in selected_relative_paths:
        src_path = os.path.join(source_dir, *rel_path.split("/"))
        if not os.path.isfile(src_path):
            skipped += 1
            continue
        fname = os.path.basename(src_path)
        if fname in _SENSITIVE_FILENAMES:
            skipped += 1
            continue
        dest_path = os.path.join(data_dir, *rel_path.split("/"))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(src_path, dest_path)
        copied += 1
    return copied, skipped


def register(app, data_dir):
    global _DATA_DIR
    _DATA_DIR = data_dir

    import pythonSrc.auth as auth
    import pythonSrc.activity_log as activity_log

    @app.route("/api/workspace/upload/preview", methods=["POST"])
    def workspace_upload_preview():
        user = auth.current_user()
        if user is None:
            return jsonify({"error": "ログインが必要です"}), 401
        body = request.get_json(silent=True) or {}
        source_dir = body.get("path")
        if not source_dir:
            return jsonify({"error": "アップロード元フォルダが指定されていません"}), 400
        try:
            files = scan(source_dir, _DATA_DIR)
            return jsonify({"sourceDir": os.path.abspath(source_dir), "files": files})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/workspace/upload/diff", methods=["POST"])
    def workspace_upload_diff():
        user = auth.current_user()
        if user is None:
            return jsonify({"error": "ログインが必要です"}), 401
        body = request.get_json(silent=True) or {}
        source_dir = body.get("path")
        relative_path = body.get("relativePath")
        if not source_dir or not relative_path:
            return jsonify({"error": "path と relativePath は必須です"}), 400
        try:
            result = get_diff(source_dir, _DATA_DIR, relative_path)
            return jsonify(result)
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/workspace/upload", methods=["POST"])
    def workspace_upload_apply():
        user = auth.current_user()
        if user is None:
            return jsonify({"error": "ログインが必要です"}), 401
        body = request.get_json(silent=True) or {}
        source_dir = body.get("path")
        selected = body.get("selectedFiles") or []
        if not source_dir:
            return jsonify({"error": "アップロード元フォルダが指定されていません"}), 400
        if not os.path.isdir(source_dir):
            return jsonify({"error": "アップロード元フォルダが存在しません"}), 400
        if not selected:
            return jsonify({"error": "アップロードするファイルが選択されていません"}), 400
        try:
            copied, skipped = apply_upload(source_dir, _DATA_DIR, selected)
            activity_log.record(
                user=user.get("username") if user else None,
                role=user.get("role") if user else None,
                method="POST",
                path="/api/workspace/upload",
                category="workspace_upload",
                item=f"{copied}件",
                status=200,
            )
            return jsonify({"message": f"{copied}件のファイルをアップロードしました（{skipped}件はスキップ）"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
