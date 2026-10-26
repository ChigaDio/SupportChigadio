"""Role 入力フォーム (BaseRoleInputForm.js) の「画面に依存しない」ロジック (Qt 非依存)。

対応表 (JS -> Python):
    getDefaultValue                -> get_default_value
    useEffect の formattedData     -> build_initial_form_data
    isFieldEnabledByDependency     -> is_field_enabled_by_dependency
    renderField / renderSingle の分岐 -> field_editor_kind (どの編集部品を出すか)
    NestedClassDataField           -> build_sub_schema / nested_initial_data / nested_to_value
    NumericInput                   -> numeric_input_change / numeric_input_blur
    BitValueEditor                 -> bit_*
    ColorValueEditor               -> to_hex / parse_hex_color / RecentColors
    BezierValueEditor              -> hermite / bezier_*
    DictionaryValueEditor          -> default_dict_scalar / dictionary_*
    VoiceRefFieldEditor / TextListIndexFieldEditor -> voice_* / text_list_* / resolve_scenario_key
    loadData (型オプション取得)      -> load_type_context
"""
from __future__ import annotations

import json
import math
import os
import re

from .dsl import js_number_to_string, js_string, js_truthy

VECTOR_AXIS_LABELS = {
    "vector2": ["X", "Y"],
    "vector3": ["X", "Y", "Z"],
    "vector4": ["X", "Y", "Z", "W"],
}

INT_TYPES = ["int", "short", "long", "byte"]
FLOAT_TYPES = ["float", "double", "decimal"]


def _lower(t) -> str:
    return js_string(t).lower()


def js_round(x) -> int:
    """Math.round (.5 は +∞ 方向)。"""
    return int(math.floor(x + 0.5))


# ============================================================
# 型オプション (enum / class_data / custom class)
# ============================================================
def make_type_context(enum_values=None, class_data_schemas=None, custom_class_schemas=None) -> dict:
    return {"enumValues": enum_values or {}, "classDataSchemas": class_data_schemas or {},
            "customClassSchemas": custom_class_schemas or {}}


def collect_types(fields) -> set:
    types = set()
    for f in fields or []:
        types.add(f.get("type"))
        if f.get("subFields"):
            types |= collect_types(f["subFields"])
    return types


def load_type_context(lookups, fields) -> dict:
    """フォームが必要とする型(enum / class_data_id / class_data / custom_class_data_id)の候補を取得する。
    ネストしたフォームはこの結果をそのまま共有する (JS の RoleFormTypeOptionsContext)。"""
    types = collect_types(fields)
    enum_list = lookups.enum_ids()
    class_id_list = lookups.class_data_ids()
    class_data_list = lookups.class_data_list()
    custom = lookups.custom_options()
    custom_class_id_list = custom.get("custom_class_id_list") or []
    enum_map, class_map = {}, {}
    class_data_names = {c.get("name") for c in class_data_list}
    for e in enum_list:
        if e.get("name") in types:
            enum_map[e["name"]] = lookups.enum_members(e["name"])
    for c in class_id_list:
        if c.get("name") in types:
            enum_map[c["name"]] = lookups.class_data_id_members(c["name"])
    for c in class_data_list:
        if c.get("name") in types:
            class_map[c["name"]] = lookups.class_data(c["name"]) or []
    for name in custom_class_id_list:
        if name in types:
            enum_map[name] = lookups.custom_class_data_id_members(name)
    # JS: valuesMap のキーが classDataList に在れば class_data 側、無ければ enum 側
    for k in list(enum_map):
        if k in class_data_names:
            class_map[k] = enum_map.pop(k)
    return make_type_context(enum_map, class_map, custom.get("custom_class_schemas") or {})


def enum_option_value(v):
    """enum の要素 (文字列 or {property|enum_property}) から値を取り出す。"""
    if isinstance(v, dict):
        return v.get("property") or v.get("enum_property") or v
    return v


def enum_options(type_name, values) -> list:
    """Autocomplete の候補 [{value, label}] (先頭は None)。"""
    return [{"value": f"{type_name}ID.None", "label": "None"}] + [
        {"value": f"{type_name}ID.{js_string(enum_option_value(v))}", "label": js_string(enum_option_value(v))}
        for v in values]


