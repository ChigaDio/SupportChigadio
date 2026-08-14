# -*- coding: utf-8 -*-
r"""
pythonSrc/csproj_sync.py

指定した .csproj ファイルに対して、指定フォルダ以下を再帰的に検索した
.cs ファイルのうち、csproj の <Compile Include="..."> に未登録のものを
一覧化し、選択したものだけを追記する機能。

対応する .csproj の形式:
    Unity が生成する伝統的な(非SDK)形式。
    例:
        <ItemGroup>
          <Compile Include="Assets\Scripts\Foo\Bar.cs" />
        </ItemGroup>
    Include のパスは、csproj ファイルが置かれているディレクトリ
    （プロジェクトルート）からの相対パスで、区切り文字は "\"、
    "Assets" から始まるのが通例。

既存フォーマットを壊さないよう、XMLパーサーで丸ごと再構築するのではなく、
正規表現でテキストベースに差分だけを追記する方式を取る（ElementTreeで
書き戻すと改行やインデント、属性順序などが変わってしまい、Unity/Gitの
diffが無駄に汚くなるため）。

進捗表示のため、追加処理は非同期ジョブとして扱い、メモリ上にジョブの
進捗を保持する。フロントエンドは /api/csproj-sync/progress/<job_id> を
ポーリングして進捗バーを更新する。
"""
import os
import re
import time
import uuid
import threading

from flask import jsonify, request

# 直近の親フォルダ名がこれに一致する.csファイルは対象外とする
_EXCLUDED_PARENT_FOLDER_NAMES = {"editor"}

# <Compile Include="..." /> または <Compile Include="...">...</Compile> の
# Include値を抽出する正規表現。名前空間の有無やタグの改行を問わず拾えるよう
# 最低限の構造だけにマッチさせる。
_COMPILE_INCLUDE_RE = re.compile(r'<Compile\s+Include\s*=\s*"([^"]+)"')

# 最後に見つかった、<Compile を含む <ItemGroup>...</ItemGroup> ブロックを
# 特定するための正規表現（追記位置を決めるために使用）。
_ITEMGROUP_RE = re.compile(r'<ItemGroup\b[^>]*>.*?</ItemGroup>', re.DOTALL)

_PROJECT_CLOSE_RE = re.compile(r'</Project\s*>')

_jobs_lock = threading.Lock()
_jobs = {}

# 進捗を視覚的に確認できるよう、1件処理するごとに挟む小休止（秒）。
# ファイル数が多い場合でも極端に遅くならない範囲に留める。
_PER_FILE_DELAY_SEC = 0.02


def _normalize_key(rel_path):
    """比較用のキー。区切り文字を統一し、大文字小文字を無視する
    （Windowsのファイルシステムは大文字小文字を区別しないため）。"""
    return rel_path.replace("/", "\\").strip("\\").lower()


def _to_windows_rel_path(base_dir, target_path):
    rel = os.path.relpath(target_path, base_dir)
    return rel.replace("/", "\\")


