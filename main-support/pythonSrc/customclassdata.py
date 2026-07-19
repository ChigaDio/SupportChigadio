# -*- coding: utf-8 -*-
"""
customclassdata.py
===================
CustomClassData / CustomClassDataID を管理する Flask Blueprint。

- CustomClassData
    ClassData の拡張版。各フィールドに「型ごとのオプション」を持てる。
      - 数値型(int/float/double/byte/short/long) : min / max ( [Range] 生成 )
      - bit  : オンオフのビットフラグ。64bit以下は ulong、65bit以上は ulong[] で
               保持する専用クラス CustomBitField を介して扱う。
               ・sizeMode: 'manual' | 'enum' | 'classDataId' | 'customClassDataId'
                 (enum等の要素数からビット数を自動算出することもできる)
               ・mode: 'multiple'(複数選択可) | 'single'(排他選択・ラジオ的)
               ・allowSelectAll: 全選択ボタンを許可するか
      - color: RGBA (UnityEngine.Color)
      - bezier: 数値(int/float)用のベジェカーブ。各点の time/value に加えて
                in/out タンジェントを保持する (UnityEngine.AnimationCurve)
      - それ以外(Enum/ClassData/ClassDataID/他のCustomClassData/Vector2/Vector3等)
        は素の参照として扱う

- CustomClassDataID
    ClassDataID の拡張版 (columns/rows のテーブル)。
    column の type に CustomClassData を指定でき、その場合はセル編集時に
    CustomClassData 側で定義したオプション(min/max, bit, color, bezier)に
    応じた専用エディタで値を編集できるよう、フロント向けにスキーマを提供する。

このファイルは app.py から `register(app, DATA_DIR)` を呼び出して組み込む。
(app.py 側に必要な追記は本ファイル末尾のコメント、または回答内の説明を参照)
"""

import os
import io
import re
import json
import struct
import shutil
import logging
import textwrap

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

# --- ディレクトリ/ファイル名定数 -------------------------------------------------
CUSTOM_CLASS_DATA = 'custom_class_data'
CUSTOM_CLASS_DATA_ID = 'custom_class_data_id'

# 既存 app.py と同じディレクトリ名(参照専用)
ENUM = 'enum'
CLASS_DATA = 'class_data'
CLASS_DATA_ID = 'class_data_id'
SCRIPT = 'Script'  # app.py と同じ Script フォルダ(SupportFiles.cs置き場)

NUMERIC_TYPES = ['int', 'float', 'double', 'byte', 'short', 'long', 'decimal', 'uint']
BASIC_TYPES = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object']
UNITY_BASIC_TYPES = ['Vector2', 'Vector3']
CUSTOM_TYPES = ['bit', 'color', 'bezier']  # CustomClassData 独自の拡張型

TYPE_MAP = {
    'int': {'cs_read': 'ReadInt32'},
    'float': {'cs_read': 'ReadSingle'},
    'double': {'cs_read': 'ReadDouble'},
    'bool': {'cs_read': 'ReadBoolean'},
    'byte': {'cs_read': 'ReadByte'},
    'short': {'cs_read': 'ReadInt16'},
    'long': {'cs_read': 'ReadInt64'},
}

# バイナリ書き込み(struct.pack)用フォーマット
PACK_MAP = {
    'int': 'i', 'uint': 'I', 'float': 'f', 'double': 'd',
    'bool': '?', 'byte': 'B', 'short': 'h', 'long': 'q', 'decimal': 'd',
}

_state = {}  # register() で DATA_DIR 等を格納する


def _data_dir():
    return _state['DATA_DIR']


def _path(*parts):
    return os.path.join(_data_dir(), *parts)


def _ensure_dirs():
    for d in [CUSTOM_CLASS_DATA, CUSTOM_CLASS_DATA_ID]:
        p = _path(d)
        os.makedirs(p, exist_ok=True)
    list_path = _path(CUSTOM_CLASS_DATA, 'custom_class_data_list.json')
    if not os.path.exists(list_path):
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump([], f)
    list_id_path = _path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json')
    if not os.path.exists(list_id_path):
        with open(list_id_path, 'w', encoding='utf-8') as f:
            json.dump([], f)


def _load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        logger.error(f"JSON parse error: {path}")
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- 型情報の収集 -----------------------------------------------------------------

