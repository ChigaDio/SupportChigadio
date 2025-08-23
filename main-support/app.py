from math import isnan, isfinite
import logging
from flask import Flask, send_from_directory, jsonify, request
import os
import json

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='build')
DATA_DIR = 'data'
ENUM = 'enum'
CLASS_DATA = 'class-data'
STATE_DATA = 'state-data'

# ディレクトリ作成
for dir_name in [ENUM, CLASS_DATA, STATE_DATA]:
    dir_path = os.path.join(DATA_DIR, dir_name)
    if not os.path.exists(dir_path):
        logger.info(f"Creating directory: {dir_path}")
        os.makedirs(dir_path)
        
# ベースファイルの作成
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, "BaseClassData.cs")):
    with open(os.path.join(DATA_DIR, CLASS_DATA, "BaseClassData.cs"), 'w', encoding='utf-8') as f:
        f.write("namespace GameCore.Classes\n{\n    public class BaseClassData\n    {\n    }\n}\n")
        
if not os.path.exists(os.path.join(DATA_DIR, STATE_DATA, "BaseState.cs")):
    code_str = """
    private bool is_active = true;
    public bool IsActive
    {
        get { return is_active; }
    }

    protected void IsActiveOff(T state_manager_data)
    {
        is_active = false;
    }

    public override void Enter(T state_manager_data)
    {
        // Base state entry logic
    }

    public override void Update(T state_manager_data)
    {
        // Base state update logic
    }

    public override void Exit(T state_manager_data)
    {
        // Base state exit logic
    }
"""
    with open(os.path.join(DATA_DIR, STATE_DATA, "BaseState.cs"), 'w', encoding='utf-8') as f:
        f.write(f"namespace GameCore.States\n{{\n    public class BaseState<T> where T : BaseStateManagerData\n    {{{code_str}\n    }}\n}}\n")

if not os.path.exists(os.path.join(DATA_DIR, STATE_DATA, "BaseStateManagerData.cs")):  
    code_str = """
    protected T now_state_id = default;

    protected T old_state_id = default;

    public void ChangeStateNowID(T new_state_id)
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
"""
    with open(os.path.join(DATA_DIR, STATE_DATA, "BaseStateManagerData.cs"), 'w', encoding='utf-8') as f:
        f.write(f"namespace GameCore.States\n{{\n    using System;\n\n    public class BaseStateManagerData<T> where T : Enum\n    {{{code_str}\n    }}\n}}\n")

