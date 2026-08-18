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
import sys
import subprocess

DATA_DIR = None

# サーバーモード(SERVER_MODE=True)のときは、ブラウザを開いているクライアントと
# Flaskプロセスが別マシンである可能性があるため、サーバー側でエディタや
# エクスプローラーを起動することはできない（vscode://file/ URLスキームで
# クライアント側から開く方式のみが安全）。
# 一方、ローカルモード(通常起動)ではブラウザとFlaskプロセスが同じPC上で
# 動いているため、サーバー側でエディタを直接起動する方式が使える。
# vscode://が未登録・ブロックされている環境でも確実に開けるよう、
# ローカルモードのときだけこの直接起動オプションを提供する。
SERVER_MODE = False


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


def _open_with_os_default(path):
    """OS標準の関連付けアプリでファイルを開く（最終フォールバック）。"""
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 (Windows専用API)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_locally(path, editor):
    """ローカルモード限定: サーバー(=自PC)側でエディタを直接起動する。
    `code`/`devenv` コマンドがPATHに無い・起動に失敗した場合は、
    OS標準の関連付け(拡張子ダブルクリック相当)にフォールバックする。"""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"ファイルが見つかりません: {path}")

    commands = {
        "vscode": ["code", "--goto", path],
        "vs": ["devenv", "/edit", path],
    }
    cmd = commands.get(editor)
    if cmd is None:
        raise ValueError(f"未対応のエディタ指定です: {editor}")

    try:
        subprocess.run(cmd, capture_output=True, timeout=5, check=True)
        return
    except (OSError, subprocess.SubprocessError):
        # code/devenv が無い、もしくはエディタ側の一時的な起動失敗。
        # OS標準の関連付けで開くフォールバックへ進む。
        pass

    _open_with_os_default(path)
    
def init(data_dir):
    """DATA_DIR を設定する。register() から呼ばれる想定だが、
    テスト等で file-locator 単体を使う場合はここを直接呼んでもよい。"""
    global DATA_DIR
    if not data_dir:
        raise ValueError("data_dir が指定されていません")
    DATA_DIR = os.path.abspath(data_dir)


def register(app, data_dir, server_mode=False):
    from flask import jsonify, request
    global SERVER_MODE
    init(data_dir)
    SERVER_MODE = server_mode

    @app.route("/api/file-locator/<category>/<path:name>", methods=["GET"])
    def file_locator_resolve(category, name):
        result = resolve(category, name)
        if result is None:
            return jsonify({"error": f"未対応のカテゴリです: {category}"}), 400
        # ローカルモードのときだけ、クライアントに「サーバー側で直接開く」
        # ボタンを出してよいことを知らせる。
        result["localOpenAvailable"] = not SERVER_MODE
        return jsonify(result)

    @app.route("/api/local-open", methods=["POST"])
    def local_open():
        if SERVER_MODE:
            # 別マシン(クライアント)のエディタをサーバー側から起動することは
            # できないため、サーバーモードでは明示的に拒否する
            # （クライアント側は代わりに vscode://file/ を使う）。
            return jsonify({"error": "サーバーモードではこの機能は使用できません"}), 403
        body = request.get_json(silent=True) or {}
        path = body.get("path")
        editor = body.get("editor", "vscode")
        try:
            open_locally(path, editor)
            return jsonify({"message": f"{os.path.basename(path)} を開きました"})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"ファイルを開けませんでした: {e}"}), 500
