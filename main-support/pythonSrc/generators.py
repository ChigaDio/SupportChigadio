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
SCRIPT_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))


CLASS_DATA_ID = 'class_data_id'
CLASS_DATA_MATRIX_ID = 'class_data_matrix_id'
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ENUM = 'enum'
CLASS_DATA = 'class_data'
STATE_DATA = 'state_data'

SCRIPT = 'Script'
OBJECTPOOL = 'ObjectPool'
EDITOR = "Editor"
DEBUG = "Debug"
LOG = "Log"

SUBMODULE = "submodule"
PLUGIN = "Plugin"


SAVE_DATA_DIR = os.path.join(DATA_DIR, "save_data")
SAVE_DATA_CUSTOM_DIR = os.path.join(SAVE_DATA_DIR, "custom_data")

def init(data_dir):
    """app.py から呼び出す初期化関数。"""
    global DATA_DIR, SAVE_DATA_DIR, SAVE_DATA_CUSTOM_DIR
    DATA_DIR = os.path.abspath(data_dir)
    SAVE_DATA_DIR = os.path.join(DATA_DIR, "save_data")
    SAVE_DATA_CUSTOM_DIR = os.path.join(SAVE_DATA_DIR, "custom_data")

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
# 1.5 共有ランタイムファイル（Python/JS）の自動生成
# ========================
# C#側で _CUSTOM_BIT_FIELD_CS を _ensure_custom_bit_field_cs() が自動生成しているのと
# 同じ考え方で、Python/JS版のBase{name}.py / Base{name}.js が使う共通クラス
# （バイナリ読み書き・bit/color/bezier/dictionary用のランタイムクラス）も、
# 手書きで配置してもらうのではなく、生成のたびにこのモジュールが自動で書き出す。
# 出力先は class_data フォルダ直下の "_Shared" サブフォルダ（C#側の _Shared 命名と統一）。

_PY_BINARY_IO_SRC = '''# -*- coding: utf-8 -*-
"""
class_data/_Shared/binary_io.py

自動生成ファイル（pythonSrc/generators.py が生成のたびに書き出す）。
手動で編集しないこと（次回生成時に上書きされる）。

Base{name}.py の read(self, reader) / write(self, writer) が使う、
対称なバイナリ読み書きの共通クラス。
- エンディアン: リトルエンディアン固定（C#側BinaryReader/BinaryWriter、
  JS側DataView(..., true)実装と揃えている）
- 文字列: 4byte(int32, リトルエンディアン)の長さプレフィックス + UTF-8バイト列
- char: 2byte(UInt16)としてUnicodeのコードポイント1つ分を読み書きする
"""
import struct


class PyBinaryReader:
    __slots__ = ('_data', '_pos')

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def _read_exact(self, size):
        end = self._pos + size
        if end > len(self._data):
            raise EOFError(
                f"バイナリの終端を超えて読み込もうとしました "
                f"(pos={self._pos}, size={size}, len={len(self._data)})"
            )
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def read_int32(self) -> int:
        return struct.unpack('<i', self._read_exact(4))[0]

    def read_uint32(self) -> int:
        return struct.unpack('<I', self._read_exact(4))[0]

    def read_byte(self) -> int:
        return struct.unpack('<B', self._read_exact(1))[0]

    def read_int16(self) -> int:
        return struct.unpack('<h', self._read_exact(2))[0]

    def read_int64(self) -> int:
        return struct.unpack('<q', self._read_exact(8))[0]

    def read_uint64(self) -> int:
        return struct.unpack('<Q', self._read_exact(8))[0]

    def read_float(self) -> float:
        return struct.unpack('<f', self._read_exact(4))[0]

    def read_double(self) -> float:
        return struct.unpack('<d', self._read_exact(8))[0]

    def read_bool(self) -> bool:
        return struct.unpack('<?', self._read_exact(1))[0]

    def read_char(self) -> str:
        return chr(struct.unpack('<H', self._read_exact(2))[0])

    def read_string(self) -> str:
        length = self.read_int32()
        if length <= 0:
            return ''
        return self._read_exact(length).decode('utf-8')

    def tell(self) -> int:
        return self._pos

    def remaining(self) -> int:
        return len(self._data) - self._pos

    def eof(self) -> bool:
        return self._pos >= len(self._data)


class PyBinaryWriter:
    __slots__ = ('_buf',)

    def __init__(self):
        self._buf = bytearray()

    def write_int32(self, value):
        self._buf += struct.pack('<i', int(value))

    def write_uint32(self, value):
        self._buf += struct.pack('<I', int(value))

    def write_byte(self, value):
        self._buf += struct.pack('<B', int(value) & 0xFF)

    def write_int16(self, value):
        self._buf += struct.pack('<h', int(value))

    def write_int64(self, value):
        self._buf += struct.pack('<q', int(value))

    def write_uint64(self, value):
        self._buf += struct.pack('<Q', int(value))

    def write_float(self, value):
        self._buf += struct.pack('<f', float(value))

    def write_double(self, value):
        self._buf += struct.pack('<d', float(value))

    def write_bool(self, value):
        self._buf += struct.pack('<?', bool(value))

    def write_char(self, value):
        code_point = ord(value) if isinstance(value, str) else int(value)
        self._buf += struct.pack('<H', code_point)

    def write_string(self, value):
        encoded = (value or '').encode('utf-8')
        self.write_int32(len(encoded))
        self._buf += encoded

    def getvalue(self) -> bytes:
        return bytes(self._buf)

    def __len__(self):
        return len(self._buf)
'''

