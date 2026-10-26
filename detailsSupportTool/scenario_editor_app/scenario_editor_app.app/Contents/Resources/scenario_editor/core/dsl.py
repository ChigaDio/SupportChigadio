"""Transaction DSL (Role を 1 行 1 コマンドで書くテキスト) のコア実装。

`js_ref/src/scenarioTransactionDsl.js` の全 export を忠実に移植したもの。Qt 非依存。

対応表 (JS -> Python):
    tokenizeLine                -> tokenize_line
    DslIssue                    -> DslIssue (属性 from_ / to_dict() で "from" キー)
    parseLine                   -> parse_line
    parseDocument               -> parse_document
    findGroupHeaders            -> find_group_headers
    computeNextGroupHeader      -> compute_next_group_header
    computeNextSubgroupHeader   -> compute_next_subgroup_header
    renumberDuplicateNodeIds    -> renumber_duplicate_node_ids
    coerceValueTokens           -> coerce_value_tokens
    compileDocument             -> compile_document
    decompileRoles              -> decompile_roles
    lintDocument                -> lint_document
    SUBGROUP_SETTING_LINE_PREFIX-> SUBGROUP_SETTING_LINE_PREFIX
    isSubGroupSettingLine       -> is_sub_group_setting_line
    extractSubGroupSettingLines -> extract_sub_group_setting_lines
    compileSubGroupSetting      -> compile_sub_group_setting
    normalizeSubGroupSetting    -> normalize_sub_group_setting
    decompileSubGroupSetting    -> decompile_sub_group_setting
    getCompletionsAt            -> get_completions_at
    (非 export だが他モジュールが使うので公開) serializeValue -> serialize_value,
    getEffectiveSubFields -> get_effective_sub_fields, incrementTrailingNumber -> increment_trailing_number

規約:
  * トークン・AST・結果はすべて JS と同じキーの dict。`from` は文字列キー "from"。
  * JS の ``undefined`` / ``null`` は Python の ``None`` に統一する
    (``{"value": undefined, "error": "..."}`` は ``{"value": None, "error": "..."}``)。
  * 文字位置(from/to/cursorCh)は **Python の str のインデックス(コードポイント単位)**。
    JS は UTF-16 コード単位なので、BMP 外の文字(絵文字など)を含む行では JS と数値が異なる。
    Qt(QTextCursor は UTF-16)と接続するときは呼び出し側で変換すること。
  * 空白・改行・数字の正規表現クラスは JS の ``\\s`` / ``.`` / ``\\d`` と同じ集合に明示している。
"""
from __future__ import annotations

import json
import math
import random
import re
import time
from decimal import Decimal

# ============================================================
# JS 互換ヘルパー
# ============================================================

# JS の \s と同じ文字集合
_WS = r"\t\n\v\f\r    -     　﻿"
_S = f"[{_WS}]"
_NS = f"[^{_WS}]"
# JS の `.` (改行 4 種以外)
_DOT = r"[^\n\r  ]"

_INT_KEY_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")


def _is_array_index(k: str) -> bool:
    return bool(_INT_KEY_RE.match(k)) and int(k) < 4294967295


def js_number_to_string(x) -> str:
    """JS の Number.prototype.toString() と同じ表記。"""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        if abs(x) < 10 ** 21:
            return str(x)
        x = float(x)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    d = Decimal(repr(abs(x)))
    t = d.as_tuple()
    digits = "".join(str(i) for i in t.digits).rstrip("0")
    exp = t.exponent + len("".join(str(i) for i in t.digits))  # 小数点の位置 n
    if digits == "":
        return "0"
    k = len(digits)
    n = exp
    if k <= n <= 21:
        s = digits + "0" * (n - k)
    elif 0 < n <= 21:
        s = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        es = ("+" if e >= 0 else "-") + str(abs(e))
        s = digits[0] + ("." + digits[1:] if k > 1 else "") + "e" + es
    return sign + s


