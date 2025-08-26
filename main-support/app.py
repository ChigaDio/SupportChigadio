from math import isnan, isfinite
import logging
import shutil
import struct
import sys
from flask import Flask, send_from_directory, jsonify, request
import os
import json

# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ディレクトリパスをプロジェクトルート基準に設定
STATIC_FOLDER = os.path.join(BASE_DIR, 'build')
DATA_DIR = os.path.join(BASE_DIR, 'data')
CLASS_DATA_ID = 'class-data-id'

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=STATIC_FOLDER)
ENUM = 'enum'
CLASS_DATA = 'class-data'
STATE_DATA = 'state-data'

# 型マッピング（Vector2, Vector3追加）
TYPE_MAP = {
    'int': {'pack': 'i', 'cs_read': 'ReadInt32'},
    'float': {'pack': 'f', 'cs_read': 'ReadSingle'},
    'double': {'pack': 'd', 'cs_read': 'ReadDouble'},
    'bool': {'pack': '?', 'cs_read': 'ReadBoolean'},
    'string': {'pack': None, 'cs_read': None},  # 特殊処理
    'vector2': {'pack': None, 'cs_read': None}, # 特殊処理
    'vector3': {'pack': None, 'cs_read': None}  # 特殊処理
}

# 型リスト取得
def get_type_lists():
    basic_types = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object']
    unity_types = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject']
    enum_list = json.load(open(os.path.join(DATA_DIR, ENUM, 'enum_list.json'))) if os.path.exists(os.path.join(DATA_DIR, ENUM, 'enum_list.json')) else []
    class_list = json.load(open(os.path.join(DATA_DIR, CLASS_DATA, 'class_list.json'))) if os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, 'class_list.json')) else []
    return (
    basic_types,
    unity_types,
    [e.get('name') for e in enum_list] if enum_list else [],
    [c.get('name') for c in class_list] if class_list else []
)


# ディレクトリ作成
for dir_name in [ENUM, CLASS_DATA, STATE_DATA, CLASS_DATA_ID]:
    dir_path = os.path.join(DATA_DIR, dir_name)
    if not os.path.exists(dir_path):
        logger.info(f"Creating directory: {dir_path}")
        os.makedirs(dir_path)
        
# ベースファイルの作成
if not  os.path.exists(os.path.join(DATA_DIR, ENUM, "enum_list.json")):
    with open(os.path.join(DATA_DIR, ENUM, "enum_list.json"), 'w', encoding='utf-8') as f:
        json.dump([], f)
        
if not  os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, "class_list.json")):
    with open(os.path.join(DATA_DIR, CLASS_DATA, "class_list.json"), 'w', encoding='utf-8') as f:
        json.dump([], f)
        
if not  os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID, "class_data_id_list.json")):
    with open(os.path.join(DATA_DIR, CLASS_DATA_ID, "class_data_id_list.json"), 'w', encoding='utf-8') as f:
        json.dump([], f)
        
if not  os.path.exists(os.path.join(DATA_DIR, STATE_DATA, "state_list.json")):
    with open(os.path.join(DATA_DIR, STATE_DATA, "state_list.json"), 'w', encoding='utf-8') as f:
        json.dump([], f)

if not os.path.exists(os.path.join(DATA_DIR, STATE_DATA, "BaseState.cs")):
    code_str = """
        private bool is_active = true;
        public bool IsActive => is_active;

        protected void IsActiveOff(T state_manager_data)
        {
            is_active = false;
        }

        public abstract void Enter(T state_manager_data);
        public abstract void Update(T state_manager_data);
        public abstract void Exit(T state_manager_data);
        public virtual T BranchNextState(T state_manager_data)
        {
            return default;
        }
"""
    with open(os.path.join(DATA_DIR, STATE_DATA, "BaseState.cs"), 'w', encoding='utf-8') as f:
        f.write(f"namespace GameCore.States\n{{\n    public class BaseState<T> where T : BaseStateManagerData\n    {{{code_str}\n    }}\n}}\n")

STATE_BRANCH = os.path.join(DATA_DIR, STATE_DATA)


os.makedirs(STATE_BRANCH, exist_ok=True)


