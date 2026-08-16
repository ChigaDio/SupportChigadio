# -*- coding: utf-8 -*-
"""
pythonSrc/matrix.py

ClassDataMatrixID（マトリクス形式のテーブルデータ）管理API。
- /api/class-data-matrix-id, /api/class-data-matrix-id/<name>
- /api/generate-class-data-matrix-id/<name>, /api/generate-binary-matrix/<name>
- /api/generate-all-binary-matrix, /api/generate-all-cs-matrix-header
- /api/generate-matrix-table-id, /api/generate-class-data-memory-viewer
- /api/class-data-matrix-id-tags 系（タグ一覧・名称変更・割り当て）

app.py から `pythonSrc.matrix.register(app, DATA_DIR)` を呼び出して有効化する。
"""
import json
import logging
import os
import shutil
import struct
import textwrap
import sys
from math import isnan, isfinite

from flask import Blueprint, jsonify, request

import pythonSrc.customclassdata
import pythonSrc.class_data_id as class_data_id_api
from pythonSrc.constants import CLASS_DATA_MATRIX_ID
from pythonSrc.data_utils import (
    get_type_lists,
    build_custom_type_info,
    generate_csharp_field,
    write_binary_field,
    load_custom_class_data_id_dict,
)

logger = logging.getLogger(__name__)
bp = Blueprint('matrix', __name__)

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

def init(data_dir):
    """app.py から呼び出す初期化関数。"""
    global DATA_DIR
    DATA_DIR = os.path.abspath(data_dir)   


# MatrixID管理
@bp.route('/api/class-data-matrix-id', methods=['GET', 'POST', 'PATCH'])
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

def _iter_all_matrix_table_names():
    list_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json')
    try:
        with open(list_path, 'r', encoding='utf-8') as f:
            items = json.load(f)
        return [item['name'] for item in items if item.get('name')]
    except Exception:
        return []


def _default_value_for_prefill_sync(field_type):
    t = (field_type or '').replace('[]', '')
    if t in ('int', 'uint'):
        return 0
    if t in ('float', 'double'):
        return 0.0
    if t == 'bool':
        return False
    if t == 'string':
        return ''
    return None


def sync_prefill_dependents_matrix(source_name, current_members):
    """仕様書項目5(追記分含む)。あるEnum/ClassDataID(source_name)のメンバー構成(current_members)が
    変わった際、それをprefillSourceName / (keyType+prefillKeys)として参照している全MatrixTableの
    セルデータ(data[row][col][field])を現在のメンバー構成に追従させる。class_data_id.pyの
    sync_prefill_dependentsとロジックは同一だが、行/列グリッド構造(data[rk][ck])を走査する点が異なる。"""
    try:
        class_schemas = class_data_id_api.load_class_schemas()
        for table_name in _iter_all_matrix_table_names():
            file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, table_name, f"{table_name}.json")
            if not os.path.exists(file_path):
                continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    table_data = json.load(f)
            except Exception:
                continue

            fields = table_data.get('fields', [])
            data_grid = table_data.get('data', {})
            changed = False

            for field in fields:
                field_type = (field.get('type') or '')
                field_name = field.get('name')
                options = field.get('options') or {}

                for rk, row_dict in data_grid.items():
                    if not isinstance(row_dict, dict):
                        continue
                    for ck, cell in row_dict.items():
                        if not isinstance(cell, dict):
                            continue
                        field_cell = cell.get(field_name)
                        if not field_cell:
                            continue
                        cell_changed, new_val = class_data_id_api.fix_prefill_in_raw_value(
                            field_cell.get('value'), field_type, options, class_schemas, source_name, current_members
                        )
                        if cell_changed:
                            field_cell['value'] = new_val
                            changed = True

            if changed:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(table_data, f, ensure_ascii=False, indent=2)
                logger.info(f"prefill同期(matrix): {table_name} を {source_name} のメンバー変更に追従させました")
    except Exception as e:
        logger.error(f"prefill同期処理エラー(matrix, source={source_name}): {str(e)}")