_PY_RUNTIME_TYPES_SRC = '''# -*- coding: utf-8 -*-
"""
class_data/_Shared/runtime_types.py

自動生成ファイル（pythonSrc/generators.py が生成のたびに書き出す）。
手動で編集しないこと（次回生成時に上書きされる）。

bit/color/bezier(AnimationCurve)フィールド用のPython版ランタイムクラス。
C#側の CustomBitField / UnityEngine.Color / UnityEngine.AnimationCurve と
同じバイナリレイアウト・同じJSONスキーマ（{"bits":[...]} / {"r","g","b","a"} /
{"points":[{"time","value","inTangent","outTangent"}, ...]}）で相互運用できる
ようにしてある。
"""


class PyBitField:
    """CustomBitField(C#)相当。Pythonのintは多倍長なので、C#のような
    64bit超えでの配列分割は行わず、1つのintをビットマスクとして使う。
    ワイヤーフォーマット（Read/Write）はC#側と互換
    （int32 size + ceil(size/64)個のuint64、リトルエンディアン）。"""
    __slots__ = ('size', '_bits')

    def __init__(self, size=8):
        self.size = max(int(size), 1)
        self._bits = 0

    def get(self, index):
        if index < 0 or index >= self.size:
            return False
        return (self._bits >> index) & 1 == 1

    def set(self, index, value):
        if index < 0 or index >= self.size:
            return
        if value:
            self._bits |= (1 << index)
        else:
            self._bits &= ~(1 << index)

    def set_exclusive(self, index):
        self._bits = 0
        self.set(index, True)

    def select_all(self):
        self._bits = (1 << self.size) - 1

    def clear(self):
        self._bits = 0

    def read(self, reader):
        self.size = reader.read_int32()
        nwords = (self.size + 63) // 64
        value = 0
        for i in range(nwords):
            value |= reader.read_uint64() << (64 * i)
        self._bits = value

    def write(self, writer):
        writer.write_int32(self.size)
        nwords = (self.size + 63) // 64
        mask = (1 << 64) - 1
        for i in range(nwords):
            writer.write_uint64((self._bits >> (64 * i)) & mask)

    def load_json(self, data):
        self.clear()
        for idx in (data or {}).get('bits', []):
            self.set(int(idx), True)

    def write_json(self, data):
        data['bits'] = [i for i in range(self.size) if self.get(i)]


class PyColor:
    """UnityEngine.Color相当の軽量版。"""
    __slots__ = ('r', 'g', 'b', 'a')

    def __init__(self, r=1.0, g=1.0, b=1.0, a=1.0):
        self.r, self.g, self.b, self.a = r, g, b, a

    def read(self, reader):
        self.r = reader.read_float()
        self.g = reader.read_float()
        self.b = reader.read_float()
        self.a = reader.read_float()

    def write(self, writer):
        writer.write_float(self.r)
        writer.write_float(self.g)
        writer.write_float(self.b)
        writer.write_float(self.a)

    def load_json(self, data):
        d = data or {}
        self.r = d.get('r', 1.0)
        self.g = d.get('g', 1.0)
        self.b = d.get('b', 1.0)
        self.a = d.get('a', 1.0)

    def write_json(self, data):
        data['r'] = self.r
        data['g'] = self.g
        data['b'] = self.b
        data['a'] = self.a


class PyKeyframe:
    __slots__ = ('time', 'value', 'in_tangent', 'out_tangent')

    def __init__(self, time=0.0, value=0.0, in_tangent=0.0, out_tangent=0.0):
        self.time = time
        self.value = value
        self.in_tangent = in_tangent
        self.out_tangent = out_tangent


class PyAnimationCurve:
    """UnityEngine.AnimationCurve(bezier)相当の軽量版。keysプロパティ名も
    Unity側に合わせてある。"""
    __slots__ = ('keys',)

    def __init__(self):
        self.keys = []

    def read(self, reader):
        count = reader.read_int32()
        self.keys = []
        for _ in range(count):
            self.keys.append(PyKeyframe(
                reader.read_float(), reader.read_float(),
                reader.read_float(), reader.read_float(),
            ))

    def write(self, writer):
        writer.write_int32(len(self.keys))
        for k in self.keys:
            writer.write_float(k.time)
            writer.write_float(k.value)
            writer.write_float(k.in_tangent)
            writer.write_float(k.out_tangent)

    def load_json(self, data):
        self.keys = []
        for p in (data or {}).get('points', []):
            self.keys.append(PyKeyframe(
                p.get('time', 0.0), p.get('value', 0.0),
                p.get('inTangent', 0.0), p.get('outTangent', 0.0),
            ))

    def write_json(self, data):
        data['points'] = [
            {'time': k.time, 'value': k.value, 'inTangent': k.in_tangent, 'outTangent': k.out_tangent}
            for k in self.keys
        ]
'''

