# -*- coding: utf-8 -*-
"""
pythonSrc/class_data_id.py

ClassDataID（ID引きのテーブルデータ）管理API。
- /api/class-data-id, /api/class-data-id/<name>, /api/generate-class-data-id/<name>
- /api/generate-binary/<name>
- /api/class-data-id-tags 系（タグ一覧・名称変更・割り当て）

app.py から `pythonSrc.class_data_id.register(app, DATA_DIR)` を呼び出して有効化する。
"""
import json
import logging
import os
import shutil
import struct
import sys
import textwrap

from math import isnan, isfinite

from flask import Blueprint, jsonify, request

import pythonSrc.customclassdata
from pythonSrc.constants import CLASS_DATA, CLASS_DATA_ID, CLASS_DATA_MATRIX_ID, TYPE_MAP
from pythonSrc.data_utils import (
    get_type_lists,
    build_custom_type_info,
    generate_csharp_field,
    write_binary_field,
)
import pythonSrc.generators as generators

logger = logging.getLogger(__name__)
bp = Blueprint('class_data_id', __name__)

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
ENUM_DIR = os.path.join(DATA_DIR, 'enum')

def init(data_dir):
    """app.py から呼び出す初期化関数。"""
    global DATA_DIR
    DATA_DIR = os.path.abspath(data_dir)


@bp.route('/api/class-data-id', methods=['GET', 'POST', 'PATCH'])
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
@bp.route('/api/class-data-id/<name>', methods=['GET', 'POST', 'DELETE'])
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
            # columns の options を正規化(bit/color/bezier/数値型)
            if isinstance(new_data, dict) and isinstance(new_data.get('columns'), list):
                for col in new_data['columns']:
                    col_type = (col.get('type') or '').replace('[]', '')
                    if isinstance(col, dict) and (col_type in ('bit', 'color', 'bezier') or col_type in pythonSrc.customclassdata.NUMERIC_TYPES):
                        pythonSrc.customclassdata._normalize_field_options(col)
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

def generate_class_data_id_cs_core(name, columns, rows):
    """{name}Row.cs / {name}Table.cs / {name}TableID.cs（+ py/js版）を生成する実処理本体。
    Flaskのrequestに依存しないので、HTTPルート(generate_class_data_id_cs)からも、
    sync_scenario_class_data_ids_core など内部処理からも呼び出せる。
    """
    if True:
        basic_types, unity_types, enum_list, class_list, class_data_id_list ,enum_data,class_data_id,class_data= get_type_lists()
        enum_name = f"{name}TableID"  # Enum名をTableIDに変更

        # 出力ディレクトリ作成
        table_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, f"{name}")
        os.makedirs(table_dir, exist_ok=True)
        
        #-- Row ---
        with open(os.path.join(table_dir, f"{name}Row.cs"), 'w', encoding='utf-8') as lf:
            # --- Row Class ---
            lf.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\nusing GameCore.Tables.ID;\nusing GameCore.Enums;\n\n")
            lf.write("namespace GameCore.Tables\n{\n")
            lf.write(f"    public class {name}Row : BaseClassDataRow\n    {{\n")
            # dictionary型を含め、generate_csharp_field に処理を委譲して
            # フィールド宣言とRead()コードの両方をここで生成する
            # (以前はここで型変換ロジックを独自に再実装しており、dictionary型を考慮していなかった)
            custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)
            read_code = ""
            # 他のclass_data_idを参照しているフィールド（依存先プリロード用）
            ref_lines = []

            #まずは自分自身のIDを入れる
            lf.write("        [SerializeField]\n")
            lf.write(f"        protected {name}TableID table_id;\n")
            lf.write(f"        public {name}TableID TableID {{ get => table_id;}}\n")
            #次はRead
            read_code += f"            table_id = ({name}TableID)id;\n"
            for col in columns:
                field_for_cs = dict(col)
                is_arr_type = isinstance(col.get('type'), str) and col['type'].endswith('[]')
                base_type = col['type'][:-2] if is_arr_type else col['type']
                if is_arr_type:
                    field_for_cs['type'] = base_type
                    field_for_cs['arraySize'] = -1  # 動的配列(List)として扱う
                else:
                    field_for_cs.setdefault('arraySize', 0)
                field_info = generate_csharp_field(
                    field_for_cs, enum_list, class_list, unity_types, basic_types,
                    class_data_id_list, custom_type_info=custom_type_info
                )
                lf.write(field_info['field'])
                read_code += field_info['read']

                # --- 依存先プリロード用: 他のclass_data_idを参照しているフィールドを記録 ---
                if base_type in class_data_id_list:
                    var_name = col['name']
                    if is_arr_type:
                        ref_lines.append(
                            f"            foreach (var v in {var_name}) {{ if (v != {base_type}TableID.None) refs.Add((GameCore.Enums.TableID.{base_type}, (int)v)); }}"
                        )
                    else:
                        ref_lines.append(
                            f"            if ({var_name} != {base_type}TableID.None) refs.Add((GameCore.Enums.TableID.{base_type}, (int){var_name}));"
                        )

            # --- Read Method ---
            lf.write("\n        public override void Read(int id,BinaryReader reader)\n")
            lf.write("        {\n")
            lf.write(read_code)
            lf.write("        }\n")

            # --- GetReferencedIds Method（依存先プリロード用。参照フィールドがある場合のみoverride） ---
            if ref_lines:
                lf.write("\n        public override List<(TableID TableId, int RefId)> GetReferencedIds()\n")
                lf.write("        {\n")
                lf.write("            var refs = new List<(TableID, int)>();\n")
                for line in ref_lines:
                    lf.write(line + "\n")
                lf.write("            return refs;\n")
                lf.write("        }\n")

            lf.write("    }\n\n")
            lf.write("}\n")

        # --- {name}RowIndex.cs（基礎クラスBaseClassDataRowIndex<T>を継承。各idのシーク位置を保持） ---
        with open(os.path.join(table_dir, f"{name}RowIndex.cs"), 'w', encoding='utf-8') as rif:
            rif.write("using GameCore.Tables.ID;\n\n")
            rif.write("namespace GameCore.Tables\n{\n")
            rif.write(f"    public class {name}RowIndex : BaseClassDataRowIndex<{enum_name}>\n    {{\n")
            rif.write("    }\n}\n")

        # --- Main Table File ---
        cs_path = os.path.join(table_dir, f"{name}Table.cs")
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\nusing GameCore.Tables.ID;\nusing GameCore.Enums;\n\n")
            f.write("namespace GameCore.Tables\n{\n")
            f.write(f"    public class {name}Table : BaseClassDataID<{enum_name}, {name}Row>\n    {{\n")
            #f.write(f"        public static Dictionary<{enum_name}, {name}Row> Table = new Dictionary<{enum_name}, {name}Row>();\n\n")

            # --- RowIndex / TableIdの静的初期化 ---
            f.write(f"        static {name}Table()\n        {{\n")
            f.write(f"            RowIndex = new {name}RowIndex();\n")
            f.write(f"            TableId = TableID.{name};\n")
            f.write("            RegisterReferenceLoader(); // 依存先プリロード用に自分自身を登録\n")
            f.write("        }\n\n")

            # --- Table Constructor（全件ロード。行インデックスも同時にキャッシュされるため、部分ロードAPIと併用しても再読み込みは走らない） ---
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
            f.write("            RowIndex.Read(reader, true); // 行インデックスブロックを読み進めつつキャッシュしておく（高速な連続読みはそのまま維持）\n")
            f.write("            for(int r=0; r<rowCount; r++) {\n")
            f.write(f"                var enumVal = ({enum_name})Enum.ToObject(typeof({enum_name}), reader.ReadInt32());\n")
            f.write(f"                var row = new {name}Row();\n")
            f.write("                row.Read(r + 1,reader);\n")  # ← Readでまとめる
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

        return {"message": f"C# files generated: {cs_path}, {enum_cs_path}", "cs_path": cs_path, "enum_cs_path": enum_cs_path}