# Enum-ID管理
@app.route('/api/enum-id', methods=['GET', 'POST', 'PATCH'])
def manage_enum_id():
    file_path = os.path.join(DATA_DIR, ENUM, 'enum_list.json')
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Returning enum-id: {data}")
            return jsonify(data)
        except FileNotFoundError:
            return jsonify([]), 404
        except Exception as e:
            logger.error(f"Error reading enum-id: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            new_enum = request.get_json()
            if not new_enum or not new_enum.get('name'):
                return jsonify({"error": "Enum name is required"}), 400
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
            if any(item['name'] == new_enum['name'] for item in data):
                return jsonify({"error": f"Enum {new_enum['name']} already exists"}), 400
            max_id = max([item['id'] for item in data], default=0) + 1
            new_enum_entry = {"id": max_id, "name": new_enum['name']}
            data.append(new_enum_entry)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            new_directory_path = os.path.join(DATA_DIR, ENUM, new_enum['name'])
            os.makedirs(new_directory_path, exist_ok=True)
            with open(os.path.join(new_directory_path, f"{new_enum['name']}.json"), 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            logger.info(f"Added enum-id: {new_enum['name']}")
            return jsonify({"message": f"Enum {new_enum['name']} created successfully", "data": new_enum_entry})
        except Exception as e:
            logger.error(f"Error adding enum-id: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'PATCH':
        try:
            delete_name = request.get_json()['name']
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Removed enum: {delete_name}")
            return jsonify({"message": f"Enum {delete_name} removed from enum_list.json"})
        except FileNotFoundError:
            return jsonify({"error": "enum_list.json not found"}), 404
        except Exception as e:
            logger.error(f"Error removing enum-id: {str(e)}")
            return jsonify({"error": str(e)}), 500
        
# 型リストの取得
def get_type_lists():
    enum_list_path = os.path.join(DATA_DIR, ENUM, 'enum_list.json')
    class_list_path = os.path.join(DATA_DIR, CLASS_DATA, 'class_list.json')
    enum_list = []
    class_list = []
    try:
        with open(enum_list_path, 'r', encoding='utf-8') as f:
            enum_list = [item['name'] for item in json.load(f)]
    except FileNotFoundError:
        pass
    try:
        with open(class_list_path, 'r', encoding='utf-8') as f:
            class_list = [item['name'] for item in json.load(f)]
    except FileNotFoundError:
        pass
    return enum_list, class_list

# Enum詳細管理
@app.route('/api/enum/<name>', methods=['GET', 'POST', 'DELETE'])
def manage_enum_detail(name):
    file_path = os.path.join(DATA_DIR, ENUM, name, f'{name}.json')
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Returning enum data for {name}: {data}")
            return jsonify(data)
        except FileNotFoundError:
            return jsonify([]), 404
        except Exception as e:
            logger.error(f"Error reading enum {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            data = request.get_json()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved enum data for {name}")
            return jsonify({"message": f"{name}.json saved successfully"})
        except Exception as e:
            logger.error(f"Error saving enum {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'DELETE':
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                os.rmdir(os.path.join(DATA_DIR, ENUM, name))
                enum_list_path = os.path.join(DATA_DIR, ENUM, 'enum_list.json')
                with open(enum_list_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data = [item for item in data if item['name'] != name]
                with open(enum_list_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Deleted enum: {name}")
                return jsonify({"message": f"{name}.json deleted successfully"})
            return jsonify({"error": f"{name}.json not found"}), 404
        except Exception as e:
            logger.error(f"Error deleting enum {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500

# Enum C#生成
@app.route('/api/generate-enum/<name>', methods=['POST'])
def generate_enum_cs(name):
    try:
        data = request.get_json()
        logger.debug(f"Generating C# enum for {name}: {data}")
        valid_data = [item for item in data if not isnan(item['value']) and isfinite(item['value'])]
        cs_content = "namespace GameCore.Enums\n{\n"
        cs_content += f"    public enum {name}\n    {{\n"
        cs_content += "        None = -1, // デフォルト値\n"
        for item in valid_data:
            cs_content += f"        {item['property']} = {item['value']}, // {item['description']}\n"
        max_value = max([item['value'] for item in valid_data], default=-1) + 1
        cs_content += f"        Max = {max_value}\n"
        cs_content += "    }\n}"
        file_path = os.path.join(DATA_DIR, ENUM, name, f'{name}.cs')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)
        logger.info(f"Generated {name}.cs")
        return jsonify({"message": f"{name}.cs generated successfully"})
    except Exception as e:
        logger.error(f"Error generating {name}.cs: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ClassData-ID管理
@app.route('/api/class-data', methods=['GET', 'POST', 'PATCH'])
def manage_class_data():
    file_path = os.path.join(DATA_DIR, CLASS_DATA, 'class_list.json')
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Returning class-data: {data}")
            return jsonify(data)
        except FileNotFoundError:
            return jsonify([]), 404
        except Exception as e:
            logger.error(f"Error reading class-data: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            new_class = request.get_json()
            if not new_class or not new_class.get('name'):
                return jsonify({"error": "Class name is required"}), 400
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
            if any(item['name'] == new_class['name'] for item in data):
                return jsonify({"error": f"Class {new_class['name']} already exists"}), 400
            max_id = max([item['id'] for item in data], default=0) + 1
            new_class_entry = {"id": max_id, "name": new_class['name']}
            data.append(new_class_entry)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            new_directory_path = os.path.join(DATA_DIR, CLASS_DATA, new_class['name'])
            os.makedirs(new_directory_path, exist_ok=True)
            with open(os.path.join(new_directory_path, f"{new_class['name']}.class.json"), 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            logger.info(f"Added class-data: {new_class['name']}")
            return jsonify({"message": f"Class {new_class['name']} created successfully", "data": new_class_entry})
        except Exception as e:
            logger.error(f"Error adding class-data: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'PATCH':
        try:
            delete_name = request.get_json()['name']
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Removed class: {delete_name}")
            return jsonify({"message": f"Class {delete_name} removed from class_list.json"})
        except FileNotFoundError:
            return jsonify({"error": "class_list.json not found"}), 404
        except Exception as e:
            logger.error(f"Error removing class-data: {str(e)}")
            return jsonify({"error": str(e)}), 500

# ClassData詳細管理
@app.route('/api/class-data/<name>', methods=['GET', 'POST', 'DELETE'])
def manage_class_detail(name):
    file_path = os.path.join(DATA_DIR, CLASS_DATA, name, f'{name}.class.json')
    logger.debug(f"Handling /api/class-data/{name} with method: {request.method}")
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Returning class data for {name}: {data}")
            return jsonify(data)
        except FileNotFoundError:
            logger.warning(f"{name}.class.json not found at {file_path}")
            return jsonify([]), 404
        except Exception as e:
            logger.error(f"Error reading class {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            data = request.get_json()
            logger.debug(f"POST data for class {name}: {data}")
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved class data for {name}")
            return jsonify({"message": f"{name}.class.json saved successfully"})
        except Exception as e:
            logger.error(f"Error saving class {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'DELETE':
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                os.rmdir(os.path.join(DATA_DIR, CLASS_DATA, name))
                class_list_path = os.path.join(DATA_DIR, CLASS_DATA, 'class_list.json')
                with open(class_list_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data = [item for item in data if item['name'] != name]
                with open(class_list_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Deleted class: {name}")
                return jsonify({"message": f"{name}.class.json deleted successfully"})
            logger.warning(f"{name}.class.json not found at {file_path}")
            return jsonify({"error": f"{name}.class.json not found"}), 404
        except Exception as e:
            logger.error(f"Error deleting class {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500

# ClassData C#生成
@app.route('/api/generate-class/<name>', methods=['POST'])
def generate_class_cs(name):
    try:
        data = request.get_json()
        logger.debug(f"Generating C# class for {name}: {data}")
        enum_list, class_list = get_type_lists()
        basic_types = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object']
        unity_types = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject']
        
        cs_content = "using GameCore.Enums;\n\n"
        cs_content += "namespace GameCore.Classes\n{\n"
        cs_content += f"    public class {name} : BaseClassData\n    {{\n"
        for item in data:
            type_str = item['type']
            var_name = item['name']
            array_size = item['arraySize']
            description = item['description']
            
            # 初期値の決定
            if type_str.lower() in ['int', 'byte', 'short', 'long']:
                initial = '0'
            elif type_str.lower() in ['float', 'double', 'decimal']:
                initial = '0.0'
            elif type_str.lower() == 'bool':
                initial = 'false'
            elif type_str in enum_list:
                type_str = f"GameCore.Enums.{type_str}"  # enum 型を完全修飾
                initial = f"GameCore.Enums.{type_str}.None"
            elif type_str in class_list or type_str in unity_types or type_str.lower() == 'object':
                initial = f"new {type_str}()"
            else:
                initial = 'null'
            
            # 配列/リストの処理
            if array_size == -1:
                type_str = f"List<{type_str}>"
                initial = f"new List<{item['type']}>()"
            elif array_size > 0:
                type_str = f"{type_str}[]"
                initial = f"new {item['type']}[{array_size}]"
            
            cs_content += f"        public {type_str} {var_name} = {initial}; // {description}\n"
        cs_content += "    }\n}"
        file_path = os.path.join(DATA_DIR, CLASS_DATA, name, f'{name}.cs')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)
        logger.info(f"Generated {name}.cs")
        return jsonify({"message": f"{name}.cs generated successfully"})
    except Exception as e:
        logger.error(f"Error generating {name}.cs: {str(e)}")
        return jsonify({"error": str(e)}), 500

# StateData-ID管理
@app.route('/api/state-data', methods=['GET', 'POST', 'PATCH'])
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
            logger.info(f"Removed state: {delete_name}")
            return jsonify({"message": f"State {delete_name} removed from state_list.json"})
        except FileNotFoundError:
            return jsonify({"error": "state_list.json not found"}), 404
        except Exception as e:
            logger.error(f"Error removing state-data: {str(e)}")
            return jsonify({"error": str(e)}), 500

# StateData詳細管理
@app.route('/api/state-data/<name>', methods=['GET', 'POST', 'DELETE'])
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
@app.route('/api/generate-state/<name>', methods=['POST'])
def generate_state_cs(name):
    try:
        data = request.get_json()
        generate_state_classes(os.path.join(DATA_DIR, STATE_DATA, name), name, data )
        generate_state_id(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_state_manager_data(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_state_branch(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
        generate_control_classes(os.path.join(DATA_DIR, STATE_DATA, name), name, data)
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
    for data in json_data.get('nodes', []):
        label = data.get("data", {}).get("label", "")
        id = data.get("id", 0)
        if label:
            code_str.append(f'      {label}{int(id):02d},\n')

    with open(file_id_path, 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.States.ID\n{\n')
        f.write(f'  public enum {name}StateID {{\n')
        f.write('       None = -1,\n')
        f.writelines(code_str)
        f.write('       Max\n')
        f.write('   }\n')
        f.write('}\n')
        
#ManagerDataの作成
def generate_state_manager_data(file_path, name, json_data):
    if not os.path.exists(os.path.join(file_path, "ManagerData")):
        os.makedirs(os.path.join(file_path, "ManagerData"))
    file_base_state_manager_data_path = os.path.join(file_path, "ManagerData", f'Base{name}StateManager.cs')
    file_state_manager_data_path = os.path.join(file_path, "ManagerData", f'{name}StateManager.cs')

    base_code_str = []
    
    
    enum_list, class_list = get_type_lists()
    basic_types = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object']
    unity_types = [
    'GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 
    'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 
    'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 
    'ScriptableObject'
    ]
    for item in json_data.get('manager', []):
        base_code_str.append(f"{generate_csharp_field(item, enum_list, class_list, unity_types, basic_types)}")
        
    with open(file_base_state_manager_data_path, 'w', encoding='utf-8') as f:
        f.write('using System.Collections.Generic;\n')
        f.write('using UnityEngine;\n\n')
        
        f.write('namespace GameCore.States.Managers\n{\n')
        f.write(f'    public class Base{name}StateManagerData : BaseStateManagerData<GameCore.States.ID.{name}StateID>\n    {{\n')
        
        for data in base_code_str:
            f.write(data)
        f.write('   }\n')
        f.write('}\n')
        
    with open(file_state_manager_data_path, 'w', encoding='utf-8') as f:
        f.write('using System.Collections.Generic;\n')
        f.write('using UnityEngine;\n\n')

        f.write('namespace GameCore.States.Managers\n{\n')
        f.write(f'    public class {name}StateManager : GameCore.States.Base{name}StateManager\n    {{\n')
        f.write('    }\n')
        f.write('}\n')
        


def generate_state_branch(file_path, name, json_data):
    branch_dir = os.path.join(file_path, "Branch")
    os.makedirs(branch_dir, exist_ok=True)
    node_dict = {node["id"]: node for node in json_data.get("nodes", [])}

    # --- Base{name}DetailStateBranch.cs ---
    base_detail_path = os.path.join(branch_dir, f'Base{name}DetailStateBranch.cs')
    with open(base_detail_path, 'w', encoding='utf-8') as f:
        f.write('using System.Collections.Generic;\n')
        f.write('using UnityEngine;\n\n')
        f.write('namespace GameCore.States.Branch\n{\n')
        f.write(f'    public abstract class Base{name}DetailStateBranch<F> ')
        f.write(f': BaseDetailStateBranch<GameCore.States.ID.{name}StateID, GameCore.States.Managers.{name}StateManagerData, F> where F : GameCore.States.Base{name}State\n')
        f.write('    {\n')
        f.write(f'        public abstract GameCore.States.ID.{name}StateID ConditionsBranch(GameCore.States.Managers.{name}StateManagerData manager_data, F state);\n')
        f.write('    }\n')
        f.write('}\n')

    # --- ノードごとの Detail クラス生成 ---
    label_groups = {}
    for node in json_data["nodes"]:
        label = node["data"]["label"]
        targets = node["data"].get("targets", [])
        if len(targets) <= 1:
            continue  # 1つ以下なら DetailBranch を作らない
        label_groups.setdefault(label, []).append(node)

    for label, nodes in label_groups.items():
        # Base{name}{label}DetailStateBranch.cs
        base_label_path = os.path.join(branch_dir, f'Base{name}{label}DetailStateBranch.cs')
        with open(base_label_path, 'w', encoding='utf-8') as f:
            f.write('using System.Collections.Generic;\n')
            f.write('using UnityEngine;\n\n')
            f.write('namespace GameCore.States.Branch\n{\n')
            f.write(f'    public abstract class Base{name}{label}DetailStateBranch : Base{name}DetailStateBranch<{name}{label}State>\n')
            f.write('    {\n')
            f.write(f'        public abstract GameCore.States.ID.{name}StateID ConditionsBranch(GameCore.States.Managers.{name}StateManagerData manager_data, GameCore.States.{name}{label}State state);\n')
            f.write('    }\n')
            f.write('}\n')

        # IDごとの BaseDetail / Detail クラス
        for node in nodes:
            node_id = int(node["id"])
            targets = node["data"].get("targets", [])
            if len(targets) <= 1:
                continue  # 1つ以下なら DetailBranch を作らない
            base_id_path = os.path.join(branch_dir, f'Base{name}{label}{node_id:02d}DetailStateBranch.cs')
            with open(base_id_path, 'w', encoding='utf-8') as f:
                f.write('using System.Collections.Generic;\n')
                f.write('using UnityEngine;\n\n')
                f.write('namespace GameCore.States.Branch\n{\n')
                f.write(f'    public abstract class Base{name}{label}{node_id:02d}DetailStateBranch : Base{name}{label}DetailStateBranch\n')
                f.write('    {\n')
                f.write(f'        public override GameCore.States.ID.{name}StateID ConditionsBranch(GameCore.States.Managers.{name}StateManagerData manager_data, GameCore.States.{name}{label}State state)\n')
                f.write('        {\n')
                for target_id in targets:
                    target_label = node_dict.get(target_id, {}).get("data", {}).get("label", "")
                    if target_label:
                        f.write(f'            if ({name}{label}_to_{target_label}{int(target_id):02d}(manager_data, state))\n')
                        f.write(f'                return GameCore.States.ID.{name}StateID.{target_label}{int(target_id):02d};\n')
                f.write(f'            return GameCore.States.ID.{name}StateID.None;\n')
                f.write('        }\n\n')
                for target_id in targets:
                    target_label = node_dict.get(target_id, {}).get("data", {}).get("label", "")
                    if target_label:
                        f.write(f'        public abstract bool {name}{label}_to_{target_label}{int(target_id):02d}(GameCore.States.Managers.{name}StateManagerData manager_data, GameCore.States.{name}{label}State state);\n')
                f.write('    }\n')
                f.write('}\n')

            impl_id_path = os.path.join(branch_dir, f'{name}{label}{node_id:02d}DetailStateBranch.cs')
            with open(impl_id_path, 'w', encoding='utf-8') as f:
                f.write('using System.Collections.Generic;\n')
                f.write('using UnityEngine;\n\n')
                f.write('namespace GameCore.States.Branch\n{\n')
                f.write(f'    public class {name}{label}{node_id:02d}DetailStateBranch : Base{name}{label}{node_id:02d}DetailStateBranch\n')
                f.write('    {\n')
                for target_id in targets:
                    target_label = node_dict.get(target_id, {}).get("data", {}).get("label", "")
                    if target_label:
                        f.write(f'        public override bool {name}{label}_to_{target_label}{int(target_id):02d}(GameCore.States.Managers.{name}StateManagerData manager_data, {name}{label}State state)\n')
                        f.write('        {\n')
                        f.write('            return false;\n')
                        f.write('        }\n\n')
                f.write('    }\n')
                f.write('}\n')

   
    # --- {name}{label}StateBranch.cs を生成 ---
    for label, nodes in label_groups.items():
        branch_path = os.path.join(branch_dir, f'{name}{label}StateBranch.cs')
        if os.path.exists(branch_path): continue  # 既に生成されている場合はスキップ
        with open(branch_path, 'w', encoding='utf-8') as f:
            f.write('using System.Collections.Generic;\n')
            f.write('using UnityEngine;\n\n')
            f.write('namespace GameCore.States.Branch\n{\n')
            f.write(f'    public class {name}{label}StateBranch : GameCore.States.Base{name}StateBranch<{name}{label}State>\n')
            f.write('    {\n')
            f.write(f'        public override GameCore.States.ID.{name}StateID ConditionsBranch(GameCore.States.Managers.{name}StateManagerData manager_data, {name}{label}State state)\n')
            f.write('        {\n')
            f.write('            var id = manager_data.GetNowID();\n')
            f.write('            var branch = Factory(id);\n')
            f.write('            return branch != null ? branch.ConditionsBranch(manager_data, state) : ')
            f.write(f'GameCore.States.ID.{name}StateID.None;\n')
            f.write('        }\n\n')
            f.write(f'        public Base{name}DetailStateBranch Factory(GameCore.States.ID.{name}StateID id)\n')
            f.write('        {\n')
            f.write('            switch (id)\n')
            f.write('            {\n')
            for node in nodes:
                f.write(f'                case GameCore.States.ID.{name}StateID.{label}{int(node["id"]):02d}:\n')
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
    enum_list, class_list = get_type_lists()  

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
        base_code_str.append(generate_csharp_field(item, enum_list, class_list, unity_types, basic_types))

        
    base_state_path = os.path.join(state_dir, f'Base{name}State.cs')
    with open(base_state_path, 'w', encoding='utf-8') as f:
        f.write('using UnityEngine;\n\n')
        f.write('namespace GameCore.States\n{\n')
        f.write(f'    public abstract class Base{name}State : BaseState<GameCore.States.Managers.{name}StateManagerData>\n')
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
        node_id = int(node.get("id"))
        targets = node.get("data", {}).get("targets", [])
        # Base{name}{label}State.cs
        base_label_state_path = os.path.join(state_dir, f'Base{name}{label}State.cs')
        with open(base_label_state_path, 'w', encoding='utf-8') as f:
            f.write('using UnityEngine;\n')
            f.write('using GameCore.States.Branch;\n\n')
            f.write('namespace GameCore.States\n{\n')
            f.write(f'    public abstract class Base{name}{label}State : GameCore.States.Base{name}State\n')
            f.write('    {\n')
            if len(targets) > 1:
                f.write(f'        public override GameCore.States.ID.{name}StateID BranchNextState(GameCore.States.Managers.{name}StateManagerData state_manager_data)\n')
                f.write('        {\n')
                f.write(f'            var branch = new {name}{label}StateBranch();\n')
                f.write(f'            var next_id = branch.ConditionsBranch(state_manager_data, this);\n')
                f.write('            return next_id;\n')
                f.write('        }\n')
            f.write('    }\n')
            f.write('}\n')

        # {name}{label}{id:02d}State.cs
        state_class_path = os.path.join(state_dir, f'{name}{label}State.cs')
        if os.path.exists(state_class_path): continue  # 既に生成されている場合はスキップ
        with open(state_class_path, 'w', encoding='utf-8') as f:
            f.write('using UnityEngine;\n\n')
            f.write('namespace GameCore.States\n{\n')
            f.write(f'    public class {name}{label}State : Base{name}{label}State\n')
            f.write('    {\n')
            f.write(f'        public override void Enter(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
            f.write(f'        public override void Update(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
            f.write(f'        public override void Exit(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
            f.write('    }\n')
            f.write('}\n')





def generate_csharp_field(item, enum_list, class_list, unity_types, basic_types):
    """
    C#フィールド宣言を生成する汎用関数

    Parameters:
        item (dict): {"type": str, "name": str, "arraySize": int, "description": str}
        enum_list (list): Enum 型名のリスト
        class_list (list): クラス型名のリスト
        unity_types (list): Unity 固有型のリスト
        basic_types (list): 基本型リスト

    Returns:
        str: C#のフィールド定義コード
    """
    type_str = item['type']
    var_name = item['name']
    array_size = item.get('arraySize', 0)
    description = item.get('description', '')

    # 初期値の決定
    lower_type = type_str.lower()
    if lower_type in ['int', 'byte', 'short', 'long']:
        initial = '0'
    elif lower_type in ['float', 'double', 'decimal']:
        initial = '0.0'
    elif lower_type == 'bool':
        initial = 'false'
    elif lower_type == 'string' or lower_type == 'char':
        initial = '""'
    elif type_str in enum_list:
        initial = f"GameCore.Enums.{type_str}.None"
        type_str = f"GameCore.Enums.{type_str}"
    elif type_str in class_list or type_str in unity_types or lower_type == 'object':
        initial = f"new {type_str}()"
    else:
        # 未知の型 → null 初期化
        initial = 'null'

    # 配列/リストの処理
    if array_size == -1:
        type_str = f"List<{type_str}>"
        initial = f"new List<{item['type']}>()"
    elif array_size > 0:
        type_str = f"{type_str}[]"
        initial = f"new {item['type']}[{array_size}]"

    return f"        public {type_str} {var_name} = {initial}; // {description}\n"   

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
        f.write('using UnityEngine;\n')
        f.write('using GameCore.States.ID;\n')
        f.write('using GameCore.States.Managers;\n')
        f.write('using GameCore.States;\n\n')

        f.write('namespace GameCore.States.Control\n{\n')
        f.write(f'    public abstract class Base{name}StateControl\n')
        f.write(f'        : BaseStateControl<{name}StateID, {name}StateManagerData, Base{name}State>\n')
        f.write('    {\n')

        # GetInitStartID()
        f.write(f'        protected override {name}StateID GetInitStartID()\n')
        f.write('        {\n')
        f.write(f'            return {init_state_id};\n')
        f.write('        }\n\n')

        # BranchState()
        f.write('        public override void BranchState()\n')
        f.write('        {\n')
        f.write('            if (!state.IsActive) return;\n\n')
        f.write('            var id = state_manager_data.GetNowID();\n')
        f.write('            switch (id)\n')
        f.write('            {\n')

        for node in nodes:
            label = node["data"]["label"]
            node_id = int(node["id"])
            state_id = f"{name}StateID.{label}{node_id:02d}"
            targets = node["data"].get("targets", [])

            f.write(f'                case {state_id}:\n')
            f.write('                {\n')
            f.write('                    state.Exit(state_manager_data);\n')

            # ターゲットがない → 終了
            if not targets:
                f.write('                    is_finish = true;\n')
                f.write('                    return;\n')
            # ターゲットが1つだけ → 直接遷移
            elif len(targets) == 1:
                next_node = targets[0]
                # 次ノードのラベル取得
                target_label = next(
                    (n["data"]["label"] for n in nodes if n["id"] == next_node), None)
                if target_label:
                    f.write(f'                    state_manager_data.ChangeStateNowID({name}StateID.{target_label}{int(next_node):02d});\n')
                    f.write('                    state = FactoryState(state_manager_data.GetNowID());\n')
                    f.write('                    if (state == null)\n')
                    f.write('                    {\n')
                    f.write('                        is_finish = true;\n')
                    f.write('                        return;\n')
                    f.write('                    }\n')
                    f.write('                    state.Enter(state_manager_data);\n')
                    f.write('                    return;\n')
            # 複数ターゲット → BranchNextStateを呼び出し
            else:
                f.write('                    var next_id = state.BranchNextState(state_manager_data);\n')
                f.write(f'                    if (next_id == {name}StateID.None)\n')
                f.write('                    {\n')
                f.write('                        is_finish = true;\n')
                f.write('                        return;\n')
                f.write('                    }\n')
                f.write('                    state = FactoryState(next_id);\n')
                f.write('                    if (state == null)\n')
                f.write('                    {\n')
                f.write('                        is_finish = true;\n')
                f.write('                        return;\n')
                f.write('                    }\n')
                f.write('                    state_manager_data.ChangeStateNowID(next_id);\n')
                f.write('                    state.Enter(state_manager_data);\n')
                f.write('                    return;\n')
            f.write('                }\n')
        f.write('            }\n')
        f.write('        }\n\n')

        # FactoryState()
        f.write(f'        public override Base{name}State FactoryState({name}StateID state_id)\n')
        f.write('        {\n')
        f.write('            switch (state_id)\n')
        f.write('            {\n')
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
        
# 静的ファイルのルーティング
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static(path):
    logger.debug(f"Serving static file: {path}")
    if path != '' and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(debug=True, port=8000)