_JS_RUNTIME_TYPES_SRC = '''// class_data/_Shared/runtimeTypes.js
//
// 自動生成ファイル（pythonSrc/generators.py が生成のたびに書き出す）。
// 手動で編集しないこと（次回生成時に上書きされる）。
//
// bit/bezier(AnimationCurve)フィールド用のJS版ランタイムクラス。
// C#側の CustomBitField / UnityEngine.AnimationCurve と同じバイナリレイアウト・
// 同じJSONスキーマ（{"bits":[...]} / {"points":[{"time","value","inTangent","outTangent"}, ...]}）
// で相互運用できるようにしてある。colorは単純なプレーンオブジェクト{r,g,b,a}のまま
// 扱う（Vector2/Vector3が配列のまま扱われているのと同じ方針）。

export class BitField {
  // C#側のCustomBitFieldと同じワイヤーフォーマット
  // （int32 size + ceil(size/64)個のuint64、リトルエンディアン）。
  // JSはBigIntを使うことで、Pythonのint同様に多倍長のビットマスクとして扱う。
  constructor(size = 8) {
    this.size = Math.max(size | 0, 1);
    this.bits = 0n;
  }

  get(index) {
    if (index < 0 || index >= this.size) return false;
    return ((this.bits >> BigInt(index)) & 1n) === 1n;
  }

  set(index, value) {
    if (index < 0 || index >= this.size) return;
    const bit = 1n << BigInt(index);
    if (value) this.bits |= bit; else this.bits &= ~bit;
  }

  setExclusive(index) { this.clear(); this.set(index, true); }
  selectAll() { this.bits = (1n << BigInt(this.size)) - 1n; }
  clear() { this.bits = 0n; }

  read(view, offset) {
    let o = offset;
    this.size = view.getInt32(o, true); o += 4;
    const nWords = Math.ceil(this.size / 64);
    let value = 0n;
    for (let i = 0; i < nWords; i++) {
      const word = view.getBigUint64(o, true); o += 8;
      value |= word << BigInt(64 * i);
    }
    this.bits = value;
    return o;
  }

  write(view, offset) {
    let o = offset;
    view.setInt32(o, this.size, true); o += 4;
    const nWords = Math.ceil(this.size / 64);
    const mask = (1n << 64n) - 1n;
    for (let i = 0; i < nWords; i++) {
      const word = (this.bits >> BigInt(64 * i)) & mask;
      view.setBigUint64(o, word, true); o += 8;
    }
    return o;
  }

  loadJson(data) {
    this.clear();
    for (const idx of (data && data.bits) || []) this.set(idx, true);
  }

  writeJson(result) {
    const bits = [];
    for (let i = 0; i < this.size; i++) if (this.get(i)) bits.push(i);
    result.bits = bits;
  }
}

export class AnimationCurveLite {
  // UnityEngine.AnimationCurve相当の軽量版。keys: [{time,value,inTangent,outTangent}, ...]
  constructor() { this.keys = []; }

  read(view, offset) {
    let o = offset;
    const count = view.getInt32(o, true); o += 4;
    this.keys = [];
    for (let i = 0; i < count; i++) {
      const time = view.getFloat32(o, true); o += 4;
      const value = view.getFloat32(o, true); o += 4;
      const inTangent = view.getFloat32(o, true); o += 4;
      const outTangent = view.getFloat32(o, true); o += 4;
      this.keys.push({ time, value, inTangent, outTangent });
    }
    return o;
  }

  write(view, offset) {
    let o = offset;
    view.setInt32(o, this.keys.length, true); o += 4;
    for (const k of this.keys) {
      view.setFloat32(o, k.time, true); o += 4;
      view.setFloat32(o, k.value, true); o += 4;
      view.setFloat32(o, k.inTangent, true); o += 4;
      view.setFloat32(o, k.outTangent, true); o += 4;
    }
    return o;
  }

  loadJson(data) {
    this.keys = ((data && data.points) || []).map((p) => ({
      time: p.time || 0, value: p.value || 0, inTangent: p.inTangent || 0, outTangent: p.outTangent || 0,
    }));
  }

  writeJson(result) {
    result.points = this.keys.map((k) => ({
      time: k.time, value: k.value, inTangent: k.inTangent, outTangent: k.outTangent,
    }));
  }
}
'''


def _shared_class_data_dir():
    d = os.path.join(SCRIPT_DATA_DIR, CLASS_DATA, '_Shared')
    os.makedirs(d, exist_ok=True)
    return d