files_content = {
    # BaseDetailStateBranch
    os.path.join(STATE_BRANCH, "BaseDetailStateBranch.cs"): """namespace GameCore.States.Branch
{
    public abstract class BaseDetailStateBranch<T, E, F>
        where T : Enum
        where E : GameCore.States.Managers.BaseStateManagerData<T>
        where F : GameCore.States.BaseState<E>
    {
        public abstract T ConditionsBranch(E state_manager_data, F state);
    }
}
""",

    # BaseStateBranch
    os.path.join(STATE_BRANCH, "BaseStateBranch.cs"): """namespace GameCore.States.Branch
{
    public abstract class BaseStateBranch<T, E, F> 
        where T : Enum
        where E : GameCore.States.Managers.BaseStateManagerData<T>
        where F : GameCore.States.BaseState<E>
    {
        public abstract T ConditionsBranch(E state_manager_data, F state);
    }
}
""",

    # BaseStateControl
    os.path.join(STATE_BRANCH, "BaseStateControl.cs"): """namespace GameCore.States.Control
{
    public abstract class BaseStateControl<T, E, F>
        where T : Enum
        where E : GameCore.States.Managers.BaseStateManagerData<T>
        where F : GameCore.States.BaseState<E>
    {

        protected E state_manager_data;
        public E StateManagerData{get { return state_manager_data; }}

        protected F state;

        protected bool is_finish = true;
        public bool IsFinish { get { return is_finish; } }

        public void StartState(Action<E> action)
        {
            OnStartState(GetInitStartID(), action);
        }
        public void StartState(T state_id)
        {
            OnStartState(state_id, null);
        }
        public void StartState()
        {
            OnStartState(GetInitStartID(), null);
        }

        protected abstract T GetInitStartID();
        protected  void OnStartState(
    CharacterStateID state_id,
    Action<E> action)
        {
            state = FactoryState(state_id);
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
            BranchState();
            after_action?.Invoke(state_manager_data);
        }

        public abstract void BranchState();
        
        public abstract F FactoryState(T state_id);

    }
}
""",

    # BaseStateManagerData
    os.path.join(STATE_BRANCH, "BaseStateManagerData.cs"): """namespace GameCore.States.Managers
{
    public abstract class BaseStateManagerData<T> where T : Enum
    {

        protected T now_state_id = default;

        protected T old_state_id = default;

        protected List<T> stack_id_list = new List<T>();

        public void PushStateID(T state_id)
        {
            stack_id_list.Add(state_id);
        }

        public T PopStateID()
        {
            if (stack_id_list.Count > 0)
            {
                var state_id = stack_id_list[stack_id_list.Count - 1];
                stack_id_list.RemoveAt(stack_id_list.Count - 1);
                return state_id;
            }
            return default;
        }

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

    }
}
"""
}

