import math
import os
import sys
import json
import logging

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
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..",".." ,"data"))


CLASS_DATA_ID = 'class-data-id'
CLASS_DATA_MATRIX_ID = 'class-data-matrix-id'
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ENUM = 'enum'
CLASS_DATA = 'class-data'
STATE_DATA = 'state-data'

SCRIPT = 'Script'
OBJECTPOOL = 'ObjectPool'
EDITOR = "Editor"
DEBUG = "Debug"
LOG = "Log"

SUBMODULE = "submodule"
PLUGIN = "Plugin"


SAVE_DATA_DIR = os.path.join(DATA_DIR, "save-data")
SAVE_DATA_CUSTOM_DIR = os.path.join(SAVE_DATA_DIR, "custom-data")

# ========================
# 1. 更新した TYPE_MAP（Pythonはそのまま、JSはDataView用に廃止 → 直接実装）
# ========================
PY_TYPE_MAP = {  # Pythonのreader用（変更なし）
    'int': {'py_read': 'read_int32'},
    'byte': {'py_read': 'read_byte'},
    'short': {'py_read': 'read_int16'},
    'long': {'py_read': 'read_int64'},
    'float': {'py_read': 'read_float'},
    'double': {'py_read': 'read_double'},
    'bool': {'py_read': 'read_bool'},
    'string': {'py_read': 'read_string'},
    'char': {'py_read': 'read_char'},
}

# JSはDataView + offset直接実装にするのでTYPE_MAP不要（BinaryReaderは他の用途で残す）

# ========================
# 2. Python版フィールド生成（load_json追加 + import用に型情報を返す）
# ========================
def generate_python_field(item, enum_list, class_list, class_id_list):
    type_str = item['type'].replace("[]", "")
    var_name = item['name']
    array_size = item.get('arraySize', 0)
    description = item.get('description', '')

    # 型正規化（短いクラス名だけ使う）
    short_type = type_str.split('.')[-1].replace("TableID", "").replace("ID", "") # クラスIDはIDを外す   
    is_enum = type_str in enum_list or short_type in enum_list
    is_class = type_str in class_list or short_type in class_list
    is_table_id = type_str in class_id_list or short_type in class_id_list

    if is_enum or is_table_id:
        py_type =  type_str.split('.')[-1]
    elif is_class:
        py_type = short_type
    elif type_str.lower() in ['vector2', 'vector3']:
        py_type = type_str.lower()
    elif type_str.lower() in PY_TYPE_MAP:
        py_type = type_str.lower()
    else:
        py_type = type_str

    is_list = array_size == -1
    is_array = array_size > 0

    # __init__用の初期値
    if py_type in ['int', 'byte', 'short', 'long']:
        initial = '0'
    elif py_type in ['float', 'double']:
        initial = '0.0'
    elif py_type == 'bool':
        initial = 'False'
    elif py_type == 'string' or py_type == 'char':
        initial = '""'
    elif py_type == 'vector2':
        initial = '[0.0, 0.0]'
    elif py_type == 'vector3':
        initial = '[0.0, 0.0, 0.0]'
    elif is_class:
        initial = f"{py_type}()"
    elif is_enum or is_table_id:
        initial = f"{py_type}.NONE"
    else:
        initial = '0'

    # readコード（readerオブジェクト使用）
    read_code = ""
    if is_list:
        read_code = f"        self.{var_name} = []\n"
        read_code += f"        count = reader.{PY_TYPE_MAP['int']['py_read']}()\n"
        read_code += f"        for _ in range(count):\n"
        indent = "            "
    elif is_array:
        read_code = f"        self.{var_name} = [None] * {array_size}\n"
        read_code += f"        for i in range({array_size}):\n"
        indent = "            "
    else:
        indent = "        "

    if is_list or is_array:
        if py_type == 'vector2':
            line = f"{indent}    self.{var_name}.append([reader.read_float(), reader.read_float()])\n" if is_list else f"{indent}    self.{var_name}[i] = [reader.read_float(), reader.read_float()]\n"
        elif py_type == 'vector3':
            line = f"{indent}    self.{var_name}.append([reader.read_float(), reader.read_float(), reader.read_float()])\n" if is_list else f"{indent}    self.{var_name}[i] = [reader.read_float(), reader.read_float(), reader.read_float()]\n"
        elif py_type in PY_TYPE_MAP:
            py_read = PY_TYPE_MAP[py_type]['py_read']
            line = f"{indent}    self.{var_name}.append(reader.{py_read}())\n" if is_list else f"{indent}    self.{var_name}[i] = reader.{py_read}()\n"
        elif is_enum or is_table_id:
            line = f"{indent}    self.{var_name}.append(reader.read_int32())\n" if is_list else f"{indent}    self.{var_name}[i] = reader.read_int32()\n"
        elif is_class:
            line = f"{indent}    add_data = {py_type}()\n"
            line += f"{indent}    add_data.read(reader)\n"
            line += f"{indent}    self.{var_name}.append(add_data)\n" if is_list else f"{indent}    self.{var_name}[i] = add_data\n"
        elif is_enum or is_table_id:
            line = f"{indent}    self.{var_name}.append(reader.read_int32())\n" if is_list else f"{indent}    self.{var_name}[i] = {py_type}(reader.read_int32())\n"
        else:
            line = f"{indent}    self.{var_name}.append({py_type}())\n" if is_list else f"{indent}    self.{var_name}[i] = {py_type}()\n"
        read_code += line
    else:
        if py_type == 'vector2':
            read_code = f"        self.{var_name} = [reader.read_float(), reader.read_float()]\n"
        elif py_type == 'vector3':
            read_code = f"        self.{var_name} = [reader.read_float(), reader.read_float(), reader.read_float()]\n"
        elif is_enum or is_table_id:
            read_code = f"        self.{var_name} = {py_type}(reader.read_int32())\n"
        elif is_class:
            read_code = f"        self.{var_name} = {py_type}()\n"
            read_code += f"        self.{var_name}.read(reader)\n"
        elif py_type in PY_TYPE_MAP:
            py_read = PY_TYPE_MAP[py_type]['py_read']
            read_code = f"        self.{var_name} = reader.{py_read}()\n"
        else:
            read_code = f"        self.{var_name} = {py_type}()  # Unsupported\n"

    # load_jsonコード（JSON対応）
    json_code = f"        self.{var_name} = data.get('{var_name}', {initial})\n"
    if is_class:
        json_code = f"        if '{var_name}' in data and data['{var_name}'] is not None:\n"
        json_code += f"            self.{var_name} = {py_type}()\n"
        json_code += f"            self.{var_name}.load_json(data['{var_name}'])\n"
        json_code += f"        else:\n"
        json_code += f"            self.{var_name} = {initial}\n"
    elif is_list or is_array:
        if is_class:
            json_code = f"        self.{var_name} = []\n"
            json_code += f"        for item in data.get('{var_name}', []):\n"
            json_code += f"            if item is not None:\n"
            json_code += f"                obj = {py_type}()\n"
            json_code += f"                obj.load_json(item)\n"
            json_code += f"                self.{var_name}.append(obj)\n"
            json_code += f"            else:\n"
            json_code += f"                self.{var_name}.append(None)\n"
        else:
            json_code = f"        self.{var_name} = data.get('{var_name}', [])\n"

    return {
        'field': f"        self.{var_name} = {initial}  # {description}\n",
        'read': read_code,
        'json': json_code,
        'used_class': py_type if is_class else None,
        'is_enum': is_enum,
        'used_enum': py_type if is_enum else None,
        'is_table_id': is_table_id,
        'used_table_id': py_type if is_table_id else None
    }

