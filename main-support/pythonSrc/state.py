# -*- coding: utf-8 -*-
"""
pythonSrc/state.py

State（ステートマシン）管理API。
- /api/state-data, /api/state-data/<name>, /api/generate-state/<name>
- ステート/ブランチ/コントロールクラスのC#生成ヘルパー群
- /api/open-code/<state_name>/<node_label>（対応する.csファイルの絶対パスを返す。
  実際にVSCode/Visual Studioで開く処理はクライアント側で行う）

app.py から `pythonSrc.state.register(app, DATA_DIR)` を呼び出して有効化する。
"""
import json
import logging
import os
import re
from math import isnan, isfinite

from flask import Blueprint, jsonify, request

from pythonSrc.constants import STATE_DATA, TYPE_MAP
from pythonSrc.data_utils import get_type_lists, generate_csharp_field

logger = logging.getLogger(__name__)
bp = Blueprint('state', __name__)

# app.py 側の register(app, DATA_DIR) で設定される
DATA_DIR = None

def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    os.makedirs(os.path.join(DATA_DIR, STATE_DATA), exist_ok=True)


def regenerate_state_group_id(data_dir):
    """
    state_list.json (各Stateグループ = name の一覧) から StateGroupID.cs を再生成する。
    グループの追加/削除の度に呼び出すことで、C#側の「ベースとなるid」を常に同期する。
    """
    state_dir = os.path.join(data_dir, STATE_DATA)
    os.makedirs(state_dir, exist_ok=True)
    list_path = os.path.join(state_dir, "state_list.json")
    try:
        with open(list_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    names = [item['name'] for item in data if item.get('name')]

    lines = []
    lines.append("namespace GameCore.States.ID\n")
    lines.append("{\n")
    lines.append("    public enum StateGroupID\n")
    lines.append("    {\n")
    lines.append("        None = 0,\n")
    for name in names:
        lines.append(f"        {name},\n")
    lines.append("        Max\n")
    lines.append("    }\n")
    lines.append("}\n")

    with open(os.path.join(state_dir, "StateGroupID.cs"), 'w', encoding='utf-8') as f:
        f.writelines(lines)


# StateData-ID管理
@bp.route('/api/state-data', methods=['GET', 'POST', 'PATCH'])
def manage_state_data():
    file_path = os.path.join(DATA_DIR, STATE_DATA, 'state_list.json')
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Returning state-data: {data}")
            return jsonify(data)
        except FileNotFoundError:
            return jsonify([]), 404
        except Exception as e:
            logger.error(f"Error reading state-data: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            new_state = request.get_json()
            if not new_state or not new_state.get('name'):
                return jsonify({"error": "State name is required"}), 400
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
            if any(item['name'] == new_state['name'] for item in data):
                return jsonify({"error": f"State {new_state['name']} already exists"}), 400
            max_id = max([item['id'] for item in data], default=0) + 1
            new_state_entry = {"id": max_id, "name": new_state['name']}
            data.append(new_state_entry)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            new_directory_path = os.path.join(DATA_DIR, STATE_DATA, new_state['name'])
            os.makedirs(new_directory_path, exist_ok=True)
            with open(os.path.join(new_directory_path, f"{new_state['name']}.state.json"), 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            regenerate_state_group_id(DATA_DIR)
            logger.info(f"Added state-data: {new_state['name']}")
            return jsonify({"message": f"State {new_state['name']} created successfully", "data": new_state_entry})
        except Exception as e:
            logger.error(f"Error adding state-data: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'PATCH':
        try:
            delete_name = request.get_json()['name']
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            regenerate_state_group_id(DATA_DIR)
            logger.info(f"Removed state: {delete_name}")
            return jsonify({"message": f"State {delete_name} removed from state_list.json"})
        except FileNotFoundError:
            return jsonify({"error": "state_list.json not found"}), 404
        except Exception as e:
            logger.error(f"Error removing state-data: {str(e)}")
            return jsonify({"error": str(e)}), 500
        


# StateData詳細管理
@bp.route('/api/state-data/<name>', methods=['GET', 'POST', 'DELETE'])
def manage_state_detail(name):
    file_path = os.path.join(DATA_DIR, STATE_DATA, name, f'{name}.state.json')
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Returning state data for {name}: {data}")
            return jsonify(data)
        except FileNotFoundError:
            return jsonify([]), 404
        except Exception as e:
            logger.error(f"Error reading state {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            data = request.get_json()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved state data for {name}")
            return jsonify({"message": f"{name}.state.json saved successfully"})
        except Exception as e:
            logger.error(f"Error saving state {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'DELETE':
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                os.rmdir(os.path.join(DATA_DIR, STATE_DATA, name))
                state_list_path = os.path.join(DATA_DIR, STATE_DATA, 'state_list.json')
                with open(state_list_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data = [item for item in data if item['name'] != name]
                with open(state_list_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Deleted state: {name}")
                return jsonify({"message": f"{name}.state.json deleted successfully"})
            return jsonify({"error": f"{name}.state.json not found"}), 404
        except Exception as e:
            logger.error(f"Error deleting state {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500

# StateData C#生成
@bp.route('/api/generate-state/<name>', methods=['POST'])
def generate_state_cs(name):
    try:
        data = request.get_json()
        generate_state_classes(os.path.join(DATA_DIR, STATE_DATA, name), name, data )
        generate_state_id(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_state_manager_data(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_state_branch(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_control_classes(os.path.join(DATA_DIR, STATE_DATA, name), name, data)

        # Python / JavaScript 版（簡易対応）も合わせて生成する
        generate_state_id_python(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_state_manager_data_python(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_state_classes_python(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_control_classes_python(os.path.join(DATA_DIR, STATE_DATA, name), name, data)

        generate_state_id_javascript(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_state_manager_data_javascript(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_state_classes_javascript(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_control_classes_javascript(os.path.join(DATA_DIR, STATE_DATA, name), name, data)

        logger.info(f"Generated {name}.cs")
        return jsonify({"message": f"{name}.cs generated successfully"})
    except Exception as e:
        logger.error(f"Error generating {name}.cs: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
#stateのIDを作成
def generate_state_id(file_path, name, json_data):
    if not os.path.exists(os.path.join(file_path, "ID")):
        os.makedirs(os.path.join(file_path, "ID"))
    file_id_path = os.path.join(file_path, "ID",f'{name}StateID.cs')

    # nodes が存在しないか空の場合は終了
    if not json_data or not json_data.get('nodes'):
        return
    
    code_str = []
    code_label = []
    for data in json_data.get('transitions', []):
        label = data.get("fromState", {})
        if label not in code_label:
            code_str.append(f'      {label},\n')
            code_label.append(label)
    for data in json_data.get('nodes', []):
        label = data.get("data", {}).get("label", "")
        id = data.get("id", 0)
        if label:
            code_str.append(f'      {label}{int(id):02d},\n')

    with open(file_id_path, 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.States.ID\n{\n')
        f.write(f'  public enum {name}StateID {{\n')
        f.write('       None = 0,\n')
        f.writelines(code_str)
        f.write('       Max\n')
        f.write('   }\n')
        f.write('}\n')

    # ベースID (ラベルのみ、番号無しで重複排除したもの)
    # 例: AAA01/AAA04 のような同じラベルの複数ノードは、ベースIDでは AAA の1つにまとまる。
    file_base_id_path = os.path.join(file_path, "ID", f'{name}StateBaseID.cs')
    base_labels = []
    for label in code_label:
        if label not in base_labels:
            base_labels.append(label)
    for data in json_data.get('nodes', []):
        label = data.get("data", {}).get("label", "")
        if label and label not in base_labels:
            base_labels.append(label)

    with open(file_base_id_path, 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.States.ID\n{\n')
        f.write(f'  public enum {name}StateBaseID {{\n')
        f.write('       None = 0,\n')
        for label in base_labels:
            f.write(f'      {label},\n')
        f.write('       Max\n')
        f.write('   }\n')
        f.write('}\n')

#ManagerDataの作成
def generate_state_manager_data(file_path, name, json_data):
    if not os.path.exists(os.path.join(file_path, "ManagerData")):
        os.makedirs(os.path.join(file_path, "ManagerData"))
    file_base_state_manager_data_path = os.path.join(file_path, "ManagerData", f'Base{name}StateManagerData.cs')
    file_state_manager_data_path = os.path.join(file_path, "ManagerData", f'{name}StateManagerData.cs')

    base_code_str = []


    base_list,unity_types,enum_list, class_list,class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
    basic_types = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object']
    unity_types = [
    'GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 
    'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 
    'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 
    'ScriptableObject'
    ]
    for item in json_data.get('manager', []):
        base_code_str.append(f"{generate_csharp_field(item, enum_list, class_list, unity_types, basic_types,class_data_id_list)['field']}")

    # --- ベースID(TestStateBaseIDのような、番号無しのラベルのみのID)の
    #     現在/直前を保持するための対応表とフィールド ---
    # 個々の {name}StateID（AAA01, BBB02, ...や、スタック用の AAA, BBB, ...）から
    # 対応する {name}StateBaseID（AAA, BBB, ...）を引けるようにする。
    id_to_base_label = []
    seen_ids = set()
    for data in json_data.get('transitions', []):
        label = data.get("fromState", "")
        if label and label not in seen_ids:
            id_to_base_label.append((label, label))
            seen_ids.add(label)
    for data in json_data.get('nodes', []):
        label = data.get("data", {}).get("label", "")
        node_id = data.get("id", 0)
        if label:
            specific_id = f"{label}{int(node_id):02d}"
            if specific_id not in seen_ids:
                id_to_base_label.append((specific_id, label))
                seen_ids.add(specific_id)

    with open(file_base_state_manager_data_path, 'w', encoding='utf-8') as f:
        f.write('using System.Collections.Generic;\n')
        f.write('using UnityEngine;\n')
        f.write('using GameCore.States.ID;\n\n')

        f.write('namespace GameCore.States.Managers\n{\n')
        f.write(f'    public class Base{name}StateManagerData : BaseStateManagerData<GameCore.States.ID.{name}StateID>\n    {{\n')

        for data in base_code_str:
            f.write(data)

        # --- ベースID: 現在/直前を保持し、ChangeStateNowID の度に自動で切り替える ---
        # Dictionaryは使わず、switch文にハードコードすることでメモリ確保・辞書引きを避ける。
        f.write(f'        protected {name}StateBaseID now_state_base_id = {name}StateBaseID.None;\n')
        f.write(f'        protected {name}StateBaseID old_state_base_id = {name}StateBaseID.None;\n\n')

        f.write(f'        public {name}StateBaseID GetNowStateBaseID() => now_state_base_id;\n')
        f.write(f'        public {name}StateBaseID GetOldStateBaseID() => old_state_base_id;\n\n')

        f.write(f'        public override void ChangeStateNowID({name}StateID new_state_id)\n')
        f.write('        {\n')
        f.write('            base.ChangeStateNowID(new_state_id);\n')
        f.write('            old_state_base_id = now_state_base_id;\n')
        f.write('            switch (new_state_id)\n')
        f.write('            {\n')
        for specific_id, base_label in id_to_base_label:
            f.write(f'                case {name}StateID.{specific_id}: now_state_base_id = {name}StateBaseID.{base_label}; break;\n')
        f.write(f'                default: now_state_base_id = {name}StateBaseID.None; break;\n')
        f.write('            }\n')
        f.write('        }\n')

        f.write('   }\n')
        f.write('}\n')
        
    if os.path.exists(file_state_manager_data_path) == False:
        with open(file_state_manager_data_path, 'w', encoding='utf-8') as f:
            f.write('using System.Collections.Generic;\n')
            f.write('using UnityEngine;\n\n')


            f.write('namespace GameCore.States.Managers\n{\n')
            f.write(f'    public class {name}StateManagerData : Base{name}StateManagerData\n    {{\n')
            f.write('    }\n')
            f.write('}\n')



def generate_state_branch(file_path, name, json_data):
    """
    ゲームステートブランチのC#コードを生成する。
    file_path: 出力先ディレクトリ
    name: ステート名（例: MainGame）
    json_data: ノード情報を持つJSONデータ
    """
    branch_dir = os.path.join(file_path, "Branch")
    os.makedirs(branch_dir, exist_ok=True)
    node_dict = {node["id"]: node for node in json_data.get("nodes", [])}

    # --- Base{name}StateBranch.cs ---
    base_main_branch_path = os.path.join(branch_dir, f'Base{name}StateBranch.cs')
    with open(base_main_branch_path, 'w', encoding='utf-8') as f:
        f.write('using System;\n')
        f.write('using UnityEngine;\n')
        f.write('using GameCore.States.Managers;\n\n')
        f.write('using GameCore.States.ID;\n')
        f.write('namespace GameCore.States.Branch\n{\n')
        f.write(f'    public abstract class Base{name}StateBranch<TState, TDetailState> : BaseStateBranch<{name}StateID, {name}StateManagerData, TState, TDetailState>\n')
        f.write(f'        where TState : GameCore.States.Base{name}State\n')
        f.write(f'        where TDetailState : Base{name}DetailStateBranch<TState>\n')
        f.write('    {\n')
        f.write(f'        public override abstract {name}StateID ConditionsBranch({name}StateManagerData manager_data, TState state);\n')
        f.write(f'        public override abstract TDetailState Factory({name}StateID id);\n')
        f.write('    }\n')
        f.write('}\n')

    # --- Base{name}DetailStateBranch.cs ---
    base_detail_path = os.path.join(branch_dir, f'Base{name}DetailStateBranch.cs')
    with open(base_detail_path, 'w', encoding='utf-8') as f:
        f.write('using System;\n')
        f.write('using UnityEngine;\n')
        f.write('using GameCore.States.ID;\n')
        f.write('using GameCore.States.Managers;\n\n')

        f.write('namespace GameCore.States.Branch\n{\n')
        f.write(f'    public abstract class Base{name}DetailStateBranch<TState> : BaseDetailStateBranch<{name}StateID, {name}StateManagerData, TState>\n')
        f.write(f'        where TState : GameCore.States.Base{name}State\n')
        f.write('    {\n')
        f.write(f'        public override abstract {name}StateID ConditionsBranch({name}StateManagerData manager_data, TState state);\n')
        f.write('    }\n')
        f.write('}\n')

    # --- ノードごとの Detail クラス生成 ---
    label_groups = {}
    for node in json_data["nodes"]:
        label = node["data"]["label"]
        targets = node["data"].get("targets", [])
        if len(targets) <= 1:
            continue  # ターゲットが1つ以下なら DetailBranch を作らない
        label_groups.setdefault(label, []).append(node)

    for label, nodes in label_groups.items():
        # --- Base{name}{label}DetailStateBranch.cs ---
        base_label_path = os.path.join(branch_dir, f'Base{name}{label}DetailStateBranch.cs')
        with open(base_label_path, 'w', encoding='utf-8') as f:
            f.write('using System;\n')
            f.write('using UnityEngine;\n')
            f.write('using GameCore.States.ID;\n')
            f.write('using GameCore.States.Managers;\n\n')
            f.write('namespace GameCore.States.Branch\n{\n')
            f.write(f'    public abstract class Base{name}{label}DetailStateBranch : Base{name}DetailStateBranch<{name}{label}State>\n')
            f.write('    {\n')
            f.write(f'        public override abstract {name}StateID ConditionsBranch({name}StateManagerData manager_data, {name}{label}State state);\n')
            # NOTE: 各遷移判定メソッドは「このlabelに属する全ノードの遷移先」の和集合として
            # ここで宣言されるが、個々のノード(下のBase...{node_id}DetailStateBranch)は
            # 自分に関係する遷移先だけを使う。abstractにすると、無関係なノードの
            # 派生クラスで「使っていない抽象メンバーを実装していない」というコンパイルエラーに
            # なるため、virtual + デフォルトfalseとして宣言し、必要な派生クラス側だけで
            # overrideする形にしている。
            for node in nodes:
                targets = node["data"].get("targets", [])
                for target_id in targets:
                    target_label = node_dict.get(target_id, {}).get("data", {}).get("label", "")
                    if target_label:
                        f.write(f'        public virtual bool {name}{label}_to_{target_label}{int(target_id):02d}({name}StateManagerData manager_data, {name}{label}State state) {{ return false; }}\n')
            f.write('    }\n')
            f.write('}\n')

        # --- IDごとの BaseDetail / Detail クラス ---
        for node in nodes:
            node_id = int(node["id"])
            targets = node["data"].get("targets", [])
            if len(targets) <= 1:
                continue  # ターゲットが1つ以下なら DetailBranch を作らない
            # Base{name}{label}{node_id:02d}DetailStateBranch.cs
            base_id_path = os.path.join(branch_dir, f'Base{name}{label}{node_id:02d}DetailStateBranch.cs')
            with open(base_id_path, 'w', encoding='utf-8') as f:
                f.write('using System;\n')
                f.write('using UnityEngine;\n')
                f.write('using GameCore.States.ID;\n')
                f.write('using GameCore.States.Managers;\n\n')
                f.write('namespace GameCore.States.Branch\n{\n')
                f.write(f'    public abstract class Base{name}{label}{node_id:02d}DetailStateBranch : Base{name}{label}DetailStateBranch\n')
                f.write('    {\n')
                f.write(f'        public override {name}StateID ConditionsBranch({name}StateManagerData manager_data, {name}{label}State state)\n')
                f.write('        {\n')
                for target_id in targets:
                    target_label = node_dict.get(target_id, {}).get("data", {}).get("label", "")
                    if target_label:
                        f.write(f'            if ({name}{label}_to_{target_label}{int(target_id):02d}(manager_data, state))\n')
                        f.write(f'                return {name}StateID.{target_label}{int(target_id):02d};\n')
                f.write(f'            return {name}StateID.None;\n')
                f.write('        }\n')
                f.write('    }\n')
                f.write('}\n')

            # {name}{label}{node_id:02d}DetailStateBranch.cs
            impl_id_path = os.path.join(branch_dir, f'{name}{label}{node_id:02d}DetailStateBranch.cs')
            if os.path.exists(impl_id_path):
                continue  # 既に生成されている場合はスキップ
            with open(impl_id_path, 'w', encoding='utf-8') as f:
                f.write('using System;\n')
                f.write('using UnityEngine;\n')
                f.write('using GameCore.States.ID;\n')
                f.write('using GameCore.States.Managers;\n\n')
                f.write('namespace GameCore.States.Branch\n{\n')
                f.write(f'    public class {name}{label}{node_id:02d}DetailStateBranch : Base{name}{label}{node_id:02d}DetailStateBranch\n')
                f.write('    {\n')
                for target_id in targets:
                    target_label = node_dict.get(target_id, {}).get("data", {}).get("label", "")
                    if target_label:
                        f.write(f'        public override bool {name}{label}_to_{target_label}{int(target_id):02d}({name}StateManagerData manager_data, {name}{label}State state)\n')
                        f.write('        {\n')
                        f.write('            return false;\n')
                        f.write('        }\n\n')
                f.write('    }\n')
                f.write('}\n')

    # --- {name}{label}StateBranch.cs を生成 ---
    for label, nodes in label_groups.items():
        branch_path = os.path.join(branch_dir, f'{name}{label}StateBranch.cs')
        if os.path.exists(branch_path):
            continue  # 既に生成されている場合はスキップ
        with open(branch_path, 'w', encoding='utf-8') as f:
            f.write('using System;\n')
            f.write('using UnityEngine;\n')
            f.write('using GameCore.States.ID;\n')
            f.write('using GameCore.States.Managers;\n\n')
            f.write('namespace GameCore.States.Branch\n{\n')
            f.write(f'    public class {name}{label}StateBranch : Base{name}StateBranch<{name}{label}State, Base{name}{label}DetailStateBranch>\n')
            f.write('    {\n')
            f.write(f'        public override {name}StateID ConditionsBranch({name}StateManagerData manager_data, {name}{label}State state)\n')
            f.write('        {\n')
            f.write('            var id = manager_data.GetNowStateID();\n')
            f.write('            var branch = Factory(id);\n')
            f.write(f'            return branch != null ? branch.ConditionsBranch(manager_data, state) : {name}StateID.None;\n')
            f.write('        }\n\n')
            f.write(f'        public override Base{name}{label}DetailStateBranch Factory({name}StateID id)\n')
            f.write('        {\n')
            f.write('            switch (id)\n')
            f.write('            {\n')
            for node in nodes:
                f.write(f'                case {name}StateID.{label}{int(node["id"]):02d}:\n')
                f.write(f'                    return new {name}{label}{int(node["id"]):02d}DetailStateBranch();\n')
            f.write('                default:\n')
            f.write('                    return null;\n')
            f.write('            }\n')
            f.write('        }\n')
            f.write('    }\n')
            f.write('}\n')


#stateの作成
def generate_state_classes(file_path, name, json_data):
    state_dir = os.path.join(file_path,"States")
    os.makedirs(state_dir, exist_ok=True)

    # --- GameCore.States.Base{name}State.cs ---




    # 型情報の取得（ダミー関数、外で定義する想定）
    basic_types, unity_types, enum_list, class_list,class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()  

    basic_types = [
        'int', 'float', 'bool', 'string', 'double',
        'byte', 'char', 'short', 'long', 'decimal', 'object'
    ]
    unity_types = [
        'GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion',
        'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite',
        'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip',
        'ScriptableObject'
    ]

    base_code_str = []
    for item in json_data.get('base', []):
        base_code_str.append(generate_csharp_field(item, enum_list, class_list, unity_types, basic_types,class_data_id_list))

        
    base_state_path = os.path.join(state_dir, f'Base{name}State.cs')
    with open(base_state_path, 'w', encoding='utf-8') as f:
        f.write('using UnityEngine;\n')
        f.write('using GameCore.States.Managers;\n')
        f.write('using GameCore.States.ID;\n\n')
        f.write('namespace GameCore.States\n{\n')
        f.write(f'    public abstract class Base{name}State : BaseState<{name}StateID, {name}StateManagerData>\n')
        f.write('    {\n')
        for data in base_code_str:
            f.write(data)
        f.write('    }\n')
        f.write('}\n')
        

    labels = []
    
    
    # --- ノードごとにBase派生クラスと通常クラスを作成 ---
    for node in json_data.get('nodes', []):
        label = node.get("data", {}).get("label", "")
        if label in labels:
            continue
        labels.append(label)
        targets = node.get("data", {}).get("targets", [])
        # Base{name}{label}State.cs
        base_label_state_path = os.path.join(state_dir, f'Base{name}{label}State.cs')
        lifecycle = _get_node_lifecycle(node)
        with open(base_label_state_path, 'w', encoding='utf-8') as f:
            f.write('using UnityEngine;\n')
            f.write('using GameCore.States.Branch;\n\n')
            f.write('namespace GameCore.States\n{\n')
            f.write(f'    public abstract class Base{name}{label}State : GameCore.States.Base{name}State\n')
            f.write('    {\n')
            f.write(_build_lifecycle_block(lifecycle))

            f.write('    }\n')
            f.write('}\n')
            

        # {name}{label}{id:02d}State.cs
        state_class_path = os.path.join(state_dir, f'{name}{label}State.cs')
        ensure_lifecycle_in_state_class(base_label_state_path, lifecycle)
        if os.path.exists(state_class_path):
            # 既存なら追記・削除の調整を実施
            ensure_branchnext_in_state_class(state_class_path, name, label, targets)
        else:
            # 新規生成
            # NOTE: UseXxxSync/UseXxxAsync のoverride（ライフサイクル設定）は
            # Base{name}{label}State.cs 側（上のブロックで書き込み済み）にのみ持たせる。
            # 本実装クラス（このファイル）には持たせない。
            with open(state_class_path, 'w', encoding='utf-8') as f:
                f.write('using UnityEngine;\n')
                f.write('using System.Threading;\n')
                f.write('using Cysharp.Threading.Tasks;\n\n')
                f.write('using GameCore.States.Branch;\n')
                f.write('namespace GameCore.States\n{\n')
                f.write(f'    public class {name}{label}State : Base{name}{label}State\n')
                f.write('    {\n')
                f.write(f'        public override void Enter(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ IsEnterActiveOff(); }}\n')
                f.write(f'        public override void Update(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ IsUpdateActiveOff(); }}\n')
                f.write(f'        public override void Exit(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ IsExitActiveOff(); }}\n')
                f.write(f'        public override async UniTask EnterAsync(GameCore.States.Managers.{name}StateManagerData state_manager_data, CancellationToken ct) {{ IsEnterActiveAsyncOff(); await UniTask.CompletedTask; }}\n')
                f.write(f'        public override async UniTask UpdateAsync(GameCore.States.Managers.{name}StateManagerData state_manager_data, CancellationToken ct) {{ IsUpdateActiveAsyncOff(); await UniTask.CompletedTask; }}\n')
                f.write(f'        public override async UniTask ExitAsync(GameCore.States.Managers.{name}StateManagerData state_manager_data, CancellationToken ct) {{ IsExitActiveAsyncOff(); await UniTask.CompletedTask; }}\n')
                if len(targets) > 1:
                    f.write(
                        f'        public override GameCore.States.ID.{name}StateID BranchNextState(GameCore.States.Managers.{name}StateManagerData state_manager_data)\n'
                        f'        {{\n'
                        f'            var branch = new {name}{label}StateBranch();\n'
                        f'            var next_id = branch.ConditionsBranch(state_manager_data, this);\n'
                        f'            return next_id;\n'
                        f'        }}\n'
                    )
                f.write('    }\n')
                f.write('}\n')
                
    for node in json_data.get('transitions', []):
        label = node.get("fromState", "")
        if label in labels:
            continue
        base_label_state_path = os.path.join(state_dir, f'Base{name}{label}State.cs')
        state_class_path = os.path.join(state_dir, f'{name}{label}State.cs')
        transition_lifecycle = _get_transition_lifecycle(node)

        if os.path.exists(base_label_state_path):
            # 既存ならライフサイクル設定だけ同期する
            ensure_lifecycle_in_state_class(base_label_state_path, transition_lifecycle)
            continue

        with open(base_label_state_path, 'w', encoding='utf-8') as f:
            f.write('using UnityEngine;\n')
            f.write('using GameCore.States.Branch;\n\n')
            f.write('namespace GameCore.States\n{\n')
            f.write(f'    public abstract class Base{name}{label}State : GameCore.States.Base{name}State\n')
            f.write('    {\n')
            f.write(_build_lifecycle_block(transition_lifecycle))
            f.write('    }\n')
            f.write('}\n')

        # 新規生成
        # NOTE: UseXxxSync/UseXxxAsync のoverride（ライフサイクル設定）は
        # Base{name}{label}State.cs 側（すぐ上で書き込み済み）にのみ持たせる。
        # 本実装クラス（このファイル）には持たせない。
        with open(state_class_path, 'w', encoding='utf-8') as f:
            f.write('using UnityEngine;\n')
            f.write('using System.Threading;\n')
            f.write('using Cysharp.Threading.Tasks;\n\n')
            f.write('using GameCore.States.Branch;\n')
            f.write('namespace GameCore.States\n{\n')
            f.write(f'    public class {name}{label}State : Base{name}{label}State\n')
            f.write('    {\n')
            f.write(f'        public override void Enter(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ IsEnterActiveOff(); }}\n')
            f.write(f'        public override void Update(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ IsUpdateActiveOff(); }}\n')
            f.write(f'        public override void Exit(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ IsExitActiveOff(); }}\n')
            f.write(f'        public override async UniTask EnterAsync(GameCore.States.Managers.{name}StateManagerData state_manager_data, CancellationToken ct) {{ IsEnterActiveAsyncOff(); await UniTask.CompletedTask; }}\n')
            f.write(f'        public override async UniTask UpdateAsync(GameCore.States.Managers.{name}StateManagerData state_manager_data, CancellationToken ct) {{ IsUpdateActiveAsyncOff(); await UniTask.CompletedTask; }}\n')
            f.write(f'        public override async UniTask ExitAsync(GameCore.States.Managers.{name}StateManagerData state_manager_data, CancellationToken ct) {{ IsExitActiveAsyncOff(); await UniTask.CompletedTask; }}\n')
            f.write('    }\n')
            f.write('}\n')
            
# --- Combinedモード用: ノードごとの Enter/Update/Exit 同期・非同期 使用設定 ---
# 遷移図でノードをクリックして開く設定パネル（フロント側）で編集される。
# node["data"]["lifecycle"] = {"enter": {"sync":bool,"async":bool}, "update": {...}, "exit": {...}}
_DEFAULT_LIFECYCLE = {
    "enter": {"sync": True, "async": False},
    "update": {"sync": True, "async": False},
    "exit": {"sync": True, "async": False},
}

_LIFECYCLE_PROP_MAP = [
    ("enter", "UseEnterSync", "UseEnterAsync"),
    ("update", "UseUpdateSync", "UseUpdateAsync"),
    ("exit", "UseExitSync", "UseExitAsync"),
]

_LIFECYCLE_MARKER_START = '        // __LIFECYCLE_OVERRIDES_START__\n'
_LIFECYCLE_MARKER_END = '        // __LIFECYCLE_OVERRIDES_END__\n'


def _normalize_lifecycle(cfg):
    """
    生のlifecycle辞書（{"enter":{"sync":..,"async":..}, ...}）を正規化する。
    未設定時のデフォルトは同期のみ。同期・非同期どちらもfalseな場合は
    同期にフォールバックする（フロント側でも「最低1つは必須」だが、
    念のためバックエンドでも保証する）。
    """
    cfg = cfg or {}
    result = {}
    for stage, default in _DEFAULT_LIFECYCLE.items():
        stage_cfg = cfg.get(stage, {}) if isinstance(cfg, dict) else {}
        sync = bool(stage_cfg.get("sync", default["sync"])) if isinstance(stage_cfg, dict) else default["sync"]
        is_async = bool(stage_cfg.get("async", default["async"])) if isinstance(stage_cfg, dict) else default["async"]
        if not sync and not is_async:
            sync = True
        result[stage] = {"sync": sync, "async": is_async}
    return result


def _get_node_lifecycle(node):
    """ノード（nodes配列の要素）の lifecycle 設定を取得する。data.lifecycle に入っている。"""
    return _normalize_lifecycle((node or {}).get("data", {}).get("lifecycle"))


def _get_transition_lifecycle(transition):
    """
    transition（transitions配列の要素。スタック/LIFOで使われるサブノードの
    ラベルもここを参照する）の lifecycle 設定を取得する。
    transitionは data にネストされておらず、直下に lifecycle を持つ。
    """
    return _normalize_lifecycle((transition or {}).get("lifecycle"))


def _build_lifecycle_block(lifecycle):
    """
    BaseStateのデフォルト（各ステージ 同期のみ）と異なる項目だけを
    UseXxxSync/UseXxxAsync のoverrideとして書き出す。目印コメントで囲むことで、
    既存ファイルに対しても差分更新（ensure_lifecycle_in_state_class）できるようにしている。
    """
    lines = [_LIFECYCLE_MARKER_START]
    for stage, sync_prop, async_prop in _LIFECYCLE_PROP_MAP:
        cfg = lifecycle[stage]
        default = _DEFAULT_LIFECYCLE[stage]
        if cfg["sync"] != default["sync"]:
            val = "true" if cfg["sync"] else "false"
            lines.append(f'        public override bool {sync_prop} => {val};\n')
        if cfg["async"] != default["async"]:
            val = "true" if cfg["async"] else "false"
            lines.append(f'        public override bool {async_prop} => {val};\n')
    lines.append(_LIFECYCLE_MARKER_END)
    return ''.join(lines)


def ensure_lifecycle_in_state_class(state_class_path, lifecycle):
    """
    既存の {name}{label}State.cs に対して、UseXxxSync/UseXxxAsync のoverrideブロックを
    差し替える（マーカーコメントが無ければ新規挿入、あれば中身だけ更新）。
    """
    if not os.path.exists(state_class_path):
        return False

    with open(state_class_path, 'r', encoding='utf-8') as fr:
        content = fr.read()

    new_block = _build_lifecycle_block(lifecycle)

    if _LIFECYCLE_MARKER_START in content and _LIFECYCLE_MARKER_END in content:
        pattern = re.compile(
            re.escape(_LIFECYCLE_MARKER_START) + r'.*?' + re.escape(_LIFECYCLE_MARKER_END),
            re.DOTALL
        )
        updated = pattern.sub(new_block.replace('\\', '\\\\'), content)
    else:
        # マーカーが無い（古い形式の）ファイル: 末尾の閉じ括弧の直前に挿入する
        updated = re.sub(r'^\s*}\s*\Z',
                          new_block + '    }\n}',
                          content,
                          flags=re.MULTILINE)

    if updated != content:
        with open(state_class_path, 'w', encoding='utf-8') as fw:
            fw.write(updated)
        return True
    return False


def ensure_branchnext_in_state_class(state_class_path, name, label, targets):
    """既存ファイルに BranchNextState を追記・削除する"""
    branch_code = (
        f'        public override GameCore.States.ID.{name}StateID BranchNextState(GameCore.States.Managers.{name}StateManagerData state_manager_data)\n'
        f'        {{\n'
        f'            var branch = new {name}{label}StateBranch();\n'
        f'            var next_id = branch.ConditionsBranch(state_manager_data, this);\n'
        f'            return next_id;\n'
        f'        }}\n'
    )

    if not os.path.exists(state_class_path):
        return False  # 新規生成時に書き込むので何もしない

    with open(state_class_path, 'r', encoding='utf-8') as fr:
        content = fr.read()

    has_branch_code = branch_code in content

    if len(targets) > 1 and not has_branch_code:
        # --- 追記処理 ---
        # クラスの終わりの直前 } に挿入する
        content = re.sub(r'^\s*}\s*\Z',
                         branch_code + '    }\n}',
                         content,
                         flags=re.MULTILINE)
        with open(state_class_path, 'w', encoding='utf-8') as fw:
            fw.write(content)
        return True

    elif len(targets) <= 1 and has_branch_code:
        # --- 削除処理 ---
        content = content.replace(branch_code, '')
        with open(state_class_path, 'w', encoding='utf-8') as fw:
            fw.write(content)
        return True

    return False





def _write_branch_switch_cases(f, name, json_data, nodes, mode):
    """
    BranchState()（同期）/ BranchStateAsync()（非同期）/ BranchStateCombined()（同期+非同期同時）
    のswitch文の中身を書き出す共通処理。3モードともこの1つの生成ロジックを共有しているため、
    遷移ロジック自体は常に一致する。

    mode:
      'sync'     - state.Exit/state.Enter(...) のみ
      'async'    - await state.ExitAsync/EnterAsync(..., CancellationToken)
      'combined' - 同期版をその場で呼びつつ、非同期版はFire-and-Forgetで発火する
    """
    def write_exit():
        if mode == 'async':
            f.write('                    await state.ExitAsync(state_manager_data, stateCts.Token);\n')
        elif mode == 'combined':
            # 呼ぶかどうかは state 自身が宣言する UseExitSync/UseExitAsync に従う。
            # （遷移図のノード設定でチェックした方だけが呼ばれるため、二重実行にならない）
            # このあと state は次Stateに差し替わるため、Exitフェーズの完了判定
            # （IsExitActive/IsExitActiveAsync）は exitingState 経由で行う。
            f.write('                    exitingState = state;\n')
            f.write('                    if (exitingState.UseExitSync) exitingState.Exit(state_manager_data);\n')
            f.write('                    if (exitingState.UseExitAsync) exitingState.ExitAsync(state_manager_data, combinedCts.Token).Forget(LogAsyncException);\n')
        else:
            f.write('                    state.Exit(state_manager_data);\n')

    def write_enter():
        if mode == 'async':
            f.write('                    var ct2 = RenewStateToken(life_time_token);\n')
            f.write('                    await state.EnterAsync(state_manager_data, ct2);\n')
        elif mode == 'combined':
            # ここでは即座にEnterを発火しない。exitingState（旧State）の
            # Exitフェーズ完了を OnUpdateStateCombined 側で待ってから、
            # 次State（新しいstate）のEnterフェーズを発火する。
            f.write('                    combinedAsyncUpdateStarted = false;\n')
            f.write('                    combinedEnterPending = true;\n')
        else:
            f.write('                    state.Enter(state_manager_data);\n')

    code_label = []
    for node in json_data.get('transitions', []):
        label = node["fromState"]
        state_id = f"{name}StateID.{label}"
        if label not in code_label:
            code_label.append(label)
            f.write(f'                case {state_id}:\n')
            f.write('                {\n')
            write_exit()
            f.write('                    state_manager_data.PopUpStateID();\n')
            f.write('                    id = state_manager_data.PopStateID();\n')
            f.write(f'                    if(id == {name}StateID.None) id = state_manager_data.SaveStateID;\n')
            f.write(f'                    if(id == {name}StateID.None)\n')
            f.write('                    {\n')
            f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
            f.write('                        is_finish = true;\n')
            f.write('                        return;\n')
            f.write('                    }\n')
            f.write('                    else\n')
            f.write('                    {\n')
            f.write('                        state_manager_data.ChangeStateNowID(id);\n')
            f.write(f'                        state_manager_data.SaveStateID = {name}StateID.None;\n')
            f.write('                    }\n')
            f.write('                    state = FactoryState(id);\n')
            f.write('                    if (state == null)\n')
            f.write('                    {\n')
            f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
            f.write(f'                        state_manager_data.SaveStateID = {name}StateID.None;\n')
            f.write('                        is_finish = true;\n')
            f.write('                        return;\n')
            f.write('                    }\n')
            write_enter()
            f.write('                    return;\n')
            f.write('                }\n')

    for node in nodes:
        label = node["data"]["label"]
        node_id = int(node["id"])
        state_id = f"{name}StateID.{label}{node_id:02d}"
        targets = node["data"].get("targets", [])

        f.write(f'                case {state_id}:\n')
        f.write('                {\n')
        write_exit()
        f.write('                    state_manager_data.PopUpStateID();\n')
        if not targets:
            if len(node["data"].get("subNodes", [])) > 0:
                f.write(f'                    state_manager_data.SaveStateID = {name}StateID.None;\n')
                for child in node["data"].get("subNodes", []):
                    child_label = child["label"]
                    child_id = f"{name}StateID.{child_label}"
                    f.write(f'                    state_manager_data.PushStateID({child_id});\n')
                f.write('                    var next_id = state_manager_data.PopStateID();\n')
                f.write('                    state = FactoryState(next_id);\n')
                f.write('                    if (state == null)\n')
                f.write('                    {\n')
                f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
                f.write(f'                        state_manager_data.SaveStateID = {name}StateID.None;\n')
                f.write('                        is_finish = true;\n')
                f.write('                        return;\n')
                f.write('                    }\n')
                write_enter()
                f.write('                    return;\n')
            else:
                f.write('                    is_finish = true;\n')
                f.write('                    return;\n')
        elif len(targets) == 1:
            next_node = targets[0]
            target_label = next(
                (n["data"]["label"] for n in nodes if n["id"] == next_node), None)
            if target_label:
                f.write(f'                    var next_id = {name}StateID.{target_label}{int(next_node):02d};\n')
                if len(node["data"].get("subNodes", [])) > 0:
                    f.write('                    state_manager_data.SaveStateID = next_id;\n')
                    for child in node["data"].get("subNodes", []):
                        child_label = child["label"]
                        child_id = f"{name}StateID.{child_label}"
                        f.write(f'                    state_manager_data.PushStateID({child_id});\n')
                    f.write('                    state_manager_data.PushStateID(next_id);\n')
                    f.write('                    next_id = state_manager_data.PopStateID();\n')
                else:
                    f.write('                    state_manager_data.ChangeStateNowID(next_id);\n')
                f.write('                    state = FactoryState(next_id);\n')
                f.write('                    if (state == null)\n')
                f.write('                    {\n')
                f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
                f.write(f'                        state_manager_data.SaveStateID = {name}StateID.None;\n')
                f.write('                        is_finish = true;\n')
                f.write('                        return;\n')
                f.write('                    }\n')
                write_enter()
                f.write('                    return;\n')
        else:
            f.write('                   var next_id = state.BranchNextState(state_manager_data);\n')
            if len(node["data"].get("subNodes", [])) > 0:
                f.write('                    state_manager_data.SaveStateID = next_id;\n')
                for child in node["data"].get("subNodes", []):
                    child_label = child["label"]
                    child_id = f"{name}StateID.{child_label}"
                    f.write(f'                    state_manager_data.PushStateID({child_id});\n')
                f.write('                    state_manager_data.PushStateID(next_id);\n')
                f.write('                    next_id = state_manager_data.PopStateID();\n')
            else:
                f.write('                    state_manager_data.ChangeStateNowID(next_id);\n')
            f.write(f'                    if (next_id == {name}StateID.None)\n')
            f.write('                    {\n')
            f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
            f.write(f'                        state_manager_data.SaveStateID = {name}StateID.None;\n')
            f.write('                        is_finish = true;\n')
            f.write('                        return;\n')
            f.write('                    }\n')
            f.write('                    state = FactoryState(next_id);\n')
            f.write('                    if (state == null)\n')
            f.write('                    {\n')
            f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
            f.write(f'                        state_manager_data.SaveStateID = {name}StateID.None;\n')
            f.write('                        is_finish = true;\n')
            f.write('                        return;\n')
            f.write('                    }\n')
            write_enter()
            f.write('                    return;\n')
        f.write('                }\n')


#Control
def generate_control_classes(file_path, name, json_data):
    control_dir = os.path.join(file_path, "Control")
    os.makedirs(control_dir, exist_ok=True)

    nodes = json_data.get('nodes', [])
    if not nodes:
        return

    # 初期 ID (id=1のノードを探す)
    init_node = next((n for n in nodes if int(n["id"]) == 1), nodes[0])
    init_label = init_node["data"]["label"]
    init_id = int(init_node["id"])
    init_state_id = f"{name}StateID.{init_label}{init_id:02d}"

    # --- Base{name}StateControl.cs ---
    base_file_path = os.path.join(control_dir, f'Base{name}StateControl.cs')
    with open(base_file_path, 'w', encoding='utf-8') as f:
        f.write('using System;\n')
        f.write('using System.Threading;\n')
        f.write('using Cysharp.Threading.Tasks;\n')
        f.write('using UnityEngine;\n')
        f.write('using GameCore.States.ID;\n')
        f.write('using GameCore.States.Managers;\n')
        f.write('using GameCore.States;\n\n')

        f.write('namespace GameCore.States.Control\n{\n')
        f.write(f'    public abstract class Base{name}StateControl\n')
        f.write(f'        : BaseStateControl<{name}StateID, {name}StateManagerData, Base{name}State>\n')
        f.write('    {\n')

        # GroupID (StateGroupTracker用)
        f.write(f'        protected override StateGroupID GroupID => StateGroupID.{name};\n\n')

        # GetInitStartID()
        f.write(f'        protected override {name}StateID GetInitStartID()\n')
        f.write('        {\n')
        f.write(f'            return {init_state_id};\n')
        f.write('        }\n\n')

        # BranchState() 同期版
        f.write('        public override void BranchState()\n')
        f.write('        {\n')
        f.write('            if (state.IsUpdateActive) return;\n\n')
        f.write('            isTransitioning = true;\n')
        f.write('            try\n')
        f.write('            {\n')
        f.write('            var id = state_manager_data.PopStateID();\n')
        f.write(f'            if(id == {name}StateID.None) id = state_manager_data.GetNowStateID();\n')
        f.write('            switch (id)\n')
        f.write('            {\n')
        _write_branch_switch_cases(f, name, json_data, nodes, mode='sync')
        f.write('            }\n')
        f.write('            }\n')
        f.write('            finally\n')
        f.write('            {\n')
        f.write('                isTransitioning = false;\n')
        f.write('            }\n')
        f.write('        }\n\n')

        # BranchStateAsync() 非同期版
        f.write('        public override async UniTask BranchStateAsync(CancellationToken life_time_token)\n')
        f.write('        {\n')
        f.write('            if (state.IsUpdateActive) return;\n\n')
        f.write('            isTransitioning = true;\n')
        f.write('            try\n')
        f.write('            {\n')
        f.write('            var id = state_manager_data.PopStateID();\n')
        f.write(f'            if(id == {name}StateID.None) id = state_manager_data.GetNowStateID();\n')
        f.write('            switch (id)\n')
        f.write('            {\n')
        _write_branch_switch_cases(f, name, json_data, nodes, mode='async')
        f.write('            }\n')
        f.write('            }\n')
        f.write('            finally\n')
        f.write('            {\n')
        f.write('                isTransitioning = false;\n')
        f.write('            }\n')
        f.write('        }\n\n')

        # BranchStateCombined() 同期+非同期を両方動かすモード
        # (IsUpdateActive/IsUpdateActiveAsyncが両方falseの時だけ StateControl 側から
        #  呼ばれるため、ここでは「呼ばれたら無条件にExitして遷移してよい」という
        #  前提で良い。実際の次StateへのEnterはExit完了待ち後にControl側が発火する)
        f.write('        public override void BranchStateCombined()\n')
        f.write('        {\n')
        f.write('            isTransitioning = true;\n')
        f.write('            try\n')
        f.write('            {\n')
        f.write('            var id = state_manager_data.PopStateID();\n')
        f.write(f'            if(id == {name}StateID.None) id = state_manager_data.GetNowStateID();\n')
        f.write('            switch (id)\n')
        f.write('            {\n')
        _write_branch_switch_cases(f, name, json_data, nodes, mode='combined')
        f.write('            }\n')
        f.write('            }\n')
        f.write('            finally\n')
        f.write('            {\n')
        f.write('                isTransitioning = false;\n')
        f.write('            }\n')
        f.write('        }\n\n')

        # FactoryState()
        f.write(f'        public override Base{name}State FactoryState({name}StateID state_id)\n')
        f.write('        {\n')
        f.write('            switch (state_id)\n')
        f.write('            {\n')
        
        code_label = []
        for node in json_data["transitions"]:
            label = node["fromState"]
            state_id = f"{name}StateID.{label}"
            class_name = f"{name}{label}State"
            if label not in code_label:
                code_label.append(label)
                f.write(f'                case {state_id}: return new {class_name}();\n')
        for node in nodes:
            label = node["data"]["label"]
            node_id = int(node["id"])
            state_id = f"{name}StateID.{label}{node_id:02d}"
            class_name = f"{name}{label}State"
            f.write(f'                case {state_id}: return new {class_name}();\n')
        f.write('                default: return null;\n')
        f.write('            }\n')
        f.write('        }\n')

        f.write('    }\n')
        f.write('}\n')

    # --- 実装クラス {name}StateControl.cs ---
    final_file_path = os.path.join(control_dir, f'{name}StateControl.cs')
    if not os.path.exists(final_file_path):
        with open(final_file_path, 'w', encoding='utf-8') as f:
            f.write('using GameCore.States.ID;\n')
            f.write('using GameCore.States.Managers;\n')
            f.write('using GameCore.States;\n\n')

            f.write('namespace GameCore.States.Control\n{\n')
            f.write(f'    public class {name}StateControl : Base{name}StateControl\n')
            f.write('    {\n')
            f.write('    }\n')
            f.write('}\n')
            



# ============================================================
# Python / JavaScript コード生成（簡易対応版）
# ------------------------------------------------------------
# C#（Unity向け）生成の Enter/Update/Exit フェーズ別アクティブフラグ
# （IsEnterActive(Async) / IsUpdateActive(Async) / IsExitActive(Async)）と
# 同じ考え方を Python / JavaScript 向けにも生成する。
#
# 【スコープ外にしたもの（今回は移植していません）】
# - StateBaseID（番号無しラベルのみのID）とその現在/直前追跡
# - DetailStateBranch群（複数遷移先ごとの条件クラスの自動生成）。
#   複数遷移先を持つノードは、C#版と同様 state.branch_next_state()
#   （JSは state.branchNextState()）をoverrideして自前実装してもらう。
# - manager フィールドのカスタム型システム（ClassData/Bit/Color/Bezier等）。
#   フィールドは列挙するだけで、型はTODOコメント付きで手動設定してもらう。
# - 純粋非同期API（C#のBranchStateAsync相当）。Combined APIで代替可能なため省略。
# ============================================================

def _collect_stack_case_labels(json_data):
    """transitions（スタック/LIFOで使われるラベル）を、C#版と同じ順序で収集する。"""
    labels = []
    for data in json_data.get('transitions', []):
        label = data.get("fromState", {})
        if label and label not in labels:
            labels.append(label)
    return labels


def _collect_node_cases(nodes):
    """
    nodes配列を、言語非依存の「ケース記述」のリストに変換する。
    Python/JavaScript生成の両方がこの1つのトラバース結果を共有する。
    """
    cases = []
    for node in nodes:
        label = node["data"]["label"]
        node_id = int(node["id"])
        targets = node["data"].get("targets", [])
        sub_nodes = [c["label"] for c in node["data"].get("subNodes", [])]
        single_target_id = None
        if len(targets) == 1:
            next_node = targets[0]
            target_label = next(
                (n["data"]["label"] for n in nodes if n["id"] == next_node), None)
            if target_label:
                single_target_id = f'{target_label}{int(next_node):02d}'
        cases.append({
            'state_id': f'{label}{node_id:02d}',
            'targets_len': len(targets),
            'single_target_id': single_target_id,
            'sub_nodes': sub_nodes,
        })
    return cases


# ------------------------------------------------------------
# Python 生成
# ------------------------------------------------------------

def generate_base_python(data_dir):
    """
    Python版の共通基底コード（初回起動時のみ）。
    - base_python/base_state.py
    - base_python/base_state_manager_data.py
    - base_python/base_state_control.py
    - base_python/state_group_tracker.py
    """
    base_dir = os.path.join(data_dir, STATE_DATA, "base_python")
    os.makedirs(base_dir, exist_ok=True)

    base_state_path = os.path.join(base_dir, "base_state.py")
    if not os.path.exists(base_state_path):
        with open(base_state_path, 'w', encoding='utf-8') as f:
            f.write('''"""
base_state.py
ステートの基底クラス（Unity/C#版 BaseState<E,T> に相当）。
Enter/Update/Exitの同期・非同期版と、フェーズ別アクティブフラグ
（Enter/Update/Exit x 同期/非同期の計6個）を持つ。
"""


class CancellationToken:
    """C#のCancellationTokenに相当する簡易実装。"""

    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def is_cancelled(self):
        return self._cancelled


class BaseState:
    def __init__(self):
        self._is_enter_active = True
        self._is_enter_active_async = True
        self._is_update_active = True
        self._is_update_active_async = True
        self._is_exit_active = True
        self._is_exit_active_async = True

        # 使わない側（use_xxx_syncやuse_xxx_asyncがFalse）は、
        # コンストラクタの時点で対応するis_xxx_active(_async)を自動的にFalseにしておく。
        if not self.use_enter_sync:
            self.is_enter_active_off()
        if not self.use_enter_async:
            self.is_enter_active_async_off()
        if not self.use_update_sync:
            self.is_update_active_off()
        if not self.use_update_async:
            self.is_update_active_async_off()
        if not self.use_exit_sync:
            self.is_exit_active_off()
        if not self.use_exit_async:
            self.is_exit_active_async_off()

    # --- フェーズ別アクティブフラグ ---
    @property
    def is_enter_active(self):
        return self._is_enter_active

    def is_enter_active_off(self):
        self._is_enter_active = False

    @property
    def is_enter_active_async(self):
        return self._is_enter_active_async

    def is_enter_active_async_off(self):
        self._is_enter_active_async = False

    @property
    def is_update_active(self):
        return self._is_update_active

    def is_update_active_off(self):
        self._is_update_active = False

    @property
    def is_update_active_async(self):
        return self._is_update_active_async

    def is_update_active_async_off(self):
        self._is_update_active_async = False

    @property
    def is_exit_active(self):
        return self._is_exit_active

    def is_exit_active_off(self):
        self._is_exit_active = False

    @property
    def is_exit_active_async(self):
        return self._is_exit_active_async

    def is_exit_active_async_off(self):
        self._is_exit_active_async = False

    # --- 各フェーズで同期/非同期のどちらを使うか（派生クラスでoverride） ---
    use_enter_sync = True
    use_enter_async = False
    use_update_sync = True
    use_update_async = False
    use_exit_sync = True
    use_exit_async = False

    # --- 同期版ライフサイクル ---
    def enter(self, state_manager_data):
        pass

    def update(self, state_manager_data):
        pass

    def exit(self, state_manager_data):
        pass

    # --- 非同期版ライフサイクル（デフォルトは同期版を呼ぶだけ） ---
    async def enter_async(self, state_manager_data, ct=None):
        self.enter(state_manager_data)
        self.is_enter_active_async_off()

    async def update_async(self, state_manager_data, ct=None):
        self.update(state_manager_data)
        self.is_update_active_async_off()

    async def exit_async(self, state_manager_data, ct=None):
        self.exit(state_manager_data)
        self.is_exit_active_async_off()

    def branch_next_state(self, state_manager_data):
        """遷移先が複数あるノードのStateでoverrideする分岐条件。"""
        return None
''')

    base_manager_data_path = os.path.join(base_dir, "base_state_manager_data.py")
    if not os.path.exists(base_manager_data_path):
        with open(base_manager_data_path, 'w', encoding='utf-8') as f:
            f.write('''"""
base_state_manager_data.py
Unity/C#版 BaseStateManagerData<T> に相当。
"""


class BaseStateManagerData:
    def __init__(self):
        self.now_state_id = None
        self.old_state_id = None
        self.save_state_id = None
        self._stack_id_list = []

    def push_state_id(self, state_id):
        self._stack_id_list.append(state_id)

    def pop_state_id(self):
        """
        NOTE: C#版のPopStateID()と同じく「覗き見(peek)」のみで、
        リストからは取り除かない。実際に取り除くのはpop_up_state_id()。
        """
        if self._stack_id_list:
            return self._stack_id_list[0]
        return None

    def pop_up_state_id(self):
        """スタック先頭を実際に取り除く（C#版のPopUpStateID()に相当）。"""
        if self._stack_id_list:
            self._stack_id_list.pop(0)

    def change_state_now_id(self, new_state_id):
        self.old_state_id = self.now_state_id
        self.now_state_id = new_state_id

    def get_now_state_id(self):
        return self.now_state_id

    def get_old_state_id(self):
        return self.old_state_id
''')

    tracker_path = os.path.join(base_dir, "state_group_tracker.py")
    if not os.path.exists(tracker_path):
        with open(tracker_path, 'w', encoding='utf-8') as f:
            f.write('''"""
state_group_tracker.py
現在アクティブなStateグループと、その1つ前のグループを追跡する
静的トラッカー（Unity/C#版 StateGroupTracker に相当）。
"""


class StateGroupTracker:
    current_group = None
    previous_group = None

    @classmethod
    def change_group(cls, new_group):
        if new_group == cls.current_group:
            return
        cls.previous_group = cls.current_group
        cls.current_group = new_group
''')

    base_control_path = os.path.join(base_dir, "base_state_control.py")
    if not os.path.exists(base_control_path):
        with open(base_control_path, 'w', encoding='utf-8') as f:
            f.write('''"""
base_state_control.py
ステートコントローラーの基底クラス（Unity/C#版 BaseStateControl<T,E,F> に相当）。

Combined API（同期Enter/Update/Exitと非同期Enter/Update/Exitを同時に動かすモード）は、
Enter/Update/Exitの3フェーズそれぞれについて、同期・非同期の両方が完了する
（is_xxx_active / is_xxx_active_async の両方がFalseになる）まで次のフェーズへ
進まない。

・Enter: 完了するまでUpdateへ進まない。
・Update: 完了するまでExit（次への遷移）へ進まない。
・Exit: _exiting_state（Exit対象として退避した旧State）の完了を待ってから、
  次StateのEnterフェーズを発火する（_combined_enter_pendingで待機）。
"""
import asyncio


def _log_async_exception(task):
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        print(f"[StateControl] async exception: {exc!r}")


class BaseStateControl:
    def __init__(self):
        self.state_manager_data = self.create_manager_data()
        self.state = None
        self.is_finish = False
        self.is_transitioning = False

        self._combined_async_update_started = False
        self._exiting_state = None
        self._combined_enter_pending = False
        self._combined_tasks = []

    # --- 派生クラスでoverride ---
    def create_manager_data(self):
        raise NotImplementedError

    def get_init_start_id(self):
        raise NotImplementedError

    def factory_state(self, state_id):
        raise NotImplementedError

    def branch_state(self):
        raise NotImplementedError

    def branch_state_combined(self):
        raise NotImplementedError

    # --- 同期API ---
    def start_state(self, action=None):
        if self.state is not None:
            print("start_state は既に開始済みです。二重呼び出しを無視しました。")
            return
        self._on_start_state(self.get_init_start_id(), action)

    def _on_start_state(self, state_id, action):
        self.state = self.factory_state(state_id)
        self.state_manager_data.change_state_now_id(state_id)
        if action:
            action(self.state_manager_data)
        self.state.enter(self.state_manager_data)

    def update_state(self, befor_action=None, after_action=None):
        if self.state is None:
            self.start_state()
        self._on_update_state(befor_action, after_action)

    def _on_update_state(self, befor_action=None, after_action=None):
        if befor_action:
            befor_action(self.state_manager_data)
        self.state.update(self.state_manager_data)
        if not self.is_transitioning:
            self.branch_state()
        if after_action:
            after_action(self.state_manager_data)

    # --- Combined API ---
    def start_state_combined(self, action=None):
        if self.state is not None:
            print("start_state_combined は既に開始済みです。二重呼び出しを無視しました。")
            return
        self._on_start_state_combined(self.get_init_start_id(), action)

    def _on_start_state_combined(self, state_id, action):
        self.state = self.factory_state(state_id)
        self.state_manager_data.change_state_now_id(state_id)
        if action:
            action(self.state_manager_data)

        self._combined_async_update_started = False
        self._exiting_state = None
        self._combined_enter_pending = False

        if self.state.use_enter_sync:
            self.state.enter(self.state_manager_data)
        if self.state.use_enter_async:
            self._fire_and_forget(self.state.enter_async(self.state_manager_data))

    def update_state_combined(self, befor_action=None, after_action=None):
        if self.state is None:
            self.start_state_combined()
        self._on_update_state_combined(befor_action, after_action)

    def _on_update_state_combined(self, befor_action=None, after_action=None):
        if befor_action:
            befor_action(self.state_manager_data)

        # 直前のbranch_state_combined()でExitを発火済み・次Stateへの切り替え待ちの場合、
        # exitingStateのExitフェーズ（同期・非同期の両方）が完了するまで待つ。
        if self._combined_enter_pending:
            if not self._exiting_state.is_exit_active and not self._exiting_state.is_exit_active_async:
                self._combined_enter_pending = False
                self._exiting_state = None
                if self.state.use_enter_sync:
                    self.state.enter(self.state_manager_data)
                if self.state.use_enter_async:
                    self._fire_and_forget(self.state.enter_async(self.state_manager_data))
            if after_action:
                after_action(self.state_manager_data)
            return

        # Enterフェーズ（同期・非同期の両方）が完了するまではUpdateへ進まない。
        if self.state.is_enter_active or self.state.is_enter_active_async:
            if after_action:
                after_action(self.state_manager_data)
            return

        if self.state.use_update_sync:
            self.state.update(self.state_manager_data)
        if self.state.use_update_async and not self._combined_async_update_started:
            self._combined_async_update_started = True
            self._fire_and_forget(self.state.update_async(self.state_manager_data))

        # Updateフェーズ（同期・非同期の両方）が完了した時だけ次へ進む。
        if not self.is_transitioning and not self.state.is_update_active and not self.state.is_update_active_async:
            self.branch_state_combined()

        if after_action:
            after_action(self.state_manager_data)

    def _fire_and_forget(self, coro):
        task = asyncio.ensure_future(coro)
        task.add_done_callback(_log_async_exception)
        self._combined_tasks.append(task)
        return task

    # --- 生成コードから呼ばれる遷移ヘルパー ---
    def _begin_exit_combined(self, next_state):
        """
        現在のstateをexitingStateとして退避してExitを発火し、
        次state（まだEnterは呼ばない）に切り替えてExit完了待ちにする。
        """
        old = self.state
        self._exiting_state = old
        if old.use_exit_sync:
            old.exit(self.state_manager_data)
        if old.use_exit_async:
            self._fire_and_forget(old.exit_async(self.state_manager_data))
        self.state = next_state
        self._combined_async_update_started = False
        self._combined_enter_pending = True

    def _begin_exit_finish(self):
        """次stateが無い（ステートマシン終了）場合のExit発火。"""
        old = self.state
        if old.use_exit_sync:
            old.exit(self.state_manager_data)
        if old.use_exit_async:
            self._fire_and_forget(old.exit_async(self.state_manager_data))
        self.is_finish = True
''')


def generate_state_id_python(file_path, name, json_data):
    py_dir = os.path.join(file_path, "Python")
    os.makedirs(py_dir, exist_ok=True)
    file_id_path = os.path.join(py_dir, f'{name}StateID.py')

    if not json_data or not json_data.get('nodes'):
        return

    members = []
    for label in _collect_stack_case_labels(json_data):
        members.append(label)
    for data in json_data.get('nodes', []):
        label = data.get("data", {}).get("label", "")
        node_id = data.get("id", 0)
        if label:
            members.append(f'{label}{int(node_id):02d}')

    with open(file_id_path, 'w', encoding='utf-8') as f:
        f.write('from enum import IntEnum\n\n\n')
        f.write(f'class {name}StateID(IntEnum):\n')
        f.write('    NONE = 0\n')
        for i, member in enumerate(members, start=1):
            f.write(f'    {member} = {i}\n')
        f.write(f'    MAX = {len(members) + 1}\n')


def generate_state_manager_data_python(file_path, name, json_data):
    py_dir = os.path.join(file_path, "Python")
    os.makedirs(py_dir, exist_ok=True)
    file_manager_path = os.path.join(py_dir, f'{name}StateManagerData.py')
    if os.path.exists(file_manager_path):
        return  # 本実装は上書きしない（C#版の{name}StateManagerData.csと同じ扱い）

    manager_fields = json_data.get('manager', [])
    with open(file_manager_path, 'w', encoding='utf-8') as f:
        f.write('from base_python.base_state_manager_data import BaseStateManagerData\n\n\n')
        f.write(f'class {name}StateManagerData(BaseStateManagerData):\n')
        f.write('    """\n')
        f.write(f'    NOTE: managerフィールドの型はC#版（Base{name}StateManagerData.cs）の\n')
        f.write('    カスタム型システム（ClassData/Bit/Color/Bezier等）に依存しているため、\n')
        f.write('    ここでは移植していません。必要なフィールドは手動で追加してください。\n')
        f.write('    """\n\n')
        f.write('    def __init__(self):\n')
        f.write('        super().__init__()\n')
        if manager_fields:
            for item in manager_fields:
                fname = item.get('name', 'value')
                f.write(f'        self.{fname} = None  # TODO: 型を設定してください\n')
        else:
            f.write('        pass\n')


def generate_state_classes_python(file_path, name, json_data):
    py_dir = os.path.join(file_path, "Python")
    os.makedirs(py_dir, exist_ok=True)
    file_states_path = os.path.join(py_dir, f'{name}States.py')
    if os.path.exists(file_states_path):
        return  # 本実装は上書きしない（C#版の{name}{label}State.csと同じ扱い）

    labels = []
    label_multi = {}
    for node in json_data.get('nodes', []):
        label = node.get("data", {}).get("label", "")
        if not label:
            continue
        if label not in labels:
            labels.append(label)
            label_multi[label] = False
        if len(node.get("data", {}).get("targets", [])) > 1:
            label_multi[label] = True
    for node in json_data.get('transitions', []):
        label = node.get("fromState", "")
        if label and label not in labels:
            labels.append(label)
            label_multi[label] = False

    if not labels:
        return

    with open(file_states_path, 'w', encoding='utf-8') as f:
        f.write('from base_python.base_state import BaseState\n\n\n')
        f.write(f'class Base{name}State(BaseState):\n')
        f.write('    pass\n\n\n')
        for label in labels:
            f.write(f'class {name}{label}State(Base{name}State):\n')
            f.write('    def enter(self, state_manager_data):\n')
            f.write('        self.is_enter_active_off()\n\n')
            f.write('    def update(self, state_manager_data):\n')
            f.write('        self.is_update_active_off()\n\n')
            f.write('    def exit(self, state_manager_data):\n')
            f.write('        self.is_exit_active_off()\n\n')
            f.write('    async def enter_async(self, state_manager_data, ct=None):\n')
            f.write('        self.is_enter_active_async_off()\n\n')
            f.write('    async def update_async(self, state_manager_data, ct=None):\n')
            f.write('        self.is_update_active_async_off()\n\n')
            f.write('    async def exit_async(self, state_manager_data, ct=None):\n')
            f.write('        self.is_exit_active_async_off()\n')
            if label_multi.get(label):
                f.write('\n    def branch_next_state(self, state_manager_data):\n')
                f.write('        # TODO: 複数遷移先の分岐条件をここに実装してください\n')
                f.write('        return None\n')
            f.write('\n\n')


def _write_branch_cases_python(f, name, json_data, nodes, mode):
    """
    mode: 'sync' | 'combined'
    C#版 _write_branch_switch_cases のロジックをPythonに移植した簡易版。
    DetailStateBranch（複数遷移先ごとの条件クラスの自動生成）は移植しておらず、
    複数遷移先を持つノードは self.state.branch_next_state() のoverrideに委ねる。
    """
    ctx = {'first': True}

    def head(cond):
        kw = 'if' if ctx['first'] else 'elif'
        ctx['first'] = False
        f.write(f'        {kw} {cond}:\n')

    def write_exit():
        if mode == 'combined':
            f.write('            pass  # Exitはself._begin_exit_combined()/_begin_exit_finish()内で発火\n')
        else:
            f.write('            self.state.exit(self.state_manager_data)\n')

    def write_enter_or_begin(state_var):
        if mode == 'combined':
            f.write(f'            self._begin_exit_combined({state_var})\n')
        else:
            f.write(f'            self.state = {state_var}\n')
            f.write('            self.state.enter(self.state_manager_data)\n')

    def write_finish_inline(indent):
        if mode == 'combined':
            f.write(f'{indent}self._begin_exit_finish()\n')
        else:
            f.write(f'{indent}self.is_finish = True\n')

    code_label = []
    for node in json_data.get('transitions', []):
        label = node["fromState"]
        if label in code_label:
            continue
        code_label.append(label)
        head(f'state_id == {name}StateID.{label}')
        write_exit()
        f.write('            self.state_manager_data.pop_up_state_id()\n')
        f.write('            popped_id = self.state_manager_data.pop_state_id()\n')
        f.write('            if popped_id is None:\n')
        f.write('                popped_id = self.state_manager_data.save_state_id\n')
        f.write('            if popped_id is None:\n')
        f.write(f'                self.state_manager_data.change_state_now_id({name}StateID.NONE)\n')
        write_finish_inline('                ')
        f.write('                return\n')
        f.write('            self.state_manager_data.change_state_now_id(popped_id)\n')
        f.write('            self.state_manager_data.save_state_id = None\n')
        f.write('            next_state = self.factory_state(popped_id)\n')
        f.write('            if next_state is None:\n')
        f.write(f'                self.state_manager_data.change_state_now_id({name}StateID.NONE)\n')
        f.write('                self.state_manager_data.save_state_id = None\n')
        write_finish_inline('                ')
        f.write('                return\n')
        write_enter_or_begin('next_state')
        f.write('            return\n')

    for node in nodes:
        label = node["data"]["label"]
        node_id = int(node["id"])
        targets = node["data"].get("targets", [])
        sub_nodes = node["data"].get("subNodes", [])

        head(f'state_id == {name}StateID.{label}{node_id:02d}')
        write_exit()
        f.write('            self.state_manager_data.pop_up_state_id()\n')

        if not targets:
            if sub_nodes:
                f.write('            self.state_manager_data.save_state_id = None\n')
                for child in sub_nodes:
                    child_label = child["label"]
                    f.write(f'            self.state_manager_data.push_state_id({name}StateID.{child_label})\n')
                f.write('            next_id = self.state_manager_data.pop_state_id()\n')
                f.write('            next_state = self.factory_state(next_id)\n')
                f.write('            if next_state is None:\n')
                f.write(f'                self.state_manager_data.change_state_now_id({name}StateID.NONE)\n')
                f.write('                self.state_manager_data.save_state_id = None\n')
                write_finish_inline('                ')
                f.write('                return\n')
                write_enter_or_begin('next_state')
                f.write('            return\n')
            else:
                write_finish_inline('            ')
                f.write('            return\n')
        elif len(targets) == 1:
            next_node = targets[0]
            target_label = next(
                (n["data"]["label"] for n in nodes if n["id"] == next_node), None)
            if target_label:
                f.write(f'            next_id = {name}StateID.{target_label}{int(next_node):02d}\n')
                if sub_nodes:
                    f.write('            self.state_manager_data.save_state_id = next_id\n')
                    for child in sub_nodes:
                        child_label = child["label"]
                        f.write(f'            self.state_manager_data.push_state_id({name}StateID.{child_label})\n')
                    f.write('            self.state_manager_data.push_state_id(next_id)\n')
                    f.write('            next_id = self.state_manager_data.pop_state_id()\n')
                else:
                    f.write('            self.state_manager_data.change_state_now_id(next_id)\n')
                f.write('            next_state = self.factory_state(next_id)\n')
                f.write('            if next_state is None:\n')
                f.write(f'                self.state_manager_data.change_state_now_id({name}StateID.NONE)\n')
                f.write('                self.state_manager_data.save_state_id = None\n')
                write_finish_inline('                ')
                f.write('                return\n')
                write_enter_or_begin('next_state')
                f.write('            return\n')
        else:
            f.write('            next_id = self.state.branch_next_state(self.state_manager_data)\n')
            if sub_nodes:
                f.write('            self.state_manager_data.save_state_id = next_id\n')
                for child in sub_nodes:
                    child_label = child["label"]
                    f.write(f'            self.state_manager_data.push_state_id({name}StateID.{child_label})\n')
                f.write('            self.state_manager_data.push_state_id(next_id)\n')
                f.write('            next_id = self.state_manager_data.pop_state_id()\n')
            else:
                f.write('            self.state_manager_data.change_state_now_id(next_id)\n')
            f.write('            if next_id is None:\n')
            f.write(f'                self.state_manager_data.change_state_now_id({name}StateID.NONE)\n')
            f.write('                self.state_manager_data.save_state_id = None\n')
            write_finish_inline('                ')
            f.write('                return\n')
            f.write('            next_state = self.factory_state(next_id)\n')
            f.write('            if next_state is None:\n')
            f.write(f'                self.state_manager_data.change_state_now_id({name}StateID.NONE)\n')
            f.write('                self.state_manager_data.save_state_id = None\n')
            write_finish_inline('                ')
            f.write('                return\n')
            write_enter_or_begin('next_state')
            f.write('            return\n')

    if ctx['first']:
        f.write('        if False:\n')
        f.write('            pass\n')
    f.write('        else:\n')
    f.write('            return\n')


def generate_control_classes_python(file_path, name, json_data):
    py_dir = os.path.join(file_path, "Python")
    os.makedirs(py_dir, exist_ok=True)
    file_control_path = os.path.join(py_dir, f'{name}StateControl.py')

    nodes = json_data.get('nodes', [])
    if not nodes:
        return

    init_node = next((n for n in nodes if int(n["id"]) == 1), nodes[0])
    init_label = init_node["data"]["label"]
    init_id = int(init_node["id"])
    init_state_id = f"{name}StateID.{init_label}{init_id:02d}"

    labels = []
    for node in nodes:
        label = node["data"]["label"]
        if label not in labels:
            labels.append(label)
    stack_labels = _collect_stack_case_labels(json_data)
    for label in stack_labels:
        if label not in labels:
            labels.append(label)

    with open(file_control_path, 'w', encoding='utf-8') as f:
        f.write('from base_python.base_state_control import BaseStateControl\n')
        f.write(f'from .{name}StateID import {name}StateID\n')
        f.write(f'from .{name}StateManagerData import {name}StateManagerData\n')
        f.write(f'from .{name}States import (\n')
        for label in labels:
            f.write(f'    {name}{label}State,\n')
        f.write(')\n\n\n')

        f.write(f'class {name}StateControl(BaseStateControl):\n')
        f.write(f'    GROUP_ID = "{name}"\n\n')

        f.write('    def create_manager_data(self):\n')
        f.write(f'        return {name}StateManagerData()\n\n')

        f.write('    def get_init_start_id(self):\n')
        f.write(f'        return {init_state_id}\n\n')

        f.write('    def factory_state(self, state_id):\n')
        f.write('        mapping = self._factory_mapping()\n')
        f.write('        factory = mapping.get(state_id)\n')
        f.write('        return factory() if factory else None\n\n')

        f.write('    def _factory_mapping(self):\n')
        f.write('        return {\n')
        written = set()
        for label in stack_labels:
            f.write(f'            {name}StateID.{label}: {name}{label}State,\n')
            written.add(f'{label}')
        for node in nodes:
            label = node["data"]["label"]
            node_id = int(node["id"])
            f.write(f'            {name}StateID.{label}{node_id:02d}: {name}{label}State,\n')
        f.write('        }\n\n')

        f.write('    def branch_state(self):\n')
        f.write('        if self.state.is_update_active:\n')
        f.write('            return\n')
        f.write('        self.is_transitioning = True\n')
        f.write('        try:\n')
        f.write('            state_id = self.state_manager_data.pop_state_id()\n')
        f.write('            if state_id is None:\n')
        f.write('                state_id = self.state_manager_data.get_now_state_id()\n')
        f.write('            self._branch_switch_sync(state_id)\n')
        f.write('        finally:\n')
        f.write('            self.is_transitioning = False\n\n')

        f.write('    def _branch_switch_sync(self, state_id):\n')
        _write_branch_cases_python(f, name, json_data, nodes, mode='sync')
        f.write('\n')

        f.write('    def branch_state_combined(self):\n')
        f.write('        self.is_transitioning = True\n')
        f.write('        try:\n')
        f.write('            state_id = self.state_manager_data.pop_state_id()\n')
        f.write('            if state_id is None:\n')
        f.write('                state_id = self.state_manager_data.get_now_state_id()\n')
        f.write('            self._branch_switch_combined(state_id)\n')
        f.write('        finally:\n')
        f.write('            self.is_transitioning = False\n\n')

        f.write('    def _branch_switch_combined(self, state_id):\n')
        _write_branch_cases_python(f, name, json_data, nodes, mode='combined')


# ------------------------------------------------------------
# JavaScript 生成
# ------------------------------------------------------------

def generate_base_javascript(data_dir):
    """
    JavaScript版の共通基底コード（初回起動時のみ）。ES Modules形式。
    - base_javascript/BaseState.js
    - base_javascript/BaseStateManagerData.js
    - base_javascript/BaseStateControl.js
    - base_javascript/StateGroupTracker.js
    """
    base_dir = os.path.join(data_dir, STATE_DATA, "base_javascript")
    os.makedirs(base_dir, exist_ok=True)

    base_state_path = os.path.join(base_dir, "BaseState.js")
    if not os.path.exists(base_state_path):
        with open(base_state_path, 'w', encoding='utf-8') as f:
            f.write('''/**
 * BaseState.js
 * ステートの基底クラス（Unity/C#版 BaseState<E,T> に相当）。
 * Enter/Update/Exitの同期・非同期版と、フェーズ別アクティブフラグ
 * （Enter/Update/Exit x 同期/非同期の計6個）を持つ。
 */

export class CancellationToken {
    constructor() {
        this._cancelled = false;
    }
    cancel() {
        this._cancelled = true;
    }
    get isCancelled() {
        return this._cancelled;
    }
}

export class BaseState {
    constructor() {
        this._isEnterActive = true;
        this._isEnterActiveAsync = true;
        this._isUpdateActive = true;
        this._isUpdateActiveAsync = true;
        this._isExitActive = true;
        this._isExitActiveAsync = true;

        // 使わない側（useXxxSyncやuseXxxAsyncがfalse）は、
        // コンストラクタの時点で対応するisXxxActive(Async)を自動的にfalseにしておく。
        if (!this.useEnterSync) this.isEnterActiveOff();
        if (!this.useEnterAsync) this.isEnterActiveAsyncOff();
        if (!this.useUpdateSync) this.isUpdateActiveOff();
        if (!this.useUpdateAsync) this.isUpdateActiveAsyncOff();
        if (!this.useExitSync) this.isExitActiveOff();
        if (!this.useExitAsync) this.isExitActiveAsyncOff();
    }

    // --- フェーズ別アクティブフラグ ---
    get isEnterActive() { return this._isEnterActive; }
    isEnterActiveOff() { this._isEnterActive = false; }
    get isEnterActiveAsync() { return this._isEnterActiveAsync; }
    isEnterActiveAsyncOff() { this._isEnterActiveAsync = false; }

    get isUpdateActive() { return this._isUpdateActive; }
    isUpdateActiveOff() { this._isUpdateActive = false; }
    get isUpdateActiveAsync() { return this._isUpdateActiveAsync; }
    isUpdateActiveAsyncOff() { this._isUpdateActiveAsync = false; }

    get isExitActive() { return this._isExitActive; }
    isExitActiveOff() { this._isExitActive = false; }
    get isExitActiveAsync() { return this._isExitActiveAsync; }
    isExitActiveAsyncOff() { this._isExitActiveAsync = false; }

    // --- 各フェーズで同期/非同期のどちらを使うか（派生クラスでoverride） ---
    get useEnterSync() { return true; }
    get useEnterAsync() { return false; }
    get useUpdateSync() { return true; }
    get useUpdateAsync() { return false; }
    get useExitSync() { return true; }
    get useExitAsync() { return false; }

    // --- 同期版ライフサイクル ---
    enter(stateManagerData) {}
    update(stateManagerData) {}
    exit(stateManagerData) {}

    // --- 非同期版ライフサイクル（デフォルトは同期版を呼ぶだけ） ---
    async enterAsync(stateManagerData, ct) {
        this.enter(stateManagerData);
        this.isEnterActiveAsyncOff();
    }
    async updateAsync(stateManagerData, ct) {
        this.update(stateManagerData);
        this.isUpdateActiveAsyncOff();
    }
    async exitAsync(stateManagerData, ct) {
        this.exit(stateManagerData);
        this.isExitActiveAsyncOff();
    }

    /** 遷移先が複数あるノードのStateでoverrideする分岐条件。 */
    branchNextState(stateManagerData) {
        return null;
    }
}
''')

    base_manager_data_path = os.path.join(base_dir, "BaseStateManagerData.js")
    if not os.path.exists(base_manager_data_path):
        with open(base_manager_data_path, 'w', encoding='utf-8') as f:
            f.write('''/**
 * BaseStateManagerData.js
 * Unity/C#版 BaseStateManagerData<T> に相当。
 */

export class BaseStateManagerData {
    constructor() {
        this.nowStateId = null;
        this.oldStateId = null;
        this.saveStateId = null;
        this._stackIdList = [];
    }

    pushStateId(stateId) {
        this._stackIdList.push(stateId);
    }

    /**
     * NOTE: C#版のPopStateID()と同じく「覗き見(peek)」のみで、
     * リストからは取り除かない。実際に取り除くのはpopUpStateId()。
     */
    popStateId() {
        if (this._stackIdList.length > 0) {
            return this._stackIdList[0];
        }
        return null;
    }

    /** スタック先頭を実際に取り除く（C#版のPopUpStateID()に相当）。 */
    popUpStateId() {
        if (this._stackIdList.length > 0) {
            this._stackIdList.shift();
        }
    }

    changeStateNowId(newStateId) {
        this.oldStateId = this.nowStateId;
        this.nowStateId = newStateId;
    }

    getNowStateId() {
        return this.nowStateId;
    }

    getOldStateId() {
        return this.oldStateId;
    }
}
''')

    tracker_path = os.path.join(base_dir, "StateGroupTracker.js")
    if not os.path.exists(tracker_path):
        with open(tracker_path, 'w', encoding='utf-8') as f:
            f.write('''/**
 * StateGroupTracker.js
 * 現在アクティブなStateグループと、その1つ前のグループを追跡する
 * 静的トラッカー（Unity/C#版 StateGroupTracker に相当）。
 */

export class StateGroupTracker {
    static currentGroup = null;
    static previousGroup = null;

    static changeGroup(newGroup) {
        if (newGroup === StateGroupTracker.currentGroup) return;
        StateGroupTracker.previousGroup = StateGroupTracker.currentGroup;
        StateGroupTracker.currentGroup = newGroup;
    }
}
''')

    base_control_path = os.path.join(base_dir, "BaseStateControl.js")
    if not os.path.exists(base_control_path):
        with open(base_control_path, 'w', encoding='utf-8') as f:
            f.write('''/**
 * BaseStateControl.js
 * ステートコントローラーの基底クラス（Unity/C#版 BaseStateControl<T,E,F> に相当）。
 *
 * Combined API（同期Enter/Update/Exitと非同期Enter/Update/Exitを同時に動かすモード）は、
 * Enter/Update/Exitの3フェーズそれぞれについて、同期・非同期の両方が完了する
 * （isXxxActive / isXxxActiveAsync の両方がfalseになる）まで次のフェーズへ進まない。
 *
 * ・Enter: 完了するまでUpdateへ進まない。
 * ・Update: 完了するまでExit（次への遷移）へ進まない。
 * ・Exit: exitingState（Exit対象として退避した旧State）の完了を待ってから、
 *   次StateのEnterフェーズを発火する（combinedEnterPendingで待機）。
 */

function logAsyncException(err) {
    console.error("[StateControl] async exception:", err);
}

export class BaseStateControl {
    constructor() {
        this.stateManagerData = this.createManagerData();
        this.state = null;
        this.isFinish = false;
        this.isTransitioning = false;

        this._combinedAsyncUpdateStarted = false;
        this._exitingState = null;
        this._combinedEnterPending = false;
    }

    // --- 派生クラスでoverride ---
    createManagerData() { throw new Error("not implemented"); }
    getInitStartId() { throw new Error("not implemented"); }
    factoryState(stateId) { throw new Error("not implemented"); }
    branchState() { throw new Error("not implemented"); }
    branchStateCombined() { throw new Error("not implemented"); }

    // --- 同期API ---
    startState(action = null) {
        if (this.state !== null) {
            console.warn("startState は既に開始済みです。二重呼び出しを無視しました。");
            return;
        }
        this._onStartState(this.getInitStartId(), action);
    }

    _onStartState(stateId, action) {
        this.state = this.factoryState(stateId);
        this.stateManagerData.changeStateNowId(stateId);
        if (action) action(this.stateManagerData);
        this.state.enter(this.stateManagerData);
    }

    updateState(beforAction = null, afterAction = null) {
        if (this.state === null) this.startState();
        this._onUpdateState(beforAction, afterAction);
    }

    _onUpdateState(beforAction = null, afterAction = null) {
        if (beforAction) beforAction(this.stateManagerData);
        this.state.update(this.stateManagerData);
        if (!this.isTransitioning) this.branchState();
        if (afterAction) afterAction(this.stateManagerData);
    }

    // --- Combined API ---
    startStateCombined(action = null) {
        if (this.state !== null) {
            console.warn("startStateCombined は既に開始済みです。二重呼び出しを無視しました。");
            return;
        }
        this._onStartStateCombined(this.getInitStartId(), action);
    }

    _onStartStateCombined(stateId, action) {
        this.state = this.factoryState(stateId);
        this.stateManagerData.changeStateNowId(stateId);
        if (action) action(this.stateManagerData);

        this._combinedAsyncUpdateStarted = false;
        this._exitingState = null;
        this._combinedEnterPending = false;

        if (this.state.useEnterSync) this.state.enter(this.stateManagerData);
        if (this.state.useEnterAsync) {
            this.state.enterAsync(this.stateManagerData).catch(logAsyncException);
        }
    }

    updateStateCombined(beforAction = null, afterAction = null) {
        if (this.state === null) this.startStateCombined();
        this._onUpdateStateCombined(beforAction, afterAction);
    }

    _onUpdateStateCombined(beforAction = null, afterAction = null) {
        if (beforAction) beforAction(this.stateManagerData);

        // 直前のbranchStateCombined()でExitを発火済み・次Stateへの切り替え待ちの場合、
        // exitingStateのExitフェーズ（同期・非同期の両方）が完了するまで待つ。
        if (this._combinedEnterPending) {
            if (!this._exitingState.isExitActive && !this._exitingState.isExitActiveAsync) {
                this._combinedEnterPending = false;
                this._exitingState = null;
                if (this.state.useEnterSync) this.state.enter(this.stateManagerData);
                if (this.state.useEnterAsync) {
                    this.state.enterAsync(this.stateManagerData).catch(logAsyncException);
                }
            }
            if (afterAction) afterAction(this.stateManagerData);
            return;
        }

        // Enterフェーズ（同期・非同期の両方）が完了するまではUpdateへ進まない。
        if (this.state.isEnterActive || this.state.isEnterActiveAsync) {
            if (afterAction) afterAction(this.stateManagerData);
            return;
        }

        if (this.state.useUpdateSync) this.state.update(this.stateManagerData);
        if (this.state.useUpdateAsync && !this._combinedAsyncUpdateStarted) {
            this._combinedAsyncUpdateStarted = true;
            this.state.updateAsync(this.stateManagerData).catch(logAsyncException);
        }

        // Updateフェーズ（同期・非同期の両方）が完了した時だけ次へ進む。
        if (!this.isTransitioning && !this.state.isUpdateActive && !this.state.isUpdateActiveAsync) {
            this.branchStateCombined();
        }

        if (afterAction) afterAction(this.stateManagerData);
    }

    // --- 生成コードから呼ばれる遷移ヘルパー ---

    /**
     * 現在のstateをexitingStateとして退避してExitを発火し、
     * 次state（まだEnterは呼ばない）に切り替えてExit完了待ちにする。
     */
    _beginExitCombined(nextState) {
        const old = this.state;
        this._exitingState = old;
        if (old.useExitSync) old.exit(this.stateManagerData);
        if (old.useExitAsync) {
            old.exitAsync(this.stateManagerData).catch(logAsyncException);
        }
        this.state = nextState;
        this._combinedAsyncUpdateStarted = false;
        this._combinedEnterPending = true;
    }

    /** 次stateが無い（ステートマシン終了）場合のExit発火。 */
    _beginExitFinish() {
        const old = this.state;
        if (old.useExitSync) old.exit(this.stateManagerData);
        if (old.useExitAsync) {
            old.exitAsync(this.stateManagerData).catch(logAsyncException);
        }
        this.isFinish = true;
    }
}
''')


def generate_state_id_javascript(file_path, name, json_data):
    js_dir = os.path.join(file_path, "JavaScript")
    os.makedirs(js_dir, exist_ok=True)
    file_id_path = os.path.join(js_dir, f'{name}StateID.js')

    if not json_data or not json_data.get('nodes'):
        return

    members = []
    for label in _collect_stack_case_labels(json_data):
        members.append(label)
    for data in json_data.get('nodes', []):
        label = data.get("data", {}).get("label", "")
        node_id = data.get("id", 0)
        if label:
            members.append(f'{label}{int(node_id):02d}')

    with open(file_id_path, 'w', encoding='utf-8') as f:
        f.write(f'/** {name}StateID.js */\n\n')
        f.write(f'export const {name}StateID = Object.freeze({{\n')
        f.write('    NONE: 0,\n')
        for i, member in enumerate(members, start=1):
            f.write(f'    {member}: {i},\n')
        f.write(f'    MAX: {len(members) + 1},\n')
        f.write('});\n')


def generate_state_manager_data_javascript(file_path, name, json_data):
    js_dir = os.path.join(file_path, "JavaScript")
    os.makedirs(js_dir, exist_ok=True)
    file_manager_path = os.path.join(js_dir, f'{name}StateManagerData.js')
    if os.path.exists(file_manager_path):
        return  # 本実装は上書きしない（C#版の{name}StateManagerData.csと同じ扱い）

    manager_fields = json_data.get('manager', [])
    with open(file_manager_path, 'w', encoding='utf-8') as f:
        f.write('import { BaseStateManagerData } from "../../base_javascript/BaseStateManagerData.js";\n\n')
        f.write('/**\n')
        f.write(f' * NOTE: managerフィールドの型はC#版（Base{name}StateManagerData.cs）の\n')
        f.write(' * カスタム型システム（ClassData/Bit/Color/Bezier等）に依存しているため、\n')
        f.write(' * ここでは移植していません。必要なフィールドは手動で追加してください。\n')
        f.write(' */\n')
        f.write(f'export class {name}StateManagerData extends BaseStateManagerData {{\n')
        f.write('    constructor() {\n')
        f.write('        super();\n')
        for item in manager_fields:
            fname = item.get('name', 'value')
            f.write(f'        this.{fname} = null; // TODO: 型を設定してください\n')
        f.write('    }\n')
        f.write('}\n')


def generate_state_classes_javascript(file_path, name, json_data):
    js_dir = os.path.join(file_path, "JavaScript")
    os.makedirs(js_dir, exist_ok=True)
    file_states_path = os.path.join(js_dir, f'{name}States.js')
    if os.path.exists(file_states_path):
        return  # 本実装は上書きしない（C#版の{name}{label}State.csと同じ扱い）

    labels = []
    label_multi = {}
    for node in json_data.get('nodes', []):
        label = node.get("data", {}).get("label", "")
        if not label:
            continue
        if label not in labels:
            labels.append(label)
            label_multi[label] = False
        if len(node.get("data", {}).get("targets", [])) > 1:
            label_multi[label] = True
    for node in json_data.get('transitions', []):
        label = node.get("fromState", "")
        if label and label not in labels:
            labels.append(label)
            label_multi[label] = False

    if not labels:
        return

    with open(file_states_path, 'w', encoding='utf-8') as f:
        f.write('import { BaseState } from "../../base_javascript/BaseState.js";\n\n')
        f.write(f'export class Base{name}State extends BaseState {{}}\n\n')
        for label in labels:
            f.write(f'export class {name}{label}State extends Base{name}State {{\n')
            f.write('    enter(stateManagerData) {\n')
            f.write('        this.isEnterActiveOff();\n')
            f.write('    }\n\n')
            f.write('    update(stateManagerData) {\n')
            f.write('        this.isUpdateActiveOff();\n')
            f.write('    }\n\n')
            f.write('    exit(stateManagerData) {\n')
            f.write('        this.isExitActiveOff();\n')
            f.write('    }\n\n')
            f.write('    async enterAsync(stateManagerData, ct) {\n')
            f.write('        this.isEnterActiveAsyncOff();\n')
            f.write('    }\n\n')
            f.write('    async updateAsync(stateManagerData, ct) {\n')
            f.write('        this.isUpdateActiveAsyncOff();\n')
            f.write('    }\n\n')
            f.write('    async exitAsync(stateManagerData, ct) {\n')
            f.write('        this.isExitActiveAsyncOff();\n')
            f.write('    }\n')
            if label_multi.get(label):
                f.write('\n    branchNextState(stateManagerData) {\n')
                f.write('        // TODO: 複数遷移先の分岐条件をここに実装してください\n')
                f.write('        return null;\n')
                f.write('    }\n')
            f.write('}\n\n')


def _write_branch_cases_javascript(f, name, json_data, nodes, mode):
    """
    mode: 'sync' | 'combined'
    C#版 _write_branch_switch_cases のロジックをJavaScriptに移植した簡易版。
    """
    def write_exit():
        if mode == 'combined':
            f.write('                // Exitはthis._beginExitCombined()/_beginExitFinish()内で発火\n')
        else:
            f.write('                this.state.exit(this.stateManagerData);\n')

    def write_enter_or_begin(state_var):
        if mode == 'combined':
            f.write(f'                this._beginExitCombined({state_var});\n')
        else:
            f.write(f'                this.state = {state_var};\n')
            f.write('                this.state.enter(this.stateManagerData);\n')

    def write_finish_inline(indent):
        if mode == 'combined':
            f.write(f'{indent}this._beginExitFinish();\n')
        else:
            f.write(f'{indent}this.isFinish = true;\n')

    code_label = []
    for node in json_data.get('transitions', []):
        label = node["fromState"]
        if label in code_label:
            continue
        code_label.append(label)
        f.write(f'            case {name}StateID.{label}: {{\n')
        write_exit()
        f.write('                this.stateManagerData.popUpStateId();\n')
        f.write('                let poppedId = this.stateManagerData.popStateId();\n')
        f.write('                if (poppedId === null) poppedId = this.stateManagerData.saveStateId;\n')
        f.write('                if (poppedId === null) {\n')
        f.write(f'                    this.stateManagerData.changeStateNowId({name}StateID.NONE);\n')
        write_finish_inline('                    ')
        f.write('                    return;\n')
        f.write('                }\n')
        f.write('                this.stateManagerData.changeStateNowId(poppedId);\n')
        f.write('                this.stateManagerData.saveStateId = null;\n')
        f.write('                const nextState = this.factoryState(poppedId);\n')
        f.write('                if (nextState === null) {\n')
        f.write(f'                    this.stateManagerData.changeStateNowId({name}StateID.NONE);\n')
        f.write('                    this.stateManagerData.saveStateId = null;\n')
        write_finish_inline('                    ')
        f.write('                    return;\n')
        f.write('                }\n')
        write_enter_or_begin('nextState')
        f.write('                return;\n')
        f.write('            }\n')

    for node in nodes:
        label = node["data"]["label"]
        node_id = int(node["id"])
        targets = node["data"].get("targets", [])
        sub_nodes = node["data"].get("subNodes", [])

        f.write(f'            case {name}StateID.{label}{node_id:02d}: {{\n')
        write_exit()
        f.write('                this.stateManagerData.popUpStateId();\n')

        if not targets:
            if sub_nodes:
                f.write('                this.stateManagerData.saveStateId = null;\n')
                for child in sub_nodes:
                    child_label = child["label"]
                    f.write(f'                this.stateManagerData.pushStateId({name}StateID.{child_label});\n')
                f.write('                const nextId = this.stateManagerData.popStateId();\n')
                f.write('                const nextState = this.factoryState(nextId);\n')
                f.write('                if (nextState === null) {\n')
                f.write(f'                    this.stateManagerData.changeStateNowId({name}StateID.NONE);\n')
                f.write('                    this.stateManagerData.saveStateId = null;\n')
                write_finish_inline('                    ')
                f.write('                    return;\n')
                f.write('                }\n')
                write_enter_or_begin('nextState')
                f.write('                return;\n')
            else:
                write_finish_inline('                ')
                f.write('                return;\n')
        elif len(targets) == 1:
            next_node = targets[0]
            target_label = next(
                (n["data"]["label"] for n in nodes if n["id"] == next_node), None)
            if target_label:
                f.write(f'                let nextId = {name}StateID.{target_label}{int(next_node):02d};\n')
                if sub_nodes:
                    f.write('                this.stateManagerData.saveStateId = nextId;\n')
                    for child in sub_nodes:
                        child_label = child["label"]
                        f.write(f'                this.stateManagerData.pushStateId({name}StateID.{child_label});\n')
                    f.write('                this.stateManagerData.pushStateId(nextId);\n')
                    f.write('                nextId = this.stateManagerData.popStateId();\n')
                else:
                    f.write('                this.stateManagerData.changeStateNowId(nextId);\n')
                f.write('                const nextState = this.factoryState(nextId);\n')
                f.write('                if (nextState === null) {\n')
                f.write(f'                    this.stateManagerData.changeStateNowId({name}StateID.NONE);\n')
                f.write('                    this.stateManagerData.saveStateId = null;\n')
                write_finish_inline('                    ')
                f.write('                    return;\n')
                f.write('                }\n')
                write_enter_or_begin('nextState')
                f.write('                return;\n')
        else:
            f.write('                let nextId = this.state.branchNextState(this.stateManagerData);\n')
            if sub_nodes:
                f.write('                this.stateManagerData.saveStateId = nextId;\n')
                for child in sub_nodes:
                    child_label = child["label"]
                    f.write(f'                this.stateManagerData.pushStateId({name}StateID.{child_label});\n')
                f.write('                this.stateManagerData.pushStateId(nextId);\n')
                f.write('                nextId = this.stateManagerData.popStateId();\n')
            else:
                f.write('                this.stateManagerData.changeStateNowId(nextId);\n')
            f.write('                if (nextId === null) {\n')
            f.write(f'                    this.stateManagerData.changeStateNowId({name}StateID.NONE);\n')
            f.write('                    this.stateManagerData.saveStateId = null;\n')
            write_finish_inline('                    ')
            f.write('                    return;\n')
            f.write('                }\n')
            f.write('                const nextState = this.factoryState(nextId);\n')
            f.write('                if (nextState === null) {\n')
            f.write(f'                    this.stateManagerData.changeStateNowId({name}StateID.NONE);\n')
            f.write('                    this.stateManagerData.saveStateId = null;\n')
            write_finish_inline('                    ')
            f.write('                    return;\n')
            f.write('                }\n')
            write_enter_or_begin('nextState')
            f.write('                return;\n')
        f.write('            }\n')

    f.write('            default:\n')
    f.write('                return;\n')


def generate_control_classes_javascript(file_path, name, json_data):
    js_dir = os.path.join(file_path, "JavaScript")
    os.makedirs(js_dir, exist_ok=True)
    file_control_path = os.path.join(js_dir, f'{name}StateControl.js')

    nodes = json_data.get('nodes', [])
    if not nodes:
        return

    init_node = next((n for n in nodes if int(n["id"]) == 1), nodes[0])
    init_label = init_node["data"]["label"]
    init_id = int(init_node["id"])
    init_state_id = f"{name}StateID.{init_label}{init_id:02d}"

    labels = []
    for node in nodes:
        label = node["data"]["label"]
        if label not in labels:
            labels.append(label)
    stack_labels = _collect_stack_case_labels(json_data)
    for label in stack_labels:
        if label not in labels:
            labels.append(label)

    with open(file_control_path, 'w', encoding='utf-8') as f:
        f.write('import { BaseStateControl } from "../../base_javascript/BaseStateControl.js";\n')
        f.write(f'import {{ {name}StateID }} from "./{name}StateID.js";\n')
        f.write(f'import {{ {name}StateManagerData }} from "./{name}StateManagerData.js";\n')
        f.write(f'import {{\n')
        for label in labels:
            f.write(f'    {name}{label}State,\n')
        f.write(f'}} from "./{name}States.js";\n\n')

        f.write(f'export class {name}StateControl extends BaseStateControl {{\n')
        f.write(f'    static GROUP_ID = "{name}";\n\n')

        f.write('    createManagerData() {\n')
        f.write(f'        return new {name}StateManagerData();\n')
        f.write('    }\n\n')

        f.write('    getInitStartId() {\n')
        f.write(f'        return {init_state_id};\n')
        f.write('    }\n\n')

        f.write('    factoryState(stateId) {\n')
        f.write('        switch (stateId) {\n')
        for label in stack_labels:
            f.write(f'            case {name}StateID.{label}: return new {name}{label}State();\n')
        for node in nodes:
            label = node["data"]["label"]
            node_id = int(node["id"])
            f.write(f'            case {name}StateID.{label}{node_id:02d}: return new {name}{label}State();\n')
        f.write('            default: return null;\n')
        f.write('        }\n')
        f.write('    }\n\n')

        f.write('    branchState() {\n')
        f.write('        if (this.state.isUpdateActive) return;\n')
        f.write('        this.isTransitioning = true;\n')
        f.write('        try {\n')
        f.write('            let stateId = this.stateManagerData.popStateId();\n')
        f.write('            if (stateId === null) stateId = this.stateManagerData.getNowStateId();\n')
        f.write('            this._branchSwitchSync(stateId);\n')
        f.write('        } finally {\n')
        f.write('            this.isTransitioning = false;\n')
        f.write('        }\n')
        f.write('    }\n\n')

        f.write('    _branchSwitchSync(stateId) {\n')
        f.write('        switch (stateId) {\n')
        _write_branch_cases_javascript(f, name, json_data, nodes, mode='sync')
        f.write('        }\n')
        f.write('    }\n\n')

        f.write('    branchStateCombined() {\n')
        f.write('        this.isTransitioning = true;\n')
        f.write('        try {\n')
        f.write('            let stateId = this.stateManagerData.popStateId();\n')
        f.write('            if (stateId === null) stateId = this.stateManagerData.getNowStateId();\n')
        f.write('            this._branchSwitchCombined(stateId);\n')
        f.write('        } finally {\n')
        f.write('            this.isTransitioning = false;\n')
        f.write('        }\n')
        f.write('    }\n\n')

        f.write('    _branchSwitchCombined(stateId) {\n')
        f.write('        switch (stateId) {\n')
        _write_branch_cases_javascript(f, name, json_data, nodes, mode='combined')
        f.write('        }\n')
        f.write('    }\n')
        f.write('}\n')


@bp.route('/api/open-code/<state_name>/<node_label>', methods=['GET'])
def open_code(state_name, node_label):
    """指定ノードに対応する State クラスの.csファイルパスを返す。

    以前はここでサーバー側 subprocess.Popen により VSCode/Visual Studio を
    直接起動していたが、Flaskサーバーとブラウザを操作しているPCが別マシンの
    場合にエディタが開けない（サーバー側の画面に開いてしまう）問題があった。
    そのため、パス解決のみを行い、実際にエディタを開く処理はクライアント側
    （ブラウザ）で行う方式に変更した。フロントエンドはこのパスを使って
    vscode://file/ のカスタムURLスキームで開くか、Visual Studio用に
    パスをコピーする。
    """
    cs_path = os.path.join(DATA_DIR, STATE_DATA, state_name, "States", f"{state_name}{node_label}State.cs")
    if not os.path.exists(cs_path):
        return jsonify({"error": "File not found"}), 404
    return jsonify({"csPath": cs_path})
# =================================================


def generate_base(data_dir):
    """
    State 用のボイラープレート生成（初回起動時のみ）。
    - state_list.json の初期化
    - BaseState.cs / BaseStateControl.cs / BaseStateManagerData.cs
    - BaseStateBranch.cs / BaseDetailStateBranch.cs
    """
    os.makedirs(os.path.join(data_dir, STATE_DATA), exist_ok=True)

    if not os.path.exists(os.path.join(data_dir, STATE_DATA, "state_list.json")):
        with open(os.path.join(data_dir, STATE_DATA, "state_list.json"), 'w', encoding='utf-8') as f:
            json.dump([], f)

    if not os.path.exists(os.path.join(data_dir, STATE_DATA, "BaseState.cs")):
        code_str = """
        // ------------------------------------------------------------
        // フェーズ別アクティブフラグ（Enter/Update/Exit × 同期/非同期の計6個）。
        // 各フェーズが「完了した」とみなされるのは、そのフェーズで使う同期・非同期の
        // 両方がfalseになった時。使わない側（UseXxxSync/UseXxxAsyncがfalse）は
        // コンストラクタで自動的にOffにしておくので、使う側だけを待てばよい。
        // 使う側は、対応するEnter/Update/Exit(Async)の実装が完了したタイミングで
        // 自分でXxxActiveOff()を呼ぶ（デフォルト生成コードでは、各メソッドの中に
        // 最初からOff呼び出しが入っている）。
        // ------------------------------------------------------------
        private bool is_enter_active = true;
        public bool IsEnterActive => is_enter_active;
        protected void IsEnterActiveOff() { is_enter_active = false; }

        private bool is_enter_active_async = true;
        public bool IsEnterActiveAsync => is_enter_active_async;
        protected void IsEnterActiveAsyncOff() { is_enter_active_async = false; }

        private bool is_update_active = true;
        public bool IsUpdateActive => is_update_active;
        protected void IsUpdateActiveOff() { is_update_active = false; }

        private bool is_update_active_async = true;
        public bool IsUpdateActiveAsync => is_update_active_async;
        protected void IsUpdateActiveAsyncOff() { is_update_active_async = false; }

        private bool is_exit_active = true;
        public bool IsExitActive => is_exit_active;
        protected void IsExitActiveOff() { is_exit_active = false; }

        private bool is_exit_active_async = true;
        public bool IsExitActiveAsync => is_exit_active_async;
        protected void IsExitActiveAsyncOff() { is_exit_active_async = false; }

        /// <summary>
        /// Combinedモードで、このStateが各フェーズで同期/非同期のどちらを使うかを宣言する。
        /// 遷移図のノードごとのチェックボックス設定に応じて、生成される具象クラス側で
        /// overrideされる（デフォルトは同期のみ）。
        /// StateControlのCombined APIはこれを見て呼び出す関数と、待つべきフラグを決めるため、
        /// 「チェックしていない方を二重に呼んでしまう」「使っていない側の完了待ちで
        /// 止まってしまう」ことがない。
        /// </summary>
        public virtual bool UseEnterSync => true;
        public virtual bool UseEnterAsync => false;
        public virtual bool UseUpdateSync => true;
        public virtual bool UseUpdateAsync => false;
        public virtual bool UseExitSync => true;
        public virtual bool UseExitAsync => false;

        protected BaseState()
        {
            // 使わない側（UseXxxSync/UseXxxAsyncがfalse）は、コンストラクタの時点で
            // 対応するIsXxxActive(Async)を自動的にfalseにしておく。
            // ※仮想メンバー呼び出しだが、派生クラスのoverrideプロパティは
            //   フィールド参照を持たない単純な式なので、ここで安全に呼べる。
            if (!UseEnterSync) IsEnterActiveOff();
            if (!UseEnterAsync) IsEnterActiveAsyncOff();
            if (!UseUpdateSync) IsUpdateActiveOff();
            if (!UseUpdateAsync) IsUpdateActiveAsyncOff();
            if (!UseExitSync) IsExitActiveOff();
            if (!UseExitAsync) IsExitActiveAsyncOff();
        }

        /// <summary>
        /// 同期版ライフサイクル。単純なStateはこちらだけoverrideすればよい。
        /// StateControlの同期API（StartState/UpdateState）から呼ばれる。
        /// </summary>
        public virtual void Enter(T state_manager_data) { }
        public virtual void Update(T state_manager_data) { }
        public virtual void Exit(T state_manager_data) { }

        /// <summary>
        /// 非同期版ライフサイクル。アセットのロード待ちなど、await が必要なStateは
        /// こちらをoverrideする。デフォルトでは同期版を呼び出すだけなので、
        /// 同期版だけをoverrideしたStateもStateControlの非同期APIから問題なく呼び出せる。
        /// （Combinedモードでは UseEnterAsync 等がfalseの時はこのメソッド自体が
        /// 呼ばれないため、二重実行にはならない）
        /// ct は StateControl 側で管理される CancellationToken で、
        /// 状態遷移が起きた時点で自動的にキャンセルされる。
        /// </summary>
        public virtual async UniTask EnterAsync(T state_manager_data, CancellationToken ct)
        {
            Enter(state_manager_data);
            await UniTask.CompletedTask;
            IsEnterActiveAsyncOff();
        }
        public virtual async UniTask UpdateAsync(T state_manager_data, CancellationToken ct)
        {
            Update(state_manager_data);
            await UniTask.CompletedTask;
            IsUpdateActiveAsyncOff();
        }
        public virtual async UniTask ExitAsync(T state_manager_data, CancellationToken ct)
        {
            Exit(state_manager_data);
            await UniTask.CompletedTask;
            IsExitActiveAsyncOff();
        }

        public virtual E BranchNextState(T state_manager_data)
        {
            return default;
        }
"""
        with open(os.path.join(data_dir, STATE_DATA, "BaseState.cs"), 'w', encoding='utf-8') as f:
            f.write(
                "using Cysharp.Threading.Tasks;\n"
                "using System.Threading;\n"
                "using GameCore.States.Managers;\n"
                "using System;\n"
                "namespace GameCore.States\n{\n"
                f"    public abstract class  BaseState<E,T>where E : Enum where T : BaseStateManagerData<E>\n"
                f"    {{{code_str}\n    }}\n}}\n"
            )

    STATE_BRANCH = os.path.join(data_dir, STATE_DATA)
    os.makedirs(STATE_BRANCH, exist_ok=True)

    # --- StateGroupID.cs / StateGroupTracker.cs ---
    # State「グループ」（=生成対象ごとの name。例: Title, Battle...）をまたいだ
    # 上位のベースID。個々の {name}StateID とは別に、
    # 「今どのグループが動いていて、直前はどのグループだったか」を追跡する。
    # state_list.json が更新される度に regenerate_state_group_id() で再生成される。
    regenerate_state_group_id(data_dir)

    if not os.path.exists(os.path.join(STATE_BRANCH, "StateGroupTracker.cs")):
        code_str = """using GameCore.States.ID;

namespace GameCore.States
{
    /// <summary>
    /// 現在アクティブな State グループ（StateGroupID）と、その1つ前のグループを
    /// 追跡する静的トラッカー。各 Base{name}StateControl が起動/再開する度に
    /// ChangeGroup を呼び出す。
    /// </summary>
    public static class StateGroupTracker
    {
        public static StateGroupID CurrentGroup { get; private set; } = StateGroupID.None;
        public static StateGroupID PreviousGroup { get; private set; } = StateGroupID.None;

        public static void ChangeGroup(StateGroupID new_group)
        {
            if (new_group == CurrentGroup) return;
            PreviousGroup = CurrentGroup;
            CurrentGroup = new_group;
        }
    }
}
"""
        with open(os.path.join(STATE_BRANCH, "StateGroupTracker.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    if not os.path.exists(os.path.join(STATE_BRANCH, "BaseStateControl.cs")):
        code_str = """
using System;
using System.Threading;
using Cysharp.Threading.Tasks;
using UnityEngine;
using GameCore.States.ID;

namespace GameCore.States.Control
{
    public abstract class BaseStateControl<T, E, F> : IDisposable
        where T : Enum
        where E : GameCore.States.Managers.BaseStateManagerData<T>,new()
        where F : GameCore.States.BaseState<T,E>
    {

        protected E state_manager_data = new E();
        public E StateManagerData{get { return state_manager_data; }}

        protected F state;

        protected bool is_finish = false;
        public bool IsFinish { get { return is_finish; } }

        /// <summary>
        /// このStateControlが担当するStateグループの識別子。
        /// Start系実行時にStateGroupTrackerへ反映される。
        /// </summary>
        protected abstract StateGroupID GroupID { get; }

        // ------------------------------------------------------------
        // ルートのCancellationTokenSource。
        // 非同期API・Combined APIが内部で使う「生存期間トークン」のもとになる。
        // Setup(externalToken) を呼ぶと、以後はそのトークンに連結される
        // （渡さなければ自前で新規作成して管理する）。
        // ------------------------------------------------------------
        private CancellationTokenSource rootCts;
        private bool isSetup;

        /// <summary>
        /// StateControlの初期セットアップ。外部からCancellationTokenを渡すと、
        /// StateControl全体（非同期API・Combined APIが内部で使うルートトークン）の
        /// 生存期間をそのトークンに入れ替える（例: this.GetCancellationTokenOnDestroy()）。
        /// 渡さなければ自前のトークンで管理する。
        /// Start系を呼ぶ前に一度だけ呼ぶのが望ましいが、呼ばれていなくても
        /// 最初のStart時に自動的に自前トークンでセットアップされる。
        /// 複数回呼ぶとその都度ルートトークンが張り替わり、それまでの非同期処理は
        /// キャンセルされる。
        /// </summary>
        public void Setup(CancellationToken externalToken = default)
        {
            rootCts?.Cancel();
            rootCts?.Dispose();
            rootCts = externalToken != default
                ? CancellationTokenSource.CreateLinkedTokenSource(externalToken)
                : new CancellationTokenSource();
            isSetup = true;
        }

        protected CancellationToken RootToken
        {
            get
            {
                if (!isSetup) Setup();
                return rootCts.Token;
            }
        }

        /// <summary>
        /// Fire-and-Forgetした非同期処理内の例外を握りつぶさずログへ出す共通ハンドラ。
        /// .Forget() の代わりに .Forget(LogAsyncException) を使う。
        /// （キャンセルによる例外は正常系なので無視する）
        /// </summary>
        protected static void LogAsyncException(Exception ex)
        {
            if (ex is OperationCanceledException) return;
            Debug.LogException(ex);
        }

        // 遷移(Exit→Enter)処理中の再入防止フラグ。
        // StartState/BranchState系の多重呼び出し（例: 誤って同フレームで2回呼んだ等）による
        // Stateの多重生成・Exit漏れを防ぐ。生成される Base{name}StateControl の
        // BranchState/BranchStateAsync/BranchStateCombined がこれをtrue/falseする。
        protected bool isTransitioning;

        // 現在の状態(Enter/Update/Exit)実行中のCancellationTokenSource。
        // 状態が切り替わるたびに古いものはキャンセル＆破棄され、
        // 外部から渡された（または RootToken の）「生存期間トークン」に
        // 連結した新しいものが作られる。※非同期API(StartStateAsync等)を使う場合のみ利用。
        protected CancellationTokenSource stateCts;

        protected CancellationToken RenewStateToken(CancellationToken life_time_token)
        {
            stateCts?.Cancel();
            stateCts?.Dispose();
            stateCts = CancellationTokenSource.CreateLinkedTokenSource(life_time_token);
            return stateCts.Token;
        }

        protected abstract T GetInitStartID();

        // ------------------------------------------------------------
        // 同期API: シンプルなStateマシン向け。CancellationTokenは扱わない。
        // Enter/Update/Exit（同期版）を直接呼び出す。
        // ------------------------------------------------------------
        public void StartState(Action<E> action = null)
        {
            if (state != null)
            {
                Debug.LogWarning("StartState は既に開始済みです。二重呼び出しを無視しました。");
                return;
            }
            OnStartState(GetInitStartID(), action);
        }
        public void StartState(T state_id)
        {
            if (state != null)
            {
                Debug.LogWarning("StartState は既に開始済みです。二重呼び出しを無視しました。");
                return;
            }
            OnStartState(state_id, null);
        }

        protected void OnStartState(T state_id, Action<E> action)
        {
            StateGroupTracker.ChangeGroup(GroupID);
            state = FactoryState(state_id);
            state_manager_data.ChangeStateNowID(state_id);
            action?.Invoke(state_manager_data);
            state.Enter(state_manager_data);
        }

        public void UpdateState(Action<E> befor_action = null, Action<E> after_action = null)
        {
            if (state == null) StartState();
            OnUpdateState(befor_action, after_action);
        }

        protected void OnUpdateState(Action<E> befor_action = null, Action<E> after_action = null)
        {
            befor_action?.Invoke(state_manager_data);
            state.Update(state_manager_data);
            if (!isTransitioning) BranchState();
            after_action?.Invoke(state_manager_data);
        }

        /// <summary>
        /// 同期版の遷移判定。CancellationTokenは扱わない版。
        /// アセットロード待ちなど非同期処理が絡まないStateマシンはこちらを使う。
        /// </summary>
        public abstract void BranchState();

        // ------------------------------------------------------------
        // 非同期API: 待ち処理(アセットロード等)が絡むStateマシン向け。
        // CancellationTokenSourceの張替え・連結を StateControl 側で管理する。
        // life_time_token を省略した場合は RootToken（Setup()で用意したもの）を使う。
        // ------------------------------------------------------------
        public UniTask StartStateAsync(CancellationToken life_time_token = default, Action<E> action = null)
        {
            if (state != null)
            {
                Debug.LogWarning("StartStateAsync は既に開始済みです。二重呼び出しを無視しました。");
                return UniTask.CompletedTask;
            }
            return OnStartStateAsync(GetInitStartID(), action, life_time_token == default ? RootToken : life_time_token);
        }
        public UniTask StartStateAsync(T state_id, CancellationToken life_time_token = default)
        {
            if (state != null)
            {
                Debug.LogWarning("StartStateAsync は既に開始済みです。二重呼び出しを無視しました。");
                return UniTask.CompletedTask;
            }
            return OnStartStateAsync(state_id, null, life_time_token == default ? RootToken : life_time_token);
        }

        protected async UniTask OnStartStateAsync(T state_id, Action<E> action, CancellationToken life_time_token)
        {
            StateGroupTracker.ChangeGroup(GroupID);
            state = FactoryState(state_id);
            state_manager_data.ChangeStateNowID(state_id);
            action?.Invoke(state_manager_data);
            CancellationToken ct = RenewStateToken(life_time_token);
            await state.EnterAsync(state_manager_data, ct);
        }

        public async UniTask UpdateStateAsync(CancellationToken life_time_token = default, Action<E> befor_action = null, Action<E> after_action = null)
        {
            CancellationToken token = life_time_token == default ? RootToken : life_time_token;
            if (state == null) await StartStateAsync(token);
            await OnUpdateStateAsync(token, befor_action, after_action);
        }

        protected async UniTask OnUpdateStateAsync(CancellationToken life_time_token, Action<E> befor_action = null, Action<E> after_action = null)
        {
            befor_action?.Invoke(state_manager_data);
            await state.UpdateAsync(state_manager_data, stateCts.Token);
            if (!isTransitioning) await BranchStateAsync(life_time_token);
            after_action?.Invoke(state_manager_data);
        }

        /// <summary>
        /// 現在の状態の遷移判定を行い、必要ならExit→(次の状態を生成)→Enterを非同期で実行する。
        /// life_time_token は次状態のEnter/Update/Exitの生存期間トークンとして引き継がれる。
        /// </summary>
        public abstract UniTask BranchStateAsync(CancellationToken life_time_token);

        // ------------------------------------------------------------
        // Combined API: 同期(Enter/Update/Exit)と非同期(EnterAsync/UpdateAsync/ExitAsync)を
        // 同時に動かすモード。呼び出し側は同期APIと同じ感覚（awaitなし）で毎フレーム呼べる。
        // 内部で使うCancellationTokenは RootToken（Setup()で入れ替え可能）に連結される。
        //
        // Enter/Update/Exit の3フェーズそれぞれに専用のアクティブフラグ
        // （IsEnterActive/IsEnterActiveAsync, IsUpdateActive/IsUpdateActiveAsync,
        //  IsExitActive/IsExitActiveAsync）があり、フェーズの同期・非同期の両方が
        // falseになるまで次のフェーズへは進まない。
        //
        // ・Enter: state自身が宣言する UseEnterSync/UseEnterAsync に従って呼ぶ。
        //   同期はその場で、非同期は Forget(LogAsyncException) で発火するだけ（待たない）。
        //   IsEnterActive/IsEnterActiveAsyncの両方がfalseになるまでUpdateは呼ばれない。
        // ・Update: 毎フレーム同期版を呼びつつ、非同期版はこの状態になってから
        //   一度だけ発火する（毎フレーム再発火しない）。
        //   IsUpdateActive/IsUpdateActiveAsyncの両方がfalseになった時だけ
        //   BranchStateCombined()（Exit呼び出し）へ進む。
        // ・Exit: BranchStateCombined()内で旧stateを exitingState に退避して呼ぶ
        //   （state自体はこの時点で次Stateに差し替わるため）。
        //   IsExitActive/IsExitActiveAsyncの両方がfalseになるまで、
        //   次Stateの Enter フェーズは発火されない（combinedEnterPending で待機）。
        // ------------------------------------------------------------
        protected CancellationTokenSource combinedCts;
        protected bool combinedAsyncUpdateStarted;

        // Exit待ちの旧State。BranchStateCombined()内で state を退避してから
        // Exitフェーズを発火し、その完了を OnUpdateStateCombined 側で待つ。
        protected F exitingState;
        // true の間は combinedEnterPending 待機中（exitingStateのExit完了待ち）。
        protected bool combinedEnterPending;

        public void StartStateCombined(Action<E> action = null)
        {
            if (state != null)
            {
                Debug.LogWarning("StartStateCombined は既に開始済みです。二重呼び出しを無視しました。");
                return;
            }
            OnStartStateCombined(GetInitStartID(), action);
        }
        public void StartStateCombined(T state_id)
        {
            if (state != null)
            {
                Debug.LogWarning("StartStateCombined は既に開始済みです。二重呼び出しを無視しました。");
                return;
            }
            OnStartStateCombined(state_id, null);
        }

        protected void OnStartStateCombined(T state_id, Action<E> action)
        {
            StateGroupTracker.ChangeGroup(GroupID);
            state = FactoryState(state_id);
            state_manager_data.ChangeStateNowID(state_id);
            action?.Invoke(state_manager_data);

            combinedCts?.Cancel();
            combinedCts?.Dispose();
            combinedCts = CancellationTokenSource.CreateLinkedTokenSource(RootToken);
            combinedAsyncUpdateStarted = false;
            exitingState = null;
            combinedEnterPending = false;

            // Enter: state自身が宣言する UseEnterSync/UseEnterAsync に従って呼ぶ
            if (state.UseEnterSync) state.Enter(state_manager_data);
            if (state.UseEnterAsync) state.EnterAsync(state_manager_data, combinedCts.Token).Forget(LogAsyncException);
        }

        public void UpdateStateCombined(Action<E> befor_action = null, Action<E> after_action = null)
        {
            if (state == null) StartStateCombined();
            OnUpdateStateCombined(befor_action, after_action);
        }

        protected void OnUpdateStateCombined(Action<E> befor_action = null, Action<E> after_action = null)
        {
            befor_action?.Invoke(state_manager_data);

            // 直前のBranchStateCombined()でExitを発火済み・次Stateへの切り替え待ちの場合、
            // exitingStateのExitフェーズ（同期・非同期の両方）が完了するまで待つ。
            // 完了したら次State（state）のEnterフェーズを発火する
            // （このフレームではまだUpdateは呼ばない）。
            if (combinedEnterPending)
            {
                if (!exitingState.IsExitActive && !exitingState.IsExitActiveAsync)
                {
                    combinedEnterPending = false;
                    exitingState = null;
                    if (state.UseEnterSync) state.Enter(state_manager_data);
                    if (state.UseEnterAsync) state.EnterAsync(state_manager_data, combinedCts.Token).Forget(LogAsyncException);
                }
                after_action?.Invoke(state_manager_data);
                return;
            }

            // Enterフェーズ（同期・非同期の両方）が完了するまではUpdateフェーズへ進まない。
            if (state.IsEnterActive || state.IsEnterActiveAsync)
            {
                after_action?.Invoke(state_manager_data);
                return;
            }

            // Update: state自身が宣言する UseUpdateSync/UseUpdateAsync に従って呼ぶ。
            // 非同期は、この状態になってから一度だけ発火する（毎フレーム再発火しない）。
            if (state.UseUpdateSync) state.Update(state_manager_data);
            if (state.UseUpdateAsync && !combinedAsyncUpdateStarted)
            {
                combinedAsyncUpdateStarted = true;
                state.UpdateAsync(state_manager_data, combinedCts.Token).Forget(LogAsyncException);
            }

            // Updateフェーズ（同期・非同期の両方）が「終わった」と自己申告した時だけ次へ進む。
            // （isTransitioningで、遷移処理自体からの再入も防止する）
            if (!isTransitioning && !state.IsUpdateActive && !state.IsUpdateActiveAsync)
            {
                BranchStateCombined();
            }

            after_action?.Invoke(state_manager_data);
        }

        /// <summary>
        /// Combinedモードでの遷移判定。IsUpdateActive/IsUpdateActiveAsyncが両方falseの時だけ
        /// StateControl側から呼ばれる（呼ばれた時点で無条件にExit・遷移してよい）。
        /// 旧stateをexitingStateに退避してからExitを発火する（同期はその場、
        /// 非同期はFire-and-Forget）。次stateのEnterは、exitingStateの
        /// IsExitActive/IsExitActiveAsyncが両方falseになるのを待ってから
        /// OnUpdateStateCombined側で発火される（combinedEnterPending）。
        /// </summary>
        public abstract void BranchStateCombined();

        public abstract F FactoryState(T state_id);

        /// <summary>
        /// StateControlが使う全てのCancellationTokenSourceを解放する。
        /// MonoBehaviourのOnDestroy等から呼ぶこと。
        /// </summary>
        public virtual void Dispose()
        {
            stateCts?.Cancel();
            stateCts?.Dispose();
            stateCts = null;
            combinedCts?.Cancel();
            combinedCts?.Dispose();
            combinedCts = null;
            exitingState = null;
            combinedEnterPending = false;
            rootCts?.Cancel();
            rootCts?.Dispose();
            rootCts = null;
        }

    }
}
"""
        with open(os.path.join(STATE_BRANCH, "BaseStateControl.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    if not os.path.exists(os.path.join(STATE_BRANCH, "BaseStateManagerData.cs")):
        code_str = """namespace GameCore.States.Managers
{
    public abstract class BaseStateManagerData<T> where T : Enum
    {

        protected T now_state_id = default;

        protected T old_state_id = default;
        
        public T SaveStateID { get; set; }

        protected List<T> stack_id_list = new List<T>();

        public void PushStateID(T state_id)
        {
            stack_id_list.Add(state_id);
        }

        public T PopStateID()
        {
            if (stack_id_list.Count > 0)
            {
                var state_id = stack_id_list[0];
                return state_id;
            }
            return default;
        }
        
        public void PopUpStateID()
        {
            if (stack_id_list.Count > 0)
            {
                stack_id_list.RemoveAt(0);

            }
        }


        public virtual void ChangeStateNowID(T new_state_id)
        {
            old_state_id = now_state_id;
            now_state_id = new_state_id;
        }

        public T GetNowStateID()
        {
            return now_state_id;
        }

        public T GetOldStateID()
        {
            return old_state_id;
        }

    }
}
"""
        with open(os.path.join(STATE_BRANCH, "BaseStateManagerData.cs"), 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.Collections.Generic;\n" + code_str)


    # --- BaseStateBranch.cs ---
    base_branch_path = os.path.join(data_dir, STATE_BRANCH, 'BaseStateBranch.cs')
    with open(base_branch_path, 'w', encoding='utf-8') as f:
        f.write('using System;\n')
        f.write('using UnityEngine;\n')
        f.write('using GameCore.States.Managers;\n\n')
        f.write('namespace GameCore.States.Branch\n{\n')
        f.write('    public abstract class BaseStateBranch<TStateId, TManagerData, TState, TDetailState>\n')
        f.write('        where TStateId : Enum\n')
        f.write('        where TManagerData : BaseStateManagerData<TStateId>\n')
        f.write('        where TState : BaseState<TStateId, TManagerData>\n')
        f.write('        where TDetailState : BaseDetailStateBranch<TStateId, TManagerData, TState>\n')
        f.write('    {\n')
        f.write('        public abstract TStateId ConditionsBranch(TManagerData manager_data, TState state);\n')
        f.write('        public abstract TDetailState Factory(TStateId id);\n')
        f.write('    }\n')
        f.write('}\n')
    # --- BaseDetailStateBranch.cs ---
    base_detail_path = os.path.join(data_dir, STATE_BRANCH, 'BaseDetailStateBranch.cs')
    with open(base_detail_path, 'w', encoding='utf-8') as f:
        f.write('using System;\n')
        f.write('using UnityEngine;\n')
        f.write('using GameCore.States.Managers;\n\n')
        f.write('namespace GameCore.States.Branch\n{\n')
        f.write('    public abstract class BaseDetailStateBranch<TStateId, TManagerData, TState>\n')
        f.write('        where TStateId : Enum\n')
        f.write('        where TManagerData : BaseStateManagerData<TStateId>\n')
        f.write('        where TState : BaseState<TStateId, TManagerData>\n')
        f.write('    {\n')
        f.write('        public abstract TStateId ConditionsBranch(TManagerData manager_data, TState state);\n')
        f.write('    }\n')
        f.write('}\n')

    # Python / JavaScript 版の共通基底コード（簡易対応）も合わせて生成する
    generate_base_python(data_dir)
    generate_base_javascript(data_dir)




def register(app, data_dir):
    """app.py から呼び出し、DATA_DIR を設定・ボイラープレート生成した上でルートを登録する。"""
    global DATA_DIR
    DATA_DIR = data_dir
    generate_base(data_dir)
    app.register_blueprint(bp)