def js_string(v) -> str:
    """JS の String(v) / テンプレートリテラル展開に相当。"""
    if v is None:
        return "undefined"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return js_number_to_string(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ",".join("" if e is None else js_string(e) for e in v)
    if isinstance(v, dict):
        return "[object Object]"
    return str(v)


def js_truthy(v) -> bool:
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return not (v == 0 or (isinstance(v, float) and math.isnan(v)))
    if isinstance(v, str):
        return v != ""
    return True  # list / dict は JS では常に truthy


def _order_keys(d: dict) -> dict:
    """JS のオブジェクトの列挙順 (配列インデックス風キーが先に昇順) に並べ替える。"""
    idx = sorted((k for k in d if _is_array_index(k)), key=int)
    if not idx:
        return d
    rest = [k for k in d if not _is_array_index(k)]
    return {k: d[k] for k in idx + rest}


def js_json_stringify(v) -> str:
    """JSON.stringify(v) 相当 (空白なし, 数値は JS 表記, キー順は JS 準拠)。"""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            return "null"
        return js_number_to_string(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(js_json_stringify(e) for e in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(str(k), ensure_ascii=False) + ":" + js_json_stringify(e)
                              for k, e in _order_keys(v).items()) + "}"
    return "null"


def _normalize_json(v):
    if isinstance(v, float) and math.isfinite(v) and v == int(v) and abs(v) < 2 ** 53:
        return int(v)
    if isinstance(v, list):
        return [_normalize_json(e) for e in v]
    if isinstance(v, dict):
        return _order_keys({k: _normalize_json(e) for k, e in v.items()})
    return v


def _bad_const(name):
    raise ValueError(name)


def js_json_parse(raw: str):
    """JSON.parse 相当。失敗時は ValueError。"""
    return _normalize_json(json.loads(raw, parse_constant=_bad_const))


def _num_value(x):
    """float を JS の number のように扱う (整数値なら int)。"""
    if isinstance(x, float) and math.isfinite(x) and x == int(x) and abs(x) < 2 ** 53:
        return int(x)
    return x


def _lower(s) -> str:
    return (s or "").lower()


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else None


def _is_nonempty_list(v) -> bool:
    return isinstance(v, list) and len(v) > 0


# ============================================================
# トークナイザ
# ============================================================

TOKEN_PATTERN = re.compile(
    rf"#{_DOT}*\Z"
    r'|"(?:[^"\\]|\\.)*"'
    r"|[(){}\[\],=:]"
    r"|-?[0-9]+(?:\.[0-9]+)?"
    rf'|[^{_WS}(){{}}\[\],="#:]+',
    re.DOTALL,
)
# 注意: 文字列リテラル中の `\\.` は JS の `.` と同じく改行 4 種に一致しない。
TOKEN_PATTERN = re.compile(
    rf"#{_DOT}*\Z"
    rf'|"(?:[^"\\]|\\{_DOT})*"'
    r"|[(){}\[\],=:]"
    r"|-?[0-9]+(?:\.[0-9]+)?"
    rf'|[^{_WS}(){{}}\[\],="#:]+'
)

_NUM_START_RE = re.compile(r"^-?[0-9]")


def tokenize_line(line: str) -> list:
    tokens = []
    for m in TOKEN_PATTERN.finditer(line):
        raw = m.group(0)
        frm = m.start()
        to = frm + len(raw)
        if raw.startswith("#"):
            typ = "COMMENT"
        elif raw.startswith('"'):
            typ = "STRING"
        elif raw == "(":
            typ = "LPAREN"
        elif raw == ")":
            typ = "RPAREN"
        elif raw == "[":
            typ = "LBRACKET"
        elif raw == "]":
            typ = "RBRACKET"
        elif raw == "{":
            typ = "LBRACE"
        elif raw == "}":
            typ = "RBRACE"
        elif raw == ":":
            typ = "COLON"
        elif raw == ",":
            typ = "COMMA"
        elif raw == "=":
            typ = "EQUALS"
        elif _NUM_START_RE.match(raw):
            typ = "NUMBER"
        else:
            typ = "IDENT"
        tokens.append({"type": typ, "value": raw, "from": frm, "to": to})
    return tokens


# ============================================================
# 診断
# ============================================================

class DslIssue:
    """診断 1 件。JS の DslIssue と同じ (message, from, to, line, severity)。"""

    __slots__ = ("message", "from_", "to", "line", "severity")

    def __init__(self, message, from_, to, line, severity="error"):
        self.message = message
        self.from_ = from_
        self.to = to
        self.line = line
        self.severity = severity

    def to_dict(self) -> dict:
        return {"message": self.message, "from": self.from_, "to": self.to, "line": self.line, "severity": self.severity}

    def __eq__(self, other):
        return isinstance(other, DslIssue) and self.to_dict() == other.to_dict()

    def __repr__(self):
        return f"DslIssue({self.to_dict()!r})"


# ============================================================
# 行パーサー
# ============================================================

_OPEN_CLOSE = {"LPAREN": "RPAREN", "LBRACKET": "RBRACKET", "LBRACE": "RBRACE"}


def _collect_value_tokens(tokens, start):
    if start >= len(tokens):
        return {"valueTokens": [], "nextIndex": start, "error": "値が指定されていません"}
    t = tokens[start]
    close_type = _OPEN_CLOSE.get(t["type"])
    if close_type:
        depth = 1
        j = start + 1
        collected = [t]
        while j < len(tokens) and depth > 0:
            if tokens[j]["type"] == t["type"]:
                depth += 1
            if tokens[j]["type"] == close_type:
                depth -= 1
            collected.append(tokens[j])
            j += 1
        if depth != 0:
            return {"valueTokens": collected, "nextIndex": j, "error": "括弧が閉じられていません"}
        return {"valueTokens": collected, "nextIndex": j, "error": None}
    if t["type"] in ("STRING", "NUMBER", "IDENT"):
        return {"valueTokens": [t], "nextIndex": start + 1, "error": None}
    return {"valueTokens": [t], "nextIndex": start + 1, "error": f"予期しないトークンです: {t['value']}"}


def parse_line(raw_line: str, line_number: int) -> dict:
    """1 行を AST ノード(type: 'blank' | 'comment' | 'call')にする。"""
    tokens = tokenize_line(raw_line)
    errors = []

    if len(tokens) == 0:
        return {"type": "blank", "line": line_number, "raw": raw_line, "errors": errors}
    if tokens[0]["type"] == "COMMENT":
        return {"type": "comment", "line": line_number, "raw": raw_line, "errors": errors}

    trailing_comment = None
    if tokens[-1]["type"] == "COMMENT":
        trailing_comment = tokens.pop()

    name_token = tokens[0]
    if name_token["type"] != "IDENT":
        errors.append(DslIssue("Role名を指定してください", name_token["from"], name_token["to"], line_number))
        return {"type": "call", "line": line_number, "raw": raw_line, "name": None, "args": [],
                "trailingComment": trailing_comment, "errors": errors}

    args = []
    i = 1
    while i < len(tokens):
        key_token = tokens[i]
        if key_token["type"] != "IDENT":
            errors.append(DslIssue("引数名を指定してください（fieldName=value 形式）", key_token["from"], key_token["to"], line_number))
            i += 1
            continue
        eq_token = tokens[i + 1] if i + 1 < len(tokens) else None
        if not eq_token or eq_token["type"] != "EQUALS":
            errors.append(DslIssue(f"'=' が必要です: {key_token['value']}=...", key_token["from"], key_token["to"], line_number))
            i += 1
            continue
        res = _collect_value_tokens(tokens, i + 2)
        value_tokens, next_index, error = res["valueTokens"], res["nextIndex"], res["error"]
        if error:
            errors.append(DslIssue(error, key_token["from"], eq_token["to"], line_number))
        to = value_tokens[-1]["to"] if value_tokens else eq_token["to"]
        args.append({"key": key_token, "valueTokens": value_tokens, "from": key_token["from"], "to": to})
        i = next_index

    return {"type": "call", "line": line_number, "raw": raw_line, "name": name_token, "args": args,
            "trailingComment": trailing_comment, "errors": errors}


def parse_document(text: str) -> list:
    return [parse_line(line, idx) for idx, line in enumerate(text.split("\n"))]


# ============================================================
# 値の型変換
# ============================================================

def _strip_quotes(raw: str) -> str:
    return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")


NUMERIC_TYPES = {"int", "uint", "short", "long", "byte", "text_list_index", "voice_ref"}
INDEX_REF_TYPES = {"text_list_index", "voice_ref"}
FLOAT_TYPES = {"float", "double", "decimal"}
VECTOR_SIZES = {"vector2": 2, "vector3": 3, "vector4": 4}
VECTOR_FIELD_NAMES = {"vector2": ["x", "y"], "vector3": ["x", "y", "z"], "vector4": ["x", "y", "z", "w"]}

BEZIER_POINT_SUBFIELDS = [
    {"name": "time", "type": "float"},
    {"name": "value", "type": "float"},
    {"name": "inTangent", "type": "float"},
    {"name": "outTangent", "type": "float"},
]
BUILTIN_STRUCT_SUBFIELDS = {
    "bit": [
        {"name": "size", "type": "int"},
        {"name": "bits", "type": "int[]"},
    ],
    "color": [
        {"name": "r", "type": "float"},
        {"name": "g", "type": "float"},
        {"name": "b", "type": "float"},
        {"name": "a", "type": "float"},
    ],
    "bezier": [
        {"name": "points", "type": "BezierPoint[]", "subFields": BEZIER_POINT_SUBFIELDS},
    ],
}


def _normalize_builtin_type(t) -> str:
    return (t or "").lower()


def _base_type(field_type):
    """JS: (fieldType || 'string').endsWith('[]') ? fieldType.slice(0, -2) : fieldType"""
    if (field_type or "string").endswith("[]"):
        return field_type[:-2]
    return field_type


def _is_array_type(field_type) -> bool:
    return (field_type or "").endswith("[]")


def get_effective_sub_fields(field_type, sub_fields, class_data_schemas):
    if _is_nonempty_list(sub_fields):
        return sub_fields
    base_type = field_type[:-2] if (field_type or "").endswith("[]") else field_type
    base_lower = _normalize_builtin_type(base_type)
    if base_lower in BUILTIN_STRUCT_SUBFIELDS:
        return BUILTIN_STRUCT_SUBFIELDS[base_lower]
    if base_lower in VECTOR_FIELD_NAMES:
        return [{"name": n, "type": "float"} for n in VECTOR_FIELD_NAMES[base_lower]]
    from_map = class_data_schemas.get(base_type) if isinstance(class_data_schemas, dict) and base_type is not None else None
    if _is_nonempty_list(from_map):
        return [{"name": f.get("name"), "type": f.get("type"), "arraySize": f.get("arraySize"),
                 "options": f.get("options"), "subFields": f.get("subFields")} for f in from_map]
    return sub_fields


def increment_trailing_number(id_) -> str:
    s = "" if id_ is None else js_string(id_)
    m = re.match(r"^(.*?)([0-9]+)\Z", s, re.DOTALL) if "\n" in s else re.match(rf"^({_DOT}*?)([0-9]+)\Z", s)
    if m:
        digits = m.group(2)
        nxt = js_number_to_string(int(digits) + 1).rjust(len(digits), "0")
        return m.group(1) + nxt
    return f"{js_string(id_)}_2"


# ============================================================
# 見出し (# ==== SUB:x NODE:y ====)
# ============================================================

GROUP_HEADER_RE = re.compile(rf"^#{_S}*===={_S}*SUB:({_NS}+){_S}+NODE:({_NS}+){_DOT}*?===={_S}*\Z")


def find_group_headers(doc_text: str) -> list:
    headers = []
    for idx, line in enumerate(doc_text.split("\n")):
        m = GROUP_HEADER_RE.match(line)
        if m:
            headers.append({"subId": m.group(1), "pathKey": m.group(2), "lineIndex": idx})
    return headers


def compute_next_group_header(doc_text: str, cursor_line: int) -> dict:
    headers = find_group_headers(doc_text)
    current_sub_id = None
    for i in range(len(headers) - 1, -1, -1):
        if headers[i]["lineIndex"] <= cursor_line:
            current_sub_id = headers[i]["subId"]
            break
    if not current_sub_id:
        current_sub_id = headers[0]["subId"] if len(headers) > 0 else "1"

    top_level = [h for h in headers if h["subId"] == current_sub_id and "/" not in h["pathKey"]]
    new_path_key = increment_trailing_number(top_level[-1]["pathKey"]) if len(top_level) > 0 else "1"
    return {"subId": current_sub_id, "newPathKey": new_path_key}


def compute_next_subgroup_header(doc_text: str, cursor_line: int):
    headers = find_group_headers(doc_text)
    current_sub_id = None
    current_parent_id = None
    for i in range(len(headers) - 1, -1, -1):
        if headers[i]["lineIndex"] <= cursor_line:
            current_sub_id = headers[i]["subId"]
            current_parent_id = headers[i]["pathKey"].split("/")[0]
            break
    if not current_sub_id or not current_parent_id:
        return None

    siblings = [h for h in headers if h["subId"] == current_sub_id and h["pathKey"].startswith(f"{current_parent_id}/")]
    new_last = increment_trailing_number(siblings[-1]["pathKey"].split("/")[-1]) if len(siblings) > 0 else "1"
    return {"subId": current_sub_id, "newPathKey": f"{current_parent_id}/{new_last}"}


_DIGITS_RE = re.compile(r"[0-9]+\Z")


def renumber_duplicate_node_ids(doc_text: str) -> dict:
    lines = doc_text.split("\n")
    headers = []
    for line_index, line in enumerate(lines):
        m = GROUP_HEADER_RE.match(line)
        if m:
            headers.append({"lineIndex": line_index, "subId": m.group(1), "path": m.group(2).split("/"),
                            "originalPath": m.group(2)})
    if len(headers) == 0:
        return {"text": doc_text, "renamed": []}

    all_ids_by_parent: dict = {}

    def parent_key_at(path, depth):
        return "/".join(path[:depth])

    for h in headers:
        for d in range(len(h["path"])):
            key = parent_key_at(h["path"], d)
            all_ids_by_parent.setdefault(key, set()).add(h["path"][d])

    seen_by_parent: dict = {}
    current_ancestor_path: list = []
    renamed = []

    for h in headers:
        depth = len(h["path"]) - 1
        new_path_segs = list(h["path"])
        for d in range(depth):
            if d < len(current_ancestor_path) and current_ancestor_path[d] is not None:
                new_path_segs[d] = current_ancestor_path[d]
        parent_key = "/".join(new_path_segs[:depth])
        id_ = new_path_segs[depth]

        seen_set = seen_by_parent.setdefault(parent_key, set())

        if id_ in seen_set:
            if _DIGITS_RE.match(id_):
                used_set = all_ids_by_parent.get(parent_key)
                if used_set is None:
                    used_set = set()
                n = 1
                while str(n) in used_set or str(n) in seen_set:
                    n += 1
                new_id = str(n)
                used_set.add(new_id)
                seen_set.add(new_id)
                new_path_segs[depth] = new_id
                renamed.append({"subId": h["subId"], "oldPath": h["originalPath"], "newPath": "/".join(new_path_segs)})
                id_ = new_id
        else:
            seen_set.add(id_)

        # currentAncestorPath[depth] = id; length = depth + 1
        while len(current_ancestor_path) <= depth:
            current_ancestor_path.append(None)
        current_ancestor_path[depth] = id_
        del current_ancestor_path[depth + 1:]
        h["newPath"] = "/".join(new_path_segs)

    new_lines = list(lines)
    for h in headers:
        if h["newPath"] != h["originalPath"]:
            new_lines[h["lineIndex"]] = new_lines[h["lineIndex"]].replace(
                f"NODE:{h['originalPath']}", f"NODE:{h['newPath']}", 1)

    return {"text": "\n".join(new_lines), "renamed": renamed}


# ============================================================
# coerce (トークン列 → 値)
# ============================================================

def _split_by_comma(tokens):
    groups = []
    current = []
    depth = 0
    for t in tokens:
        if t["type"] in ("LPAREN", "LBRACKET", "LBRACE"):
            depth += 1
        if t["type"] in ("RPAREN", "RBRACKET", "RBRACE"):
            depth -= 1
        if t["type"] == "COMMA" and depth == 0:
            groups.append(current)
            current = []
        else:
            current.append(t)
    if len(current) > 0 or len(groups) > 0:
        groups.append(current)
    return [g for g in groups if len(g) > 0]


def _parse_object_literal_tokens(value_tokens, sub_fields, line_text, class_data_schemas):
    if len(value_tokens) == 0 or value_tokens[0]["type"] != "LBRACE":
        return {"value": None, "error": "{ フィールド名: 値, ... } の形式で指定してください（例: { x: 0, y: 0 }）"}
    if value_tokens[-1]["type"] != "RBRACE":
        return {"value": None, "error": "{ が閉じられていません"}
    inner = value_tokens[1:-1]
    groups = _split_by_comma(inner)
    sub_field_by_name = {f.get("name"): f for f in sub_fields}
    result = {}
    for g in groups:
        if len(g) == 0:
            continue
        if g[0]["type"] != "IDENT" or len(g) < 2 or g[1]["type"] != "COLON":
            return {"value": None, "error": "{ フィールド名: 値 } の形式で指定してください（例: { x: 0, y: 0 }）"}
        sub_name = g[0]["value"]
        sub_field = sub_field_by_name.get(sub_name)
        if not sub_field:
            return {"value": None, "error": f"存在しないフィールドです: {sub_name}"}
        sub_value_tokens = g[2:]
        r = coerce_value_tokens(sub_value_tokens, sub_field.get("type"), sub_field.get("options"), line_text,
                                sub_field.get("subFields"), class_data_schemas)
        if r.get("error"):
            return {"value": None, "error": f"{sub_name}: {r['error']}"}
        result[sub_name] = r["value"]
    return {"value": result, "error": None}


def coerce_value_tokens(value_tokens, field_type, field_options, line_text, sub_fields, class_data_schemas) -> dict:
    """トークン列を型に応じた実値へ。失敗時は {"value": None, "error": str}。
    候補外の enum 値だけは {"value": raw, "error": str, "warningOnly": True}。"""
    base_type = _base_type(field_type)
    is_array_type = _is_array_type(field_type)
    effective = get_effective_sub_fields(field_type, sub_fields, class_data_schemas)
    base_lower = _normalize_builtin_type(base_type)

    if is_array_type:
        if len(value_tokens) == 0 or value_tokens[0]["type"] != "LBRACKET":
            return {"value": None, "error": "配列は [値, 値, ...] の形式で指定してください"}
        inner = value_tokens[1:-1]
        items = _split_by_comma(inner)
        result = []
        for item_tokens in items:
            r = coerce_value_tokens(item_tokens, base_type, field_options, line_text, sub_fields, class_data_schemas)
            if r.get("error"):
                return {"value": None, "error": r["error"]}
            result.append(r["value"])
        return {"value": result, "error": None}

    if base_lower in VECTOR_SIZES:
        names = VECTOR_FIELD_NAMES[base_lower]
        vec_fields = [{"name": n, "type": "float"} for n in names]
        r = _parse_object_literal_tokens(value_tokens, vec_fields, line_text, class_data_schemas)
        if r.get("error"):
            return {"value": None, "error": r["error"]}
        obj = r["value"]
        missing = [n for n in names if n not in obj]
        if len(missing) > 0:
            ex = ", ".join(f"{n}: 0" for n in names)
            return {"value": None, "error": f"{', '.join(missing)} が指定されていません（例: {{ {ex} }}）"}
        return {"value": [obj[n] for n in names], "error": None}

    if _is_nonempty_list(effective):
        return _parse_object_literal_tokens(value_tokens, effective, line_text, class_data_schemas)

    if base_lower == "dictionary":
        if len(value_tokens) == 0:
            return {"value": None, "error": "値が指定されていません"}
        frm = value_tokens[0]["from"]
        to = value_tokens[-1]["to"]
        raw = line_text[frm:to] if isinstance(line_text, str) else "".join(t["value"] for t in value_tokens)
        try:
            return {"value": js_json_parse(raw), "error": None}
        except ValueError:
            return {"value": None, "error": 'dictionaryはJSON形式で指定してください（例: {"key":"value"}）'}

    if len(value_tokens) > 0 and value_tokens[0]["type"] == "LBRACE":
        frm = value_tokens[0]["from"]
        to = value_tokens[-1]["to"]
        raw = line_text[frm:to] if isinstance(line_text, str) else "".join(t["value"] for t in value_tokens)
        try:
            return {"value": js_json_parse(raw), "error": None}
        except ValueError:
            pass

    if len(value_tokens) != 1:
        if base_lower == "string":
            return {"value": None,
                    "error": '文字列は "" で囲んでください（例: text="Hello {name}"）。{ } , ( ) # = などの記号を含む文字列は、'
                             '必ず "" で囲む必要があります'}
        return {"value": None,
                "error": '値の形式が不正です（"" で囲んでいない文字列に、区切り記号として扱われる文字（{ } , ( ) # = など）が含まれていませんか？）'}
    tok = value_tokens[0]

    if base_lower in NUMERIC_TYPES:
        if tok["type"] != "NUMBER":
            if base_lower == "text_list_index":
                msg = "テキストのインデックス(整数)を指定してください（-1 = 未選択）"
            elif base_lower == "voice_ref":
                msg = "ボイスのインデックス(整数)を指定してください（-1 = 未選択）"
            else:
                msg = "整数を指定してください"
            return {"value": None, "error": msg}
        f = float(tok["value"])
        if math.isfinite(f):
            return {"value": int(math.trunc(f)), "error": None}
        return {"value": f, "error": None}
    if base_lower in FLOAT_TYPES:
        if tok["type"] != "NUMBER":
            return {"value": None, "error": "数値を指定してください"}
        return {"value": _num_value(float(tok["value"])), "error": None}
    if base_lower == "bool":
        if tok["type"] == "IDENT" and tok["value"] in ("true", "false"):
            return {"value": tok["value"] == "true", "error": None}
        return {"value": None, "error": "true または false を指定してください"}
    if base_lower == "char":
        raw = _strip_quotes(tok["value"]) if tok["type"] == "STRING" else tok["value"]
        if len(raw) != 1:
            return {"value": None, "error": "1文字だけ指定してください"}
        return {"value": raw, "error": None}

    if base_lower == "string" and tok["type"] != "STRING":
        return {"value": None, "error": '文字列は "" で囲んでください（例: text="Hello {name}"）'}
    raw = _strip_quotes(tok["value"]) if tok["type"] == "STRING" else tok["value"]
    if _is_nonempty_list(field_options):
        if raw in field_options:
            return {"value": raw, "error": None}
        qualified = f"{js_string(field_type)}.{raw}"
        if qualified in field_options:
            return {"value": qualified, "error": None}
        more = "..." if len(field_options) > 5 else ""
        return {"value": raw,
                "error": f"候補にありません: {raw}（候補: {', '.join(js_string(o) for o in field_options[:5])}{more}）",
                "warningOnly": True}
    return {"value": raw, "error": None}


# ============================================================
# serialize (値 → DSL ソース)
# ============================================================

_RESERVED_RE = re.compile(rf'[{_WS}"#=()\[\]{{}},:]')


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def serialize_value(value, field_type, sub_fields, class_data_schemas) -> str:
    base_type = _base_type(field_type)
    is_array_type = _is_array_type(field_type)
    effective = get_effective_sub_fields(field_type, sub_fields, class_data_schemas)
    base_lower = _normalize_builtin_type(base_type)

    if base_lower in VECTOR_SIZES and not is_array_type:
        names = VECTOR_FIELD_NAMES[base_lower]
        if isinstance(value, list):
            arr = value
        elif isinstance(value, dict):
            arr = [value[n] if value.get(n) is not None else 0 for n in names]
        else:
            arr = []
        parts = []
        for idx, n in enumerate(names):
            v = arr[idx] if idx < len(arr) else None
            parts.append(f"{n}: {js_string(0 if v is None else v)}")
        return "{ " + ", ".join(parts) + " }"

    if _is_nonempty_list(effective):
        if is_array_type:
            arr = value if isinstance(value, list) else []
            return "[" + ", ".join(serialize_value(v, base_type, effective, class_data_schemas) for v in arr) + "]"
        parts = [f"{f.get('name')}: {serialize_value(_get(value, f.get('name')), f.get('type'), f.get('subFields'), class_data_schemas)}"
                 for f in effective]
        return "{ " + ", ".join(parts) + " }"

    if is_array_type:
        arr = value if isinstance(value, list) else []
        return "[" + ", ".join(serialize_value(v, base_type, None, class_data_schemas) for v in arr) + "]"
    if base_lower in NUMERIC_TYPES or base_lower in FLOAT_TYPES:
        dflt = -1 if base_lower in INDEX_REF_TYPES else 0
        return js_string(dflt if value is None else value)
    if base_lower == "bool":
        return "true" if js_truthy(value) else "false"
    if base_lower == "dictionary":
        return js_json_stringify({} if value is None else value)
    if isinstance(value, (dict, list)):
        return js_json_stringify(value)
    s = "" if value is None else js_string(value)
    if base_lower == "string":
        return _quote(s)
    if s == "" or _RESERVED_RE.search(s):
        return _quote(s)
    return s


# ============================================================
# コンパイル / デコンパイル
# ============================================================

def _rand_base36(n=5) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    return "".join(random.choice(chars) for _ in range(n))


def compile_document(text: str, role_schemas: dict, existing_roles=None, class_data_schemas=None) -> dict:
    """DSL テキスト → {"roles": [...], "diagnostics": [DslIssue, ...]}"""
    existing_roles = existing_roles if existing_roles is not None else []
    class_data_schemas = class_data_schemas if class_data_schemas is not None else {}
    parsed_lines = parse_document(text)
    diagnostics = []
    roles = []

    existing_by_name: dict = {}
    for r in existing_roles:
        existing_by_name.setdefault(r.get("name"), []).append(r)
    used_count: dict = {}

    for node in parsed_lines:
        if node["type"] != "call":
            diagnostics.extend(node["errors"])
            continue
        diagnostics.extend(node["errors"])
        if not node.get("name"):
            continue

        role_name = node["name"]["value"]
        schema = role_schemas.get(role_name)
        if schema is None:
            diagnostics.append(DslIssue(f"未知のRoleです: {role_name}", node["name"]["from"], node["name"]["to"], node["line"]))
            continue

        fields = schema.get("fields") or []
        field_by_name = {f.get("name"): f for f in fields}
        seen_fields = set()
        data = []

        for arg in node["args"]:
            field_name = arg["key"]["value"]
            field = field_by_name.get(field_name)
            if not field:
                diagnostics.append(DslIssue(f"Role「{role_name}」に存在しないフィールドです: {field_name}",
                                            arg["key"]["from"], arg["key"]["to"], node["line"]))
                continue
            if field_name in seen_fields:
                diagnostics.append(DslIssue(f"フィールド {field_name} が重複しています", arg["key"]["from"], arg["key"]["to"],
                                            node["line"], "warning"))
            seen_fields.add(field_name)

            r = coerce_value_tokens(arg["valueTokens"], field.get("type"), field.get("options"), node["raw"],
                                    field.get("subFields"), class_data_schemas)
            value, error, warning_only = r.get("value"), r.get("error"), r.get("warningOnly")
            if error:
                diagnostics.append(DslIssue(error, arg["from"], arg["to"], node["line"], "warning" if warning_only else "error"))
            data.append({"name": field_name, "type": field.get("type"), "value": value})

        if len(node["args"]) > 0:
            for field in fields:
                if field.get("required") is False:
                    continue
                if field.get("name") in seen_fields:
                    continue
                diagnostics.append(DslIssue(f"Role「{role_name}」の必須フィールドが指定されていません: {field.get('name')}",
                                            node["name"]["from"], node["name"]["to"], node["line"], "error"))

        idx = used_count.get(role_name, 0)
        used_count[role_name] = idx + 1
        candidates = existing_by_name.get(role_name, [])
        existing = candidates[idx] if idx < len(candidates) else None
        uid = existing.get("uniqueId") if existing else None
        if not js_truthy(uid):
            uid = f"{role_name}_{int(time.time() * 1000)}_{len(roles)}_{_rand_base36()}"

        base_role = dict(existing) if existing else {"id": schema.get("id"), "branchType": schema.get("branchType")}
        roles.append({**base_role, "uniqueId": uid, "name": role_name, "data": data})

    return {"roles": roles, "diagnostics": diagnostics}


def decompile_roles(roles, role_schemas: dict, class_data_schemas=None) -> str:
    class_data_schemas = class_data_schemas if class_data_schemas is not None else {}
    lines = []
    for role in roles or []:
        schema = role_schemas.get(role.get("name"))
        parts = [role.get("name")]
        field_defs = (schema.get("fields") if isinstance(schema, dict) else None)
        for field in role.get("data") or []:
            field_def = None
            if isinstance(field_defs, list):
                field_def = next((f for f in field_defs if f.get("name") == field.get("name")), None)
            typ = (field_def.get("type") if field_def else None) or field.get("type") or "string"
            parts.append(f"{field.get('name')}={serialize_value(field.get('value'), typ, field_def.get('subFields') if field_def else None, class_data_schemas)}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


# ============================================================
# サブグループ設定行 ('#@ field=value ...')
# ============================================================

SETTING_PSEUDO_ROLE = "@@"
SETTING_LINE_RE = re.compile(rf"^#@(?:{_S}|\Z)")
SUBGROUP_SETTING_LINE_PREFIX = "#@"


def is_sub_group_setting_line(line) -> bool:
    return bool(SETTING_LINE_RE.match(line or ""))


def _optional_setting_schema(setting_schema) -> dict:
    fields = []
    for f in ((setting_schema or {}).get("fields") or []):
        fields.append({**f, "required": False})
    return {**(setting_schema or {}), "fields": fields}


def _relabel_setting_diagnostic(issue):
    if issue is not None and isinstance(issue.message, str) and SETTING_PSEUDO_ROLE in issue.message:
        issue.message = (issue.message
                         .replace(f"Role「{SETTING_PSEUDO_ROLE}」", "サブグループ設定", 1)
                         .replace(f"未知のRoleです: {SETTING_PSEUDO_ROLE}", "サブグループ設定を読み取れません", 1))
    return issue


def lint_document(text: str, role_schemas: dict, class_data_schemas=None, setting_schema=None) -> list:
    class_data_schemas = class_data_schemas if class_data_schemas is not None else {}
    if setting_schema is not None:
        lines = [SETTING_PSEUDO_ROLE + ln[2:] if SETTING_LINE_RE.match(ln) else ln for ln in text.split("\n")]
        res = compile_document("\n".join(lines),
                               {**role_schemas, SETTING_PSEUDO_ROLE: _optional_setting_schema(setting_schema)},
                               [], class_data_schemas)
        return [_relabel_setting_diagnostic(d) for d in res["diagnostics"]]
    return compile_document(text, role_schemas, [], class_data_schemas)["diagnostics"]


def extract_sub_group_setting_lines(body_lines) -> list:
    return [ln[2:].strip(_WS_STRIP) for ln in (body_lines or []) if SETTING_LINE_RE.match(ln)]


# String.prototype.trim が除く空白 (= JS の \s と同じ集合)
_WS_STRIP = "\t\n\v\f\r                  　﻿"


def compile_sub_group_setting(line_text: str, setting_schema, class_data_schemas=None) -> dict:
    class_data_schemas = class_data_schemas if class_data_schemas is not None else {}
    res = compile_document(f"{SETTING_PSEUDO_ROLE} {line_text}",
                           {SETTING_PSEUDO_ROLE: _optional_setting_schema(setting_schema)}, [], class_data_schemas)
    return {"data": res["roles"][0]["data"] if len(res["roles"]) > 0 else [],
            "diagnostics": [_relabel_setting_diagnostic(d) for d in res["diagnostics"]]}


def normalize_sub_group_setting(current, setting_schema, defaults_data):
    cur = current if isinstance(current, list) else []
    if not isinstance(setting_schema, dict) or not _is_nonempty_list(setting_schema.get("fields")):
        return cur
    out = []
    for f in setting_schema["fields"]:
        found = next((d for d in cur if d and d.get("name") == f.get("name")), None)
        if found and found.get("value") is not None:
            out.append({"name": f.get("name"), "type": f.get("type"), "value": found["value"]})
            continue
        dflt = next((d for d in (defaults_data or []) if d and d.get("name") == f.get("name")), None)
        out.append({"name": f.get("name"), "type": f.get("type"), "value": dflt.get("value") if dflt else None})
    return out


def decompile_sub_group_setting(data, setting_schema, class_data_schemas=None) -> str:
    class_data_schemas = class_data_schemas if class_data_schemas is not None else {}
    if not isinstance(data, list) or len(data) == 0 or setting_schema is None:
        return ""
    text = decompile_roles([{"name": SETTING_PSEUDO_ROLE, "data": data}], {SETTING_PSEUDO_ROLE: setting_schema},
                           class_data_schemas)
    return SUBGROUP_SETTING_LINE_PREFIX + text[len(SETTING_PSEUDO_ROLE):]


# ============================================================
# 補完候補
# ============================================================

def _field_items(sub_fields, pred=None, prefix=None):
    out = []
    for f in sub_fields:
        out.append(f)
    return out


def _entries_of(inner, region_end):
    entries = []
    current = []
    entry_start = None
    brace_depth = 0
    for tok in inner:
        if entry_start is None:
            entry_start = tok["from"]
        if tok["type"] in ("LPAREN", "LBRACKET", "LBRACE"):
            brace_depth += 1
        if tok["type"] in ("RPAREN", "RBRACKET", "RBRACE"):
            brace_depth -= 1
        if tok["type"] == "COMMA" and brace_depth == 0:
            entries.append({"tokens": current, "start": entry_start, "end": tok["from"]})
            current = []
            entry_start = None
        else:
            current.append(tok)
    if len(current) > 0:
        entries.append({"tokens": current, "start": entry_start, "end": region_end})
    return entries


def _complete_object_literal(line, value_tokens, cursor_ch, sub_fields, region_end, class_data_schemas):
    if len(value_tokens) == 0 or value_tokens[0]["type"] != "LBRACE":
        return []

    depth = 0
    close_idx = -1
    for k, tk in enumerate(value_tokens):
        if tk["type"] == "LBRACE":
            depth += 1
        if tk["type"] == "RBRACE":
            depth -= 1
            if depth == 0:
                close_idx = k
                break
    effective_end = value_tokens[close_idx]["from"] if close_idx >= 0 else region_end
    inner = value_tokens[1:(close_idx if close_idx >= 0 else len(value_tokens))]

    entries = _entries_of(inner, effective_end)
    used_names = {e["tokens"][0]["value"] for e in entries if e["tokens"] and e["tokens"][0]["value"]}

    cursor_entry = next((e for e in entries if e["start"] is not None and cursor_ch >= e["start"] and cursor_ch <= e["end"]), None)

    def all_unused():
        return [{"label": f"{f.get('name')}: ", "type": "field", "detail": f.get("type")}
                for f in sub_fields if f.get("name") not in used_names]

    if not cursor_entry:
        return all_unused()

    cursor_group = cursor_entry["tokens"]
    key_tok = cursor_group[0] if cursor_group else None
    if not key_tok:
        return all_unused()
    colon_tok = cursor_group[1] if len(cursor_group) > 1 else None
    if (key_tok["type"] != "IDENT" or not colon_tok or colon_tok["type"] != "COLON" or cursor_ch <= key_tok["to"]
            or (cursor_ch > key_tok["to"] and cursor_ch <= colon_tok["from"])):
        prefix = line[key_tok["from"]:cursor_ch] if cursor_ch > key_tok["from"] else ""
        pl = prefix.lower()
        return [{"label": f"{f.get('name')}: ", "type": "field", "detail": f.get("type")}
                for f in sub_fields
                if (f.get("name") == key_tok["value"] or f.get("name") not in used_names)
                and f.get("name").lower().startswith(pl)]

    sub_field = next((f for f in sub_fields if f.get("name") == key_tok["value"]), None)
    if not sub_field:
        return []
    sub_value_tokens = cursor_group[2:]

    nested = get_effective_sub_fields(sub_field.get("type"), sub_field.get("subFields"), class_data_schemas)
    if _is_nonempty_list(nested):
        if (sub_field.get("type") or "").endswith("[]"):
            return _complete_array_of_object_literal(line, sub_value_tokens, cursor_ch, nested, cursor_entry["end"], class_data_schemas)
        return _complete_object_literal(line, sub_value_tokens, cursor_ch, nested, cursor_entry["end"], class_data_schemas)
    return _complete_scalar_value(line, sub_value_tokens, cursor_ch, sub_field)


def _complete_array_of_object_literal(line, value_tokens, cursor_ch, sub_fields, region_end, class_data_schemas):
    if len(value_tokens) == 0 or value_tokens[0]["type"] != "LBRACKET":
        return []
    depth = 0
    close_idx = -1
    for k, tk in enumerate(value_tokens):
        if tk["type"] == "LBRACKET":
            depth += 1
        if tk["type"] == "RBRACKET":
            depth -= 1
            if depth == 0:
                close_idx = k
                break
    effective_end = value_tokens[close_idx]["from"] if close_idx >= 0 else region_end
    inner = value_tokens[1:(close_idx if close_idx >= 0 else len(value_tokens))]
    entries = _entries_of(inner, effective_end)
    cursor_entry = next((e for e in entries if e["start"] is not None and cursor_ch >= e["start"] and cursor_ch <= e["end"]), None)
    if not cursor_entry:
        return []
    return _complete_object_literal(line, cursor_entry["tokens"], cursor_ch, sub_fields, cursor_entry["end"], class_data_schemas)


def _bare_of(o: str) -> str:
    return o[o.index(".") + 1:] if "." in o else o


def _complete_scalar_value(line, value_tokens, cursor_ch, field):
    last_tok = value_tokens[-1] if value_tokens else None
    typed_prefix = line[last_tok["from"]:cursor_ch] if last_tok and cursor_ch > last_tok["from"] else ""
    options = field.get("options")
    if _is_nonempty_list(options):
        def to_item(o):
            return {"label": _bare_of(o), "insertText": o, "type": "value"}

        prefix_lower = typed_prefix.lower()
        if not prefix_lower:
            return [to_item(o) for o in options]

        last_dot = prefix_lower.rfind(".")
        has_qualifier = last_dot >= 0
        after_dot = prefix_lower[last_dot + 1:] if has_qualifier else prefix_lower
        full_prefix = prefix_lower

        if has_qualifier and after_dot == "":
            return [to_item(o) for o in options]

        starts_with, contains = [], []
        for o in options:
            bare_lower = _bare_of(o).lower()
            full_lower = o.lower()
            starts = bare_lower.startswith(after_dot) or (has_qualifier and full_lower.startswith(full_prefix))
            if starts:
                starts_with.append(o)
                continue
            if after_dot in bare_lower:
                contains.append(o)
        return [to_item(o) for o in starts_with + contains]
    if field.get("type") == "bool":
        return [{"label": o, "type": "value"} for o in ("true", "false") if o.startswith(typed_prefix)]
    return []


def _build_role_insert_text(role_name, schema, class_data_schemas):
    if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
        return role_name
    parts = []
    for field in schema["fields"]:
        if field.get("default") is None:
            continue
        sub_fields = get_effective_sub_fields(field.get("type"), field.get("subFields"), class_data_schemas)
        parts.append(f"{field.get('name')}={serialize_value(field['default'], field.get('type'), sub_fields, class_data_schemas)}")
    if len(parts) == 0:
        return role_name
    return f"{role_name} {' '.join(parts)}"


def get_completions_at(text, cursor_line, cursor_ch, role_names, role_schemas, class_data_schemas=None, setting_schema=None):
    class_data_schemas = class_data_schemas if class_data_schemas is not None else {}
    lines = text.split("\n")

    def line_at(i):
        return lines[i] if 0 <= i < len(lines) else ""

    if setting_schema is not None and cursor_ch >= 3 and SETTING_LINE_RE.match(line_at(cursor_line)):
        lines[cursor_line] = SETTING_PSEUDO_ROLE + lines[cursor_line][2:]
        role_schemas = {**role_schemas, SETTING_PSEUDO_ROLE: _optional_setting_schema(setting_schema)}
    line = line_at(cursor_line)
    tokens = [t for t in tokenize_line(line) if t["type"] != "COMMENT"]

    def role_item(n):
        return {"label": n, "type": "role", "insertText": _build_role_insert_text(n, role_schemas.get(n), class_data_schemas)}

    if len(tokens) == 0:
        return [role_item(n) for n in role_names]

    first = tokens[0]
    if cursor_ch <= first["to"]:
        if first["type"] != "IDENT":
            return []
        prefix = line[first["from"]:cursor_ch]
        return [role_item(n) for n in role_names if n.lower().startswith(prefix.lower())]

    role_name = first["value"]
    schema = role_schemas.get(role_name)
    if schema is None:
        return []
    schema_fields = schema.get("fields") or []

    for i in range(1, len(tokens)):
        t = tokens[i]
        if t["type"] != "EQUALS":
            continue
        field_name = tokens[i - 1]["value"] if i - 1 >= 0 else None
        field = next((f for f in schema_fields if f.get("name") == field_name), None)
        if not field:
            continue

        res = _collect_value_tokens(tokens, i + 1)
        value_tokens, span_error = res["valueTokens"], res["error"]
        is_unclosed = bool(span_error) and "閉じられていません" in span_error
        region_start = t["to"]
        region_end = len(line) if is_unclosed else (value_tokens[-1]["to"] if len(value_tokens) > 0 else region_start)
        if cursor_ch < region_start or cursor_ch > region_end:
            continue

        field_sub_fields = get_effective_sub_fields(field.get("type"), field.get("subFields"), class_data_schemas)
        if _is_nonempty_list(field_sub_fields):
            if (field.get("type") or "").endswith("[]"):
                return _complete_array_of_object_literal(line, value_tokens, cursor_ch, field_sub_fields, region_end, class_data_schemas)
            return _complete_object_literal(line, value_tokens, cursor_ch, field_sub_fields, region_end, class_data_schemas)

        return _complete_scalar_value(line, value_tokens, cursor_ch, field)

    used_fields = set()
    for i in range(1, len(tokens)):
        if tokens[i]["type"] == "IDENT" and i + 1 < len(tokens) and tokens[i + 1]["type"] == "EQUALS":
            used_fields.add(tokens[i]["value"])
    current_token = next((t for t in tokens if t is not first and t["type"] == "IDENT"
                          and cursor_ch >= t["from"] and cursor_ch <= t["to"]), None)
    prefix = line[current_token["from"]:cursor_ch] if current_token else ""
    pl = prefix.lower()
    cur_val = current_token["value"] if current_token else None
    return [{"label": f"{f.get('name')}=", "type": "field", "detail": f.get("type")}
            for f in schema_fields
            if (f.get("name") not in used_fields or f.get("name") == cur_val)
            and f.get("name").lower().startswith(pl)]