@bp.route('/api/class-data-matrix-id/<name>', methods=['GET', 'POST', 'DELETE'])
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
            if isinstance(data, dict) and isinstance(data.get('fields'), list):
                for field in data['fields']:
                    field_type = (field.get('type') or '').replace('[]', '') if isinstance(field, dict) else ''
                    if isinstance(field, dict) and (field_type in ('bit', 'color', 'bezier') or field_type in pythonSrc.customclassdata.NUMERIC_TYPES):
                        pythonSrc.customclassdata._normalize_field_options(field)
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
@bp.route('/api/generate-class-data-matrix-id/<name>', methods=['POST'])
def generate_cs_matrix(name):
    file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f'{name}.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        row_id = json_data['rowId']
        col_id = json_data['colId']
        fields = json_data['fields']
        
        
        
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
        custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)
        if row_id in class_data_id_list or row_id in custom_type_info['custom_class_id_list']:
            row_id += "Table"
        if col_id in class_data_id_list or col_id in custom_type_info['custom_class_id_list']:
            col_id += "Table"    

        # {name}MatrixRow.cs
        row_cs = f"using System.IO;\nusing System;\nusing System.Collections.Generic;\nusing UnityEngine;\nusing GameCore.Enums;\nusing GameCore.Tables.ID;\n\n"
        row_cs += f"namespace GameCore.Tables {{\n    public class {name}MatrixRow : BaseClassDataMatrixRow {{\n"
        # 自分がどのRow/Colに属するセルかを自動保持する(仕様書: RowDataにrowID,colIDを追加してそのTableIDのIDを設定)
        row_cs += "        [SerializeField]\n"
        row_cs += f"        protected {row_id}ID rowId_;\n"
        row_cs += f"        public {row_id}ID RowId {{ get => rowId_; }}\n"
        row_cs += "        [SerializeField]\n"
        row_cs += f"        protected {col_id}ID colId_;\n"
        row_cs += f"        public {col_id}ID ColId {{ get => colId_; }}\n\n"
        read_code = f"        public override void Read(int rowId, int colId, BinaryReader reader) {{\n"
        read_code += f"            rowId_ = ({row_id}ID)rowId;\n"
        read_code += f"            colId_ = ({col_id}ID)colId;\n"
        ref_lines = []  # 依存先プリロード用: 他のclass_data_idを参照しているフィールド
        for field in fields:
            # ★ Matrixのフィールドは "int[]" のような配列サフィックス表記を使うため、
            #   generate_csharp_field が期待する arraySize 方式に変換してから渡す
            field_for_cs = dict(field)
            is_arr_type = isinstance(field.get('type'), str) and field['type'].endswith('[]')
            base_type = field['type'][:-2] if is_arr_type else field['type']
            if is_arr_type:
                field_for_cs['type'] = base_type
                field_for_cs['arraySize'] = -1  # 動的配列(List)として扱う
            else:
                field_for_cs.setdefault('arraySize', 0)
            field_info = generate_csharp_field(field_for_cs, enum_list, class_list, unity_types, basic_types,class_data_id_list)
            row_cs += field_info['field']
            read_code += field_info['read']

            if base_type in class_data_id_list:
                var_name = field['name']
                if is_arr_type:
                    ref_lines.append(
                        f"            foreach (var v in {var_name}) {{ if (v != {base_type}TableID.None) refs.Add((TableID.{base_type}, (int)v)); }}"
                    )
                else:
                    ref_lines.append(
                        f"            if ({var_name} != {base_type}TableID.None) refs.Add((TableID.{base_type}, (int){var_name}));"
                    )
        row_cs += read_code + "        }\n"

        if ref_lines:
            row_cs += "\n        public override List<(TableID TableId, int RefId)> GetReferencedIds() {\n"
            row_cs += "            var refs = new List<(TableID, int)>();\n"
            for line in ref_lines:
                row_cs += line + "\n"
            row_cs += "            return refs;\n"
            row_cs += "        }\n"

        row_cs += "    }\n}\n"
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID,f"{name}", f"{name}MatrixRow.cs"), 'w', encoding='utf-8') as f:
            f.write(row_cs)

        # {name}MatrixRowIndex.cs（基礎クラスBaseClassDataRowIndex<TRow>を継承。rowKeyごとのシーク位置を保持）
        row_index_cs = "using GameCore.Tables.ID;\n\n"
        row_index_cs += "namespace GameCore.Tables {\n"
        row_index_cs += f"    public class {name}MatrixRowIndex : BaseClassDataRowIndex<{row_id}ID> {{\n"
        row_index_cs += "    }\n}\n"
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, f"{name}", f"{name}MatrixRowIndex.cs"), 'w', encoding='utf-8') as f:
            f.write(row_index_cs)

        # {name}MatrixID.cs
        matrix_cs = f"using System.IO;\nusing GameCore.Tables.ID;\nusing GameCore.Enums;\nusing System;\nusing System.Collections.Generic;\nusing Cysharp.Threading.Tasks;\n\n"
        matrix_cs += f"namespace GameCore.Tables {{\n    public class {name}MatrixTable : BaseClassDataMatrixID<{row_id}ID, {col_id}ID, {name}MatrixRow> {{\n"
        matrix_cs += f"        static {name}MatrixTable()\n        {{\n"
        matrix_cs += f"            RowIndex = new {name}MatrixRowIndex();\n"
        matrix_cs += f"            TableId = MatrixTableID.{name};\n"
        matrix_cs += f"            MatrixTableRegistry.Loaders[TableId] = (header, reader) => header.GetData<{name}MatrixTable>(MatrixTableID.{name}, reader);\n"
        matrix_cs += f"            MatrixTableRegistry.Unloaders[TableId] = () => {{ Table.Clear(); s_cellIndexCache.Clear(); }};\n"
        matrix_cs += "        }\n\n"
        matrix_cs += "        public override void Read(BinaryReader reader) {\n"
        matrix_cs += f"            {name}MatrixTable.Table.Clear();\n"
        matrix_cs += f"            int rowCount = reader.ReadInt32();\n"
        matrix_cs += f"            List<{row_id}ID> rowKeys = new List<{row_id}ID>(); for(int i=0; i<rowCount; i++) rowKeys.Add(({row_id}ID)reader.ReadInt32());\n"
        matrix_cs += f"            int colCount = reader.ReadInt32();\n"
        matrix_cs += f"            List<{col_id}ID> colKeys = new List<{col_id}ID>(); for(int i=0; i<colCount; i++) colKeys.Add(({col_id}ID)reader.ReadInt32());\n"
        matrix_cs += f"            s_colKeys = colKeys;\n"
        matrix_cs += f"            RowIndex.Read(reader, true); // 行インデックスブロックを読み進めつつキャッシュしておく（高速な連続読みはそのまま維持）\n"
        matrix_cs += f"            foreach(var rk in rowKeys) {{ Table[rk] = new Dictionary<{col_id}ID, {name}MatrixRow>(); }}\n"
        matrix_cs += "            foreach(var rk in rowKeys) {\n"
        matrix_cs += "                int cellIndexCount = reader.ReadInt32();\n"
        matrix_cs += f"                var cellIndex = new Dictionary<{col_id}ID, (long, int)>();\n"
        matrix_cs += "                for (int i = 0; i < cellIndexCount; i++) {\n"
        matrix_cs += f"                    var cid = ({col_id}ID)Enum.ToObject(typeof({col_id}ID), reader.ReadInt32());\n"
        matrix_cs += "                    long off = reader.ReadInt64();\n"
        matrix_cs += "                    int sz = reader.ReadInt32();\n"
        matrix_cs += "                    cellIndex[cid] = (off, sz);\n"
        matrix_cs += "                }\n"
        matrix_cs += "                s_cellIndexCache[rk] = cellIndex; // 行インデックスブロックはここでキャッシュしておく（列/セル単位の後読みに使う）\n"
        matrix_cs += f"                foreach(var ck in colKeys) {{ var row = new {name}MatrixRow(); row.Read(Convert.ToInt32(rk), Convert.ToInt32(ck), reader); Table[rk][ck] = row; }}\n"
        matrix_cs += "            }\n"
        matrix_cs += "        }\n\n"

        # --- セル/行/列単位のシングルロード・アンロードUtil ---
        # (仕様書: グループ/サブグループ/Single対応。Singleはセル=rowID×colIDを指定する)
        matrix_cs += f"        /// <summary>指定した1セル(rowId×colId)だけをシークして読み込む</summary>\n"
        matrix_cs += f"        public static async UniTask LoadSingleAsync({row_id}ID rowId, {col_id}ID colId, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>\n"
        matrix_cs += "            {\n"
        matrix_cs += "                ReadOneCell(rowId, colId, header, reader, preloadReferences);\n"
        matrix_cs += "                action?.Invoke();\n"
        matrix_cs += "                await UniTask.CompletedTask;\n"
        matrix_cs += "            });\n"
        matrix_cs += "        }\n\n"

        matrix_cs += f"        public static void LoadSingle({row_id}ID rowId, {col_id}ID colId, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "            => UniTask.Action(async () => { await LoadSingleAsync(rowId, colId, preloadReferences, action); }).Invoke();\n\n"

        matrix_cs += f"        /// <summary>指定した複数セル(rowId,colIdの組)だけをシークして読み込む(配列対応)</summary>\n"
        matrix_cs += f"        public static async UniTask LoadSingleAsync(IEnumerable<({row_id}ID Row, {col_id}ID Col)> cells, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>\n"
        matrix_cs += "            {\n"
        matrix_cs += "                ReadManyCells(cells, header, reader, preloadReferences);\n"
        matrix_cs += "                action?.Invoke();\n"
        matrix_cs += "                await UniTask.CompletedTask;\n"
        matrix_cs += "            });\n"
        matrix_cs += "        }\n\n"

        matrix_cs += f"        public static void LoadSingle(IEnumerable<({row_id}ID Row, {col_id}ID Col)> cells, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "            => UniTask.Action(async () => { await LoadSingleAsync(cells, preloadReferences, action); }).Invoke();\n\n"

        matrix_cs += f"        /// <summary>指定した1セルだけをTableから解放する(テーブル全体は解放しない)</summary>\n"
        matrix_cs += f"        public static void UnloadSingle({row_id}ID rowId, {col_id}ID colId, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            UnloadOneCell(rowId, colId);\n"
        matrix_cs += "            action?.Invoke();\n"
        matrix_cs += "        }\n\n"

        matrix_cs += f"        public static async UniTask UnloadSingleAsync({row_id}ID rowId, {col_id}ID colId, Action action = null)\n"
        matrix_cs += "        {\n            UnloadSingle(rowId, colId, action);\n            await UniTask.CompletedTask;\n        }\n\n"

        matrix_cs += f"        /// <summary>指定した複数セルだけをTableから解放する(配列対応)</summary>\n"
        matrix_cs += f"        public static void UnloadSingle(IEnumerable<({row_id}ID Row, {col_id}ID Col)> cells, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            UnloadManyCells(cells);\n"
        matrix_cs += "            action?.Invoke();\n"
        matrix_cs += "        }\n\n"

        matrix_cs += f"        public static async UniTask UnloadSingleAsync(IEnumerable<({row_id}ID Row, {col_id}ID Col)> cells, Action action = null)\n"
        matrix_cs += "        {\n            UnloadSingle(cells, action);\n            await UniTask.CompletedTask;\n        }\n\n"

        # --- セル: 複数行 × 単一列(row[], col) ---
        matrix_cs += f"        /// <summary>複数行 × 単一列のセルだけをシークして読み込む(row[], col)</summary>\n"
        matrix_cs += f"        public static async UniTask LoadSingleAsync(IEnumerable<{row_id}ID> rowIds, {col_id}ID colId, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>\n"
        matrix_cs += "            {\n"
        matrix_cs += f"                var cells = new List<({row_id}ID Row, {col_id}ID Col)>();\n"
        matrix_cs += "                foreach (var rowId in rowIds) cells.Add((rowId, colId));\n"
        matrix_cs += "                ReadManyCells(cells, header, reader, preloadReferences);\n"
        matrix_cs += "                action?.Invoke();\n"
        matrix_cs += "                await UniTask.CompletedTask;\n"
        matrix_cs += "            });\n"
        matrix_cs += "        }\n\n"

        matrix_cs += f"        public static void LoadSingle(IEnumerable<{row_id}ID> rowIds, {col_id}ID colId, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "            => UniTask.Action(async () => { await LoadSingleAsync(rowIds, colId, preloadReferences, action); }).Invoke();\n\n"

        matrix_cs += f"        /// <summary>複数行 × 単一列のセルだけをTableから解放する(row[], col。テーブル全体は解放しない)</summary>\n"
        matrix_cs += f"        public static void UnloadSingle(IEnumerable<{row_id}ID> rowIds, {col_id}ID colId, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            foreach (var rowId in rowIds) UnloadOneCell(rowId, colId);\n"
        matrix_cs += "            action?.Invoke();\n"
        matrix_cs += "        }\n\n"

        matrix_cs += f"        public static async UniTask UnloadSingleAsync(IEnumerable<{row_id}ID> rowIds, {col_id}ID colId, Action action = null)\n"
        matrix_cs += "        {\n            UnloadSingle(rowIds, colId, action);\n            await UniTask.CompletedTask;\n        }\n\n"

        # --- セル: 単一行 × 複数列(row, col[]) ---
        matrix_cs += f"        /// <summary>単一行 × 複数列のセルだけをシークして読み込む(row, col[])</summary>\n"
        matrix_cs += f"        public static async UniTask LoadSingleAsync({row_id}ID rowId, IEnumerable<{col_id}ID> colIds, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>\n"
        matrix_cs += "            {\n"
        matrix_cs += f"                var cells = new List<({row_id}ID Row, {col_id}ID Col)>();\n"
        matrix_cs += "                foreach (var colId in colIds) cells.Add((rowId, colId));\n"
        matrix_cs += "                ReadManyCells(cells, header, reader, preloadReferences);\n"
        matrix_cs += "                action?.Invoke();\n"
        matrix_cs += "                await UniTask.CompletedTask;\n"
        matrix_cs += "            });\n"
        matrix_cs += "        }\n\n"

        matrix_cs += f"        public static void LoadSingle({row_id}ID rowId, IEnumerable<{col_id}ID> colIds, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "            => UniTask.Action(async () => { await LoadSingleAsync(rowId, colIds, preloadReferences, action); }).Invoke();\n\n"

        matrix_cs += f"        /// <summary>単一行 × 複数列のセルだけをTableから解放する(row, col[]。テーブル全体は解放しない)</summary>\n"
        matrix_cs += f"        public static void UnloadSingle({row_id}ID rowId, IEnumerable<{col_id}ID> colIds, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            foreach (var colId in colIds) UnloadOneCell(rowId, colId);\n"
        matrix_cs += "            action?.Invoke();\n"
        matrix_cs += "        }\n\n"

        matrix_cs += f"        public static async UniTask UnloadSingleAsync({row_id}ID rowId, IEnumerable<{col_id}ID> colIds, Action action = null)\n"
        matrix_cs += "        {\n            UnloadSingle(rowId, colIds, action);\n            await UniTask.CompletedTask;\n        }\n\n"

        # --- 行単位(rowだけ・全列) ---
        matrix_cs += f"        public static async UniTask LoadRowAsync({row_id}ID rowId, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>\n"
        matrix_cs += "            {\n"
        matrix_cs += "                ReadOneRow(rowId, header, reader, preloadReferences);\n"
        matrix_cs += "                action?.Invoke();\n"
        matrix_cs += "                await UniTask.CompletedTask;\n"
        matrix_cs += "            });\n"
        matrix_cs += "        }\n\n"
        matrix_cs += f"        public static void LoadRow({row_id}ID rowId, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "            => UniTask.Action(async () => { await LoadRowAsync(rowId, preloadReferences, action); }).Invoke();\n\n"
        matrix_cs += f"        public static void UnloadRow({row_id}ID rowId, Action action = null)\n"
        matrix_cs += "        {\n            UnloadOneRow(rowId);\n            action?.Invoke();\n        }\n\n"
        matrix_cs += f"        public static async UniTask UnloadRowAsync({row_id}ID rowId, Action action = null)\n"
        matrix_cs += "        {\n            UnloadRow(rowId, action);\n            await UniTask.CompletedTask;\n        }\n\n"

        # --- 行単位(複数行・配列対応 row[]) ---
        matrix_cs += f"        /// <summary>複数行(全列)だけをまとめてシークして読み込む(row[])</summary>\n"
        matrix_cs += f"        public static async UniTask LoadRowAsync(IEnumerable<{row_id}ID> rowIds, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>\n"
        matrix_cs += "            {\n"
        matrix_cs += "                foreach (var rowId in rowIds) ReadOneRow(rowId, header, reader, preloadReferences);\n"
        matrix_cs += "                action?.Invoke();\n"
        matrix_cs += "                await UniTask.CompletedTask;\n"
        matrix_cs += "            });\n"
        matrix_cs += "        }\n\n"
        matrix_cs += f"        public static void LoadRow(IEnumerable<{row_id}ID> rowIds, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "            => UniTask.Action(async () => { await LoadRowAsync(rowIds, preloadReferences, action); }).Invoke();\n\n"
        matrix_cs += f"        /// <summary>複数行だけをまとめてTableから解放する(row[]。テーブル全体は解放しない)</summary>\n"
        matrix_cs += f"        public static void UnloadRow(IEnumerable<{row_id}ID> rowIds, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            foreach (var rowId in rowIds) UnloadOneRow(rowId);\n"
        matrix_cs += "            action?.Invoke();\n"
        matrix_cs += "        }\n\n"
        matrix_cs += f"        public static async UniTask UnloadRowAsync(IEnumerable<{row_id}ID> rowIds, Action action = null)\n"
        matrix_cs += "        {\n            UnloadRow(rowIds, action);\n            await UniTask.CompletedTask;\n        }\n\n"

        # --- 列単位(colだけ・全行) ---
        matrix_cs += f"        public static async UniTask LoadColumnAsync({col_id}ID colId, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>\n"
        matrix_cs += "            {\n"
        matrix_cs += "                ReadOneColumn(colId, header, reader, preloadReferences);\n"
        matrix_cs += "                action?.Invoke();\n"
        matrix_cs += "                await UniTask.CompletedTask;\n"
        matrix_cs += "            });\n"
        matrix_cs += "        }\n\n"
        matrix_cs += f"        public static void LoadColumn({col_id}ID colId, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "            => UniTask.Action(async () => { await LoadColumnAsync(colId, preloadReferences, action); }).Invoke();\n\n"
        matrix_cs += f"        public static void UnloadColumn({col_id}ID colId, Action action = null)\n"
        matrix_cs += "        {\n            UnloadOneColumn(colId);\n            action?.Invoke();\n        }\n\n"
        matrix_cs += f"        public static async UniTask UnloadColumnAsync({col_id}ID colId, Action action = null)\n"
        matrix_cs += "        {\n            UnloadColumn(colId, action);\n            await UniTask.CompletedTask;\n        }\n\n"

        # --- 列単位(複数列・配列対応 col[]) ---
        matrix_cs += f"        /// <summary>複数列(全行)だけをまとめてシークして読み込む(col[])</summary>\n"
        matrix_cs += f"        public static async UniTask LoadColumnAsync(IEnumerable<{col_id}ID> colIds, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>\n"
        matrix_cs += "            {\n"
        matrix_cs += "                foreach (var colId in colIds) ReadOneColumn(colId, header, reader, preloadReferences);\n"
        matrix_cs += "                action?.Invoke();\n"
        matrix_cs += "                await UniTask.CompletedTask;\n"
        matrix_cs += "            });\n"
        matrix_cs += "        }\n\n"
        matrix_cs += f"        public static void LoadColumn(IEnumerable<{col_id}ID> colIds, bool preloadReferences = false, Action action = null)\n"
        matrix_cs += "            => UniTask.Action(async () => { await LoadColumnAsync(colIds, preloadReferences, action); }).Invoke();\n\n"
        matrix_cs += f"        /// <summary>複数列だけをまとめてTableから解放する(col[]。テーブル全体は解放しない)</summary>\n"
        matrix_cs += f"        public static void UnloadColumn(IEnumerable<{col_id}ID> colIds, Action action = null)\n"
        matrix_cs += "        {\n"
        matrix_cs += "            foreach (var colId in colIds) UnloadOneColumn(colId);\n"
        matrix_cs += "            action?.Invoke();\n"
        matrix_cs += "        }\n\n"
        matrix_cs += f"        public static async UniTask UnloadColumnAsync(IEnumerable<{col_id}ID> colIds, Action action = null)\n"
        matrix_cs += "        {\n            UnloadColumn(colIds, action);\n            await UniTask.CompletedTask;\n        }\n"

        matrix_cs += "    }\n}\n"
        with open(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID,f"{name}", f"{name}MatrixTable.cs"), 'w', encoding='utf-8') as f:
            f.write(matrix_cs)

        # {name}MatrixExample.cs
        # class_data_id.py側の{name}TableExample.cs(GetRow/ForID/Find等の拡張メソッド群)と同じ考え方で、
        # Matrix向けの拡張メソッド(GetCell/HasCell/Get{name}MatrixRow/Get{name}MatrixCol/FindCell/FindAllCell)を生成する。
        # 注意: {row_id}TableExample.cs / {col_id}TableExample.cs 側で既に
        # `GetRow(this {row_id}TableID id)` という拡張メソッドが生成されているため、
        # 単純に `GetRow` という名前で行アクセス用拡張メソッドを生やすと、同じ
        # namespace(GameCore.Tables)内で拡張メソッド名が衝突し、あいまい参照(CS0121)になる。
        # そのため、Matrix固有の名前(Get{name}MatrixRow / Get{name}MatrixCol)にしている。
        example_cs_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, f"{name}", f"{name}MatrixExample.cs")
        with open(example_cs_path, 'w', encoding='utf-8') as ef:
            template = f"""
using System;
using UnityEngine;
using GameCore.Tables;
using GameCore.Tables.ID;
using System.Collections.Generic;
namespace GameCore.Tables
{{
    public static class {name}MatrixExtensions
    {{
        /// <summary>指定したセル(row×col)のデータを取得する。存在しなければnullを返す</summary>
        public static {name}MatrixRow Get{name}MatrixCell(this {row_id}ID rowId, {col_id}ID colId)
        {{
            var result = {name}MatrixTable.TryGetCell(rowId, colId);
            return result.Found ? result.Data : null;
        }}

        /// <summary>指定したセル(row×col)がTableに存在するかどうかを高速に判定する</summary>
        public static bool Has{name}MatrixCell(this {row_id}ID rowId, {col_id}ID colId)
        {{
            return {name}MatrixTable.TryGetCell(rowId, colId).Found;
        }}

        /// <summary>指定した行(全列)を取得する。行が存在しなければnullを返す
        /// ({row_id}ID側に既に汎用のGetRow拡張メソッドがあるため、{name}Matrix専用の名前にしている)</summary>
        public static Dictionary<{col_id}ID, {name}MatrixRow> Get{name}MatrixRow(this {row_id}ID rowId)
        {{
            return {name}MatrixTable.Table.TryGetValue(rowId, out var rowDict) ? rowDict : null;
        }}

        /// <summary>指定した列(全行)を取得する。列が存在しなければnullを返す
        /// ({col_id}ID側に既に汎用のGetRow拡張メソッドがあるため、{name}Matrix専用の名前にしている)</summary>
        public static Dictionary<{row_id}ID, {name}MatrixRow> Get{name}MatrixCol(this {col_id}ID colId)
        {{
            var result = new Dictionary<{row_id}ID, {name}MatrixRow>();
            foreach (var rowKv in {name}MatrixTable.Table)
            {{
                if (rowKv.Value.TryGetValue(colId, out var cell))
                {{
                    result[rowKv.Key] = cell;
                }}
            }}
            return result.Count > 0 ? result : null;
        }}

        /// <summary>条件(predicate)に合致する全セルを検索する</summary>
        public static List<({row_id}ID Row, {col_id}ID Col, {name}MatrixRow Data)> FindAllCells(Func<{row_id}ID, {col_id}ID, {name}MatrixRow, bool> predicate)
        {{
            if (predicate == null) throw new ArgumentNullException(nameof(predicate));
            var results = new List<({row_id}ID, {col_id}ID, {name}MatrixRow)>();
            foreach (var rowKv in {name}MatrixTable.Table)
            {{
                foreach (var colKv in rowKv.Value)
                {{
                    if (predicate(rowKv.Key, colKv.Key, colKv.Value)) results.Add((rowKv.Key, colKv.Key, colKv.Value));
                }}
            }}
            return results;
        }}

        /// <summary>条件(predicate)に合致する最初のセルを検索する。見つからなければnullを返す</summary>
        public static ({row_id}ID Row, {col_id}ID Col, {name}MatrixRow Data)? FindCell(Func<{row_id}ID, {col_id}ID, {name}MatrixRow, bool> predicate)
        {{
            if (predicate == null) throw new ArgumentNullException(nameof(predicate));
            foreach (var rowKv in {name}MatrixTable.Table)
            {{
                foreach (var colKv in rowKv.Value)
                {{
                    if (predicate(rowKv.Key, colKv.Key, colKv.Value)) return (rowKv.Key, colKv.Key, colKv.Value);
                }}
            }}
            return null;
        }}
    }}
}}
            """
            ef.write(template)

        return jsonify({"message": f"C# generated for {name}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# バイナリ生成
@bp.route('/api/generate-binary-matrix/<name>', methods=['POST'])
def generate_binary_matrix(name):
    file_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, name, f'{name}.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        row_keys = list(json_data['data'].keys())
        col_keys = list(json_data['data'][row_keys[0]].keys()) if row_keys else []
        fields = json_data['fields']
        basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data= get_type_lists()
        custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)
        custom_class_data_id = load_custom_class_data_id_dict(custom_type_info['custom_class_id_list'])

        row_type_id = json_data['rowId'] + 'ID'
        col_type_id = json_data['colId'] + 'ID'

        def resolve_key_id(type_id, key):
            if type_id in enum_data:
                return next((item['id'] for item in enum_data[type_id] if item['property'] == key), 0)
            elif type_id in class_data_id:
                return next((row['id'] for row in class_data_id[type_id]['rows'] if row['enum_property'] == key), 0)
            elif type_id in custom_class_data_id:
                return next((row['id'] for row in custom_class_data_id[type_id]['rows'] if row['enum_property'] == key), 0)
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
                            class_data_id_list, enum_data, class_data_id, class_data,
                            options=field.get('options'), custom_type_info=custom_type_info
                        )

        return jsonify({"message": f"Binary generated for {name}"})
    except Exception as e:
        logger.error(f"Error generating binary matrix for {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500



#バイナリデータ生成
def generate_binary_matrix_data(name, json_data):
    import io

    row_keys = list(json_data['data'].keys())
    col_keys = list(json_data['data'][row_keys[0]].keys()) if row_keys else []
    rowId = json_data['rowId'] + "ID"
    colId = json_data['colId'] + "ID"
    fields = json_data['fields']
    basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id,class_data = get_type_lists()
    custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)
    custom_class_data_id = load_custom_class_data_id_dict(custom_type_info['custom_class_id_list'])

    def resolve_key_id(type_id, key):
        if type_id in enum_data:
            return next((item['id'] for item in enum_data[type_id] if item['property'] == key), 0)
        elif type_id in class_data_id:
            return next((row['id'] for row in class_data_id[type_id]['rows'] if row['enum_property'] == key), 0)
        elif type_id in custom_class_data_id:
            return next((row['id'] for row in custom_class_data_id[type_id]['rows'] if row['enum_property'] == key), 0)
        return 0

    # --- ① ヘッダー部（rowKeys / colKeys）：フォーマットは従来通り ---
    header_buf = io.BytesIO()
    header_buf.write(struct.pack('i', len(row_keys)))
    row_ids = []
    for rk in row_keys:
        rid = resolve_key_id(rowId, rk)
        row_ids.append(rid)
        header_buf.write(struct.pack('i', rid))
    header_buf.write(struct.pack('i', len(col_keys)))
    col_ids = []
    for ck in col_keys:
        cid = resolve_key_id(colId, ck)
        col_ids.append(cid)
        header_buf.write(struct.pack('i', cid))
    header_bytes = header_buf.getvalue()

    # --- ② rowKey(行)ごとに「行ブロック」を作る。行ブロックの中に、さらにcolKeyごとの
    #      セル単位シークインデックス(cellIndex)を埋め込むことで、行単位・列単位・セル単位
    #      いずれの部分ロードにも対応できるようにする。
    #      row_block = [cellIndexCount:4] + (colKeyId:4/offset:8(行ブロック先頭からの相対)/size:4)*colCount
    #                  + セルデータ本体(colKeys順に連結)
    cell_index_header_size = 4
    cell_index_entry_size = 4 + 8 + 4

    row_block_list = []
    for rk in row_keys:
        # まず各セルを個別にシリアライズしてサイズを確定させる
        cell_bytes_list = []
        for ck in col_keys:
            cell = json_data['data'][rk][ck]
            cf = io.BytesIO()
            for field in fields:
                value = cell.get(field['name'])
                write_binary_field(
                    cf, value, field['type'],
                    basic_types, unity_types, enum_list, class_list,
                    class_data_id_list, enum_data, class_data_id, class_data,
                    options=field.get('options'), custom_type_info=custom_type_info
                )
            cell_bytes_list.append(cf.getvalue())

        cell_index_size = cell_index_header_size + cell_index_entry_size * len(col_keys)
        cell_data_base_offset = cell_index_size  # 行ブロック内でのセルデータ開始位置

        cell_index_buf = io.BytesIO()
        cell_index_buf.write(struct.pack('i', len(col_keys)))
        current_cell_offset = cell_data_base_offset
        for cid, cell_bytes in zip(col_ids, cell_bytes_list):
            cell_index_buf.write(struct.pack('i', cid))
            cell_index_buf.write(struct.pack('q', current_cell_offset))
            cell_index_buf.write(struct.pack('i', len(cell_bytes)))
            current_cell_offset += len(cell_bytes)

        row_block_list.append(cell_index_buf.getvalue() + b''.join(cell_bytes_list))

    # --- ③ 行インデックス（rowKeyのid / テーブル先頭からの相対offset / size(行ブロック全体のサイズ)）を追加 ---
    #     構造: [rowIndexCount:4] + (id:4 / offset:8(相対) / size:4) * rowKeyCount
    row_index_header_size = 4
    row_index_entry_size = 4 + 8 + 4
    row_index_size = row_index_header_size + row_index_entry_size * len(row_keys)
    row_data_base_offset = len(header_bytes) + row_index_size

    row_index_buf = io.BytesIO()
    row_index_buf.write(struct.pack('i', len(row_keys)))
    current_offset = row_data_base_offset
    for rid, row_block in zip(row_ids, row_block_list):
        row_index_buf.write(struct.pack('i', rid))
        row_index_buf.write(struct.pack('q', current_offset))
        row_index_buf.write(struct.pack('i', len(row_block)))
        current_offset += len(row_block)

    return bytearray(header_bytes + row_index_buf.getvalue() + b''.join(row_block_list))