# ファイル生成
for path, content in files_content.items():
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created: {path}")
    else:
        print(f"Skipped (exists): {path}")

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
# BaseClassDataRow.cs を生成
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID, "BaseClassDataRow.cs")):
    code_str = """
    using System.IO;

    namespace GameCore.Tables
    {
        public abstract class BaseClassDataRow
        {
            public abstract void Read(BinaryReader reader);
        }
    }
    """
    with open(os.path.join(DATA_DIR, CLASS_DATA_ID, "BaseClassDataRow.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")

# BaseClassDataID.cs を生成
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID, "BaseClassDataID.cs")):
    code_str = """
    using System.IO;
    using System;

    namespace GameCore.Tables
    {
        public abstract class BaseClassDataID<T,E> where T : Enum where E : BaseClassDataRow
        {
            public static Dictionary<T,E> Table = new Dictionary<T,E>();
        }
    }
    """
    with open(os.path.join(DATA_DIR, CLASS_DATA_ID, "BaseClassDataID.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")

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
        cs_content += "        None = 0, // デフォルト値\n"
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
        basic_types, unity_types, enum_list, class_list = get_type_lists()
        if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, name)):
            os.makedirs(os.path.join(DATA_DIR, CLASS_DATA, name), exist_ok=True)
        cs_path = os.path.join(DATA_DIR, CLASS_DATA,name, f"{name}.cs")
        
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
            f.write("namespace GameCore.Classes\n{\n")
            f.write(f"    public class {name} : BaseClassData\n    {{\n")
            read_codes = []
            for item in data:
                field_data = generate_csharp_field(item, enum_list, class_list, unity_types, basic_types)
                f.write(field_data['field'])
                read_codes.append(field_data['read'])
            f.write(f"\n        public {name}(BinaryReader reader) : base(reader)\n        {{\n")
            for read_code in read_codes:
                f.write(read_code)
            f.write("        }\n")
            f.write("    }\n}\n")
        return jsonify({"message": f"C# file generated: {cs_path}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
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
        
@app.route('/api/class-data-id', methods=['GET', 'POST', 'PATCH'])
def manage_class_data_id():
    # ディレクトリ確認と作成
    class_data_id_dir = os.path.join(DATA_DIR, CLASS_DATA_ID)
    os.makedirs(class_data_id_dir, exist_ok=True)
    
    file_path = os.path.join(class_data_id_dir, 'class_data_id_list.json')

    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"ClassDataIDリストを返します: {data}")
            return jsonify(data), 200
        except FileNotFoundError:
            logger.warning("class_data_id_list.jsonが見つかりません")
            return jsonify([]), 200  # 空リストを返す（404ではなく）
        except json.JSONDecodeError:
            logger.error("class_data_id_list.jsonの形式が不正です")
            return jsonify({"error": "class_data_id_list.jsonの形式が不正です"}), 500
        except Exception as e:
            logger.error(f"ClassDataIDリストの読み込みエラー: {str(e)}")
            return jsonify({"error": f"データ読み込みエラー: {str(e)}"}), 500

    elif request.method == 'POST':
        try:
            new_class_id = request.get_json()
            if not new_class_id or not new_class_id.get('name'):
                logger.error("名前が指定されていません")
                return jsonify({"error": "名前は必須です"}), 400
            name = new_class_id['name']
            if ':' in name:
                logger.error(f"名前に不正な文字 ':' が含まれています: {name}")
                return jsonify({"error": "名前に':'を含めることはできません"}), 400

            # 既存データの読み込み
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
            except json.JSONDecodeError:
                logger.error("class_data_id_list.jsonの形式が不正です")
                return jsonify({"error": "class_data_id_list.jsonの形式が不正です"}), 500

            # 名前の重複チェック
            if any(item['name'] == name for item in data):
                logger.error(f"ClassDataID {name} はすでに存在します")
                return jsonify({"error": f"ClassDataID {name} はすでに存在します"}), 400

            # 新しいIDを生成
            max_id = max([item['id'] for item in data], default=0) + 1
            new_entry = {"id": max_id, "name": name}
            data.append(new_entry)

            # class_data_id_list.jsonを更新
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 新しいClassDataIDのデータファイルを作成（空のrowsとcolumns）
            data_file_path = os.path.join(class_data_id_dir, name, f"{name}.json")
            os.makedirs(os.path.dirname(data_file_path), exist_ok=True)
            with open(data_file_path, 'w', encoding='utf-8') as f:
                json.dump({"columns": [], "rows": []}, f, ensure_ascii=False, indent=2)

            logger.info(f"ClassDataIDを作成しました: {name}")
            return jsonify({"message": f"ClassDataID {name} を正常に作成しました", "data": new_entry}), 201

        except json.JSONDecodeError:
            logger.error("リクエストデータの形式が不正です")
            return jsonify({"error": "リクエストデータの形式が不正です"}), 400
        except Exception as e:
            logger.error(f"ClassDataID作成エラー: {str(e)}")
            return jsonify({"error": f"作成エラー: {str(e)}"}), 500

    elif request.method == 'PATCH':
        try:
            delete_name = request.get_json().get('name')
            if not delete_name:
                logger.error("削除する名前が指定されていません")
                return jsonify({"error": "削除する名前を指定してください"}), 400

            # 既存データの読み込み
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                logger.warning("class_data_id_list.jsonが見つかりません")
                return jsonify({"error": "class_data_id_list.jsonが見つかりません"}), 404
            except json.JSONDecodeError:
                logger.error("class_data_id_list.jsonの形式が不正です")
                return jsonify({"error": "class_data_id_list.jsonの形式が不正です"}), 500

            # 指定された名前を削除
            if not any(item['name'] == delete_name for item in data):
                logger.warning(f"ClassDataID {delete_name} が見つかりません")
                return jsonify({"error": f"ClassDataID {delete_name} が見つかりません"}), 404

            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 関連ディレクトリの削除
            data_dir = os.path.join(class_data_id_dir, delete_name)
            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)
                logger.info(f"ディレクトリを削除しました: {data_dir}")

            logger.info(f"ClassDataIDを削除しました: {delete_name}")
            return jsonify({"message": f"ClassDataID {delete_name} を正常に削除しました"}), 200

        except json.JSONDecodeError:
            logger.error("リクエストデータの形式が不正です")
            return jsonify({"error": "リクエストデータの形式が不正です"}), 400
        except Exception as e:
            logger.error(f"ClassDataID削除エラー: {str(e)}")
            return jsonify({"error": f"削除エラー: {str(e)}"}), 500