# ========================
# 3. JS版フィールド生成（DataView + offset対応 + loadJson + import用）
# ========================
def generate_js_field(item, enum_list, class_list, class_id_list):
    type_str = item['type'].replace("[]", "")
    var_name = item['name']
    array_size = item.get('arraySize', 0)
    description = item.get('description', '')

    short_type = type_str.split('.')[-1].replace("TableID", "").replace("ID", "") # クラスIDはIDを外す   
    is_enum = type_str in enum_list or short_type in enum_list
    is_class = type_str in class_list or short_type in class_list
    is_table_id = type_str in class_id_list or short_type in class_id_list

    if is_enum or is_table_id:
        js_type = type_str.split('.')[-1]
    elif is_class:
        js_type = short_type
    elif type_str.lower() in ['vector2', 'vector3']:
        js_type = type_str.lower()
    else:
        js_type = type_str.lower()

    is_list = array_size == -1
    is_array = array_size > 0

    # constructor用初期値
    if js_type in ['int', 'byte', 'short', 'long']:
        initial = '0'
    elif js_type in ['float', 'double']:
        initial = '0.0'
    elif js_type == 'bool':
        initial = 'false'
    elif js_type == 'string' or js_type == 'char':
        initial = '""'
    elif js_type == 'vector2':
        initial = '[0.0, 0.0]'
    elif js_type == 'vector3':
        initial = '[0.0, 0.0, 0.0]'
    elif is_class:
        initial = f"new {js_type}()"
    elif is_enum or is_table_id:
        initial = f"{js_type}.NONE"
    else:
        initial = '0'

    # readコード（DataView + offset、戻り値で新しいoffsetを返す）
    read_code = ""
    if is_list:
        read_code = f"        let count = view.getInt32(o, true); o += 4;\n"
        read_code += f"        this.{var_name} = [];\n"
        read_code += f"        for (let i = 0; i < count; i++) {{\n"
        indent = "            "
    elif is_array:
        read_code = f"        this.{var_name} = new Array({array_size});\n"
        read_code += f"        for (let i = 0; i < {array_size}; i++) {{\n"
        indent = "            "
    else:
        indent = "        "

    if is_list or is_array:
        if js_type == 'vector2':
            line = f"{indent}    this.{var_name}.push([view.getFloat32(o, true), view.getFloat32(o + 4, true)]); o += 8;\n" if is_list else f"{indent}    this.{var_name}[i] = [view.getFloat32(o, true), view.getFloat32(o + 4, true)]; o += 8;\n"
        elif js_type == 'vector3':
            line = f"{indent}    this.{var_name}.push([view.getFloat32(o, true), view.getFloat32(o + 4, true), view.getFloat32(o + 8, true)]); o += 12;\n" if is_list else f"{indent}    this.{var_name}[i] = [view.getFloat32(o, true), view.getFloat32(o + 4, true), view.getFloat32(o + 8, true)]; o += 12;\n"
        elif js_type == 'int':
            line = f"{indent}    this.{var_name}.push(view.getInt32(o, true)); o += 4;\n" if is_list else f"{indent}    this.{var_name}[i] = view.getInt32(o, true); o += 4;\n"
        elif js_type == 'float':
            line = f"{indent}    this.{var_name}.push(view.getFloat32(o, true)); o += 4;\n" if is_list else f"{indent}    this.{var_name}[i] = view.getFloat32(o, true); o += 4;\n"
        elif js_type == 'double':
            line = f"{indent}    this.{var_name}.push(view.getFloat64(o, true)); o += 8;\n" if is_list else f"{indent}    this.{var_name}[i] = view.getFloat64(o, true); o += 8;\n"
        elif js_type == 'bool':
            line = f"{indent}    this.{var_name}.push(view.getUint8(o) !== 0); o += 1;\n" if is_list else f"{indent}    this.{var_name}[i] = view.getUint8(o) !== 0; o += 1;\n"
        elif js_type == 'string':
            line = f"{indent}    let len = view.getInt32(o, true); o += 4;\n"
            line += f"{indent}    let bytes = new Uint8Array(view.buffer, view.byteOffset + o, len);\n"
            line += f"{indent}    this.{var_name}.push(new TextDecoder('utf-8').decode(bytes)); o += len;\n" if is_list else f"{indent}    this.{var_name}[i] = new TextDecoder('utf-8').decode(bytes); o += len;\n"
        elif is_enum or is_table_id:
            line = f"{indent}    this.{var_name}.push(view.getInt32(o, true)); o += 4;\n" if is_list else f"{indent}    this.{var_name}[i] = view.getInt32(o, true); o += 4;\n"
        elif is_class:
            line = f"{indent}    const add_data = new {js_type}();\n"
            line += f"{indent}    o = add_data.read(view, o);\n"
            line += f"{indent}    this.{var_name}.push(add_data);\n" if is_list else f"{indent}    this.{var_name}[i] = add_data;\n"
        elif is_enum or is_table_id:
            line = f"{indent}    this.{var_name}.push(view.getInt32(o, true)); o += 4;\n" if is_list else f"{indent}    this.{var_name}[i] = {js_type}(view.getInt32(o, true)); o += 4;\n"
        else:
            line = f"{indent}    this.{var_name}.push(0); o += 4; // Unsupported\n" if is_list else f"{indent}    this.{var_name}[i] = 0; o += 4; // Unsupported\n"
        read_code += line
        if is_list or is_array:
            read_code += "        }\n"
    else:
        # 単一値
        if js_type == 'vector2':
            read_code = f"        this.{var_name} = [view.getFloat32(o, true), view.getFloat32(o + 4, true)]; o += 8;\n"
        elif js_type == 'vector3':
            read_code = f"        this.{var_name} = [view.getFloat32(o, true), view.getFloat32(o + 4, true), view.getFloat32(o + 8, true)]; o += 12;\n"
        elif js_type == 'int':
            read_code = f"        this.{var_name} = view.getInt32(o, true); o += 4;\n"
        elif js_type == 'byte':
            read_code = f"        this.{var_name} = view.getUint8(o); o += 1;\n"
        elif js_type == 'short':
            read_code = f"        this.{var_name} = view.getInt16(o, true); o += 2;\n"
        elif js_type == 'long':
            read_code = f"        this.{var_name} = view.getBigInt64(o, true); o += 8;\n"
        elif js_type == 'char':
            read_code = f"        this.{var_name} = String.fromCharCode(view.getUint16(o, true)); o += 2;\n"
        elif js_type == 'uint':
            read_code = f"        this.{var_name} = view.getUint32(o, true); o += 4;\n"
        elif js_type == "int64":
            read_code = f"        this.{var_name} = view.getBigInt64(o, true); o += 8;\n"
        elif js_type == "int32":
            read_code = f"        this.{var_name} = view.getInt32(o, true); o += 4;\n"
        elif js_type == 'float':
            read_code = f"        this.{var_name} = view.getFloat32(o, true); o += 4;\n"
        elif js_type == 'double':
            read_code = f"        this.{var_name} = view.getFloat64(o, true); o += 8;\n"
        elif js_type == 'bool':
            read_code = f"        this.{var_name} = view.getUint8(o) !== 0; o += 1;\n"
        elif js_type == 'string':
            read_code = f"        let len = view.getInt32(o, true); o += 4;\n"
            read_code += f"        let bytes = new Uint8Array(view.buffer, view.byteOffset + o, len);\n"
            read_code += f"        this.{var_name} = new TextDecoder('utf-8').decode(bytes); o += len;\n"
        elif is_enum or is_table_id:
            read_code = f"        this.{var_name} = {js_type}(view.getInt32(o, true)); o += 4;\n"
        elif is_class:
            read_code = f"        this.{var_name} = new {js_type}();\n"
            read_code += f"        o = this.{var_name}.read(view, o);\n"
        else:
            read_code = f"        this.{var_name} = 0; o += 4; // Unsupported\n"

    # loadJsonコード
    json_code = f"        this.{var_name} = data.{var_name} ?? {initial};\n"
    if is_class:
        json_code = f"        if (data.{var_name} !== undefined && data.{var_name} !== null) {{\n"
        json_code += f"            this.{var_name} = new {js_type}();\n"
        json_code += f"            this.{var_name}.loadJson(data.{var_name});\n"
        json_code += f"        }} else {{\n"
        json_code += f"            this.{var_name} = {initial};\n"
        json_code += f"        }}\n"
    elif is_list or is_array:
        if is_class:
            json_code = f"        this.{var_name} = [];\n"
            json_code += f"        for (let item of (data.{var_name} || [])) {{\n"
            json_code += f"            if (item !== null && item !== undefined) {{\n"
            json_code += f"                const obj = new {js_type}();\n"
            json_code += f"                obj.loadJson(item);\n"
            json_code += f"                this.{var_name}.push(obj);\n"
            json_code += f"            }} else {{\n"
            json_code += f"                this.{var_name}.push(null);\n"
            json_code += f"            }}\n"
            json_code += f"        }}\n"
        else:
            json_code = f"        this.{var_name} = data.{var_name} || [];\n"

    return {
        'field': f"        this.{var_name} = {initial}; // {description}\n",
        'read': read_code,
        'json': json_code,
        'used_class': js_type if is_class else None,
        'is_enum': is_enum,
        'used_enum': js_type if is_enum else None,
        'is_table_id': is_table_id,
        'used_table_id': js_type if is_table_id else None
    }

