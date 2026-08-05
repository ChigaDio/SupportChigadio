# -*- coding: utf-8 -*-
"""
pythonSrc/download.py

ワークスペースの「ダウンロード」機能。
`data/` フォルダの内容を、指定した場所へコピーする。

ダウンロード対象の絞り込みルール:
- .json / .bytes / .txt などのデータファイルは常に含める。
- 自動生成コードのうち "Base〜" (例: BaseFoo.cs / BaseFoo.py / BaseFoo.js) は
  再ダウンロードに含めてよい（基礎クラスは常に自動生成されるため）。
- 一方、Base/本実装の分割生成を実際に行っているカテゴリ配下にある
  "Base〜" で始まらないコードファイル（本実装クラス。例: Foo.cs、
  {name}RoleAction.cs、{name}{label}State.cs、{name}StateManagerData.cs、
  {name}{label}StateBranch.cs、SystemData.cs 等）は、ユーザーがUnity側で
  手を加えている可能性があるため、以下のルールでチェックリスト化する:
    - 保存先に **まだ存在しない** 場合 → 初期状態でチェック（含める）
    - 保存先に **既に存在する** 場合   → 初期状態でチェックを外す（上書きしない）
  実際に含めるかどうかは、フロントエンドでユーザーが確認・変更したチェック結果
  (`selectedFiles`) に従う。
- Enum・ClassDataID・ClassDataMatrixID・CustomClassDataID・
  Assets(Sound/Texture/GameObject/Material/Scene)・ScenarioEvent・
  ScenarioConditions・Animator・ConstClassData 等、分割生成を行わない
  カテゴリは対象にしない（常にそのまま全て含める）。
- users.json / .flask_secret など機微ファイルは常に除外する。
"""
import os
import shutil

from flask import jsonify, request

_DATA_DIR = None

# 除外判定の対象拡張子（自動生成コードのみ。json/bytes等は対象外＝常に含める）
_CLASS_CODE_EXTENSIONS = {".cs", ".py", ".js"}

# 「Base〜 / 本実装クラス」の分割生成が実際に行われているカテゴリの
# フォルダパス（DATA_DIRからの相対パス、POSIX区切り）のみを除外判定の対象にする。
# 各generatorの実装を確認した結果:
#   - class_data                  : class_data.py       Base{name}.cs / {name}.cs
#   - custom_class_data           : customclassdata.py   Base{name}.cs / {name}.cs
#   - behavior_data               : behavior.py          Base{name}〜.cs / {name}〜.cs
#   - scenario_data/scenario_role : app.py                {name}RoleData.cs(常に自動再生成) /
#                                                          {name}RoleAction.cs(初回のみ生成・本実装)
#   - state_data                  : state.py             ManagerData/Base{name}StateManagerData.cs
#                                                          / {name}StateManagerData.cs、
#                                                          States/{name}{label}State.cs、
#                                                          Branch/{name}{label}StateBranch.cs、
#                                                          Branch/{name}{label}{id}DetailStateBranch.cs
#   - save_data                   : savedata.py / app.py Base{name}.cs / {name}.cs
#                                                          (name = SystemData / PlayerData)
# これら配下では、"Base"で始まらないコードファイルは全て本実装候補として扱う
# （個別のsibling一致チェックはせず、フォルダ単位でホワイトリスト化する方式。
#  カテゴリごとに命名規則がまちまちなため、これが最も取りこぼしが少ない）。
_CLASS_SPLIT_FOLDERS = [
    "class_data",
    "custom_class_data",
    "behavior_data",
    "scenario_data/scenario_role",
    "state_data",
    "save_data",
]

# ダウンロードに含めない機微ファイル（万一データフォルダ配下に紛れ込んだ場合の保険。
# 通常はユーザー情報等はバージョン管理外のapp_metaフォルダに保存されるため、
# ここには存在しない想定）
_SENSITIVE_FILENAMES = {"users.json", ".flask_secret", "local_settings.json"}

# ダウンロード対象から除外するトップレベルフォルダ
_EXCLUDE_TOP_DIRS = {"logs"}


def _rel_folder_posix(root, data_dir):
    rel = os.path.relpath(root, data_dir).replace("\\", "/")
    return "" if rel == "." else rel


def _rel_posix(data_dir_rel, fname):
    return (fname if data_dir_rel == "." else f"{data_dir_rel}/{fname}").replace("\\", "/")


def _in_class_split_folder(rel_folder):
    return any(rel_folder == p or rel_folder.startswith(p + "/") for p in _CLASS_SPLIT_FOLDERS)


def _is_concrete_class_file(root, fname, siblings, data_dir):
    """Base/本実装の分割生成が実在するカテゴリ配下にある「本実装クラス」ファイルかどうか。
    対象カテゴリ配下（_CLASS_SPLIT_FOLDERS）でなければ、常に False（＝除外対象にしない）。"""
    rel_folder = _rel_folder_posix(root, data_dir)
    if not _in_class_split_folder(rel_folder):
        return False
    name, ext = os.path.splitext(fname)
    if ext.lower() not in _CLASS_CODE_EXTENSIONS:
        return False
    if name.startswith("Base"):
        return False
    # フォルダがホワイトリスト対象であれば、Base〜で始まらないコードファイルは
    # 命名規則が多様（{name}RoleAction.cs, {name}{label}State.cs 等）なため、
    # siblingの厳密一致は求めずそのまま本実装候補として扱う。
    return True


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
            if not _is_concrete_class_file(root, fname, siblings, data_dir):
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
            if _is_concrete_class_file(root, fname, siblings, data_dir):
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
