from math import isnan, isfinite
import logging
import re
import shutil
import struct
import subprocess
import sys
from flask import Flask, send_file, send_from_directory, jsonify, request
import os
import json
import textwrap

import psutil
import pythonSrc.generators as generators
import pythonSrc.scenario as scenario
import pythonSrc.assets as assets
import pythonSrc.dbgServer as dbgServer
import pythonSrc.addressableInit
import pythonSrc.behavior
import pythonSrc.animation
import threading
from pathlib import Path
import pythonSrc.scene as scene
import pythonSrc.savedata as savedata
import pythonSrc.expansion as expansion


if getattr(sys, 'frozen', False):
    # exe実行時
    # 一つ前
    base_dir = os.path.abspath(os.path.join(sys.executable, ".."))
else:
    # 開発時
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if base_dir not in sys.path:
    sys.path.append(base_dir)

isDbg = True
# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
    isDbg = False
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ディレクトリパスをプロジェクトルート基準に設定
STATIC_FOLDER = os.path.join(BASE_DIR, 'build')
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))


CLASS_DATA_ID = 'class_data_id'
CLASS_DATA_MATRIX_ID = 'class_data_matrix_id'
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=STATIC_FOLDER)
ENUM = 'enum'
CLASS_DATA = 'class_data'
STATE_DATA = 'state_data'

SCRIPT = 'Script'
OBJECTPOOL = 'ObjectPool'
EDITOR = "Editor"
DEBUG = "Debug"
LOG = "Log"
PYTHON = "Python"

SUBMODULE = "submodule"
PLUGIN = "Plugin"

CONST_CLASS_DATA = 'const_class_data'
 
# ConstClassData で使用できる型と、C#での表現
CONST_TYPE_MAP = {
    'int':     {'cs_type': 'int',    'is_const': True,  'default': '0'},
    'uint':    {'cs_type': 'uint',   'is_const': True,  'default': '0'},
    'float':   {'cs_type': 'float',  'is_const': True,  'default': '0'},
    'string':  {'cs_type': 'string', 'is_const': True,  'default': ''},
    # Vector2 / Vector3 はC#のconstにできないため static readonly を使う
    'vector2': {'cs_type': 'Vector2', 'is_const': False, 'default': [0, 0]},
    'vector3': {'cs_type': 'Vector3', 'is_const': False, 'default': [0, 0, 0]},
}


SAVE_DATA_DIR = os.path.join(DATA_DIR, "save_data")
SAVE_DATA_CUSTOM_DIR = os.path.join(SAVE_DATA_DIR, "custom_data")

def find_highest_assets_folder(base_folder = BASE_DIR):
    """
    BASE_FOLDERから親ディレクトリを遡って、最も上位のAssetsフォルダを検索する。
    見つからない場合はNoneを返す。
    """
    current_path = Path(base_folder).resolve()
    
    # ディスクのルートに達するまで親ディレクトリを遡る
    while current_path != current_path.parent:
        # 現在のディレクトリ内にAssetsフォルダがあるかチェック
        assets_path = current_path / "Assets"
        if assets_path.exists() and assets_path.is_dir():
            return assets_path
        # 親ディレクトリに移動
        current_path = current_path.parent
    
    # ルートディレクトリにもAssetsフォルダがあるかチェック
    assets_path = current_path / "Assets"
    if assets_path.exists() and assets_path.is_dir():
        return assets_path
    
    return None

def move_dll_files(base_folder = BASE_DIR, plugin_folder_name=os.path.join(SUBMODULE,PLUGIN)):
    """
    Pluginフォルダ内のDLLファイルを、最も上位のAssetsフォルダに移動する。
    """
    
    if isDbg:
        return
    # Assetsフォルダを検索
    assets_folder = find_highest_assets_folder(base_folder)
    if not assets_folder:
        print("Assetsフォルダが見つかりませんでした。")
        return
    
    print(f"Assetsフォルダが見つかりました: {assets_folder}")

    # Pluginフォルダのパスを構築
    plugin_folder = Path(base_folder) / plugin_folder_name
    if not plugin_folder.exists() or not plugin_folder.is_dir():
        print(f"Pluginフォルダが見つかりません: {plugin_folder}")
        return
    
    # DLLファイルを検索して移動
    dll_files = list(plugin_folder.glob("*.dll"))
    if not dll_files:
        print(f"Pluginフォルダ内にDLLファイルが見つかりません: {plugin_folder}")
        return
    
    for dll_file in dll_files:
        destination = assets_folder / dll_file.name
        try:
            shutil.move(str(dll_file), str(destination))
            print(f"移動成功: {dll_file} -> {destination}")
        except Exception as e:
            print(f"移動失敗: {dll_file} -> {destination}, エラー: {e}")
            
move_dll_files()

scenario.generate_scenario_folder(DATA_DIR)
scenario.generate_base_script_file(DATA_DIR)
assets.generate_base()

pythonSrc.addressableInit.generate_base()
pythonSrc.behavior.generate_base()
pythonSrc.animation.generate_base()
pythonSrc.scene.generate_base() 
pythonSrc.savedata.generate_base()
expansion.get_static_file_path()

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

import os
import json

def get_enum_values():
    enum_list_path = os.path.join(DATA_DIR, ENUM, 'enum_list.json')
    class_id_list_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')

    if os.path.exists(enum_list_path):
        with open(enum_list_path, 'r', encoding='utf-8') as f:
            enum_list = json.load(f)
    else:
        enum_list = []

    if os.path.exists(class_id_list_path):
        with open(class_id_list_path, 'r', encoding='utf-8') as f:
            class_id_list = json.load(f)
    else:
        class_id_list = []

    enum_values = {}

    for e in enum_list:
        enum_file_path = os.path.join(DATA_DIR, ENUM, e['name'], f"{e['name']}.json")
        if os.path.exists(enum_file_path):
            with open(enum_file_path, 'r', encoding='utf-8') as f:
                enum_data = json.load(f)
        else:
            enum_data = []
        enum_values[e['name']] = [r['property'] for r in enum_data]

    for c in class_id_list:
        class_file_path = os.path.join(DATA_DIR, CLASS_DATA_ID, c['name'], f"{c['name']}.json")
        if os.path.exists(class_file_path):
            with open(class_file_path, 'r', encoding='utf-8') as f:
                class_id_data = json.load(f)
        else:
            class_id_data = {'rows': []}
        enum_values[c['name']] = [r['enum_property'] for r in class_id_data['rows']]

    return enum_values

# JSONファイルを読み込む汎用関数
def load_json_files(item_list, base_dir):
    data_dict = {}
    for item in item_list:
        name = item.get('name')
        if not name or not isinstance(name, str):
            print(f"警告: 不正なnameが見つかりました: {item}")
            continue
        
        # JSONファイルのパスを構築
        json_path = os.path.join(DATA_DIR, base_dir, name, f"{name}.json")
        
        try:
            name += "ID"
            if os.path.exists(json_path):
                with open(json_path, 'r',encoding='utf-8') as f:
                    data_dict[name] = json.load(f)
                    print(f"成功: {json_path} を読み込みました")
            else:
                print(f"警告: {json_path} は存在しません")
                data_dict[name] = []  # ファイルが存在しない場合は空リストを設定
        except json.JSONDecodeError as e:
            print(f"エラー: {json_path} のJSONパースに失敗しました: {e}")
            data_dict[name] = []
        except Exception as e:
            print(f"エラー: {json_path} の読み込み中に予期しないエラーが発生しました: {e}")
            data_dict[name] = []
    
    return data_dict

def load_json_data_files(item_list, base_dir):
    data_dict = {}
    for item in item_list:
        name = item.get('name')
        if not name or not isinstance(name, str):
            print(f"警告: 不正なnameが見つかりました: {item}")
            continue
        
        # JSONファイルのパスを構築
        json_path = os.path.join(DATA_DIR, base_dir, name, f"{name}.class.json")
        
        try:
            if os.path.exists(json_path):
                with open(json_path, 'r',encoding='utf-8') as f:
                    data_dict[name] = json.load(f)
                    print(f"成功: {json_path} を読み込みました")
            else:
                print(f"警告: {json_path} は存在しません")
                data_dict[name] = []  # ファイルが存在しない場合は空リストを設定
        except json.JSONDecodeError as e:
            print(f"エラー: {json_path} のJSONパースに失敗しました: {e}")
            data_dict[name] = []
        except Exception as e:
            print(f"エラー: {json_path} の読み込み中に予期しないエラーが発生しました: {e}")
            data_dict[name] = []
    
    return data_dict

# 型リスト取得
def get_type_lists():
    basic_types = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object']
    unity_types = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject']
    enum_list = json.load(open(os.path.join(DATA_DIR, ENUM, 'enum_list.json'))) if os.path.exists(os.path.join(DATA_DIR, ENUM, 'enum_list.json')) else []
    class_list = json.load(open(os.path.join(DATA_DIR, CLASS_DATA, 'class_list.json'))) if os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, 'class_list.json')) else []
    class_data_id_list = json.load(open(os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json'))) if os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')) else []
    # enum_listとclass_listからJSONファイルを読み込む
    enum_data = load_json_files(enum_list, ENUM)
    class_data_id = load_json_files(class_data_id_list, CLASS_DATA_ID)
    class_data = load_json_data_files(class_list,CLASS_DATA)
    return (
    basic_types,
    unity_types,
    [e.get('name') for e in enum_list] if enum_list else [],
    [c.get('name') for c in class_list] if class_list else [],
    [c.get('name') for c in class_data_id_list] if class_data_id_list else [],
    enum_data if enum_data else [],
    class_data_id if class_data_id else [],
    class_data if class_data else []
)
    
def get_json_enum(name):
    enum_data = json.load(open(os.path.join(DATA_DIR, ENUM,f"{name}", f"{name}.json"))) if os.path.exists(os.path.join(DATA_DIR, ENUM,f"{name}", f"{name}.json")) else []
    return enum_data

def get_json_data_id(name):
    data_id = json.load(open(os.path.join(DATA_DIR, CLASS_DATA_ID,f"{name}", f"{name}.json"))) if os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID,f"{name}", f"{name}.json")) else []
    return data_id


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

        protected void IsActiveOff()
        {
            is_active = false;
        }

        public abstract void Enter(T state_manager_data);
        public abstract void Update(T state_manager_data);
        public abstract void Exit(T state_manager_data);
        
        public virtual E BranchNextState(T state_manager_data)
        {
            return default;
        }
"""
    with open(os.path.join(DATA_DIR, STATE_DATA, "BaseState.cs"), 'w', encoding='utf-8') as f:
        f.write(f"using GameCore.States.Managers;\nusing System;\nnamespace GameCore.States\n{{\n    public abstract class  BaseState<E,T>where E : Enum where T : BaseStateManagerData<E>\n    {{{code_str}\n    }}\n}}\n")

STATE_BRANCH = os.path.join(DATA_DIR, STATE_DATA)


os.makedirs(STATE_BRANCH, exist_ok=True)


files_content = {


    # BaseStateControl
    os.path.join(STATE_BRANCH, "BaseStateControl.cs"): """
using System;
using System.Collections.Generic;
namespace GameCore.States.Control
{
    public abstract class BaseStateControl<T, E, F>
        where T : Enum
        where E : GameCore.States.Managers.BaseStateManagerData<T>,new()
        where F : GameCore.States.BaseState<T,E>
    {

        protected E state_manager_data = new E();
        public E StateManagerData{get { return state_manager_data; }}

        protected F state;

        protected bool is_finish = false;
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
    T state_id,
    Action<E> action)
        {
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
            f.write("using System;\n")
            f.write("using System.Collections.Generic;\n")
            f.write(content)
        print(f"Created: {path}")
    else:
        print(f"Skipped (exists): {path}")


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
    using System.Collections.Generic;

    namespace GameCore.Tables
    {
        public abstract class BaseClassDataID<T,E> : BaseTable where T : Enum where E : BaseClassDataRow
        {
            public static Dictionary<T,E> Table = new Dictionary<T,E>();
            public override abstract void Read(BinaryReader reader);
            public override void Release()
            {
                Table.Clear();
            }
        }
    }
    """
    with open(os.path.join(DATA_DIR, CLASS_DATA_ID, "BaseClassDataID.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
# BaseTable.cs を生成
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID, "BaseTable.cs")):
    code_str = """
    using System.IO;
    using System;
    using System.Collections.Generic;

    namespace GameCore.Tables
    {
        public abstract class BaseTable
        {

            public abstract void Read(BinaryReader reader);
            public abstract void Release();

        }
    }
    """
    with open(os.path.join(DATA_DIR, CLASS_DATA_ID, "BaseTable.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")


# --- BaseStateBranch.cs ---
base_branch_path = os.path.join(DATA_DIR, STATE_BRANCH, 'BaseStateBranch.cs')
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
base_detail_path = os.path.join(DATA_DIR, STATE_BRANCH, 'BaseDetailStateBranch.cs')
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
    
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID)):
    os.makedirs(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID))
    
    
# BaseTable.cs を生成
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "BaseTableMatrix.cs")):
    code_str = """
    using System.IO;
    using System;
    using System.Collections.Generic;

    namespace GameCore.Tables
    {
        public abstract class BaseTableMatrix : BaseTable
        {

            public override abstract void Read(BinaryReader reader);
            public override abstract void Release();

        }
    }
    """
    with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "BaseTableMatrix.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")

# BaseClassDataMatrixID.cs 生成 (初回のみ)
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "BaseClassDataMatrixID.cs")):
    code_str = """
    using System.IO;
    using System;
    using System.Collections.Generic;

    namespace GameCore.Tables
    {
        public abstract class BaseClassDataMatrixID<TRow, TCol, E> : BaseTableMatrix where TRow : Enum where TCol : Enum where E : BaseClassDataMatrixRow
        {
            public static Dictionary<TRow, Dictionary<TCol, E>> Table = new Dictionary<TRow, Dictionary<TCol, E>>();
            public override abstract void Read(BinaryReader reader);
            public override void Release()
            {
                Table.Clear();
            }
        }
    }
    """
    with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "BaseClassDataMatrixID.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")

# BaseClassDataMatrixRow.cs 生成
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "BaseClassDataMatrixRow.cs")):
    code_str = """
    using System.IO;

    namespace GameCore.Tables
    {
        public abstract class BaseClassDataMatrixRow
        {
            public abstract void Read(BinaryReader reader);
        }
    }
    """
    with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "BaseClassDataMatrixRow.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
#BaseCustomClassData
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, "BaseCustomClassData.cs")):
    code_str = """
    using System.IO;

    namespace GameCore.Classes
    {
        public abstract class BaseCustomClassData
        {
            public abstract void Read(BinaryReader reader);
        }
    }
    """
    with open(os.path.join(DATA_DIR, CLASS_DATA, "BaseCustomClassData.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")

#ClassDataIDCore.cs 生成
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID, "ClassDataIDCore.cs")):
    code_str = """
using Cysharp.Threading.Tasks;
using GameCore;
using GameCore.Tables;
using System.IO;
using System.Threading;
using System;
using UnityEngine;
using UnityEngine.AddressableAssets;                    // ← 追加
using UnityEngine.ResourceManagement.AsyncOperations;   // ← 追加

public class ClassDataIDCore : BaseSingleton<ClassDataIDCore>
{
    private ClassDataHeader m_classDataTables;
    private CancellationToken cts;
    private bool isLoaded;
    public bool IsLoaded => isLoaded;

    public override void AwakeSingleton()
    {
        base.AwakeSingleton();
        instance = this;
        if (cts == null) cts = this.GetCancellationTokenOnDestroy();
        isLoaded = false;
        
        DontDestroyOnLoad(instance);
    }
    

    private void OnDestroy()
    {
    }

    /// <summary>
    /// ALL_ID_BIN を読み込み（Addressable対応追加）
    /// </summary>
    public async UniTask LoadClassDataAsync(Func<BinaryReader, ClassDataHeader, UniTask> onLoaded, bool addressable = false)
    {
        if (cts == null) cts = this.GetCancellationTokenOnDestroy();
        if (isLoaded) return;

        string path = addressable == true ?  SupportFiles.ID_BIN_FILE  :  SupportFiles.ALL_ID_BIN;

        try
        {
            if (!addressable)
            {
                // 従来の同期ファイル読み込み
                using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read))
                using (BinaryReader reader = new BinaryReader(fs))
                {
                    if (m_classDataTables == null) m_classDataTables = new ClassDataHeader(reader);
                    if (onLoaded != null)
                    {
                        await ExecuteOnThreadPoolAndReturn(onLoaded, reader, m_classDataTables, cts);
                    }
                    isLoaded = true;
                }
            }
            else
            {
                // ====================== Addressableの場合 ======================
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(path);

                TextAsset textAsset = await handle.ToUniTask(cancellationToken: cts);

                if (textAsset == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {path}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return;
                }

                using (MemoryStream ms = new MemoryStream(textAsset.bytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    if (m_classDataTables == null) m_classDataTables = new ClassDataHeader(reader);
                    if (onLoaded != null)
                    {
                        await ExecuteOnThreadPoolAndReturn(onLoaded, reader, m_classDataTables, cts);
                    }
                    isLoaded = true;
                }

                if (handle.IsValid()) Addressables.Release(handle);
            }
        }
        catch (OperationCanceledException)
        {
            Debug.LogWarning("TableIDCoreの読み込みがキャンセルされました。");
        }
        catch (Exception ex)
        {
            Debug.LogError($"読み込み中にエラーが発生: {ex}");
        }
    }

    private async UniTask ExecuteOnThreadPoolAndReturn(
        Func<BinaryReader, ClassDataHeader, UniTask> action,
        BinaryReader reader,
        ClassDataHeader classDataHeader,
        CancellationToken token)
    {
#if UNITY_WEBGL
        await action(reader, classDataHeader).AttachExternalCancellation(token);
#else
        await UniTask.SwitchToThreadPool();
        await action(reader, classDataHeader).AttachExternalCancellation(token);
        await UniTask.SwitchToMainThread();
#endif
    }
}


    """
    with open(os.path.join(DATA_DIR, CLASS_DATA_ID, "ClassDataIDCore.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
#ClassDataMatrixIDCore.cs 生成
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "ClassDataMatrixIDCore.cs")):
    code_str = """
using Cysharp.Threading.Tasks;
using GameCore;
using GameCore.Tables;
using System.IO;
using System.Threading;
using System;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

public class ClassDataMatrixIDCore : BaseSingleton<ClassDataMatrixIDCore>
{
    private ClassDataMatrixHeader m_classDataTables;
    private CancellationToken cts;
    private bool isLoaded;

    public override void AwakeSingleton()
    {
        base.AwakeSingleton();
        instance = this;
        if (cts == null) cts = this.GetCancellationTokenOnDestroy();
        isLoaded = false;
        DontDestroyOnLoad(instance);
    }


    private void OnDestroy()
    {

    }

    /// <summary>
    /// all_class_data.bin を読み込み、BinaryReader をラムダに渡して実行
    /// </summary>
    public async UniTask LoadClassDataAsync(Func<BinaryReader, ClassDataMatrixHeader, UniTask> onLoaded, bool addressable = false)
    {
        if (cts == null) cts = this.GetCancellationTokenOnDestroy();
        if (isLoaded) return;

        string path = addressable == true ? SupportFiles.MATRIX_ID_BIN_FILE : SupportFiles.ALL_MATRIX_ID_BIN;

        try
        {
            if (!addressable)
            {
                // 従来の同期ファイル読み込み
                using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read))
                using (BinaryReader reader = new BinaryReader(fs))
                {
                    if (m_classDataTables == null) m_classDataTables = new ClassDataMatrixHeader(reader);
                    if (onLoaded != null)
                    {
                        await ExecuteOnThreadPoolAndReturn(onLoaded, reader, m_classDataTables, cts);
                    }
                    isLoaded = true;
                }
            }
            else
            {
                // ====================== Addressableの場合 ======================
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(path);

                TextAsset textAsset = await handle.ToUniTask(cancellationToken: cts);

                if (textAsset == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {path}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return;
                }

                using (MemoryStream ms = new MemoryStream(textAsset.bytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    if (m_classDataTables == null) m_classDataTables = new ClassDataMatrixHeader(reader);
                    if (onLoaded != null)
                    {
                        await ExecuteOnThreadPoolAndReturn(onLoaded, reader, m_classDataTables, cts);
                    }
                    isLoaded = true;
                }

                if (handle.IsValid()) Addressables.Release(handle);
            }
        }
        catch (OperationCanceledException)
        {
            Debug.LogWarning("TableIDCoreの読み込みがキャンセルされました。");
        }
        catch (Exception ex)
        {
            Debug.LogError($"読み込み中にエラーが発生: {ex}");
        }
    }

    private async UniTask ExecuteOnThreadPoolAndReturn(
    Func<BinaryReader, ClassDataMatrixHeader, UniTask> action,
    BinaryReader reader,
    ClassDataMatrixHeader classDataHeader,
    CancellationToken token)
    {
#if UNITY_WEBGL
        await action(reader, classDataHeader).AttachExternalCancellation(token);
#else
        await UniTask.SwitchToThreadPool();
        await action(reader, classDataHeader).AttachExternalCancellation(token);
        await UniTask.SwitchToMainThread();
#endif
    }

}



    """
    
    with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "ClassDataMatrixIDCore.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR, SCRIPT)):
    os.makedirs(os.path.join(DATA_DIR, SCRIPT))
    
if not os.path.exists(os.path.join(DATA_DIR, SCRIPT,EDITOR)):
    os.makedirs(os.path.join(DATA_DIR, SCRIPT,EDITOR))
    
if not os.path.exists(os.path.join(DATA_DIR, SCRIPT,"SupportFiles.cs")):
    code_str = """