# ========================
# 新規追加：JS版 BinaryReader用フィールド生成（Row/TableID専用）
# ========================
def generate_js_binary_field(item, enum_list, class_list, class_id_list):
    type_str = item['type'].replace("[]", "")
    var_name = item['name']
    array_size = item.get('arraySize', 0)
    description = item.get('description', '')

    short_type = type_str.split('.')[-1].replace("TableID", "").replace("ID", "")  # クラスIDはIDを外す
    is_enum = type_str in enum_list or short_type in enum_list
    is_class = type_str in class_list or short_type in class_list
    is_table_id = type_str in class_id_list or short_type in class_id_list

    if is_enum or is_table_id:
        js_type = type_str.split('.')[-1]
    elif is_class:
        js_type = short_type
    elif type_str.lower() in ['vector2', 'vector3']:
        js_type = type_str.lower()
    else:
        js_type = type_str.lower()

    is_list = array_size == -1
    is_array = array_size > 0

    # constructor初期値
    if js_type in ['int', 'byte', 'short', 'long']:
        initial = '0'
    elif js_type in ['float', 'double']:
        initial = '0.0'
    elif js_type == 'bool':
        initial = 'false'
    elif js_type == 'string' or js_type == 'char':
        initial = '""'
    elif js_type == 'vector2':
        initial = 'null'
    elif js_type == 'vector3':
        initial = 'null'
    elif is_class:
        initial = f"new {js_type}()"
    elif is_enum or is_table_id:
        initial = f"{js_type}.NONE"
    else:
        initial = '0'

    # ========================
    # BinaryReader 用 readコード
    # ========================
    read_code = ""
    if is_list:
        read_code = f"        this.{var_name} = [];\n"
        read_code += f"        const count = reader.readInt32();\n"
        read_code += f"        for (let i = 0; i < count; i++) {{\n"
        indent = "            "
    elif is_array:
        read_code = f"        this.{var_name} = new Array({array_size});\n"
        read_code += f"        for (let i = 0; i < {array_size}; i++) {{\n"
        indent = "            "
    else:
        indent = "        "

    if is_list or is_array:
        if js_type == 'vector2':
            line = f"{indent}    this.{var_name}.push(reader.readVector2());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readVector2();\n"
        elif js_type == 'vector3':
            line = f"{indent}    this.{var_name}.push(reader.readVector3());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readVector3();\n"
        elif js_type == 'int':
            line = f"{indent}    this.{var_name}.push(reader.readInt32());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readInt32();\n"
        elif js_type == 'byte':
            line = f"{indent}    this.{var_name}.push(reader.readByte());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readByte();\n"
        elif js_type == 'short':
            line = f"{indent}    this.{var_name}.push(reader.readInt16());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readInt16();\n"
        elif js_type == 'long':
            line = f"{indent}    this.{var_name}.push(reader.readInt64());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readInt64();\n"
        elif js_type == 'float':
            line = f"{indent}    this.{var_name}.push(reader.readFloat32());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readFloat32();\n"
        elif js_type == 'double':
            line = f"{indent}    this.{var_name}.push(reader.readDouble());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readDouble();\n"
        elif js_type == 'bool':
            line = f"{indent}    this.{var_name}.push(reader.readBoolean());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readBoolean();\n"
        elif js_type == 'string':
            line = f"{indent}    this.{var_name}.push(reader.readString());\n" if is_list else f"{indent}    this.{var_name}[i] = reader.readString();\n"
        elif js_type == 'char':
            line = f"{indent}    this.{var_name}.push(String.fromCharCode(reader.readChar()));\n" if is_list else f"{indent}    this.{var_name}[i] = String.fromCharCode(reader.readChar());\n"
        elif is_enum or is_table_id:
            line = f"{indent}    this.{var_name}.push( {js_type}.fromInt(reader.readInt32()));\n" if is_list else f"{indent}    this.{var_name}[i] = {js_type}.fromInt(reader.readInt32());\n"
        elif is_class:
            line = f"{indent}    const add_data = new {js_type}();\n"
            line += f"{indent}    add_data.read(reader);\n"
            line += f"{indent}    this.{var_name}.push(add_data);\n" if is_list else f"{indent}    this.{var_name}[i] = add_data;\n"
        else:
            line = f"{indent}    this.{var_name}.push(0); // Unsupported\n" if is_list else f"{indent}    this.{var_name}[i] = 0; // Unsupported\n"
        read_code += line
        if is_list or is_array:
            read_code += "        }\n"
    else:
        # 単一値
        if js_type == 'vector2':
            read_code = f"        this.{var_name} = reader.readVector2();\n"
        elif js_type == 'vector3':
            read_code = f"        this.{var_name} = reader.readVector3();\n"
        elif js_type == 'int':
            read_code = f"        this.{var_name} = reader.readInt32();\n"
        elif js_type == 'byte':
            read_code = f"        this.{var_name} = reader.readByte();\n"
        elif js_type == 'short':
            read_code = f"        this.{var_name} = reader.readInt16();\n"
        elif js_type == 'long':
            read_code = f"        this.{var_name} = reader.readInt64();\n"
        elif js_type == 'float':
            read_code = f"        this.{var_name} = reader.readFloat32();\n"
        elif js_type == 'double':
            read_code = f"        this.{var_name} = reader.readDouble();\n"
        elif js_type == 'bool':
            read_code = f"        this.{var_name} = reader.readBoolean();\n"
        elif js_type == 'string':
            read_code = f"        this.{var_name} = reader.readString();\n"
        elif js_type == 'char':
            read_code = f"        this.{var_name} = String.fromCharCode(reader.readChar());\n"
        elif is_enum or is_table_id:
            read_code = f"        this.{var_name} = {js_type}.fromInt(reader.readInt32());\n"
        elif is_class:
            read_code = f"        this.{var_name} = new {js_type}();\n"
            read_code += f"        this.{var_name}.read(reader);\n"
        else:
            read_code = f"        this.{var_name} = 0; // Unsupported\n"

    # loadJson / fromJson 用コード（そのまま）
    json_code = f"        this.{var_name} = data.{var_name} ?? {initial};\n"
    if is_class:
        json_code = f"        if (data.{var_name} !== undefined && data.{var_name} !== null) {{\n"
        json_code += f"            this.{var_name} = new {js_type}();\n"
        json_code += f"            this.{var_name}.loadJson(data.{var_name});\n"
        json_code += f"        }} else {{\n"
        json_code += f"            this.{var_name} = {initial};\n"
        json_code += f"        }}\n"
    elif is_list or is_array:
        if is_class:
            json_code = f"        this.{var_name} = [];\n"
            json_code += f"        for (let item of (data.{var_name} || [])) {{\n"
            json_code += f"            if (item !== null && item !== undefined) {{\n"
            json_code += f"                const obj = new {js_type}();\n"
            json_code += f"                obj.loadJson(item);\n"
            json_code += f"                this.{var_name}.push(obj);\n"
            json_code += f"            }} else {{\n"
            json_code += f"                this.{var_name}.push(null);\n"
            json_code += f"            }}\n"
            json_code += f"        }}\n"
        else:
            json_code = f"        this.{var_name} = data.{var_name} || [];\n"

    return {
        'field': f"        this.{var_name} = {initial}; // {description}\n",
        'read': read_code,
        'json': json_code,
        'used_class': js_type if is_class else None,
        'is_enum': is_enum,
        'used_enum': js_type if is_enum else None,
        'is_table_id': is_table_id,
        'used_table_id': js_type if is_table_id else None
    }

