# -*- coding: utf-8 -*-
"""
pythonSrc/download.py

ワークスペースの「ダウンロード」機能。
`data/` フォルダの内容を、指定した場所へコピーする。

ダウンロード対象の絞り込みルール:
- .json / .bytes / .txt などのデータファイルは常に含める。
- 自動生成コードのうち "Base〜" (例: BaseFoo.cs / BaseFoo.py / BaseFoo.js) は
  再ダウンロードに含めてよい（基礎クラスは常に自動生成されるため）。
- 一方、対応する Base〜 ファイルが存在する「本実装クラス」(例: Foo.cs) は
  ユーザーがUnity側で手を加えている可能性があるため、以下のルールでチェックリスト化する:
    - 保存先に **まだ存在しない** 場合 → 初期状態でチェック（含める）
    - 保存先に **既に存在する** 場合   → 初期状態でチェックを外す（上書きしない）
  実際に含めるかどうかは、フロントエンドでユーザーが確認・変更したチェック結果
  (`selectedFiles`) に従う。
- Enum関連の生成物には Base/本実装の区別が無いため、除外対象にしない。
- users.json / .flask_secret など機微ファイルは常に除外する。
"""
import os
import shutil

from flask import jsonify, request

_DATA_DIR = None

# 除外判定の対象拡張子（自動生成コードのみ。json/bytes等は対象外＝常に含める）
_CLASS_CODE_EXTENSIONS = {".cs", ".py", ".js"}

# このフォルダ名を含むパスは enum 系生成物とみなし、Base/本実装の区別をしない
_ENUM_DIR_MARKERS = {"enum"}

# ダウンロードに含めない機微ファイル（ユーザー情報/セッション鍵など）
_SENSITIVE_FILENAMES = {"users.json", ".flask_secret", "local_settings.json"}

# ダウンロード対象から除外するトップレベルフォルダ
_EXCLUDE_TOP_DIRS = {"logs"}


def _is_enum_path(root):
    parts = {p.lower() for p in root.replace("\\", "/").split("/")}
    return bool(parts & _ENUM_DIR_MARKERS)


def _rel_posix(data_dir_rel, fname):
    return (fname if data_dir_rel == "." else f"{data_dir_rel}/{fname}").replace("\\", "/")


def _is_concrete_class_file(root, fname, siblings):
    """Base〜と対になっている「本実装クラス」ファイルかどうか。"""
    name, ext = os.path.splitext(fname)
    if ext.lower() not in _CLASS_CODE_EXTENSIONS:
        return False
    if name.startswith("Base"):
        return False
    if _is_enum_path(root):
        return False
    return f"Base{name}{ext}" in siblings


def _dest_root(data_dir, dest_dir):
    return os.path.join(dest_dir, os.path.basename(os.path.normpath(data_dir)))


def scan_concrete_candidates(data_dir, dest_dir):
    """本実装クラス候補ファイルを列挙し、保存先に既に存在するかどうかを調べる。

    戻り値: (dest_root, [{"path": 相対パス, "alreadyExists": bool, "checked": bool}, ...])
    """
    dest_root = _dest_root(data_dir, dest_dir)
    results = []
    for root, dirs, files in os.walk(data_dir):
        rel = os.path.relpath(root, data_dir)
        rel_parts = [] if rel == "." else rel.replace("\\", "/").split("/")
        if rel_parts and rel_parts[0] in _EXCLUDE_TOP_DIRS:
            dirs[:] = []
            continue
        siblings = set(files)
        for fname in files:
            if fname in _SENSITIVE_FILENAMES:
                continue
            if not _is_concrete_class_file(root, fname, siblings):
                continue
            rel_path = _rel_posix(rel, fname)
            dest_file = os.path.join(dest_root, *rel_path.split("/"))
            already_exists = os.path.exists(dest_file)
            results.append({
                "path": rel_path,
                "alreadyExists": already_exists,
                # 保存先に無ければ初期チェックON（含める）、既にあればOFF（上書きしない）
                "checked": not already_exists,
            })
    results.sort(key=lambda r: r["path"])
    return dest_root, results


def copy_data_for_download(data_dir, dest_dir, selected_concrete_files=None):
    """data_dir配下をdest_dirへコピーする。

    `selected_concrete_files` は、ユーザーがダウンロードに含めることを選択した
    「本実装クラス」ファイルの相対パス一覧（scan_concrete_candidatesが返す "path"）。
    Base〜・json・bytes・enum関連など、本実装クラス以外は常にコピーされる。
    """
    selected = set(selected_concrete_files or [])
    copied = 0
    skipped = 0
    dest_root = _dest_root(data_dir, dest_dir)
    for root, dirs, files in os.walk(data_dir):
        rel = os.path.relpath(root, data_dir)
        rel_parts = [] if rel == "." else rel.replace("\\", "/").split("/")
        if rel_parts and rel_parts[0] in _EXCLUDE_TOP_DIRS:
            dirs[:] = []
            continue

        target_dir = os.path.join(dest_root, rel) if rel != "." else dest_root
        os.makedirs(target_dir, exist_ok=True)
        siblings = set(files)
        for fname in files:
            if fname in _SENSITIVE_FILENAMES:
                skipped += 1
                continue
            if _is_concrete_class_file(root, fname, siblings):
                rel_path = _rel_posix(rel, fname)
                if rel_path not in selected:
                    skipped += 1
                    continue
            shutil.copy2(os.path.join(root, fname), os.path.join(target_dir, fname))
            copied += 1
    return dest_root, copied, skipped


def _select_directory():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askdirectory()
    root.destroy()
    return path if path else None


def register(app, data_dir):
    global _DATA_DIR
    _DATA_DIR = data_dir

    import pythonSrc.auth as auth

    @app.route("/api/browse-folder", methods=["POST"])
    def browse_folder():
        """サーバー側でフォルダ選択ダイアログを開き、選択されたパスを返す。
        （ダウンロード実行やマイページのデフォルト保存先設定から共通で利用）"""
        user = auth.current_user()
        if user is None:
            return jsonify({"error": "ログインが必要です"}), 401
        path = _select_directory()
        if not path:
            return jsonify({"error": "フォルダが選択されませんでした"}), 400
        return jsonify({"path": path})

    @app.route("/api/workspace/download/preview", methods=["POST"])
    def workspace_download_preview():
        user = auth.current_user()
        if user is None:
            return jsonify({"error": "ログインが必要です"}), 401
        body = request.get_json(silent=True) or {}
        dest_dir = body.get("path")
        if not dest_dir:
            return jsonify({"error": "保存先パスが指定されていません"}), 400
        if not os.path.isdir(dest_dir):
            return jsonify({"error": "保存先フォルダが存在しません"}), 400
        dest_root, candidates = scan_concrete_candidates(_DATA_DIR, dest_dir)
        return jsonify({"destPath": dest_root, "concreteFiles": candidates})

    @app.route("/api/workspace/download", methods=["POST"])
    def workspace_download():
        user = auth.current_user()
        if user is None:
            return jsonify({"error": "ログインが必要です"}), 401

        body = request.get_json(silent=True) or {}
        dest_dir = body.get("path")
        if not dest_dir:
            return jsonify({"error": "保存先が指定されていません"}), 400
        if not os.path.isdir(dest_dir):
            return jsonify({"error": "保存先フォルダが存在しません"}), 400

        selected_files = body.get("selectedFiles")

        try:
            dest_root, copied, skipped = copy_data_for_download(_DATA_DIR, dest_dir, selected_files)
            return jsonify({
                "message": f"{copied}件のファイルをダウンロードしました（{skipped}件は除外/スキップ）",
                "path": dest_root,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