using UnityEngine;
using System;
using System.IO;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace GameCore
{
    /// <summary>
    /// サポートデータ内の代表的なファイルを一箇所で定義して取得できるヘルパー。
    /// ALL_SOUND_BIN など、呼び出し側はその名前だけ参照すればフルパスが返る。
    /// </summary>
    public static class SupportFiles
    {
        public const string SUPPORT_ROOT_NAME = "SupportChigadio";
        public const string SUPPORT_DATA_NAME = "data";

        // data直下のフォルダ
        public const string ASSETS_FOLDER = "assets-data";
        public const string SOUND_FOLDER = "sound";
        public const string TEXTURE_FOLDER = "texture";
        public const string GAMEOBJECT_FOLDER = "gameobject";

        //dataID
        public const string ID_FOLDER = "class_data_id";
        public const string ID_BIN_FILE = "all_class_data.bytes";

        //matrixID
        public const string MATRIX_DATA_ID_FOLDER = "class_data_matrix_id";
        public const string MATRIX_ID_BIN_FILE = "all_class_data_matrix.bytes";

        // ファイル名（ここだけ定義すればOK）
        public const string ALL_SOUND_BIN_FILE = "sound_data.bytes";
        public const string ALL_TEXTURE_BIN_FILE = "texture_data.bytes";
        public const string ALL_GAMEOBJECT_BIN_FILE = "gameobject_data.bytes";

        //Scenario
        public const string SCENARIO_FOLDER = "scenario_data";
        public const string SCENARIO_EVEMT_FOLDER = "scenario_event_data";
        public const string ALL_SCENARIO_EVENT_BIN_FILE = "all_events.bytes";

        // キャッシュ（最初に解決したパスを保持）
        public static string s_cachedSupportDataPath = null;

        /// <summary>
        /// SupportChigadio/data のフルパスを取得（キャッシュあり／EditorではAssetDatabaseを試行）
        /// </summary>
        private static string SupportDataPath
        {
            get
            {
                if (!string.IsNullOrEmpty(s_cachedSupportDataPath)) return s_cachedSupportDataPath;

#if UNITY_EDITOR
                // EditorならAssetDatabaseでまず探す（ただしメインスレッドでないと例外になる可能性があるので try/catch）
                try
                {
                    string assetsRelative = FindFolderPathByAssetDatabase(SUPPORT_ROOT_NAME); // "Assets/..."
                    if (!string.IsNullOrEmpty(assetsRelative))
                    {
                        string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
                        string absoluteSupportRoot = Path.GetFullPath(Path.Combine(projectRoot, assetsRelative)); // -> .../Project/Assets/.../SupportChigadio
                        string dataPath = Path.Combine(absoluteSupportRoot, "..", SUPPORT_DATA_NAME);
                        s_cachedSupportDataPath = Path.GetFullPath(dataPath).Replace("\\\\", "/");
                        return s_cachedSupportDataPath;
                    }
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"AssetDatabase lookup failed (maybe called from background thread): {e.Message}. Falling back to filesystem.");
                }
#endif
                // ファイルシステム上での候補（projectRoot/SupportChigadio/data）
                string projectRootFs = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
                string candidate = Path.Combine(projectRootFs, SUPPORT_ROOT_NAME, SUPPORT_DATA_NAME);
                if (Directory.Exists(candidate))
                {
                    s_cachedSupportDataPath = Path.GetFullPath(candidate).Replace("\\\\", "/");
                    return s_cachedSupportDataPath;
                }

                // それでも見つからなければプロジェクト内を検索（重い可能性あり）
                try
                {
                    var dirs = Directory.GetDirectories(projectRootFs, SUPPORT_ROOT_NAME, SearchOption.AllDirectories);
                    if (dirs != null && dirs.Length > 0)
                    {
                        string found = dirs[0];
                        string dataPath = Path.Combine(found, SUPPORT_DATA_NAME);
                        s_cachedSupportDataPath = Path.GetFullPath(dataPath).Replace("\\\\", "/");
                        return s_cachedSupportDataPath;
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"Fallback search failed: {ex.Message}");
                }

                // 最後の最終手段：Project直下の GameData を使う
                string fallback = Path.Combine(projectRootFs, "GameData");
                s_cachedSupportDataPath = Path.GetFullPath(fallback).Replace("\\\\", "/");
                return s_cachedSupportDataPath;
            }
        }

        /// <summary>
        /// これだけ参照すれば all_sound.bytes のフルパスが得られる（呼び出し側はこれだけ見れば良い）
        /// </summary>
        public static string ALL_SOUND_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ASSETS_FOLDER, SOUND_FOLDER, ALL_SOUND_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_TEXTURE_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ASSETS_FOLDER, TEXTURE_FOLDER, ALL_TEXTURE_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_GAMEOBJECT_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ASSETS_FOLDER, GAMEOBJECT_FOLDER, ALL_GAMEOBJECT_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_MATRIX_ID_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, MATRIX_DATA_ID_FOLDER, MATRIX_ID_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_ID_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ID_FOLDER, ID_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_SCENARIO_EVENTS_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, SCENARIO_FOLDER, SCENARIO_EVEMT_FOLDER, ALL_SCENARIO_EVENT_BIN_FILE)).Replace("\\\\", "/");

#if UNITY_EDITOR
        // Editor専用：AssetDatabaseで探して "Assets/..." を返す（失敗すれば null）
        private static string FindFolderPathByAssetDatabase(string folderName)
        {
            string[] guids = AssetDatabase.FindAssets("t:folder " + folderName, new[] { "Assets" });
            foreach (var guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid); // "Assets/...."
                if (AssetDatabase.IsValidFolder(path) && Path.GetFileName(path) == folderName)
                    return path;
            }
            return null;
        }
#endif

        /// <summary>
        /// 補助：絶対パスがプロジェクト内（Projectルート）に含まれるなら "Assets/..." 相対パスを返す。AssetDatabase系APIに渡したいときに使える。
        /// </summary>
        public static string GetAssetRelativePath(string absolutePath)
        {
            if (string.IsNullOrEmpty(absolutePath)) return null;
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..")).Replace("\\\\", "/");
            absolutePath = Path.GetFullPath(absolutePath).Replace("\\\\", "/");
            if (absolutePath.StartsWith(projectRoot, StringComparison.OrdinalIgnoreCase))
            {
                string rel = absolutePath.Substring(projectRoot.Length).TrimStart('/', '\\\\');
                return rel;
            }
            return null;
        }

        /// <summary>
        /// 存在確認のショートカット
        /// </summary>
        public static bool ALL_SOUND_BIN_Exists => File.Exists(ALL_SOUND_BIN);
        
                /// <summary>
        /// Addressableのチェック
        /// </summary>
        public static bool ADDRESSABLE_CHECK = true;
    }
}

"""
    with open(os.path.join(DATA_DIR, SCRIPT,"SupportFiles.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")

if not os.path.exists(os.path.join(DATA_DIR, SCRIPT,EDITOR,"SupportFilesPostprocessor.cs")):
    code_str = """
    #if UNITY_EDITOR
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;
using System.IO;
using System.Collections.Generic;
using GameCore;

public class SupportFilesPostprocessor : IPostprocessBuildWithReport
{
    public int callbackOrder => 100;

    public void OnPostprocessBuild(BuildReport report)
    {
        string buildDir = Path.GetDirectoryName(report.summary.outputPath);
        if (string.IsNullOrEmpty(buildDir)) return;

        // コピー対象のファイルと、それぞれの SupportChigadio/data 以下の相対フォルダ
        var allFiles = new List<(string filePath, string targetSubFolder)>
        {
            (SupportFiles.ALL_SOUND_BIN, Path.Combine(SupportFiles.ASSETS_FOLDER, SupportFiles.SOUND_FOLDER)),
            (SupportFiles.ALL_TEXTURE_BIN, Path.Combine(SupportFiles.ASSETS_FOLDER, SupportFiles.TEXTURE_FOLDER)),
            (SupportFiles.ALL_GAMEOBJECT_BIN, Path.Combine(SupportFiles.ASSETS_FOLDER, SupportFiles.GAMEOBJECT_FOLDER)),
            (SupportFiles.ALL_MATRIX_ID_BIN, SupportFiles.MATRIX_DATA_ID_FOLDER),
            (SupportFiles.ALL_ID_BIN, SupportFiles.ID_FOLDER),
            (SupportFiles.ALL_SCENARIO_EVENTS_BIN,Path.Combine(SupportFiles.SCENARIO_FOLDER,SupportFiles.SCENARIO_EVEMT_FOLDER))
        };

        foreach (var (filePath, targetFolder) in allFiles)
        {
            CopySupportFileToTargetFolder(filePath, buildDir, targetFolder);
        }
    }