# ============================================================
# 既定値・初期値
# ============================================================
def get_default_value(type_, array_size, options, ctx: dict):
    """型ごとの汎用初期値 (JS の getDefaultValue)。"""
    enum_values = ctx.get("enumValues", {})
    class_schemas = ctx.get("classDataSchemas", {})
    custom_schemas = ctx.get("customClassSchemas", {})

    def base():
        low = _lower(type_)
        if low in INT_TYPES:
            return 0
        if low in FLOAT_TYPES:
            return 0.0
        if low == "char":
            return ""
        if low == "bool":
            return False
        if low == "string":
            return ""
        if low in VECTOR_AXIS_LABELS:
            return [0] * len(VECTOR_AXIS_LABELS[low])
        if type_ == "bit":
            return {"size": (options or {}).get("size", 8) if (options or {}).get("size") is not None else 8, "bits": []}
        if type_ == "color":
            return {"r": 1, "g": 1, "b": 1, "a": 1}
        if type_ == "bezier":
            o = options or {}
            return {"points": [
                {"time": 0, "value": o["min"] if o.get("min") is not None else 0, "inTangent": 0, "outTangent": 0},
                {"time": 1, "value": o["max"] if o.get("max") is not None else 1, "inTangent": 0, "outTangent": 0}]}
        if type_ == "dictionary":
            return {"entries": []}
        if type_ in ("text_list_index", "voice_ref"):
            return -1
        if type_ in custom_schemas:
            return {f["name"]: get_default_value(f.get("type"), f.get("arraySize"), f.get("options"), ctx)
                    for f in custom_schemas[type_] or []}
        if type_ in enum_values and len(enum_values[type_]) > 0:
            return f"{type_}ID.None"
        if type_ in class_schemas and len(class_schemas[type_]) > 0:
            return {f["name"]: get_default_value(f.get("type"), f.get("arraySize"), f.get("options"), ctx)
                    for f in class_schemas[type_] or []}
        return ""

    if array_size is None or array_size == 0:
        return base()
    if isinstance(array_size, (int, float)) and array_size > 0:
        return [base() for _ in range(int(array_size))]
    if array_size == -1:
        return []
    return base()


def build_initial_form_data(schema, initial_data, ctx: dict) -> list:
    """優先順位: ①既存データの値 → ②Role側に保存済みのデフォルト値(field.default) → ③型ごとの汎用初期値。"""
    out = []
    for field in schema["fields"]:
        item = next((d for d in initial_data or [] if d.get("name") == field.get("name")), None)
        has_saved_default = field.get("default") is not None
        if item is not None:
            value = item.get("value")
        elif has_saved_default:
            value = field["default"]
        else:
            value = get_default_value(field.get("type"), field.get("arraySize"), None, ctx)
        out.append({"name": field.get("name"), "value": value,
                    "arraySize": field["arraySize"] if field.get("arraySize") is not None else 0})
    return out


def is_field_enabled_by_dependency(field, form_data) -> bool:
    """dependency (parentFieldName / enableValues) を評価する。無ければ常に表示。"""
    dep = field.get("dependency")
    if not dep or not js_truthy(dep.get("parentFieldName")):
        return True
    parent = next((d for d in form_data if d.get("name") == dep["parentFieldName"]), None)
    parent_val = parent.get("value") if parent else None
    enable_values = dep.get("enableValues") or []
    if len(enable_values) == 0:
        return True
    if isinstance(parent_val, bool):
        for v in enable_values:
            if isinstance(v, bool):
                if v == parent_val:
                    return True
                continue
            s = js_string(v).lower()
            if (s == "true" and parent_val is True) or (s == "false" and parent_val is False):
                return True
        return False
    str_val = "" if parent_val is None else js_string(parent_val)
    short_val = str_val.split(".")[-1] if "." in str_val else str_val
    if not str_val or short_val == "None" or str_val.endswith(".None"):
        return False
    for v in enable_values:
        sv = js_string(v)
        short_enable = sv.split(".")[-1] if "." in sv else sv
        if sv == str_val or short_enable == short_val or sv == short_val or short_enable == str_val:
            return True
    return False