# ClassDataID詳細データ（GET追加）
@app.route('/api/class-data-id/<name>', methods=['GET', 'POST', 'DELETE'])
def class_data_id_detail(name):
    file_path = os.path.join(DATA_DIR, CLASS_DATA_ID, name, f"{name}.json")
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Returning class-data-id detail: {name}")
            return jsonify(data)
        except FileNotFoundError:
            logger.error(f"ClassDataID {name} not found")
            return jsonify({"error": f"ClassDataID {name} not found"}), 404
        except Exception as e:
            logger.error(f"Error reading class-data-id {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        try:
            new_data = request.get_json()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved class-data-id: {name}")
            return jsonify({"message": f"Data for {name} saved"})
        except Exception as e:
            logger.error(f"Error saving class-data-id {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'DELETE':
        try:
            os.remove(file_path)
            logger.info(f"Deleted class-data-id: {name}")
            return jsonify({"message": f"{name}.json deleted"})
        except FileNotFoundError:
            logger.error(f"ClassDataID {name} not found")
            return jsonify({"error": "File not found"}), 404
        except Exception as e:
            logger.error(f"Error deleting class-data-id {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500

# ClassDataIDのCS生成
@app.route('/api/generate-class-data-id/<name>', methods=['POST'])
def generate_class_data_id_cs(name):
    try:
        data = request.get_json()
        columns = data['columns']
        rows = data['rows']
        basic_types, unity_types, enum_list, class_list = get_type_lists()
        enum_name = f"{name}TableID"  # Enum名をTableIDに変更

        # 出力ディレクトリ作成
        table_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, f"{name}")
        os.makedirs(table_dir, exist_ok=True)

        # --- Main Table File ---
        cs_path = os.path.join(table_dir, f"{name}Table.cs")
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
            f.write("namespace GameCore.Tables\n{\n")
            f.write(f"    public class {name}Table : BaseClassDataID<{enum_name}, {name}Row>\n    {{\n")
            #f.write(f"        public static Dictionary<{enum_name}, {name}Row> Table = new Dictionary<{enum_name}, {name}Row>();\n\n")

            # --- Row Class ---
            f.write(f"        public class {name}Row : BaseClassDataRow\n        {{\n")
            for col in columns:
                type_str = col['type']
                if type_str in enum_list:
                    type_str = f"GameCore.Enums.{type_str}"
                elif type_str in class_list:
                    type_str = f"GameCore.Classes.{type_str}"
                elif type_str.lower() in ['vector2', 'vector3']:
                    type_str = type_str.capitalize()

                f.write(f"            private {type_str} {col['name']};\n")
                f.write(f"            public {type_str} {col['name'].capitalize()} {{ get => {col['name']}; }}\n")

            # --- Read Method ---
            f.write("\n            public override void Read(BinaryReader reader)\n")
            f.write("            {\n")
            for i, col in enumerate(columns):
                type_lower = col['type'].lower()
                if type_lower in TYPE_MAP:
                    if type_lower == 'string':
                        f.write(f"                int len{i} = reader.ReadInt32();\n")
                        f.write(f"                {col['name']} = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len{i}));\n")
                    elif type_lower == 'vector2':
                        f.write(f"                {col['name']} = new Vector2(reader.ReadSingle(), reader.ReadSingle());\n")
                    elif type_lower == 'vector3':
                        f.write(f"                {col['name']} = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n")
                    else:
                        f.write(f"                {col['name']} = reader.{TYPE_MAP[type_lower]['cs_read']}();\n")
                elif col['type'] in enum_list:
                    f.write(f"                {col['name']} = (GameCore.Enums.{col['type']})Enum.ToObject(typeof(GameCore.Enums.{col['type']}), reader.ReadInt32());\n")
                elif col['type'] in class_list:
                    f.write(f"                {col['name']} = new GameCore.Classes.{col['type']}(reader);\n")
                else:
                    f.write(f"                {col['name']} = default; // Unsupported\n")
            f.write("            }\n")
            f.write("        }\n\n")

            # --- Table Constructor ---
            f.write(f"        public {name}Table(BinaryReader reader) : base(reader)\n        {{\n")
            f.write("            int rowCount = reader.ReadInt32();\n")
            f.write("            int colCount = reader.ReadInt32();\n")
            f.write("            var colNames = new string[colCount];\n")
            f.write("            var colTypes = new string[colCount];\n")
            f.write("            for(int i=0; i<colCount; i++) {\n")
            f.write("                int len = reader.ReadInt32();\n")
            f.write("                colNames[i] = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len));\n")
            f.write("                len = reader.ReadInt32();\n")
            f.write("                colTypes[i] = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len));\n")
            f.write("            }\n")
            f.write("            for(int r=0; r<rowCount; r++) {\n")
            f.write(f"                var enumVal = ({enum_name})Enum.ToObject(typeof({enum_name}), reader.ReadInt32());\n")
            f.write(f"                var row = new {name}Row();\n")
            f.write("                row.Read(reader);\n")  # ← Readでまとめる
            f.write("                Table[enumVal] = row;\n")
            f.write("            }\n")
            f.write("        }\n")
            f.write("    }\n}\n")

        # --- Enum File ---
        enum_cs_path = os.path.join(table_dir, f"{name}TableID.cs")
        with open(enum_cs_path, 'w', encoding='utf-8') as ef:
            ef.write("using System;\n\n")
            ef.write("namespace GameCore.Tables.ID\n{\n")
            ef.write(f"    public enum {name}TableID\n    {{\n")
            ef.write("        None = 0,\n")
            for i, row in enumerate(rows, start=1):
                ef.write(f"        {row['enum_property']} = {i},\n")
            ef.write("        Max\n")
            ef.write("    }\n}\n")
            
            
        #Exsample
        exsample_cs_path = os.path.join(table_dir, f"{name}TableExample.cs")
        with open(exsample_cs_path, 'w', encoding='utf-8') as ef:
           ef.write("using System;\nusing UnityEngine;\n")
           ef.write("using GameCore.Tables;\nusing GameCore.Tables.ID;\n\n")
           ef.write("namespace GameCore.Tables\n{\n")
           ef.write(f"    public static class {name}IDExtensions\n    {{\n")
           ef.write(f"        public static {name}Row GetRow(this {name}TableID id)\n")
           ef.write("        {\n")
           ef.write(f"            if ({name}Table.Table.TryGetValue(id, out var row))\n")
           ef.write("            {\n")
           ef.write("                return row;\n")
           ef.write("            }\n")
           ef.write("            else\n")
           ef.write("            {\n")
           ef.write("                return null; // または throw new KeyNotFoundException()\n")
           ef.write("            }\n")
           ef.write("        }\n")
           ef.write("    }\n")
           ef.write("}\n")


        return jsonify({"message": f"C# files generated: {cs_path}, {enum_cs_path}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
#バイナリ書き込み
def write_binary_field(f, value, type_str, enum_list, class_list):
    type_lower = type_str.lower()

    if type_lower in TYPE_MAP:
        # 文字列処理
        if type_lower == 'string':
            val_bytes = (value or '').encode('utf-8') if isinstance(value, str) else b''
            f.write(struct.pack('i', len(val_bytes)))
            f.write(val_bytes)

        # ベクトル2
        elif type_lower == 'vector2':
            x, y = value if isinstance(value, (list, tuple)) and len(value) >= 2 else [0.0, 0.0]
            f.write(struct.pack('ff', float(x), float(y)))

        # ベクトル3
        elif type_lower == 'vector3':
            x, y, z = value if isinstance(value, (list, tuple)) and len(value) >= 3 else [0.0, 0.0, 0.0]
            f.write(struct.pack('fff', float(x), float(y), float(z)))

        # 基本型（int, float, double, bool）
        else:
            default_value = 0 if type_lower in ['int', 'float', 'double'] else False
            safe_value = value if value is not None else default_value
            if type_lower == 'int':
                safe_value = int(safe_value)
            elif type_lower == 'float':
                safe_value = float(safe_value)
            elif type_lower == 'double':
                safe_value = float(safe_value)
            elif type_lower == 'bool':
                safe_value = bool(safe_value)
            f.write(struct.pack(TYPE_MAP[type_lower]['pack'], safe_value))

    elif type_str in enum_list:
        # Enumはintとして処理
        f.write(struct.pack('i', int(value) if value is not None else 0))

    elif type_str in class_list:
        # ClassDataの再帰処理
        class_data = json.load(open(os.path.join(DATA_DIR, CLASS_DATA, f"{type_str}.json"))) \
            if os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, f"{type_str}.json")) else []
        for item in class_data:
            array_size = item.get('arraySize', 0)
            item_value = value.get(item['name']) if isinstance(value, dict) else None
            if array_size == -1:  # List
                values = item_value if isinstance(item_value, list) else []
                f.write(struct.pack('i', len(values)))
                for v in values:
                    write_binary_field(f, v, item['type'], enum_list, class_list)
            elif array_size > 0:  # Array
                values = item_value if isinstance(item_value, list) else [None] * array_size
                for v in values[:array_size]:
                    write_binary_field(f, v, item['type'], enum_list, class_list)
            else:
                write_binary_field(f, item_value, item['type'], enum_list, class_list)
    else:
        f.write(struct.pack('i', 0))  # 未サポート型


# ClassDataID Binary生成（行のレコード値を正確に書き込み）
@app.route('/api/generate-binary/<name>', methods=['POST'])
def generate_binary(name):
    try:
        data = request.get_json()
        columns = data['columns']
        rows = data['rows']
        if  not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID, f"{name}",f"{name}Table.bin")):
            os.makedirs(os.path.join(DATA_DIR, CLASS_DATA_ID, f"{name}"), exist_ok=True)
        bin_path = os.path.join(DATA_DIR, CLASS_DATA_ID, name, f"{name}Table.bin")
        basic_types, unity_types, enum_list, class_list = get_type_lists()
        with open(bin_path, 'wb') as f:
            # ヘッダ: 行数, カラム数
            f.write(struct.pack('ii', len(rows), len(columns)))
            # カラムメタ: 名前長, 名前, 型名長, 型名
            #for col in columns:
            #    name_bytes = col['name'].encode('utf-8')
            #    type_bytes = col['type'].encode('utf-8')
            #    f.write(struct.pack('i', len(name_bytes)))
            #    f.write(name_bytes)
            #    f.write(struct.pack('i', len(type_bytes)))
            #    f.write(type_bytes)
            # データ: 行ごとにEnumValue, 各カラム値
            for row in rows:
                f.write(struct.pack('i', row['id']))
                for col in columns:
                    col_type = col['type'].lower()
                    col_value = row['data'].get(col['name'])
                    if col_type in TYPE_MAP:
                        actual_value = col_value.get('value') if isinstance(col_value, dict) else col_value
                        if col_type == 'string':
                            val_bytes = (actual_value or '').encode('utf-8') if isinstance(actual_value, str) else b''
                            f.write(struct.pack('i', len(val_bytes)))
                            f.write(val_bytes)
                        elif col_type == 'vector2':
                            x, y = actual_value if isinstance(actual_value, (list, tuple)) and len(actual_value) >= 2 else [0.0, 0.0]
                            f.write(struct.pack('ff', float(x), float(y)))
                        elif col_type == 'vector3':
                            x, y, z = actual_value if isinstance(actual_value, (list, tuple)) and len(actual_value) >= 3 else [0.0, 0.0, 0.0]
                            f.write(struct.pack('fff', float(x), float(y), float(z)))
                        elif col_type == 'double':
                            f.write(struct.pack('d', float(actual_value) if actual_value is not None else 0.0))
                        elif col_type == 'bool':
                            f.write(struct.pack('?', bool(actual_value) if actual_value is not None else False))
                        else:
                            default_value = 0 if col_type in ['int', 'float'] else False
                            f.write(struct.pack(TYPE_MAP[col_type]['pack'], actual_value if actual_value is not None else default_value))

                    elif col['type'] in enum_list:
                        actual_value = col_value.get('value') if isinstance(col_value, dict) else col_value
                        f.write(struct.pack('i', int(actual_value) if actual_value is not None else 0))
                    elif col['type'] in class_list:
                        class_data = json.load(open(os.path.join(DATA_DIR, CLASS_DATA, f"{col['type']}.json"))) if os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, f"{col['type']}.json")) else []
                        for item in class_data:
                            item_value = col_value.get(item['name']) if isinstance(col_value, dict) else None
                            array_size = item.get('arraySize', 0)
                            if array_size == -1:  # List
                                values = item_value if isinstance(item_value, list) else []
                                f.write(struct.pack('i', len(values)))
                                for v in values:
                                    write_binary_field(f, v, item['type'], enum_list, class_list)
                            elif array_size > 0:  # Array
                                values = item_value if isinstance(item_value, list) else [None] * array_size
                                for v in values[:array_size]:
                                    write_binary_field(f, v, item['type'], enum_list, class_list)
                            else:
                                write_binary_field(f, item_value, item['type'], enum_list, class_list)
                    else:
                        f.write(struct.pack('i', 0))  # 未サポート型
        return jsonify({"message": f"Binary generated: {bin_path}"})
    except Exception as e:
        logger.error(f"Error generating binary for {name}: {str(e)}")
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
    code_label = []
    for data in json_data.get('nodes', []):
        label = data.get("data", {}).get("label", "")
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
        