def get_extended_type_lists():
    """
    既存の basic/unity/enum/classData/classDataID に加え、
    CustomClassData の一覧・スキーマ(オプション込み)をまとめて返す。
    """
    enum_list = [e.get('name') for e in _load_json(_path(ENUM, 'enum_list.json'), [])]
    class_list = [c.get('name') for c in _load_json(_path(CLASS_DATA, 'class_list.json'), [])]
    class_data_id_list = [c.get('name') for c in _load_json(_path(CLASS_DATA_ID, 'class_data_id_list.json'), [])]
    custom_class_list = [c.get('name') for c in _load_json(_path(CUSTOM_CLASS_DATA, 'custom_class_data_list.json'), [])]
    custom_class_id_list = [c.get('name') for c in _load_json(_path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json'), [])]

    custom_class_schemas = {}
    for name in custom_class_list:
        fields = _load_json(
            _path(CUSTOM_CLASS_DATA, name, f"{name}.customclass.json"), []
        )
        _refresh_live_bit_flag_names(fields)
        custom_class_schemas[name] = fields

    return {
        'basic_types': BASIC_TYPES,
        'unity_types': UNITY_BASIC_TYPES,
        'custom_types': CUSTOM_TYPES,
        'enum_list': enum_list,
        'class_list': class_list,
        'class_data_id_list': class_data_id_list,
        'custom_class_list': custom_class_list,
        'custom_class_id_list': custom_class_id_list,
        'custom_class_schemas': custom_class_schemas,
    }


def _bit_source_entries(mode, source_name):
    """
    enum / classDataId / customClassDataId を参照する bit フィールドについて、
    ビットインデックスに対応する実体の名前(と元の値/id)を順番どおりに返す。
    この並び順がそのままビットインデックスになるので、C#生成側でも同じ並びから
    ToIndex() を組み立てられる => 手動でのインデックス管理(マジックナンバー)が不要になる。
    """
    if mode == 'enum':
        data = _load_json(_path(ENUM, source_name, f"{source_name}.json"), [])
        return [{'name': item.get('property'), 'value': item.get('value')}
                for item in data if item.get('property')]
    if mode == 'classDataId':
        data = _load_json(_path(CLASS_DATA_ID, source_name, f"{source_name}.json"), {'rows': []})
        return [{'name': row.get('enum_property'), 'value': row.get('id')}
                for row in data.get('rows', []) if row.get('enum_property')]
    if mode == 'customClassDataId':
        data = _load_json(_path(CUSTOM_CLASS_DATA_ID, source_name, f"{source_name}.json"), {'rows': []})
        return [{'name': row.get('enum_property'), 'value': row.get('id')}
                for row in data.get('rows', []) if row.get('enum_property')]
    return None


def _bit_source_cs_type(mode, source_name):
    """sizeMode の参照先が C# 上でどの型になるかを返す(拡張メソッド生成用)"""
    if mode == 'enum':
        return f"GameCore.Enums.{source_name}ID"
    if mode in ('classDataId', 'customClassDataId'):
        return f"GameCore.Tables.ID.{source_name}TableID"
    return None


def _bit_size_from_source(mode, source_name):
    """enum / classDataId / customClassDataId の要素数からビット数を算出する"""
    entries = _bit_source_entries(mode, source_name)
    return max(len(entries), 1) if entries else None


def _refresh_live_bit_flag_names(fields):
    """
    bit フィールドのうち sizeMode が enum/classDataId/customClassDataId を
    参照しているものについて、flagNames/size を「読み込み時」に参照元の
    最新データから再計算し、その場でフィールドを更新する。

    _normalize_field_options() は CustomClassData の保存時(POST)にしか
    呼ばれないため、保存後に参照元(enum/classDataId/customClassDataId)側の
    項目が追加・削除・改名されると、保存済みの flagNames が古いまま
    (最悪の場合、生成時点で参照解決に失敗した "Flag0/Flag1..." のまま)
    になってしまう。CustomClassDataID の値編集(セル編集)のたびに
    「参照先の定義そのものの名前」を使わせたいので、type-options 取得の
    たびに毎回ライブで再計算して返す(保存ファイル自体は書き換えない)。
    """
    for field in fields or []:
        if field.get('type') != 'bit':
            continue
        options = field.get('options') or {}
        size_mode = options.get('sizeMode', 'manual')
        source_name = options.get('sizeSourceName')
        if size_mode == 'manual' or not source_name:
            continue
        entries = _bit_source_entries(size_mode, source_name)
        if not entries:
            # 参照元が見つからない場合は、保存済みの内容をそのまま使う
            # (存在しないものを勝手に Flag0/Flag1 で上書きしない)
            continue
        flag_names = [e['name'] for e in entries]
        options['flagNames'] = flag_names
        options['size'] = len(flag_names)
        options['generatedFromSource'] = True
        field['options'] = options


def _normalize_field_options(field):
    """フィールドの type に応じて options を補完・正規化する（保存前に呼ぶ）"""
    type_str = field.get('type', '')
    options = field.get('options') or {}

    if type_str in NUMERIC_TYPES:
        field['options'] = {
            'min': options.get('min', None),
            'max': options.get('max', None),
        }
    elif type_str == 'bit':
        size_mode = options.get('sizeMode', 'manual')
        source_name = options.get('sizeSourceName')
        size = options.get('size', 8)
        source_entries = None
        if size_mode != 'manual' and source_name:
            source_entries = _bit_source_entries(size_mode, source_name)
            if source_entries:
                size = len(source_entries)
        size = max(int(size or 1), 1)
        if source_entries:
            # enum/classDataId/customClassDataId が参照元の場合は、そちらの名前をそのまま
            # ビット名として使う(=マジックナンバーで管理させない)。手動編集不可。
            flag_names = [e['name'] for e in source_entries]
        else:
            flag_names = options.get('flagNames') or [f"Flag{i}" for i in range(size)]
            # 個数を size に合わせる
            if len(flag_names) < size:
                flag_names = flag_names + [f"Flag{i}" for i in range(len(flag_names), size)]
            else:
                flag_names = flag_names[:size]
        field['options'] = {
            'sizeMode': size_mode,
            'sizeSourceName': source_name,
            'size': size,
            'mode': options.get('mode', 'multiple'),  # 'multiple' | 'single'
            'allowSelectAll': bool(options.get('allowSelectAll', True)) if options.get('mode', 'multiple') == 'multiple' else False,
            'flagNames': flag_names,
            # true の場合、flagNames は参照元から自動生成されたものなのでフロント側では読み取り専用にする
            'generatedFromSource': bool(source_entries),
        }
    elif type_str == 'color':
        field['options'] = {}
    elif type_str == 'bezier':
        field['options'] = {
            'valueType': options.get('valueType', 'float') if options.get('valueType') in ('float', 'int') else 'float',
            'min': options.get('min', 0),
            'max': options.get('max', 1),
        }
    else:
        field['options'] = {}
    return field


def _default_value_for_field(field):
    t = field.get('type')
    opts = field.get('options') or {}
    if t in NUMERIC_TYPES:
        return opts.get('min') if opts.get('min') is not None else 0
    if t == 'bool':
        return False
    if t == 'string':
        return ''
    if t == 'Vector2':
        return [0, 0]
    if t == 'Vector3':
        return [0, 0, 0]
    if t == 'bit':
        return {'size': opts.get('size', 8), 'bits': []}
    if t == 'color':
        return {'r': 1, 'g': 1, 'b': 1, 'a': 1}
    if t == 'bezier':
        return {'points': [
            {'time': 0, 'value': opts.get('min', 0), 'inTangent': 0, 'outTangent': 0},
            {'time': 1, 'value': opts.get('max', 1), 'inTangent': 0, 'outTangent': 0},
        ]}
    return None


# =====================================================================================
# Blueprint
# =====================================================================================
bp = Blueprint('customclassdata', __name__, url_prefix='/api')


# ---------------------------------------------------------------------------
# CustomClassData 一覧管理
# ---------------------------------------------------------------------------
@bp.route('/custom-class-data', methods=['GET', 'POST', 'PATCH'])
def manage_custom_class_data():
    _ensure_dirs()
    file_path = _path(CUSTOM_CLASS_DATA, 'custom_class_data_list.json')

    if request.method == 'GET':
        return jsonify(_load_json(file_path, []))

    if request.method == 'POST':
        try:
            body = request.get_json()
            name = (body or {}).get('name', '').strip()
            if not name:
                return jsonify({"error": "名前は必須です"}), 400
            if ':' in name:
                return jsonify({"error": "名前に':'を含めることはできません"}), 400
            data = _load_json(file_path, [])
            if any(item['name'] == name for item in data):
                return jsonify({"error": f"CustomClassData {name} はすでに存在します"}), 400
            max_id = max([item['id'] for item in data], default=0) + 1
            entry = {"id": max_id, "name": name}
            data.append(entry)
            _save_json(file_path, data)
            _save_json(_path(CUSTOM_CLASS_DATA, name, f"{name}.customclass.json"), [])
            return jsonify({"message": f"CustomClassData {name} を作成しました", "data": entry})
        except Exception as e:
            logger.error(f"CustomClassData作成エラー: {e}")
            return jsonify({"error": str(e)}), 500

    if request.method == 'PATCH':
        try:
            delete_name = request.get_json().get('name')
            data = _load_json(file_path, [])
            data = [item for item in data if item['name'] != delete_name]
            _save_json(file_path, data)
            target_dir = _path(CUSTOM_CLASS_DATA, delete_name)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            return jsonify({"message": f"CustomClassData {delete_name} を削除しました"})
        except Exception as e:
            logger.error(f"CustomClassData削除エラー: {e}")
            return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# CustomClassData 詳細(フィールド一覧・オプション込み)
# ---------------------------------------------------------------------------
@bp.route('/custom-class-data/<name>', methods=['GET', 'POST', 'DELETE'])
def custom_class_data_detail(name):
    file_path = _path(CUSTOM_CLASS_DATA, name, f"{name}.customclass.json")

    if request.method == 'GET':
        data = _load_json(file_path, None)
        if data is None:
            return jsonify({"error": f"CustomClassData {name} が見つかりません"}), 404
        return jsonify(data)

    if request.method == 'POST':
        try:
            fields = request.get_json() or []
            # id 補完 + オプション正規化
            for i, field in enumerate(fields):
                field['id'] = field.get('id') or i + 1
                _normalize_field_options(field)
            _save_json(file_path, fields)
            return jsonify({"message": f"{name}.customclass.json を保存しました"})
        except Exception as e:
            logger.error(f"CustomClassData保存エラー({name}): {e}")
            return jsonify({"error": str(e)}), 500

    if request.method == 'DELETE':
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            target_dir = _path(CUSTOM_CLASS_DATA, name)
            if os.path.exists(target_dir) and not os.listdir(target_dir):
                os.rmdir(target_dir)
            list_path = _path(CUSTOM_CLASS_DATA, 'custom_class_data_list.json')
            data = _load_json(list_path, [])
            data = [item for item in data if item['name'] != name]
            _save_json(list_path, data)
            return jsonify({"message": f"{name} を削除しました"})
        except FileNotFoundError:
            return jsonify({"error": "見つかりません"}), 404
        except Exception as e:
            logger.error(f"CustomClassData削除エラー({name}): {e}")
            return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# 型/スキーマ一括取得(フロント用)
# ---------------------------------------------------------------------------
@bp.route('/custom-class-data-type-options', methods=['GET'])
def custom_class_data_type_options():
    """
    CustomClassDataDetailGrid / CustomClassDataIdDetailGrid が使う
    型候補一覧 + CustomClassData の全スキーマ(オプション込み)をまとめて返す。
    """
    return jsonify(get_extended_type_lists())


# ---------------------------------------------------------------------------
# 共有 CustomBitField.cs の生成
# ---------------------------------------------------------------------------
_CUSTOM_BIT_FIELD_CS = '''using System;
using System.Collections.Generic;
using System.IO;

namespace GameCore.Classes
{
    // 汎用ビットフィールドの共通実装。
    // 64bit以下は ulong 1個、65bit以上は ulong[] で保持する。
    // bit配列(bool[])ではなくビット演算で扱うことでメモリ効率を優先する。
    //
    // ・sizeMode が「手動指定」のフィールドは非ジェネリックの CustomBitField を使う。
    // ・sizeMode が enum/classDataId/customClassDataId を参照しているフィールドは
    //   ジェネリック版 CustomBitField<T> (T = 参照先の enum/TableID型) を使うことで、
    //   field.Set(FooID.Bar, true) のように「参照先の定義そのものの名前」で
    //   ビットを指定できる(インデックスをマジックナンバーで管理する必要がない)。
    [Serializable]
    public abstract class CustomBitFieldBase
    {
        [SerializeField]
        public int Size { get; protected set; }
        [SerializeField]
        protected ulong single;
        [SerializeField]
        protected ulong[] array;
        protected bool UseArray => Size > 64;

        protected void InitStorage(int size)
        {
            Size = size <= 0 ? 1 : size;
            if (UseArray)
            {
                array = new ulong[(Size + 63) / 64];
            }
        }

        public bool Get(int index)
        {
            if (index < 0 || index >= Size) return false;
            if (UseArray)
            {
                int block = index / 64;
                int bit = index % 64;
                return (array[block] & (1UL << bit)) != 0;
            }
            return (single & (1UL << index)) != 0;
        }

        public void Set(int index, bool value)
        {
            if (index < 0 || index >= Size) return;
            if (UseArray)
            {
                int block = index / 64;
                int bit = index % 64;
                if (value) array[block] |= (1UL << bit);
                else array[block] &= ~(1UL << bit);
            }
            else
            {
                if (value) single |= (1UL << index);
                else single &= ~(1UL << index);
            }
        }

        // 排他選択(single)用: 指定index以外をすべてクリアしてONにする
        public void SetExclusive(int index)
        {
            Clear();
            Set(index, true);
        }

        public void SelectAll()
        {
            for (int i = 0; i < Size; i++) Set(i, true);
        }

        public void Clear()
        {
            single = 0;
            if (UseArray)
                for (int i = 0; i < array.Length; i++) array[i] = 0;
        }

        public virtual void Read(BinaryReader reader)
        {
            int size = reader.ReadInt32();
            InitStorage(size);
            if (UseArray)
            {
                for (int i = 0; i < array.Length; i++) array[i] = reader.ReadUInt64();
            }
            else
            {
                single = reader.ReadUInt64();
                array = null;
            }
        }

        public void Write(BinaryWriter writer)
        {
            writer.Write(Size);
            if (UseArray)
                foreach (var v in array) writer.Write(v);
            else
                writer.Write(single);
        }
    }

    // 手動指定(sizeMode = manual)のビットフィールド。ビットはインデックスで指定する。
    [Serializable]
    public class CustomBitField : CustomBitFieldBase
    {
        public CustomBitField() : this(1) { }

        public CustomBitField(int size)
        {
            InitStorage(size);
        }
    }

    // 参照付き(sizeMode = enum/classDataId/customClassDataId)のビットフィールド。
    // T には参照先の型(XxxID / XxxTableID)が入る。
    // コンストラクタに渡す order は「ビットインデックス ⇔ T の値」の対応表で、
    // C#生成のたびに参照先の並び順から自動的に組み立てられる。
    [Serializable]
        [Serializable]
    public class CustomBitField<T> : CustomBitFieldBase where T : struct, Enum
    {
        // 型ごとに一度だけ計算される
        private static readonly int MaxValue =
            Enum.GetValues<T>().Max(e => Convert.ToInt32(e));

        public CustomBitField()
        {
            InitStorage(MaxValue);
        }

        private static int ToIndex(T id)
        {
            return Convert.ToInt32(id);
        }

        public bool Get(T id)
        {
            return Get(ToIndex(id));
        }

        public void Set(T id, bool value)
        {
            Set(ToIndex(id), value);
        }

        public void SetExclusive(T id)
        {
            SetExclusive(ToIndex(id));
        }

        public T FromIndex(int index)
        {
            if (index < 0 || index > MaxValue)
                return default;

            return (T)Enum.ToObject(typeof(T), index);
        }

        public override void Read(BinaryReader reader)
        {
            int size = reader.ReadInt32();

            // 保存データのサイズを読み捨て、enumのサイズで初期化
            InitStorage(MaxValue);

            if (UseArray)
            {
                for (int i = 0; i < array.Length; i++)
                    array[i] = reader.ReadUInt64();
            }
            else
            {
                single = reader.ReadUInt64();
                array = null;
            }
        }
    }
}

'''


def _write_bit_extension_file(out_dir, extension_code):
    """generate_custom_field が返した extension コードをファイルへ書き出す"""
    if not extension_code:
        return None
    m = re.search(r'class (\w+)', extension_code)
    if not m:
        return None
    ext_path = os.path.join(out_dir, f"{m.group(1)}.cs")
    with open(ext_path, 'w', encoding='utf-8') as f:
        f.write(extension_code)
    return ext_path


def _ensure_custom_bit_field_cs():
    shared_dir = _path(CUSTOM_CLASS_DATA, '_Shared')
    os.makedirs(shared_dir, exist_ok=True)
    cs_path = os.path.join(shared_dir, 'CustomBitField.cs')
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write(_CUSTOM_BIT_FIELD_CS)
    return cs_path


# ---------------------------------------------------------------------------
# フィールド -> C# field / read コード生成
# ---------------------------------------------------------------------------
def _bit_cs_type_and_initial(options):
    """
    bit フィールドの C# 型と初期化式を返す。
    ・sizeMode = manual                                -> CustomBitField(size)
    ・sizeMode = enum/classDataId/customClassDataId     -> CustomBitField<T>(T.A, T.B, ...)
      (T = 参照先の型。<> の中身は参照元によって生成のたびに自動的に決まる)
    """
    size_mode = options.get('sizeMode', 'manual')
    source_name = options.get('sizeSourceName')
    if source_name:
        entries = _bit_source_entries(size_mode, source_name)
        source_cs_type = _bit_source_cs_type(size_mode, source_name)
        if entries and source_cs_type:
            cs_type = f"GameCore.Classes.CustomBitField<{source_cs_type}>"
            initial = f"new {cs_type}()"
            return cs_type, initial
    # 手動指定、または参照解決に失敗した場合は非ジェネリック版にフォールバック
    cs_type = 'GameCore.Classes.CustomBitField'
    initial = f"new GameCore.Classes.CustomBitField({options.get('size', 8)})"
    return cs_type, initial


def generate_custom_field(item, type_info):
    type_str = item['type']
    var_name = item['name']
    array_size = item.get('arraySize', 0)
    description = item.get('description', '')
    options = item.get('options') or {}

    enum_list = type_info['enum_list']
    class_list = type_info['class_list']
    class_data_id_list = type_info['class_data_id_list']
    custom_class_list = type_info['custom_class_list']
    custom_class_id_list = type_info['custom_class_id_list']

    # 型名の末尾が "[]" で配列を表す場合(CustomClassDataID の columns など、
    # 専用の arraySize を持たず型名だけで配列表現するケース)は、
    # app.py の ClassDataID 側(`"[]" in col['type']`)と同じく常に可変長(List)として扱う。
    # (固定長配列はここでは表現されないため、List 一択にする)
    if isinstance(type_str, str) and type_str.endswith('[]'):
        type_str = type_str[:-2]
        if array_size == 0:
            array_size = -1

    attribute = ''  # [Range]等の属性

    # --- 型の解決 ---------------------------------------------------------
    if type_str == 'bit':
        cs_type, initial = _bit_cs_type_and_initial(options)
    elif type_str == 'color':
        cs_type = 'UnityEngine.Color'
        initial = 'new UnityEngine.Color(1f, 1f, 1f, 1f)'
    elif type_str == 'bezier':
        cs_type = 'UnityEngine.AnimationCurve'
        initial = 'new UnityEngine.AnimationCurve()'
    elif type_str in enum_list:
        cs_type = f"GameCore.Enums.{type_str}ID"
        initial = f"GameCore.Enums.{type_str}ID.None"
    elif type_str in class_list:
        cs_type = f"GameCore.Classes.{type_str}"
        initial = f"new {cs_type}()"
    elif type_str in class_data_id_list:
        cs_type = f"GameCore.Tables.ID.{type_str}TableID"
        initial = f"{cs_type}.None"
    elif type_str in custom_class_id_list:
        # 他の CustomClassDataID を参照する場合も ClassDataID 同様、TableID enum として扱う
        cs_type = f"GameCore.Tables.ID.{type_str}TableID"
        initial = f"{cs_type}.None"
    elif type_str in custom_class_list:
        cs_type = f"GameCore.Classes.{type_str}"
        initial = f"new {cs_type}()"
    elif type_str == 'Vector2':
        cs_type = 'UnityEngine.Vector2'
        initial = 'new UnityEngine.Vector2()'
    elif type_str == 'Vector3':
        cs_type = 'UnityEngine.Vector3'
        initial = 'new UnityEngine.Vector3()'
    elif type_str.lower() in ('int', 'byte', 'short', 'long', 'uint'):
        cs_type = type_str.lower()
        initial = '0'
        if type_str in NUMERIC_TYPES and (options.get('min') is not None and options.get('max') is not None):
            attribute = f"        [UnityEngine.Range({options['min']}, {options['max']})]\n"
    elif type_str.lower() in ('float', 'double', 'decimal'):
        cs_type = type_str.lower()
        initial = '0.0f' if type_str.lower() == 'float' else '0.0'
        if type_str in NUMERIC_TYPES and (options.get('min') is not None and options.get('max') is not None):
            attribute = f"        [UnityEngine.Range({options['min']}f, {options['max']}f)]\n"
    elif type_str.lower() == 'bool':
        cs_type = 'bool'
        initial = 'false'
    elif type_str.lower() == 'string':
        cs_type = 'string'
        initial = '""'
    else:
        cs_type = type_str
        initial = f"new {type_str}()"

    is_list = array_size == -1
    is_array = array_size > 0
    if is_list:
        cs_type_full = f"List<{cs_type}>"
        initial_full = f"new List<{cs_type}>()"
    elif is_array:
        cs_type_full = f"{cs_type}[]"
        initial_full = f"new {cs_type}[{array_size}]"
    else:
        cs_type_full = cs_type
        initial_full = initial

    # --- 単一要素の読み込みコード ------------------------------------------
    def read_single(target_expr, assign=True):
        prefix = f"{target_expr} = " if assign else ''
        if type_str == 'bit':
            # initial は CustomBitField(size) か CustomBitField<T>(T.A, T.B, ...) のどちらか
            # (フィールド宣言時と同じ order で再構築してから、バイナリの中身だけ Read で読み込む)
            return f"                {target_expr}.Read(reader);\n"
        if type_str == 'color':
            return f"                {prefix}new UnityEngine.Color(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n"
        if type_str == 'bezier':
            code = f"                {{ int __kc = reader.ReadInt32(); var __keys = new UnityEngine.Keyframe[__kc];\n"
            code += "                  for (int __k = 0; __k < __kc; __k++) { __keys[__k] = new UnityEngine.Keyframe(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()); }\n"
            code += f"                  {target_expr} = new UnityEngine.AnimationCurve(__keys); }}\n"
            return code
        if type_str in enum_list or type_str in class_data_id_list or type_str in custom_class_id_list:
            return f"                {prefix}({cs_type})Enum.ToObject(typeof({cs_type}), reader.ReadInt32());\n"
        if type_str in class_list or type_str in custom_class_list:
            return f"                {prefix}new {cs_type}(); {target_expr}.Read(reader);\n"
        if type_str.lower() == 'string':
            return (f"                {{ int __len = reader.ReadInt32(); "
                     f"{target_expr} = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(__len)); }}\n")
        if type_str == 'Vector2':
            return f"                {prefix}new UnityEngine.Vector2(reader.ReadSingle(), reader.ReadSingle());\n"
        if type_str == 'Vector3':
            return f"                {prefix}new UnityEngine.Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());\n"
        if type_str.lower() in TYPE_MAP:
            return f"                {prefix}reader.{TYPE_MAP[type_str.lower()]['cs_read']}();\n"
        return f"                {prefix}default; // Unsupported type: {type_str}\n"

    read_code = ""
    if is_list:
        read_code = f"            {var_name} = new List<{cs_type}>();\n"
        read_code += f"            int {var_name}_count = reader.ReadInt32();\n"
        read_code += f"            for (int i = 0; i < {var_name}_count; i++) {{\n"
        read_code += f"                {cs_type} __v_{var_name} = default;\n"
        read_code += read_single(f"__v_{var_name}")
        read_code += f"                {var_name}.Add(__v_{var_name});\n"
        read_code += "            }\n"
    elif is_array:
        read_code = f"            {var_name} = new {cs_type}[{array_size}];\n"
        read_code += f"            for (int i = 0; i < {array_size}; i++) {{\n"
        read_code += read_single(f"{var_name}[i]")
        read_code += "            }\n"
    else:
        read_code = read_single(var_name)

    field_decl = (
        f"{attribute}"
        f"        [SerializeField]\n"
        f"        protected {cs_type_full} {var_name} = {initial_full};\n"
        f"        public {cs_type_full} {var_name[0].upper()}{var_name[1:]} {{ get => {var_name}; }} // {description}\n"
    )

    extension_code = ''  # CustomBitField<T> により拡張メソッド方式は不要になったため常に空

    return {'field': field_decl, 'read': read_code, 'extension': extension_code}


def _generate_bit_extension_code(item, var_name):
    """
    [非推奨] 旧方式(拡張メソッドで ToIndex/FromIndex を提供する方式)の名残。
    現在は generate_custom_field 内で CustomBitField<T> (T=参照先の型) を直接
    フィールドの型として使うため、この拡張クラスは不要になった。
    呼び出し元との互換のため関数自体は残しているが、常に空文字を返す。
    """
    return ''


# ---------------------------------------------------------------------------
# CustomClassData C#生成
# ---------------------------------------------------------------------------
@bp.route('/generate-custom-class/<name>', methods=['POST'])
def generate_custom_class_cs(name):
    try:
        fields = request.get_json() or []
        type_info = get_extended_type_lists()
        out_dir = _path(CUSTOM_CLASS_DATA, name)
        os.makedirs(out_dir, exist_ok=True)

        # 共有のビットフィールドクラスを最新化
        bit_cs_path = _ensure_custom_bit_field_cs()

        base_cs_path = os.path.join(out_dir, f"Base{name}.cs")
        with open(base_cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
            f.write("namespace GameCore.Classes\n{\n")
            f.write("     [Serializable]\n")
            f.write(f"    public class Base{name} : BaseCustomClassData\n    {{\n")
            read_codes = []
            for item in fields:
                field_data = generate_custom_field(item, type_info)
                f.write(field_data['field'])
                read_codes.append(field_data['read'])
                _write_bit_extension_file(out_dir, field_data.get('extension'))
            f.write(f"\n        public Base{name}() : base() {{ }}\n")
            f.write("        public override void Read(BinaryReader reader)\n        {\n")
            for read_code in read_codes:
                f.write(read_code)
            f.write("        }\n")
            f.write("    }\n}\n")

        cs_path = os.path.join(out_dir, f"{name}.cs")
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
            f.write("namespace GameCore.Classes\n{\n")
            f.write("     [Serializable]\n")
            f.write(f"    public class {name} : Base{name}\n    {{\n")
            f.write("    }\n}\n")

        return jsonify({"message": f"C#ファイルを生成しました: {cs_path} (共有: {bit_cs_path})"})
    except Exception as e:
        logger.error(f"CustomClassData C#生成エラー({name}): {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# CustomClassDataID 一覧管理
# ---------------------------------------------------------------------------
@bp.route('/custom-class-data-id', methods=['GET', 'POST', 'PATCH'])
def manage_custom_class_data_id():
    _ensure_dirs()
    file_path = _path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json')

    if request.method == 'GET':
        return jsonify(_load_json(file_path, []))

    if request.method == 'POST':
        try:
            body = request.get_json()
            name = (body or {}).get('name', '').strip()
            if not name:
                return jsonify({"error": "名前は必須です"}), 400
            if ':' in name:
                return jsonify({"error": "名前に':'を含めることはできません"}), 400
            data = _load_json(file_path, [])
            if any(item['name'] == name for item in data):
                return jsonify({"error": f"CustomClassDataID {name} はすでに存在します"}), 400
            max_id = max([item['id'] for item in data], default=0) + 1
            entry = {"id": max_id, "name": name}
            data.append(entry)
            _save_json(file_path, data)
            _save_json(_path(CUSTOM_CLASS_DATA_ID, name, f"{name}.json"), {"columns": [], "rows": []})
            return jsonify({"message": f"CustomClassDataID {name} を作成しました", "data": entry}), 201
        except Exception as e:
            logger.error(f"CustomClassDataID作成エラー: {e}")
            return jsonify({"error": str(e)}), 500

    if request.method == 'PATCH':
        try:
            delete_name = request.get_json().get('name')
            data = _load_json(file_path, [])
            data = [item for item in data if item['name'] != delete_name]
            _save_json(file_path, data)
            target_dir = _path(CUSTOM_CLASS_DATA_ID, delete_name)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            return jsonify({"message": f"CustomClassDataID {delete_name} を削除しました"})
        except Exception as e:
            logger.error(f"CustomClassDataID削除エラー: {e}")
            return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# CustomClassDataID タグ機能 (ClassDataID の app.py 側タグ機能と同等)
# ---------------------------------------------------------------------------
#
# タグは custom_class_data_id ディレクトリ配下に tags.json として保存する:
#   [{"id": 1, "name": "戦闘"}, {"id": 2, "name": "UI"}, ...]
#
# 各 CustomClassDataID エントリ(custom_class_data_id_list.json の各要素)には
# "tag" フィールド(タグ名。未設定は null)を追加する。
# ------------------------------------------------------------
@bp.route('/custom-class-data-id-tags', methods=['GET', 'POST', 'PATCH'])
def manage_custom_class_data_id_tags():
    _ensure_dirs()
    file_path = _path(CUSTOM_CLASS_DATA_ID, 'tags.json')

    if request.method == 'GET':
        return jsonify(_load_json(file_path, []))

    if request.method == 'POST':
        try:
            new_tag = request.get_json()
            if not new_tag or not new_tag.get('name'):
                return jsonify({"error": "タグ名は必須です"}), 400
            name = new_tag['name']

            data = _load_json(file_path, [])
            if any(t['name'] == name for t in data):
                return jsonify({"error": f"タグ {name} はすでに存在します"}), 400

            max_id = max([t['id'] for t in data], default=0) + 1
            new_entry = {"id": max_id, "name": name}
            data.append(new_entry)
            _save_json(file_path, data)

            return jsonify({"message": f"タグ {name} を作成しました", "data": new_entry}), 201
        except Exception as e:
            logger.error(f"CustomClassDataIDタグ作成エラー: {e}")
            return jsonify({"error": str(e)}), 500

    if request.method == 'PATCH':
        # タグ削除。割り当て済みのCustomClassDataIDエントリからも解除する
        try:
            delete_name = request.get_json().get('name')
            if not delete_name:
                return jsonify({"error": "削除するタグ名を指定してください"}), 400

            data = _load_json(file_path, None)
            if data is None:
                return jsonify({"error": "tags.jsonが見つかりません"}), 404
            if not any(t['name'] == delete_name for t in data):
                return jsonify({"error": f"タグ {delete_name} が見つかりません"}), 404
            data = [t for t in data if t['name'] != delete_name]
            _save_json(file_path, data)

            # custom_class_data_id_list.json 側の tag も解除
            list_path = _path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json')
            list_data = _load_json(list_path, None)
            if list_data is not None:
                changed = False
                for item in list_data:
                    if item.get('tag') == delete_name:
                        item['tag'] = None
                        changed = True
                if changed:
                    _save_json(list_path, list_data)

            return jsonify({"message": f"タグ {delete_name} を削除しました"})
        except Exception as e:
            logger.error(f"CustomClassDataIDタグ削除エラー: {e}")
            return jsonify({"error": str(e)}), 500


@bp.route('/custom-class-data-id-tags/<int:tag_id>', methods=['PUT'])
def rename_custom_class_data_id_tag(tag_id):
    """タグ名の変更(割り当て済みCustomClassDataIDの tag フィールドも追従して更新)"""
    file_path = _path(CUSTOM_CLASS_DATA_ID, 'tags.json')
    try:
        new_name = request.get_json().get('name')
        if not new_name:
            return jsonify({"error": "新しいタグ名を指定してください"}), 400

        data = _load_json(file_path, None)
        if data is None:
            return jsonify({"error": "tags.jsonが見つかりません"}), 404

        target = next((t for t in data if t['id'] == tag_id), None)
        if not target:
            return jsonify({"error": "指定されたタグが見つかりません"}), 404
        if any(t['name'] == new_name and t['id'] != tag_id for t in data):
            return jsonify({"error": f"タグ {new_name} はすでに存在します"}), 400

        old_name = target['name']
        target['name'] = new_name
        _save_json(file_path, data)

        # custom_class_data_id_list.json 側の tag 名も追従
        list_path = _path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json')
        list_data = _load_json(list_path, None)
        if list_data is not None:
            changed = False
            for item in list_data:
                if item.get('tag') == old_name:
                    item['tag'] = new_name
                    changed = True
            if changed:
                _save_json(list_path, list_data)

        return jsonify({"message": f"タグ名を {old_name} から {new_name} に変更しました"})
    except Exception as e:
        logger.error(f"CustomClassDataIDタグ名変更エラー: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route('/custom-class-data-id/<name>/tag', methods=['PUT'])
def set_custom_class_data_id_tag(name):
    """特定のCustomClassDataIDエントリにタグを割り当てる(tag=nullで未設定に戻す)"""
    list_path = _path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json')
    try:
        tag = request.get_json().get('tag')  # None も許容(未設定に戻す)

        data = _load_json(list_path, None)
        if data is None:
            return jsonify({"error": "custom_class_data_id_list.jsonが見つかりません"}), 404

        target = next((item for item in data if item['name'] == name), None)
        if not target:
            return jsonify({"error": f"CustomClassDataID {name} が見つかりません"}), 404

        # タグが指定されている場合は存在確認
        if tag is not None:
            tags_path = _path(CUSTOM_CLASS_DATA_ID, 'tags.json')
            tag_list = _load_json(tags_path, [])
            if not any(t['name'] == tag for t in tag_list):
                return jsonify({"error": f"タグ {tag} が見つかりません"}), 404

        target['tag'] = tag
        _save_json(list_path, data)

        return jsonify({"message": f"{name} にタグを設定しました", "data": target})
    except Exception as e:
        logger.error(f"CustomClassDataIDタグ割り当てエラー {name}: {e}")
        return jsonify({"error": str(e)}), 500
@bp.route('/custom-class-data-id/<name>', methods=['GET', 'POST', 'DELETE'])
def custom_class_data_id_detail(name):
    file_path = _path(CUSTOM_CLASS_DATA_ID, name, f"{name}.json")

    if request.method == 'GET':
        data = _load_json(file_path, None)
        if data is None:
            return jsonify({"error": f"CustomClassDataID {name} が見つかりません"}), 404
        return jsonify(data)

    if request.method == 'POST':
        try:
            new_data = request.get_json()
            _save_json(file_path, new_data)
            return jsonify({"message": f"{name}.json を保存しました"})
        except Exception as e:
            logger.error(f"CustomClassDataID保存エラー({name}): {e}")
            return jsonify({"error": str(e)}), 500

    if request.method == 'DELETE':
        try:
            os.remove(file_path)
            return jsonify({"message": f"{name}.json を削除しました"})
        except FileNotFoundError:
            return jsonify({"error": "見つかりません"}), 404
        except Exception as e:
            logger.error(f"CustomClassDataID削除エラー({name}): {e}")
            return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# CustomClassDataID C#生成 (TableID enum + データテーブルクラス)
# ---------------------------------------------------------------------------
@bp.route('/generate-custom-class-data-id/<name>', methods=['POST'])
def generate_custom_class_data_id_cs(name):
    try:
        data = request.get_json() or {"columns": [], "rows": []}
        columns = data.get('columns', [])
        rows = data.get('rows', [])
        type_info = get_extended_type_lists()

        out_dir = _path(CUSTOM_CLASS_DATA_ID, name)
        os.makedirs(out_dir, exist_ok=True)
        _ensure_custom_bit_field_cs()

        # --- TableID enum ---------------------------------------------------
        id_cs_path = os.path.join(out_dir, f"{name}TableID.cs")
        with open(id_cs_path, 'w', encoding='utf-8') as f:
            f.write("namespace GameCore.Tables.ID\n{\n")
            f.write(f"    public enum {name}TableID\n    {{\n")
            f.write("        None = 0,\n")
            for i, row in enumerate(rows):
                f.write(f"        {row.get('enum_property', f'{name}_{i}')} = {i + 1},\n")
            f.write("    }\n}\n")

        # --- Row class (各列を型どおりのフィールドとして持つ) ------------------
        row_cs_path = os.path.join(out_dir, f"{name}Row.cs")
        with open(row_cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
            f.write("namespace GameCore.Classes\n{\n")
            f.write(f"    public class {name}Row : BaseCustomClassData\n    {{\n")
            read_codes = []
            for col in columns:
                item = {
                    'name': col['name'],
                    'type': col['type'],
                    'description': col.get('description', ''),
                    'arraySize': col.get('arraySize', 0),
                    'options': col.get('options', {}),
                }
                field_data = generate_custom_field(item, type_info)
                f.write(field_data['field'])
                read_codes.append(field_data['read'])
                _write_bit_extension_file(out_dir, field_data.get('extension'))
            f.write(f"\n        public {name}Row() : base() {{ }}\n")
            f.write("        public override void Read(BinaryReader reader)\n        {\n")
            for rc in read_codes:
                f.write(rc)
            f.write("        }\n")
            f.write("    }\n}\n")

        # --- Table class (行全体を Dictionary で保持し、バイナリから一括読み込みする) ---
        # 従来ここが無く、CustomClassDataID は Row クラスまでしか生成されていなかった。
        # app.py の ClassDataID( {name}Table : BaseClassDataID<...> )と同じ役割のクラスを追加する。
        table_cs_path = os.path.join(out_dir, f"{name}Table.cs")
        with open(table_cs_path, 'w', encoding='utf-8') as f:
            f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\nusing GameCore.Tables.ID;\n\n")
            f.write("namespace GameCore.Tables\n{\n")
            f.write(f"    public class {name}Table : BaseTable\n    {{\n")
            f.write(f"        public static readonly Dictionary<{name}TableID, GameCore.Classes.{name}Row> Table = new Dictionary<{name}TableID, GameCore.Classes.{name}Row>();\n\n")
            f.write("        public override void Read(BinaryReader reader)\n        {\n")
            f.write(f"            {name}Table.Table.Clear();\n")
            f.write("            int rowCount = reader.ReadInt32();\n")
            f.write("            int colCount = reader.ReadInt32();\n")
            f.write("            var colNames = new string[colCount];\n")
            f.write("            var colTypes = new string[colCount];\n")
            f.write("            for (int i = 0; i < colCount; i++) {\n")
            f.write("                int len = reader.ReadInt32();\n")
            f.write("                colNames[i] = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len));\n")
            f.write("                len = reader.ReadInt32();\n")
            f.write("                colTypes[i] = System.Text.Encoding.UTF8.GetString(reader.ReadBytes(len));\n")
            f.write("            }\n")
            f.write("            for (int r = 0; r < rowCount; r++) {\n")
            f.write(f"                var enumVal = ({name}TableID)Enum.ToObject(typeof({name}TableID), reader.ReadInt32());\n")
            f.write(f"                var row = new GameCore.Classes.{name}Row();\n")
            f.write("                row.Read(reader);\n")
            f.write("                Table[enumVal] = row;\n")
            f.write("            }\n")
            f.write("        }\n")
            f.write("\n        public override void Release()\n        {\n")
            f.write(f"            {name}Table.Table.Clear();\n")
            f.write("        }\n")
            f.write("    }\n}\n")

        return jsonify({"message": f"C#ファイルを生成しました: {id_cs_path}, {row_cs_path}, {table_cs_path}"})
    except Exception as e:
        logger.error(f"CustomClassDataID C#生成エラー({name}): {e}")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# CustomClassDataID バイナリ生成 (app.py の ClassDataID 用 generate_binary_data /
# generate-all-binary / TableID / ClassDataHeader / *Core.cs に相当するものが
# CustomClassDataID には無かったため、ここに追加する)
# ---------------------------------------------------------------------------
def _write_custom_single_value(f, value, type_str, options, type_info):
    """1つの値をバイナリへ書き込む(bit/color/bezierを含む拡張型対応、再帰あり)"""
    options = options or {}
    enum_list = type_info['enum_list']
    class_list = type_info['class_list']
    class_data_id_list = type_info['class_data_id_list']
    custom_class_list = type_info['custom_class_list']
    custom_class_id_list = type_info['custom_class_id_list']
    custom_class_schemas = type_info['custom_class_schemas']

    if type_str == 'bit':
        size = int(options.get('size', 8) or 8)
        bits = (value or {}).get('bits') if isinstance(value, dict) else []
        bits = bits or []
        f.write(struct.pack('i', size))
        nwords = (size + 63) // 64
        if size <= 64:
            word = 0
            for idx in bits:
                if isinstance(idx, int) and 0 <= idx < size:
                    word |= (1 << idx)
            f.write(struct.pack('Q', word))
        else:
            words = [0] * nwords
            for idx in bits:
                if isinstance(idx, int) and 0 <= idx < size:
                    words[idx // 64] |= (1 << (idx % 64))
            for w in words:
                f.write(struct.pack('Q', w))
        return

    if type_str == 'color':
        c = value if isinstance(value, dict) else {}
        f.write(struct.pack('ffff', float(c.get('r', 1) or 0), float(c.get('g', 1) or 0),
                             float(c.get('b', 1) or 0), float(c.get('a', 1) or 0)))
        return

    if type_str == 'bezier':
        pts = (value or {}).get('points', []) if isinstance(value, dict) else []
        f.write(struct.pack('i', len(pts)))
        for p in pts:
            f.write(struct.pack('ffff', float(p.get('time', 0) or 0), float(p.get('value', 0) or 0),
                                 float(p.get('inTangent', 0) or 0), float(p.get('outTangent', 0) or 0)))
        return

    if type_str.lower() == 'string':
        val_bytes = (value or '').encode('utf-8') if isinstance(value, str) else b''
        f.write(struct.pack('i', len(val_bytes)))
        f.write(val_bytes)
        return

    if type_str == 'Vector2':
        x, y = value if isinstance(value, (list, tuple)) and len(value) >= 2 else [0.0, 0.0]
        f.write(struct.pack('ff', float(x or 0), float(y or 0)))
        return

    if type_str == 'Vector3':
        x, y, z = value if isinstance(value, (list, tuple)) and len(value) >= 3 else [0.0, 0.0, 0.0]
        f.write(struct.pack('fff', float(x or 0), float(y or 0), float(z or 0)))
        return

    if type_str.lower() in PACK_MAP:
        type_lower = type_str.lower()
        default_value = False if type_lower == 'bool' else 0
        safe_value = value if value is not None else default_value
        try:
            if type_lower == 'bool':
                safe_value = bool(safe_value)
            elif type_lower in ('float', 'double', 'decimal'):
                safe_value = float(safe_value)
            else:
                safe_value = int(safe_value)
        except (TypeError, ValueError):
            safe_value = default_value
        f.write(struct.pack(PACK_MAP[type_lower], safe_value))
        return

    if type_str in enum_list:
        property_name = value.split('.')[-1] if isinstance(value, str) else None
        if property_name:
            enum_items = _load_json(_path(ENUM, type_str, f"{type_str}.json"), [])
            # generate_enum_cs は item['value'] をそのまま C# の enum 値として書き出すため、
            # バイナリ側もそれに合わせて value を優先する(無ければ id にフォールバック)。
            actual = next(
                (it.get('value', it.get('id', 0)) for it in enum_items if it.get('property') == property_name),
                0,
            )
        else:
            actual = int(value) if isinstance(value, (int, float)) else 0
        f.write(struct.pack('i', int(actual)))
        return

    if type_str in class_data_id_list or type_str in custom_class_id_list:
        base_dir = CLASS_DATA_ID if type_str in class_data_id_list else CUSTOM_CLASS_DATA_ID
        property_name = value.split('.')[-1] if isinstance(value, str) else None
        if property_name:
            data = _load_json(_path(base_dir, type_str, f"{type_str}.json"), {'rows': []})
            actual = next((row.get('id', 0) for row in data.get('rows', []) if row.get('enum_property') == property_name), 0)
        else:
            actual = int(value) if isinstance(value, (int, float)) else 0
        f.write(struct.pack('i', actual))
        return

    if type_str in class_list:
        schema = _load_json(_path(CLASS_DATA, type_str, f"{type_str}.class.json"), [])
        _write_custom_schema_value(f, value, schema, type_info)
        return

    if type_str in custom_class_list:
        schema = custom_class_schemas.get(type_str) or _load_json(
            _path(CUSTOM_CLASS_DATA, type_str, f"{type_str}.customclass.json"), [])
        _write_custom_schema_value(f, value, schema, type_info)
        return

    f.write(struct.pack('i', 0))  # 未サポート型


def _write_custom_schema_value(f, value, schema, type_info):
    """classData / customClassData の再帰書き込み(値は {フィールド名: 値} の辞書)"""
    value = value if isinstance(value, dict) else {}
    for field in schema:
        _write_custom_field_value(
            f, field, value.get(field.get('name')), type_info
        )


def _write_custom_field_value(f, item, value, type_info):
    """item: {'type','arraySize','options'} を持つ列/フィールド定義1つ分の書き込み(配列/リスト対応)"""
    array_size = item.get('arraySize', 0)
    type_str = item.get('type')
    options = item.get('options') or {}

    # 型名の末尾が "[]" で配列を表す場合(CustomClassDataID の columns など、
    # 専用の arraySize を持たず型名だけで配列表現するケース)は、
    # generate_custom_field(C#生成側)と揃えて常に可変長(List)として書き込む。
    if isinstance(type_str, str) and type_str.endswith('[]'):
        type_str = type_str[:-2]
        if array_size == 0:
            array_size = -1

    if array_size == -1:  # List
        values = value if isinstance(value, list) else []
        f.write(struct.pack('i', len(values)))
        for v in values:
            _write_custom_single_value(f, v, type_str, options, type_info)
    elif array_size > 0:  # 固定長配列
        values = value if isinstance(value, list) else []
        for i in range(array_size):
            v = values[i] if i < len(values) else None
            _write_custom_single_value(f, v, type_str, options, type_info)
    else:
        _write_custom_single_value(f, value, type_str, options, type_info)


def generate_custom_binary_data(name, json_data, type_info):
    """CustomClassDataID 1テーブル分をバイナリ化する(app.pyのgenerate_binary_data相当)"""
    f = io.BytesIO()
    rows = json_data.get('rows', [])
    columns = json_data.get('columns', [])

    f.write(struct.pack('i', len(rows)))
    f.write(struct.pack('i', len(columns)))

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
            cell = (row.get('data') or {}).get(col['name'], {})
            value = cell.get('value') if isinstance(cell, dict) else cell
            _write_custom_field_value(f, col, value, type_info)

    return f.getvalue()


@bp.route('/generate-all-custom-binary', methods=['POST'])
def generate_all_custom_binary():
    """
    全 CustomClassDataID を1つの all_custom_class_data.bytes にまとめて書き出す。
    app.py の /api/generate-all-binary (ClassDataID用) に相当するものが
    CustomClassDataID には存在していなかったため追加。
    """
    try:
        id_list = _load_json(_path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json'), [])
        type_info = get_extended_type_lists()

        sections = {}
        for item in id_list:
            item_name = item['name']
            json_data = _load_json(_path(CUSTOM_CLASS_DATA_ID, item_name, f"{item_name}.json"), {'columns': [], 'rows': []})
            sections[item_name] = generate_custom_binary_data(item_name, json_data, type_info)

        # ヘッダーサイズ: [count:4] + 各エントリ[id:4][name_len:4][name:N][offset:8][size:4]
        header_size = 4
        for item in id_list:
            header_size += 4 + 4 + len(item['name'].encode('utf-8')) + 8 + 4

        current_offset = header_size
        offsets = {}
        for item in id_list:
            offsets[item['name']] = current_offset
            current_offset += len(sections[item['name']])

        header = bytearray()
        header.extend(struct.pack('i', len(id_list)))
        for item in id_list:
            item_name = item['name']
            name_encoded = item_name.encode('utf-8')
            header.extend(struct.pack('i', item['id']))
            header.extend(struct.pack('i', len(name_encoded)))
            header.extend(name_encoded)
            header.extend(struct.pack('q', offsets[item_name]))
            header.extend(struct.pack('i', len(sections[item_name])))

        out_path = _path(CUSTOM_CLASS_DATA_ID, 'all_custom_class_data_id.bytes')
        with open(out_path, 'wb') as bf:
            bf.write(header)
            for item in id_list:
                bf.write(sections[item['name']])

        logger.info("Generated all_custom_class_data_id.bytes")
        return jsonify({"message": f"all_custom_class_data_id.bytes を生成しました: {out_path}"})
    except Exception as e:
        logger.error(f"CustomClassDataID 全バイナリ生成エラー: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route('/generate-custom-table-id', methods=['POST'])
def generate_custom_table_id():
    """
    全 CustomClassDataID を束ねるマスター登録用enum(CustomTableID)を生成する。
    app.py の /api/generate-table-id (ClassDataID用 TableID.cs) に相当。
    """
    try:
        id_list = _load_json(_path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json'), [])
        cs_content = "namespace GameCore.Enums\n{\n"
        cs_content += "    public enum CustomTableID\n    {\n"
        cs_content += "        None = 0,\n"
        for item in id_list:
            cs_content += f"        {item['name']} = {item['id']},\n"
        max_id = max([item['id'] for item in id_list], default=0) + 1
        cs_content += f"        Max = {max_id}\n"
        cs_content += "    }\n}\n"

        out_path = _path(CUSTOM_CLASS_DATA_ID, 'CustomTableID.cs')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(cs_content)

        return jsonify({"message": f"CustomTableID enum を生成しました: {out_path}"})
    except Exception as e:
        logger.error(f"CustomTableID生成エラー: {e}")
        return jsonify({"error": str(e)}), 500


_CUSTOM_CLASS_DATA_HEADER_CS = '''using System;
using System.IO;
using System.Collections.Generic;
using GameCore.Enums;

namespace GameCore.Tables
{
    public class CustomClassDataHeader
    {
        public Dictionary<CustomTableID, (string Name, long Offset, int Size)> Entries = new Dictionary<CustomTableID, (string, long, int)>();

        public CustomClassDataHeader(BinaryReader reader)
        {
            int count = reader.ReadInt32();
            for (int i = 0; i < count; i++)
            {
                int id = reader.ReadInt32();
                CustomTableID tableId = (CustomTableID)Enum.ToObject(typeof(CustomTableID), id);
                int nameLen = reader.ReadInt32();
                string name = new string(reader.ReadChars(nameLen));
                long offset = reader.ReadInt64();
                int size = reader.ReadInt32();
                Entries[tableId] = (name, offset, size);
            }
        }

        public TTable GetData<TTable>(CustomTableID id, BinaryReader reader) where TTable : BaseTable, new()
        {
            if (!Entries.TryGetValue(id, out var entry)) return null;
            reader.BaseStream.Seek(entry.Offset, SeekOrigin.Begin);
            TTable data = new TTable();
            data.Read(reader);
            return data;
        }
    }
}
'''

_CUSTOM_CLASS_DATA_ID_CORE_CS = '''using Cysharp.Threading.Tasks;
using GameCore;
using GameCore.Tables;
using System.IO;
using System.Threading;
using System;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

public class CustomClassDataIDCore : BaseSingleton<CustomClassDataIDCore>
{
    private CustomClassDataHeader m_classDataTables;
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

    /// <summary>
    /// all_custom_class_data.bin を読み込み、BinaryReader をラムダに渡して実行
    /// </summary>
    public async UniTask LoadClassDataAsync(Func<BinaryReader, CustomClassDataHeader, UniTask> onLoaded, bool addressable = false)
    {
        if (cts == null) cts = this.GetCancellationTokenOnDestroy();
        if (isLoaded) return;

        string path = addressable == true ? SupportFiles.CUSTOM_CLASS_DATA_ID_BIN_FILE : SupportFiles.ALL_CUSTOM_CLASS_DATA_ID_BIN;

        try
        {
            if (!addressable)
            {
                using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read))
                using (BinaryReader reader = new BinaryReader(fs))
                {
                    if (m_classDataTables == null) m_classDataTables = new CustomClassDataHeader(reader);
                    if (onLoaded != null)
                    {
                        await ExecuteOnThreadPoolAndReturn(onLoaded, reader, m_classDataTables, cts);
                    }
                    isLoaded = true;
                }
            }
            else
            {
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
                    if (m_classDataTables == null) m_classDataTables = new CustomClassDataHeader(reader);
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
            Debug.LogWarning("CustomClassDataIDCoreの読み込みがキャンセルされました。");
        }
        catch (Exception ex)
        {
            Debug.LogError($"読み込み中にエラーが発生: {ex}");
        }
    }

    private async UniTask ExecuteOnThreadPoolAndReturn(
        Func<BinaryReader, CustomClassDataHeader, UniTask> action,
        BinaryReader reader,
        CustomClassDataHeader classDataHeader,
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
'''


def _ensure_support_files_custom_entries():
    """
    SupportFiles.cs は app.py 側で最初の1回だけ自動生成される既存ファイルのため、
    ここでは中身を丸ごと書き換えたりはせず、CustomClassDataID 用の定数
    (CUSTOM_ID_FOLDER / CUSTOM_ID_BIN_FILE / ALL_CUSTOM_ID_BIN) が無ければ
    該当箇所の直後に追記するだけに留める(ベストエフォート)。
    """
    sf_path = _path(SCRIPT, 'SupportFiles.cs')
    if not os.path.exists(sf_path):
        return "SupportFiles.cs が見つからないためスキップしました(先にapp.py側の初期化を一度実行してください)"

    with open(sf_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'CUSTOM_ID_BIN_FILE' in content:
        return "SupportFiles.cs は既に対応済みです"

    lines = content.splitlines(keepends=True)
    new_lines = []
    inserted_const = False
    inserted_prop = False
    for line in lines:
        new_lines.append(line)
        if not inserted_const and 'public const string ID_BIN_FILE' in line:
            new_lines.append('\n')
            new_lines.append('        //customClassDataId\n')
            new_lines.append('        public const string CUSTOM_ID_FOLDER = "custom_class_data_id";\n')
            new_lines.append('        public const string CUSTOM_ID_BIN_FILE = "all_custom_class_data.bytes";\n')
            inserted_const = True
        if not inserted_prop and 'public static string ALL_ID_BIN ' in line:
            new_lines.append(
                '        public static string ALL_CUSTOM_ID_BIN => '
                'Path.GetFullPath(Path.Combine(SupportDataPath, CUSTOM_ID_FOLDER, CUSTOM_ID_BIN_FILE)).Replace("\\\\", "/");\n'
            )
            inserted_prop = True

    if not (inserted_const and inserted_prop):
        return ("SupportFiles.cs の想定箇所が見つからず自動追記できませんでした。"
                "CUSTOM_ID_FOLDER / CUSTOM_ID_BIN_FILE / ALL_CUSTOM_ID_BIN を手動で追加してください。")

    with open(sf_path, 'w', encoding='utf-8') as f:
        f.write(''.join(new_lines))
    return "SupportFiles.cs に CustomClassDataID 用の定数を追記しました"


def generate_custom_tags_load_script():
    """
    custom_class_data_id/tags.json を元に、タグ名ごとに
    ・LoadAsync{タグ名} / Load{タグ名} (そのタグが付いたテーブルだけを読み込む)
    ・Release{タグ名}                  (そのタグが付いたテーブルだけを解放する)
    を持つ CustomTableIdUtils.cs を生成する。
    app.py の generate_tags_load_script() (ClassDataID用 TableIdUtils) と
    同じ考え方だが、「リリース(解放)」にも対応させている。
    """
    tags_path = _path(CUSTOM_CLASS_DATA_ID, 'tags.json')
    tags = _load_json(tags_path, None)
    if tags is None:
        return  # タグ未使用のプロジェクトでは何もしない

    id_list = _load_json(_path(CUSTOM_CLASS_DATA_ID, 'custom_class_data_id_list.json'), [])

    dict_tags_scripts = {}

    for tag in tags:
        tag_name = tag['name']
        tagged_items = [item['name'] for item in id_list if item.get('tag') == tag_name]

        lines = []
        indent = 0

        def add(text=""):
            lines.append("    " * indent + text)

        # -------------------------
        # 非同期ロード
        # -------------------------
        add(f"public static async UniTask LoadAsync{tag_name}(Action action = null)")
        add("{")
        indent += 1
        add("await CustomClassDataIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
        add("{")
        indent += 1
        for item_name in tagged_items:
            add(f"header.GetData<GameCore.Tables.{item_name}Table>(GameCore.Enums.CustomTableID.{item_name}, reader);")
            add("await UniTask.Yield();")
        add("action?.Invoke();")
        add("await UniTask.CompletedTask;")
        indent -= 1
        add("});")
        indent -= 1
        add("}")
        add()

        # -------------------------
        # 同期ロード
        # -------------------------
        add(f"public static void Load{tag_name}(Action action = null)")
        add("{")
        indent += 1
        add("UniTask.Action(async () =>")
        add("{")
        indent += 1
        add("await CustomClassDataIDCore.Instance.LoadClassDataAsync(async (reader, header) =>")
        add("{")
        indent += 1
        for item_name in tagged_items:
            add(f"header.GetData<GameCore.Tables.{item_name}Table>(GameCore.Enums.CustomTableID.{item_name}, reader);")
        add("action?.Invoke();")
        add("await UniTask.CompletedTask;")
        indent -= 1
        add("});")
        indent -= 1
        add("}).Invoke();")
        indent -= 1
        add("}")
        add()

        # -------------------------
        # リリース(解放): タグに属するテーブルの静的Dictionaryをクリアする
        # -------------------------
        add(f"public static void Release{tag_name}()")
        add("{")
        indent += 1
        for item_name in tagged_items:
            add(f"GameCore.Tables.{item_name}Table.Table.Clear();")
        indent -= 1
        add("}")
        add()

        dict_tags_scripts[tag_name] = lines

    append_str = "\n".join("\n".join(lines) for lines in dict_tags_scripts.values())

    code_str = f"""
using System;
using Cysharp.Threading.Tasks;
using System.Collections.Generic;

namespace GameCore.Tables.ID
{{
    // custom_class_data_id のタグ設定から自動生成。
    // タグごとに Load(非同期/同期) と Release(解放) をまとめて呼び出せる。
    public static class CustomTableIdUtils
    {{
{textwrap.indent(append_str, '        ')}
    }}
}}
"""

    cs_path = _path(CUSTOM_CLASS_DATA_ID, 'CustomTableIdUtils.cs')
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write(code_str)


@bp.route('/generate-custom-cs-header', methods=['POST'])
def generate_custom_cs_header():
    """
    CustomClassDataHeader.cs (全テーブルのオフセット表) と、
    それを読み込む CustomClassDataIDCore.cs (シングルトンローダー) を生成する。
    app.py の /api/generate-all-cs-header (ClassDataID用) に相当するものが
    CustomClassDataID には存在していなかったため追加。
    """
    try:
        header_path = _path(CUSTOM_CLASS_DATA_ID, 'CustomClassDataHeader.cs')
        with open(header_path, 'w', encoding='utf-8') as f:
            f.write(_CUSTOM_CLASS_DATA_HEADER_CS)

        core_path = _path(CUSTOM_CLASS_DATA_ID, 'CustomClassDataIDCore.cs')
        with open(core_path, 'w', encoding='utf-8') as f:
            f.write(_CUSTOM_CLASS_DATA_ID_CORE_CS)

        generate_custom_tags_load_script()

        support_note = _ensure_support_files_custom_entries()

        return jsonify({
            "message": f"C#ヘッダーを生成しました: {header_path}, {core_path}",
            "supportFilesNote": support_note,
        })
    except Exception as e:
        logger.error(f"CustomClassDataHeader生成エラー: {e}")
        return jsonify({"error": str(e)}), 500


# =====================================================================================
def register(app, data_dir):
    """app.py から呼び出すエントリポイント。"""
    _state['DATA_DIR'] = data_dir
    _ensure_dirs()
    app.register_blueprint(bp)
    logger.info("customclassdata blueprint registered")