# ========================
# 4. Python版クラス生成（import対応 + load_json追加）
# ========================
def generate_class_python(name, data, enum_list, class_list, class_id_list):
    py_dir = os.path.join(DATA_DIR, CLASS_DATA, name)
    os.makedirs(py_dir, exist_ok=True)

    used_classes = set()
    enum_classes = set()
    table_classes = set()
    field_lines = []
    read_lines = []
    json_lines = []

    for item in data:
        f = generate_python_field(item, enum_list, class_list, class_id_list)
        field_lines.append(f['field'])
        read_lines.append(f['read'])
        json_lines.append(f['json'])
        if f['used_class']:
            used_classes.add(f['used_class'])
        if f['is_enum']:
            enum_classes.add(f['used_enum'])
        if f['is_table_id']:
            table_classes.add(f['used_table_id'])

    base_path = os.path.join(py_dir, f"Base{name}.py")
    with open(base_path, 'w', encoding='utf-8') as f:
        f.write("from ..BaseCustomClassData import BaseCustomClassData\n")
        for uc in sorted(used_classes):
            if uc != name:  # 自分自身は不要
                f.write(f"from ...class-data.{uc}.{uc} import {uc}\n")
        for ec in sorted(enum_classes):
            if ec != name:
                f.write(f"from ...enum.{ec.replace('ID', '')}.{ec} import {ec}\n")
        for tc in sorted(table_classes):
            if tc != name:
                f.write(f"from ...class-data-id.{tc.replace('TableID', '')}.{tc} import {tc}\n")

        f.write("\n")
        f.write(f"class Base{name}(BaseCustomClassData):\n")
        f.write("    def __init__(self):\n")
        f.write("        super().__init__()\n")
        for line in field_lines:
            f.write(line)
        f.write("\n    def read(self, reader):\n")
        for line in read_lines:
            f.write(line)
        f.write("\n    def load_json(self, data):\n")
        for line in json_lines:
            f.write(line)

    # 空の継承クラス
    user_path = os.path.join(py_dir, f"{name}.py")
    with open(user_path, 'w', encoding='utf-8') as f:
        f.write(f"from .Base{name} import Base{name}\n\n")
        f.write(f"class {name}(Base{name}):\n")
        f.write("    pass\n")

    return base_path




