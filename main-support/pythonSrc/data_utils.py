# -*- coding: utf-8 -*-
"""
pythonSrc/data_utils.py

class_data / class_data_id / matrix / state / behavior 等、複数のルートモジュールから
共通して利用されるデータ読み込み・型解決・バイナリ書き込みヘルパー。

元々 app.py に直書きされていたものを切り出したもの。DATA_DIR は app.py 起動時に
`data_utils.init(DATA_DIR)` を1度呼び出すことで設定される。
"""
import json
import os
import struct
from math import isnan, isfinite
import sys

import pythonSrc.customclassdata

from pythonSrc.constants import ENUM, CLASS_DATA, CLASS_DATA_ID, TYPE_MAP,ASSETS_DATA,GAMEOBJECT_DATA,TEXTURE_DATA,SOUND_DATA

# app.py 側の register(app, DATA_DIR) で設定される
# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
    isDbg = False
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))


def init(data_dir):
    """app.py から起動時に一度だけ呼び出し、DATA_DIR を共有する。"""
    global DATA_DIR
    DATA_DIR = data_dir


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

# CustomClassData / CustomClassDataID の型リスト取得
# (get_type_lists() のタプルは既存呼び出し箇所が多いため互換性を壊さないよう、
#  こちらは独立した追加ヘルパーとして用意する)
def get_custom_type_lists():
    custom_class_list_path = os.path.join(DATA_DIR, 'custom_class_data', 'custom_class_data_list.json')
    custom_class_id_list_path = os.path.join(DATA_DIR, 'custom_class_data_id', 'custom_class_data_id_list.json')
    custom_class_list_raw = json.load(open(custom_class_list_path, encoding='utf-8')) if os.path.exists(custom_class_list_path) else []
    custom_class_id_list_raw = json.load(open(custom_class_id_list_path, encoding='utf-8')) if os.path.exists(custom_class_id_list_path) else []
    custom_class_list = [c.get('name') for c in custom_class_list_raw] if custom_class_list_raw else []
    custom_class_id_list = [c.get('name') for c in custom_class_id_list_raw] if custom_class_id_list_raw else []

    custom_class_schemas = {}
    for nm in custom_class_list:
        p = os.path.join(DATA_DIR, 'custom_class_data', nm, f"{nm}.customclass.json")
        schema = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else []
        try:
            pythonSrc.customclassdata._refresh_live_bit_flag_names(schema)
        except Exception:
            pass
        custom_class_schemas[nm] = schema

    return custom_class_list, custom_class_id_list, custom_class_schemas


def load_custom_class_data_id_dict(custom_class_id_list):
    """CustomClassDataID の行データを class_data_id と同じ形( {name+'ID': {'rows': [...]}} )で読み込む"""
    result = {}
    for nm in custom_class_id_list:
        p = os.path.join(DATA_DIR, 'custom_class_data_id', nm, f"{nm}.json")
        result[nm + 'ID'] = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {'rows': []}
    return result


def build_custom_type_info(enum_list, class_list, class_data_id_list):
    """write_binary_field(_extend) / generate_custom_field 用の type_info dict を組み立てる。
    (pythonSrc/customclassdata.py の関数がそのまま利用できる形)"""
    custom_class_list, custom_class_id_list, custom_class_schemas = get_custom_type_lists()
    return {
        'enum_list': enum_list,
        'class_list': class_list,
        'class_data_id_list': class_data_id_list,
        'custom_class_list': custom_class_list,
        'custom_class_id_list': custom_class_id_list,
        'custom_class_schemas': custom_class_schemas,
    }


class _ExtendWriter:
    """bytearray(f.extend方式) に customclassdata.py 側の f.write(...) ベースの関数を
    そのまま流用するためのアダプタ"""
    def __init__(self, buf):
        self._buf = buf

    def write(self, data):
        self._buf.extend(data)


def get_json_enum(name):
    enum_data = json.load(open(os.path.join(DATA_DIR, ENUM,f"{name}", f"{name}.json"))) if os.path.exists(os.path.join(DATA_DIR, ENUM,f"{name}", f"{name}.json")) else []
    return enum_data