    private void CopySupportFileToTargetFolder(string sourceFilePath, string buildRoot, string targetSubFolder)
    {
        if (!File.Exists(sourceFilePath))
        {
            Debug.LogWarning($"[SupportFilesPostprocessor] Source file not found: {sourceFilePath}");
            return;
        }

        string destPath = Path.Combine(buildRoot, SupportFiles.SUPPORT_ROOT_NAME, SupportFiles.SUPPORT_DATA_NAME, targetSubFolder, Path.GetFileName(sourceFilePath));

        // コピー先フォルダを作成
        string destDir = Path.GetDirectoryName(destPath);
        if (!Directory.Exists(destDir))
            Directory.CreateDirectory(destDir);

        // 上書きコピー
        File.Copy(sourceFilePath, destPath, true);
        Debug.Log($"[SupportFilesPostprocessor] Copied {sourceFilePath} -> {destPath}");
    }
}
#endif

    """
    
    with open(os.path.join(DATA_DIR, SCRIPT,EDITOR,"SupportFilesPostprocessor.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,DEBUG)):
    os.mkdir(os.path.join(DATA_DIR,SCRIPT,DEBUG))
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG)):
    os.makedirs(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG))
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG,"DebugLogBridgeRuntime.cs")):
    code_str = '''
    using System;
using System.Net.WebSockets;
using UnityEngine;
using WebSocketSharp;
using WebSocket = WebSocketSharp.WebSocket;

public class DebugLogBridgeRuntime : MonoBehaviour
{
    private WebSocket ws;
    private const string WebSocketUrl = "ws://localhost:8765"; // Python WebSocketサーバーのURL
    private float reconnectTimer;
    private bool isConnecting;

    void Awake()
    {
        TryConnect();
        DontDestroyOnLoad(this);
    }

    void Update()
    {
        // 再接続監視
        reconnectTimer += Time.deltaTime;
        if (reconnectTimer > 5f)
        {
            reconnectTimer = 0f;
            if (ws == null || ws.ReadyState != WebSocketSharp.WebSocketState.Open)
            {
                TryConnect();
            }
        }
    }

    private void TryConnect()
    {
        if (isConnecting) return; // 接続試行中の重複防止
        isConnecting = true;

        try
        {
            // 既存の接続を閉じる
            ws?.Close();

            // 新しいWebSocketを作成
            ws = new WebSocket(WebSocketUrl);

            // イベントハンドラを設定（メインスレッドで実行）
            ws.OnOpen += (sender, e) =>
            {
                UnityEngine.Debug.Log("WebSocket connected successfully!");
            };

            ws.OnError += (sender, e) =>
            {
                UnityEngine.Debug.LogWarning($"WebSocket error: {e.Message}");
                ws = null; // 再接続をトリガー
            };

            ws.OnClose += (sender, e) =>
            {
                UnityEngine.Debug.Log($"WebSocket disconnected. Reason: {e.Reason}");
                ws = null; // 再接続をトリガー
            };

            // オプション: サーバーからのメッセージ受信（必要に応じて有効化）
            // ws.OnMessage += (sender, e) =>
            // {
            //     UnityEngine.Debug.Log($"Received message: {e.Data}");
            // };

            // 非同期接続を試行
            ws.ConnectAsync();
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogWarning($"DebugBridge WebSocket connection failed: {e.Message}");
            ws = null;
        }
        finally
        {
            isConnecting = false;
        }
    }

    public void SendLog(string message, string type)
    {
        if (ws == null || ws.ReadyState != WebSocketSharp.WebSocketState.Open)
        {
            UnityEngine.Debug.LogWarning("WebSocket not connected. Skipping send.");
            return;
        }

        var json = JsonUtility.ToJson(new LogData
        {
            message = message,
            type = type,
            time = DateTime.Now.ToString("HH:mm:ss")
        });

        try
        {
            ws.Send(json);
            UnityEngine.Debug.Log($"Sent log: [{type}] {message}");
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogWarning($"Failed to send log: {e.Message}");
            ws = null; // 再接続をトリガー
        }
    }

    [Serializable]
    private class LogData
    {
        public string message;
        public string type;
        public string time;
    }

    void OnDestroy()
    {
        if (ws != null)
        {
            ws.Close();
            ws = null;
        }
    }
}
    '''
    with open(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG,"DebugLogBridgeRuntime.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,ENUM,"EnumIDIter.cs")):
    code_str = """
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
namespace GameCore
{
    public readonly struct EnumIDIter<T> where T : unmanaged, Enum
    {
        private readonly int _value;

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public EnumIDIter(T value)
        {
            _value = Unsafe.As<T, int>(ref value);
    #if UNITY_EDITOR
            if (!Enum.IsDefined(typeof(T), value))
                throw new ArgumentException($"Invalid enum value: {value}");
    #endif
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static implicit operator EnumIDIter<T>(T value) => new(value);

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static implicit operator T(EnumIDIter<T> iter)
        {
            int val = iter._value;
            return Unsafe.As<int, T>(ref val);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static EnumIDIter<T> operator ++(EnumIDIter<T> iter)
        {
            int next = iter._value + 1;
            T nextEnum = Unsafe.As<int, T>(ref next);
    #if UNITY_EDITOR
            if (!Enum.IsDefined(typeof(T), nextEnum))
                throw new InvalidOperationException($"Enum value out of range: {next}");
    #endif
            return new(nextEnum);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static bool operator <(EnumIDIter<T> a, EnumIDIter<T> b) => a._value < b._value;
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static bool operator >(EnumIDIter<T> a, EnumIDIter<T> b) => a._value > b._value;
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static bool operator ==(EnumIDIter<T> a, EnumIDIter<T> b) => a._value == b._value;
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static bool operator !=(EnumIDIter<T> a, EnumIDIter<T> b) => a._value != b._value;
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static bool operator <=(EnumIDIter<T> a, EnumIDIter<T> b) => a._value <= b._value;
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static bool operator >=(EnumIDIter<T> a, EnumIDIter<T> b) => a._value >= b._value;

        public override bool Equals(object obj) => obj is EnumIDIter<T> other && this == other;
        public override int GetHashCode() => _value.GetHashCode();
    }
}

    """
    with open(os.path.join(DATA_DIR,ENUM,"EnumIDIter.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
    
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG,"DebugLogBridge.cs")):
    code_str = '''
using System.Diagnostics;
using UnityEngine;

/// <summary>
/// デバッグ汎用関数
/// </summary>
public static class DebugLogBridge
{
    private static DebugLogBridgeRuntime runtime;

    [Conditional("UNITY_EDITOR")]
    [Conditional("DEVELOPMENT_BUILD")]
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    private static void Init()
    {
        if (UnityEngine.Debug.isDebugBuild || Application.isEditor)
        {
            var go = new GameObject("DebugBridge");
            Object.DontDestroyOnLoad(go);
            runtime = go.AddComponent<DebugLogBridgeRuntime>();
        }
    }

    [Conditional("UNITY_EDITOR")]
    [Conditional("DEVELOPMENT_BUILD")]
    public static void Log(string message)
    {
        UnityEngine.Debug.Log(message);
        runtime?.SendLog(message, "Log");
    }

    [Conditional("UNITY_EDITOR")]
    [Conditional("DEVELOPMENT_BUILD")]
    public static void LogWarning(string message)
    {
        UnityEngine.Debug.LogWarning(message);
        runtime?.SendLog(message, "Warning");
    }

    [Conditional("UNITY_EDITOR")]
    [Conditional("DEVELOPMENT_BUILD")]
    public static void LogError(string message)
    {
        UnityEngine.Debug.LogError(message);
        runtime?.SendLog(message, "Error");
    }
}

    '''
    with open(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG,"DebugLogBridge.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,"BaseSingleton.cs")):
    code_str = '''
using NUnit.Framework;
using UnityEngine;

namespace GameCore
{
    public class BaseSingleton<T> : MonoBehaviour where T : MonoBehaviour
    {
        protected static T instance;

        public static T Instance
        {
            get
            {
                if (instance == null)
                {
                    // まず、既にシーン内にあるかチェック
                    instance =  GameObject.FindAnyObjectByType<T>(FindObjectsInactive.Exclude);

                    if (instance == null)
                    {
                        // まだなければ新しく生成
                        GameObject instanceObj = new GameObject();
                        instance = instanceObj.AddComponent<T>();
                        instanceObj.name = typeof(T).Name;
                    }
                }

                return instance;
            }
        }

        public virtual void AwakeSingleton()
        {
            if (instance == null)
            {
                instance = gameObject.GetComponent<T>();
            }
        }

        public void Awake()
        {
            AwakeSingleton();
        }

    }
}


    '''
    with open(os.path.join(DATA_DIR,SCRIPT,"BaseSingleton.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
    
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,"FastEnumBitFlags.cs")):
        code_str = """
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
namespace GameCore.Utils
{
    public sealed class FastEnumBitFlags<TEnum> where TEnum : struct, Enum
    {
        private readonly ulong[] _bits;
        private readonly int _bitCount;
        private readonly int _arrayLength;

        public FastEnumBitFlags()
        {
            var values = (TEnum[])Enum.GetValues(typeof(TEnum));
            int maxValue = values.Select(v => Convert.ToInt32(v)).Max();
            _bitCount = maxValue + 1;
            if (_bitCount <= 0)
                throw new ArgumentException("Enum must contain at least one non-negative value.");

            _arrayLength = (_bitCount + 63) / 64;
            _bits = new ulong[_arrayLength];
        }


        private FastEnumBitFlags(ulong[] bits, int bitCount, int arrayLength)
        {
            _bits = bits;
            _bitCount = bitCount;
            _arrayLength = arrayLength;
        }

        #region 基本操作（従来通り）

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public bool IsSet(TEnum flag)
        {
            int index = Convert.ToInt32(flag);
            return index > 0 && index < _bitCount && GetBit(index);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void Set(TEnum flag)
        {
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount) SetBit(index);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void Clear(TEnum flag)
        {
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount) ClearBit(index);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void Toggle(TEnum flag)
        {
            int index = Convert.ToInt32(flag);
            if (index >= 0 && index < _bitCount)
                FlipBit(index);
        }

        #endregion

        #region 演算付きビット操作（XOR / AND / OR）

        /// <summary>
        /// XOR 演算でビット操作
        /// flag = true  → 反転
        /// flag = false → 何もしない
        /// </summary>
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void XORBit(TEnum flag, bool value)
        {
            if (!value) return;
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount)
                FlipBit(index);
        }

        /// <summary>
        /// AND 演算でビット操作
        /// flag = true  → 何もしない
        /// flag = false → クリア
        /// </summary>
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void ANDBit(TEnum flag, bool value)
        {
            if (value) return;
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount)
                ClearBit(index);
        }

        /// <summary>
        /// OR 演算でビット操作
        /// flag = true  → セット
        /// flag = false → 何もしない
        /// </summary>
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void ORBit(TEnum flag, bool value)
        {
            if (!value) return;
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount)
                SetBit(index);
        }

        #endregion

        #region 内部ヘルパー（インライン）

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private bool GetBit(int index)
        {
            int arrayIdx = index >> 6;
            int bitIdx = index & 63;
            return (_bits[arrayIdx] & (1UL << bitIdx)) != 0;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void SetBit(int index)
        {
            int arrayIdx = index >> 6;
            int bitIdx = index & 63;
            _bits[arrayIdx] |= 1UL << bitIdx;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void ClearBit(int index)
        {
            int arrayIdx = index >> 6;
            int bitIdx = index & 63;
            _bits[arrayIdx] &= ~(1UL << bitIdx);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void FlipBit(int index)
        {
            int arrayIdx = index >> 6;
            int bitIdx = index & 63;
            _bits[arrayIdx] ^= 1UL << bitIdx;
        }

        #endregion

        #region ユーティリティ

        public void ClearAll() => Array.Clear(_bits, 0, _arrayLength);

        public void SetAll()
        {
            for (int i = 0; i < _arrayLength - 1; i++)
                _bits[i] = ulong.MaxValue;
            int rem = _bitCount & 63;
            _bits[_arrayLength - 1] = rem > 0 ? (1UL << rem) - 1 : ulong.MaxValue;
        }

        public FastEnumBitFlags<TEnum> Clone()
        {
            var clone = new ulong[_arrayLength];
            Buffer.BlockCopy(_bits, 0, clone, 0, _bits.Length * 8);
            return new FastEnumBitFlags<TEnum>(clone, _bitCount, _arrayLength);
        }

        public IEnumerable<TEnum> GetSetFlags()
        {
            for (int i = 1; i < _bitCount; i++)
            {
                if (GetBit(i) && Enum.IsDefined(typeof(TEnum), i))
                    yield return (TEnum)(object)i;
            }
        }

        #endregion
    }
}
        """
        with open(os.path.join(DATA_DIR,SCRIPT,"FastEnumBitFlags.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)
            
#python版 -DataClassID-
if not os.path.exists(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseClassDataRow.py")):
    code = """
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseClassDataRow(ABC):
    @abstractmethod
    def read(self, reader):
        pass

    @classmethod
    def from_json(cls, data: dict) -> 'BaseClassDataRow':
        raise NotImplementedError("from_json must be implemented in subclass")
    """
    with open(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseClassDataRow.py"), 'w', encoding='utf-8') as f:
        f.write(code)
if not os.path.exists(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseTable.py")):
    code = """
from abc import ABC, abstractmethod


class BaseTable(ABC):
    @abstractmethod
    def read(self, reader):
        pass

    @abstractmethod
    def release(self):
        pass
    """
    with open(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseTable.py"), 'w', encoding='utf-8') as f:
        f.write(code)
        
if not os.path.exists(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseClassDataID.py")):
    code = """
from abc import ABC
from typing import Dict
from enum import Enum
from BaseTable import BaseTable
from BaseClassDataRow import BaseClassDataRow


class BaseClassDataID(BaseTable, ABC):
    Table: Dict[Enum, BaseClassDataRow] = {}

    def release(self):
        self.__class__.Table.clear()

    @classmethod
    def load_from_json(cls, json_data: dict):
        cls.Table.clear()
        for enum_name, row_data in json_data.items():
            try:
                enum_val = cls._get_enum(enum_name)
            except (KeyError, AttributeError):
                raise ValueError(f"Unknown enum name: {enum_name}")
            row = cls._get_row_class().from_json(row_data)
            cls.Table[enum_val] = row

    @classmethod
    def _get_enum(cls, name: str):
        raise NotImplementedError("サブクラスでオーバーライドしてください")

    @classmethod
    def _get_row_class(cls):
        raise NotImplementedError("サブクラスでオーバーライドしてください")
    """
    with open(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseClassDataID.py"), 'w', encoding='utf-8') as f:
        f.write(code)
        
#python版 -ClassData-
if not os.path.exists(os.path.join(DATA_DIR,CLASS_DATA,"BaseCustomClassData.py")):
    code = """
from abc import ABC, abstractmethod
class BaseCustomClassData(ABC):
    @abstractmethod
    def read(self, reader):
        pass

    def load_json(self, data):
        pass
    """
    with open(os.path.join(DATA_DIR,CLASS_DATA,"BaseCustomClassData.py"), 'w', encoding='utf-8') as f:
        f.write(code)

#js版　-BinaryReader-
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,"BinaryReader.js")):
    code = """
export class BinaryReader {
    constructor(buffer) {
        this._buffer = buffer;   // ArrayBuffer 推奨
        this._offset = 0;
    }

    readInt32() {
        const value = new Int32Array(this._buffer, this._offset, 1)[0];
        this._offset += 4;
        return value;
    }
    
    readInt16() {
        const value = new Int16Array(this._buffer, this._offset, 1)[0];
        this._offset += 2;
        return value;
    }
    
    readInt64() {
        const value = new BigInt64Array(this._buffer, this._offset, 1)[0];
        this._offset += 8;
        return value;

    }

    readFloat32() {
        const value = new Float32Array(this._buffer, this._offset, 1)[0];
        this._offset += 4;
        return value;
    }

    readBoolean() {
        const value = new Uint8Array(this._buffer, this._offset, 1)[0] !== 0;
        this._offset += 1;
        return value;
    }

    readString() {
        const len = this.readInt32();
        if (len <= 0) return "";
        const bytes = new Uint8Array(this._buffer, this._offset, len);
        this._offset += len;
        return new TextDecoder("utf-8").decode(bytes);
    }

    readDouble() {
        const value = new Float64Array(this._buffer, this._offset, 1)[0];
        this._offset += 8;
        return value;
    }

    readUint() {
        const value = new Uint32Array(this._buffer, this._offset, 1)[0];
        this._offset += 4;
        return value;
    }

    readVector2() {
        return {
            x: this.readFloat32(),
            y: this.readFloat32()
        };
    }

    readVector3() {
        return {
            x: this.readFloat32(),
            y: this.readFloat32(),
            z: this.readFloat32()
        };
    }
    
    readChar()
    {
        const value = new Uint16Array(this._buffer, this._offset, 1)[0];
        this._offset += 2;
        return value;

    }
}
    """
    with open(os.path.join(DATA_DIR,SCRIPT,"BinaryReader.js"), 'w', encoding='utf-8') as f:
        f.write(code)

#js版 -DataClassID-
if not os.path.exists(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseClassDataID.js")):
    code = """
import { BaseTable } from './BaseTable.js';
import { BaseClassDataRow } from './BaseClassDataRow.js';

export class BaseClassDataID extends BaseTable {
  static Table = new Map();

  release() {
    this.constructor.Table.clear();
  }

  static loadFromJson(jsonData) {
    this.Table.clear();
    for (const [enumName, rowData] of Object.entries(jsonData)) {
      const enumVal = this._getEnum(enumName);
      const row = this._getRowClass().fromJson(rowData);
      this.Table.set(enumVal, row);
    }
  }

  static _getEnum(name) {
    throw new Error('_getEnum must be implemented in subclass');
  }

  static _getRowClass() {
    throw new Error('_getRowClass must be implemented in subclass');
  }
}
    """
    with open(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseClassDataID.js"), 'w', encoding='utf-8') as f:
        f.write(code)
if not os.path.exists(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseTable.js")):
    code = """
export class BaseTable {
  read(reader) { throw new Error('read must be implemented'); }
  release() { throw new Error('release must be implemented'); }
}
    """
    with open(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseTable.js"), 'w', encoding='utf-8') as f:
        f.write(code)

if not os.path.exists(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseClassDataRow.js")):
    code = """
export class BaseClassDataRow {
  read(reader) { throw new Error('read must be implemented'); }
  static fromJson(data) { throw new Error('fromJson must be implemented'); }
}
    """
    with open(os.path.join(DATA_DIR,CLASS_DATA_ID,"BaseClassDataRow.js"), 'w', encoding='utf-8') as f:
        f.write(code)
        
if not os.path.exists(os.path.join(DATA_DIR,CLASS_DATA,"BaseCustomClassData.js")):
    code = """

export class BaseCustomClassData {
    read(view, offset) {
        throw new Error("read() must be implemented");
    }
    loadJson(data) {
        throw new Error("loadJson() must be implemented");
    }
}
    """
    with open(os.path.join(DATA_DIR,CLASS_DATA,"BaseCustomClassData.js"), 'w', encoding='utf-8') as f:
        f.write(code)

#Pythonのワークスペース場所作成
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,PYTHON)):
    os.mkdir(os.path.join(DATA_DIR,SCRIPT,PYTHON))

if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,PYTHON,"app.py")):
    code = """
import os
import sys

if getattr(sys, 'frozen', False):
    # exe実行時
    # 一つ前
    base_dir = os.path.abspath(os.path.join(sys.executable, ".."))
else:
    # 開発時
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if base_dir not in sys.path:
    sys.path.append(base_dir)

isDbg = True
# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
    isDbg = False
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
def main():
    pass

if __name__ == "__main__":
    main()
    """
    
    with open(os.path.join(DATA_DIR,SCRIPT,PYTHON,"app.py"), 'w', encoding='utf-8') as f:
        f.write(code + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,PYTHON,"myproject.code-workspace")):
    code = """
{
  "folders": [
    {
      "path": "."
    }
  ]
}
"""
    with open(os.path.join(DATA_DIR,SCRIPT,PYTHON,"myproject.code-workspace"), 'w', encoding='utf-8') as f:
        f.write(code.strip() + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,PYTHON,"vscode.bat")):
    code = """
@echo off
cd /d "%~dp0"
code "%~dp0myproject.code-workspace"
exit
    """
    with open(os.path.join(DATA_DIR,SCRIPT,PYTHON,"vscode.bat"), 'w', encoding='utf-8') as f:
        f.write(code.strip() + "\n")


if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,OBJECTPOOL)):
    os.mkdir(os.path.join(DATA_DIR,SCRIPT,OBJECTPOOL))
            



        
#TableID MatrixTableID の事前作成
new_entries = [
    {'name': 'TableID',"namespace" :"Enums","Path":CLASS_DATA_ID},
    {'name': 'MatrixTableID',"namespace" : "Tables","Path": CLASS_DATA_MATRIX_ID},
]

for entry in new_entries:
    path_file_path = os.path.join(DATA_DIR,f"{entry['Path']}",f"{entry['name']}.cs")
    if not os.path.exists(path_file_path):
        code_str = f"""
namespace GameCore.{entry['namespace']}
{{
    public enum {entry['name']}
    {{
        None = 0,
        Max
    }}
}}
"""
        with open(path_file_path, 'w', encoding='utf-8') as f:
            f.write(code_str)
        
    
    
    
    
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

@app.route('/api/enum/<name>', methods=['GET', 'POST', 'DELETE'])
def manage_enum_detail(name):
    
    
    file_path = os.path.join(DATA_DIR, ENUM, name.replace("ID",""), f'{name}.json')
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

@app.route('/api/generate-enum/<name>', methods=['POST'])
def generate_enum_cs(name):
    try:
        data = request.get_json()
        logger.debug(f"Generating C# enum for {name}: {data}")
        valid_data = [item for item in data if not isnan(item['value']) and isfinite(item['value'])]
        cs_content = "namespace GameCore.Enums\n{\n"
        cs_content += f"    public enum {name}ID\n    {{\n"
        cs_content += "        None = 0, // デフォルト値\n"
        defauldFlag = False
        default = "None"
        for item in valid_data:
            if defauldFlag == False:
                default = f"{item['property']}"
                defauldFlag = True
            cs_content += f"        {item['property']} = {item['value']}, // {item['description']}\n"
        max_value = max([item['value'] for item in valid_data], default=-1) + 1
        cs_content += f"        Max = {max_value}\n"
        cs_content += "    }\n}"
        cs_path = os.path.join(DATA_DIR, ENUM, f"{name}", f"{name}ID.cs")
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)
            
        #Extension
        cs_path = os.path.join(DATA_DIR, ENUM, f"{name}", f"{name}IDExtensions.cs")
        cs_content = f"""
using System;
using UnityEngine;
using System.Collections.Generic;
namespace GameCore.Enums
{{
    public static class {name}IDExtensions
    {{
        public static int ToInt(this {name}ID id)
        {{
            return (int)id;
        }}
        public static {name}ID To{name}ID(this int id)
        {{
            return ({name}ID)id;
        }}
        public static int ToIndex(this {name}ID id)
        {{
            return (int)id - 1;
        }}
        public static void ForID(Action<{name}ID> action)
        {{
            if (action == null) throw new ArgumentNullException(nameof(action));
            for (EnumIDIter<{name}ID> id = {name}ID.{default}; id < {name}ID.Max; id++)
            {{
                action(id);
            }}
        }}
        public static List<{name}ID> FindAll(Func<{name}ID, bool> predicate)
        {{
            if (predicate == null) throw new ArgumentNullException(nameof(predicate));

            var results = new List<{name}ID>();
            for (EnumIDIter<{name}ID> id = {name}ID.{default}; id < {name}ID.Max; id++)
            {{
                {name}ID value = id;
                if (!Enum.IsDefined(typeof({name}ID), value))
                    continue; // 無効な値はスキップ
                if (predicate(value))
                    results.Add(value);
            }}

            return results;
        }}

        public static {name}ID Find(Func<{name}ID, bool> predicate)
        {{
            if (predicate == null) throw new ArgumentNullException(nameof(predicate));

            for (EnumIDIter<{name}ID> id = {name}ID.{default}; id < {name}ID.Max; id++)
            {{
                {name}ID value = id;
                if (!Enum.IsDefined(typeof({name}ID), value))
                    continue; // 無効な値はスキップ
                if (predicate(value))
                    return value;
            }}

            return {name}ID.None; // デフォルト値（必要に応じて変更）
        }}
        
        
        
    }}
}}
        """
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)
            
        py_content = generators.generate_enum_python(name, data)
        js_content = generators.generate_enum_js(name, data)

        py_path = os.path.join(DATA_DIR, ENUM, name, f"{name}ID.py")
        js_path = os.path.join(DATA_DIR, ENUM, name, f"{name}ID.js")

        with open(py_path, 'w+', encoding='utf-8') as f:
            f.write(py_content)
        with open(js_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
        
        return jsonify({"message": f"C# enum {name}ID generated successfully"})
    except Exception as e:
        logger.error(f"Error generating C# enum {name}: {str(e)}")
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
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data= get_type_lists()
        if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, name)):
            os.makedirs(os.path.join(DATA_DIR, CLASS_DATA, name), exist_ok=True)
        cs_path = os.path.join(DATA_DIR, CLASS_DATA,name, f"Base{name}.cs")
        
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
            f.write("namespace GameCore.Classes\n{\n")
            f.write(f"    public class Base{name} : BaseCustomClassData\n    {{\n")
            read_codes = []
            for item in data:
                field_data = generate_csharp_field(item, enum_list, class_list, unity_types, basic_types,class_data_id_list)
                f.write(field_data['field'])
                read_codes.append(field_data['read'])
            f.write(f"\n        public Base{name}() : base() {{ }}\n        public override void Read(BinaryReader reader)        {{\n")
            for read_code in read_codes:
                f.write(read_code)
            f.write("        }\n")
            f.write("    }\n}\n")
        cs_path = os.path.join(DATA_DIR, CLASS_DATA,name, f"{name}.cs")
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
            f.write("namespace GameCore.Classes\n{\n")
            f.write(f"    public class {name} : Base{name}\n    {{\n")
            f.write("    }\n}\n")
            
        py_path = generators.generate_class_python(name, data, enum_list, class_list, class_data_id_list)
        js_path = generators.generate_class_js(name, data, enum_list, class_list, class_data_id_list)
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
    
def generate_binary_data(name, json_data):
    import io
    f = io.BytesIO()

    rows = json_data.get('rows', [])
    columns = json_data.get('columns', [])
    basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data = get_type_lists()

    f.write(struct.pack('i', len(rows)))
    f.write(struct.pack('i', len(columns)))

    if name == "MobGuest":
        print("aaa")

    for col in columns:
        name_encoded = col['name'].encode('utf-8')
        type_encoded = col['type'].encode('utf-8')
        f.write(struct.pack('i', len(name_encoded)))
        f.write(name_encoded)
        f.write(struct.pack('i', len(type_encoded)))
        f.write(type_encoded)

    for row in rows:
        f.write(struct.pack('i', row.get('id', 0)))
        for col in columns:
            cell = row['data'].get(col['name'], {})
            value = cell.get('value') if isinstance(cell, dict) else cell

            if isinstance(value, (int, float)) and (isnan(value) or not isfinite(value)):
                f.write(struct.pack('i', 0))
                continue

            write_binary_field(
                f, value, col['type'],
                basic_types, unity_types, enum_list, class_list,
                class_data_id_list, enum_data, class_data_id, class_data
            )

    return f.getvalue()

@app.route('/api/generate-all-binary', methods=['POST'])
def generate_all_binary():
    try:
        all_binary_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'all_class_data.bytes')

        list_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')
        with open(list_path, 'r', encoding='utf-8') as f:
            class_list = json.load(f)

        # ① 先にすべてのセクションを生成しておく
        sections = {}
        for item in class_list:
            name = item['name']
            file_path = os.path.join(DATA_DIR, CLASS_DATA_ID, name, f'{name}.json')
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            sections[name] = generate_binary_data(name, json_data)

        # ② ヘッダーサイズを正確に計算
        # 構造: [count:4] + 各エントリ[id:4][name_len:4][name:N][offset:8][size:4]
        header_size = 4  # count
        for item in class_list:
            name_len = len(item['name'].encode('utf-8'))
            header_size += 4 + 4 + name_len + 8 + 4

        # ③ オフセットを計算
        current_offset = header_size
        offsets = {}
        for item in class_list:
            name = item['name']
            offsets[name] = current_offset
            current_offset += len(sections[name])

        # ④ ヘッダーを構築
        header = bytearray()
        header.extend(struct.pack('i', len(class_list)))
        for item in class_list:
            name = item['name']
            name_encoded = name.encode('utf-8')
            header.extend(struct.pack('i', item['id']))
            header.extend(struct.pack('i', len(name_encoded)))
            header.extend(name_encoded)
            header.extend(struct.pack('q', offsets[name]))   # 正しいオフセット
            header.extend(struct.pack('i', len(sections[name])))  # 正しいサイズ

        # ⑤ 1回で書き込む
        with open(all_binary_path, 'wb') as f:
            f.write(header)
            for item in class_list:
                f.write(sections[item['name']])

        logger.info("Generated all_class_data.bytes")
        return jsonify({"message": "All binary generated successfully"})

    except Exception as e:
        logger.error(f"Error generating all binary: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-table-id', methods=['POST'])
def generate_table_id():
    try:
        table_id_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'TableID.cs')
        class_list_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')
        with open(class_list_path, 'r', encoding='utf-8') as f:
            class_list = json.load(f)
        
        cs_content = "namespace GameCore.Enums\n{\n"
        cs_content += "    public enum TableID\n    {\n"
        cs_content += "        None = 0,\n"
        for item in class_list:
            cs_content += f"        {item['name']} = {item['id']},\n"
        max_id = max([item['id'] for item in class_list], default=0) + 1
        cs_content += f"        Max = {max_id}\n"
        cs_content += "    }\n}"
        
        with open(table_id_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)
        
        return jsonify({"message": "TableID enum generated successfully"})
    except Exception as e:
        logger.error(f"Error generating TableID: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-all-enums', methods=['POST'])
def generate_all_enums():
    try:
        enum_list_path = os.path.join(DATA_DIR, ENUM, 'enum_list.json')
        with open(enum_list_path, 'r', encoding='utf-8') as f:
            enum_list = json.load(f)
        
        for enum_item in enum_list:
            name = enum_item['name']
            file_path = os.path.join(DATA_DIR, ENUM, name, f'{name}.json')
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            valid_data = [item for item in data if not isnan(item['value']) and isfinite(item['value'])]
            cs_content = "namespace GameCore.Enums\n{\n"
            cs_content += f"    public enum {name}ID\n    {{\n"
            cs_content += "        None = 0, // デフォルト値\n"
            for item in valid_data:
                cs_content += f"        {item['property']} = {item['value']}, // {item['description']}\n"
            max_value = max([item['value'] for item in valid_data], default=-1) + 1
            cs_content += f"        Max = {max_value}\n"
            cs_content += "    }\n}"
            
            cs_path = os.path.join(DATA_DIR, ENUM, f"{name}.cs")
            with open(cs_path, 'w', encoding='utf-8') as f:
                f.write(cs_content)
        
        return jsonify({"message": "All enums (excluding TableID) generated successfully"})
    except Exception as e:
        logger.error(f"Error generating all enums: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-all-cs-header', methods=['POST'])
def generate_all_cs_header():
    try:
        cs_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'ClassDataHeader.cs')
        list_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')
        
        cs_content = """
using System;
using System.IO;
using System.Collections.Generic;
using GameCore.Enums;

namespace GameCore.Tables
{
    public class ClassDataHeader
    {
        public Dictionary<TableID, (string Name, long Offset, int Size)> Entries = new Dictionary<TableID, (string, long, int)>();

        public ClassDataHeader(BinaryReader reader)
        {
            int count = reader.ReadInt32();
            for(int i = 0; i < count; i++)
            {
                int id = reader.ReadInt32();
                TableID tableId = (TableID)Enum.ToObject(typeof(TableID), id);
                int nameLen = reader.ReadInt32();
                string name = new string(reader.ReadChars(nameLen));
                long offset = reader.ReadInt64();
                int size = reader.ReadInt32();
                Entries[tableId] = (name, offset, size);
            }
        }

        public TTable GetData<TTable>(TableID id, BinaryReader reader) where TTable : BaseTable,new()
        {
            if (!Entries.TryGetValue(id, out var entry)) return null;
            reader.BaseStream.Seek(entry.Offset, SeekOrigin.Begin);
            TTable data = new TTable();
            data.Read(reader);
            return data;
        }


    }
}
"""
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)
        generate_tags_load_script()
        return jsonify({"message": "C# header generated successfully"})
    except Exception as e:
        logger.error(f"Error generating C# header: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
    
cs_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'ClassDataHeader.cs')
list_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')
        
cs_content = """
using System;
using System.IO;
using System.Collections.Generic;
using GameCore.Enums;

namespace GameCore.Tables
{
    public class ClassDataHeader
    {
        public Dictionary<TableID, (string Name, long Offset, int Size)> Entries = new Dictionary<TableID, (string, long, int)>();

        public ClassDataHeader(BinaryReader reader)
        {
            int count = reader.ReadInt32();
            for(int i = 0; i < count; i++)
            {
                int id = reader.ReadInt32();
                TableID tableId = (TableID)Enum.ToObject(typeof(TableID), id);
                int nameLen = reader.ReadInt32();
                string name = new string(reader.ReadChars(nameLen));
                long offset = reader.ReadInt64();
                int size = reader.ReadInt32();
                Entries[tableId] = (name, offset, size);
            }
        }

        public TTable GetData<TTable>(TableID id, BinaryReader reader) where TTable : BaseTable,new()
        {
            if (!Entries.TryGetValue(id, out var entry)) return null;
            reader.BaseStream.Seek(entry.Offset, SeekOrigin.Begin);
            TTable data = new TTable();
            data.Read(reader);
            return data;
        }


    }
}
"""
with open(cs_path, 'w', encoding='utf-8') as f:
    f.write(cs_content)


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
    file_path = os.path.join(DATA_DIR, CLASS_DATA_ID, name.replace("ID",""), f"{name}.json")
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

@app.route('/api/generate-class-data-id/<name>', methods=['POST'])
def generate_class_data_id_cs(name):
    try:
        data = request.get_json()
        columns = data['columns']
        rows = data['rows']
        basic_types, unity_types, enum_list, class_list, class_data_id_list ,enum_data,class_data_id,class_data= get_type_lists()
        enum_name = f"{name}TableID"  # Enum名をTableIDに変更

        # 出力ディレクトリ作成
        table_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, f"{name}")
        os.makedirs(table_dir, exist_ok=True)
        
        #-- Row ---
        with open(os.path.join(table_dir, f"{name}Row.cs"), 'w', encoding='utf-8') as lf:
            # --- Row Class ---
            lf.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\nusing GameCore.Tables.ID;\n\n")
            lf.write("namespace GameCore.Tables\n{\n")
            lf.write(f"    public class {name}Row : BaseClassDataRow\n    {{\n")
            for col in columns:
                type_str = col['type'].replace("[]", "")
                if type_str in enum_list:
                    type_str = f"GameCore.Enums.{type_str}ID"
                elif type_str in class_list:
                    type_str = f"GameCore.Classes.{type_str}"
                elif type_str in class_data_id_list:
                    type_str = f"GameCore.Tables.ID.{type_str}TableID"
                elif type_str.lower() in ['vector2', 'vector3']:
                    type_str = type_str.capitalize()
                if "[]" in col['type']:
                    type_str = f"List<{type_str}>"
                lf.write(f"            private {type_str} {col['name']};\n")
                lf.write(f"            public {type_str} {col['name'].capitalize()} {{ get => {col['name']}; }}\n")
                
            # --- Read Method ---
            lf.write("\n            public override void Read(BinaryReader reader)\n")
            lf.write("            {\n")
            for i, col in enumerate(columns):
                type_lower = col['type'].lower().replace("[]", "")
                
                array_type = ""
                if col['type'].replace("[]", "") in class_data_id_list:
                    array_type = f"GameCore.Tables.ID.{col['type'].replace('[]', '')}TableID"
                elif col['type'].replace("[]", "") in enum_list:
                    array_type = f"GameCore.Enums.{col['type'].replace('[]', '')}ID"
                elif col['type'].replace("[]", "") in class_list:
                    array_type = f"GameCore.Classes.{col['type'].replace('[]', '')}"
            
                #配列対応
                array_size = 0
                if "[]" in col['type']:
                    array_size = -1
                if array_size == -1:
                    col['type'] = col['type'].replace("[]", "")
                    lf.write(f"                int count{i} = reader.ReadInt32();\n")
                    lf.write(f"                {col['name']} = new List<{array_type if array_type else col['type']}>();\n")
                    lf.write(f"                for(int j=0; j<count{i}; j++) {{\n")
                    if type_lower in TYPE_MAP:
                        if type_lower == 'string':
                            lf.write(f"                    int len{col['name']} = reader.ReadInt32();\n")
                            lf.write(f"                    {col['name']}.Add(System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len{col['name']})));\n")
                        elif type_lower == 'vector2':
                            lf.write(f"                    {col['name']}.Add(new Vector2(reader.ReadSingle(), reader.ReadSingle()));\n")
                        elif type_lower == 'vector3':
                            lf.write(f"                    {col['name']}.Add(new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()));\n")
                            
                        else:
                            lf.write(f"                    {col['name']}.Add(reader.{TYPE_MAP[type_lower]['cs_read']}());\n")
                    elif col['type'] in enum_list:
                        lf.write(f"                    {col['name']}.Add((GameCore.Enums.{col['type']}ID)Enum.ToObject(typeof(GameCore.Enums.{col['type']}ID), reader.ReadInt32()));\n")
                    elif col['type'] in class_list:
                        lf.write(f"                    var item = new GameCore.Classes.{col['type']}();\n                    item.Read(reader);\n                    {col['name']}.Add(item);\n")
                    elif col['type'] in class_data_id_list:
                        lf.write(f"                    {col['name']}.Add((GameCore.Tables.ID.{col['type']}TableID)Enum.ToObject(typeof(GameCore.Tables.ID.{col['type']}TableID), reader.ReadInt32()));\n")
                    else:
                        lf.write(f"                    reader.BaseStream.Seek({TYPE_MAP.get(type_lower, {}).get('size', 4)}, SeekOrigin.Current); // Unsupported type, skip\n")
                    lf.write("                }\n")
                elif array_size > 0:
                    col['type'] = col['type'].replace("[]", "")
                    lf.write(f"                {col['name']} = new {array_type if array_type else col['type']}[{array_size}];\n")
                    lf.write(f"                for(int j=0; j<{array_size}; j++) {{\n")
                    if type_lower in TYPE_MAP:
                            if type_lower == 'string':
                                lf.write(f"                    int len{col['name']} = reader.ReadInt32();\n")
                                lf.write(f"                    {col['name']}[j] = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len{col['name']}));\n")
                            elif type_lower == 'vector2':
                                lf.write(f"                    {col['name']}[j] = new Vector2(reader.ReadSingle(), reader.ReadSingle());\n")
                            elif type_lower == 'vector3':
                                lf.write(f"                    {col['name']}[j] = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n")
                            else:
                                lf.write(f"                    {col['name']}[j] = reader.{TYPE_MAP[type_lower]['cs_read']}();\n")
                    elif col['type'] in enum_list:
                            lf.write(f"                    {col['name']}[j] = (GameCore.Enums.{col['type']}ID)Enum.ToObject(typeof(GameCore.Enums.{col['type']}ID), reader.ReadInt32());\n")
                    elif col['type'] in class_list:
                            lf.write(f"                    var item = new GameCore.Classes.{col['type']}();\n                    item.Read(reader);\n                    {col['name']}[j] = item;\n")
                    elif col['type'] in class_data_id_list:
                            lf.write(f"                    {col['name']}[j] = (GameCore.Tables.ID.{col['type']}TableID)Enum.ToObject(typeof(GameCore.Tables.ID.{col['type']}TableID), reader.ReadInt32());\n")
                    else:
                            lf.write(f"                    reader.BaseStream.Seek({TYPE_MAP.get(type_lower, {}).get('size', 4)}, SeekOrigin.Current); // Unsupported type, skip\n")
                    lf.write("                }\n")
                if array_size == 0:
                    if type_lower in TYPE_MAP:
                        if type_lower == 'string':
                            lf.write(f"                int len{i} = reader.ReadInt32();\n")
                            lf.write(f"                {col['name']} = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len{i}));\n")
                        elif type_lower == 'vector2':
                            lf.write(f"                {col['name']} = new Vector2(reader.ReadSingle(), reader.ReadSingle());\n")
                        elif type_lower == 'vector3':
                            lf.write(f"                {col['name']} = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n")
                        else:
                            lf.write(f"                {col['name']} = reader.{TYPE_MAP[type_lower]['cs_read']}();\n")
                    elif col['type'] in enum_list:
                        lf.write(f"                {col['name']} = (GameCore.Enums.{col['type']}ID)Enum.ToObject(typeof(GameCore.Enums.{col['type']}ID), reader.ReadInt32());\n")
                    elif col['type'] in class_list:
                        lf.write(f"                {col['name']} = new GameCore.Classes.{col['type']}();\n                {col['name']}.Read(reader);\n")
                    elif col['type'] in class_data_id_list:
                        lf.write(f"                {col['name']} = (GameCore.Tables.ID.{col['type']}TableID)Enum.ToObject(typeof(GameCore.Tables.ID.{col['type']}TableID), reader.ReadInt32());\n")
                    else:
                        lf.write(f"                {col['name']} = default; // Unsupported\n")
            lf.write("            }\n")
            lf.write("        }\n\n")
            lf.write("}\n\n")

        # --- Main Table File ---
        cs_path = os.path.join(table_dir, f"{name}Table.cs")
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\nusing GameCore.Tables.ID;\n\n")
            f.write("namespace GameCore.Tables\n{\n")
            f.write(f"    public class {name}Table : BaseClassDataID<{enum_name}, {name}Row>\n    {{\n")
            #f.write(f"        public static Dictionary<{enum_name}, {name}Row> Table = new Dictionary<{enum_name}, {name}Row>();\n\n")

            # --- Table Constructor ---
            f.write(f"        public override void Read(BinaryReader reader)\n        {{\n")
            f.write(f"            {name}Table.Table.Clear();\n")
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
        defaultFlag = False
        default = "None"
        with open(enum_cs_path, 'w', encoding='utf-8') as ef:
            ef.write("using System;\n\n")
            ef.write("namespace GameCore.Tables.ID\n{\n")
            ef.write(f"    public enum {name}TableID\n    {{\n")
            ef.write("        None = 0,\n")
            for i, row in enumerate(rows, start=1):
                if defaultFlag == False:
                    default = row['enum_property']
                    defaultFlag = True
                ef.write(f"        {row['enum_property']} = {i},\n")
            ef.write("        Max\n")
            ef.write("    }\n}\n")
            
        # Example
        exsample_cs_path = os.path.join(table_dir, f"{name}TableExample.cs")
        with open(exsample_cs_path, 'w', encoding='utf-8') as ef:
            template = f"""
using System;
using UnityEngine;
using GameCore.Tables;
using GameCore.Tables.ID;
using System.Collections.Generic;
namespace GameCore.Tables
{{
    public static class {name}IDExtensions
    {{
        public static {name}Row GetRow(this {name}TableID id)
        {{
            if ({name}Table.Table.TryGetValue(id, out var row))
            {{
                return row;
            }}
            else
            {{
                return null; // または throw new KeyNotFoundException()
            }}
        }}
        public static int ToInt(this {name}TableID id)
        {{
            return (int)id;
        }}
        
        public static int ToIndex(this {name}TableID id)
        {{
            return (int)id - 1;
        }}
        public static {name}TableID To{name}TableID(this int id)
        {{
            return ({name}TableID)id;
        }}
        public static void ForID(Action<{name}TableID> action)
        {{
            if (action == null) throw new ArgumentNullException(nameof(action));
            for (EnumIDIter<{name}TableID> id = {name}TableID.{default}; id < {name}TableID.Max; id++)
            {{
                action(id);
            }}
        }}
        public static List<{name}TableID> FindAll(Func<{name}TableID, bool> predicate)
        {{
            if (predicate == null) throw new ArgumentNullException(nameof(predicate));
            var results = new List<{name}TableID>();
            for (EnumIDIter<{name}TableID> id = {name}TableID.{default}; id < {name}TableID.Max; id++)
            {{
                {name}TableID value = id;
                if (!Enum.IsDefined(typeof({name}TableID), value))continue; // 無効な値はスキップ
                if (predicate(value))results.Add(value);
            }}
            
            return results;
        }}
        
        public static {name}TableID Find(Func<{name}TableID, bool> predicate)
        {{
            if (predicate == null) throw new ArgumentNullException(nameof(predicate));
            for (EnumIDIter<{name}TableID> id = {name}TableID.{default}; id < {name}TableID.Max; id++)
            {{
                {name}TableID value = id;
                if (!Enum.IsDefined(typeof({name}TableID), value))continue; // 無効な値はスキップ
                if (predicate(value))return value;
            }}
            
            return {name}TableID.None; // デフォルト値（必要に応じて変更）
        }}
    }}
}}
            """
            ef.write(template)
            
        py_row_path = generators.generate_row_python(name, columns, rows, enum_list, class_list, class_data_id_list)
        py_table_path = generators.generate_table_python(name, columns, rows, enum_list, class_list, class_data_id_list)

        # Python用 TableID enum
        enum_data = [
            {'property': row['enum_property'], 'value': i + 1, 'description': row.get('description', '')}
            for i, row in enumerate(rows)
        ]
        py_enum_path = os.path.join(table_dir, f"{name}TableID.py")
        with open(py_enum_path, 'w', encoding='utf-8') as f:
            f.write(generators.generate_enum_python(f"{name}TableID", enum_data))

        # JS生成
        js_row_path = generators.generate_row_js(name, columns, rows, enum_list, class_list, class_data_id_list)
        js_table_path = generators.generate_table_js(name, columns, rows, enum_list, class_list, class_data_id_list)

        # JS用 TableID enum
        js_enum_path = os.path.join(table_dir, f"{name}TableID.js")
        with open(js_enum_path, 'w', encoding='utf-8') as f:
            f.write(generators.generate_enum_js(f"{name}TableID", enum_data))

        return jsonify({"message": f"C# files generated: {cs_path}, {enum_cs_path}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
#バイナリ書き込み
def write_binary_field(f, value, type_str, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data):
    
    if type_str.endswith('[]'):
        inner_type = type_str[:-2]
        values = value if isinstance(value, list) else []
        f.write(struct.pack('i', len(values)))
        for v in values:
            write_binary_field(f, v, inner_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data)
        return
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
            
    elif type_str + 'ID' in class_data_id:
        property_name = value['value'].split('.')[-1] if isinstance(value, dict) else value.split('.')[-1] if isinstance(value, str) else ''
        actual_id = next((row['id'] for row in class_data_id[type_str + 'ID']['rows'] if row['enum_property'] == property_name), 0)
        f.write(struct.pack('i', actual_id))

    elif type_str in enum_list:
        #数値ではなければ
        if not isinstance(value, (int, float)):
            # 文字列ならTextureID.以降を取得、辞書ならvalueを使用
            property_name = value.split('.')[-1]
            actual_id = next((item['id'] for item in enum_data[type_str + 'ID'] if item['property'] == property_name), 0) if property_name else 0
            value = actual_id
        # Enumはintとして処理
        f.write(struct.pack('i', int(value) if value is not None else 0))

    elif type_str in class_list:
        # ClassDataの再帰処理
        class_schema_path = os.path.join(DATA_DIR, CLASS_DATA, type_str, f"{type_str}.class.json")
        class_schema = json.load(open(class_schema_path, encoding="utf-8")) if os.path.exists(class_schema_path) else []
        for item in class_schema:  # class_data → class_schema
            array_size = item.get('arraySize', 0)
            item_value = value.get(item['name']) if isinstance(value, dict) else None
            if array_size == -1:  # List
                values = item_value if isinstance(item_value, list) else []
                f.write(struct.pack('i', len(values)))
                for v in values:
                    write_binary_field(f, v, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data)
            elif array_size > 0:  # Array
                values = item_value if isinstance(item_value, list) else [None] * array_size
                for v in values[:array_size]:
                    write_binary_field(f, v, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data)
            else:
                write_binary_field(f, item_value, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data )
    else:
        f.write(struct.pack('i', 0))  # 未サポート型
        
def write_binary_field_extend(f, value, type_str, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data):
    if type_str.endswith('[]'):
        inner_type = type_str[:-2]
        values = value if isinstance(value, list) else []
        f.extend(struct.pack('i', len(values)))
        for v in values:
            write_binary_field_extend(f, v, inner_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data)
        return
    type_lower = type_str.lower()

    if type_lower in TYPE_MAP:
        # 文字列処理
        if type_lower == 'string':
            val_bytes = (value or '').encode('utf-8') if isinstance(value, str) else b''
            f.extend(struct.pack('i', len(val_bytes)))
            f.extend(val_bytes)

        # ベクトル2
        elif type_lower == 'vector2':
            x, y = value if isinstance(value, (list, tuple)) and len(value) >= 2 else [0.0, 0.0]
            f.extend(struct.pack('ff', float(x), float(y)))

        # ベクトル3
        elif type_lower == 'vector3':
            x, y, z = value if isinstance(value, (list, tuple)) and len(value) >= 3 else [0.0, 0.0, 0.0]
            f.extend(struct.pack('fff', float(x), float(y), float(z)))

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
            f.extend(struct.pack(TYPE_MAP[type_lower]['pack'], safe_value))

    elif type_str + 'ID' in class_data_id:
        property_name = value['value'].split('.')[-1] if isinstance(value, dict) else value.split('.')[-1] if isinstance(value, str) else ''
        actual_id = next((row['id'] for row in class_data_id[type_str + 'ID']['rows'] if row['enum_property'] == property_name), 0)
        f.extend(struct.pack('i', actual_id))

    elif type_str in enum_list:
        #数値ではなければ
        if not isinstance(value, (int, float)):
            # 文字列ならTextureID.以降を取得、辞書ならvalueを使用
            property_name = value.split('.')[-1]
            actual_id = next((item['id'] for item in enum_data[type_str + 'ID'] if item['property'] == property_name), 0) if property_name else 0
            value = actual_id
        # Enumはintとして処理
        f.extend(struct.pack('i', int(value) if value is not None else 0))

    elif type_str in class_list:
        # ClassDataの再帰処理
        class_schema_path = os.path.join(DATA_DIR, CLASS_DATA, type_str, f"{type_str}.class.json")
        class_schema = json.load(open(class_schema_path, encoding="utf-8")) if os.path.exists(class_schema_path) else []
        for item in class_schema:  # class_data → class_schema
            array_size = item.get('arraySize', 0)
            item_value = value.get(item['name']) if isinstance(value, dict) else None
            if array_size == -1:  # List
                values = item_value if isinstance(item_value, list) else []
                f.extend(struct.pack('i', len(values)))
                for v in values:
                    write_binary_field_extend(f, v, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data)
            elif array_size > 0:  # Array
                values = item_value if isinstance(item_value, list) else [None] * array_size
                for v in values[:array_size]:
                    write_binary_field_extend(f, v, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data)
            else:
                write_binary_field_extend(f, item_value, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data )
    else:
        f.extend(struct.pack('i', 0))  # 未サポート型


# ClassDataID Binary生成（行のレコード値を正確に書き込み）
@app.route('/api/generate-binary/<name>', methods=['POST'])
def generate_binary(name):
    try:
        data = request.get_json()
        columns = data['columns']
        rows = data['rows']
        bin_path = os.path.join(DATA_DIR, CLASS_DATA_ID, name, f"{name}Table.bytes")
        os.makedirs(os.path.dirname(bin_path), exist_ok=True)
        
        basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data = get_type_lists()
        
        with open(bin_path, 'wb') as f:
            # ヘッダ: 行数, カラム数
            f.write(struct.pack('ii', len(rows), len(columns)))
            
            # カラムメタ: 名前長, 名前, 型名長, 型名
            for col in columns:
                name_bytes = col['name'].encode('utf-8')
                type_bytes = col['type'].encode('utf-8')
                f.write(struct.pack('i', len(name_bytes)))
                f.write(name_bytes)
                f.write(struct.pack('i', len(type_bytes)))
                f.write(type_bytes)
            
            # データ: 行ごとにEnumValue, 各カラム値
            for row in rows:
                f.write(struct.pack('i', row.get('id', 0)))
                for col in columns:
                    col_type = col['type'].lower()
                    col_value = row['data'].get(col['name'])
                    type_id = col['type'] + 'ID'
                    
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
                    
                    elif type_id in enum_data:
                        # 文字列ならTextureID.以降を取得、辞書ならvalueを使用
                        property_name = col_value['value'].split('.')[-1]
                        actual_id = next((item['id'] for item in enum_data[type_id] if item['property'] == property_name), 0)
                        f.write(struct.pack('i', actual_id))
                    
                    elif type_id in class_data_id:
                        # 文字列ならPersonalityID.以降を取得、辞書ならvalueを使用
                        property_name = col_value['value'].split('.')[-1]
                        actual_id = next((row['id'] for row in class_data_id[type_id]['rows'] if row['enum_property'] == property_name), 0)
                        f.write(struct.pack('i', actual_id))
                    
                    elif col['type'] in class_list:
                        # .class.jsonを正しく参照し、col_valueから.valueを取り出す
                        class_schema = json.load(open(os.path.join(DATA_DIR, CLASS_DATA,f"{col['type'].replace('[]', '')}", f"{col['type'].replace('[]', '')}.class.json"), 'r', encoding='utf-8')) if os.path.exists(os.path.join(DATA_DIR, CLASS_DATA,f"{col['type'].replace('[]', '')}", f"{col['type'].replace('[]', '')}.class.json")) else []
                        actual_value = col_value.get('value') if isinstance(col_value, dict) else col_value
                        for item in class_schema:
                            item_value = actual_value.get(item['name'])
                            array_size = item.get('arraySize', 0)
                            if array_size == -1:  # List
                                values = item_value if isinstance(item_value, list) else []
                                f.write(struct.pack('i', len(values)))
                                for v in values:
                                    write_binary_field(f, v, item['type'],basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data)
                            elif array_size > 0:  # Array
                                values = item_value if isinstance(item_value, list) else [None] * array_size
                                for v in values[:array_size]:
                                    write_binary_field(f, v, item['type'],basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data)
                            else:
                                write_binary_field(f, item_value, item['type'],basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data)
                    else:
                        col_name_type = col['type']
                        # 配列型カラム("int[]", "MyClass[]"など)
                        if col_name_type.endswith('[]'):
                            base_type = col_name_type[:-2]
                            arr_vals = actual_value if isinstance(actual_value, list) else []
                            f.write(struct.pack('i', len(arr_vals)))  # 長さを先に書く
                            for v in arr_vals:
                                write_binary_field(f, v, base_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data)
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
        
    with open(file_base_state_manager_data_path, 'w', encoding='utf-8') as f:
        f.write('using System.Collections.Generic;\n')
        f.write('using UnityEngine;\n\n')
        
        f.write('namespace GameCore.States.Managers\n{\n')
        f.write(f'    public class Base{name}StateManagerData : BaseStateManagerData<GameCore.States.ID.{name}StateID>\n    {{\n')
        
        for data in base_code_str:
            f.write(data)
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
            for node in nodes:
                targets = node["data"].get("targets", [])
                for target_id in targets:
                    target_label = node_dict.get(target_id, {}).get("data", {}).get("label", "")
                    if target_label:
                        f.write(f'        public abstract bool {name}{label}_to_{target_label}{int(target_id):02d}({name}StateManagerData manager_data, {name}{label}State state);\n')
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
                f.write('        }\n\n')
                for target_id in targets:
                    target_label = node_dict.get(target_id, {}).get("data", {}).get("label", "")
                    if target_label:
                        f.write(f'        public override abstract bool {name}{label}_to_{target_label}{int(target_id):02d}({name}StateManagerData manager_data, {name}{label}State state);\n')
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
        with open(base_label_state_path, 'w', encoding='utf-8') as f:
            f.write('using UnityEngine;\n')
            f.write('using GameCore.States.Branch;\n\n')
            f.write('namespace GameCore.States\n{\n')
            f.write(f'    public abstract class Base{name}{label}State : GameCore.States.Base{name}State\n')
            f.write('    {\n')


            f.write('    }\n')
            f.write('}\n')

        # {name}{label}{id:02d}State.cs
        state_class_path = os.path.join(state_dir, f'{name}{label}State.cs')
        if os.path.exists(state_class_path):
            # 既存なら追記・削除の調整を実施
            ensure_branchnext_in_state_class(state_class_path, name, label, targets)
        else:
            # 新規生成
            with open(state_class_path, 'w', encoding='utf-8') as f:
                f.write('using UnityEngine;\n\n')
                f.write('using GameCore.States.Branch;\n')
                f.write('namespace GameCore.States\n{\n')
                f.write(f'    public class {name}{label}State : Base{name}{label}State\n')
                f.write('    {\n')
                f.write(f'        public override void Enter(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
                f.write(f'        public override void Update(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
                f.write(f'        public override void Exit(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
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
        if os.path.exists(base_label_state_path):
            continue
        with open(base_label_state_path, 'w', encoding='utf-8') as f:
            f.write('using UnityEngine;\n')
            f.write('using GameCore.States.Branch;\n\n')
            f.write('namespace GameCore.States\n{\n')
            f.write(f'    public abstract class Base{name}{label}State : GameCore.States.Base{name}State\n')
            f.write('    {\n')


            f.write('    }\n')
            f.write('}\n')

        # {name}{label}{id:02d}State.cs
        state_class_path = os.path.join(state_dir, f'{name}{label}State.cs')

  
        # 新規生成
        with open(state_class_path, 'w', encoding='utf-8') as f:
            f.write('using UnityEngine;\n\n')
            f.write('using GameCore.States.Branch;\n')
            f.write('namespace GameCore.States\n{\n')
            f.write(f'    public class {name}{label}State : Base{name}{label}State\n')
            f.write('    {\n')
            f.write(f'        public override void Enter(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
            f.write(f'        public override void Update(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
            f.write(f'        public override void Exit(GameCore.States.Managers.{name}StateManagerData state_manager_data) {{ }}\n')
            f.write('    }\n')
            f.write('}\n')
            
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




# C#フィールド生成（private + ゲッター）
def generate_csharp_field(item, enum_list, class_list, unity_types, basic_types,class_id_list):
    type_str = item['type'].replace("[]", "")
    var_name = item['name']
    array_size = item.get('arraySize', 0)
    description = item.get('description', '')

    # 型変換
    if type_str in enum_list:
        type_str = f"GameCore.Enums.{type_str}ID"
        item['type'] =  type_str
    elif type_str in class_list:
        type_str = f"GameCore.Classes.{type_str}"
        item['type'] =  type_str
    elif type_str in class_id_list:
        type_str = f"GameCore.Tables.ID.{type_str}TableID"
        item['type'] =  type_str
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
    elif type_str.startswith('GameCore.Tables.'):
        initial = f"{type_str}.None"
    else:
        initial = f"new {type_str}()"
        
    find_type = item['type'].replace("[]", "").replace("TableID","").replace("ID","").split('.')[-1]

    # BinaryReader読み込みコード
    read_code = ""
    if is_list:
        read_code = f"            {var_name} = new List<{item['type']}>();\n"
        read_code += f"            int {var_name}_count = reader.ReadInt32();\n"
        read_code += f"            for(int i=0; i<{var_name}_count; i++) {{\n"
        if find_type.lower() in TYPE_MAP:
            if find_type.lower() == 'string':
                read_code += f"                    int len_{var_name} = reader.ReadInt32();\n"
                read_code += f"                    {var_name}.Add(System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len_{var_name})));\n"    
            elif find_type.lower() == 'vector2':
                read_code += f"                {var_name}.Add(new Vector2(reader.ReadSingle(), reader.ReadSingle()));\n"
            elif find_type.lower() == 'vector3':
                read_code += f"                {var_name}.Add(new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()));\n"
            else:
                read_code += f"                {var_name}.Add(reader.{TYPE_MAP[item['type'].lower()]['cs_read']}());\n"
        elif find_type in enum_list:
            read_code += f"                {var_name}.Add(({item['type']})Enum.ToObject(typeof({item['type']}), reader.ReadInt32()));\n"
        elif find_type in class_id_list:
            read_code += f"                {var_name}.Add(({item['type']})Enum.ToObject(typeof({item['type']}), reader.ReadInt32()));\n"
        elif find_type in class_list:
            read_code += f"                var add_data = new {item['type']}();\n"
            read_code += f"                add_data.Read(reader);\n"
            read_code += f"                {var_name}.Add(add_data);\n"
        else:
            read_code += f"                {var_name}.Add(new {item['type']}()); // Unsupported\n"
        read_code += "            }\n"
    elif is_array:
        read_code = f"            {var_name} = new {item['type']}[{array_size}];\n"
        read_code += f"            for(int i=0; i<{array_size}; i++) {{\n"
        if find_type.lower() in TYPE_MAP:
            if find_type.lower() == 'string':
                read_code += f"                    int len_{var_name} = reader.ReadInt32();\n"
                read_code += f"                    {var_name}[i] = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len_{var_name}));\n"
            elif find_type.lower() == 'vector2':
                read_code += f"                {var_name}[i] = new Vector2(reader.ReadSingle(), reader.ReadSingle());\n"
            elif find_type.lower() == 'vector3':
                read_code += f"                {var_name}[i] = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n"
            else:
                read_code += f"                {var_name}[i] = reader.{TYPE_MAP[find_type.lower()]['cs_read']}();\n"
        elif find_type in enum_list:
            read_code += f"                {var_name}[i] = ({item['type']})Enum.ToObject(typeof({item['type']}), reader.ReadInt32());\n"
        elif find_type in class_id_list:
            read_code += f"                {var_name}[i] = ({item['type']})Enum.ToObject(typeof({item['type']}), reader.ReadInt32());\n" 
        elif find_type in class_list:
            read_code += f"                {var_name}[i] = new {item['type']}();\n"
            read_code += f"                {var_name}[i].Read(reader);\n"
        else:
            read_code += f"                {var_name}[i] = new {item['type']}(); // Unsupported\n"
        read_code += "            }\n"
    else:
        if type_str.lower() in TYPE_MAP:
            if type_str.lower() == 'string':
                read_code = f"                    int len_{var_name} = reader.ReadInt32();\n"
                read_code += f"                    {var_name} = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len_{var_name}));\n"
            elif type_str.lower() == 'vector2':
                read_code = f"            {var_name} = new Vector2(reader.ReadSingle(), reader.ReadSingle());\n"
            elif type_str.lower() == 'vector3':
                read_code = f"            {var_name} = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n"
            else:
                read_code = f"            {var_name} = reader.{TYPE_MAP[type_str.lower()]['cs_read']}();\n"
        elif type_str.startswith('GameCore.Enums.'):
            read_code = f"            {var_name} = ({type_str})Enum.ToObject(typeof({type_str}), reader.ReadInt32());\n"
        elif type_str.startswith('GameCore.Tables.'):
            read_code = f"            {var_name} = ({type_str})Enum.ToObject(typeof({type_str}), reader.ReadInt32());\n"
        elif type_str.startswith('GameCore.Classes.'):
            read_code = f"            {var_name} = new {type_str}();\n            {var_name}.Read(reader);\n"
            
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
        f.write('            if (state.IsActive) return;\n\n')
        f.write('            var id = state_manager_data.PopStateID();\n')
        f.write(f'            if(id == {name}StateID.None) id = state_manager_data.GetNowStateID();\n')
        f.write('            switch (id)\n')
        f.write('            {\n')
        
        
        code_label = []
        for node in json_data.get('transitions', []):
            label = node["fromState"]
            node_id = int(node["id"])
            state_id = f"{name}StateID.{label}"
            if label not in code_label:
                code_label.append(label)
                f.write(f'                case {state_id}:\n')
                f.write('                {\n')
                f.write('                    state.Exit(state_manager_data);\n')
                f.write('                    state_manager_data.PopUpStateID();\n')
                f.write('                    id = state_manager_data.PopStateID();\n')
                f.write(f'                    if(id == {name}StateID.None) id = state_manager_data.SaveStateID;\n')
                f.write(f'                    if(id == {name}StateID.None)\n')
                f.write('                    {\n')
                f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
                f.write('                        is_finish = true;\n')
                f.write('                        return;\n')
                f.write('                    }\n')
                f.write(f'                    else\n')
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
                f.write('                    state.Enter(state_manager_data);\n')
                f.write('                    return;\n')
                f.write('                }\n')

        for node in nodes:
            label = node["data"]["label"]
            node_id = int(node["id"])
            state_id = f"{name}StateID.{label}{node_id:02d}"
            targets = node["data"].get("targets", [])

            f.write(f'                case {state_id}:\n')
            f.write('                {\n')
            f.write('                    state.Exit(state_manager_data);\n')
            f.write('                    state_manager_data.PopUpStateID();\n')
            # ターゲットがない → 終了
            if not targets:
                if len(node["data"].get("subNodes", [])) > 0:
                    f.write(f'                    state_manager_data.SaveStateID = {name}StateID.None;\n')
                    for child in node["data"].get("subNodes", []):
                        child_label = child["label"]
                        child_id = f"{name}StateID.{child_label}"
                        f.write(f'                    state_manager_data.PushStateID({child_id});\n')
                    f.write(f'                    var next_id = state_manager_data.PopStateID();\n')
                    f.write('                    state = FactoryState(next_id);\n')
                    f.write('                    if (state == null)\n')
                    f.write('                    {\n')
                    f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
                    f.write(f'                        state_manager_data.SaveStateID = {name}StateID.None;\n')
                    f.write('                        is_finish = true;\n')
                    f.write('                        return;\n')
                    f.write('                    }\n')
                    f.write('                    state.Enter(state_manager_data);\n')
                    f.write('                    return;\n')
                else:
                    f.write('                    is_finish = true;\n')
                    f.write('                    return;\n')
            # ターゲットが1つだけ → 直接遷移
            elif len(targets) == 1:

                next_node = targets[0]
                # 次ノードのラベル取得
                target_label = next(
                    (n["data"]["label"] for n in nodes if n["id"] == next_node), None)
                if target_label:
                    f.write(f'                    var next_id = {name}StateID.{target_label}{int(next_node):02d};\n')
                    
                    if len(node["data"].get("subNodes", [])) > 0:
                        f.write(f'                    state_manager_data.SaveStateID = next_id;\n')
                        for child in node["data"].get("subNodes", []):
                            child_label = child["label"]
                            child_id = f"{name}StateID.{child_label}"
                            f.write(f'                    state_manager_data.PushStateID({child_id});\n')
                        f.write(f'                    state_manager_data.PushStateID(next_id);\n')
                        f.write(f'                    next_id = state_manager_data.PopStateID();\n')
                    else:
                        f.write(f'                    state_manager_data.ChangeStateNowID(next_id);\n')
                    f.write('                    state = FactoryState(next_id);\n')
                    f.write('                    if (state == null)\n')
                    f.write('                    {\n')
                    f.write(f'                        state_manager_data.ChangeStateNowID({name}StateID.None);\n')
                    f.write(f'                        state_manager_data.SaveStateID = {name}StateID.None;\n')
                    f.write('                        is_finish = true;\n')
                    f.write('                        return;\n')
                    f.write('                    }\n')
                    f.write('                    state.Enter(state_manager_data);\n')
                    f.write('                    return;\n')
            # 複数ターゲット → BranchNextStateを呼び出し
            else:      
                f.write(f'                   var next_id = state.BranchNextState(state_manager_data);\n')
                if len(node["data"].get("subNodes", [])) > 0:
                    f.write(f'                    state_manager_data.SaveStateID = next_id;\n')
                    for child in node["data"].get("subNodes", []):
                        child_label = child["label"]
                        child_id = f"{name}StateID.{child_label}"
                        f.write(f'                    state_manager_data.PushStateID({child_id});\n')
                    f.write(f'                    state_manager_data.PushStateID(next_id);\n')
                    f.write(f'                    next_id = state_manager_data.PopStateID();\n')
                else:
                    f.write(f'                    state_manager_data.ChangeStateNowID(next_id);\n')
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
            
# MatrixID管理
@app.route('/api/class-data-matrix-id', methods=['GET', 'POST', 'PATCH'])
def manage_matrix_id():
    file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json')
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        except FileNotFoundError:
            return jsonify([]), 200
    elif request.method == 'POST':
        new_matrix = request.get_json()
        name = new_matrix['name']
        if not name or ':' in name:
            return jsonify({"error": "Invalid name"}), 400
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = []
        if any(item['name'] == name for item in data):
            return jsonify({"error": f"Matrix {name} already exists"}), 400
        max_id = max([item['id'] for item in data], default=0) + 1
        # ★ rowId / colId / tag も一覧側に保持しておく（詳細ページ・タグ機能で参照するため）
        new_entry = {
            "id": max_id,
            "name": name,
            "rowId": new_matrix.get('rowId', ''),
            "colId": new_matrix.get('colId', ''),
            "tag": None,
        }
        data.append(new_entry)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.makedirs(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name), exist_ok=True)
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f"{name}.json"), 'w', encoding='utf-8') as f:
            json.dump(new_matrix, f, indent=2)
        return jsonify({"message": f"Matrix {name} created", "data": new_entry})
    elif request.method == 'PATCH':
        delete_name = request.get_json()['name']
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            shutil.rmtree(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, delete_name), ignore_errors=True)
            return jsonify({"message": "Deleted"})
        except FileNotFoundError:
            return jsonify({"error": "List file not found"}), 404

@app.route('/api/class-data-matrix-id/<name>', methods=['GET', 'POST', 'DELETE'])
def handle_matrix_data(name):
    file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f'{name}.json')
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        except FileNotFoundError:
            return jsonify({"error": f"Matrix {name} not found"}), 404
    elif request.method == 'POST':
        try:
            data = request.get_json()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return jsonify({"message": f"Matrix {name} saved"})
        except Exception as e:
            logger.error(f"Error saving {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'DELETE':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            os.remove(file_path)
            return jsonify({"message": f"Matrix {name} deleted"})
        except FileNotFoundError:
            return jsonify({"error": f"Matrix {name} not found"}), 404
        
# C#生成
@app.route('/api/generate-class-data-matrix-id/<name>', methods=['POST'])
def generate_cs_matrix(name):
    file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f'{name}.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        row_id = json_data['rowId']
        col_id = json_data['colId']
        fields = json_data['fields']
        
        
        
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
        if row_id in class_data_id_list:
            row_id += "Table"
        if col_id in class_data_id_list:
            col_id += "Table"    

        # {name}MatrixRow.cs
        row_cs = f"using System.IO;\nusing System;\nusing System.Collections.Generic;\n\n"
        row_cs += f"namespace GameCore.Tables {{\n    public class {name}MatrixRow : BaseClassDataMatrixRow {{\n"
        read_code = "        public override void Read(BinaryReader reader) {\n"
        for field in fields:
            # ★ Matrixのフィールドは "int[]" のような配列サフィックス表記を使うため、
            #   generate_csharp_field が期待する arraySize 方式に変換してから渡す
            field_for_cs = dict(field)
            if isinstance(field_for_cs.get('type'), str) and field_for_cs['type'].endswith('[]'):
                field_for_cs['type'] = field_for_cs['type'][:-2]
                field_for_cs['arraySize'] = -1  # 動的配列(List)として扱う
            else:
                field_for_cs.setdefault('arraySize', 0)
            field_info = generate_csharp_field(field_for_cs, enum_list, class_list, unity_types, basic_types,class_data_id_list)
            row_cs += field_info['field']
            read_code += field_info['read']
        row_cs += read_code + "        }\n    }\n}\n"
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID,f"{name}", f"{name}MatrixRow.cs"), 'w', encoding='utf-8') as f:
            f.write(row_cs)

        # {name}MatrixID.cs
        matrix_cs = f"using System.IO;\nusing GameCore.Tables.ID;\nusing GameCore.Enums;\nusing System;\nusing System.Collections.Generic;\n\n"
        matrix_cs += f"namespace GameCore.Tables {{\n    public class {name}MatrixTable : BaseClassDataMatrixID<{row_id}ID, {col_id}ID, {name}MatrixRow> {{\n"
        matrix_cs += "        public override void Read(BinaryReader reader) {\n"
        matrix_cs += f"            {name}MatrixTable.Table.Clear();\n"
        matrix_cs += f"            int rowCount = reader.ReadInt32();\n"
        matrix_cs += f"            List<{row_id}ID> rowKeys = new List<{row_id}ID>(); for(int i=0; i<rowCount; i++) rowKeys.Add(({row_id}ID)reader.ReadInt32());\n"
        matrix_cs += f"            int colCount = reader.ReadInt32();\n"
        matrix_cs += f"            List<{col_id}ID> colKeys = new List<{col_id}ID>(); for(int i=0; i<colCount; i++) colKeys.Add(({col_id}ID)reader.ReadInt32());\n"
        matrix_cs += f"            foreach(var rk in rowKeys) {{ Table[rk] = new Dictionary<{col_id}ID, {name}MatrixRow>(); }}\n"
        matrix_cs += f"            foreach(var rk in rowKeys) {{ foreach(var ck in colKeys) {{ var row = new {name}MatrixRow(); row.Read(reader); Table[rk][ck] = row; }} }}\n"
        matrix_cs += "        }\n    }\n}\n"
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID,f"{name}", f"{name}MatrixTable.cs"), 'w', encoding='utf-8') as f:
            f.write(matrix_cs)
        return jsonify({"message": f"C# generated for {name}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# バイナリ生成
@app.route('/api/generate-binary-matrix/<name>', methods=['POST'])
def generate_binary_matrix(name):
    file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f'{name}.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        row_keys = list(json_data['data'].keys())
        col_keys = list(json_data['data'][row_keys[0]].keys()) if row_keys else []
        fields = json_data['fields']
        basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data= get_type_lists()

        row_type_id = json_data['rowId'] + 'ID'
        col_type_id = json_data['colId'] + 'ID'

        def resolve_key_id(type_id, key):
            if type_id in enum_data:
                return next((item['id'] for item in enum_data[type_id] if item['property'] == key), 0)
            elif type_id in class_data_id:
                return next((row['id'] for row in class_data_id[type_id]['rows'] if row['enum_property'] == key), 0)
            return 0

        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f"{name}.bytes"), 'wb') as f:
            f.write(struct.pack('i', len(row_keys)))
            for rk in row_keys:
                f.write(struct.pack('i', resolve_key_id(row_type_id, rk)))
            f.write(struct.pack('i', len(col_keys)))
            for ck in col_keys:
                f.write(struct.pack('i', resolve_key_id(col_type_id, ck)))
            for rk in row_keys:
                for ck in col_keys:
                    cell = json_data['data'][rk][ck]
                    for field in fields:
                        value = cell.get(field['name'])
                        write_binary_field(
                            f, value, field['type'],
                            basic_types, unity_types, enum_list, class_list,
                            class_data_id_list, enum_data, class_data_id, class_data
                        )

        return jsonify({"message": f"Binary generated for {name}"})
    except Exception as e:
        logger.error(f"Error generating binary matrix for {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500



#バイナリデータ生成
def generate_binary_matrix_data(name, json_data):
    binary_data = bytearray()
    row_keys = list(json_data['data'].keys())
    col_keys = list(json_data['data'][row_keys[0]].keys()) if row_keys else []
    rowId = json_data['rowId'] + "ID"
    colId = json_data['colId'] + "ID"
    fields = json_data['fields']
    basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data = get_type_lists()

    def resolve_key_id(type_id, key):
        if type_id in enum_data:
            return next((item['id'] for item in enum_data[type_id] if item['property'] == key), 0)
        elif type_id in class_data_id:
            return next((row['id'] for row in class_data_id[type_id]['rows'] if row['enum_property'] == key), 0)
        return 0

    binary_data.extend(struct.pack('i', len(row_keys)))
    for rk in row_keys:
        binary_data.extend(struct.pack('i', resolve_key_id(rowId, rk)))
    binary_data.extend(struct.pack('i', len(col_keys)))
    for ck in col_keys:
        binary_data.extend(struct.pack('i', resolve_key_id(colId, ck)))
    for rk in row_keys:
        for ck in col_keys:
            cell = json_data['data'][rk][ck]
            for field in fields:
                value = cell.get(field['name'])
                write_binary_field_extend(
                    binary_data, value, field['type'],
                    basic_types, unity_types, enum_list, class_list,
                    class_data_id_list, enum_data, class_data_id, class_data
                )

    return binary_data
#Matrixを一つのバイナリファイルにまとめる
@app.route('/api/generate-all-binary-matrix', methods=['POST'])
def generate_all_binary_matrix():
    try:
        all_binary_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'all_class_data_matrix.bytes')
        header = bytearray()
        data_sections = bytearray()
        
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json'), 'r', encoding='utf-8') as f:
            matrix_list = json.load(f)
        
        header.extend(struct.pack('i', len(matrix_list)))
        
        offsets = {}
        current_offset = 4 + sum(4 + 4 + len(item['name'].encode('utf-8')) + 8 + 4 for item in matrix_list)
        
        for matrix in matrix_list:
            name = matrix['name']
            matrix_id = matrix.get('id', 0)  # IDが定義されていると仮定
            name_encoded = name.encode('utf-8')
            
            header.extend(struct.pack('i', matrix_id))
            header.extend(struct.pack('i', len(name_encoded)))
            header.extend(name_encoded)
            header.extend(struct.pack('q', 0))  # 仮オフセット
            header.extend(struct.pack('i', 0))  # 仮サイズ
            
            file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f'{name}.json')
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                section = generate_binary_matrix_data(name, json_data)
                
                offsets[name] = current_offset
                current_offset += len(section)
                data_sections.extend(section)
        
        with open(all_binary_path, 'wb') as f:
            f.write(header)
            f.write(data_sections)
        
        with open(all_binary_path, 'r+b') as f:
            pos = 4
            for matrix in matrix_list:
                name = matrix['name']
                name_len = len(name.encode('utf-8'))
                pos += 4 + 4 + name_len
                
                f.seek(pos)
                f.write(struct.pack('q', offsets.get(name, 0)))
                
                pos += 8
                file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f'{name}.json')
                section_size = 0
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f2:
                        json_data = json.load(f2)
                    section_size = len(generate_binary_matrix_data(name, json_data))
                f.write(struct.pack('i', section_size))
                
                pos += 4
        
        logger.info("Generated all_class_data_matrix.bytes")
        return jsonify({"message": "All matrix binary generated successfully"})
    except Exception as e:
        logger.error(f"Error generating all matrix binary: {str(e)}")
        return jsonify({"error": str(e)}), 500
#Matrixのヘルパークラス生成
@app.route('/api/generate-all-cs-matrix-header', methods=['POST'])
def generate_all_cs_matrix_header():
    try:
        # ClassDataMatrixHeader.cs
        cs_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'ClassDataMatrixHeader.cs')
        list_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json')

        
        cs_content = """

using System;
using System.IO;
using System.Collections.Generic;
using GameCore.Enums;

namespace GameCore.Tables
{
    public class ClassDataMatrixHeader
    {
        public Dictionary<MatrixTableID, (string Name, long Offset, int Size)> Entries = new Dictionary<MatrixTableID, (string, long, int)>();

        public ClassDataMatrixHeader(BinaryReader reader)
        {
            int count = reader.ReadInt32();
            for(int i = 0; i < count; i++)
            {
                int id = reader.ReadInt32();
                MatrixTableID tableId = (MatrixTableID)Enum.ToObject(typeof(MatrixTableID), id);
                int nameLen = reader.ReadInt32();
                string name = new string(reader.ReadChars(nameLen));
                long offset = reader.ReadInt64();
                int size = reader.ReadInt32();
                Entries[tableId] = (name, offset, size);
            }
        }

        public TTable GetData<TTable>(MatrixTableID id, BinaryReader reader) where TTable : BaseTableMatrix, new()
        {
            if (!Entries.TryGetValue(id, out var entry)) return null;
            reader.BaseStream.Seek(entry.Offset, SeekOrigin.Begin);
            TTable data = new TTable();
            data.Read(reader);
            return data;
        }
    }
}

"""
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)
        generate_matrix_tags_load_script()
        return jsonify({"message": "All C# headers and helper generated"})
    except Exception as e:
        logger.error(f"Error generating C# headers: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
 # ClassDataMatrixHeader.cs
cs_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'ClassDataMatrixHeader.cs')
list_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json')

        
cs_content = """

using System;
using System.IO;
using System.Collections.Generic;
using GameCore.Enums;

namespace GameCore.Tables
{
    public class ClassDataMatrixHeader
    {
        public Dictionary<MatrixTableID, (string Name, long Offset, int Size)> Entries = new Dictionary<MatrixTableID, (string, long, int)>();

        public ClassDataMatrixHeader(BinaryReader reader)
        {
            int count = reader.ReadInt32();
            for(int i = 0; i < count; i++)
            {
                int id = reader.ReadInt32();
                MatrixTableID tableId = (MatrixTableID)Enum.ToObject(typeof(MatrixTableID), id);
                int nameLen = reader.ReadInt32();
                string name = new string(reader.ReadChars(nameLen));
                long offset = reader.ReadInt64();
                int size = reader.ReadInt32();
                Entries[tableId] = (name, offset, size);
            }
        }

        public TTable GetData<TTable>(MatrixTableID id, BinaryReader reader) where TTable : BaseTableMatrix, new()
        {
            if (!Entries.TryGetValue(id, out var entry)) return null;
            reader.BaseStream.Seek(entry.Offset, SeekOrigin.Begin);
            TTable data = new TTable();
            data.Read(reader);
            return data;
        }
    }
}

"""
with open(cs_path, 'w', encoding='utf-8') as f:
    f.write(cs_content)

@app.route('/api/generate-matrix-table-id', methods=['POST'])
def generate_matrix_table_id():
    try:
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
        cs = "namespace GameCore.Tables {\n    public enum MatrixTableID {\n        None = 0,\n"
        for item in data:
            cs += f"        {item['name']} = {item['id']},\n"
        cs += f"        Max,\n"
        cs += "    }\n}\n"
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, "MatrixTableID.cs"), 'w', encoding='utf-8') as f:
            f.write(cs)
        return jsonify({"message": "MatrixTableID generated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
##--------------------------------------------------
# Scenario
def generate_scenario_role_factory():
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, 'scenario_role_list.json')
    roles = []
    if os.path.exists(list_path):
        with open(list_path, 'r', encoding='utf-8') as f:
            roles = json.load(f)

    # Generate ScenarioRoleID enum
    enum_content = """using System;

namespace GameCore.Scenario {
    public enum ScenarioRoleID {
        None = 0,
"""
    for role in roles:
        enum_content += f"        {role['name']} = {role['id']},\n"
    enum_content += """        Max
    }
}
"""
    with open(os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, "ScenarioRoleID.cs"), 'w', encoding='utf-8') as f:
        f.write(enum_content)

    # Generate ScenarioRoleFactory class
    factory_content = """using System;

namespace GameCore.Scenario {
    public static class ScenarioRoleFactory {
        public static BaseScenarioRoleData CreateRoleData(ScenarioRoleID id) {
            switch (id) {
"""
    for role in roles:
        factory_content += f"""                case ScenarioRoleID.{role['name']}:
                    return new {role['name']}RoleData();
"""
    factory_content += """                default:
                    return null;
            }
        }

        public static BaseOrigintScenarioRoleAction CreateRoleAction(BaseScenarioRoleData data) {
            if (data == null) return null;
            switch (data.RoleID) {
"""
    for role in roles:
        factory_content += f"""                case ScenarioRoleID.{role['name']}:
                    return new {role['name']}RoleAction(data as {role['name']}RoleData);
"""
    factory_content += """                default:
                    return null;
            }
        }
    }
}
"""
    with open(os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, "ScenarioRoleFactory.cs"), 'w', encoding='utf-8') as f:
        f.write(factory_content)

@app.route('/api/scenario-role', methods=['GET', 'POST', 'PATCH'])
def handle_scenario_role_list():
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, 'scenario_role_list.json')
    if request.method == 'GET':
        if os.path.exists(list_path):
            with open(list_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump([], f)
        return jsonify([])
    elif request.method == 'POST':
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        branchType = data.get('branchType', 'General')
        if not name:
            return jsonify({"error": "Name is required"}), 400
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                roles = json.load(f)
                max_id = max([r['id'] for r in roles], default=0) + 1
                new_role = {"id": max_id, "name": name, "description": description, "branchType": branchType}
                roles.append(new_role)
                f.seek(0)
                json.dump(roles, f)
        else:
            new_role = {"id": 1, "name": name, "description": description, "branchType": branchType}
            with open(list_path, 'w', encoding='utf-8') as f:
                json.dump([new_role], f)
        role_dir = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, name)
        os.makedirs(role_dir, exist_ok=True)
        with open(os.path.join(role_dir, f"{name}.json"), 'w', encoding='utf-8') as f:
            json.dump([], f)
        generate_scenario_role_factory()  # Generate enum and factory
        return jsonify({"message": "Role created", "data": new_role})
    elif request.method == 'PATCH':  # Used for delete
        data = request.json
        name = data.get('name')
        if not name:
            return jsonify({"error": "Name is required"}), 400
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                roles = json.load(f)
                roles = [r for r in roles if r['name'] != name]
                f.seek(0)
                f.truncate()
                json.dump(roles, f)
        role_dir = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, name)
        if os.path.exists(role_dir):
            shutil.rmtree(role_dir)
        generate_scenario_role_factory()  # Regenerate enum and factory
        return jsonify({"message": "Role deleted"})

@app.route('/api/scenario-role/<name>', methods=['GET', 'POST', 'DELETE'])
def handle_scenario_role_detail(name):
    role_dir = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, name)
    data_path = os.path.join(role_dir, f"{name}.json")
    if request.method == 'GET':
        if os.path.exists(data_path):
            with open(data_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        return jsonify([])
    elif request.method == 'POST':
        data = request.json
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        generate_scenario_role_factory()
        return jsonify({"message": "Data saved"})
    elif request.method == 'DELETE':
        list_path = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, 'scenario_role_list.json')
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                roles = json.load(f)
                roles = [r for r in roles if r['name'] != name]
                f.seek(0)
                f.truncate()
                json.dump(roles, f)
        if os.path.exists(role_dir):
            shutil.rmtree(role_dir)
        return jsonify({"message": "Role deleted"})

@app.route('/api/generate-scenario-role/<name>', methods=['POST'])
def generate_scenario_role_cs(name):
    role_dir = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, name)
    data_path = os.path.join(role_dir, f"{name}.json")
    
    basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
    if not os.path.exists(data_path):
        return jsonify({"error": "Data not found"}), 404
    with open(data_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    data = json_data.get('data', [])
    branch_type = json_data.get('branchType', 'General')
    
    cs_data_path = os.path.join(role_dir, f"{name}RoleData.cs")
    with open(cs_data_path, 'w', encoding='utf-8') as f:
        f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
        f.write("namespace GameCore.Scenario \n{\n")
        f.write(f"   public class {name}RoleData : BaseScenarioRoleData \n    {{\n")
        read_codes = []
        for item in data:
            field_data = generate_csharp_field(item, enum_list, class_list, unity_types, basic_types,class_data_id_list)
            f.write(field_data['field'])
            read_codes.append(field_data['read'])
        f.write(f"\n        public {name}RoleData() : base() {{  RoleID = ScenarioRoleID.{name};  }}\n       public override void ReadBinary(BinaryReader reader)        {{\n")
        for read_code in read_codes:
            f.write(read_code)
        f.write("        }\n")
        f.write("    }\n}\n")
    
  
    base_action_class = "BaseScenarioRoleBranchAction" if branch_type == 'Branch' else "BaseScenarioRoleAction"
    # Generate Action class inheriting from BaseScenarioRoleAction
    cs_action_content = f"""
using Cysharp.Threading.Tasks;
using System;
using System.Threading;
using UnityEngine;

namespace GameCore.Scenario {{
    public class {name}RoleAction : {base_action_class}<{name}RoleData> {{
        public {name}RoleAction({name}RoleData roleData) : base(roleData) {{
        }}

        public override void OnInitialize(ScenarioExecuteData executeData, CancellationTokenSource ct) {{
            // Custom initialization logic
            base.OnInitialize(executeData,ct);
        }}
        
        public override void OnOneExecute(ScenarioExecuteData executeData, CancellationTokenSource ct) {{
        }}

        public override void OnExecute(ScenarioExecuteData executeData, CancellationTokenSource ct) {{
            // Custom action logic using RoleData
            Debug.Log($"Executing {name} with RoleID: {{RoleData.RoleID}}");
        }}

        public override void OnFinalize(ScenarioExecuteData executeData, CancellationTokenSource ct) {{
            // Custom cleanup logic
        }}
        
        public override async UniTask OnInitializeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {{

            await base.OnInitializeAsync(executeData, ct);
        }}
        public override async UniTask OnOneExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {{
            // Implement action logic here
            await UniTask.CompletedTask;
        }}
        public override async UniTask OnExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {{
            // Implement action logic here
            await UniTask.CompletedTask;
        }}
        public override async UniTask OnFinalizeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {{
            await UniTask.CompletedTask;
        }}
    }}
}}
"""
    
    # Write both files
    cs_action_path = os.path.join(role_dir, f"{name}RoleAction.cs")

    if not os.path.exists(cs_action_path):
        with open(cs_action_path, 'w', encoding='utf-8') as f:
            f.write(cs_action_content)
    
    return jsonify({"message": "C# data and action classes generated"})

#============================================================================
#ScenarioEvent管理
@app.route('/api/scenario-event', methods=['GET', 'POST'])
def handle_scenario_event_list():
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    if request.method == 'GET':
        if os.path.exists(list_path):
            with open(list_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        return jsonify([])
    elif request.method == 'POST':
        data = request.json
        id = data.get('id')
        name = data.get('name')
        description = data.get('description', '')
        if not id or not name:
            return jsonify({"error": "ID and Name are required"}), 400
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                events = json.load(f)
                if any(e['id'] == id for e in events):
                    return jsonify({"error": "ID already exists"}), 400
                new_event = {"id": id, "name": name, "description": description, "subEvents": []}
                events.append(new_event)
                f.seek(0)
                f.truncate()
                json.dump(events, f)
        else:
            new_event = {"id": id, "name": name, "description": description, "subEvents": []}
            with open(list_path, 'w', encoding='utf-8') as f:
                json.dump([new_event], f)
        event_dir = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id)
        os.makedirs(event_dir, exist_ok=True)
        with open(os.path.join(event_dir, f"{id}.json"), 'w', encoding='utf-8') as f:
            json.dump(new_event, f)
        return jsonify({"message": "Event created"})

@app.route('/api/scenario-event/<id>', methods=['PATCH', 'DELETE'])
def handle_scenario_event(id):
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    event_dir = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id)
    event_path = os.path.join(event_dir, f"{id}.json")
    if request.method == 'PATCH':
        data = request.json
        name = data.get('name')
        description = data.get('description')
        if not os.path.exists(list_path):
            return jsonify({"error": "Event not found"}), 404
        with open(list_path, 'r+', encoding='utf-8') as f:
            events = json.load(f)
            for event in events:
                if event['id'] == id:
                    if name is not None:
                        event['name'] = name
                    if description is not None:
                        event['description'] = description
                    f.seek(0)
                    f.truncate()
                    json.dump(events, f)
                    with open(event_path, 'w', encoding='utf-8') as ef:
                        json.dump(event, ef)
                    return jsonify({"message": "Event updated"})
        return jsonify({"error": "Event not found"}), 404
    elif request.method == 'DELETE':
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                events = json.load(f)
                events = [e for e in events if e['id'] != id]
                f.seek(0)
                f.truncate()
                json.dump(events, f)
        if os.path.exists(event_dir):
            shutil.rmtree(event_dir)
        return jsonify({"message": "Event deleted"})

@app.route('/api/scenario-event/<id>/sub', methods=['POST'])
def add_sub_event(id):
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"error": "Name is required"}), 400
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    event_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id, f"{id}.json")
    if os.path.exists(list_path):
        with open(list_path, 'r+', encoding='utf-8') as f:
            events = json.load(f)
            for event in events:
                if event['id'] == id:
                    max_sub_id = max([s['subId'] for s in event.get('subEvents', [])], default=0) + 1
                    new_sub = {"subId": max_sub_id, "name": name}
                    event['subEvents'].append(new_sub)
                    f.seek(0)
                    f.truncate()
                    json.dump(events, f)
                    with open(event_path, 'r+', encoding='utf-8') as ef:
                        eventData = json.load(ef)
                        for subEv in eventData["subEvents"]:
                            if subEv['name'] == name:
                                return jsonify({"message": "すでに存在しています", "subId": max_sub_id})
                        eventData["subEvents"].append(new_sub)
                        ef.seek(0)
                        ef.truncate()
                        json.dump(eventData, ef)
                    return jsonify({"message": "Sub event added", "subId": max_sub_id})
        return jsonify({"error": "Event not found"}), 404
    return jsonify({"error": "Event not found"}), 404

@app.route('/api/scenario-event/<id>/sub/<int:subId>', methods=['PATCH', 'DELETE'])
def handle_sub_event(id, subId):
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    event_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id, f"{id}.json")
    if request.method == 'PATCH':
        data = request.json
        name = data.get('name')
        if not os.path.exists(list_path):
            return jsonify({"error": "Event not found"}), 404
        with open(list_path, 'r+', encoding='utf-8') as f:
            events = json.load(f)
            for event in events:
                if event['id'] == id:
                    for sub in event['subEvents']:
                        if sub['subId'] == subId:
                            if name is not None:
                                sub['name'] = name
                            f.seek(0)
                            f.truncate()
                            json.dump(events, f)
                            with open(event_path, 'w', encoding='utf-8') as ef:
                                json.dump(event, ef)
                            return jsonify({"message": "Sub event updated"})
            return jsonify({"error": "Sub event not found"}), 404
    elif request.method == 'DELETE':
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                events = json.load(f)
                for event in events:
                    if event['id'] == id:
                        event['subEvents'] = [s for s in event['subEvents'] if s['subId'] != subId]
                        f.seek(0)
                        f.truncate()
                        json.dump(events, f)
                        with open(event_path, 'w', encoding='utf-8') as ef:
                            json.dump(event, ef)
                        return jsonify({"message": "Sub event deleted"})
        return jsonify({"error": "Event or sub event not found"}), 404
    
# Transition管理
# 既存のエンドポイント（省略された部分は前のコードと同じ）
@app.route('/api/scenario-event/<eventId>/sub/<subId>/transition', methods=['GET', 'POST'])
def handle_transition(eventId, subId):
    app.logger.debug(f"Received eventId: {eventId}, subId: {subId}")
    if not eventId or eventId == 'undefined' or not subId or subId == 'undefined':
        app.logger.error(f"Invalid parameters: eventId={eventId}, subId={subId}")
        return jsonify({'error': 'Invalid eventId or subId'}), 400
    file_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, eventId, f"{eventId}.json")
    if request.method == 'GET':
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return jsonify(data.get('subgroups', {}).get(subId, {'nodes': [], 'edges': []}))
            return jsonify({'nodes': [], 'edges': []})
        except Exception as e:
            app.logger.error(f"Error reading {file_path}: {str(e)}")
            return jsonify({'error': str(e)}), 500
    else:  # POST
        try:
            data = request.get_json()
            current_data = {}
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            current_data.setdefault('subgroups', {}).update({subId: data})
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            return jsonify({'message': 'Transition saved'})
        except Exception as e:
            app.logger.error(f"Error saving {file_path}: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/scenario-event/<eventId>/sub/<subId>/transition/<parentId>/subgroup', methods=['GET', 'POST'])
def handle_subgroup(eventId, subId, parentId):
    app.logger.debug(f"Subgroup request: eventId={eventId}, subId={subId}, parentId={parentId}")
    if not eventId or eventId == 'undefined' or not subId or subId == 'undefined' or not parentId:
        app.logger.error(f"Invalid parameters: eventId={eventId}, subId={subId}, parentId={parentId}")
        return jsonify({'error': 'Invalid parameters'}), 400
    file_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, eventId, f"{eventId}.json")
    if request.method == 'GET':
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                subgroups = data.get('subgroups', {}).get(subId, {}).get('nodes', [])
                for node in subgroups:
                    if node['id'] == parentId:
                        return jsonify(node['data'].get('subgroups', {}).get(parentId, {'nodes': [], 'edges': []}))
                return jsonify({'nodes': [], 'edges': []})
            return jsonify({'nodes': [], 'edges': []})
        except Exception as e:
            app.logger.error(f"Error reading {file_path}: {str(e)}")
            return jsonify({'error': str(e)}), 500
    else:  # POST
        try:
            data = request.get_json()
            current_data = {}
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            subgroups = current_data.get('subgroups', {}).get(subId, {}).get('nodes', [])
            updated_nodes = subgroups
            for node in updated_nodes:
                if node['id'] == parentId:
                    node['data']['subgroups'] = node['data'].get('subgroups', {})
                    node['data']['subgroups'][parentId] = data
            current_data.setdefault('subgroups', {}).setdefault(subId, {})['nodes'] = updated_nodes
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            return jsonify({'message': 'Subgroup saved'})
        except Exception as e:
            app.logger.error(f"Error saving {file_path}: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/scenario-event/<eventId>/sub/<int:subId>/transition/<nodeId>/role', methods=['POST'])
def add_role(eventId, subId, nodeId):
    try:
        data = request.get_json()
        file_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, eventId, f"{eventId}.json")
        current_data = {}
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
        subgroups = current_data.get('subgroups', {}).get(subId, {}).get('nodes', [])
        for node in subgroups:
            if node['id'] == nodeId:
                node['data']['roles'] = node['data'].get('roles', []) + [{
                    'id': data['roleId'],
                    'name': data['name'],
                    'branchType': data['branchType'],
                    'data': []
                }]
                break
            if node['data'].get('subgroups', {}).get(nodeId):
                node['data']['subgroups'][nodeId]['nodes'][0]['data']['roles'] = (
                    node['data']['subgroups'][nodeId]['nodes'][0]['data'].get('roles', []) + [{
                        'id': data['roleId'],
                        'name': data['name'],
                        'branchType': data['branchType'],
                        'data': []
                    }]
                )
                break
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
        return jsonify({'message': 'Role added'})
    except Exception as e:
        app.logger.error(f"Error adding role: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scenario-role', methods=['GET', 'POST'])
def handle_roles():
    roles_path = os.path.join(DATA_DIR, 'scenario_role.json')
    if request.method == 'GET':
        try:
            if os.path.exists(roles_path):
                with open(roles_path, 'r', encoding='utf-8') as f:
                    return jsonify(json.load(f))
            return jsonify([])
        except Exception as e:
            app.logger.error(f"Error reading roles {roles_path}: {str(e)}")
            return jsonify({"error": "Failed to read roles"}), 500
    elif request.method == 'POST':
        try:
            data = request.json
            role_id = data.get('id')
            name = data.get('name')
            description = data.get('description', '')
            actions = data.get('actions', [])
            if not role_id or not name:
                return jsonify({"error": "ID and name are required"}), 400
            roles = []
            if os.path.exists(roles_path):
                with open(roles_path, 'r', encoding='utf-8') as f:
                    roles = json.load(f)
            if any(r['id'] == role_id for r in roles):
                return jsonify({"error": "Role ID already exists"}), 400
            roles.append({"id": role_id, "name": name, "description": description, "actions": actions})
            with open(roles_path, 'w', encoding='utf-8') as f:
                json.dump(roles, f, ensure_ascii=False, indent=2)
            return jsonify({"message": "Role added", "data": roles})
        except Exception as e:
            app.logger.error(f"Error adding role to {roles_path}: {str(e)}")
            return jsonify({"error": "Failed to add role"}), 500

@app.route('/api/scenario-role/<roleId>', methods=['PATCH', 'DELETE'])
def handle_role(roleId):
    roles_path = os.path.join(DATA_DIR, 'scenario_role.json')
    try:
        if not os.path.exists(roles_path):
            return jsonify({"error": "No roles found"}), 404
        with open(roles_path, 'r', encoding='utf-8') as f:
            roles = json.load(f)
        if request.method == 'PATCH':
            data = request.json
            for role in roles:
                if role['id'] == roleId:
                    role.update({
                        "name": data.get('name', role['name']),
                        "description": data.get('description', role['description']),
                        "actions": data.get('actions', role['actions'])
                    })
                    with open(roles_path, 'w', encoding='utf-8') as f:
                        json.dump(roles, f, ensure_ascii=False, indent=2)
                    return jsonify({"message": "Role updated", "data": roles})
            return jsonify({"error": "Role not found"}), 404
        elif request.method == 'DELETE':
            roles = [role for role in roles if role['id'] != roleId]
            with open(roles_path, 'w', encoding='utf-8') as f:
                json.dump(roles, f, ensure_ascii=False, indent=2)
            return jsonify({"message": "Role deleted", "data": roles})
    except Exception as e:
        app.logger.error(f"Error handling role {roleId}: {str(e)}")
        return jsonify({"error": "Failed to handle role"}), 500
    
    
# API追加
@app.route('/api/role-form-schema/<roleName>', methods=['GET'])
def get_role_form_schema(roleName):
    try:
        schema = scenario.generate_role_form_schema(roleName,DATA_DIR)
        return jsonify(schema)
    except Exception as e:
        app.logger.error(f"Error fetching role schema: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scenario-role', methods=['GET'])
def get_roles():
    try:
        roles = []
        for file in os.listdir('data/scenario-role'):
            if file.endswith('.json'):
                with open(f'data/scenario-role/{file}', 'r', encoding='utf-8') as f:
                    role_data = json.load(f)
                    roles.append({
                        'id': file.replace('.json', ''),
                        'name': file.replace('.json', ''),
                        'description': role_data.get('description', ''),
                        'branchType': role_data.get('branchType', 'General')
                    })
        return jsonify(roles)
    except Exception as e:
        app.logger.error(f"Error fetching roles: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/save-role-data/<eventId>/<subId>/<nodeId>/<roleId>', methods=['POST'])
def save_role_data(eventId, subId, nodeId, roleId):
    try:
        data = request.get_json()
        formData = data.get('formData', {})
        file_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, eventId, f"{eventId}.json")
        current_data = {}
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
        subgroups = current_data.get('subgroups', {}).get(subId, {}).get('nodes', [])
        for node in subgroups:
            if node['id'] == nodeId:
                node['data']['roles'] = [
                    role if role['id'] != roleId else { **role, 'data': formData }
                    for role in node['data'].get('roles', [])
                ]
                break
            if node['data'].get('subgroups', {}).get(nodeId):
                node['data']['subgroups'][nodeId]['nodes'][0]['data']['roles'] = [
                    role if role['id'] != roleId else { **role, 'data': formData }
                    for role in node['data']['subgroups'][nodeId]['nodes'][0]['data'].get('roles', [])
                ]
                break
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
        return jsonify({'message': 'Role data saved'})
    except Exception as e:
        app.logger.error(f"Error saving role data: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
# エンドポイント
@app.route('/api/fix-all-events', methods=['POST'])
def fix_all_events_endpoint():
    try:
        scenario.fix_all_events()
        return jsonify({"message": "All events fixed successfully"})
    except Exception as e:
        logger.error(f"Error fixing all events: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-all-event-bin', methods=['POST'])
def generate_all_event_bin_endpoint():
    try:
        scenario.fix_all_events()  # 先に Fix
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
        result = scenario.generate_all_event_bin(basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error generating all event bin: {str(e)}")
        return jsonify({"error": str(e)}), 500
    

#===============================================================================
#Assets

# Texture
@app.route('/api/texture', methods=['GET'])
def get_texture():
    return jsonify(assets.get_texture_data())

@app.route('/api/texture/add_group', methods=['POST'])
def add_texture_group():
    data = request.json
    assets.add_texture_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/texture/delete_group', methods=['POST'])
def delete_texture_group():
    data = request.json
    assets.delete_texture_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/texture/add_texture', methods=['POST'])
def add_texture():
    data = request.json
    assets.add_texture(
        data['group_name'],
        data['name'],
        data['desc'],
        data['isSpriteRender']
    )
    return jsonify({'status': 'success'})

@app.route('/api/texture/delete_texture', methods=['POST'])
def delete_texture():
    data = request.json
    assets.delete_texture(data['group_name'], data['index'])
    return jsonify({'status': 'success'})

@app.route('/api/texture/generate', methods=['POST'])
def generate_texture_files():
    assets.generate_texture_csharp()
    assets.generate_texture_bin()
    return jsonify({'status': 'success'})

@app.route('/api/texture/serve/<group_name>/<int:index>')
def serve_texture(group_name, index):
    file_path = assets.get_texture_file_path(group_name, index)
    if file_path and os.path.exists(file_path):
        return send_file(file_path, mimetype='image/png')
    return jsonify({'error': 'File not found'}), 404

# GameObject
@app.route('/api/gameobject', methods=['GET'])
def get_gameobject():
    return jsonify(assets.get_gameobject_data())

@app.route('/api/gameobject/add_group', methods=['POST'])
def add_gameobject_group():
    data = request.json
    assets.add_gameobject_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/gameobject/delete_group', methods=['POST'])
def delete_gameobject_group():
    data = request.json
    assets.delete_gameobject_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/gameobject/add_gameobject', methods=['POST'])
def add_gameobject():
    data = request.json
    assets.add_gameobject(
        data['group_name'],
        data['name'],
        data['desc']
    )
    return jsonify({'status': 'success'})

@app.route('/api/gameobject/delete_gameobject', methods=['POST'])
def delete_gameobject():
    data = request.json
    assets.delete_gameobject(data['group_name'], data['index'])
    return jsonify({'status': 'success'})

@app.route('/api/gameobject/generate', methods=['POST'])
def generate_gameobject_files():
    assets.generate_gameobject_csharp()
    assets.generate_gameobject_bin()
    return jsonify({'status': 'success'})



#=================================================-----
# Sound

@app.route('/api/sound', methods=['GET'])
def get_sound():
    return jsonify(assets.get_sound_data())

@app.route('/api/sound/add_group', methods=['POST'])
def add_group():
    data = request.json
    assets.add_sound_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/sound/delete_group', methods=['POST'])
def delete_group():
    data = request.json
    assets.delete_sound_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/sound/add_sound', methods=['POST'])
def add_sound():
    data = request.json
    assets.add_sound(
        data['group_name'],
        data['name'],
        data['desc'],
        data['volume'],
        data['type']
    )
    return jsonify({'status': 'success'})

@app.route('/api/sound/delete_sound', methods=['POST'])
def delete_sound():
    data = request.json
    assets.delete_sound(data['group_name'], data['index'])
    return jsonify({'status': 'success'})

@app.route('/api/sound/generate', methods=['POST'])
def generate_files():
    assets.generate_sound_csharp()
    assets.generate_sound_bin()
    return jsonify({'status': 'success'})

@app.route('/api/open-code/<state_name>/<node_label>', methods=['GET'])
def open_code(state_name, node_label):
    cs_path = os.path.join(DATA_DIR, STATE_DATA, state_name, "States",f"{state_name}{node_label}State.cs")
    if not os.path.exists(cs_path):
        return jsonify({"error": "File not found"}), 404

    # Possible Visual Studio 2022 Community paths
    possible_vs_paths = [
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Professional\Common7\IDE\devenv.exe",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\Professional\Common7\IDE\devenv.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\devenv.exe",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\devenv.exe"
    ]

    vs_path = None
    for path in possible_vs_paths:
        if os.path.exists(path):
            vs_path = path
            break

    if not vs_path:
        return jsonify({"error": "Visual Studio 2022 not found on system"}), 404

    # Check if Visual Studio is running
    vs_running = False
    for proc in psutil.process_iter(['name']):
        if proc.info['name'].lower() == 'devenv.exe':
            vs_running = True
            break

    if not vs_running:
        return jsonify({"error": "Visual Studio 2022 is not currently running"}), 400

    try:
        subprocess.Popen([vs_path, "/edit", cs_path], shell=True)
        return jsonify({"message": "Opened in Visual Studio"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# Sound serve endpoint for playback
@app.route('/api/sound/serve/<group_name>/<int:index>')
def serve_sound(group_name, index):
    file_path = assets.get_sound_file_path(group_name, index)
    if file_path and os.path.exists(file_path):
        return send_file(file_path, mimetype='audio/mpeg')
    return jsonify({'error': 'File not found'}), 404

# =================================================
# Behavior Tree API (追加部分)



@app.route('/api/behavior-data', methods=['GET'])
def get_behavior_data():
    return pythonSrc.behavior.get_behavior_data()

@app.route('/api/behavior-data', methods=['POST'])
def add_behavior():
    return pythonSrc.behavior.add_behavior(request)


@app.route('/api/behavior-data/<name>', methods=['DELETE'])
def delete_behavior(name):
    return pythonSrc.behavior.delete_behavior()

@app.route('/api/behavior-data/<name>', methods=['GET'])
def get_behavior_detail(name):
    return pythonSrc.behavior.get_behavior_detail(name)

@app.route('/api/behavior-data/<name>', methods=['PUT'])
def save_behavior_detail(name):
    return pythonSrc.behavior.save_behavior_detail(name,request)

@app.route('/api/behavior-generate/<name>', methods=['POST'])
def generate_behavior_code(name):
    basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
    return pythonSrc.behavior.generate_behavior_code(name,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)

#======================================================--
#animator
# ========================================
# 1. 全データ取得（Grid表示用）
# ========================================
@app.route('/api/animator-data', methods=['GET'])
def api_animator_data():
    registered = pythonSrc.animation.load_index()               # ["Player", "Enemy", ...]
    rows = []
    id_counter = 0

    for name in registered:
        try:
            meta = pythonSrc.animation.load_individual(name)
            group = meta.get("group", "Default")
            desc  = meta.get("desc", "")
            path  = meta.get("absolute_path", "")
            ctrl  = os.path.basename(path) if path else ""
        except Exception:
            group = desc = path = ctrl = ""

        id_counter += 1
        rows.append({
            "id": id_counter,
            "name": name,
            "group": group,
            "desc": desc,
            "path": path,
            "controller": ctrl
        })

    return jsonify(rows)

# ========================================
# 2. 新規作成（Gridの「作成」ボタン）
# ========================================
@app.route('/api/animator-create', methods=['POST'])
def api_animator_create():
    try:
        payload = request.get_json(silent=True) or {}
        group = payload.get('group', 'Default').strip()
        name  = payload.get('name', '').strip()

        if not name:
            return jsonify({"error": "名前は必須です"}), 400
        if ':' in name:
            return jsonify({"error": ": は使用できません"}), 400

        # 重複チェック（indexにあればNG）
        if name in pythonSrc.animation.load_index():
            return jsonify({"error": f"{name} は既に存在します"}), 400

        # assets.py の関数呼び出し（内部で個別保存＋index登録）
        pythonSrc.animation.add_animator(group, name, "Created via Grid")
        return jsonify({"message": f"{name} 作成＆自動生成完了！"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========================================
# 3. 削除（Gridの削除ボタン → PATCH）
# ========================================
@app.route('/api/animator-data', methods=['PATCH'])
def api_animator_delete():
    try:
        payload = request.get_json(silent=True) or {}
        target_name = payload.get('name')
        if not target_name:
            return jsonify({"error": "name 必須"}), 400

        index = pythonSrc.animation.load_index()
        if target_name not in index:
            return jsonify({"error": f"{target_name} が見つかりません"}), 404

        # 1. 個別フォルダごと削除
        individual_dir = os.path.dirname(pythonSrc.animation.get_individual_path(target_name))
        if os.path.exists(individual_dir):
            import shutil
            shutil.rmtree(individual_dir)

        # 2. 生成済み.cs削除（従来通り）
        cs_path = os.path.join(pythonSrc.animation.ANIM_DATA, f"{target_name}", 
                               f"{target_name}AnimationManager.g.cs")
        if os.path.exists(cs_path):
            os.remove(cs_path)

        # 3. indexから除去
        index.remove(target_name)
        pythonSrc.animation.save_index(index)

        return jsonify({"message": f"{target_name} 削除完了"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========================================
# 4. 全自動生成（Gridの「全Animator自動生成」ボタン）
# ========================================
@app.route('/api/generate-all-animator', methods=['POST'])
def api_generate_all_animator():
    try:
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
        pythonSrc.animation.generate_all_animator_csharp(basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)
        return jsonify({"message": "全Animator自動生成完了！\nUnityでリフレッシュしてね"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # /api/animator-data/{name} (GET) - 個別取得
@app.route('/api/animator-data/<name>', methods=['GET'])
def api_get_animator_detail(name):
    try:
        data = pythonSrc.animation.load_individual(name)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

# /api/animator-data/{name} (POST) - 保存
@app.route('/api/animator-data/<name>', methods=['POST'])
def api_save_animator_detail(name):
    try:
        payload = request.get_json()
        pythonSrc.animation.save_individual(name, payload)
        return jsonify({"message": f"{name} 保存完了"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# /api/generate-animator/{name} (POST) - 個別生成
@app.route('/api/generate-animator/<name>', methods=['POST'])
def api_generate_single_animator(name):
    try:
        ctrl = pythonSrc.animation.load_individual(name)
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
        pythonSrc.animation.generate_single_animator_csharp(ctrl,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)  # ← 新規関数
        return jsonify({"message": f"{name}AnimationManager.g.cs 生成完了！"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#==================================================================
# Scene
#==================================================================

@app.route('/api/scene/get', methods=['GET'])
def get_scenes():
    data = scene.load_scene_data()
    return jsonify(data)

@app.route('/api/scene/add', methods=['POST'])
def add_scene():
    data = request.json
    enum_name = data.get('enum_name')
    scene_type = data.get('scene_type') # Added scene_type
    result = scene.add_scene(enum_name, scene_type)
    return jsonify(result)

@app.route('/api/scene/delete', methods=['POST'])
def delete_scene():
    data = request.json
    enum_name = data.get('enum_name')
    result = scene.delete_scene(enum_name)
    return jsonify(result)

@app.route('/api/scene/generate', methods=['POST'])
def generate_scene_code():
    result = scene.generate_cs_files() # Changed function name
    return jsonify(result)

# --- SaveData (SystemData/PlayerData) Management ---

@app.route('/api/save-data/<name>', methods=['GET', 'POST'])
def manage_save_data_schema(name):
    if name not in ['SystemData', 'PlayerData']:
        return jsonify({"error": "Invalid save data type"}), 400

    file_path = os.path.join(SAVE_DATA_CUSTOM_DIR, f"{name}.json")

    if request.method == 'GET':
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return jsonify(data)
            except Exception as e:
                logger.error(f"Error reading {name} schema: {e}")
                return jsonify([]), 500 # Return empty list if error or file empty
        else:
            return jsonify([]) # Return empty list if file doesn't exist

    elif request.method == 'POST':
        try:
            data = request.get_json()
            # Ensure directory exists
            if not os.path.exists(SAVE_DATA_CUSTOM_DIR):
                os.makedirs(SAVE_DATA_CUSTOM_DIR)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return jsonify({"message": f"{name} schema saved successfully"})
        except Exception as e:
            logger.error(f"Error saving {name} schema: {e}")
            return jsonify({"error": str(e)}), 500

@app.route('/api/generate-save-data/<name>', methods=['POST'])
def generate_save_data_cs(name):
    if name not in ['SystemData', 'PlayerData']:
        return jsonify({"error": "Invalid save data type"}), 400

    # Get data from request or file
    data = request.get_json()
    if not data:
        file_path = os.path.join(SAVE_DATA_CUSTOM_DIR, f"{name}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []

    try:
        # Generate C# Code
        field_declarations = ""
        for item in data:
            type_name = item.get('type', 'int')
            var_name = item.get('name', 'Variable')
            array_size = item.get('arraySize', 0)
            description = item.get('description', '')

            # Basic comment
            if description:
                field_declarations += f"        /// <summary>\n        /// {description}\n        /// </summary>\n"
            
            # Field definition
            if array_size > 0:
                 field_declarations += f"        public {type_name}[] {var_name} = new {type_name}[{array_size}];\n"
            else:
                 # Initialize string to empty to avoid null issues if desired, or default
                 if type_name == 'string':
                     field_declarations += f"        public string {var_name} = \"\";\n"
                 else:
                     field_declarations += f"        public {type_name} {var_name};\n"

        code_str = f"""using System;
using UnityEngine;
using System.Collections.Generic;
using GameCore.Enums;
using GameCore.Tables;

namespace GameCore.SaveSystem
{{
    [Serializable]
    public class Base{name}
    {{
{field_declarations}
    }}
}}
"""
        cs_path = os.path.join(SAVE_DATA_CUSTOM_DIR, f"Base{name}.cs")
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(code_str)
        
        return jsonify({"message": f"{name}.cs generated successfully"})
    except Exception as e:
        logger.error(f"Error generating {name}.cs: {e}")
        return jsonify({"error": str(e)}), 500
    #if request.method == 'PATCH':
    #    try:
    #        delete_name = request.get_json()['name']
    #        with open(file_path, 'r', encoding='utf-8') as f:
    #            data = json.load(f)
    #        data = [item for item in data if item['name'] != delete_name]
    #        with open(file_path, 'w', encoding='utf-8') as f:
    #            json.dump(data, f, ensure_ascii=False, indent=2)
    #        logger.info(f"Removed enum: {delete_name}")
    #        return jsonify({"message": f"Enum {delete_name} removed from enum_list.json"})
    #    except FileNotFoundError:
    #        return jsonify({"error": "enum_list.json not found"}), 404
    #    except Exception as e:
    #        logger.error(f"Error removing enum-id: {str(e)}")
    #        return jsonify({"error": str(e)}), 500
# 静的ファイルのルーティング
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static(path):
    logger.debug(f"Serving static file: {path}")
    if path != '' and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

def _validate_const_value(type_str, value):
    """サーバー側でも型に応じた値のバリデーションを行う"""
    if type_str in ('int', 'uint'):
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return False
        if type_str == 'uint' and iv < 0:
            return False
        return True
    if type_str == 'float':
        try:
            float(value)
        except (TypeError, ValueError):
            return False
        return True
    if type_str == 'string':
        return isinstance(value, str)
    if type_str in ('vector2', 'vector3'):
        expected_len = 2 if type_str == 'vector2' else 3
        if not isinstance(value, (list, tuple)) or len(value) != expected_len:
            return False
        for v in value:
            try:
                float(v)
            except (TypeError, ValueError):
                return False
        return True
    return False
 
 
def _format_cs_literal(type_str, value):
    """C#のリテラル表現に変換"""
    if type_str == 'int':
        return str(int(value))
    if type_str == 'uint':
        return f"{int(value)}u"
    if type_str == 'float':
        return f"{float(value)}f"
    if type_str == 'string':
        escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
        return f"\"{escaped}\""
    if type_str == 'vector2':
        x, y = value
        return f"new Vector2({float(x)}f, {float(y)}f)"
    if type_str == 'vector3':
        x, y, z = value
        return f"new Vector3({float(x)}f, {float(y)}f, {float(z)}f)"
    return "null"
 
 
# ------------------------------------------------------------
# 2) ConstClassData 一覧管理（GET / POST / PATCH）
#    ClassDataIdGrid の /api/class-data-id と同じパターン
# ------------------------------------------------------------
@app.route('/api/const-class-data', methods=['GET', 'POST', 'PATCH'])
def manage_const_class_data():
    const_class_dir = os.path.join(DATA_DIR, CONST_CLASS_DATA)
    os.makedirs(const_class_dir, exist_ok=True)
    file_path = os.path.join(const_class_dir, 'const_class_data_list.json')
 
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data), 200
        except FileNotFoundError:
            return jsonify([]), 200
        except json.JSONDecodeError:
            logger.error("const_class_data_list.jsonの形式が不正です")
            return jsonify({"error": "const_class_data_list.jsonの形式が不正です"}), 500
        except Exception as e:
            logger.error(f"ConstClassDataリストの読み込みエラー: {str(e)}")
            return jsonify({"error": f"データ読み込みエラー: {str(e)}"}), 500
 
    elif request.method == 'POST':
        try:
            new_item = request.get_json()
            if not new_item or not new_item.get('name'):
                return jsonify({"error": "名前は必須です"}), 400
            name = new_item['name']
            if ':' in name:
                return jsonify({"error": "名前に':'を含めることはできません"}), 400
 
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
 
            if any(item['name'] == name for item in data):
                return jsonify({"error": f"ConstClass {name} はすでに存在します"}), 400
 
            max_id = max([item['id'] for item in data], default=0) + 1
            new_entry = {"id": max_id, "name": name}
            data.append(new_entry)
 
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
 
            # 定数データ用の空ファイルを作成
            data_file_path = os.path.join(const_class_dir, name, f"{name}.json")
            os.makedirs(os.path.dirname(data_file_path), exist_ok=True)
            with open(data_file_path, 'w', encoding='utf-8') as f:
                json.dump({"constants": []}, f, ensure_ascii=False, indent=2)
 
            logger.info(f"ConstClassDataを作成しました: {name}")
            return jsonify({"message": f"ConstClass {name} を正常に作成しました", "data": new_entry}), 201
 
        except Exception as e:
            logger.error(f"ConstClassData作成エラー: {str(e)}")
            return jsonify({"error": f"作成エラー: {str(e)}"}), 500
 
    elif request.method == 'PATCH':
        try:
            delete_name = request.get_json().get('name')
            if not delete_name:
                return jsonify({"error": "削除する名前を指定してください"}), 400
 
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
 
            if not any(item['name'] == delete_name for item in data):
                return jsonify({"error": f"ConstClass {delete_name} が見つかりません"}), 404
 
            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
 
            data_dir = os.path.join(const_class_dir, delete_name)
            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)
 
            logger.info(f"ConstClassDataを削除しました: {delete_name}")
            return jsonify({"message": f"ConstClass {delete_name} を正常に削除しました"}), 200
 
        except FileNotFoundError:
            return jsonify({"error": "const_class_data_list.jsonが見つかりません"}), 404
        except Exception as e:
            logger.error(f"ConstClassData削除エラー: {str(e)}")
            return jsonify({"error": f"削除エラー: {str(e)}"}), 500
 
 
# ------------------------------------------------------------
# 3) ConstClassData 詳細（定数リストの取得・保存・削除）
# ------------------------------------------------------------
@app.route('/api/const-class-data/<name>', methods=['GET', 'POST', 'DELETE'])
def const_class_data_detail(name):
    file_path = os.path.join(DATA_DIR, CONST_CLASS_DATA, name, f"{name}.json")
 
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data), 200
        except FileNotFoundError:
            return jsonify({"constants": []}), 200
        except Exception as e:
            logger.error(f"ConstClassData詳細読み込みエラー {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
    elif request.method == 'POST':
        try:
            body = request.get_json()
            constants = body.get('constants', [])
 
            # サーバー側バリデーション
            seen_names = set()
            for c in constants:
                if c.get('type') not in CONST_TYPE_MAP:
                    return jsonify({"error": f"不正な型です: {c.get('type')}"}), 400
                if not c.get('name') or not re.match(r'^[A-Za-z0-9_]+$', c['name']):
                    return jsonify({"error": f"不正な定数名です: {c.get('name')}"}), 400
                if c['name'] in seen_names:
                    return jsonify({"error": f"定数名が重複しています: {c['name']}"}), 400
                seen_names.add(c['name'])
                if not _validate_const_value(c['type'], c.get('value')):
                    return jsonify({"error": f"値が不正です（{c['name']}）: 数値のみ入力してください"}), 400
 
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({"constants": constants}, f, ensure_ascii=False, indent=2)
 
            logger.info(f"ConstClassDataを保存しました: {name}")
            return jsonify({"message": f"{name} の定数データを保存しました"}), 200
 
        except Exception as e:
            logger.error(f"ConstClassData保存エラー {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
    elif request.method == 'DELETE':
        try:
            os.remove(file_path)
            return jsonify({"message": f"{name}.json deleted"}), 200
        except FileNotFoundError:
            return jsonify({"error": "File not found"}), 404
        except Exception as e:
            logger.error(f"ConstClassData削除エラー {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
 
# ------------------------------------------------------------
# 4) C# static class 生成
# ------------------------------------------------------------
def _write_const_class_cs(name, constants):
    class_dir = os.path.join(DATA_DIR, CONST_CLASS_DATA, name)
    os.makedirs(class_dir, exist_ok=True)
    cs_path = os.path.join(class_dir, f"{name}ConstData.cs")
 
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write("using UnityEngine;\n\n")
        f.write("namespace GameCore.Consts\n{\n")
        f.write(f"    public static class {name}ConstData\n    {{\n")
        for c in constants:
            type_str = c['type']
            info = CONST_TYPE_MAP[type_str]
            literal = _format_cs_literal(type_str, c['value'])
            if info['is_const']:
                f.write(f"        // {c['comment']}\n")
                f.write(f"        public const {info['cs_type']} {c['name']} = {literal};\n")
            else:
                # Vector2 / Vector3 は const 不可のため static readonly
                f.write(f"        public static readonly {info['cs_type']} {c['name']} = {literal};\n")
        f.write("    }\n}\n")
    return cs_path
 
 
@app.route('/api/generate-const-class/<name>', methods=['POST'])
def generate_const_class_cs(name):
    try:
        body = request.get_json() or {}
        constants = body.get('constants')
 
        # bodyに定数が渡されなかった場合は保存済みデータを使用
        if constants is None:
            file_path = os.path.join(DATA_DIR, CONST_CLASS_DATA, name, f"{name}.json")
            with open(file_path, 'r', encoding='utf-8') as f:
                constants = json.load(f).get('constants', [])
 
        for c in constants:
            if c.get('type') not in CONST_TYPE_MAP:
                return jsonify({"error": f"不正な型です: {c.get('type')}"}), 400
            if not _validate_const_value(c['type'], c.get('value')):
                return jsonify({"error": f"値が不正です（{c.get('name')}）"}), 400
 
        cs_path = _write_const_class_cs(name, constants)
        logger.info(f"ConstClass C#を生成しました: {cs_path}")
        return jsonify({"message": f"C#ファイルを生成しました: {cs_path}"}), 200
 
    except Exception as e:
        logger.error(f"ConstClass生成エラー {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500
 
 
@app.route('/api/generate-all-const-class', methods=['POST'])
def generate_all_const_class():
    try:
        list_path = os.path.join(DATA_DIR, CONST_CLASS_DATA, 'const_class_data_list.json')
        if not os.path.exists(list_path):
            return jsonify({"message": "ConstClassDataがありません"}), 200
        with open(list_path, 'r', encoding='utf-8') as f:
            class_list = json.load(f)
 
        generated = []
        for item in class_list:
            name = item['name']
            data_path = os.path.join(DATA_DIR, CONST_CLASS_DATA, name, f"{name}.json")
            if not os.path.exists(data_path):
                continue
            with open(data_path, 'r', encoding='utf-8') as f:
                constants = json.load(f).get('constants', [])
            _write_const_class_cs(name, constants)
            generated.append(name)
 
        return jsonify({"message": f"{len(generated)}件の静的クラスを生成しました: {', '.join(generated)}"}), 200
    except Exception as e:
        logger.error(f"全ConstClass生成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500
 
 
# ============================================================
# ClassDataID タグ機能
# ============================================================
#
# タグは class_data_id ディレクトリ配下に tags.json として保存する:
#   [{"id": 1, "name": "戦闘"}, {"id": 2, "name": "UI"}, ...]
#
# 各 ClassDataID エントリ（class_data_id_list.json の各要素）には
# "tag" フィールド（タグ名。未設定は null）を追加する。
# ------------------------------------------------------------
 
@app.route('/api/class-data-id-tags', methods=['GET', 'POST', 'PATCH'])
def manage_class_data_id_tags():
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_ID)
    os.makedirs(tags_dir, exist_ok=True)
    file_path = os.path.join(tags_dir, 'tags.json')
 
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data), 200
        except FileNotFoundError:
            return jsonify([]), 200
        except Exception as e:
            logger.error(f"タグリスト読み込みエラー: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
    elif request.method == 'POST':
        try:
            new_tag = request.get_json()
            if not new_tag or not new_tag.get('name'):
                return jsonify({"error": "タグ名は必須です"}), 400
            name = new_tag['name']
 
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
 
            if any(t['name'] == name for t in data):
                return jsonify({"error": f"タグ {name} はすでに存在します"}), 400
 
            max_id = max([t['id'] for t in data], default=0) + 1
            new_entry = {"id": max_id, "name": name}
            data.append(new_entry)
 
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
 
            return jsonify({"message": f"タグ {name} を作成しました", "data": new_entry}), 201
        except Exception as e:
            logger.error(f"タグ作成エラー: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
    elif request.method == 'PATCH':
        # タグ削除。割り当て済みのClassDataIDエントリからも解除する
        try:
            delete_name = request.get_json().get('name')
            if not delete_name:
                return jsonify({"error": "削除するタグ名を指定してください"}), 400
 
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not any(t['name'] == delete_name for t in data):
                return jsonify({"error": f"タグ {delete_name} が見つかりません"}), 404
            data = [t for t in data if t['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
 
            # class_data_id_list.json 側の tag も解除
            list_path = os.path.join(tags_dir, 'class_data_id_list.json')
            if os.path.exists(list_path):
                with open(list_path, 'r', encoding='utf-8') as f:
                    list_data = json.load(f)
                changed = False
                for item in list_data:
                    if item.get('tag') == delete_name:
                        item['tag'] = None
                        changed = True
                if changed:
                    with open(list_path, 'w', encoding='utf-8') as f:
                        json.dump(list_data, f, ensure_ascii=False, indent=2)
 
            return jsonify({"message": f"タグ {delete_name} を削除しました"}), 200
        except FileNotFoundError:
            return jsonify({"error": "tags.jsonが見つかりません"}), 404
        except Exception as e:
            logger.error(f"タグ削除エラー: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
 
@app.route('/api/class-data-id-tags/<int:tag_id>', methods=['PUT'])
def rename_class_data_id_tag(tag_id):
    """タグ名の変更（割り当て済みClassDataIDの tag フィールドも追従して更新）"""
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_ID)
    file_path = os.path.join(tags_dir, 'tags.json')
    try:
        new_name = request.get_json().get('name')
        if not new_name:
            return jsonify({"error": "新しいタグ名を指定してください"}), 400
 
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
 
        target = next((t for t in data if t['id'] == tag_id), None)
        if not target:
            return jsonify({"error": "指定されたタグが見つかりません"}), 404
        if any(t['name'] == new_name and t['id'] != tag_id for t in data):
            return jsonify({"error": f"タグ {new_name} はすでに存在します"}), 400
 
        old_name = target['name']
        target['name'] = new_name
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
 
        # class_data_id_list.json 側の tag 名も追従
        list_path = os.path.join(tags_dir, 'class_data_id_list.json')
        if os.path.exists(list_path):
            with open(list_path, 'r', encoding='utf-8') as f:
                list_data = json.load(f)
            changed = False
            for item in list_data:
                if item.get('tag') == old_name:
                    item['tag'] = new_name
                    changed = True
            if changed:
                with open(list_path, 'w', encoding='utf-8') as f:
                    json.dump(list_data, f, ensure_ascii=False, indent=2)
 
        return jsonify({"message": f"タグ名を {old_name} から {new_name} に変更しました"}), 200
    except FileNotFoundError:
        return jsonify({"error": "tags.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"タグ名変更エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500
 
 
@app.route('/api/class-data-id/<name>/tag', methods=['PUT'])
def set_class_data_id_tag(name):
    """特定のClassDataIDエントリにタグを割り当てる（tag=nullで未設定に戻す）"""
    list_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')
    try:
        tag = request.get_json().get('tag')  # None も許容（未設定に戻す）
 
        with open(list_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
 
        target = next((item for item in data if item['name'] == name), None)
        if not target:
            return jsonify({"error": f"ClassDataID {name} が見つかりません"}), 404
 
        # タグが指定されている場合は存在確認
        if tag is not None:
            tags_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'tags.json')
            if os.path.exists(tags_path):
                with open(tags_path, 'r', encoding='utf-8') as f:
                    tag_list = json.load(f)
                if not any(t['name'] == tag for t in tag_list):
                    return jsonify({"error": f"タグ {tag} が見つかりません"}), 404
 
        target['tag'] = tag
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
 
        return jsonify({"message": f"{name} にタグを設定しました", "data": target}), 200
    except FileNotFoundError:
        return jsonify({"error": "class_data_id_list.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"タグ割り当てエラー {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
def generate_tags_load_script():
    """tags.json をロードしてタグ名を列挙するC#スクリプトを生成"""
    tags_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'tags.json')
    try:
        tags = []
        with open(tags_path, 'r', encoding='utf-8') as f:
            tags = json.load(f)
            
        class_data_id_list = []
        with open(os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json'), 'r', encoding='utf-8') as f:
            class_data_id_list = json.load(f)
            
        dict_tags_load_write_script = {}
        
        for tag in tags:
            tag_name = tag["name"]
            tagged_items = [
                item["name"] for item in class_data_id_list
                if item.get("tag") == tag_name
            ]
        
            lines = []
            indent = 0
        
            def add(text=""):
                lines.append("    " * indent + text)
        
            # -------------------------
            # 非同期
            # -------------------------
            add(f"public static async UniTask LoadAsync{tag_name}(Action action = null)")
            add("{")
            indent += 1
        
            add("await ClassDataIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
            add("{")
            indent += 1
        
            for item_name in tagged_items:
                add(f"header.GetData<GameCore.Tables.{item_name}Table>(GameCore.Enums.TableID.{item_name}, reader);")
                add("await UniTask.Yield();")
        
            add("action?.Invoke();")
            add("await UniTask.CompletedTask;")
            indent -= 1
            add("});")
        
            indent -= 1
            add("}")
            add()
        
            # -------------------------
            # 同期
            # -------------------------
            add(f"public static void Load{tag_name}(Action action = null)")
            add("{")
            indent += 1
        
            add("UniTask.Action(async () =>")
            add("{")
            indent += 1
        
            add("await ClassDataIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
            add("{")
            indent += 1
        
            for item_name in tagged_items:
                add(f"header.GetData<GameCore.Tables.{item_name}Table>(GameCore.Enums.TableID.{item_name}, reader);")
        
            add("action?.Invoke();")
            add("await UniTask.CompletedTask;")
            indent -= 1
            add("});")
        
            indent -= 1
            add("}).Invoke();")
        
            indent -= 1
            add("}")
            add()
        
            dict_tags_load_write_script[tag_name] = lines
        
        append_str = "\n".join(
            "\n".join(lines)
            for lines in dict_tags_load_write_script.values()
        )
        
        code_str =f"""
using System;
using Cysharp.Threading.Tasks;
using System.Collections.Generic;
        
namespace GameCore.Enums
{{
    public static class TableIdUtils
    {{
{textwrap.indent(append_str, '        ')}
    }}
}}
"""
    
        #ファイル書き込み
        cs_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'TableIdUtils.cs')
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(code_str)
    
        
            
        
        
    except FileNotFoundError:
        return jsonify({"error": "tags.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"タグロードスクリプト生成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500
 
        target = next((item for item in data if item['name'] == name), None)
        if not target:
            return jsonify({"error": f"ClassDataID {name} が見つかりません"}), 404
    except FileNotFoundError:
        return jsonify({"error": "class_data_id_list.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"タグ割り当てエラー : {str(e)}")
        return jsonify({"error": str(e)}), 500



# ============================================================
# ClassDataMatrixID タグ機能（ClassDataIDのタグ機能と同等）
# ============================================================
#
# タグは class_data_matrix_id ディレクトリ配下に tags.json として保存する:
#   [{"id": 1, "name": "戦闘"}, {"id": 2, "name": "UI"}, ...]
#
# 各 ClassDataMatrixID エントリ（class_data_matrix_id_list.json の各要素）には
# "tag" フィールド（タグ名。未設定は null）を追加する。
# ------------------------------------------------------------

@app.route('/api/class-data-matrix-id-tags', methods=['GET', 'POST', 'PATCH'])
def manage_class_data_matrix_id_tags():
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID)
    os.makedirs(tags_dir, exist_ok=True)
    file_path = os.path.join(tags_dir, 'tags.json')

    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data), 200
        except FileNotFoundError:
            return jsonify([]), 200
        except Exception as e:
            logger.error(f"Matrixタグリスト読み込みエラー: {str(e)}")
            return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        try:
            new_tag = request.get_json()
            if not new_tag or not new_tag.get('name'):
                return jsonify({"error": "タグ名は必須です"}), 400
            name = new_tag['name']

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []

            if any(t['name'] == name for t in data):
                return jsonify({"error": f"タグ {name} はすでに存在します"}), 400

            max_id = max([t['id'] for t in data], default=0) + 1
            new_entry = {"id": max_id, "name": name}
            data.append(new_entry)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return jsonify({"message": f"タグ {name} を作成しました", "data": new_entry}), 201
        except Exception as e:
            logger.error(f"Matrixタグ作成エラー: {str(e)}")
            return jsonify({"error": str(e)}), 500

    elif request.method == 'PATCH':
        # タグ削除。割り当て済みのClassDataMatrixIDエントリからも解除する
        try:
            delete_name = request.get_json().get('name')
            if not delete_name:
                return jsonify({"error": "削除するタグ名を指定してください"}), 400

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not any(t['name'] == delete_name for t in data):
                return jsonify({"error": f"タグ {delete_name} が見つかりません"}), 404
            data = [t for t in data if t['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # class_data_matrix_id_list.json 側の tag も解除
            list_path = os.path.join(tags_dir, 'class_data_matrix_id_list.json')
            if os.path.exists(list_path):
                with open(list_path, 'r', encoding='utf-8') as f:
                    list_data = json.load(f)
                changed = False
                for item in list_data:
                    if item.get('tag') == delete_name:
                        item['tag'] = None
                        changed = True
                if changed:
                    with open(list_path, 'w', encoding='utf-8') as f:
                        json.dump(list_data, f, ensure_ascii=False, indent=2)

            return jsonify({"message": f"タグ {delete_name} を削除しました"}), 200
        except FileNotFoundError:
            return jsonify({"error": "tags.jsonが見つかりません"}), 404
        except Exception as e:
            logger.error(f"Matrixタグ削除エラー: {str(e)}")
            return jsonify({"error": str(e)}), 500


@app.route('/api/class-data-matrix-id-tags/<int:tag_id>', methods=['PUT'])
def rename_class_data_matrix_id_tag(tag_id):
    """タグ名の変更（割り当て済みClassDataMatrixIDの tag フィールドも追従して更新）"""
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID)
    file_path = os.path.join(tags_dir, 'tags.json')
    try:
        new_name = request.get_json().get('name')
        if not new_name:
            return jsonify({"error": "新しいタグ名を指定してください"}), 400

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        target = next((t for t in data if t['id'] == tag_id), None)
        if not target:
            return jsonify({"error": "指定されたタグが見つかりません"}), 404
        if any(t['name'] == new_name and t['id'] != tag_id for t in data):
            return jsonify({"error": f"タグ {new_name} はすでに存在します"}), 400

        old_name = target['name']
        target['name'] = new_name
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # class_data_matrix_id_list.json 側の tag 名も追従
        list_path = os.path.join(tags_dir, 'class_data_matrix_id_list.json')
        if os.path.exists(list_path):
            with open(list_path, 'r', encoding='utf-8') as f:
                list_data = json.load(f)
            changed = False
            for item in list_data:
                if item.get('tag') == old_name:
                    item['tag'] = new_name
                    changed = True
            if changed:
                with open(list_path, 'w', encoding='utf-8') as f:
                    json.dump(list_data, f, ensure_ascii=False, indent=2)

        return jsonify({"message": f"タグ名を {old_name} から {new_name} に変更しました"}), 200
    except FileNotFoundError:
        return jsonify({"error": "tags.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"Matrixタグ名変更エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/class-data-matrix-id/<name>/tag', methods=['PUT'])
def set_class_data_matrix_id_tag(name):
    """特定のClassDataMatrixIDエントリにタグを割り当てる（tag=nullで未設定に戻す）"""
    list_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json')
    try:
        tag = request.get_json().get('tag')  # None も許容（未設定に戻す）

        with open(list_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        target = next((item for item in data if item['name'] == name), None)
        if not target:
            return jsonify({"error": f"ClassDataMatrixID {name} が見つかりません"}), 404

        # タグが指定されている場合は存在確認
        if tag is not None:
            tags_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'tags.json')
            if os.path.exists(tags_path):
                with open(tags_path, 'r', encoding='utf-8') as f:
                    tag_list = json.load(f)
                if not any(t['name'] == tag for t in tag_list):
                    return jsonify({"error": f"タグ {tag} が見つかりません"}), 404

        target['tag'] = tag
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return jsonify({"message": f"{name} にタグを設定しました", "data": target}), 200
    except FileNotFoundError:
        return jsonify({"error": "class_data_matrix_id_list.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"Matrixタグ割り当てエラー {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500


def generate_matrix_tags_load_script():
    """tags.json をロードしてタグ名ごとにMatrixをロードするC#スクリプトを生成（ClassDataIDのTableIdUtilsと同等）"""
    tags_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'tags.json')
    try:
        tags = []
        if os.path.exists(tags_path):
            with open(tags_path, 'r', encoding='utf-8') as f:
                tags = json.load(f)
        else:
            tags = []

        matrix_list = []
        list_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json')
        if os.path.exists(list_path):
            with open(list_path, 'r', encoding='utf-8') as f:
                matrix_list = json.load(f)

        dict_tags_load_write_script = {}

        for tag in tags:
            tag_name = tag["name"]
            tagged_items = [
                item["name"] for item in matrix_list
                if item.get("tag") == tag_name
            ]

            lines = []
            indent = 0

            def add(text=""):
                lines.append("    " * indent + text)

            # -------------------------
            # 非同期
            # -------------------------
            add(f"public static async UniTask LoadAsync{tag_name}(Action action = null)")
            add("{")
            indent += 1

            add("await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
            add("{")
            indent += 1

            for item_name in tagged_items:
                add(f"header.GetData<GameCore.Tables.{item_name}MatrixTable>(GameCore.Tables.MatrixTableID.{item_name}, reader);")
                add("await UniTask.Yield();")

            add("action?.Invoke();")
            add("await UniTask.CompletedTask;")
            indent -= 1
            add("});")

            indent -= 1
            add("}")
            add()

            # -------------------------
            # 同期
            # -------------------------
            add(f"public static void Load{tag_name}(Action action = null)")
            add("{")
            indent += 1

            add("UniTask.Action(async () =>")
            add("{")
            indent += 1

            add("await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
            add("{")
            indent += 1

            for item_name in tagged_items:
                add(f"header.GetData<GameCore.Tables.{item_name}MatrixTable>(GameCore.Tables.MatrixTableID.{item_name}, reader);")

            add("action?.Invoke();")
            add("await UniTask.CompletedTask;")
            indent -= 1
            add("});")

            indent -= 1
            add("}).Invoke();")

            indent -= 1
            add("}")
            add()

            dict_tags_load_write_script[tag_name] = lines

        append_str = "\n".join(
            "\n".join(lines)
            for lines in dict_tags_load_write_script.values()
        )

        code_str = f"""
using System;
using Cysharp.Threading.Tasks;
using System.Collections.Generic;

namespace GameCore.Tables
{{
    public static class MatrixTableIdUtils
    {{
{textwrap.indent(append_str, '        ')}
    }}
}}
"""

        cs_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'MatrixTableIdUtils.cs')
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(code_str)

    except Exception as e:
        logger.error(f"Matrixタグロードスクリプト生成エラー: {str(e)}")


def flask_main():
    app.run(debug=True, port=8000,use_reloader=False)

if __name__ == '__main__':
    websocket_thread = threading.Thread(target=dbgServer.mainServer, daemon=True)
    flask_thread = threading.Thread(target=flask_main, daemon=True)
    
    # Start both threads
    flask_thread.start()
    websocket_thread.start()

    # Keep the main thread alive
    try:
        websocket_thread.join()
        flask_thread.join()
    except KeyboardInterrupt:
        print("Shutting down servers...")