# ========================
# 5. JS版クラス生成（import対応 + read(view, offset) + loadJson）
# ========================
def generate_class_js(name, data, enum_list, class_list, class_id_list):
    js_dir = os.path.join(DATA_DIR, CLASS_DATA, name)
    os.makedirs(js_dir, exist_ok=True)

    used_classes = set()
    enum_classes = set()
    table_classes = set()

    field_lines = []
    read_lines = []
    json_lines = []

    for item in data:
        f = generate_js_field(item, enum_list, class_list, class_id_list)
        field_lines.append(f['field'])
        read_lines.append(f['read'])
        json_lines.append(f['json'])
        if f['used_class']:
            used_classes.add(f['used_class'])
        if f['is_enum']:
            enum_classes.add(f['used_enum'])
        if f['is_table_id']:
            table_classes.add(f['used_table_id'])

    base_path = os.path.join(js_dir, f"Base{name}.js")
    with open(base_path, 'w', encoding='utf-8') as f:
        f.write("import { BaseCustomClassData } from '../BaseCustomClassData.js';\n")
        for uc in sorted(used_classes):
            if uc != name:
                f.write(f"import {{ {uc} }} from '../{uc}/{uc}.js';\n")
        for ec in sorted(enum_classes):
            if ec != name:
                f.write(f"import {{ {ec} }} from '../../enum/{ec.replace('ID', '')}/{ec}.js';\n")
        for tc in sorted(table_classes):
            if tc != name:
                f.write(f"import {{ {tc} }} from '../../class-data-id/{tc.replace('TableID', '')}/{tc}.js';\n")
        f.write("\n")
        f.write(f"export class Base{name} extends BaseCustomClassData {{\n")
        f.write("    constructor() {\n")
        f.write("        super();\n")
        for line in field_lines:
            f.write(line)
        f.write("    }\n\n")
        f.write("    read(view, offset) {\n")
        f.write("        let o = offset;\n")
        for line in read_lines:
            f.write(line)
        f.write("        return o;\n")
        f.write("    }\n\n")
        f.write("    loadJson(data) {\n")
        for line in json_lines:
            f.write(line)
        f.write("    }\n")
        f.write("}\n")

    # 空の継承クラス
    user_path = os.path.join(js_dir, f"{name}.js")
    with open(user_path, 'w', encoding='utf-8') as f:
        f.write(f"import {{ Base{name} }} from './Base{name}.js';\n\n")
        f.write(f"export class {name} extends Base{name} {{\n")
        f.write("}\n")

    return base_path


