# -*- coding: utf-8 -*-
"""
pythonSrc/class_data.py

ClassData / Enum 管理API。
- /api/enum-id, /api/enum/<name>, /api/generate-enum/<name>
- /api/class-data, /api/class-data/<name>, /api/generate-class/<name>
- /api/generate-all-binary, /api/generate-table-id
- /api/generate-all-enums, /api/generate-all-cs-header

app.py から `pythonSrc.class_data.register(app, DATA_DIR)` を呼び出して有効化する。
"""
import json
import logging
import os
import struct
from math import isnan, isfinite
import sys
from flask import Blueprint, jsonify, request

import pythonSrc.trash as trash

import pythonSrc.customclassdata
from pythonSrc.constants import ENUM, CLASS_DATA, CLASS_DATA_ID
from pythonSrc.data_utils import (
    get_type_lists,
    build_custom_type_info,
    generate_csharp_field,
    write_binary_field,
)
import pythonSrc.generators as generators
import pythonSrc.class_data_id as class_data_id

logger = logging.getLogger(__name__)
bp = Blueprint('class_data', __name__)

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
    """app.py から呼び出す初期化関数。"""
    global DATA_DIR
    DATA_DIR = os.path.abspath(data_dir)


# Enum-ID管理
@bp.route('/api/enum-id', methods=['GET', 'POST', 'PATCH'])
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