def field_editor_kind(field, ctx: dict) -> str:
    """renderSingle が選ぶ編集部品の種類。
    'voice_ref' 'text_list_index' 'bit' 'color' 'bezier' 'dictionary' 'custom_class' 'enum' 'class'
    'string' 'char' 'int' 'float' 'bool' 'vector' 'text'(フォールバック)"""
    t = field.get("type")
    for k in ("voice_ref", "text_list_index", "bit", "color", "bezier", "dictionary"):
        if t == k:
            return k
    if (ctx["customClassSchemas"].get(t) or []):
        return "custom_class"
    if len(ctx["enumValues"].get(t) or []) > 0:
        return "enum"
    if (ctx["classDataSchemas"].get(t) or []):
        return "class"
    low = _lower(t)
    if low == "string":
        return "string"
    if low == "char":
        return "char"
    if low in INT_TYPES:
        return "int"
    if low in FLOAT_TYPES:
        return "float"
    if low == "bool":
        return "bool"
    if low in VECTOR_AXIS_LABELS:
        return "vector"
    return "text"


def field_array_info(field) -> dict:
    """配列の種類。{"kind": 'single'|'fixed'|'dynamic', "length": n|None}"""
    n = field.get("arraySize") if field.get("arraySize") is not None else 0
    if n == 0:
        return {"kind": "single", "length": None}
    if n == -1:
        return {"kind": "dynamic", "length": None}
    return {"kind": "fixed", "length": n}


def current_field_value(field, form_data, ctx):
    item = next((d for d in form_data if d.get("name") == field.get("name")), None)
    v = item.get("value") if item else None
    if v is None:
        v = get_default_value(field.get("type"), field.get("arraySize"), None, ctx)
    return v


def array_value_of(field, current, ctx) -> list:
    """配列フィールドの現在値(リストでなければ既定の配列)。"""
    info = field_array_info(field)
    if isinstance(current, list):
        return current
    if info["kind"] == "dynamic":
        return []
    return [get_default_value(field.get("type"), 0, None, ctx) for _ in range(int(info["length"] or 0))]


def move_item(arr, src, dst) -> list:
    new = list(arr)
    item = new.pop(src)
    new.insert(dst, item)
    return new


def set_field_value(form_data, name, value, array_size=None) -> list:
    """handleChange。"""
    return [({**d, "value": value, "arraySize": array_size if array_size is not None else d.get("arraySize")}
             if d.get("name") == name else d) for d in form_data]


# ---- ネストした class_data
def build_sub_schema(fields) -> dict:
    return {"fields": [{**sub, "label": sub.get("label") or sub.get("name"),
                        "arraySize": sub["arraySize"] if sub.get("arraySize") is not None else 0} for sub in fields]}


def nested_initial_data(value, sub_schema) -> list:
    out = []
    for n, v in (value or {}).items():
        f = next((f for f in sub_schema["fields"] if f.get("name") == n), None)
        out.append({"name": n, "value": v, "arraySize": (f.get("arraySize") if f else None) or 0})
    return out


def nested_to_value(sub_data) -> dict:
    return {d["name"]: d["value"] for d in sub_data}


# ============================================================
# 数値入力 (NumericInput)
# ============================================================
_ALLOW_FLOAT = re.compile(r"^-?(\d*\.?\d*)?\Z")
_ALLOW_INT = re.compile(r"^-?\d*\Z")