# ========================
# 1. Python版 enum 生成関数（BaseClassDataID互換・load_json不要でシンプル）
# ========================
def generate_enum_python(name, data):
    # C#と同じフィルタリング（NaN/inf除外）
    valid_data = [item for item in data if not math.isnan(item['value']) and math.isfinite(item['value'])]
    name = name.replace("IDID", "ID")  # Enum名はIDを外す（例：ClassID -> Class）
    if "ID" not in name:
        name += "ID"  # Enum名はIDを付ける（例：Class -> ClassID）
    if not valid_data:
        valid_data = [{'property': 'NONE', 'value': 1, 'description': 'fallback'}]  # 最低限1つ確保
    
    # default（C#と同じく最初の項目）
    default_prop = valid_data[0]['property']
    default_member = 'NONE' if default_prop == 'None' else default_prop
    
    # enum本文生成（PythonではNoneが予約語なのでNONEに正規化）
    py_content = """from enum import IntEnum
from typing import Callable, List, Any


class {name}(IntEnum):
    NONE = 0  # デフォルト値（C#のNoneに相当）
""".format(name=name)
    
    for item in valid_data:
        member_name = 'NONE' if item['property'] == 'None' else item['property']
        py_content += f"    {member_name} = {item['value']}  # {item['description']}\n"
    
    max_value = max((item['value'] for item in valid_data), default=-1) + 1
    py_content += f"    MAX = {max_value}\n\n"
    
    # Extensions（C#とほぼ同じ挙動）
    py_content += f"""def to_int(id: "{name}") -> int:
    return int(id)


def to_{name}(id: int) -> "{name}":
    return {name}(id)


def to_index(id: "{name}") -> int:
    return int(id) - 1


def for_id(action: Callable[["{name}"], None]):
    if action is None:
        raise ValueError("action cannot be None")
    start = {name}.{default_member}.value
    for i in range(start, {name}.MAX.value):
        try:
            value = {name}(i)
            action(value)
        except ValueError:
            continue  # 未定義の値はスキップ


def find_all(predicate: Callable[["{name}"], bool]) -> List["{name}"]:
    if predicate is None:
        raise ValueError("predicate cannot be None")
    results: List["{name}"] = []
    start = {name}.{default_member}.value
    for i in range(start, {name}.MAX.value):
        try:
            value = {name}(i)
            if predicate(value):
                results.append(value)
        except ValueError:
            continue
    return results


def find(predicate: Callable[["{name}"], bool]) -> "{name}":
    if predicate is None:
        raise ValueError("predicate cannot be None")
    start = {name}.{default_member}.value
    for i in range(start, {name}.MAX.value):
        try:
            value = {name}(i)
            if predicate(value):
                return value
        except ValueError:
            continue
    return {name}.NONE
"""
    return py_content


# ========================
# JS版 Enum 生成（純粋なJavaScript対応版）
# ========================
def generate_enum_js(name, data):
    valid_data = [item for item in data if not math.isnan(item.get('value', 0)) and math.isfinite(item.get('value', 0))]
    name = name.replace("IDID", "ID")  # Enum名はIDを外す（例：ClassID -> Class）
    if "ID" not in name:
        name += "ID"  # Enum名はIDを付ける（例：Class -> ClassID）
    if not valid_data:
        valid_data = [{'property': 'None', 'value': 0, 'description': 'default'}]

    default_prop = valid_data[0]['property']

    js_content = f"""// {name} - Pure JavaScript Version
export const {name} = {{
    None: 0,  // デフォルト値（C#互換）
"""

    for item in valid_data:
        prop = item['property']
        if prop == "None":
            prop = "None"  # そのまま
        js_content += f"    {prop}: {item['value']},  // {item.get('description', '')}\n"

    max_value = max((item['value'] for item in valid_data), default=0) + 1
    js_content += f"    Max: {max_value}\n}};\n\n"

    # ヘルパー関数（Extensions）
    js_content += f"""export const {name}Extensions = {{
    /**
     * Enumを数値に変換
     */
    toInt(id) {{
        return Number(id);
    }},

    /**
     * 数値をEnumに変換
     */
    to{name}(id) {{
        return id;
    }},

    /**
     * 0-based indexに変換
     */
    toIndex(id) {{
        return Number(id) - 1;
    }},

    /**
     * すべてのIDに対して処理を実行
     */
    forID(action) {{
        if (typeof action !== 'function') {{
            throw new Error('action must be a function');
        }}
        const start = {name}.{default_prop};
        const max = {name}.Max;
        for (let id = start; id < max; id++) {{
            if (Object.values({name}).includes(id)) {{
                action(id);
            }}
        }}
    }},

    /**
     * 条件に合うすべてのIDを返す
     */
    findAll(predicate) {{
        if (typeof predicate !== 'function') {{
            throw new Error('predicate must be a function');
        }}
        const results = [];
        const start = {name}.{default_prop};
        const max = {name}.Max;
        for (let id = start; id < max; id++) {{
            if (Object.values({name}).includes(id)) {{
                if (predicate(id)) {{
                    results.push(id);
                }}
            }}
        }}
        return results;
    }},

    /**
     * 条件に合う最初のIDを返す（見つからなければ None）
     */
    find(predicate) {{
        if (typeof predicate !== 'function') {{
            throw new Error('predicate must be a function');
        }}
        const start = {name}.{default_prop};
        const max = {name}.Max;
        for (let id = start; id < max; id++) {{
            if (Object.values({name}).includes(id)) {{
                if (predicate(id)) {{
                    return id;
                }}
            }}
        }}
        return {name}.None;
    }}
}};
"""

    return js_content