@bp.route('/api/generate-class-data-id/<name>', methods=['POST'])
def generate_class_data_id_cs(name):
    try:
        data = request.get_json()
        result = generate_class_data_id_cs_core(name, data['columns'], data['rows'])
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def generate_binary_core(name, columns, rows):
    """{name}Table.bytes を生成する実処理本体。Flaskのrequestに依存しないので、
    HTTPルート(generate_binary)からも内部処理からも呼び出せる。
    """
    if True:
        bin_path = os.path.join(DATA_DIR, CLASS_DATA_ID, name, f"{name}Table.bytes")
        os.makedirs(os.path.dirname(bin_path), exist_ok=True)
        
        basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data = get_type_lists()
        custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)
        
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

            # ------------------------------------------------------------
            # 行オフセットテーブル(シングルロード対応: 項目3-新規)。
            # ここにいったんプレースホルダを書いておき、各行を書き終えた後に
            # 実際の開始位置でシークして書き戻す(assets.pyの offsets 方式と同じ)。
            # これにより「id -> 何バイト目から読めばよいか」がわかり、
            # 全行を順番に読まなくても該当行だけシークして読み込める。
            # ------------------------------------------------------------
            row_offsets = [0] * len(rows)
            row_offsets_pos = f.tell()
            f.write(struct.pack('i' * len(rows), *row_offsets)) if rows else None

            # データ: 行ごとにEnumValue, 各カラム値
            for row_index, row in enumerate(rows):
                row_offsets[row_index] = f.tell()
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
                            item_options = item.get('options')
                            if array_size == -1:  # List
                                values = item_value if isinstance(item_value, list) else []
                                f.write(struct.pack('i', len(values)))
                                for v in values:
                                    write_binary_field(f, v, item['type'],basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data, options=item_options, custom_type_info=custom_type_info)
                            elif array_size > 0:  # Array
                                values = item_value if isinstance(item_value, list) else [None] * array_size
                                for v in values[:array_size]:
                                    write_binary_field(f, v, item['type'],basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data, options=item_options, custom_type_info=custom_type_info)
                            else:
                                write_binary_field(f, item_value, item['type'],basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data, options=item_options, custom_type_info=custom_type_info)

                    elif col['type'] in ('bit', 'color', 'bezier') or col['type'] in custom_type_info['custom_class_list'] or col['type'] in custom_type_info['custom_class_id_list']:
                        # CustomClassData / CustomClassDataID 参照、または bit/color/bezier型
                        actual_value = col_value.get('value') if isinstance(col_value, dict) else col_value
                        pythonSrc.customclassdata._write_custom_single_value(f, actual_value, col['type'], col.get('options') or {}, custom_type_info)

                    else:
                        col_name_type = col['type']
                        actual_value = col_value.get('value') if isinstance(col_value, dict) else col_value
                        # 配列型カラム("int[]", "MyClass[]", "SomeCustomClass[]"など)
                        if col_name_type.endswith('[]'):
                            base_type = col_name_type[:-2]
                            arr_vals = actual_value if isinstance(actual_value, list) else []
                            f.write(struct.pack('i', len(arr_vals)))  # 長さを先に書く
                            for v in arr_vals:
                                write_binary_field(f, v, base_type, basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data, options=col.get('options'), custom_type_info=custom_type_info)
                            else:
                                f.write(struct.pack('i', 0))  # 未サポート型

            # オフセットテーブルを実値で書き戻す
            if rows:
                end_pos = f.tell()
                f.seek(row_offsets_pos)
                f.write(struct.pack('i' * len(rows), *row_offsets))
                f.seek(end_pos)


        return {"message": f"Binary generated: {bin_path}", "bin_path": bin_path}


@bp.route('/api/generate-binary/<name>', methods=['POST'])
def generate_binary(name):
    try:
        data = request.get_json()
        result = generate_binary_core(name, data['columns'], data['rows'])
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error generating binary for {name}: {str(e)}")
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
 