#ManagerDataの作成
def generate_state_manager_data(file_path, name, json_data):
    if not os.path.exists(os.path.join(file_path, "ManagerData")):
        os.makedirs(os.path.join(file_path, "ManagerData"))
    file_base_state_manager_data_path = os.path.join(file_path, "ManagerData", f'Base{name}StateManager.cs')
    file_state_manager_data_path = os.path.join(file_path, "ManagerData", f'{name}StateManager.cs')

    base_code_str = []


    base_list,unity_types,enum_list, class_list = get_type_lists()
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
    basic_types, unity_types, enum_list, class_list = get_type_lists()  

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




#stateで使用
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

# C#フィールド生成（private + ゲッター）
def generate_csharp_field(item, enum_list, class_list, unity_types, basic_types):
    type_str = item['type']
    var_name = item['name']
    array_size = item.get('arraySize', 0)
    description = item.get('description', '')

    # 型変換
    if type_str in enum_list:
        type_str = f"GameCore.Enums.{type_str}"
    elif type_str in class_list:
        type_str = f"GameCore.Classes.{type_str}"
    elif type_str.lower() in TYPE_MAP:
        type_str = type_str.capitalize() if type_str.lower() in ['vector2', 'vector3'] else type_str.lower()
    else:
        type_str = type_str

    # 配列/List処理
    is_list = array_size == -1
    is_array = array_size > 0
    if is_list:
        type_str = f"List<{type_str}>"
    elif is_array:
        type_str = f"{type_str}[]"

    # 初期値
    if type_str.lower() in ['int', 'byte', 'short', 'long']:
        initial = '0'
    elif type_str.lower() in ['float', 'double', 'decimal']:
        initial = '0.0'
    elif type_str.lower() == 'bool':
        initial = 'false'
    elif type_str.lower() == 'string' or type_str.lower() == 'char':
        initial = '""'
    elif type_str.lower() == 'vector2':
        initial = 'new Vector2()'
    elif type_str.lower() == 'vector3':
        initial = 'new Vector3()'
    elif type_str.startswith('GameCore.Enums.'):
        initial = f"{type_str}.None"
    else:
        initial = f"new {type_str}()"

    # BinaryReader読み込みコード
    read_code = ""
    if is_list:
        read_code = f"            {var_name} = new List<{item['type']}>();\n"
        read_code += f"            int {var_name}_count = reader.ReadInt32();\n"
        read_code += f"            for(int i=0; i<{var_name}_count; i++) {{\n"
        if item['type'].lower() in TYPE_MAP:
            if item['type'].lower() == 'vector2':
                read_code += f"                {var_name}.Add(new Vector2(reader.ReadSingle(), reader.ReadSingle()));\n"
            elif item['type'].lower() == 'vector3':
                read_code += f"                {var_name}.Add(new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()));\n"
            else:
                read_code += f"                {var_name}.Add(reader.{TYPE_MAP[item['type'].lower()]['cs_read']}());\n"
        elif item['type'] in enum_list:
            read_code += f"                {var_name}.Add((GameCore.Enums.{item['type']})Enum.ToObject(typeof(GameCore.Enums.{item['type']}), reader.ReadInt32()));\n"
        elif item['type'] in class_list:
            read_code += f"                {var_name}.Add(new GameCore.Classes.{item['type']}(reader));\n"
        else:
            read_code += f"                {var_name}.Add(new {item['type']}()); // Unsupported\n"
        read_code += "            }\n"
    elif is_array:
        read_code = f"            {var_name} = new {item['type']}[{array_size}];\n"
        read_code += f"            for(int i=0; i<{array_size}; i++) {{\n"
        if item['type'].lower() in TYPE_MAP:
            if item['type'].lower() == 'vector2':
                read_code += f"                {var_name}[i] = new Vector2(reader.ReadSingle(), reader.ReadSingle());\n"
            elif item['type'].lower() == 'vector3':
                read_code += f"                {var_name}[i] = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n"
            else:
                read_code += f"                {var_name}[i] = reader.{TYPE_MAP[item['type'].lower()]['cs_read']}();\n"
        elif item['type'] in enum_list:
            read_code += f"                {var_name}[i] = (GameCore.Enums.{item['type']})Enum.ToObject(typeof(GameCore.Enums.{item['type']}), reader.ReadInt32());\n"
        elif item['type'] in class_list:
            read_code += f"                {var_name}[i] = new GameCore.Classes.{item['type']}(reader);\n"
        else:
            read_code += f"                {var_name}[i] = new {item['type']}(); // Unsupported\n"
        read_code += "            }\n"
    else:
        if type_str.lower() in TYPE_MAP:
            if type_str.lower() == 'vector2':
                read_code = f"            {var_name} = new Vector2(reader.ReadSingle(), reader.ReadSingle());\n"
            elif type_str.lower() == 'vector3':
                read_code = f"            {var_name} = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n"
            else:
                read_code = f"            {var_name} = reader.{TYPE_MAP[type_str.lower()]['cs_read']}();\n"
        elif type_str.startswith('GameCore.Enums.'):
            read_code = f"            {var_name} = ({type_str})Enum.ToObject(typeof({type_str}), reader.ReadInt32());\n"
        elif type_str.startswith('GameCore.Classes.'):
            read_code = f"            {var_name} = new {type_str}(reader);\n"
        else:
            read_code = f"            {var_name} = new {type_str}(); // Unsupported\n"

    return {
        'field': f"        private {type_str} {var_name};\n        public {type_str} {var_name.capitalize()} {{ get => {var_name}; }} // {description}\n",
        'read': read_code
    }

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
        f.write('            var id = state_manager_data.PopStateID();\n')
        f.write('            if(id == default) id = state_manager_data.GetNowID();\n')
        f.write('            switch (id)\n')
        f.write('            {\n')
        
        
        code_label = []
        for node in nodes:
            label = node["data"]["label"]
            node_id = int(node["id"])
            state_id = f"{name}StateID.{label}"
            targets = node["data"].get("targets", [])
            if label not in code_label:
                code_label.append(label)
                f.write(f'                case {state_id}:\n')
                f.write('                {\n')
                f.write('                    state.Exit(state_manager_data);\n')
                f.write('                    var id = state_manager_data.PopStateID();\n')
                f.write('                    if(id == default) id = state_manager_data.GetNowID();\n')
                f.write('                    state = FactoryState(id);\n')
                f.write('                    if (state == null)\n')
                f.write('                    {\n')
                f.write('                        is_finish = true;\n')
                f.write('                        return;\n')
                f.write('                    }\n')
                f.write('                    state.Enter(state_manager_data);\n')
                f.write('                }\n')

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
                f.write('                    state_manager_data.ChangeStateNowID(next_id);\n')
                if len(node["data"].get("subNodes", [])) > 0:
                    for child in node["data"].get("subNodes", []):
                        child_label = child["label"]
                        child_id = f"{name}StateID.{child_label}"
                        f.write(f'                    state_manager_data.PushStateID({child_id});\n')
                    f.write(f'                    next_id = state_manager_data.PopStateID();\n')
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
        
        code_label = []
        for node in nodes:
            label = node["data"]["label"]
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