# ========================
# 1. Python版 Row 生成（BaseClassDataRow互換 + from_json + read）
# ========================
def generate_row_python(name, columns, rows, enum_list, class_list, class_data_id_list):
    # 配列サイズをサンプル行から取得（C#と完全一致）
    array_sizes = {}
    if rows and len(rows) > 0 and 'data' in rows[0]:
        for col in columns:
            col_name = col['name']
            if col_name in rows[0]['data'] and isinstance(rows[0]['data'][col_name].get('value'), list):
                array_sizes[col_name] = len(rows[0]['data'][col_name]['value'])
            else:
                array_sizes[col_name] = 0
    else:
        array_sizes = {col['name']: 0 for col in columns}

    used_classes = set()
    enum_classes = set()
    table_classes = set()
    field_lines = []
    read_lines = []
    json_lines = []   # from_json用

    for col in columns:
        item = col.copy()
        item['name'] = col['name']
        item['type'] = col['type']
        # generate_python_field を再利用（前回の関数そのまま使える）
        f = generate_python_field(item, enum_list, class_list, class_data_id_list)  # 既に定義済みの関数

        field_lines.append(f['field'])
        read_lines.append(f['read'])
        json_lines.append(f['json'])   # load_json用のコードをfrom_jsonでもそのまま使用可能
        
        if f.get('used_class'):
            used_classes.add(f['used_class'])
        if f.get('is_enum'):
            enum_classes.add(f['used_enum'])
        if f.get('is_table_id'):
            table_classes.add(f['used_table_id'])

    py_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, name)
    os.makedirs(py_dir, exist_ok=True)

    row_path = os.path.join(py_dir, f"{name}Row.py")
    with open(row_path, 'w', encoding='utf-8') as f:
        f.write("from ..BaseClassDataRow import BaseClassDataRow\n")
        for uc in sorted(used_classes):
            if uc != name:
                # 相対パス（CLASS_DATA_ID/name/ から CLASS_DATA/uc/uc.py へ）
                f.write(f"from ...class-data.{uc}.{uc} import {uc}\n")
        for ec in sorted(enum_classes):
            if ec != name:
                f.write(f"from ...enum.{ec.replace('ID', '')}.{ec} import {ec}\n")
        for tc in sorted(table_classes):
            if tc != name:
                f.write(f"from ...class-data-id.{tc.replace('TableID', '')}.{tc} import {tc}\n")
        f.write("\n")
        f.write(f"class {name}Row(BaseClassDataRow):\n")
        f.write("    def __init__(self):\n")
        f.write("        super().__init__()\n")
        for line in field_lines:
            f.write(line)
        f.write("\n    def read(self, reader):\n")
        for line in read_lines:
            f.write(line)
        f.write("\n    @classmethod\n")
        f.write("    def from_json(cls, data: dict):\n")
        f.write("        self = cls()\n")
        for line in json_lines:
            f.write(line.replace("self.", "self."))  # インデント調整
        f.write("        return self\n")

    return row_path


# ========================
# 2. JS版 Row 生成（BaseClassDataRow互換 + fromJson + read(reader)）
# ========================
def generate_row_js(name, columns, rows, enum_list, class_list, class_data_id_list):
    # 配列サイズ取得（C#と完全一致）
    array_sizes = {}
    if rows and len(rows) > 0 and 'data' in rows[0]:
        for col in columns:
            col_name = col['name']
            if col_name in rows[0]['data'] and isinstance(rows[0]['data'][col_name].get('value'), list):
                array_sizes[col_name] = len(rows[0]['data'][col_name]['value'])
            else:
                array_sizes[col_name] = 0
    else:
        array_sizes = {col['name']: 0 for col in columns}

    used_classes = set()
    enum_classes = set()
    table_classes = set()
    field_lines = []
    read_lines = []
    json_lines = []

    for col in columns:
        item = col.copy()
        item['name'] = col['name']
        item['type'] = col['type']
        # ★★★ BinaryReader専用フィールド生成を使用 ★★★
        f = generate_js_binary_field(item, enum_list, class_list, class_data_id_list)
        field_lines.append(f['field'])
        read_lines.append(f['read'])
        json_lines.append(f['json'])
        if f.get('used_class'):
            used_classes.add(f['used_class'])
        if f.get('is_enum'):
            enum_classes.add(f['used_enum'])
        if f.get('is_table_id'):
            table_classes.add(f['used_table_id'])

    js_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, name)
    os.makedirs(js_dir, exist_ok=True)

    row_path = os.path.join(js_dir, f"{name}Row.js")
    with open(row_path, 'w', encoding='utf-8') as f:
        f.write("import { BaseClassDataRow } from '../BaseClassDataRow.js';\n")
        for uc in sorted(used_classes):
            if uc != name:
                f.write(f"import {{ {uc} }} from '../../../class-data/{uc}/{uc}.js';\n")
        for ec in sorted(enum_classes):
            if ec != name:
                f.write(f"import {{ {ec} }} from '../../enum/{ec.replace('ID', '')}/{ec}.js';\n")
        for tc in sorted(table_classes):
            if tc != name:
                f.write(f"import {{ {tc} }} from '../../class-data-id/{tc.replace('TableID', '')}/{tc}.js';\n")
        f.write("\n")
        f.write(f"export class {name}Row extends BaseClassDataRow {{\n")
        f.write("    constructor() {\n")
        f.write("        super();\n")
        for line in field_lines:
            f.write(line)
        f.write("    }\n\n")
        f.write("    read(reader) {\n")
        for line in read_lines:
            f.write(line)
        f.write("    }\n\n")
        # JSON読み込み関数（fromJson）
        f.write("    static fromJson(data) {\n")
        f.write("        const self = new this();\n")
        for line in json_lines:
            # this. → self. に置換
            fixed = line.replace("this.", "self.")
            f.write(fixed)
        f.write("        return self;\n")
        f.write("    }\n")
        f.write("}\n")

    return row_path