@bp.route('/api/class-data-id-tags', methods=['GET', 'POST', 'PATCH'])
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
 
 
@bp.route('/api/class-data-id-tags/<int:tag_id>', methods=['PUT'])
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
 
 
@bp.route('/api/class-data-id/<name>/tag', methods=['PUT'])
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
        # タグを変更した場合、サブグループはそのタグに属さなくなるのでクリアする
        if target.get('subgroup') and target.get('tag') != tag:
            target['subgroup'] = None
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
 
        return jsonify({"message": f"{name} にタグを設定しました", "data": target}), 200
    except FileNotFoundError:
        return jsonify({"error": "class_data_id_list.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"タグ割り当てエラー {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# ClassDataID サブグループ機能(タグ配下の第2階層)
# ============================================================
# tags.json の各タグエントリに "subgroups": [名前, ...] を持たせる
# (登録順がそのままサブグループの並び順・enum ID順になる)。
# class_data_id_list.json の各エントリは "subgroup": 名前|null を持つ。
# サブグループはタグに従属するため、タグが変わる/削除されると
# 該当エントリの subgroup も一緒にクリアされる。
@bp.route('/api/class-data-id-tags/<int:tag_id>/subgroups', methods=['GET', 'POST'])
def manage_class_data_id_subgroups(tag_id):
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_ID)
    file_path = os.path.join(tags_dir, 'tags.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return jsonify({"error": "tags.jsonが見つかりません"}), 404

    target = next((t for t in data if t['id'] == tag_id), None)
    if not target:
        return jsonify({"error": "指定されたタグが見つかりません"}), 404
    target.setdefault('subgroups', [])

    if request.method == 'GET':
        return jsonify(target['subgroups']), 200

    # POST: サブグループを新規追加(登録順を維持)
    try:
        sub_name = (request.get_json() or {}).get('name')
        if not sub_name:
            return jsonify({"error": "サブグループ名は必須です"}), 400
        if sub_name in target['subgroups']:
            return jsonify({"error": f"サブグループ {sub_name} はすでに存在します"}), 400

        target['subgroups'].append(sub_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"message": f"サブグループ {sub_name} を作成しました", "data": target['subgroups']}), 201
    except Exception as e:
        logger.error(f"サブグループ作成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/class-data-id-tags/<int:tag_id>/subgroups/<path:sub_name>', methods=['DELETE'])
def delete_class_data_id_subgroup(tag_id, sub_name):
    """サブグループを削除する。所属していたエントリはタグ直下(subgroup=null)へ戻す"""
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_ID)
    file_path = os.path.join(tags_dir, 'tags.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        target = next((t for t in data if t['id'] == tag_id), None)
        if not target:
            return jsonify({"error": "指定されたタグが見つかりません"}), 404
        target.setdefault('subgroups', [])
        if sub_name not in target['subgroups']:
            return jsonify({"error": f"サブグループ {sub_name} が見つかりません"}), 404
        target['subgroups'].remove(sub_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # class_data_id_list.json 側で当該サブグループに属していたエントリを解除
        list_path = os.path.join(tags_dir, 'class_data_id_list.json')
        if os.path.exists(list_path):
            with open(list_path, 'r', encoding='utf-8') as f:
                list_data = json.load(f)
            changed = False
            for item in list_data:
                if item.get('tag') == target['name'] and item.get('subgroup') == sub_name:
                    item['subgroup'] = None
                    changed = True
            if changed:
                with open(list_path, 'w', encoding='utf-8') as f:
                    json.dump(list_data, f, ensure_ascii=False, indent=2)

        return jsonify({"message": f"サブグループ {sub_name} を削除しました"}), 200
    except FileNotFoundError:
        return jsonify({"error": "tags.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"サブグループ削除エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/class-data-id/<name>/subgroup', methods=['PUT'])
def set_class_data_id_subgroup(name):
    """特定のClassDataIDエントリにサブグループを割り当てる(subgroup=nullで解除)。
    エントリに現在割り当てられているタグの subgroups に含まれている必要がある。"""
    list_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')
    try:
        subgroup = request.get_json().get('subgroup')

        with open(list_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        target = next((item for item in data if item['name'] == name), None)
        if not target:
            return jsonify({"error": f"ClassDataID {name} が見つかりません"}), 404

        if subgroup is not None:
            if not target.get('tag'):
                return jsonify({"error": "サブグループを設定するには先にタグを設定してください"}), 400
            tags_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'tags.json')
            with open(tags_path, 'r', encoding='utf-8') as f:
                tag_list = json.load(f)
            tag_entry = next((t for t in tag_list if t['name'] == target['tag']), None)
            if not tag_entry or subgroup not in tag_entry.get('subgroups', []):
                return jsonify({"error": f"サブグループ {subgroup} はタグ {target['tag']} に登録されていません"}), 404

        target['subgroup'] = subgroup
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"message": f"{name} にサブグループを設定しました", "data": target}), 200
    except FileNotFoundError:
        return jsonify({"error": "class_data_id_list.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"サブグループ割り当てエラー {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# Scenario連携(項目6・8)
# ============================================================
# ClassDataID側の「タグ」を Scenario 用に1つ固定で使う(タグ名固定: "Scenario")。
# 親イベントごとに Scenario_{親} というサブグループを作り、
# その中に Scenario_{親}_{サブ} という ClassDataID エントリを1つずつ作る。
# シナリオイベント側(親/サブの追加・削除)から、このエンドポイントを
# 呼び出すことで、常に最新のイベント構成へ自動追従させる。
SCENARIO_TAG_NAME = "Scenario"
SCENARIO_SUB_NAME = "ScenarioMain"


def _ensure_scenario_tag():
    """"Scenario"タグが存在するか確認し、無ければ新規作成して返す(項目8)。"""
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_ID)
    os.makedirs(tags_dir, exist_ok=True)
    file_path = os.path.join(tags_dir, 'tags.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tags = json.load(f)
    except FileNotFoundError:
        tags = []

    target = next((t for t in tags if t['name'] == SCENARIO_TAG_NAME), None)
    if target is None:
        # 初めてScenarioタグを作るときだけ、サブタグ(サブグループ)の既定値として
        # ScenarioMainを設定する。
        max_id = max([t['id'] for t in tags], default=0) + 1
        target = {"id": max_id, "name": SCENARIO_TAG_NAME, "subgroups": [SCENARIO_SUB_NAME]}
        tags.append(target)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(tags, f, ensure_ascii=False, indent=2)
    else:
        target.setdefault('subgroups', [])
        # 既存のScenarioタグにScenarioMainが(まだ)無ければ追加する
        # (「最初にtagsを見てなかったら追加で」の要望への対応)。
        if SCENARIO_SUB_NAME not in target['subgroups']:
            target['subgroups'].append(SCENARIO_SUB_NAME)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(tags, f, ensure_ascii=False, indent=2)

    return tags, target


def generate_scenario_parent_enum_csharp(parent_name, sub_names):
    """親イベントごとの Scenario_{親}ID enum を生成する(assets.pyの
    generate_subgroup_enum_details_csharp と同じ考え方)。
    中身は Scenario_{親}_{サブ} の各サブの名前。
    ENUM_DIR/Scenario_{親}/Scenario_{親}ID.cs に生成する。
    """
    target_dir = os.path.join(ENUM_DIR, f"Scenario_{parent_name}")
    os.makedirs(target_dir, exist_ok=True)
    enum_name = f"Scenario_{parent_name}"

    cs_content = "namespace GameCore.Enums\n{\n"
    cs_content += f"    public enum {enum_name}ID\n    {{\n"
    cs_content += "        None = 0, // デフォルト値\n"
    for i, sub_name in enumerate(sub_names, start=1):
        cs_content += f"        {sub_name} = {i},\n"
    cs_content += f"        Max = {len(sub_names) + 1}\n"
    cs_content += "    }\n}"

    cs_path = os.path.join(target_dir, f"{enum_name}ID.cs")
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write(cs_content)

    json_dict = []
    js_path = os.path.join(target_dir, f"{enum_name}.json")
    with open(js_path, 'w', encoding='utf-8') as f:
        for i, sub_name in enumerate(sub_names, start=1):
            json_dict.append({
                "description": f"Scenario_{parent_name}_{sub_name}",
                "id": i,
                "property": sub_name,
                "value": i,
            })
        json.dump(json_dict, f, ensure_ascii=False, indent=4)

    return enum_name


def sync_scenario_parent_enum_files(events):
    """現在のイベント構成に基づき、Scenario_{親}ID enum一式を再生成し、
    存在しなくなった親のenumフォルダは削除する(項目6: 追加・削除に自動追従)。
    さらに assets.py の LoadSingle 群と同様に、親ごとの開始ラッパー関数
    (Scenario_{親}())を ScenarioParentUtils.cs へまとめて生成する
    (シナリオマネージャーコアの ScenarioExecuteUpdate を呼び出すだけの薄いラッパー)。
    """
    os.makedirs(ENUM_DIR, exist_ok=True)
    expected_dirs = set()
    wrapper_lines = []

    for ev in events:
        parent_name = ev['parent']
        sub_names = ev.get('subs', [])
        if not sub_names:
            continue
        enum_name = generate_scenario_parent_enum_csharp(parent_name, sub_names)
        expected_dirs.add(f"Scenario_{parent_name}")

        # Scenario_{親}() ラッパー(assets.pyのLoadSingle群と同じ考え方:
        # ローカルenumの値からサブ名を求めてScenarioManagerCoreへ委譲する)
        wrapper_lines.append(f"        // {parent_name}")
        wrapper_lines.append(f"        public static async UniTask Scenario_{parent_name}(")
        wrapper_lines.append(f"            this ScenarioManagerCore core,")
        wrapper_lines.append(f"            {enum_name}ID sub = {enum_name}ID.{sub_names[0]},")
        wrapper_lines.append(f"            bool addressable = false,")
        wrapper_lines.append(f"            Action<ScenarioExecuteData> action = null,")
        wrapper_lines.append(f"            CancellationTokenSource cts = null)")
        wrapper_lines.append("        {")
        wrapper_lines.append(f"            var subName = _{enum_name}IDToName(sub);")
        wrapper_lines.append(f"            await core.ScenarioExecuteUpdate(\"{parent_name}\", subName, addressable, action, cts);")
        wrapper_lines.append("        }")
        wrapper_lines.append("")
        wrapper_lines.append(f"        private static string _{enum_name}IDToName({enum_name}ID id)")
        wrapper_lines.append("        {")
        wrapper_lines.append("            switch (id)")
        wrapper_lines.append("            {")
        for sub_name in sub_names:
            wrapper_lines.append(f"                case {enum_name}ID.{sub_name}: return \"{sub_name}\";")
        wrapper_lines.append("                default: return string.Empty;")
        wrapper_lines.append("            }")
        wrapper_lines.append("        }")
        wrapper_lines.append("")

    # 存在しなくなった親のenumフォルダを削除(項目6: 削除への追従)
    if os.path.isdir(ENUM_DIR):
        for entry in os.listdir(ENUM_DIR):
            if entry.startswith("Scenario_") and entry not in expected_dirs:
                entry_path = os.path.join(ENUM_DIR, entry)
                if os.path.isdir(entry_path):
                    shutil.rmtree(entry_path)

    # ScenarioParentUtils.cs(Scenario_{親}()ラッパー群)を生成
    scenario_root_dir = os.path.join(DATA_DIR, 'scenario', 'scenario_event_data')
    os.makedirs(scenario_root_dir, exist_ok=True)
    utils_content = "using System;\n"
    utils_content += "using System.Threading;\n"
    utils_content += "using Cysharp.Threading.Tasks;\n"
    utils_content += "using GameCore.Enums;\n\n"
    utils_content += "namespace GameCore.Scenario\n{\n"
    utils_content += "    // sync-scenario実行のたびに再生成される。手動編集は反映されないので注意。\n"
    utils_content += "    public static class ScenarioParentUtils\n    {\n"
    utils_content += "\n".join(wrapper_lines)
    utils_content += "\n    }\n}\n"
    with open(os.path.join(scenario_root_dir, "ScenarioParentUtils.cs"), 'w', encoding='utf-8') as f:
        f.write(utils_content)


def _remove_class_data_id_entry_files(name):
    """class_data_id配下の {name}/ ディレクトリ(Row.cs/Table.cs/TableID.cs/bytes等一式)を削除する。"""
    entry_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, name)
    if os.path.isdir(entry_dir):
        shutil.rmtree(entry_dir)


def sync_scenario_class_data_ids_core(events):
    """events: [{ "name": str, "parent": str(event id), "subs": [str, ...] }, ...] を受け取り、
    ClassDataID側のScenarioタグ配下(Scenario_{親}エントリ)を追従させる実処理本体。
    Flaskのrequestに依存しないので、HTTP経由でもapp.py/scenario.py側からの直接呼び出しでも使える。

    やること:
    - イベントの識別は表示名ではなく id(ev['parent'])で行う。これにより
      親イベントの「名前変更」を「削除+新規追加」ではなく正しく「リネーム」として扱える。
    - 存在しなくなった親イベントのエントリは、class_data_id_list.jsonからもファイル一式からも削除する。
    - サブイベントの追加・削除・並び替えを含め、既存エントリも毎回JSONを再同期する。
    - 同期後、そのScenario_{親}エントリのRow.cs/Table.cs/TableID.cs(+py/js)とバイナリ(.bytes)を
      その場で自動的に再生成する(手動でC#生成ボタンを押さなくても常に最新になる)。
    """
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_ID)
    os.makedirs(tags_dir, exist_ok=True)
    list_path = os.path.join(tags_dir, 'class_data_id_list.json')

    # Scenarioタグ・ScenarioMainサブタグの存在を保証(初回のみ既定値を設定)
    _ensure_scenario_tag()

    try:
        with open(list_path, 'r', encoding='utf-8') as f:
            items = json.load(f)
    except FileNotFoundError:
        items = []

    # event_id(=ev['parent']) -> {"item_name":..., "name":..., "subs":[...]}
    wanted_by_id = {
        ev['parent']: {
            "item_name": f"Scenario_{ev['name']}",
            "name": ev['name'],
            "subs": ev.get('subs', []),
        }
        for ev in events
    }

    def is_scenario_item(item):
        return item.get('tag') == SCENARIO_TAG_NAME and item.get('name') != 'ScenarioEvent'

    # --- 既存Scenario系エントリのうち、scenario_event_id が未付与のもの(旧仕様で
    #     作られたエントリ)を、名前の一致で可能な限り自己修復する ---
    used_ids = {item.get('scenario_event_id') for item in items if is_scenario_item(item)}
    for item in items:
        if not is_scenario_item(item) or item.get('scenario_event_id') is not None:
            continue
        for ev_id, wanted in wanted_by_id.items():
            if ev_id in used_ids:
                continue
            if item.get('name') == wanted['item_name']:
                item['scenario_event_id'] = ev_id
                used_ids.add(ev_id)
                break

    # --- 存在しなくなった親イベントのエントリを削除(リネーム/削除への追従) ---
    removed = []
    kept_items = []
    for item in items:
        if is_scenario_item(item) and item.get('scenario_event_id') is not None and item['scenario_event_id'] not in wanted_by_id:
            _remove_class_data_id_entry_files(item['name'])
            removed.append(item['name'])
            continue
        kept_items.append(item)
    items = kept_items

    # --- リネーム検出: scenario_event_id は一致するが name が変わっている ---
    renamed = []
    by_event_id = {item.get('scenario_event_id'): item for item in items if is_scenario_item(item) and item.get('scenario_event_id') is not None}
    for ev_id, wanted in wanted_by_id.items():
        item = by_event_id.get(ev_id)
        if item is not None and item['name'] != wanted['item_name']:
            _remove_class_data_id_entry_files(item['name'])  # 旧名のRow/Table/バイナリ一式を削除
            renamed.append((item['name'], wanted['item_name']))
            item['name'] = wanted['item_name']

    # --- 新規イベント分のエントリを追加 ---
    existing_ids_in_use = {item.get('scenario_event_id') for item in items if is_scenario_item(item)}
    max_id = max([item.get('id', 0) for item in items], default=0)
    created = []
    for ev_id, wanted in wanted_by_id.items():
        if ev_id in existing_ids_in_use:
            continue
        max_id += 1
        items.append({
            "name": wanted['item_name'],
            "id": max_id,
            "tag": SCENARIO_TAG_NAME,
            "subgroup": SCENARIO_SUB_NAME,
            "scenario_event_id": ev_id,
        })
        created.append(wanted['item_name'])

    # --- 全Scenario_{親}エントリのJSON/Row.cs/Table.cs/TableID.cs/バイナリを再同期・再生成 ---
    for item in items:
        if not is_scenario_item(item):
            continue
        wanted = wanted_by_id.get(item.get('scenario_event_id'))
        if wanted is None:
            continue
        data = sync_scenario_class_data_ids_from_details(wanted['name'], wanted['subs'], item['name'])
        generate_class_data_id_cs_core(item['name'], data['columns'], data['rows'])
        generate_binary_core(item['name'], data['columns'], data['rows'])

    with open(list_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    # 親ごとの Scenario_{親}ID enum と、Scenario_{親}() 開始ラッパー関数を同期・再生成する。
    sync_scenario_parent_enum_files(events)

    # タグ/サブグループ単位の一括Load/Unload util(TableIdUtils.cs)も併せて最新化する。
    try:
        generate_tags_load_script()
    except Exception as e:
        logger.warning(f"TableIdUtils.cs再生成をスキップしました: {e}")

    return {"created": created, "removed": removed, "renamed": renamed}


def reorder_scenario_class_data_ids(events):
    """class_data_id_list.json のid採番を、以下の方針で並び替える:

      1. Scenario関連(タグ=Scenario のエントリ、および name="ScenarioEvent")以外の
         既存IDは、元の並び順(現在のid昇順)を保ったまま 1 から詰めてインクリメント
      2. その直後に ScenarioEvent
      3. その後ろに 各Scenarioグループ(Scenario_{親})を、イベント登録順(eventsの順序)で並べる

    シナリオの追加・編集・削除の度に呼ばれる想定(sync_scenario_class_data_ids_core と
    セットで使う)。
    """
    list_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json')
    try:
        with open(list_path, 'r', encoding='utf-8') as f:
            items = json.load(f)
    except FileNotFoundError:
        return

    def is_scenario_group_item(item):
        return item.get('tag') == SCENARIO_TAG_NAME and item.get('name') != 'ScenarioEvent'

    others = [item for item in items if not is_scenario_group_item(item) and item.get('name') != 'ScenarioEvent']
    others.sort(key=lambda item: item.get('id', 0))  # 元の並び順を保持

    scenario_event_item = next((item for item in items if item.get('name') == 'ScenarioEvent'), None)

    scenario_items_by_name = {item['name']: item for item in items if is_scenario_group_item(item)}
    ordered_scenario_items = []
    for ev in events:
        item = scenario_items_by_name.pop(f"Scenario_{ev['name']}", None)
        if item is not None:
            ordered_scenario_items.append(item)
    # eventsに載っていない(想定外の)Scenarioエントリが残っていれば、末尾に元順で保持しておく
    if scenario_items_by_name:
        leftovers = list(scenario_items_by_name.values())
        leftovers.sort(key=lambda item: item.get('id', 0))
        ordered_scenario_items.extend(leftovers)

    new_order = list(others)
    if scenario_event_item is not None:
        new_order.append(scenario_event_item)
    new_order.extend(ordered_scenario_items)

    for i, item in enumerate(new_order, start=1):
        item['id'] = i

    with open(list_path, 'w', encoding='utf-8') as f:
        json.dump(new_order, f, ensure_ascii=False, indent=2)

def sync_scenario_class_data_ids_from_details(name,details_event,event):

    #クラスパスを取得
    class_id_path = os.path.join(DATA_DIR, CLASS_DATA_ID,event)
    #フォルダを作成
    os.makedirs(class_id_path,exist_ok=True)
    
    data = {
    "columns": [],
    "rows": []
    }

    data["columns"].append({ "type": "ScenarioEvent", "name": "scenario_id", "description": "シナリオのID", "options": {} })
    
    count = 1
    for details in details_event:
        
        data["rows"].append(
            {
                "id" : count,
                "enum_property": details,
                "description": "",
                "data": {
                "scenario_id": {
                    "value": f"ScenarioEventID.{name}_{details}",
                    "type": "ScenarioEvent"
                    }
                } 
            }
        )
        count += 1
    

    class_id_path_json = os.path.join(class_id_path,f"{event}.json")
    with open(class_id_path_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return data

        




def sync_scenario_class_data_ids_from_scenario_events(scenario_events):
    """scenario_event_list.json そのままの形([{ "id":..., "subEvents":[{"name":...}] }, ...])を
    受け取れる薄いラッパー。app.py側の親/サブ追加・削除ハンドラから、その場で
    直接この関数を呼び出すだけで同期できる(HTTPを経由しない)。
    親の識別には id(URLやディレクトリ名にも使われている一意な値)を使う。
    """
    events = [
        {
            "name":ev["name"],
            "parent": ev["id"],
            "subs": [sub["name"] for sub in ev.get("subEvents", [])],
        }
        for ev in scenario_events
    ]
    return sync_scenario_class_data_ids_core(events)


@bp.route('/api/class-data-id/sync-scenario', methods=['POST'])
def sync_scenario_class_data_ids():
    """シナリオイベント(親/サブ)の現在の構成を受け取り、ClassDataID側の
    Scenario タグ配下(Scenario_{親}サブグループ・Scenario_{親}_{サブ}エントリ)を
    追従させる(項目6: イベント追加・削除時の自動更新)。HTTP経由での呼び出し用。
    app.py側から直接呼ぶ場合は sync_scenario_class_data_ids_from_scenario_events を使う。

    request body:
    {
        "events": [
            { "parent": "Opening", "subs": ["Intro", "Meeting"] },
            { "parent": "Ending",  "subs": ["Good", "Bad"] }
        ]
    }
    """
    try:
        events = (request.get_json() or {}).get('events', [])
        result = sync_scenario_class_data_ids_core(events)
        reorder_scenario_class_data_ids(events)
        return jsonify({
            "message": "Scenario用ClassDataIDを同期しました",
            **result,
        }), 200
    except Exception as e:
        logger.error(f"Scenario ClassDataID同期エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500



def generate_tags_load_script():
    """tags.json / class_data_id_list.json をもとに、タグ単位・サブグループ単位の
    一括ロード/アンロードutilと、ClassDataID単体(複数まとめても可)のシングル
    ロード/アンロードutilをまとめて TableIdUtils.cs に生成する。"""
    tags_path = os.path.join(DATA_DIR, CLASS_DATA_ID, 'tags.json')
    try:
        tags = []
        with open(tags_path, 'r', encoding='utf-8') as f:
            tags = json.load(f)
            
        class_data_id_list = []
        with open(os.path.join(DATA_DIR, CLASS_DATA_ID, 'class_data_id_list.json'), 'r', encoding='utf-8') as f:
            class_data_id_list = json.load(f)

        # ------------------------------------------------------------
        # 重複処理の削減(項目9): Load/Unloadの同期・非同期4メソッドを
        # 1か所で組み立てる共通ヘルパー。タグ単位・サブグループ単位どちらも
        # これを通す。
        # ------------------------------------------------------------
        def build_bulk_block(suffix, item_names):
            lines = []
            indent = 0

            def add(text=""):
                lines.append("    " * indent + text)

            # 非同期ロード
            add(f"public static async UniTask LoadAsync{suffix}(Action action = null)")
            add("{")
            indent += 1
            add("await ClassDataIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
            add("{")
            indent += 1
            for item_name in item_names:
                add(f"header.GetData<GameCore.Tables.{item_name}Table>(GameCore.Enums.TableID.{item_name}, reader);")
                add("await UniTask.Yield();")
            add("action?.Invoke();")
            add("await UniTask.CompletedTask;")
            indent -= 1
            add("});")
            indent -= 1
            add("}")
            add()

            # 同期ロード
            add(f"public static void Load{suffix}(Action action = null)")
            add("{")
            indent += 1
            add("UniTask.Action(async () =>")
            add("{")
            indent += 1
            add("await ClassDataIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
            add("{")
            indent += 1
            for item_name in item_names:
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

            # 非同期アンロード(新規)
            add(f"public static async UniTask UnloadAsync{suffix}(Action action = null)")
            add("{")
            indent += 1
            for item_name in item_names:
                add(f"ClassDataIDCore.Instance.UnloadClassData(GameCore.Enums.TableID.{item_name});")
                add("await UniTask.Yield();")
            add("action?.Invoke();")
            add("await UniTask.CompletedTask;")
            indent -= 1
            add("}")
            add()

            # 同期アンロード(新規)
            #add(f"public static void Unload{suffix}(Action action = null)")
            #add("{")
            #indent += 1
            #for item_name in item_names:
            #    add(f"ClassDataIDCore.Instance.UnloadClassData(GameCore.Enums.TableID.{item_name});")
            #add("action?.Invoke();")
            #indent -= 1
            #add("}")
            #add()

            return lines

        all_blocks = []

        for tag in tags:
            tag_name = tag["name"]
            tag_items = [
                item["name"] for item in class_data_id_list
                if item.get("tag") == tag_name
            ]
            # タグ全体(サブグループ問わず全部)
            all_blocks += build_bulk_block(tag_name, tag_items)

            # サブグループ単位(項目: サブグループ単位でのロード、アンロード)
            for sub_name in tag.get('subgroups', []):
                sub_items = [
                    item["name"] for item in class_data_id_list
                    if item.get("tag") == tag_name and item.get("subgroup") == sub_name
                ]
                all_blocks += build_bulk_block(f"{tag_name}_{sub_name}", sub_items)

        # ------------------------------------------------------------
        # シングルロード/アンロード(項目: シングルロード・アンロード)。
        # ClassDataID 1件のみのオーバーロードに加え、配列引数で複数件を
        # 一括ロード/アンロードできるオーバーロードも生成する。
        # 各テーブルはgenerate_binaryで書き込んだ行オフセットテーブルを使い、
        # 該当行だけシークして読み込む想定(ClassDataIDCore側でTableID→
        # ファイルパス解決とシーク読み込みを行う)。
        # ------------------------------------------------------------
        single_lines = []
        indent = 0

        def add_single(text=""):
            single_lines.append("    " * indent + text)

        add_single("public static async UniTask LoadSingleAsync(GameCore.Enums.TableID id, Action action = null)")
        add_single("{")
        indent += 1
        add_single("await ClassDataIDCore.Instance.LoadClassDataSingleAsync(id);")
        add_single("action?.Invoke();")
        indent -= 1
        add_single("}")
        add_single()

        add_single("public static async UniTask LoadSingleAsync(GameCore.Enums.TableID[] ids, Action action = null)")
        add_single("{")
        indent += 1
        add_single("foreach (var id in ids)")
        add_single("{")
        indent += 1
        add_single("await ClassDataIDCore.Instance.LoadClassDataSingleAsync(id);")
        add_single("await UniTask.Yield();")
        indent -= 1
        add_single("}")
        add_single("action?.Invoke();")
        indent -= 1
        add_single("}")
        add_single()

        add_single("public static void LoadSingle(GameCore.Enums.TableID id, Action action = null)")
        add_single("{")
        indent += 1
        add_single("UniTask.Action(async () => { await LoadSingleAsync(id, action); }).Invoke();")
        indent -= 1
        add_single("}")
        add_single()

        add_single("public static void LoadSingle(GameCore.Enums.TableID[] ids, Action action = null)")
        add_single("{")
        indent += 1
        add_single("UniTask.Action(async () => { await LoadSingleAsync(ids, action); }).Invoke();")
        indent -= 1
        add_single("}")
        add_single()

        add_single("public static async UniTask UnloadSingleAsync(GameCore.Enums.TableID id, Action action = null)")
        add_single("{")
        indent += 1
        add_single("ClassDataIDCore.Instance.UnloadClassData(id);")
        add_single("action?.Invoke();")
        add_single("await UniTask.CompletedTask;")
        indent -= 1
        add_single("}")
        add_single()

        add_single("public static async UniTask UnloadSingleAsync(GameCore.Enums.TableID[] ids, Action action = null)")
        add_single("{")
        indent += 1
        add_single("foreach (var id in ids)")
        add_single("{")
        indent += 1
        add_single("ClassDataIDCore.Instance.UnloadClassData(id);")
        add_single("await UniTask.Yield();")
        indent -= 1
        add_single("}")
        add_single("action?.Invoke();")
        indent -= 1
        add_single("}")
        add_single()

        add_single("public static void UnloadSingle(GameCore.Enums.TableID id, Action action = null)")
        add_single("{")
        indent += 1
        add_single("ClassDataIDCore.Instance.UnloadClassData(id);")
        add_single("action?.Invoke();")
        indent -= 1
        add_single("}")
        add_single()

        add_single("public static void UnloadSingle(GameCore.Enums.TableID[] ids, Action action = null)")
        add_single("{")
        indent += 1
        add_single("foreach (var id in ids) ClassDataIDCore.Instance.UnloadClassData(id);")
        add_single("action?.Invoke();")
        indent -= 1
        add_single("}")
        add_single()

        all_blocks += single_lines

        append_str = "\n".join(all_blocks)
        
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





def generate_base(data_dir):
    """
    ClassDataID 用のボイラープレート生成（初回起動時のみ）。
    - class_data_id_list.json の初期化
    - BaseClassDataRow / BaseClassDataRowIndex / ClassDataReferenceLoader / BaseClassDataID / BaseTable (.cs/.py/.js)
    - ClassDataIDCore.cs
    - TableID.cs
    """
    os.makedirs(os.path.join(data_dir, CLASS_DATA_ID), exist_ok=True)

    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_ID, "class_data_id_list.json")):
        with open(os.path.join(data_dir, CLASS_DATA_ID, "class_data_id_list.json"), 'w', encoding='utf-8') as f:
            json.dump([], f)

    # BaseClassDataRow.cs を生成
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_ID, "BaseClassDataRow.cs")):
        code_str = """
    using System.IO;
    using System.Collections.Generic;
    using GameCore.Enums;

    namespace GameCore.Tables
    {
        public abstract class BaseClassDataRow
        {
            public abstract void Read(int id,BinaryReader reader);

            /// <summary>
            /// この行が参照している他のclass_data_idの(TableID, 参照先id)一覧。
            /// 参照フィールドを持つテーブルでは自動生成コード側でoverrideされる。デフォルトは空。
            /// </summary>
            public virtual List<(TableID TableId, int RefId)> GetReferencedIds()
            {
                return new List<(TableID, int)>();
            }
        }
    }
    """
        with open(os.path.join(data_dir, CLASS_DATA_ID, "BaseClassDataRow.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")

    # BaseClassDataRowIndex.cs を生成（テーブル内の各id=各行のシーク位置を保持する基礎クラス）
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_ID, "BaseClassDataRowIndex.cs")):
        code_str = """
    using System.IO;
    using System;
    using System.Collections.Generic;

    namespace GameCore.Tables
    {
        // テーブル内の各行(id)ごとの[Offset(テーブル先頭からの相対位置), Size]を保持する。
        // 各テーブルの{Name}RowIndexはこのクラスを継承して生成される。
        public abstract class BaseClassDataRowIndex<T> where T : Enum
        {
            public Dictionary<T, (long Offset, int Size)> Entries = new Dictionary<T, (long, int)>();
            public bool IsRead { get; private set; }

            // reader は「行インデックスブロックの先頭」に位置している前提。
            // forceReload=true でデバッグ用に読み直しできる。
            public void Read(BinaryReader reader, bool forceReload = false)
            {
                if (IsRead && !forceReload) return;
                Entries.Clear();
                int count = reader.ReadInt32();
                for (int i = 0; i < count; i++)
                {
                    int idVal = reader.ReadInt32();
                    T id = (T)Enum.ToObject(typeof(T), idVal);
                    long offset = reader.ReadInt64();
                    int size = reader.ReadInt32();
                    Entries[id] = (offset, size);
                }
                IsRead = true;
            }
        }
    }
    """
        with open(os.path.join(data_dir, CLASS_DATA_ID, "BaseClassDataRowIndex.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")

    # ClassDataReferenceLoader.cs を生成
    # 依存先(参照先)プリロード用の自己登録レジストリ。
    # 各{Name}Tableの静的コンストラクタが自分自身のTableIdに対するローダーをここへ登録する。
    # ID側もMatrix側も、行(またはセル)が持つ「参照先id」を実際にロードする際にこのレジストリを経由する。
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_ID, "ClassDataReferenceLoader.cs")):
        code_str = """
    using System.IO;
    using System;
    using System.Collections.Generic;
    using GameCore.Enums;

    namespace GameCore.Tables
    {
        public static class ClassDataReferenceLoader
        {
            // (参照先id, header, reader, preloadReferences, forceReloadIndex, 循環参照防止用visited)
            public delegate void LoadOneDelegate(int refId, ClassDataHeader header, BinaryReader reader, bool preloadReferences, bool forceReloadIndex, HashSet<(TableID, int)> visited);

            public static readonly Dictionary<TableID, LoadOneDelegate> Loaders = new Dictionary<TableID, LoadOneDelegate>();
        }
    }
    """
        with open(os.path.join(data_dir, CLASS_DATA_ID, "ClassDataReferenceLoader.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")

    # BaseClassDataID.cs を生成
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_ID, "BaseClassDataID.cs")):
        code_str = """
    using System.IO;
    using System;
    using System.Collections.Generic;
    using GameCore.Enums;

    namespace GameCore.Tables
    {
        public abstract class BaseClassDataID<T,E> : BaseTable where T : Enum where E : BaseClassDataRow, new()
        {
            public static Dictionary<T,E> Table = new Dictionary<T,E>();

            // 各テーブルの静的コンストラクタで {Name}RowIndex と TableId がセットされる
            protected static BaseClassDataRowIndex<T> RowIndex;
            protected static TableID TableId;

            public override abstract void Read(BinaryReader reader);
            public override void Release()
            {
                Table.Clear();
            }

            /// <summary>
            /// 依存先プリロードのレジストリに自分自身を登録する。各テーブルの静的コンストラクタから呼ぶこと。
            /// </summary>
            protected static void RegisterReferenceLoader()
            {
                ClassDataReferenceLoader.Loaders[TableId] = (refId, header, reader, preloadReferences, forceReloadIndex, visited) =>
                {
                    T typedId = (T)Enum.ToObject(typeof(T), refId);
                    ReadOneInternal(typedId, header, reader, preloadReferences, forceReloadIndex, visited);
                };
            }

            /// <summary>
            /// 行インデックス（idごとのシーク位置）だけを読み込む。既に読み込み済みならスキップ（forceReload=trueで再読み込み）。
            /// </summary>
            protected static void EnsureRowIndexLoaded(BinaryReader reader, long tableBaseOffset, bool forceReload = false)
            {
                if (RowIndex.IsRead && !forceReload) return;

                reader.BaseStream.Seek(tableBaseOffset, SeekOrigin.Begin);
                int rowCount = reader.ReadInt32();
                int colCount = reader.ReadInt32();
                for (int i = 0; i < colCount; i++)
                {
                    int nameLen = reader.ReadInt32();
                    reader.ReadBytes(nameLen);
                    int typeLen = reader.ReadInt32();
                    reader.ReadBytes(typeLen);
                }
                // ここでreaderは行インデックスブロックの先頭に位置している
                RowIndex.Read(reader, forceReload);
            }

            /// <summary>
            /// 実際に1行読み込む内部処理。preloadReferences=trueの場合、この行が参照している他テーブルのidも
            /// (ネストして)連鎖的にロードする。visitedで循環参照を防ぐ。
            /// </summary>
            private static void ReadOneInternal(T id, ClassDataHeader header, BinaryReader reader, bool preloadReferences, bool forceReloadIndex, HashSet<(TableID, int)> visited)
            {
                var visitKey = (TableId, Convert.ToInt32(id));
                if (visited.Contains(visitKey)) return; // 循環参照ガード
                visited.Add(visitKey);

                if (!header.Entries.TryGetValue(TableId, out var tableEntry)) return;
                long tableBaseOffset = tableEntry.Offset;

                EnsureRowIndexLoaded(reader, tableBaseOffset, forceReloadIndex);
                if (!RowIndex.Entries.TryGetValue(id, out var entry)) return;

                reader.BaseStream.Seek(tableBaseOffset + entry.Offset, SeekOrigin.Begin);
                reader.ReadInt32(); // 行データ先頭のid(int)を読み飛ばす（idは引数側で分かっているため）
                E row = new E();
                row.Read(Convert.ToInt32(id), reader);
                Table[id] = row;

                if (preloadReferences)
                {
                    foreach (var reference in row.GetReferencedIds())
                    {
                        if (ClassDataReferenceLoader.Loaders.TryGetValue(reference.TableId, out var loader))
                        {
                            loader(reference.RefId, header, reader, true, forceReloadIndex, visited);
                        }
                    }
                }
            }

            /// <summary>
            /// 指定した1つのid(行)だけをロードする。テーブル全体はロードしない。
            /// TableId(マスターのTableID)は各テーブルの静的コンストラクタで既に設定済みのため、呼び出し側は意識しなくてよい。
            /// preloadReferences=trueで、この行が参照している他テーブルのidも(ネストして)連鎖的にロードする。
            /// </summary>
            public static void ReadOne(T id, ClassDataHeader header, BinaryReader reader, bool preloadReferences = false, bool forceReloadIndex = false)
            {
                ReadOneInternal(id, header, reader, preloadReferences, forceReloadIndex, new HashSet<(TableID, int)>());
            }

            /// <summary>
            /// 指定した複数のid(行)だけをロードする。テーブル全体はロードしない。
            /// preloadReferences=trueの場合、バッチ全体で1つのvisitedセットを共有するため、同じ参照先の二重ロードを避けられる。
            /// </summary>
            public static void ReadMany(IEnumerable<T> ids, ClassDataHeader header, BinaryReader reader, bool preloadReferences = false, bool forceReloadIndex = false)
            {
                var visited = new HashSet<(TableID, int)>();
                foreach (var id in ids)
                {
                    ReadOneInternal(id, header, reader, preloadReferences, forceReloadIndex, visited);
                }
            }

            /// <summary>
            /// テーブル全体をロードする（既存のRead(reader)を利用、高速な連続読みはそのまま）。
            /// preloadReferences=trueで、全行が参照している他テーブルのidも(ネストして)連鎖的にロードする。
            /// </summary>
            public virtual void ReadAll(ClassDataHeader header, BinaryReader reader, bool preloadReferences = false)
            {
                Read(reader);
                if (!preloadReferences) return;

                var visited = new HashSet<(TableID, int)>();
                foreach (var id in Table.Keys) visited.Add((TableId, Convert.ToInt32(id)));

                foreach (var row in Table.Values)
                {
                    foreach (var reference in row.GetReferencedIds())
                    {
                        if (ClassDataReferenceLoader.Loaders.TryGetValue(reference.TableId, out var loader))
                        {
                            loader(reference.RefId, header, reader, true, false, visited);
                        }
                    }
                }
            }

            /// <summary>指定した1つのidだけをアンロードする（テーブル全体は消さない）</summary>
            public static void UnloadOne(T id)
            {
                Table.Remove(id);
            }

            /// <summary>指定した複数のidだけをアンロードする（テーブル全体は消さない）</summary>
            public static void UnloadMany(IEnumerable<T> ids)
            {
                foreach (var id in ids) Table.Remove(id);
            }

            /// <summary>条件(predicate)に合致するidを一括アンロードする</summary>
            public static void UnloadWhere(Func<T, E, bool> predicate)
            {
                var keysToRemove = new List<T>();
                foreach (var kv in Table)
                {
                    if (predicate(kv.Key, kv.Value)) keysToRemove.Add(kv.Key);
                }
                foreach (var key in keysToRemove) Table.Remove(key);
            }
        }
    }
    """
        with open(os.path.join(data_dir, CLASS_DATA_ID, "BaseClassDataID.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")
        
    # BaseTable.cs を生成
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_ID, "BaseTable.cs")):
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
        with open(os.path.join(data_dir, CLASS_DATA_ID, "BaseTable.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")



    #ClassDataIDCore.cs 生成
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_ID, "ClassDataIDCore.cs")):
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
        with open(os.path.join(data_dir, CLASS_DATA_ID, "ClassDataIDCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")
        

    #python版 -DataClassID-
    if not os.path.exists(os.path.join(data_dir,CLASS_DATA_ID,"BaseClassDataRow.py")):
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
        with open(os.path.join(data_dir,CLASS_DATA_ID,"BaseClassDataRow.py"), 'w', encoding='utf-8') as f:
            f.write(code)
    if not os.path.exists(os.path.join(data_dir,CLASS_DATA_ID,"BaseTable.py")):
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
        with open(os.path.join(data_dir,CLASS_DATA_ID,"BaseTable.py"), 'w', encoding='utf-8') as f:
            f.write(code)
        
    if not os.path.exists(os.path.join(data_dir,CLASS_DATA_ID,"BaseClassDataID.py")):
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
        with open(os.path.join(data_dir,CLASS_DATA_ID,"BaseClassDataID.py"), 'w', encoding='utf-8') as f:
            f.write(code)
        

    #js版 -DataClassID-
    if not os.path.exists(os.path.join(data_dir,CLASS_DATA_ID,"BaseClassDataID.js")):
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
        with open(os.path.join(data_dir,CLASS_DATA_ID,"BaseClassDataID.js"), 'w', encoding='utf-8') as f:
            f.write(code)
    if not os.path.exists(os.path.join(data_dir,CLASS_DATA_ID,"BaseTable.js")):
        code = """
export class BaseTable {
  read(reader) { throw new Error('read must be implemented'); }
  release() { throw new Error('release must be implemented'); }
}
    """
        with open(os.path.join(data_dir,CLASS_DATA_ID,"BaseTable.js"), 'w', encoding='utf-8') as f:
            f.write(code)

    if not os.path.exists(os.path.join(data_dir,CLASS_DATA_ID,"BaseClassDataRow.js")):
        code = """
export class BaseClassDataRow {
  read(reader) { throw new Error('read must be implemented'); }
  static fromJson(data) { throw new Error('fromJson must be implemented'); }
}
    """
        with open(os.path.join(data_dir,CLASS_DATA_ID,"BaseClassDataRow.js"), 'w', encoding='utf-8') as f:
            f.write(code)
        

    # TableID.cs の事前作成
    table_id_path = os.path.join(data_dir, CLASS_DATA_ID, "TableID.cs")
    if not os.path.exists(table_id_path):
        code_str = """
namespace GameCore.Enums
{
    public enum TableID
    {
        None = 0,
        Max
    }
}
"""
        with open(table_id_path, 'w', encoding='utf-8') as f:
            f.write(code_str)


def register(app, data_dir):
    """app.py から呼び出し、DATA_DIR を設定・ボイラープレート生成した上でルートを登録する。"""
    global DATA_DIR
    DATA_DIR = data_dir
    generate_base(data_dir)
    app.register_blueprint(bp)