def _parse_num(raw: str, is_float: bool):
    m = re.match(r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", raw) if is_float else re.match(r"\s*([+-]?\d+)", raw)
    if not m:
        return None
    if not is_float:
        return int(m.group(1))
    v = float(m.group(1))
    return int(v) if v == int(v) and abs(v) < 1e21 else v


def numeric_input_change(raw: str, is_float: bool):
    """入力欄の変更。-> (accepted, notify)  accepted=False なら入力を受け付けない。
    notify は (True, 値) か (False, None)。"""
    pat = _ALLOW_FLOAT if is_float else _ALLOW_INT
    if not pat.match(raw):
        return False, (False, None)
    parsed = _parse_num(raw, is_float)
    if parsed is not None:
        return True, (True, parsed)
    if raw in ("", "-"):
        return True, (True, 0)
    return True, (False, None)


def numeric_input_blur(input_str: str, is_float: bool):
    """フォーカスアウト。-> (表示する文字列, 通知する値)"""
    parsed = _parse_num(input_str, is_float)
    if parsed is None or input_str == "-":
        return "0", 0
    return js_number_to_string(parsed), parsed


# ============================================================
# bit
# ============================================================
def bit_flag_names(options, value) -> list:
    size = (options or {}).get("size")
    if size is None:
        size = (value or {}).get("size") if isinstance(value, dict) and value.get("size") is not None else 8
    names = (options or {}).get("flagNames")
    if names and len(names) == size:
        return list(names)
    return [f"Flag{i}" for i in range(size)]


def bit_size(options, value) -> int:
    s = (options or {}).get("size")
    if s is None:
        s = value.get("size") if isinstance(value, dict) else None
    return s if s is not None else 8


def bit_toggle(value, options, i) -> dict:
    size = bit_size(options, value)
    bits = value.get("bits") if isinstance(value, dict) and isinstance(value.get("bits"), list) else []
    if (options or {}).get("mode") == "single":
        return {"size": size, "bits": [i]}
    return {"size": size, "bits": [b for b in bits if b != i] if i in bits else [*bits, i]}


def bit_filter(flag_names, query) -> list:
    q = js_string(query).strip().lower()
    entries = [(label, i) for i, label in enumerate(flag_names)]
    return [e for e in entries if q in e[0].lower()] if q else entries


# ============================================================
# color
# ============================================================
COLOR_DEFAULT = {"r": 1, "g": 1, "b": 1, "a": 1}
COLOR_COMMIT_MS = 150
RECENT_COLORS_MAX = 10


def to_hex(v) -> str:
    return format(js_round(max(0, min(1, v)) * 255), "02x")


def color_key(c) -> str:
    a = c.get("a")
    return f"{to_hex(c['r'])}{to_hex(c['g'])}{to_hex(c['b'])}{js_round((1 if a is None else a) * 100)}"


_HEX_RE = re.compile(r"^#?([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})\Z", re.I)


def parse_hex_color(text):
    """'#RGB' / '#RRGGBB' / '#RRGGBBAA'(# は省略可)を {r,g,b,a?} へ。不正なら None。"""
    m = _HEX_RE.match(js_string(text).strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(ch + ch for ch in h)
    out = {"r": int(h[0:2], 16) / 255, "g": int(h[2:4], 16) / 255, "b": int(h[4:6], 16) / 255}
    if len(h) == 8:
        out["a"] = int(h[6:8], 16) / 255
    return out


def color_hex(c) -> str:
    return f"#{to_hex(c['r'])}{to_hex(c['g'])}{to_hex(c['b'])}"


def color_css(c) -> str:
    a = c.get("a")
    return f"rgba({js_round(c['r'] * 255)},{js_round(c['g'] * 255)},{js_round(c['b'] * 255)},{1 if a is None else a})"


class RecentColors:
    """最近使った色 (JS: localStorage 'scn-recent-colors-v1')。設定フォルダの JSON に保存。"""

    FILE = "scn-recent-colors-v1.json"

    def __init__(self, directory=None):
        self.path = os.path.join(directory, self.FILE) if directory else None
        self._cache = None

    def get(self) -> list:
        if self._cache is None:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self._cache = [c for c in raw if isinstance(c, dict) and isinstance(c.get("r"), (int, float))] \
                    if isinstance(raw, list) else []
            except (OSError, ValueError, TypeError):
                self._cache = []
        return self._cache

    def push(self, c):
        entry = {"r": c["r"], "g": c["g"], "b": c["b"], "a": 1 if c.get("a") is None else c["a"]}
        self._cache = ([entry] + [x for x in self.get() if color_key(x) != color_key(c)])[:RECENT_COLORS_MAX]
        if self.path:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f)
            except OSError:
                pass


# ============================================================
# bezier
# ============================================================
TANGENT_HANDLE_LEN = 40
TANGENT_MIN_DX = 10


def hermite(p0, p1, t) -> float:
    dt = (p1["time"] - p0["time"]) or 1
    s = (t - p0["time"]) / dt
    h00 = 2 * s ** 3 - 3 * s ** 2 + 1
    h10 = s ** 3 - 2 * s ** 2 + s
    h01 = -2 * s ** 3 + 3 * s ** 2
    h11 = s ** 3 - s ** 2
    return h00 * p0["value"] + h10 * dt * p0["outTangent"] + h01 * p1["value"] + h11 * dt * p1["inTangent"]


def bezier_points(value, options) -> list:
    o = options or {}
    if isinstance(value, dict) and isinstance(value.get("points"), list) and len(value["points"]) >= 2:
        return sorted(value["points"], key=lambda p: p["time"])
    return [{"time": 0, "value": o.get("min") if o.get("min") is not None else 0, "inTangent": 0, "outTangent": 0},
            {"time": 1, "value": o.get("max") if o.get("max") is not None else 1, "inTangent": 0, "outTangent": 0}]


class BezierGeometry:
    """SVG(W×H, 余白 PAD)上の座標変換。"""

    def __init__(self, options, W=360, H=180, PAD=20):
        o = options or {}
        self.min = o.get("min") if o.get("min") is not None else 0
        self.max = o.get("max") if o.get("max") is not None else 1
        self.W, self.H, self.PAD = W, H, PAD
        self.sx = W - PAD * 2
        self.sy = (H - PAD * 2) / ((self.max - self.min) or 1)

    def x_to_px(self, t):
        return self.PAD + t * (self.W - self.PAD * 2)

    def y_to_px(self, v):
        return self.H - self.PAD - ((v - self.min) / ((self.max - self.min) or 1)) * (self.H - self.PAD * 2)

    def px_to_x(self, px):
        return max(0, min(1, (px - self.PAD) / (self.W - self.PAD * 2)))

    def px_to_y(self, py):
        return self.min + (1 - (py - self.PAD) / (self.H - self.PAD * 2)) * (self.max - self.min)

    def tangent_to_handle_offset(self, tangent, side):
        dtime = 1 if side == "out" else -1
        dvalue = tangent if side == "out" else -tangent
        dx = self.sx * dtime
        dy = -self.sy * dvalue
        ln = math.hypot(dx, dy) or 1
        return dx / ln * TANGENT_HANDLE_LEN, dy / ln * TANGENT_HANDLE_LEN

    def handle_offset_to_tangent(self, dx, dy, side):
        min_dx = TANGENT_MIN_DX if side == "out" else -TANGENT_MIN_DX
        clamped = max(dx, min_dx) if side == "out" else min(dx, min_dx)
        return -(dy * self.sx) / (clamped * self.sy)

    def curve_points(self, points, steps=24):
        out = []
        for i in range(len(points) - 1):
            p0, p1 = points[i], points[i + 1]
            for s in range(steps + 1):
                t = p0["time"] + (p1["time"] - p0["time"]) * (s / steps)
                out.append((self.x_to_px(t), self.y_to_px(hermite(p0, p1, t))))
        return out


def bezier_update_point(points, index, patch) -> dict:
    return {"points": [({**p, **patch} if i == index else p) for i, p in enumerate(points)]}


def bezier_add_point(points, options) -> dict:
    o = options or {}
    mn = o.get("min") if o.get("min") is not None else 0
    mx = o.get("max") if o.get("max") is not None else 1
    return {"points": [*points, {"time": 0.5, "value": (mn + mx) / 2, "inTangent": 0, "outTangent": 0}]}


def bezier_remove_point(points, index):
    if len(points) <= 2:
        return None
    return {"points": [p for i, p in enumerate(points) if i != index]}


def js_parse_float_or0(s) -> float:
    """parseFloat(s) || 0"""
    from .transition_ops import js_parse_float
    v = js_parse_float(s)
    return v if v else 0


# ============================================================
# dictionary
# ============================================================
def default_dict_scalar(t, ctx: dict):
    low = _lower(t)
    if low in INT_TYPES:
        return 0
    if low in FLOAT_TYPES:
        return 0.0
    if low == "bool":
        return False
    if low in ("string", "char"):
        return ""
    if low in VECTOR_AXIS_LABELS:
        return [0] * len(VECTOR_AXIS_LABELS[low])
    if low == "bit":
        return {"size": 8, "bits": []}
    if low == "color":
        return {"r": 1, "g": 1, "b": 1, "a": 1}
    if low == "bezier":
        return {"points": [{"time": 0, "value": 0, "inTangent": 0, "outTangent": 0},
                           {"time": 1, "value": 1, "inTangent": 0, "outTangent": 0}]}
    if len(ctx["enumValues"].get(t) or []) > 0:
        return f"{t}ID.None"
    if t in ctx["customClassSchemas"] or t in ctx["classDataSchemas"]:
        return {}
    return ""


def dictionary_options(options) -> dict:
    o = options or {}
    va = o.get("valueArraySize") if o.get("valueArraySize") is not None else 0
    return {"keyType": o.get("keyType") or "int", "valueType": o.get("valueType") or "int",
            "valueIsArray": va != 0, "valueOptions": o.get("valueOptions") or {}}


def dictionary_entries(value) -> list:
    return value["entries"] if isinstance(value, dict) and isinstance(value.get("entries"), list) else []


def dictionary_add_entry(value, options, ctx) -> dict:
    d = dictionary_options(options)
    key = 0 if d["keyType"].lower() == "int" else f"{d['keyType']}ID.None"
    val = [] if d["valueIsArray"] else default_dict_scalar(d["valueType"], ctx)
    return {"entries": [*dictionary_entries(value), {"key": key, "value": val}]}


def dictionary_update(value, i, *, key=None, val=None, set_key=False, set_val=False) -> dict:
    es = []
    for idx, e in enumerate(dictionary_entries(value)):
        if idx == i:
            e = {**e}
            if set_key:
                e["key"] = key
            if set_val:
                e["value"] = val
        es.append(e)
    return {"entries": es}


def dictionary_remove(value, i) -> dict:
    return {"entries": [e for idx, e in enumerate(dictionary_entries(value)) if idx != i]}


# ============================================================
# voice_ref / text_list_index
# ============================================================
def index_value(value) -> int:
    """numericValue。数値以外・不正は -1。"""
    if isinstance(value, bool):
        return -1
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return value
    if isinstance(value, str) and value.strip() != "":
        m = re.match(r"\s*([+-]?\d+)", value)
        return int(m.group(1)) if m else -1
    return -1


def resolve_scenario_key(event_list, event_id, sub_id) -> str:
    """列キー "{イベント名}_{サブイベント名}"。見つからなければ ValueError。"""
    if not event_id or not sub_id:
        raise ValueError("シナリオイベント文脈が必要です（eventId / subId）。")
    ev = next((e for e in event_list or [] if js_string(e.get("id")) == js_string(event_id)), None)
    sub = next((s for s in (ev or {}).get("subEvents") or [] if js_string(s.get("subId")) == js_string(sub_id)), None)
    if not ev or not sub:
        raise ValueError("このシナリオ／サブイベントが見つかりませんでした（一覧を再読み込みしてください）。")
    return f"{ev.get('name')}_{sub.get('name')}"


def strip_sound_id_prefix(v) -> str:
    if v is None:
        return ""
    s = js_string(v)
    return s.split(".")[-1] if "." in s else s


def _join_defined(parts) -> str:
    return "_".join("" if p is None else js_string(p) for p in parts)


def build_sound_lookup(sound_data) -> dict:
    """/api/sound のレスポンスから「SoundID名 → {group, index, name, desc, type}」を作る。"""
    out = {}
    groups = (sound_data or {}).get("groups") or {}
    for group_name, group_value in groups.items():
        for index, item in enumerate((group_value or {}).get("items") or []):
            entry = {"group": group_name, "index": index, "name": item.get("name"),
                     "desc": item.get("desc") or "", "type": item.get("type")}
            nest = item.get("nest_path") if isinstance(item.get("nest_path"), list) else []
            keys = []
            for k in ("_".join(js_string(x) for x in [group_name, item.get("subgroup"), item.get("name")] if js_truthy(x)),
                      _join_defined([group_name, *nest, item.get("name")])):
                if k not in keys:
                    keys.append(k)
            for k in keys:
                out.setdefault(k, entry)
    return out


def extract_cell_list(cell, field_name):
    """セルから配列を取り出す。フィールド自体が無ければ None。"""
    if not isinstance(cell, (dict, list)):
        return []
    if isinstance(cell, list):
        return cell
    fc = cell.get(field_name, _MISSING)
    if fc is _MISSING:
        return None
    if isinstance(fc, dict) and "value" in fc:
        return fc["value"] if isinstance(fc["value"], list) else []
    return fc if isinstance(fc, list) else []


_MISSING = object()


def voice_languages(table, scenario_key, field_name) -> list:
    """Matrix の各行(=言語)から、このシナリオ列の voices を取り出す。[{label, colKey, list|None}]"""
    if not table or not scenario_key:
        return []
    data = table.get("data") or {}
    out = []
    for row_key in data:
        row = data[row_key] or {}
        col = next((k for k in row if k == scenario_key or k == f"ScenarioEventID.{scenario_key}"
                    or k.endswith(f".{scenario_key}")), None)
        lst = extract_cell_list(row[col], field_name) if col else None
        out.append({"label": row_key.split(".")[-1] if "." in row_key else row_key, "colKey": col, "list": lst})
    return out


def active_language(languages, language):
    for l in languages:
        if l["label"].lower() == js_string(language).lower():
            return l
    return languages[0] if languages else None


def voice_items(active, sound_lookup) -> list:
    items = []
    for i, sid in enumerate((active or {}).get("list") or []):
        sound_id = strip_sound_id_prefix(sid)
        info = sound_lookup.get(sound_id) if sound_lookup is not None else None
        desc = info.get("desc") if info else ""
        items.append({"index": i, "soundId": sound_id, "info": info,
                      "label": f"{i} : {sound_id}{' — ' + desc if desc else ''}"})
    return items


def length_mismatch(languages) -> str:
    with_list = [l for l in languages if isinstance(l["list"], list)]
    if len(with_list) < 2:
        return ""
    if len({len(l["list"]) for l in with_list}) > 1:
        return " / ".join(f"{l['label']}:{len(l['list'])}件" for l in with_list)
    return ""


def text_list_items(table, scenario_key, preview_language, field_name, matrix_name="ScenarioText") -> list:
    """text_list_index の候補 [{index, label, text}]。取れなければ ValueError(元の JS と同じ文言)。"""
    data = (table or {}).get("data") or {}
    row_keys = list(data.keys())
    lang_key = next((k for k in row_keys if k == preview_language or k.endswith(f".{preview_language}")
                     or k == f"LanguageID.{preview_language}"), None)
    if lang_key is None:
        lang_key = next((k for k in row_keys if js_string(k).lower() == js_string(preview_language).lower()), None)
    if lang_key is None:
        raise ValueError(f'Matrix {matrix_name} に言語 "{preview_language}" の行がありません'
                         f'（存在する行: {", ".join(row_keys) or "なし"}）。')
    row = data[lang_key] or {}
    col = next((k for k in row if k == scenario_key or k == f"ScenarioEventID.{scenario_key}"
                or k.endswith(f".{scenario_key}")), None)
    if col is None:
        raise ValueError(f'Matrix {matrix_name}（{preview_language}）に列 "{scenario_key}" がありません。'
                         f'Matrix 側にこのシナリオの行を追加してください。')
    cell = row[col] or {}
    lst = []
    if isinstance(cell, (dict, list)):
        fc = cell.get(field_name, _MISSING) if isinstance(cell, dict) else _MISSING
        if isinstance(fc, dict) and "value" in fc:
            lst = fc["value"] if isinstance(fc["value"], list) else []
        elif isinstance(fc, list):
            lst = fc
        elif isinstance(cell, list):
            lst = cell
        elif fc is _MISSING:
            raise ValueError(f'列 "{scenario_key}" にフィールド "{field_name}" がありません'
                             f'（このMatrixのフィールド: {", ".join(cell.keys()) or "なし"}）。')
    out = []
    for i, t in enumerate(lst):
        text = t if isinstance(t, str) else ("" if t is None else js_string(t))
        out.append({"index": i, "label": f"{i} : {text}", "text": text})
    return out


def js_normalize_numbers(v):
    """JS の number は 1.0 と 1 を区別しない。保存時に整数値の float を int へ寄せる (JSON が 1.0 にならないように)。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        if v == v and abs(v) < 1e15 and v == int(v):
            return int(v)
        return v
    if isinstance(v, list):
        return [js_normalize_numbers(x) for x in v]
    if isinstance(v, dict):
        return {k: js_normalize_numbers(x) for k, x in v.items()}
    return v
