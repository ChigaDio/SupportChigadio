# -*- coding: utf-8 -*-
"""
pythonSrc/constants.py

app.py およびルート別モジュール（class_data / class_data_id / matrix / state /
behavior_routes など）から共有される定数群。

ここに定数を集約することで、各モジュールが app.py を逆に import する
循環importを避けている。
"""

# --- データ格納ディレクトリ名（DATA_DIR 配下のサブフォルダ名） ---
ENUM = 'enum'
CLASS_DATA = 'class_data'
CLASS_DATA_ID = 'class_data_id'
CLASS_DATA_MATRIX_ID = 'class_data_matrix_id'
STATE_DATA = 'state_data'
CONST_CLASS_DATA = 'const_class_data'

ASSETS_DATA = "assets_data"
GAMEOBJECT_DATA = "gameobject"
MATERIAL_DATA = "material"
SOUND_DATA = "sound"
TEXTURE_DATA = "texture"

# --- Unity側 Script 出力フォルダ関連 ---
SCRIPT = 'Script'
OBJECTPOOL = 'ObjectPool'
EDITOR = "Editor"
DEBUG = "Debug"
LOG = "Log"
PYTHON = "Python"

# --- DLL配置関連 ---
SUBMODULE = "submodule"
PLUGIN = "Plugin"

# --- バイナリ書き込み用型マッピング（Vector2, Vector3含む） ---
TYPE_MAP = {
    'int': {'pack': 'i', 'cs_read': 'ReadInt32'},
    'float': {'pack': 'f', 'cs_read': 'ReadSingle'},
    'double': {'pack': 'd', 'cs_read': 'ReadDouble'},
    'bool': {'pack': '?', 'cs_read': 'ReadBoolean'},
    'string': {'pack': None, 'cs_read': None},  # 特殊処理
    'vector2': {'pack': None, 'cs_read': None},  # 特殊処理
    'vector3': {'pack': None, 'cs_read': None},  # 特殊処理
}

# --- ConstClassData で使用できる型と、C#での表現 ---
CONST_TYPE_MAP = {
    'int':     {'cs_type': 'int',    'is_const': True,  'default': '0'},
    'uint':    {'cs_type': 'uint',   'is_const': True,  'default': '0'},
    'float':   {'cs_type': 'float',  'is_const': True,  'default': '0'},
    'string':  {'cs_type': 'string', 'is_const': True,  'default': ''},
    # Vector2 / Vector3 はC#のconstにできないため static readonly を使う
    'vector2': {'cs_type': 'Vector2', 'is_const': False, 'default': [0, 0]},
    'vector3': {'cs_type': 'Vector3', 'is_const': False, 'default': [0, 0, 0]},
}