#Matrixを一つのバイナリファイルにまとめる
@bp.route('/api/generate-all-binary-matrix', methods=['POST'])
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
@bp.route('/api/generate-all-cs-matrix-header', methods=['POST'])
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
    
if not os.path.exists(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID)):
    os.makedirs(os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID), exist_ok=True)
    
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

@bp.route('/api/generate-matrix-table-id', methods=['POST'])
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


@bp.route('/api/generate-class-data-memory-viewer', methods=['POST'])
def generate_class_data_memory_viewer():
    """
    ロード状況の可視化エディタウィンドウ(ClassDataMemoryViewerWindow.cs)を生成する。
    リフレクションで BaseClassDataID<,> / BaseClassDataMatrixID<,,> を継承する全テーブルを走査し、
    各テーブルの「ロード済み件数/全件数」「概算メモリサイズ(バイナリ上のバイト数の合計)」を一覧表示する。
    """
    try:
        editor_dir = os.path.join(DATA_DIR, "Editor")
        os.makedirs(editor_dir, exist_ok=True)

        code_str = """
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;

namespace GameCore.Tables.Editor
{
    /// <summary>
    /// class_data_id / class_data_matrix_id の各テーブルについて、
    /// ロード済みid数と概算メモリサイズ(バイナリ上のバイト数の合計)を一覧表示するエディタウィンドウ。
    /// </summary>
    public class ClassDataMemoryViewerWindow : EditorWindow
    {
        private class TableInfo
        {
            public string Name;
            public int LoadedCount;
            public int TotalCount;
            public long MemoryBytes;
        }

        private static readonly Color HeaderColor = new Color(0.14f, 0.16f, 0.21f);
        private static readonly Color AccentColor = new Color(0.30f, 0.62f, 0.98f);
        private static readonly Color EmptyBarColor = new Color(0f, 0f, 0f, 0.25f);
        private static readonly Color RowColorA = new Color(1f, 1f, 1f, 0.02f);
        private static readonly Color RowColorB = new Color(1f, 1f, 1f, 0.06f);

        private Vector2 scroll;
        private string search = "";
        private bool showId = true;
        private bool showMatrix = true;
        private bool autoRefresh = true;
        private double lastRefreshTime;

        private List<TableInfo> idTables = new List<TableInfo>();
        private List<TableInfo> matrixTables = new List<TableInfo>();

        [MenuItem("GameCore/Class Data Memory Viewer")]
        public static void Open()
        {
            var window = GetWindow<ClassDataMemoryViewerWindow>("Class Data Memory");
            window.minSize = new Vector2(440, 340);
            window.Refresh();
        }

        private void OnEnable() => Refresh();

        private void OnGUI()
        {
            DrawToolbar();
            EditorGUILayout.Space(4);
            DrawSummary();
            EditorGUILayout.Space(4);

            scroll = EditorGUILayout.BeginScrollView(scroll);
            showId = DrawSection("ID テーブル", showId, idTables);
            EditorGUILayout.Space(8);
            showMatrix = DrawSection("Matrix テーブル", showMatrix, matrixTables);
            EditorGUILayout.EndScrollView();

            if (autoRefresh && EditorApplication.timeSinceStartup - lastRefreshTime > 1.0)
            {
                Refresh();
            }
        }

        private void DrawToolbar()
        {
            EditorGUILayout.BeginHorizontal(EditorStyles.toolbar);
            search = EditorGUILayout.TextField(search, EditorStyles.toolbarSearchField, GUILayout.MinWidth(140));
            if (GUILayout.Button("Refresh", EditorStyles.toolbarButton, GUILayout.Width(64))) Refresh();
            autoRefresh = GUILayout.Toggle(autoRefresh, "Auto", EditorStyles.toolbarButton, GUILayout.Width(50));
            GUILayout.FlexibleSpace();
            EditorGUILayout.EndHorizontal();
        }

        private void DrawSummary()
        {
            long idBytes = idTables.Sum(t => t.MemoryBytes);
            long matrixBytes = matrixTables.Sum(t => t.MemoryBytes);

            var rect = EditorGUILayout.BeginVertical();
            EditorGUI.DrawRect(rect, HeaderColor);
            EditorGUILayout.Space(4);
            EditorGUILayout.BeginHorizontal();
            GUILayout.Space(8);
            var boldStyle = new GUIStyle(EditorStyles.boldLabel) { normal = { textColor = Color.white } };
            GUILayout.Label("ID: " + FormatBytes(idBytes), boldStyle);
            GUILayout.Space(12);
            GUILayout.Label("Matrix: " + FormatBytes(matrixBytes), boldStyle);
            GUILayout.FlexibleSpace();
            var totalStyle = new GUIStyle(boldStyle) { normal = { textColor = AccentColor } };
            GUILayout.Label("Total: " + FormatBytes(idBytes + matrixBytes), totalStyle);
            GUILayout.Space(8);
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.Space(4);
            EditorGUILayout.EndVertical();
        }

        private bool DrawSection(string title, bool expanded, List<TableInfo> tables)
        {
            expanded = EditorGUILayout.Foldout(expanded, title + " (" + tables.Count + ")", true);
            if (!expanded) return expanded;

            int i = 0;
            foreach (var info in tables)
            {
                if (!string.IsNullOrEmpty(search) && info.Name.IndexOf(search, StringComparison.OrdinalIgnoreCase) < 0)
                {
                    continue;
                }

                var rowRect = EditorGUILayout.BeginHorizontal(GUILayout.Height(20));
                EditorGUI.DrawRect(rowRect, (i % 2 == 0) ? RowColorA : RowColorB);

                GUILayout.Label(info.Name, GUILayout.Width(180));

                float ratio = info.TotalCount > 0 ? (float)info.LoadedCount / info.TotalCount : 0f;
                var barRect = GUILayoutUtility.GetRect(80, 16, GUILayout.ExpandWidth(true));
                DrawProgressBar(barRect, ratio, info.LoadedCount + " / " + info.TotalCount);

                GUILayout.Label(FormatBytes(info.MemoryBytes), GUILayout.Width(80));

                EditorGUILayout.EndHorizontal();
                i++;
            }

            if (tables.Count == 0)
            {
                EditorGUILayout.HelpBox("テーブルが見つかりませんでした。", MessageType.Info);
            }

            return expanded;
        }

        private void DrawProgressBar(Rect rect, float value, string label)
        {
            EditorGUI.DrawRect(rect, EmptyBarColor);
            var fillRect = new Rect(rect.x, rect.y, rect.width * Mathf.Clamp01(value), rect.height);
            Color fillColor = value <= 0f ? new Color(0.4f, 0.4f, 0.4f) : Color.Lerp(new Color(0.85f, 0.35f, 0.35f), AccentColor, value);
            EditorGUI.DrawRect(fillRect, fillColor);

            var style = new GUIStyle(EditorStyles.miniLabel) { alignment = TextAnchor.MiddleCenter };
            style.normal.textColor = Color.white;
            GUI.Label(rect, label, style);
        }

        private static string FormatBytes(long bytes)
        {
            if (bytes < 1024) return bytes + " B";
            double kb = bytes / 1024.0;
            if (kb < 1024) return kb.ToString("0.0") + " KB";
            double mb = kb / 1024.0;
            return mb.ToString("0.00") + " MB";
        }

        private void Refresh()
        {
            lastRefreshTime = EditorApplication.timeSinceStartup;
            idTables.Clear();
            matrixTables.Clear();

            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type[] types;
                try { types = asm.GetTypes(); }
                catch { continue; }

                foreach (var type in types)
                {
                    if (type.IsAbstract || type.BaseType == null || !type.BaseType.IsGenericType) continue;

                    string baseName = type.BaseType.GetGenericTypeDefinition().Name;
                    if (baseName.StartsWith("BaseClassDataID"))
                    {
                        var info = BuildIdTableInfo(type);
                        if (info != null) idTables.Add(info);
                    }
                    else if (baseName.StartsWith("BaseClassDataMatrixID"))
                    {
                        var info = BuildMatrixTableInfo(type);
                        if (info != null) matrixTables.Add(info);
                    }
                }
            }

            idTables = idTables.OrderByDescending(t => t.MemoryBytes).ToList();
            matrixTables = matrixTables.OrderByDescending(t => t.MemoryBytes).ToList();
            Repaint();
        }

        private static long GetTupleItem2(object tuple)
        {
            if (tuple == null) return 0;
            var field = tuple.GetType().GetField("Item2");
            return field != null ? Convert.ToInt64(field.GetValue(tuple)) : 0;
        }

        private TableInfo BuildIdTableInfo(Type type)
        {
            var tableField = type.BaseType.GetField("Table", BindingFlags.Public | BindingFlags.Static);
            var rowIndexField = type.BaseType.GetField("RowIndex", BindingFlags.NonPublic | BindingFlags.Static);
            if (tableField == null) return null;

            var table = tableField.GetValue(null) as System.Collections.IDictionary;
            if (table == null) return null;

            int totalCount = 0;
            long memory = 0;
            var rowIndexObj = rowIndexField?.GetValue(null);
            var entries = GetEntriesDictionary(rowIndexObj);
            if (entries != null)
            {
                totalCount = entries.Count;
                foreach (var key in table.Keys)
                {
                    if (entries.Contains(key)) memory += GetTupleItem2(entries[key]);
                }
            }

            return new TableInfo { Name = type.Name, LoadedCount = table.Count, TotalCount = totalCount, MemoryBytes = memory };
        }

        private TableInfo BuildMatrixTableInfo(Type type)
        {
            var tableField = type.BaseType.GetField("Table", BindingFlags.Public | BindingFlags.Static);
            var rowIndexField = type.BaseType.GetField("RowIndex", BindingFlags.NonPublic | BindingFlags.Static);
            var cellIndexCacheField = type.BaseType.GetField("s_cellIndexCache", BindingFlags.NonPublic | BindingFlags.Static);
            if (tableField == null) return null;

            var table = tableField.GetValue(null) as System.Collections.IDictionary;
            if (table == null) return null;

            var cellIndexCache = cellIndexCacheField?.GetValue(null) as System.Collections.IDictionary;
            long memory = 0;

            foreach (var rowKey in table.Keys)
            {
                var rowDict = table[rowKey] as System.Collections.IDictionary;
                if (rowDict == null) continue;

                System.Collections.IDictionary cellIndex = null;
                if (cellIndexCache != null && cellIndexCache.Contains(rowKey))
                {
                    cellIndex = cellIndexCache[rowKey] as System.Collections.IDictionary;
                }

                foreach (var colKey in rowDict.Keys)
                {
                    if (cellIndex != null && cellIndex.Contains(colKey))
                    {
                        memory += GetTupleItem2(cellIndex[colKey]);
                    }
                }
            }

            int totalRowCount = 0;
            var rowIndexObj = rowIndexField?.GetValue(null);
            var entries = GetEntriesDictionary(rowIndexObj);
            if (entries != null) totalRowCount = entries.Count;

            return new TableInfo { Name = type.Name, LoadedCount = table.Count, TotalCount = totalRowCount, MemoryBytes = memory };
        }

        private static System.Collections.IDictionary GetEntriesDictionary(object rowIndexObj)
        {
            if (rowIndexObj == null) return null;
            var entriesField = rowIndexObj.GetType().GetField("Entries", BindingFlags.Public | BindingFlags.Instance);
            return entriesField?.GetValue(rowIndexObj) as System.Collections.IDictionary;
        }
    }
}
"""
        with open(os.path.join(editor_dir, "ClassDataMemoryViewerWindow.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")

        return jsonify({"message": "ClassDataMemoryViewerWindow generated"})
    except Exception as e:
        logger.error(f"Error generating class data memory viewer: {str(e)}")
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

@bp.route('/api/class-data-matrix-id-tags', methods=['GET', 'POST', 'PATCH'])
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


@bp.route('/api/class-data-matrix-id-tags/<int:tag_id>', methods=['PUT'])
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


@bp.route('/api/class-data-matrix-id/<name>/tag', methods=['PUT'])
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

        old_tag = target.get('tag')
        target['tag'] = tag
        # タグを変更した場合、サブグループはそのタグに属さなくなるのでクリアする
        # (旧タグと新タグを比較する。代入後のtargetと比較すると常にFalseになるので注意)
        if target.get('subgroup') and old_tag != tag:
            target['subgroup'] = None
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return jsonify({"message": f"{name} にタグを設定しました", "data": target}), 200
    except FileNotFoundError:
        return jsonify({"error": "class_data_matrix_id_list.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"Matrixタグ割り当てエラー {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# ClassDataMatrixID サブグループ機能(タグ配下の第2階層)。class_data_idと同じ設計。
# tags.json の各タグエントリに "subgroups": [名前, ...] を持たせる。
# class_data_matrix_id_list.json の各エントリは "subgroup": 名前|null を持つ。
# ============================================================
@bp.route('/api/class-data-matrix-id-tags/<int:tag_id>/subgroups', methods=['GET', 'POST'])
def manage_class_data_matrix_id_subgroups(tag_id):
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID)
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
        logger.error(f"Matrixサブグループ作成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/class-data-matrix-id-tags/<int:tag_id>/subgroups/<path:sub_name>', methods=['DELETE'])
def delete_class_data_matrix_id_subgroup(tag_id, sub_name):
    """サブグループを削除する。所属していたエントリはタグ直下(subgroup=null)へ戻す"""
    tags_dir = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID)
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

        list_path = os.path.join(tags_dir, 'class_data_matrix_id_list.json')
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
        logger.error(f"Matrixサブグループ削除エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route('/api/class-data-matrix-id/<name>/subgroup', methods=['PUT'])
def set_class_data_matrix_id_subgroup(name):
    """特定のClassDataMatrixIDエントリにサブグループを割り当てる(subgroup=nullで解除)"""
    list_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'class_data_matrix_id_list.json')
    try:
        subgroup = request.get_json().get('subgroup')

        with open(list_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        target = next((item for item in data if item['name'] == name), None)
        if not target:
            return jsonify({"error": f"ClassDataMatrixID {name} が見つかりません"}), 404

        if subgroup is not None:
            if not target.get('tag'):
                return jsonify({"error": "サブグループを設定するには先にタグを設定してください"}), 400
            tags_path = os.path.join(DATA_DIR, CLASS_DATA_MATRIX_ID, 'tags.json')
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
        return jsonify({"error": "class_data_matrix_id_list.jsonが見つかりません"}), 404
    except Exception as e:
        logger.error(f"Matrixサブグループ割り当てエラー {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500


def generate_matrix_tags_load_script():
    """tags.json / class_data_matrix_id_list.json をもとに、タグ単位・サブグループ単位の
    一括ロード/アンロードutilと、{Name}ごとの専用型(row/col)シングルロード/アンロードutil
    (LoadSingle{Name}(...)。単一セル/行配列×単一列/単一行×列配列/セル配列/行列配列の直積/
    行のみ(行全体)/列のみ(列全体)/行配列のみ(各行全体)/列配列のみ(各列全体)の9パターン対応)
    をまとめて MatrixTableIdUtils.cs に生成する（class_data_idのTableIdUtils側のLoadSingle{Name}
    (idType id, ...)と同じ考え方。ただしMatrixのセルはrow×colの組で特定されるため、汎用の
    GameCore.Tables.MatrixTableIdを引数に取るオーバーロードは廃止し、行・列それぞれの専用型を
    引数に取る形にしている）"""
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

        # ------------------------------------------------------------
        # タグ単位・サブグループ単位、共通の一括ロード/アンロードブロック生成ヘルパー
        # (class_data_idのgenerate_tags_load_scriptのbuild_bulk_blockと同じ考え方)
        # ------------------------------------------------------------
        def build_bulk_block(suffix, item_names):
            lines = []
            indent = 0

            def add(text=""):
                lines.append("    " * indent + text)

            add(f"public static async UniTask LoadAsync{suffix}(Action action = null)")
            add("{")
            indent += 1
            add("await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
            add("{")
            indent += 1
            for item_name in item_names:
                add(f"header.GetData<GameCore.Tables.{item_name}MatrixTable>(GameCore.Tables.MatrixTableID.{item_name}, reader);")
                add("await UniTask.Yield();")
            add("action?.Invoke();")
            add("await UniTask.CompletedTask;")
            indent -= 1
            add("});")
            indent -= 1
            add("}")
            add()

            add(f"public static void Load{suffix}(Action action = null)")
            add("{")
            indent += 1
            add("UniTask.Action(async () =>")
            add("{")
            indent += 1
            add("await ClassDataMatrixIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
            add("{")
            indent += 1
            for item_name in item_names:
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

            # アンロード(タグ/サブグループ全体をまとめて解放)
            add(f"public static void Unload{suffix}(Action action = null)")
            add("{")
            indent += 1
            for item_name in item_names:
                add(f"ClassDataMatrixIDCore.Instance.UnloadClassData(GameCore.Tables.MatrixTableID.{item_name});")
            add("action?.Invoke();")
            indent -= 1
            add("}")
            add()

            return lines

        all_blocks = []

        for tag in tags:
            tag_name = tag["name"]
            tag_items = [
                item["name"] for item in matrix_list
                if item.get("tag") == tag_name
            ]
            # タグ全体(サブグループ問わず全部)
            all_blocks += build_bulk_block(tag_name, tag_items)

            # サブグループ単位
            for sub_name in tag.get('subgroups', []):
                sub_items = [
                    item["name"] for item in matrix_list
                    if item.get("tag") == tag_name and item.get("subgroup") == sub_name
                ]
                all_blocks += build_bulk_block(f"{tag_name}_{sub_name}", sub_items)

        # ------------------------------------------------------------
        # {name}ごとの専用型シングルロード/アンロード。
        # class_data_id.py の LoadSingle{Name}({Name}TableID id, ...) と同じ考え方だが、
        # Matrixのセルは(row, col)の組で特定されるため、行・列それぞれの専用型を引数に取る
        # (汎用のGameCore.Tables.MatrixTableIdを引数に取るオーバーロードは廃止し、
        #  呼び出し側が取り違えないよう、行・列の型がそのままシグネチャに出る形にした)。
        # 単体セルだけでなく、行/列を配列にした場合や、片方を省略した場合(行/列全体)の
        # 組み合わせパターンをまとめてオーバーロード生成する。実体は各{Name}MatrixTable.cs側の
        # LoadSingleAsync/LoadRowAsync/LoadColumnAsync/UnloadSingle/UnloadRow/UnloadColumnへ委譲するだけ。
        #
        #   1. (row, col)              : 単一セル
        #   2. (row[], col)             : 複数行 × 単一列のセル
        #   3. (row, col[])             : 単一行 × 複数列のセル
        #   4. (cells: (row,col)[])     : 行・列を組で指定した複数セル
        #   5. (row[], col[])           : 複数行 × 複数列の全組み合わせセル(直積)
        #   6. (row)                    : colを指定しない → その1行全体
        #   7. (col)                    : rowを指定しない → その1列全体
        #   8. (row[])                  : colを指定しない → 各行ごとに行全体
        #   9. (col[])                  : rowを指定しない → 各列ごとに列全体
        # ------------------------------------------------------------
        single_lines = []
        indent = 0

        def add_single(text=""):
            single_lines.append("    " * indent + text)

        basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data = get_type_lists()
        custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)

        for item in matrix_list:
            item_name = item.get('name')
            row_id = item.get('rowId', '')
            col_id = item.get('colId', '')
            if not item_name or not row_id or not col_id:
                continue
            if row_id in class_data_id_list or row_id in custom_type_info['custom_class_id_list']:
                row_id += "Table"
            if col_id in class_data_id_list or col_id in custom_type_info['custom_class_id_list']:
                col_id += "Table"
            row_type = f"{row_id}ID"
            col_type = f"{col_id}ID"
            table_ref = f"GameCore.Tables.{item_name}MatrixTable"
            cell_tuple_type = f"IEnumerable<({row_type} Row, {col_type} Col)>"

            patterns = [
                {
                    'params': [(row_type, 'row'), (col_type, 'col')],
                    'pre': [],
                    'name_suffix': '',
                    'load_call': f"await {table_ref}.LoadSingleAsync(row, col, false, action);",
                    'unload_call': f"{table_ref}.UnloadSingle(row, col, action);",
                    'doc': f"{item_name}: 指定した1セル(row×col)だけを、事前記録済みのシーク位置で直接読み込む(テーブル全体はロードしない)",
                    'undoc': f"{item_name}: 指定した1セルだけをTableから解放する(テーブル全体は解放しない)",
                },
                {
                    'params': [(f"IEnumerable<{row_type}>", 'rows'), (col_type, 'col')],
                    'pre': [],
                    'name_suffix': '',
                    'load_call': f"await {table_ref}.LoadSingleAsync(rows, col, false, action);",
                    'unload_call': f"{table_ref}.UnloadSingle(rows, col, action);",
                    'doc': f"{item_name}: 複数行(row[]) × 単一列(col)のセルだけをまとめて読み込む(テーブル全体はロードしない)",
                    'undoc': f"{item_name}: 複数行(row[]) × 単一列(col)のセルだけをTableから解放する(テーブル全体は解放しない)",
                },
                {
                    'params': [(row_type, 'row'), (f"IEnumerable<{col_type}>", 'cols')],
                    'pre': [],
                    'name_suffix': '',
                    'load_call': f"await {table_ref}.LoadSingleAsync(row, cols, false, action);",
                    'unload_call': f"{table_ref}.UnloadSingle(row, cols, action);",
                    'doc': f"{item_name}: 単一行(row) × 複数列(col[])のセルだけをまとめて読み込む(テーブル全体はロードしない)",
                    'undoc': f"{item_name}: 単一行(row) × 複数列(col[])のセルだけをTableから解放する(テーブル全体は解放しない)",
                },
                {
                    'params': [(cell_tuple_type, 'cells')],
                    'pre': [],
                    'name_suffix': '',
                    'load_call': f"await {table_ref}.LoadSingleAsync(cells, false, action);",
                    'unload_call': f"{table_ref}.UnloadSingle(cells, action);",
                    'doc': f"{item_name}: 指定した複数セル(row,colの組)だけをまとめて読み込む(配列対応。テーブル全体はロードしない)",
                    'undoc': f"{item_name}: 指定した複数セルだけをTableから解放する(配列対応。テーブル全体は解放しない)",
                },
                {
                    'params': [(f"IEnumerable<{row_type}>", 'rows'), (f"IEnumerable<{col_type}>", 'cols')],
                    'pre': [
                        f"var cells = new List<({row_type} Row, {col_type} Col)>();",
                        "foreach (var r in rows) { foreach (var c in cols) { cells.Add((r, c)); } }",
                    ],
                    'name_suffix': '',
                    'load_call': f"await {table_ref}.LoadSingleAsync(cells, false, action);",
                    'unload_call': f"{table_ref}.UnloadSingle(cells, action);",
                    'doc': f"{item_name}: 複数行(row[]) × 複数列(col[])の全組み合わせセルをまとめて読み込む(直積。テーブル全体はロードしない)",
                    'undoc': f"{item_name}: 複数行(row[]) × 複数列(col[])の全組み合わせセルをTableから解放する(直積。テーブル全体は解放しない)",
                },
                # --- 行全体 / 列全体系(6〜9)は、row_typeとcol_typeが同じ型のときに
                # 「LoadSingle{Name}(T row)」と「LoadSingle{Name}(T col)」が完全に同一シグネチャに
                # なってコンパイルエラー(CS0111)になってしまうため、行専用/列専用でメソッド名自体を
                # 分ける(LoadSingleRow{Name} / LoadSingleColumn{Name})。型が異なる場合でも同じ命名規則で
                # 統一しておく。
                {
                    'params': [(row_type, 'row')],
                    'pre': [],
                    'name_suffix': 'Row',
                    'load_call': f"await {table_ref}.LoadRowAsync(row, false, action);",
                    'unload_call': f"{table_ref}.UnloadRow(row, action);",
                    'doc': f"{item_name}: colを指定しない場合は、指定した1行(row)全体をまとめて読み込む(テーブル全体はロードしない)",
                    'undoc': f"{item_name}: colを指定しない場合は、指定した1行(row)全体をTableから解放する(テーブル全体は解放しない)",
                },
                {
                    'params': [(col_type, 'col')],
                    'pre': [],
                    'name_suffix': 'Column',
                    'load_call': f"await {table_ref}.LoadColumnAsync(col, false, action);",
                    'unload_call': f"{table_ref}.UnloadColumn(col, action);",
                    'doc': f"{item_name}: rowを指定しない場合は、指定した1列(col)全体をまとめて読み込む(テーブル全体はロードしない)",
                    'undoc': f"{item_name}: rowを指定しない場合は、指定した1列(col)全体をTableから解放する(テーブル全体は解放しない)",
                },
                {
                    'params': [(f"IEnumerable<{row_type}>", 'rows')],
                    'pre': [],
                    'name_suffix': 'Row',
                    'load_call': f"await {table_ref}.LoadRowAsync(rows, false, action);",
                    'unload_call': f"{table_ref}.UnloadRow(rows, action);",
                    'doc': f"{item_name}: colを指定しない場合は、複数行(row[])をそれぞれ行全体でまとめて読み込む(テーブル全体はロードしない)",
                    'undoc': f"{item_name}: colを指定しない場合は、複数行(row[])をそれぞれ行全体でTableから解放する(テーブル全体は解放しない)",
                },
                {
                    'params': [(f"IEnumerable<{col_type}>", 'cols')],
                    'pre': [],
                    'name_suffix': 'Column',
                    'load_call': f"await {table_ref}.LoadColumnAsync(cols, false, action);",
                    'unload_call': f"{table_ref}.UnloadColumn(cols, action);",
                    'doc': f"{item_name}: rowを指定しない場合は、複数列(col[])をそれぞれ列全体でまとめて読み込む(テーブル全体はロードしない)",
                    'undoc': f"{item_name}: rowを指定しない場合は、複数列(col[])をそれぞれ列全体でTableから解放する(テーブル全体は解放しない)",
                },
            ]

            for pattern in patterns:
                sig_params = ", ".join(f"{t} {n}" for t, n in pattern['params'])
                call_args = ", ".join(n for t, n in pattern['params'])
                method_name = f"{item_name}{pattern['name_suffix']}"

                add_single(f"/// <summary>{pattern['doc']}</summary>")
                add_single(f"public static async UniTask LoadSingleAsync{method_name}({sig_params}, Action action = null)")
                add_single("{")
                indent += 1
                for line in pattern['pre']:
                    add_single(line)
                add_single(pattern['load_call'])
                indent -= 1
                add_single("}")
                add_single()

                add_single(f"public static void LoadSingle{method_name}({sig_params}, Action action = null)")
                add_single("{")
                indent += 1
                add_single(f"UniTask.Action(async () => {{ await LoadSingleAsync{method_name}({call_args}, action); }}).Invoke();")
                indent -= 1
                add_single("}")
                add_single()

                add_single(f"/// <summary>{pattern['undoc']}</summary>")
                add_single(f"public static void UnloadSingle{method_name}({sig_params}, Action action = null)")
                add_single("{")
                indent += 1
                for line in pattern['pre']:
                    add_single(line)
                add_single(pattern['unload_call'])
                indent -= 1
                add_single("}")
                add_single()

                add_single(f"public static async UniTask UnloadSingleAsync{method_name}({sig_params}, Action action = null)")
                add_single("{")
                indent += 1
                add_single(f"UnloadSingle{method_name}({call_args}, action);")
                add_single("await UniTask.CompletedTask;")
                indent -= 1
                add_single("}")
                add_single()

        all_blocks += single_lines

        append_str = "\n".join(all_blocks)

        code_str = f"""
using System;
using Cysharp.Threading.Tasks;
using System.Collections.Generic;
using GameCore.Tables.ID;
using GameCore.Enums;

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



def generate_base(data_dir):
    """
    ClassDataMatrixID 用のボイラープレート生成（初回起動時のみ）。
    - BaseTableMatrix.cs / BaseClassDataMatrixID.cs / BaseClassDataMatrixRow.cs
    - ClassDataMatrixIDCore.cs
    - MatrixTableID.cs
    """
    os.makedirs(os.path.join(data_dir, CLASS_DATA_MATRIX_ID), exist_ok=True)

    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_MATRIX_ID)):
        os.makedirs(os.path.join(data_dir, CLASS_DATA_MATRIX_ID))
    
    
    # MatrixTableRegistry.cs 生成
    # MatrixTableID単位で「テーブル丸ごとのLoad/Unload」を行うためのディスパッチレジストリ。
    # 各{name}MatrixTableの静的コンストラクタが自分自身を登録する。
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "MatrixTableRegistry.cs")):
        code_str = """
    using System;
    using System.IO;
    using System.Collections.Generic;

    namespace GameCore.Tables
    {
        public static class MatrixTableRegistry
        {
            public static readonly Dictionary<MatrixTableID, Action<ClassDataMatrixHeader, BinaryReader>> Loaders = new Dictionary<MatrixTableID, Action<ClassDataMatrixHeader, BinaryReader>>();
            public static readonly Dictionary<MatrixTableID, Action> Unloaders = new Dictionary<MatrixTableID, Action>();
        }
    }
    """
        with open(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "MatrixTableRegistry.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")

    # BaseTableMatrix.cs を生成
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "BaseTableMatrix.cs")):
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
        with open(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "BaseTableMatrix.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")

    # BaseClassDataMatrixID.cs 生成
    # ※以前は「初回のみ」生成していたが、TryGetCellなどベースクラス側の機能追加が
    #   既存プロジェクトに反映されない不具合があったため、常に再生成する
    #   (ユーザーが手を加えるファイルではなく、完全自動生成のボイラープレートのため)
    if True:
        code_str = """
    using System.IO;
    using System;
    using System.Collections.Generic;
    using GameCore.Enums;

    namespace GameCore.Tables
    {
        public abstract class BaseClassDataMatrixID<TRow, TCol, E> : BaseTableMatrix where TRow : Enum where TCol : Enum where E : BaseClassDataMatrixRow, new()
        {
            public static Dictionary<TRow, Dictionary<TCol, E>> Table = new Dictionary<TRow, Dictionary<TCol, E>>();

            // 各テーブルの静的コンストラクタで {Name}MatrixRowIndex と TableId がセットされる（rowKeyごとのシーク位置）
            protected static BaseClassDataRowIndex<TRow> RowIndex;
            protected static MatrixTableID TableId;
            // 列キー一覧（行インデックス読み込み時にキャッシュされる）
            protected static List<TCol> s_colKeys;
            // rowKeyごとの「セル単位のシーク位置」キャッシュ（row_blockの先頭からの相対offset）
            protected static Dictionary<TRow, Dictionary<TCol, (long Offset, int Size)>> s_cellIndexCache = new Dictionary<TRow, Dictionary<TCol, (long, int)>>();

            public override abstract void Read(BinaryReader reader);
            public override void Release()
            {
                Table.Clear();
                s_cellIndexCache.Clear();
            }

            /// <summary>
            /// 行インデックス（rowKeyごとのシーク位置）と列キー一覧だけを読み込む。
            /// 既に読み込み済みならスキップ（forceReload=trueで再読み込み）。
            /// </summary>
            protected static void EnsureRowIndexLoaded(BinaryReader reader, long tableBaseOffset, bool forceReload = false)
            {
                if (RowIndex.IsRead && !forceReload) return;

                reader.BaseStream.Seek(tableBaseOffset, SeekOrigin.Begin);
                int rowCount = reader.ReadInt32();
                for (int i = 0; i < rowCount; i++) reader.ReadInt32(); // rowKeyのid列（行インデックスに再度現れるのでここでは読み捨て）
                int colCount = reader.ReadInt32();
                s_colKeys = new List<TCol>(colCount);
                for (int i = 0; i < colCount; i++)
                {
                    s_colKeys.Add((TCol)Enum.ToObject(typeof(TCol), reader.ReadInt32()));
                }
                // ここでreaderは行インデックスブロックの先頭に位置している
                RowIndex.Read(reader, forceReload);

                if (forceReload) s_cellIndexCache.Clear();
            }

            /// <summary>
            /// 指定したrowKeyの「セル単位のシーク位置(row_block先頭からの相対offset)」を読み込む。
            /// 既に読み込み済みならキャッシュを返す（forceReload=trueで再読み込み）。
            /// </summary>
            protected static Dictionary<TCol, (long Offset, int Size)> EnsureCellIndexLoaded(TRow rowId, BinaryReader reader, long tableBaseOffset, bool forceReload = false)
            {
                if (!forceReload && s_cellIndexCache.TryGetValue(rowId, out var cached)) return cached;
                if (!RowIndex.Entries.TryGetValue(rowId, out var rowEntry)) return null;

                reader.BaseStream.Seek(tableBaseOffset + rowEntry.Offset, SeekOrigin.Begin);
                int cellIndexCount = reader.ReadInt32();
                var cellIndex = new Dictionary<TCol, (long, int)>();
                for (int i = 0; i < cellIndexCount; i++)
                {
                    int colIdVal = reader.ReadInt32();
                    TCol colId = (TCol)Enum.ToObject(typeof(TCol), colIdVal);
                    long offset = reader.ReadInt64();
                    int size = reader.ReadInt32();
                    cellIndex[colId] = (offset, size);
                }
                s_cellIndexCache[rowId] = cellIndex;
                return cellIndex;
            }

            /// <summary>
            /// セルが参照している他のclass_data_idを(ネストして)連鎖的にプリロードする。
            /// idHeader/idReaderはID側(all_class_data.bytes)のヘッダーとreader。呼び出し側で別途開いたものを渡す。
            /// </summary>
            private static void PreloadCellReferences(E cell, ClassDataHeader idHeader, BinaryReader idReader, HashSet<(TableID, int)> visited)
            {
                if (cell == null || idHeader == null || idReader == null) return;
                foreach (var reference in cell.GetReferencedIds())
                {
                    ClassDataReferenceDispatcher.Load(reference.TableId, reference.RefId, idHeader, idReader, true, false, visited);
                }
            }

            private static void ReadCellInternal(TRow rowId, TCol colId, Dictionary<TCol, (long Offset, int Size)> cellIndex, BinaryReader reader, long tableBaseOffset, long rowOffset,
                bool preloadReferences, ClassDataHeader idHeader, BinaryReader idReader, HashSet<(TableID, int)> visited)
            {
                if (cellIndex == null || !cellIndex.TryGetValue(colId, out var cellEntry)) return;
                reader.BaseStream.Seek(tableBaseOffset + rowOffset + cellEntry.Offset, SeekOrigin.Begin);
                var cell = new E();
                cell.Read(Convert.ToInt32(rowId), Convert.ToInt32(colId), reader);
                if (!Table.TryGetValue(rowId, out var rowDict))
                {
                    rowDict = new Dictionary<TCol, E>();
                    Table[rowId] = rowDict;
                }
                rowDict[colId] = cell;

                if (preloadReferences) PreloadCellReferences(cell, idHeader, idReader, visited);
            }

            // ========================= 行単位 =========================

            /// <summary>
            /// 指定した1つのrowKey(行、全列)だけをロードする。テーブル全体はロードしない。
            /// preloadReferences=trueの場合、idHeader/idReader(ID側の別途開いたヘッダーとreader)経由で参照先も(ネストして)連鎖的にロードする。
            /// </summary>
            public static void ReadOneRow(TRow rowId, ClassDataMatrixHeader header, BinaryReader reader, bool preloadReferences = false, ClassDataHeader idHeader = null, BinaryReader idReader = null, bool forceReloadIndex = false)
            {
                if (!header.Entries.TryGetValue(TableId, out var tableEntry)) return;
                long tableBaseOffset = tableEntry.Offset;

                EnsureRowIndexLoaded(reader, tableBaseOffset, forceReloadIndex);
                if (!RowIndex.Entries.TryGetValue(rowId, out var rowEntry)) return;
                var cellIndex = EnsureCellIndexLoaded(rowId, reader, tableBaseOffset, forceReloadIndex);

                var visited = new HashSet<(TableID, int)>();
                foreach (var ck in s_colKeys)
                {
                    ReadCellInternal(rowId, ck, cellIndex, reader, tableBaseOffset, rowEntry.Offset, preloadReferences, idHeader, idReader, visited);
                }
            }

            /// <summary>指定した複数のrowKey(行)だけをロードする。テーブル全体はロードしない。
            /// forceReloadIndexは最初の1件目でのみ適用する(2件目以降まで毎回全体を再読込しない)。</summary>
            public static void ReadManyRows(IEnumerable<TRow> rowIds, ClassDataMatrixHeader header, BinaryReader reader, bool preloadReferences = false, ClassDataHeader idHeader = null, BinaryReader idReader = null, bool forceReloadIndex = false)
            {
                bool first = true;
                foreach (var rowId in rowIds)
                {
                    ReadOneRow(rowId, header, reader, preloadReferences, idHeader, idReader, forceReloadIndex && first);
                    first = false;
                }
            }

            /// <summary>指定した1つのrowKey(行全体)だけをアンロードする（テーブル全体は消さない）</summary>
            public static void UnloadOneRow(TRow rowId)
            {
                Table.Remove(rowId);
                s_cellIndexCache.Remove(rowId);
            }

            /// <summary>指定した複数のrowKeyだけをアンロードする（テーブル全体は消さない）</summary>
            public static void UnloadManyRows(IEnumerable<TRow> rowIds)
            {
                foreach (var rowId in rowIds) UnloadOneRow(rowId);
            }

            /// <summary>条件(predicate)に合致するrowKey(行)を一括アンロードする</summary>
            public static void UnloadRowsWhere(Func<TRow, Dictionary<TCol, E>, bool> predicate)
            {
                var keysToRemove = new List<TRow>();
                foreach (var kv in Table)
                {
                    if (predicate(kv.Key, kv.Value)) keysToRemove.Add(kv.Key);
                }
                foreach (var key in keysToRemove) UnloadOneRow(key);
            }

            // ========================= 列単位 =========================

            /// <summary>
            /// 指定した1つのcolKey(列、全行)だけをロードする。テーブル全体はロードしない。
            /// </summary>
            public static void ReadOneColumn(TCol colId, ClassDataMatrixHeader header, BinaryReader reader, bool preloadReferences = false, ClassDataHeader idHeader = null, BinaryReader idReader = null, bool forceReloadIndex = false)
            {
                if (!header.Entries.TryGetValue(TableId, out var tableEntry)) return;
                long tableBaseOffset = tableEntry.Offset;

                EnsureRowIndexLoaded(reader, tableBaseOffset, forceReloadIndex);
                var visited = new HashSet<(TableID, int)>();
                foreach (var rowId in RowIndex.Entries.Keys)
                {
                    if (!RowIndex.Entries.TryGetValue(rowId, out var rowEntry)) continue;
                    var cellIndex = EnsureCellIndexLoaded(rowId, reader, tableBaseOffset, forceReloadIndex);
                    ReadCellInternal(rowId, colId, cellIndex, reader, tableBaseOffset, rowEntry.Offset, preloadReferences, idHeader, idReader, visited);
                }
            }

            /// <summary>指定した複数のcolKey(列)だけをロードする。テーブル全体はロードしない。</summary>
            public static void ReadManyColumns(IEnumerable<TCol> colIds, ClassDataMatrixHeader header, BinaryReader reader, bool preloadReferences = false, ClassDataHeader idHeader = null, BinaryReader idReader = null, bool forceReloadIndex = false)
            {
                bool first = true;
                foreach (var colId in colIds)
                {
                    ReadOneColumn(colId, header, reader, preloadReferences, idHeader, idReader, forceReloadIndex && first);
                    first = false;
                }
            }

            /// <summary>指定した1つのcolKey(列全体)だけをアンロードする（テーブル全体は消さない）</summary>
            public static void UnloadOneColumn(TCol colId)
            {
                foreach (var rowDict in Table.Values) rowDict.Remove(colId);
            }

            /// <summary>指定した複数のcolKeyだけをアンロードする（テーブル全体は消さない）</summary>
            public static void UnloadManyColumns(IEnumerable<TCol> colIds)
            {
                foreach (var colId in colIds) UnloadOneColumn(colId);
            }

            /// <summary>条件(predicate)に合致するcolKey(列)を一括アンロードする</summary>
            public static void UnloadColumnsWhere(Func<TCol, bool> predicate)
            {
                if (s_colKeys == null) return;
                var colsToRemove = new List<TCol>();
                foreach (var ck in s_colKeys)
                {
                    if (predicate(ck)) colsToRemove.Add(ck);
                }
                foreach (var ck in colsToRemove) UnloadOneColumn(ck);
            }

            // ========================= セル単位 =========================

            /// <summary>
            /// 指定したセル(rowId×colId)が、現在メモリ上のTableに存在するかどうかを高速に判定する。
            /// ファイルアクセスは一切行わず、既にロード済みのTableを辞書引きするだけ(O(1))。
            /// 存在すればFound=true・Dataにそのセルのデータを、存在しなければFound=false・Data=defaultを返す。
            /// </summary>
            public static (bool Found, E Data) TryGetCell(TRow rowId, TCol colId)
            {
                if (Table.TryGetValue(rowId, out var rowDict) && rowDict.TryGetValue(colId, out var cell))
                {
                    return (true, cell);
                }
                return (false, default);
            }

            /// <summary>指定した1つのセル(rowKey×colKey)だけをロードする。</summary>
            public static void ReadOneCell(TRow rowId, TCol colId, ClassDataMatrixHeader header, BinaryReader reader, bool preloadReferences = false, ClassDataHeader idHeader = null, BinaryReader idReader = null, bool forceReloadIndex = false)
            {
                if (!header.Entries.TryGetValue(TableId, out var tableEntry)) return;
                long tableBaseOffset = tableEntry.Offset;

                EnsureRowIndexLoaded(reader, tableBaseOffset, forceReloadIndex);
                if (!RowIndex.Entries.TryGetValue(rowId, out var rowEntry)) return;
                var cellIndex = EnsureCellIndexLoaded(rowId, reader, tableBaseOffset, forceReloadIndex);
                var visited = new HashSet<(TableID, int)>();
                ReadCellInternal(rowId, colId, cellIndex, reader, tableBaseOffset, rowEntry.Offset, preloadReferences, idHeader, idReader, visited);
            }

            /// <summary>指定した複数のセル(rowKey×colKeyの組)だけをロードする。</summary>
            public static void ReadManyCells(IEnumerable<(TRow Row, TCol Col)> cells, ClassDataMatrixHeader header, BinaryReader reader, bool preloadReferences = false, ClassDataHeader idHeader = null, BinaryReader idReader = null, bool forceReloadIndex = false)
            {
                bool first = true;
                foreach (var cell in cells)
                {
                    ReadOneCell(cell.Row, cell.Col, header, reader, preloadReferences, idHeader, idReader, forceReloadIndex && first);
                    first = false;
                }
            }

            /// <summary>指定した1つのセルだけをアンロードする</summary>
            public static void UnloadOneCell(TRow rowId, TCol colId)
            {
                if (Table.TryGetValue(rowId, out var rowDict)) rowDict.Remove(colId);
            }

            /// <summary>指定した複数のセルだけをアンロードする</summary>
            public static void UnloadManyCells(IEnumerable<(TRow Row, TCol Col)> cells)
            {
                foreach (var cell in cells) UnloadOneCell(cell.Row, cell.Col);
            }

            /// <summary>条件(predicate)に合致するセルを一括アンロードする</summary>
            public static void UnloadCellsWhere(Func<TRow, TCol, E, bool> predicate)
            {
                var toRemove = new List<(TRow, TCol)>();
                foreach (var rowKv in Table)
                {
                    foreach (var colKv in rowKv.Value)
                    {
                        if (predicate(rowKv.Key, colKv.Key, colKv.Value)) toRemove.Add((rowKv.Key, colKv.Key));
                    }
                }
                foreach (var pair in toRemove) UnloadOneCell(pair.Item1, pair.Item2);
            }

            /// <summary>
            /// テーブル全体をロードする（既存のRead(reader)を利用、高速な連続読みはそのまま）。
            /// preloadReferences=trueの場合、idHeader/idReader経由で全セルの参照先も(ネストして)連鎖的にロードする。
            /// </summary>
            public virtual void ReadAll(ClassDataMatrixHeader header, BinaryReader reader, bool preloadReferences = false, ClassDataHeader idHeader = null, BinaryReader idReader = null)
            {
                Read(reader);
                if (!preloadReferences || idHeader == null || idReader == null) return;

                var visited = new HashSet<(TableID, int)>();
                foreach (var rowDict in Table.Values)
                {
                    foreach (var cell in rowDict.Values)
                    {
                        PreloadCellReferences(cell, idHeader, idReader, visited);
                    }
                }
            }
        }
    }
    """
        with open(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "BaseClassDataMatrixID.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")

    # BaseClassDataMatrixRow.cs 生成
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "BaseClassDataMatrixRow.cs")):
        code_str = """
    using System.IO;
    using System.Collections.Generic;
    using GameCore.Enums;

    namespace GameCore.Tables
    {
        [System.Serializable]
        public abstract class BaseClassDataMatrixRow
        {
            // rowId/colIdは列挙値をintにキャストした生の値。生成される{Name}MatrixRowでは
            // これを使って型付きのRowId/ColIdプロパティ(TRowID/TColID)をReadの先頭でセットする
            // (class_data_idのRow.Read(int id, reader)でtable_idを自動セットしているのと同じ考え方)。
            public abstract void Read(int rowId, int colId, BinaryReader reader);

            /// <summary>
            /// このセルが参照している他のclass_data_idの(TableID, 参照先id)一覧。
            /// 参照フィールドを持つセルでは自動生成コード側でoverrideされる。デフォルトは空。
            /// </summary>
            public virtual List<(TableID TableId, int RefId)> GetReferencedIds()
            {
                return new List<(TableID, int)>();
            }
        }
    }
    """
        with open(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "BaseClassDataMatrixRow.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")
        

    #ClassDataMatrixIDCore.cs 生成
    if not os.path.exists(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "ClassDataMatrixIDCore.cs")):
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
        // 注意: 以前はここに「if (isLoaded) return;」があり、2回目以降の呼び出しでonLoadedが
        // 一切実行されない致命的なバグがあった(タグ一括ロード・行/列/セル単位のシングルロード等、
        // 初回ロード以降に呼ばれるものが全て無反応になっていた)。ヘッダーはキャッシュ済みなら
        // 再パースしないが、onLoadedは呼び出しごとに毎回必ず実行する。

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

    /// <summary>指定したMatrixTableID 1件だけをロードする（テーブル丸ごと）。MatrixTableRegistry経由でディスパッチする。</summary>
    public async UniTask LoadClassDataSingleAsync(MatrixTableID id, Action action = null, bool addressable = false)
    {
        await LoadClassDataAsync(async (reader, header) =>
        {
            if (MatrixTableRegistry.Loaders.TryGetValue(id, out var loader))
            {
                loader(header, reader);
            }
            else
            {
                Debug.LogWarning($"MatrixTableRegistryに{id}のローダーが登録されていません。");
            }
            action?.Invoke();
            await UniTask.CompletedTask;
        }, addressable);
    }

    /// <summary>指定したMatrixTableID 1件だけをアンロードする（テーブル丸ごと）。</summary>
    public void UnloadClassData(MatrixTableID id)
    {
        if (MatrixTableRegistry.Unloaders.TryGetValue(id, out var unloader))
        {
            unloader();
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
    
        with open(os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "ClassDataMatrixIDCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str.strip() + "\n")
        

    # MatrixTableID.cs の事前作成
    matrix_table_id_path = os.path.join(data_dir, CLASS_DATA_MATRIX_ID, "MatrixTableID.cs")
    if not os.path.exists(matrix_table_id_path):
        code_str = """
namespace GameCore.Tables
{
    public enum MatrixTableID
    {
        None = 0,
        Max
    }
}
"""
        with open(matrix_table_id_path, 'w', encoding='utf-8') as f:
            f.write(code_str)


def register(app, data_dir):
    """app.py から呼び出し、DATA_DIR を設定・ボイラープレート生成した上でルートを登録する。"""
    global DATA_DIR
    DATA_DIR = data_dir
    generate_base(data_dir)
    app.register_blueprint(bp)