def parse_compile_includes(csproj_path):
    """csprojの生テキストから、既存の<Compile Include>のパス一覧を抽出する。"""
    with open(csproj_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
    return content, _COMPILE_INCLUDE_RE.findall(content)


def find_cs_files(search_folder):
    """search_folder以下を再帰的に走査し、.csファイルの絶対パス一覧を返す。
    直近の親フォルダ名が"Editor"（大文字小文字を問わない）のものは除外する。"""
    results = []
    for root, dirs, files in os.walk(search_folder):
        parent_name = os.path.basename(root)
        if parent_name.lower() in _EXCLUDED_PARENT_FOLDER_NAMES:
            # このフォルダ自体がEditorフォルダ → 配下ごとスキップ
            dirs[:] = []
            continue
        for fname in files:
            if fname.lower().endswith(".cs"):
                results.append(os.path.join(root, fname))
    return results


def scan(csproj_path, search_folder):
    """追加候補となる.csファイルの一覧を返す。"""
    if not os.path.isfile(csproj_path):
        raise FileNotFoundError(f"csprojファイルが見つかりません: {csproj_path}")
    if not os.path.isdir(search_folder):
        raise FileNotFoundError(f"検索フォルダが見つかりません: {search_folder}")

    csproj_dir = os.path.dirname(os.path.abspath(csproj_path))
    _content, existing_includes = parse_compile_includes(csproj_path)
    existing_keys = {_normalize_key(p) for p in existing_includes}

    all_cs_files = find_cs_files(search_folder)

    candidates = []
    skipped_editor = 0
    already_registered = 0
    for abs_path in all_cs_files:
        rel_path = _to_windows_rel_path(csproj_dir, abs_path)
        key = _normalize_key(rel_path)
        if key in existing_keys:
            already_registered += 1
            continue
        candidates.append({
            "relativePath": rel_path,
            "absolutePath": abs_path,
        })

    candidates.sort(key=lambda c: c["relativePath"].lower())

    return {
        "csprojPath": os.path.abspath(csproj_path),
        "searchFolder": os.path.abspath(search_folder),
        "totalScanned": len(all_cs_files),
        "alreadyRegistered": already_registered,
        "candidates": candidates,
    }


def _insert_compile_entries(content, rel_paths):
    """contentに<Compile Include="...">エントリを追記したテキストを返す。
    既存の<Compile>を含む最後のItemGroupの終了タグ直前（＝閉じタグと同じ行頭
    インデントの位置）に挿入する。見つからなければ、</Project>の直前に
    新しいItemGroupを追加する。"""
    lines = "".join(f'    <Compile Include="{p}" />\n' for p in rel_paths)

    target_block = None
    for m in _ITEMGROUP_RE.finditer(content):
        block = m.group(0)
        if "<Compile" in block:
            target_block = m  # 最後に見つかったCompileブロックを使う

    if target_block is not None:
        block = target_block.group(0)
        block_start = target_block.start()
        close_tag_rel = block.rindex("</ItemGroup>")
        # "</ItemGroup>" の直前にある行頭からのインデント文字列ごと保持するため、
        # その行の先頭（直前の改行の直後）を挿入位置にする。こうしないと、
        # 閉じタグ側の元インデントが新規追加行に食われてズレてしまう。
        prefix = block[:close_tag_rel]
        last_newline = prefix.rfind("\n")
        insert_at_in_block = 0 if last_newline == -1 else last_newline + 1
        insert_at = block_start + insert_at_in_block
        return content[:insert_at] + lines + content[insert_at:]

    # <Compile>を含むItemGroupが存在しない場合は、</Project>の直前に新設する
    m = _PROJECT_CLOSE_RE.search(content)
    if not m:
        raise ValueError("csprojファイルの形式を認識できません（</Project>が見つかりません）")
    new_block = f"  <ItemGroup>\n{lines}  </ItemGroup>\n"
    insert_at = m.start()
    return content[:insert_at] + new_block + content[insert_at:]


def _run_job(job_id, csproj_path, rel_paths):
    job = _jobs[job_id]
    try:
        with open(csproj_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        added = []
        total = len(rel_paths)
        for idx, rel_path in enumerate(rel_paths, start=1):
            content = _insert_compile_entries(content, [rel_path])
            added.append(rel_path)
            with _jobs_lock:
                job["done"] = idx
                job["message"] = f"{rel_path} を追加しました"
            time.sleep(_PER_FILE_DELAY_SEC)

        with open(csproj_path, "w", encoding="utf-8-sig") as f:
            f.write(content)

        with _jobs_lock:
            job["status"] = "done"
            job["message"] = f"{total}件のファイルをcsprojに追加しました"
            job["addedFiles"] = added
    except Exception as e:
        with _jobs_lock:
            job["status"] = "error"
            job["message"] = str(e)


def start_apply_job(csproj_path, rel_paths):
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "total": len(rel_paths),
            "done": 0,
            "status": "running",
            "message": "開始しました",
            "addedFiles": [],
        }
    t = threading.Thread(target=_run_job, args=(job_id, csproj_path, rel_paths), daemon=True)
    t.start()
    return job_id


def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _select_file_dialog(filetypes):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(filetypes=filetypes)
    root.destroy()
    return path if path else None


def register(app, data_dir):
    import pythonSrc.auth as auth

    @app.route("/api/csproj-sync/browse-csproj", methods=["POST"])
    def csproj_sync_browse_csproj():
        if auth.current_user() is None:
            return jsonify({"error": "ログインが必要です"}), 401
        path = _select_file_dialog([("C# Project", "*.csproj"), ("All Files", "*.*")])
        if not path:
            return jsonify({"error": "ファイルが選択されませんでした"}), 400
        return jsonify({"path": path})

    # フォルダ選択は download.py の /api/browse-folder を共通で使う

    @app.route("/api/csproj-sync/scan", methods=["POST"])
    def csproj_sync_scan():
        if auth.current_user() is None:
            return jsonify({"error": "ログインが必要です"}), 401
        body = request.get_json(silent=True) or {}
        csproj_path = body.get("csprojPath")
        search_folder = body.get("searchFolder")
        if not csproj_path or not search_folder:
            return jsonify({"error": "csprojPath と searchFolder は必須です"}), 400
        try:
            result = scan(csproj_path, search_folder)
            return jsonify(result)
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/csproj-sync/apply", methods=["POST"])
    def csproj_sync_apply():
        if auth.current_user() is None:
            return jsonify({"error": "ログインが必要です"}), 401
        body = request.get_json(silent=True) or {}
        csproj_path = body.get("csprojPath")
        rel_paths = body.get("relativePaths") or []
        if not csproj_path:
            return jsonify({"error": "csprojPath は必須です"}), 400
        if not os.path.isfile(csproj_path):
            return jsonify({"error": f"csprojファイルが見つかりません: {csproj_path}"}), 400
        if not rel_paths:
            return jsonify({"error": "追加対象のファイルが選択されていません"}), 400
        job_id = start_apply_job(csproj_path, rel_paths)
        return jsonify({"jobId": job_id})

    @app.route("/api/csproj-sync/progress/<job_id>", methods=["GET"])
    def csproj_sync_progress(job_id):
        job = get_job(job_id)
        if job is None:
            return jsonify({"error": "指定されたジョブが見つかりません"}), 404
        return jsonify(job)
