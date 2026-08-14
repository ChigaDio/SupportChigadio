# -*- coding: utf-8 -*-
"""
pythonSrc/file_locator.py

各種一覧グリッド（ClassDataGrid / ClassDataIdGrid / CustomClassDataGrid /
CustomClassDataIdGrid / ScenarioRoleGrid / BehaviorGrid / StateGrid /
AnimatorDataGrid / ClassDataMatrixIdGrid）の各行から、対応する
「JSONデータファイル」と「生成済みC#ファイル群」の絶対パスを解決するための
汎用API。

    GET /api/file-locator/<category>/<name>
        -> { "jsonPath": "絶対パス or null",
             "csFiles": [{"label": "ファイル名", "path": "絶対パス"}, ...] }

カテゴリごとにC#ファイルの命名規則・生成本数が異なる（例: StateはID/
ManagerData/States/Branchの各フォルダに複数生成される）ため、個々の
ファイル名を決め打ちするのではなく、対象ディレクトリ以下を再帰的に走査して
見つかった.csファイルを全て返す方式にしている。フロントエンドは1件だけなら
そのまま開き、複数あればメニューから選ばせる。

パスの利用先は、クライアント側のエディタ（VSCodeのカスタムURLスキーム
vscode://file/… や、Visual Studioへのパスコピー）であり、本モジュール自体は
ファイルを開く処理そのものは行わない（あくまでパス解決のみ）。
"""
import os
import re

DATA_DIR = None


def init(data_dir):
    global DATA_DIR
    DATA_DIR = os.path.abspath(data_dir)


def _to_valid_identifier(name):
    """pythonSrc/animation.py の to_valid_identifier と同じ変換規則。
    Animatorの個別データは、この変換後の名前でフォルダ・ファイルが
    作られるため、パス解決時にも同じ規則を適用する必要がある。"""
    if not name or name == "None":
        return "None"
    s = re.sub(r'[ .\-\(\)\[\]]+', '_', name)
    if s and s[0].isdigit():
        s = '_' + s
    keywords = {'class', 'namespace', 'public', 'void', 'int', 'float', 'bool', 'true', 'false', 'null'}
    if s in keywords:
        s += '_'
    return s


def _first_existing(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def _find_cs_files(dir_path):
    """dir_path以下を再帰的に走査し、.csファイルの絶対パス一覧を
    ファイル名昇順で返す。"""
    results = []
    if not dir_path or not os.path.isdir(dir_path):
        return results
    for root, _dirs, files in os.walk(dir_path):
        for fname in files:
            if fname.lower().endswith(".cs"):
                results.append(os.path.join(root, fname))
    results.sort(key=lambda p: os.path.basename(p).lower())
    return results


def resolve(category, name):
    """category, name から {jsonPath, csFiles} を解決する。
    未対応カテゴリの場合は None を返す。"""
    if DATA_DIR is None:
        return None

    if category == "class_data":
        d = os.path.join(DATA_DIR, "class_data", name)
        json_path = os.path.join(d, f"{name}.class.json")
    elif category == "class_data_id":
        # 詳細JSONの読み込みは name.replace("ID","") ディレクトリ、
        # C#生成は name そのままのディレクトリという既存実装上の食い違いが
        # あるため、両方を候補として調べる。
        candidate_dirs = [
            os.path.join(DATA_DIR, "class_data_id", name),
            os.path.join(DATA_DIR, "class_data_id", name.replace("ID", "")),
        ]
        d = next((c for c in candidate_dirs if os.path.isdir(c)), candidate_dirs[0])
        json_path = _first_existing([os.path.join(c, f"{name}.json") for c in candidate_dirs])
    elif category == "custom_class_data":
        d = os.path.join(DATA_DIR, "custom_class_data", name)
        json_path = os.path.join(d, f"{name}.customclass.json")
    elif category == "custom_class_data_id":
        d = os.path.join(DATA_DIR, "custom_class_data_id", name)
        json_path = os.path.join(d, f"{name}.json")
    elif category == "scenario_role":
        d = os.path.join(DATA_DIR, "scenario_data", "scenario_role", name)
        json_path = os.path.join(d, f"{name}.json")
    elif category == "behavior_data":
        d = os.path.join(DATA_DIR, "behavior_data", name)
        json_path = os.path.join(d, f"{name}.json")
    elif category == "state_data":
        d = os.path.join(DATA_DIR, "state_data", name)
        json_path = os.path.join(d, f"{name}.state.json")
    elif category == "animator_data":
        safe_name = _to_valid_identifier(name)
        d = os.path.join(DATA_DIR, "assets_data", "anim_data", safe_name)
        json_path = os.path.join(d, f"{safe_name}.json")
    elif category == "class_data_matrix_id":
        d = os.path.join(DATA_DIR, "class_data_matrix_id", name)
        json_path = os.path.join(d, f"{name}.json")
    else:
        return None

    if json_path and not os.path.isfile(json_path):
        json_path = None

    cs_files = _find_cs_files(d)
    return {
        "jsonPath": json_path,
        "csFiles": [{"label": os.path.basename(p), "path": p} for p in cs_files],
    }


def register(app, data_dir):
    from flask import jsonify
    init(data_dir)

    @app.route("/api/file-locator/<category>/<path:name>", methods=["GET"])
    def file_locator_resolve(category, name):
        result = resolve(category, name)
        if result is None:
            return jsonify({"error": f"未対応のカテゴリです: {category}"}), 400
        return jsonify(result)