# ========================
# 3. Python版 Table 生成（BaseClassDataID互換 + read(binary) + load_from_json）
# ========================
def generate_table_python(name, columns, rows, enum_list, class_list, class_data_id_list):
    py_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, name)
    table_path = os.path.join(py_dir, f"{name}Table.py")

    with open(table_path, 'w', encoding='utf-8') as f:
        f.write("from ..BaseClassDataID import BaseClassDataID\n")
        f.write(f"from .{name}Row import {name}Row\n")
        f.write(f"from .{name}TableID import {name}TableID\n")
        f.write("from typing import Dict\n\n")
        f.write(f"class {name}Table(BaseClassDataID):\n")
        f.write(f"    Table: Dict[{name}TableID, {name}Row] = {{}}\n\n")
        f.write("    @classmethod\n")
        f.write("    def _get_enum(cls, name: str):\n")
        f.write(f"        return {name}TableID[name]\n")
        f.write("    @classmethod\n")
        f.write("    def _get_row_class(cls):\n")
        f.write(f"        return {name}Row\n\n")
        f.write("    def read(self, reader):\n")
        f.write("        self.Table.clear()\n")
        f.write("        row_count = reader.read_int32()\n")
        f.write("        col_count = reader.read_int32()\n")
        f.write("        for _ in range(col_count):\n")
        f.write("            len_name = reader.read_int32()\n")
        f.write("            _ = reader.read_string()  # col name（ヘッダー読み飛ばし）\n")
        f.write("            len_type = reader.read_int32()\n")
        f.write("            _ = reader.read_string()  # col type\n")
        f.write("        for _ in range(row_count):\n")
        f.write("            enum_int = reader.read_int32()\n")
        f.write(f"            enum_val = {name}TableID(enum_int)\n")
        f.write(f"            row = {name}Row()\n")
        f.write("            row.read(reader)\n")
        f.write("            self.Table[enum_val] = row\n")

    return table_path


# ========================
# 4. JS版 Table 生成（BaseClassDataID互換 + read(reader)）
# ========================
def generate_table_js(name, columns, rows, enum_list, class_list, class_data_id_list):
    js_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, name)
    table_path = os.path.join(js_dir, f"{name}Table.js")

    with open(table_path, 'w', encoding='utf-8') as f:
        f.write("import { BaseClassDataID } from '../BaseClassDataID.js';\n")
        f.write(f"import {{ {name}Row }} from './{name}Row.js';\n")
        f.write(f"import {{ {name}TableID }} from './{name}TableID.js';\n\n")
        f.write(f"export class {name}Table extends BaseClassDataID {{\n")
        f.write("    static Table = new Map();\n\n")
        f.write("    static _getEnum(name) {\n")
        f.write(f"        return {name}TableID[name];\n")
        f.write("    }\n\n")
        f.write("    static _getRowClass() {\n")
        f.write(f"        return {name}Row;\n")
        f.write("    }\n\n")
        f.write("    read(reader) {\n")
        f.write("        this.constructor.Table.clear();\n")
        f.write("        const rowCount = reader.readInt32();\n")
        f.write("        const colCount = reader.readInt32();\n")
        f.write("        for (let i = 0; i < colCount; i++) {\n")
        f.write("            const lenName = reader.readInt32();\n")
        f.write("            reader.readString(); // col name（ヘッダー読み飛ばし）\n")
        f.write("            const lenType = reader.readInt32();\n")
        f.write("            reader.readString(); // col type\n")
        f.write("        }\n")
        f.write("        for (let r = 0; r < rowCount; r++) {\n")
        f.write("            const enumInt = reader.readInt32();\n")
        f.write(f"            const enumVal = {name}TableID[Object.keys({name}TableID).find(key => {name}TableID[key] === enumInt)] || enumInt;\n")
        f.write(f"            const row = new {name}Row();\n")
        f.write("            row.read(reader);\n")
        f.write("            this.constructor.Table.set(enumVal, row);\n")
        f.write("        }\n")
        f.write("    }\n\n")
        # GetRowヘルパー（C# Exampleと同等）
        f.write("    static getRow(id) {\n")
        f.write("        return this.Table.get(id) ?? null;\n")
        f.write("    }\n")
        f.write("}\n")

    return table_path