@bp.route('/api/enum/<name>', methods=['GET', 'POST', 'DELETE'])
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

            # 仕様書項目5(追記分): このEnumをprefill元として参照しているList/Dictionaryフィールドを
            # 現在のメンバー構成に追従させる(class_data_id.py側でmatrix/scenarioへもカスケードする)。
            try:
                import pythonSrc.class_data_id as class_data_id_api
                current_members = [item.get('property') for item in (data or []) if isinstance(item, dict) and item.get('property')]
                class_data_id_api.sync_prefill_dependents(name, current_members)
            except Exception as sync_err:
                logger.error(f"prefill同期カスケードエラー(enum={name}): {str(sync_err)}")

            return jsonify({"message": f"{name}.json saved successfully"})
        except Exception as e:
            logger.error(f"Error saving enum {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    elif request.method == 'DELETE':
        try:
            if os.path.exists(file_path):
                enum_list_path = os.path.join(DATA_DIR, ENUM, 'enum_list.json')
                with open(enum_list_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 復元時に一覧へ戻せるよう、削除前のエントリを退避しておく
                deleted_entry = next((item for item in data if item.get('name') == name), None)
                data = [item for item in data if item['name'] != name]
                with open(enum_list_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                # 即時削除ではなくゴミ箱へ退避（一定期間内なら復元可能）
                trash.move_to_trash('enum', name, os.path.join(DATA_DIR, ENUM, name), list_entry=deleted_entry)
                logger.info(f"Deleted enum: {name}")
                try:
                    import pythonSrc.class_data_id as class_data_id_api
                    class_data_id_api.sync_prefill_dependents(name, [])
                except Exception as sync_err:
                    logger.error(f"prefill同期カスケードエラー(enum削除={name}): {str(sync_err)}")
                return jsonify({"message": f"{name}.json deleted successfully"})
            return jsonify({"error": f"{name}.json not found"}), 404
        except Exception as e:
            logger.error(f"Error deleting enum {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500

@bp.route('/api/generate-enum/<name>', methods=['POST'])
def generate_enum_cs(name):
    try:
        data = request.get_json()
        generate_enum_files(name, data)
        return jsonify({"message": f"C# enum {name}ID generated successfully"})
    except Exception as e:
        logger.error(f"Error generating C# enum {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500


def generate_enum_files(name, data):
    """
    enum の C#/Python/JS ファイル一式を生成する（/api/generate-enum/<name> の実処理）。
    Flaskルート以外（例: pythonSrc/scene.py がシーン用enumを同期する時）からも
    直接呼び出せるよう、独立した関数として切り出している。
    """
    try:
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
        
    except Exception as e:
        logger.error(f"Error generating C# enum {name}: {str(e)}")
        raise

# ClassData-ID管理
@bp.route('/api/class-data', methods=['GET', 'POST', 'PATCH'])
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
            # 復元時に一覧へ戻せるよう、削除前のエントリを退避しておく
            deleted_entry = next((item for item in data if item.get('name') == delete_name), None)
            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # 一覧から消すだけでなく、実データフォルダも即時削除ではなく
            # ゴミ箱へ退避する（一定期間内なら復元可能）
            trash.move_to_trash('class_data', delete_name,
                                 os.path.join(DATA_DIR, CLASS_DATA, delete_name), list_entry=deleted_entry)
            logger.info(f"Removed class: {delete_name}")
            return jsonify({"message": f"Class {delete_name} removed from class_list.json"})
        except FileNotFoundError:
            return jsonify({"error": "class_list.json not found"}), 404
        except Exception as e:
            logger.error(f"Error removing class-data: {str(e)}")
            return jsonify({"error": str(e)}), 500

# ClassData詳細管理
@bp.route('/api/class-data/<name>', methods=['GET', 'POST', 'DELETE'])
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
            # bit/color/bezier/数値型のoptionsを正規化(CustomClassDataと同じロジックを再利用)
            if isinstance(data, list):
                for field in data:
                    if isinstance(field, dict) and (field.get('type') in ('bit', 'color', 'bezier') or field.get('type', '') in pythonSrc.customclassdata.NUMERIC_TYPES):
                        pythonSrc.customclassdata._normalize_field_options(field)
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
                class_list_path = os.path.join(DATA_DIR, CLASS_DATA, 'class_list.json')
                with open(class_list_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                deleted_entry = next((item for item in data if item.get('name') == name), None)
                data = [item for item in data if item['name'] != name]
                with open(class_list_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                trash.move_to_trash('class_data', name,
                                     os.path.join(DATA_DIR, CLASS_DATA, name), list_entry=deleted_entry)
                logger.info(f"Deleted class: {name}")
                return jsonify({"message": f"{name}.class.json deleted successfully"})
            logger.warning(f"{name}.class.json not found at {file_path}")
            return jsonify({"error": f"{name}.class.json not found"}), 404
        except Exception as e:
            logger.error(f"Error deleting class {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500

# ClassData C#生成
@bp.route('/api/generate-class/<name>', methods=['POST'])
def generate_class_cs(name):
    try:
        data = request.get_json()
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data= get_type_lists()
        custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)
        if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, name)):
            os.makedirs(os.path.join(DATA_DIR, CLASS_DATA, name), exist_ok=True)
        cs_path = os.path.join(DATA_DIR, CLASS_DATA,name, f"Base{name}.cs")
        
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
            f.write("namespace GameCore.Classes\n{\n")
            f.write(f"    [Serializable]\n")
            f.write(f"    public class Base{name} : BaseCustomClassData\n    {{\n")
            read_codes = []
            for item in data:
                field_data = generate_csharp_field(item, enum_list, class_list, unity_types, basic_types,class_data_id_list, custom_type_info=custom_type_info)
                f.write(field_data['field'])
                read_codes.append(field_data['read'])
            f.write(f"\n        public Base{name}() : base() {{ }}\n        public override void Read(BinaryReader reader)        {{\n")
            for read_code in read_codes:
                f.write(read_code)
            f.write("        }\n")
            f.write("    }\n}\n")
        if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA, name, f"{name}.cs")):
            cs_path = os.path.join(DATA_DIR, CLASS_DATA,name, f"{name}.cs")
            with open(cs_path, 'w', encoding='utf-8') as f:
                f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
                f.write("namespace GameCore.Classes\n{\n")
                f.write(f"    [Serializable]\n")
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

    rows = json_data.get('rows', [])
    columns = json_data.get('columns', [])
    basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data = get_type_lists()
    custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)

    # --- ① ヘッダー部（rowCount / colCount / 列定義）：フォーマットは従来通り ---
    header_buf = io.BytesIO()
    header_buf.write(struct.pack('i', len(rows)))
    header_buf.write(struct.pack('i', len(columns)))

    for col in columns:
        name_encoded = col['name'].encode('utf-8')
        type_encoded = col['type'].encode('utf-8')
        header_buf.write(struct.pack('i', len(name_encoded)))
        header_buf.write(name_encoded)
        header_buf.write(struct.pack('i', len(type_encoded)))
        header_buf.write(type_encoded)
    header_bytes = header_buf.getvalue()

    # --- ② 各行を個別にシリアライズ（行ごとのバイト長を先に確定させるため） ---
    row_bytes_list = []
    for row in rows:
        rf = io.BytesIO()
        rf.write(struct.pack('i', row.get('id', 0)))
        for col in columns:
            cell = row['data'].get(col['name'], {})
            value = cell.get('value') if isinstance(cell, dict) else cell

            if isinstance(value, (int, float)) and (isnan(value) or not isfinite(value)):
                rf.write(struct.pack('i', 0))
                continue

            write_binary_field(
                rf, value, col['type'],
                basic_types, unity_types, enum_list, class_list,
                class_data_id_list, enum_data, class_data_id, class_data,
                options=col.get('options'), custom_type_info=custom_type_info
            )
        row_bytes_list.append(rf.getvalue())

    # --- ③ 行インデックス（id / テーブル先頭からの相対offset / size）を追加 ---
    #     構造: [rowIndexCount:4] + (id:4 / offset:8(相対) / size:4) * rowCount
    row_index_header_size = 4
    row_index_entry_size = 4 + 8 + 4
    row_index_size = row_index_header_size + row_index_entry_size * len(rows)
    row_data_base_offset = len(header_bytes) + row_index_size  # 行データ本体の開始位置（テーブル先頭からの相対）

    row_index_buf = io.BytesIO()
    row_index_buf.write(struct.pack('i', len(rows)))
    current_offset = row_data_base_offset
    for row, row_bytes in zip(rows, row_bytes_list):
        row_index_buf.write(struct.pack('i', row.get('id', 0)))
        row_index_buf.write(struct.pack('q', current_offset))
        row_index_buf.write(struct.pack('i', len(row_bytes)))
        current_offset += len(row_bytes)

    return header_bytes + row_index_buf.getvalue() + b''.join(row_bytes_list)

@bp.route('/api/generate-all-binary', methods=['POST'])
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

@bp.route('/api/generate-table-id', methods=['POST'])
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

@bp.route('/api/generate-all-enums', methods=['POST'])
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

@bp.route('/api/generate-all-cs-header', methods=['POST'])
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
        class_data_id.generate_tags_load_script()
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)
        return jsonify({"message": "C# header generated successfully"})
    except Exception as e:
        logger.error(f"Error generating C# header: {str(e)}")
        return jsonify({"error": str(e)}), 500
    



def generate_base(data_dir):
    """
    ClassData / Enum 用のボイラープレート生成（初回起動時のみ）。
    - enum_list.json / class_list.json の初期化
    - BaseCustomClassData.cs / .py / .js
    - EnumIDIter.cs
    """
    os.makedirs(os.path.join(data_dir, ENUM), exist_ok=True)
    os.makedirs(os.path.join(data_dir, CLASS_DATA), exist_ok=True)

    if not os.path.exists(os.path.join(data_dir, ENUM, "enum_list.json")):
        with open(os.path.join(data_dir, ENUM, "enum_list.json"), 'w', encoding='utf-8') as f:
            json.dump([], f)

    if not os.path.exists(os.path.join(data_dir, CLASS_DATA, "class_list.json")):
        with open(os.path.join(data_dir, CLASS_DATA, "class_list.json"), 'w', encoding='utf-8') as f:
            json.dump([], f)

    #BaseCustomClassData
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA, "BaseCustomClassData.cs")):
        code_str = """
    using System.IO;

    namespace GameCore.Classes
    {
        [System.Serializable]
        public abstract class BaseCustomClassData
        {
            public abstract void Read(BinaryReader reader);
        }
    }
    """
        with open(os.path.join(data_dir, CLASS_DATA, "BaseCustomClassData.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")


    if not os.path.exists(os.path.join(data_dir,ENUM,"EnumIDIter.cs")):
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
        with open(os.path.join(data_dir,ENUM,"EnumIDIter.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")
    

    #python版 -ClassData-
    if not os.path.exists(os.path.join(data_dir,CLASS_DATA,"BaseCustomClassData.py")):
        code = """
from abc import ABC, abstractmethod
class BaseCustomClassData(ABC):
    @abstractmethod
    def read(self, reader):
        pass

    def load_json(self, data):
        pass
    """
        with open(os.path.join(data_dir,CLASS_DATA,"BaseCustomClassData.py"), 'w', encoding='utf-8') as f:
            f.write(code)


    if not os.path.exists(os.path.join(data_dir,CLASS_DATA,"BaseCustomClassData.js")):
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
        with open(os.path.join(data_dir,CLASS_DATA,"BaseCustomClassData.js"), 'w', encoding='utf-8') as f:
            f.write(code)




def register(app, data_dir):
    """app.py から呼び出し、DATA_DIR を設定・ボイラープレート生成した上でルートを登録する。"""
    global DATA_DIR
    DATA_DIR = data_dir
    generate_base(data_dir)
    app.register_blueprint(bp)