def _ensure_py_binary_io():
    """Python版の共通バイナリ読み書きクラスを最新化する（C#側の
    _ensure_custom_bit_field_cs()と同じ「生成のたびに自動で書き出す」方式）。"""
    path = os.path.join(_shared_class_data_dir(), 'binary_io.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_PY_BINARY_IO_SRC)
    return path


def _ensure_py_runtime_types():
    """Python版のbit/color/bezier用ランタイムクラスを最新化する。"""
    path = os.path.join(_shared_class_data_dir(), 'runtime_types.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_PY_RUNTIME_TYPES_SRC)
    return path


def _ensure_js_runtime_types():
    """JS版のbit/bezier用ランタイムクラスを最新化する。"""
    path = os.path.join(_shared_class_data_dir(), 'runtimeTypes.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_JS_RUNTIME_TYPES_SRC)
    return path


# ========================
# 2. Python版フィールド生成（load_json追加 + import用に型情報を返す）
# ========================
def generate_python_field(item, enum_list, class_list, class_id_list):
    type_str = item['type'].replace("[]", "")
    var_name = item['name']
    array_size = item.get('arraySize', 0)
    description = item.get('description', '')
    options = item.get('options') or {}

    # --- bit / color / bezier: 専用のPythonランタイムクラス(_Shared/runtime_types.py)
    #     に委譲する。いずれもスカラー専用（配列/リストのbitフィールド等は現状非対応、
    #     実運用上ほぼ使われないため）。
    if type_str in ('bit', 'color', 'bezier'):
        class_name = {'bit': 'PyBitField', 'color': 'PyColor', 'bezier': 'PyAnimationCurve'}[type_str]
        if type_str == 'bit':
            size = int(options.get('size', 8) or 8)
            initial = f"{class_name}({size})"
        else:
            initial = f"{class_name}()"
        return {
            'field': f"        self.{var_name} = {initial}  # {description}\n",
            'read': f"        self.{var_name}.read(reader)\n",
            'write': f"        self.{var_name}.write(writer)\n",
            'json': f"        self.{var_name}.load_json(data.get('{var_name}', {{}}))\n",
            'json_write': f"        __d_{var_name} = {{}}\n        self.{var_name}.write_json(__d_{var_name})\n        data['{var_name}'] = __d_{var_name}\n",
            'used_class': None, 'is_enum': False, 'used_enum': None,
            'is_table_id': False, 'used_table_id': None,
            'used_runtime_type': class_name,
        }

    # --- dictionary: keyType/valueTypeの組み合わせに応じて、素のdictとして
    #     読み書きする。JSON表現はC#/JS版と揃えて {"entries":[{"key":...,"value":...}]}。
    if type_str == 'dictionary':
        key_type = options.get('keyType', 'int')
        value_type = options.get('valueType', 'int')
        value_array_size = options.get('valueArraySize', 0) or 0
        value_options = options.get('valueOptions') or {}

        def _py_basic_read(t):
            tl = t.lower()
            if tl in PY_TYPE_MAP:
                return f"reader.{PY_TYPE_MAP[tl]['py_read']}()"
            if t in enum_list or t in class_id_list:
                return "reader.read_int32()"
            return "reader.read_int32()  # TODO: 未対応の型です"

        def _py_basic_write(t, expr):
            tl = t.lower()
            if tl in PY_TYPE_MAP:
                return f"writer.{PY_TYPE_MAP[tl]['py_read'].replace('read_', 'write_')}({expr})"
            if t in enum_list or t in class_id_list:
                return f"writer.write_int32(int({expr}))"
            return f"writer.write_int32(0)  # TODO: 未対応の型です"

        read_code = f"        self.{var_name} = {{}}\n"
        read_code += f"        __n_{var_name} = reader.read_int32()\n"
        read_code += f"        for _ in range(__n_{var_name}):\n"
        read_code += f"            __k = {_py_basic_read(key_type)}\n"
        if value_array_size == -1:
            read_code += f"            __cnt = reader.read_int32()\n"
            read_code += f"            __v = [{_py_basic_read(value_type)} for _ in range(__cnt)]\n"
        else:
            read_code += f"            __v = {_py_basic_read(value_type)}\n"
        read_code += f"            self.{var_name}[__k] = __v\n"

        write_code = f"        writer.write_int32(len(self.{var_name}))\n"
        write_code += f"        for __k, __v in self.{var_name}.items():\n"
        write_code += f"            {_py_basic_write(key_type, '__k')}\n"
        if value_array_size == -1:
            write_code += f"            writer.write_int32(len(__v))\n"
            write_code += f"            for __item in __v:\n"
            write_code += f"                {_py_basic_write(value_type, '__item')}\n"
        else:
            write_code += f"            {_py_basic_write(value_type, '__v')}\n"

        json_code = f"        self.{var_name} = {{}}\n"
        json_code += f"        for __e in (data.get('{var_name}', {{}}) or {{}}).get('entries', []):\n"
        json_code += f"            self.{var_name}[__e['key']] = __e['value']\n"

        json_write_code = f"        __entries_{var_name} = []\n"
        json_write_code += f"        for __k, __v in self.{var_name}.items():\n"
        json_write_code += f"            __entries_{var_name}.append({{'key': __k, 'value': __v}})\n"
        json_write_code += f"        data['{var_name}'] = {{'entries': __entries_{var_name}}}\n"

        return {
            'field': f"        self.{var_name} = {{}}  # {description}\n",
            'read': read_code, 'write': write_code,
            'json': json_code, 'json_write': json_write_code,
            'used_class': None, 'is_enum': False, 'used_enum': None,
            'is_table_id': False, 'used_table_id': None,
        }

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

    # --- write(writer)コード（readと対称。writerの生成/closeは呼び出し元の責務）--
    # readerが read_int32()等の対称メソッドを持つ前提で、writerは write_int32()等の
    # 対称メソッドを持つものとする（呼び出し元のwriterクラスにこれらが無ければ追加要）。
    write_code = ""
    if is_list:
        write_code = f"        writer.write_int32(len(self.{var_name}))\n"
        write_code += f"        for __v in self.{var_name}:\n"
        w_indent = "            "
    elif is_array:
        write_code = f"        for __v in self.{var_name}[:{array_size}]:\n"
        w_indent = "            "
    else:
        w_indent = "        "

    def py_write_stmt(expr):
        if py_type == 'vector2':
            return f"{w_indent}writer.write_float({expr}[0]); writer.write_float({expr}[1])\n"
        if py_type == 'vector3':
            return f"{w_indent}writer.write_float({expr}[0]); writer.write_float({expr}[1]); writer.write_float({expr}[2])\n"
        if py_type in PY_TYPE_MAP:
            return f"{w_indent}writer.{PY_TYPE_MAP[py_type]['py_read'].replace('read_', 'write_')}({expr})\n"
        if is_enum or is_table_id:
            return f"{w_indent}writer.write_int32(int({expr}))\n"
        if is_class:
            return f"{w_indent}{expr}.write(writer)\n"
        return f"{w_indent}pass  # Unsupported type for write: {py_type}\n"

    if is_list or is_array:
        write_code += py_write_stmt("__v")
    else:
        write_code += py_write_stmt(f"self.{var_name}")

    # --- to_json()コード: dataに自身の値をキー=フィールド名でセットする ---------
    def py_to_json_expr(expr):
        if py_type in ('vector2', 'vector3'):
            return f"list({expr})"
        if is_enum or is_table_id:
            return f"int({expr})"
        return expr

    if is_class:
        json_write_code = (
            f"        if self.{var_name} is not None:\n"
            f"            __d_{var_name} = {{}}\n"
            f"            self.{var_name}.write_json(__d_{var_name})\n"
            f"            data['{var_name}'] = __d_{var_name}\n"
            f"        else:\n"
            f"            data['{var_name}'] = None\n"
        )
    elif is_list or is_array:
        if is_class:
            json_write_code = (
                f"        __list_{var_name} = []\n"
                f"        for __v in self.{var_name}:\n"
                f"            if __v is not None:\n"
                f"                __d = {{}}\n"
                f"                __v.write_json(__d)\n"
                f"                __list_{var_name}.append(__d)\n"
                f"            else:\n"
                f"                __list_{var_name}.append(None)\n"
                f"        data['{var_name}'] = __list_{var_name}\n"
            )
        else:
            json_write_code = f"        data['{var_name}'] = list(self.{var_name})\n"
    else:
        json_write_code = f"        data['{var_name}'] = {py_to_json_expr(f'self.{var_name}')}\n"

    return {
        'field': f"        self.{var_name} = {initial}  # {description}\n",
        'read': read_code,
        'write': write_code,
        'json': json_code,
        'json_write': json_write_code,
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
    options = item.get('options') or {}

    # --- bit / bezier: 専用のJSランタイムクラス(_Shared/runtimeTypes.js)に委譲する
    #     （colorは既存のVector2/Vector3同様プレーンオブジェクトのまま扱う）。
    #     いずれもスカラー専用。
    if type_str == 'bit':
        size = int(options.get('size', 8) or 8)
        return {
            'field': f"        this.{var_name} = new BitField({size}); // {description}\n",
            'read': f"        o = this.{var_name}.read(view, o);\n",
            'write': f"        o = this.{var_name}.write(view, o);\n",
            'json': f"        this.{var_name}.loadJson(data.{var_name});\n",
            'json_write': f"        result.{var_name} = {{}}; this.{var_name}.writeJson(result.{var_name});\n",
            'used_class': None, 'is_enum': False, 'used_enum': None,
            'is_table_id': False, 'used_table_id': None,
            'used_runtime_type': 'BitField',
        }
    if type_str == 'bezier':
        return {
            'field': f"        this.{var_name} = new AnimationCurveLite(); // {description}\n",
            'read': f"        o = this.{var_name}.read(view, o);\n",
            'write': f"        o = this.{var_name}.write(view, o);\n",
            'json': f"        this.{var_name}.loadJson(data.{var_name});\n",
            'json_write': f"        result.{var_name} = {{}}; this.{var_name}.writeJson(result.{var_name});\n",
            'used_class': None, 'is_enum': False, 'used_enum': None,
            'is_table_id': False, 'used_table_id': None,
            'used_runtime_type': 'AnimationCurveLite',
        }
    if type_str == 'color':
        return {
            'field': f"        this.{var_name} = {{ r: 1, g: 1, b: 1, a: 1 }}; // {description}\n",
            'read': (f"        this.{var_name} = {{ r: view.getFloat32(o, true), g: view.getFloat32(o + 4, true), "
                      f"b: view.getFloat32(o + 8, true), a: view.getFloat32(o + 12, true) }}; o += 16;\n"),
            'write': (f"        view.setFloat32(o, this.{var_name}.r, true); view.setFloat32(o + 4, this.{var_name}.g, true); "
                       f"view.setFloat32(o + 8, this.{var_name}.b, true); view.setFloat32(o + 12, this.{var_name}.a, true); o += 16;\n"),
            'json': f"        this.{var_name} = data.{var_name} || {{ r: 1, g: 1, b: 1, a: 1 }};\n",
            'json_write': f"        result.{var_name} = {{ ...this.{var_name} }};\n",
            'used_class': None, 'is_enum': False, 'used_enum': None,
            'is_table_id': False, 'used_table_id': None,
        }

    # --- dictionary: JSのMapとして読み書きする。JSON表現はC#/Python版と揃えて
    #     { entries: [{ key, value }, ...] }。
    if type_str == 'dictionary':
        key_type = options.get('keyType', 'int')
        value_type = options.get('valueType', 'int')
        value_array_size = options.get('valueArraySize', 0) or 0

        def _js_basic_read(t):
            tl = t.lower()
            if tl == 'string':
                code = "(() => { const len = view.getInt32(o, true); o += 4; "
                code += "const s = new TextDecoder().decode(new Uint8Array(view.buffer, view.byteOffset + o, len)); o += len; return s; })()"
                return code
            if tl == 'float':
                return "(() => { const v = view.getFloat32(o, true); o += 4; return v; })()"
            if tl == 'double':
                return "(() => { const v = view.getFloat64(o, true); o += 8; return v; })()"
            if tl == 'bool':
                return "(() => { const v = view.getUint8(o) !== 0; o += 1; return v; })()"
            # int / enum / classId等はすべてint32として扱う
            return "(() => { const v = view.getInt32(o, true); o += 4; return v; })()"

        def _js_basic_write(t, expr):
            tl = t.lower()
            if tl == 'string':
                code = f"{{ const b = new TextEncoder().encode({expr}); view.setInt32(o, b.length, true); o += 4; "
                code += "new Uint8Array(view.buffer, view.byteOffset + o, b.length).set(b); o += b.length; }"
                return code
            if tl == 'float':
                return f"{{ view.setFloat32(o, {expr}, true); o += 4; }}"
            if tl == 'double':
                return f"{{ view.setFloat64(o, {expr}, true); o += 8; }}"
            if tl == 'bool':
                return f"{{ view.setUint8(o, {expr} ? 1 : 0); o += 1; }}"
            return f"{{ view.setInt32(o, {expr}, true); o += 4; }}"

        read_code = f"        this.{var_name} = new Map();\n"
        read_code += f"        {{ const __n = view.getInt32(o, true); o += 4;\n"
        read_code += f"          for (let __i = 0; __i < __n; __i++) {{\n"
        read_code += f"              const __k = {_js_basic_read(key_type)};\n"
        if value_array_size == -1:
            read_code += "              const __cnt = view.getInt32(o, true); o += 4;\n"
            read_code += "              const __v = [];\n"
            read_code += f"              for (let __j = 0; __j < __cnt; __j++) {{ __v.push({_js_basic_read(value_type)}); }}\n"
        else:
            read_code += f"              const __v = {_js_basic_read(value_type)};\n"
        read_code += f"              this.{var_name}.set(__k, __v);\n"
        read_code += "          }\n        }\n"

        write_code = f"        view.setInt32(o, this.{var_name}.size, true); o += 4;\n"
        write_code += f"        for (const [__k, __v] of this.{var_name}.entries()) {{\n"
        write_code += f"            {_js_basic_write(key_type, '__k')}\n"
        if value_array_size == -1:
            write_code += "            view.setInt32(o, __v.length, true); o += 4;\n"
            write_code += f"            for (const __item of __v) {{ {_js_basic_write(value_type, '__item')} }}\n"
        else:
            write_code += f"            {_js_basic_write(value_type, '__v')}\n"
        write_code += "        }\n"

        json_code = f"        this.{var_name} = new Map();\n"
        json_code += f"        for (const __e of (data.{var_name} && data.{var_name}.entries) || []) {{\n"
        json_code += f"            this.{var_name}.set(__e.key, __e.value);\n"
        json_code += "        }\n"

        json_write_code = f"        result.{var_name} = {{ entries: Array.from(this.{var_name}.entries()).map(([key, value]) => ({{ key, value }})) }};\n"

        return {
            'field': f"        this.{var_name} = new Map(); // {description}\n",
            'read': read_code, 'write': write_code,
            'json': json_code, 'json_write': json_write_code,
            'used_class': None, 'is_enum': False, 'used_enum': None,
            'is_table_id': False, 'used_table_id': None,
        }

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

    # --- write(view, offset)コード（read(view,o)と対称。新しいoffsetを返す）------
    def js_write_stmt(target_expr):
        if js_type == 'vector2':
            return (f"        view.setFloat32(o, {target_expr}[0], true); o += 4;\n"
                     f"        view.setFloat32(o, {target_expr}[1], true); o += 4;\n")
        if js_type == 'vector3':
            return (f"        view.setFloat32(o, {target_expr}[0], true); o += 4;\n"
                     f"        view.setFloat32(o, {target_expr}[1], true); o += 4;\n"
                     f"        view.setFloat32(o, {target_expr}[2], true); o += 4;\n")
        if js_type == 'int' or js_type == 'int32':
            return f"        view.setInt32(o, {target_expr}, true); o += 4;\n"
        if js_type == 'byte':
            return f"        view.setUint8(o, {target_expr}); o += 1;\n"
        if js_type == 'short':
            return f"        view.setInt16(o, {target_expr}, true); o += 2;\n"
        if js_type == 'uint':
            return f"        view.setUint32(o, {target_expr}, true); o += 4;\n"
        if js_type == 'long' or js_type == 'int64':
            return f"        view.setBigInt64(o, BigInt({target_expr}), true); o += 8;\n"
        if js_type == 'char':
            return f"        view.setUint16(o, {target_expr}.charCodeAt(0), true); o += 2;\n"
        if js_type == 'float':
            return f"        view.setFloat32(o, {target_expr}, true); o += 4;\n"
        if js_type == 'double':
            return f"        view.setFloat64(o, {target_expr}, true); o += 8;\n"
        if js_type == 'bool':
            return f"        view.setUint8(o, {target_expr} ? 1 : 0); o += 1;\n"
        if js_type == 'string':
            code = f"        {{ const __bytes = new TextEncoder().encode({target_expr}); view.setInt32(o, __bytes.length, true); o += 4;\n"
            code += "          new Uint8Array(view.buffer, view.byteOffset + o, __bytes.length).set(__bytes); o += __bytes.length; }\n"
            return code
        if is_enum or is_table_id:
            return f"        view.setInt32(o, {target_expr}, true); o += 4;\n"
        if is_class:
            return f"        o = {target_expr}.write(view, o);\n"
        return f"        o += 4; // Unsupported type for write: {js_type}\n"

    write_code = ""
    if is_list or is_array:
        write_code = f"        view.setInt32(o, this.{var_name}.length, true); o += 4;\n" if is_list else ""
        write_code += f"        for (const __v of this.{var_name}) {{\n"
        write_code += "    " + js_write_stmt("__v").replace("\n", "\n    ").rstrip() + "\n"
        write_code += "        }\n"
    else:
        write_code = js_write_stmt(f"this.{var_name}")

    # --- writeJson(data)コード: 引数に渡されたオブジェクトへ自身の値を書き込む ---
    # （loadJson(data)と対で「引数にデータを入れる」方式に統一する）
    def js_to_json_expr(expr):
        if js_type in ('vector2', 'vector3'):
            return f"[...{expr}]"
        return expr

    if is_class:
        json_write_assign = (
            f"        if (this.{var_name}) {{ result.{var_name} = {{}}; this.{var_name}.writeJson(result.{var_name}); }}\n"
            f"        else {{ result.{var_name} = null; }}\n"
        )
    elif is_list or is_array:
        if is_class:
            json_write_assign = (
                f"        result.{var_name} = this.{var_name}.map(__v => {{\n"
                f"            if (!__v) return null;\n"
                f"            const __d = {{}}; __v.writeJson(__d); return __d;\n"
                f"        }});\n"
            )
        else:
            json_write_assign = f"        result.{var_name} = [...this.{var_name}];\n"
    else:
        json_write_assign = f"        result.{var_name} = {js_to_json_expr('this.' + var_name)};\n"

    return {
        'field': f"        this.{var_name} = {initial}; // {description}\n",
        'read': read_code,
        'write': write_code,
        'json': json_code,
        'json_write': json_write_assign,
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
    py_dir = os.path.join(SCRIPT_DATA_DIR, CLASS_DATA, name)
    os.makedirs(py_dir, exist_ok=True)

    # ★ 共有ランタイムファイル（バイナリ読み書き・bit/color/bezier用クラス）を
    #   自動生成のたびに最新化する（C#側の_ensure_custom_bit_field_cs()と同じ方式）。
    _ensure_py_binary_io()
    _ensure_py_runtime_types()

    used_classes = set()
    enum_classes = set()
    table_classes = set()
    used_runtime_types = set()
    field_lines = []
    read_lines = []
    write_lines = []
    json_lines = []
    json_write_lines = []

    for item in data:
        f = generate_python_field(item, enum_list, class_list, class_id_list)
        field_lines.append(f['field'])
        read_lines.append(f['read'])
        write_lines.append(f.get('write', ''))
        json_lines.append(f['json'])
        json_write_lines.append(f.get('json_write', ''))
        if f['used_class']:
            used_classes.add(f['used_class'])
        if f['is_enum']:
            enum_classes.add(f['used_enum'])
        if f['is_table_id']:
            table_classes.add(f['used_table_id'])
        if f.get('used_runtime_type'):
            used_runtime_types.add(f['used_runtime_type'])

    base_path = os.path.join(py_dir, f"Base{name}.py")
    with open(base_path, 'w', encoding='utf-8') as f:
        f.write("from ..BaseCustomClassData import BaseCustomClassData\n")
        if used_runtime_types:
            f.write(f"from .._Shared.runtime_types import {', '.join(sorted(used_runtime_types))}\n")
        for uc in sorted(used_classes):
            if uc != name:  # 自分自身は不要
                f.write(f"from ...class_data.{uc}.{uc} import {uc}\n")
        for ec in sorted(enum_classes):
            if ec != name:
                f.write(f"from ...enum.{ec.replace('ID', '')}.{ec} import {ec}\n")
        for tc in sorted(table_classes):
            if tc != name:
                f.write(f"from ...class_data_id.{tc.replace('TableID', '')}.{tc} import {tc}\n")

        f.write("\n")
        f.write(f"class Base{name}(BaseCustomClassData):\n")
        f.write("    def __init__(self):\n")
        f.write("        super().__init__()\n")
        for line in field_lines:
            f.write(line)
        f.write("\n    def read(self, reader):\n")
        for line in read_lines:
            f.write(line)
        # ★ write(writer): readと対称のバイナリ書込。writerの生成・open/closeは
        #   呼び出し元の責務（このメソッド内では行わない）。
        f.write("\n    def write(self, writer):\n")
        for line in write_lines:
            f.write(line)
        f.write("\n    def load_json(self, data):\n")
        for line in json_lines:
            f.write(line)
        # ★ write_json(data): 引数に渡された辞書へ自身の値を書き込む
        #   （load_jsonと対になる「引数にデータを入れる」方式に統一）。
        f.write("\n    def write_json(self, data):\n")
        for line in json_write_lines:
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
    js_dir = os.path.join(SCRIPT_DATA_DIR, CLASS_DATA, name)
    os.makedirs(js_dir, exist_ok=True)

    # ★ 共有ランタイムファイル（bit/bezier用クラス）を自動生成のたびに最新化する
    #   （C#側の_ensure_custom_bit_field_cs()と同じ方式）。
    _ensure_js_runtime_types()

    used_classes = set()
    enum_classes = set()
    table_classes = set()
    used_runtime_types = set()

    field_lines = []
    read_lines = []
    write_lines = []
    json_lines = []
    json_write_lines = []

    for item in data:
        f = generate_js_field(item, enum_list, class_list, class_id_list)
        field_lines.append(f['field'])
        read_lines.append(f['read'])
        write_lines.append(f.get('write', ''))
        json_lines.append(f['json'])
        json_write_lines.append(f.get('json_write', ''))
        if f['used_class']:
            used_classes.add(f['used_class'])
        if f['is_enum']:
            enum_classes.add(f['used_enum'])
        if f['is_table_id']:
            table_classes.add(f['used_table_id'])
        if f.get('used_runtime_type'):
            used_runtime_types.add(f['used_runtime_type'])

    base_path = os.path.join(js_dir, f"Base{name}.js")
    with open(base_path, 'w', encoding='utf-8') as f:
        f.write("import { BaseCustomClassData } from '../BaseCustomClassData.js';\n")
        if used_runtime_types:
            f.write(f"import {{ {', '.join(sorted(used_runtime_types))} }} from '../_Shared/runtimeTypes.js';\n")
        for uc in sorted(used_classes):
            if uc != name:
                f.write(f"import {{ {uc} }} from '../{uc}/{uc}.js';\n")
        for ec in sorted(enum_classes):
            if ec != name:
                f.write(f"import {{ {ec} }} from '../../enum/{ec.replace('ID', '')}/{ec}.js';\n")
        for tc in sorted(table_classes):
            if tc != name:
                f.write(f"import {{ {tc} }} from '../../class_data_id/{tc.replace('TableID', '')}/{tc}.js';\n")
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
        # ★ write(view, offset): readと対称のバイナリ書込。DataViewの生成・
        #   バッファ確保は呼び出し元の責務とし、書込後のoffsetを返す。
        f.write("    write(view, offset) {\n")
        f.write("        let o = offset;\n")
        for line in write_lines:
            f.write(line)
        f.write("        return o;\n")
        f.write("    }\n\n")
        f.write("    loadJson(data) {\n")
        for line in json_lines:
            f.write(line)
        f.write("    }\n\n")
        # ★ writeJson(result): loadJson(data)と対で、引数に渡されたオブジェクトへ
        #   自身の値を書き込む方式に統一する。
        f.write("    writeJson(result) {\n")
        for line in json_write_lines:
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

    py_dir = os.path.join(SCRIPT_DATA_DIR, CLASS_DATA_ID, name)
    os.makedirs(py_dir, exist_ok=True)

    row_path = os.path.join(py_dir, f"{name}Row.py")
    with open(row_path, 'w', encoding='utf-8') as f:
        f.write("from ..BaseClassDataRow import BaseClassDataRow\n")
        for uc in sorted(used_classes):
            if uc != name:
                # 相対パス（CLASS_DATA_ID/name/ から CLASS_DATA/uc/uc.py へ）
                f.write(f"from ...class_data.{uc}.{uc} import {uc}\n")
        for ec in sorted(enum_classes):
            if ec != name:
                f.write(f"from ...enum.{ec.replace('ID', '')}.{ec} import {ec}\n")
        for tc in sorted(table_classes):
            if tc != name:
                f.write(f"from ...class_data_id.{tc.replace('TableID', '')}.{tc} import {tc}\n")
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

    js_dir = os.path.join(SCRIPT_DATA_DIR, CLASS_DATA_ID, name)
    os.makedirs(js_dir, exist_ok=True)

    row_path = os.path.join(js_dir, f"{name}Row.js")
    with open(row_path, 'w', encoding='utf-8') as f:
        f.write("import { BaseClassDataRow } from '../BaseClassDataRow.js';\n")
        for uc in sorted(used_classes):
            if uc != name:
                f.write(f"import {{ {uc} }} from '../../../class_data/{uc}/{uc}.js';\n")
        for ec in sorted(enum_classes):
            if ec != name:
                f.write(f"import {{ {ec} }} from '../../enum/{ec.replace('ID', '')}/{ec}.js';\n")
        for tc in sorted(table_classes):
            if tc != name:
                f.write(f"import {{ {tc} }} from '../../class_data_id/{tc.replace('TableID', '')}/{tc}.js';\n")
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
    py_dir = os.path.join(SCRIPT_DATA_DIR, CLASS_DATA_ID, name)
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
    js_dir = os.path.join(SCRIPT_DATA_DIR, CLASS_DATA_ID, name)
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