def get_json_enum_parent():
    enum_data = json.load(open(os.path.join(DATA_DIR, ENUM, f"enum_list.json"))) if os.path.exists(os.path.join(DATA_DIR, ENUM,f"enum_list.json")) else []
    return enum_data

def add_json_enum_parent(name):
        # JSON読み込み
    with open(os.path.join(DATA_DIR, ENUM,"enum_list.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
        
     # 既に存在するなら追加しない
    if any(item["name"] == name for item in data):
        return None

    # 最大ID + 1
    new_id = max((item["id"] for item in data), default=0) + 1

    # 追加
    new_item = {
        "id": new_id,
        "name": name,
        "view": False
    }

    data.append(new_item)

    # JSON保存
    with open(os.path.join(DATA_DIR, ENUM,"enum_list.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return new_item

def get_json_data_id(name):
    data_id = json.load(open(os.path.join(DATA_DIR, CLASS_DATA_ID,f"{name}", f"{name}.json"))) if os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_ID,f"{name}", f"{name}.json")) else []
    return data_id

def get_json_gameobject():
    data_id = json.load(open(os.path.join(DATA_DIR,ASSETS_DATA,GAMEOBJECT_DATA ,f"assets_gameobject.json"))) if os.path.exists(os.path.join(DATA_DIR, ASSETS_DATA,GAMEOBJECT_DATA,f"assets_gameobject.json")) else []
    return data_id

def get_json_sound():
    data_id = json.load(open(os.path.join(DATA_DIR,ASSETS_DATA,SOUND_DATA ,f"assets_sound.json"))) if os.path.exists(os.path.join(DATA_DIR, ASSETS_DATA,SOUND_DATA,f"assets_sound.json")) else []
    return data_id

def get_json_texture():
    data_id = json.load(open(os.path.join(DATA_DIR,ASSETS_DATA,TEXTURE_DATA ,f"assets_texture.json"))) if os.path.exists(os.path.join(DATA_DIR, ASSETS_DATA,TEXTURE_DATA,f"assets_texture.json")) else []
    return data_id


#バイナリ書き込み
def write_binary_field(f, value, type_str, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=None, custom_type_info=None):

    if type_str.endswith('[]'):
        inner_type = type_str[:-2]
        values = value if isinstance(value, list) else []
        f.write(struct.pack('i', len(values)))
        for v in values:
            write_binary_field(f, v, inner_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=options, custom_type_info=custom_type_info)
        return

    # ★ dictionary型: { entries: [{key, value}, ...] } を
    #   [件数][キー][値][キー][値]... の順で書き込む。
    #   値は options.valueArraySize (0=単一 / -1=可変長List / N=固定長配列) に応じて
    #   ClassDataのフィールドと同じ規則で書き込むため、
    #   Dictionary<T,List<~>> や Dictionary<T,Dictionary<TE,~>> のような入れ子にも
    #   再帰的に対応できる（write_binary_field自身を再帰呼び出しするため）。
    if type_str == 'dictionary':
        opts = options or {}
        key_type = opts.get('keyType', 'int')
        value_type = opts.get('valueType', 'int')
        value_array_size = opts.get('valueArraySize', 0) or 0
        value_options = opts.get('valueOptions') or {}
        entries = value.get('entries', []) if isinstance(value, dict) else []

        f.write(struct.pack('i', len(entries)))
        for entry in entries:
            k = entry.get('key') if isinstance(entry, dict) else None
            v = entry.get('value') if isinstance(entry, dict) else None

            # キー（int / Enum / ClassDataID / CustomClassDataID のみ）
            write_binary_field(f, k, key_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=None, custom_type_info=custom_type_info)

            # 値（0=単一 / -1=可変長List / N>0=固定長配列）
            if value_array_size == -1:
                values = v if isinstance(v, list) else []
                f.write(struct.pack('i', len(values)))
                for vv in values:
                    write_binary_field(f, vv, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=value_options, custom_type_info=custom_type_info)
            elif value_array_size > 0:
                values = v if isinstance(v, list) else [None] * value_array_size
                for vv in values[:value_array_size]:
                    write_binary_field(f, vv, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=value_options, custom_type_info=custom_type_info)
            else:
                write_binary_field(f, v, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=value_options, custom_type_info=custom_type_info)
        return

    # bit / color / bezier、および CustomClassData・CustomClassDataID を参照する型は
    # pythonSrc/customclassdata.py 側の実装(既にbit/color/bezier対応済み)へ委譲する
    if type_str in ('bit', 'color', 'bezier') or (
        custom_type_info and (
            type_str in custom_type_info.get('custom_class_list', [])
            or type_str in custom_type_info.get('custom_class_id_list', [])
        )
    ):
        ti = custom_type_info or {
            'enum_list': enum_list, 'class_list': class_list, 'class_data_id_list': class_data_id_list,
            'custom_class_list': [], 'custom_class_id_list': [], 'custom_class_schemas': {},
        }
        pythonSrc.customclassdata._write_custom_single_value(f, value, type_str, options or {}, ti)
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
            item_options = item.get('options')
            if array_size == -1:  # List
                values = item_value if isinstance(item_value, list) else []
                f.write(struct.pack('i', len(values)))
                for v in values:
                    write_binary_field(f, v, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=item_options, custom_type_info=custom_type_info)
            elif array_size > 0:  # Array
                values = item_value if isinstance(item_value, list) else [None] * array_size
                for v in values[:array_size]:
                    write_binary_field(f, v, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=item_options, custom_type_info=custom_type_info)
            else:
                write_binary_field(f, item_value, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=item_options, custom_type_info=custom_type_info)
    else:
        f.write(struct.pack('i', 0))  # 未サポート型
        
def write_binary_field_extend(f, value, type_str, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=None, custom_type_info=None):
    if type_str.endswith('[]'):
        inner_type = type_str[:-2]
        values = value if isinstance(value, list) else []
        f.extend(struct.pack('i', len(values)))
        for v in values:
            write_binary_field_extend(f, v, inner_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=options, custom_type_info=custom_type_info)
        return

    # ★ dictionary型（write_binary_fieldと同じ規則。f.extend版）
    if type_str == 'dictionary':
        opts = options or {}
        key_type = opts.get('keyType', 'int')
        value_type = opts.get('valueType', 'int')
        value_array_size = opts.get('valueArraySize', 0) or 0
        value_options = opts.get('valueOptions') or {}
        entries = value.get('entries', []) if isinstance(value, dict) else []

        f.extend(struct.pack('i', len(entries)))
        for entry in entries:
            k = entry.get('key') if isinstance(entry, dict) else None
            v = entry.get('value') if isinstance(entry, dict) else None

            write_binary_field_extend(f, k, key_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=None, custom_type_info=custom_type_info)

            if value_array_size == -1:
                values = v if isinstance(v, list) else []
                f.extend(struct.pack('i', len(values)))
                for vv in values:
                    write_binary_field_extend(f, vv, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=value_options, custom_type_info=custom_type_info)
            elif value_array_size > 0:
                values = v if isinstance(v, list) else [None] * value_array_size
                for vv in values[:value_array_size]:
                    write_binary_field_extend(f, vv, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=value_options, custom_type_info=custom_type_info)
            else:
                write_binary_field_extend(f, v, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=value_options, custom_type_info=custom_type_info)
        return

    if type_str in ('bit', 'color', 'bezier') or (
        custom_type_info and (
            type_str in custom_type_info.get('custom_class_list', [])
            or type_str in custom_type_info.get('custom_class_id_list', [])
        )
    ):
        ti = custom_type_info or {
            'enum_list': enum_list, 'class_list': class_list, 'class_data_id_list': class_data_id_list,
            'custom_class_list': [], 'custom_class_id_list': [], 'custom_class_schemas': {},
        }
        pythonSrc.customclassdata._write_custom_single_value(_ExtendWriter(f), value, type_str, options or {}, ti)
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
            item_options = item.get('options')
            if array_size == -1:  # List
                values = item_value if isinstance(item_value, list) else []
                f.extend(struct.pack('i', len(values)))
                for v in values:
                    write_binary_field_extend(f, v, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=item_options, custom_type_info=custom_type_info)
            elif array_size > 0:  # Array
                values = item_value if isinstance(item_value, list) else [None] * array_size
                for v in values[:array_size]:
                    write_binary_field_extend(f, v, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=item_options, custom_type_info=custom_type_info)
            else:
                write_binary_field_extend(f, item_value, item['type'], basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=item_options, custom_type_info=custom_type_info)
    else:
        f.extend(struct.pack('i', 0))  # 未サポート型



# C#フィールド生成（private + ゲッター）
# ============================================================
# dictionary型のC#コード生成用ヘルパー
# ・型名解決（_dict_cs_type_name）と読み込みコード生成（_dict_read_*）を分離している
# ・valueType が 'dictionary' の場合は再帰的に解決するため、
#   Dictionary<T,List<~>> や Dictionary<T,Dictionary<TE,~>> のような入れ子にも対応する
# ・注意: bit / color / bezier / CustomClassData / CustomClassDataID を
#   Dictionaryの「値」に使うケースは、pythonSrc/customclassdata.py 側の実装に
#   深く依存するため現状未対応（該当箇所はTODOコメント付きでint読み飛ばしにフォールバックする）
# ============================================================
def _dict_cs_type_name(type_str, options, enum_list, class_list, class_id_list):
    if type_str == 'dictionary':
        opts = options or {}
        key_cs = _dict_cs_type_name(opts.get('keyType', 'int'), None, enum_list, class_list, class_id_list)
        value_type = opts.get('valueType', 'int')
        value_array_size = opts.get('valueArraySize', 0) or 0
        value_options = opts.get('valueOptions') or {}
        value_cs = _dict_cs_type_name(value_type, value_options, enum_list, class_list, class_id_list)
        if value_array_size == -1:
            value_cs = f"List<{value_cs}>"
        elif value_array_size > 0:
            value_cs = f"{value_cs}[]"
        return f"Dictionary<{key_cs}, {value_cs}>"
    if type_str in enum_list:
        return f"GameCore.Enums.{type_str}ID"
    if type_str in class_list:
        return f"GameCore.Classes.{type_str}"
    if type_str in class_id_list:
        return f"GameCore.Tables.ID.{type_str}TableID"
    if type_str.lower() in TYPE_MAP:
        return type_str.capitalize() if type_str.lower() in ['vector2', 'vector3'] else type_str.lower()
    return type_str


def _dict_read_single_stmts(target, type_str, options, enum_list, class_list, class_id_list, indent):
    """1つの値(キー or 値。type_strが'dictionary'なら入れ子Dictionary)をreaderから
    読み込み、ローカル変数targetへ代入するC#文のリストを返す。"""
    if type_str == 'dictionary':
        return _dict_read_dictionary_stmts(target, options, enum_list, class_list, class_id_list, indent)

    tl = type_str.lower()
    lines = []
    if tl in TYPE_MAP:
        if tl == 'string':
            lines.append(f"{indent}int {target}_len = reader.ReadInt32();")
            lines.append(f"{indent}{target} = System.Text.Encoding.UTF8.GetString(reader.ReadBytes({target}_len));")
        elif tl == 'vector2':
            lines.append(f"{indent}{target} = new Vector2(reader.ReadSingle(), reader.ReadSingle());")
        elif tl == 'vector3':
            lines.append(f"{indent}{target} = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());")
        else:
            lines.append(f"{indent}{target} = reader.{TYPE_MAP[tl]['cs_read']}();")
    elif type_str in enum_list or type_str in class_id_list:
        cs_type = _dict_cs_type_name(type_str, None, enum_list, class_list, class_id_list)
        lines.append(f"{indent}{target} = ({cs_type})Enum.ToObject(typeof({cs_type}), reader.ReadInt32());")
    elif type_str in class_list:
        cs_type = _dict_cs_type_name(type_str, None, enum_list, class_list, class_id_list)
        lines.append(f"{indent}{target} = new {cs_type}();")
        lines.append(f"{indent}{target}.Read(reader);")
    else:
        # bit / color / bezier / CustomClassData(ID) 等: Dictionaryの値としては現状未対応
        lines.append(f"{indent}reader.ReadInt32(); // TODO: '{type_str}' 型はDictionaryのキー/値として未対応です")
    return lines


def _dict_read_dictionary_stmts(target, options, enum_list, class_list, class_id_list, indent):
    opts = options or {}
    key_type = opts.get('keyType', 'int')
    value_type = opts.get('valueType', 'int')
    value_array_size = opts.get('valueArraySize', 0) or 0
    value_options = opts.get('valueOptions') or {}

    key_cs = _dict_cs_type_name(key_type, None, enum_list, class_list, class_id_list)
    item_cs = _dict_cs_type_name(value_type, value_options, enum_list, class_list, class_id_list)
    if value_array_size == -1:
        value_cs = f"List<{item_cs}>"
    elif value_array_size > 0:
        value_cs = f"{item_cs}[]"
    else:
        value_cs = item_cs
    dict_cs_type = f"Dictionary<{key_cs}, {value_cs}>"

    lines = [
        f"{indent}{target} = new {dict_cs_type}();",
        f"{indent}int {target}_count = reader.ReadInt32();",
        f"{indent}for (int {target}_i = 0; {target}_i < {target}_count; {target}_i++) {{",
    ]
    inner = indent + "    "
    lines.append(f"{inner}{key_cs} {target}_key;")
    lines += _dict_read_single_stmts(f"{target}_key", key_type, None, enum_list, class_list, class_id_list, inner)

    if value_array_size == -1:
        lines.append(f"{inner}var {target}_val = new List<{item_cs}>();")
        lines.append(f"{inner}int {target}_val_count = reader.ReadInt32();")
        lines.append(f"{inner}for (int {target}_j = 0; {target}_j < {target}_val_count; {target}_j++) {{")
        item_indent = inner + "    "
        lines.append(f"{item_indent}{item_cs} {target}_item;")
        lines += _dict_read_single_stmts(f"{target}_item", value_type, value_options, enum_list, class_list, class_id_list, item_indent)
        lines.append(f"{item_indent}{target}_val.Add({target}_item);")
        lines.append(f"{inner}}}")
    elif value_array_size > 0:
        lines.append(f"{inner}var {target}_val = new {item_cs}[{value_array_size}];")
        lines.append(f"{inner}for (int {target}_j = 0; {target}_j < {value_array_size}; {target}_j++) {{")
        item_indent = inner + "    "
        lines.append(f"{item_indent}{item_cs} {target}_item;")
        lines += _dict_read_single_stmts(f"{target}_item", value_type, value_options, enum_list, class_list, class_id_list, item_indent)
        lines.append(f"{item_indent}{target}_val[{target}_j] = {target}_item;")
        lines.append(f"{inner}}}")
    else:
        lines.append(f"{inner}{item_cs} {target}_val;")
        lines += _dict_read_single_stmts(f"{target}_val", value_type, value_options, enum_list, class_list, class_id_list, inner)

    lines.append(f"{inner}{target}[{target}_key] = {target}_val;")
    lines.append(f"{indent}}}")
    return lines


def generate_csharp_field(item, enum_list, class_list, unity_types, basic_types,class_id_list, custom_type_info=None):
    type_str = item['type'].replace("[]", "")

    # ★ dictionary型: bit/color/bezier同様にここで早期returnする（他モジュールへの委譲なしで完結）
    if type_str == 'dictionary':
        var_name = item['name']
        description = item.get('description', '')
        options = item.get('options') or {}
        dict_cs_type = _dict_cs_type_name('dictionary', options, enum_list, class_list, class_id_list)
        read_lines = _dict_read_dictionary_stmts(var_name, options, enum_list, class_list, class_id_list, "            ")
        return {
            'field': f"        [SerializeField]\n        protected {dict_cs_type} {var_name} = new {dict_cs_type}();\n        public {dict_cs_type} {var_name.capitalize()} {{ get => {var_name}; }} // {description}\n",
            'read': "\n".join(read_lines) + "\n"
        }

    # bit / color / bezier、CustomClassData・CustomClassDataID参照は
    # pythonSrc/customclassdata.py 側の実装(bit/color/bezier対応済み)へ委譲する
    if custom_type_info and (
        type_str in ('bit', 'color', 'bezier')
        or type_str in custom_type_info.get('custom_class_list', [])
        or type_str in custom_type_info.get('custom_class_id_list', [])
    ):
        custom_field = pythonSrc.customclassdata.generate_custom_field(item, custom_type_info)
        return {'field': custom_field['field'], 'read': custom_field['read']}

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
        'field': f"        [SerializeField]\n        protected {type_str} {var_name};\n        public {type_str} {var_name.capitalize()} {{ get => {var_name}; }} // {description}\n",
        'read': read_code
    }

