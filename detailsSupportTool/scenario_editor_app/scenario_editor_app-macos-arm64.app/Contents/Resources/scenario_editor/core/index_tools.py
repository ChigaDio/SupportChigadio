"""text_list_index / voice_ref など「Matrixの何番目か」を指す整数フィールドの一括調整 (Qt 非依存)。

`js_ref/src/scenarioIndexTools.js` の移植。

対応表 (JS -> Python):
    INDEX_TYPES / INT_TYPES          -> INDEX_TYPES / INT_TYPES
    collectIndexFields               -> collect_index_fields
    planIndexAdjust                  -> plan_index_adjust
    applyIndexChanges                -> apply_index_changes
    splitSections                    -> split_sections
    findSiblingSections              -> find_sibling_sections
    planIndexAdjustInDsl             -> plan_index_adjust_in_dsl
    applyIndexChangesToDsl           -> apply_index_changes_to_dsl
    collectIndexFieldsInDsl          -> collect_index_fields_in_dsl

オプションは JS と同じキー名(camelCase)の dict で渡す(startNodeId, includeStart ...)。
"""
from __future__ import annotations

import re

from .dsl import tokenize_line

INDEX_TYPES = {"text_list_index", "voice_ref"}
INT_TYPES = {"int", "uint", "short", "long", "byte"}


def _type_of_field(role_schemas, role_name, field_name):
    schema = (role_schemas or {}).get(role_name)
    fields = schema.get("fields") if isinstance(schema, dict) else None
    if isinstance(fields, list):
        for f in fields:
            if f and f.get("name") == field_name:
                t = f.get("type")
                return str(t).lower() if t else None
    return None


def _is_target_type(t, include_int):
    return bool(t) and (t in INDEX_TYPES or (bool(include_int) and t in INT_TYPES))


def _key_of(role_name, field_name):
    return f"{role_name}.{field_name}"


def _matches_target(target, role_name, field_name):
    return (not target) or target == "all" or (
        target.get("roleName") == role_name and target.get("fieldName") == field_name)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_integer(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and v == v and v not in (float("inf"), float("-inf")) and v == int(v)


def _to_number(v):
    """JS の Number(v) 相当 (数値/数字文字列のみ想定)。変換できなければ nan。"""
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    if s == "":
        return 0
    try:
        f = float(s)
    except ValueError:
        return float("nan")
    return int(f) if f == int(f) and abs(f) < 2 ** 53 else f


def _sort_fields(items):
    return sorted(items, key=lambda f: (f["roleName"], f["fieldName"]))


# ---------------------------------------------------------------- GUI (ノード配列)
def collect_index_fields(nodes, role_schemas, opts=None):
    include_int = bool((opts or {}).get("includeInt", False))
    found = {}
    for node in nodes or []:
        for role in ((node.get("data") or {}).get("roles") or []):
            for entry in role.get("data") or []:
                if not entry:
                    continue
                t = _type_of_field(role_schemas, role.get("name"), entry.get("name"))
                if not _is_target_type(t, include_int):
                    continue
                k = _key_of(role.get("name"), entry.get("name"))
                cur = found.get(k) or {"roleName": role.get("name"), "fieldName": entry.get("name"), "type": t, "count": 0}
                v = entry.get("value")
                cur["count"] += (len([x for x in v if _is_num(x)]) if isinstance(v, list) else (1 if _is_num(v) else 0))
                found[k] = cur
    return _sort_fields([f for f in found.values() if f["count"] > 0])


def _list_occurrences(nodes, role_schemas, target, include_int):
    occ = []
    for node_index, node in enumerate(nodes or []):
        for role in ((node.get("data") or {}).get("roles") or []):
            for entry_index, entry in enumerate(role.get("data") or []):
                if not entry or not _matches_target(target, role.get("name"), entry.get("name")):
                    continue
                if not _is_target_type(_type_of_field(role_schemas, role.get("name"), entry.get("name")), include_int):
                    continue
                base = {"nodeId": str(node.get("id")), "nodeIndex": node_index, "roleUniqueId": role.get("uniqueId"),
                        "roleName": role.get("name"), "fieldName": entry.get("name"), "entryIndex": entry_index}
                v = entry.get("value")
                if _is_num(v):
                    occ.append({**base, "arrayIndex": None, "value": v})
                elif isinstance(v, list):
                    for ai, x in enumerate(v):
                        if _is_num(x):
                            occ.append({**base, "arrayIndex": ai, "value": x})
    return occ


def _has_base(opts):
    b = opts.get("base") if opts else None
    return b is not None and b != ""


def _sequence_start(items, start_idx, idx_key, include_start, skip_negative, opts, step, warnings, k):
    """連番の最初の値(next)を返す。決められなければ None (warnings 追記済み)。"""
    start_items = [o for o in items if o[idx_key] == start_idx and not (skip_negative and o["value"] < 0)]
    if _has_base(opts):
        first = _to_number(opts["base"])
        nxt = first if include_start else first + _to_number(step)
    elif start_items:
        first = (start_items[0] if include_start else start_items[-1])["value"]
        nxt = first if include_start else first + _to_number(step)
    else:
        warnings.append(f"{k}: 起点のサブグループに値が無いため、開始値を決められません(開始値を指定してください)")
        return None
    if not _is_integer(nxt):
        warnings.append(f"{k}: 開始値が整数ではありません")
        return None
    return nxt


def plan_index_adjust(nodes, role_schemas, opts=None):
    opts = opts or {}
    start_node_id = opts.get("startNodeId")
    end_node_id = opts.get("endNodeId")
    mode = opts.get("mode", "shift")
    delta = opts.get("delta", 0)
    step = opts.get("step", 1)
    target = opts.get("target")
    include_int = opts.get("includeInt", False)
    skip_negative = opts.get("skipNegative", True)
    include_start = opts["includeStart"] if opts.get("includeStart") is not None else mode == "shift"
    warnings = []
    lst = nodes or []
    start_idx = next((i for i, n in enumerate(lst) if str(n.get("id")) == str(start_node_id)), -1)
    if start_idx < 0:
        return {"changes": [], "warnings": warnings, "error": "起点のサブグループが見つかりません"}
    end_idx = len(lst) - 1
    if end_node_id is not None and end_node_id != "":
        e = next((i for i, n in enumerate(lst) if str(n.get("id")) == str(end_node_id)), -1)
        if e < 0:
            return {"changes": [], "warnings": warnings, "error": "終点のサブグループが見つかりません"}
        end_idx = e
    if end_idx < start_idx:
        return {"changes": [], "warnings": warnings, "error": "終点が起点より前にあります"}
    if not _is_integer(_to_number(delta)) or not _is_integer(_to_number(step)):
        return {"changes": [], "warnings": warnings, "error": "増減量・増分は整数で指定してください"}

    occ = _list_occurrences(lst, role_schemas, target, include_int)
    changes = []

    def push(o, to):
        if to == o["value"]:
            return
        if to < 0:
            warnings.append(f"ノード{o['nodeId']} {o['roleName']}.{o['fieldName']}: {_js_num(o['value'])} → {_js_num(to)} は負の値になるため変更しません")
            return
        changes.append({"nodeId": o["nodeId"], "roleUniqueId": o["roleUniqueId"], "roleName": o["roleName"],
                        "fieldName": o["fieldName"], "entryIndex": o["entryIndex"], "arrayIndex": o["arrayIndex"],
                        "from": o["value"], "to": to})

    if mode == "shift":
        for o in occ:
            if o["nodeIndex"] < start_idx or o["nodeIndex"] > end_idx:
                continue
            if o["nodeIndex"] == start_idx and not include_start:
                continue
            if skip_negative and o["value"] < 0:
                continue
            push(o, o["value"] + _to_number(delta))
        return {"changes": changes, "warnings": warnings}

    by_key = {}
    for o in occ:
        by_key.setdefault(_key_of(o["roleName"], o["fieldName"]), []).append(o)
    for k, items in by_key.items():
        nxt = _sequence_start(items, start_idx, "nodeIndex", include_start, skip_negative, opts, step, warnings, k)
        if nxt is None:
            continue
        for o in items:
            if o["nodeIndex"] < start_idx or o["nodeIndex"] > end_idx:
                continue
            if o["nodeIndex"] == start_idx and not include_start:
                continue
            if skip_negative and o["value"] < 0:
                continue
            push(o, nxt)
            nxt += _to_number(step)
    return {"changes": changes, "warnings": warnings}


def _js_num(x):
    if isinstance(x, float) and x == int(x) and abs(x) < 1e21:
        return str(int(x))
    return str(x)


def apply_index_changes(nodes, changes):
    by_node = {}
    for c in changes or []:
        by_node.setdefault(c["nodeId"], []).append(c)
    out = []
    for node in nodes or []:
        lst = by_node.get(str(node.get("id")))
        if not lst:
            out.append(node)
            continue
        roles = []
        for role in ((node.get("data") or {}).get("roles") or []):
            mine = [c for c in lst if str(c.get("roleUniqueId")) == str(role.get("uniqueId"))]
            if not mine:
                roles.append(role)
                continue
            data = []
            for ei, entry in enumerate(role.get("data") or []):
                cs = [c for c in mine if c.get("entryIndex") == ei]
                if not cs:
                    data.append(entry)
                elif isinstance(entry.get("value"), list):
                    arr = list(entry["value"])
                    for c in cs:
                        ai = c["arrayIndex"]
                        while len(arr) <= ai:
                            arr.append(None)
                        arr[ai] = c["to"]
                    data.append({**entry, "value": arr})
                else:
                    data.append({**entry, "value": cs[0]["to"]})
            roles.append({**role, "data": data})
        out.append({**node, "data": {**(node.get("data") or {}), "roles": roles}})
    return out


# ---------------------------------------------------------------- DSL (テキスト)
_HEADER_RE = re.compile(r"^#\s*====\s*SUB:(\S+)\s+NODE:(\S+).*?====\s*$")


def split_sections(text):
    lines = str(text).split("\n")
    heads = []
    for i, line in enumerate(lines):
        m = _HEADER_RE.match(line)
        if m:
            heads.append({"subId": m.group(1), "pathKey": m.group(2), "headerLine": i})
    out = []
    for idx, h in enumerate(heads):
        pk = h["pathKey"]
        out.append({**h, "parentKey": pk[:pk.rindex("/")] if "/" in pk else "",
                    "bodyStart": h["headerLine"] + 1,
                    "bodyEnd": heads[idx + 1]["headerLine"] if idx + 1 < len(heads) else len(lines)})
    return out


def find_sibling_sections(text, cursor_line):
    sections = split_sections(text)
    cur = None
    for s in reversed(sections):
        if s["headerLine"] <= cursor_line:
            cur = s
            break
    if cur is None:
        return {"current": None, "siblings": [], "sections": sections}
    siblings = [s for s in sections if s["subId"] == cur["subId"] and s["parentKey"] == cur["parentKey"]]
    return {"current": cur, "siblings": siblings, "sections": sections}


_INT_RE = re.compile(r"^-?[0-9]+\Z")


def _scan_line(line):
    tokens = tokenize_line(line)
    if not tokens or tokens[0]["type"] != "IDENT":
        return []
    role_name = tokens[0]["value"]
    out = []
    for i in range(1, len(tokens) - 2):
        k, eq, v = tokens[i], tokens[i + 1], tokens[i + 2]
        if k["type"] != "IDENT" or eq["type"] != "EQUALS":
            continue
        if v["type"] == "NUMBER" and _INT_RE.match(v["value"]):
            out.append({"fieldName": k["value"], "roleName": role_name, "from": v["from"], "to": v["to"],
                        "value": int(v["value"]), "listIndex": None})
        elif v["type"] == "LBRACKET":
            j = i + 3
            li = 0
            while j < len(tokens) and tokens[j]["type"] != "RBRACKET":
                if tokens[j]["type"] == "NUMBER" and _INT_RE.match(tokens[j]["value"]):
                    out.append({"fieldName": k["value"], "roleName": role_name, "from": tokens[j]["from"],
                                "to": tokens[j]["to"], "value": int(tokens[j]["value"]), "listIndex": li})
                    li += 1
                elif tokens[j]["type"] != "COMMA":
                    li += 1
                j += 1
    return out


def plan_index_adjust_in_dsl(text, role_schemas, opts=None):
    opts = opts or {}
    cursor_line = opts.get("cursorLine", 0)
    end_path_key = opts.get("endPathKey")
    mode = opts.get("mode", "shift")
    delta = opts.get("delta", 0)
    step = opts.get("step", 1)
    target = opts.get("target")
    include_int = opts.get("includeInt", False)
    skip_negative = opts.get("skipNegative", True)
    include_start = opts["includeStart"] if opts.get("includeStart") is not None else mode == "shift"
    warnings = []
    found = find_sibling_sections(text, cursor_line)
    current, siblings = found["current"], found["siblings"]
    if not current:
        return {"changes": [], "warnings": warnings, "error": "カーソルがサブグループ(見出し)の中にありません"}
    start_idx = next(i for i, s in enumerate(siblings) if s["headerLine"] == current["headerLine"])
    end_idx = len(siblings) - 1
    if end_path_key:
        e = next((i for i, s in enumerate(siblings) if s["pathKey"] == end_path_key), -1)
        if e < 0:
            return {"changes": [], "warnings": warnings, "error": "終点のサブグループが見つかりません"}
        end_idx = e
    if end_idx < start_idx:
        return {"changes": [], "warnings": warnings, "error": "終点が起点より前にあります"}
    if not _is_integer(_to_number(delta)) or not _is_integer(_to_number(step)):
        return {"changes": [], "warnings": warnings, "error": "増減量・増分は整数で指定してください"}

    lines = str(text).split("\n")
    occ = []
    for sec_index, sec in enumerate(siblings):
        for li in range(sec["bodyStart"], sec["bodyEnd"]):
            for o in _scan_line(lines[li]):
                if not _matches_target(target, o["roleName"], o["fieldName"]):
                    continue
                if not _is_target_type(_type_of_field(role_schemas, o["roleName"], o["fieldName"]), include_int):
                    continue
                occ.append({**o, "line": li, "secIndex": sec_index, "pathKey": sec["pathKey"]})

    changes = []

    def push(o, to):
        if to == o["value"]:
            return
        if to < 0:
            warnings.append(f"{o['pathKey']} {o['roleName']}.{o['fieldName']}: {o['value']} → {_js_num(to)} は負の値になるため変更しません")
            return
        changes.append({"line": o["line"], "from": o["from"], "to": o["to"], "fromValue": o["value"], "toValue": to,
                        "roleName": o["roleName"], "fieldName": o["fieldName"], "pathKey": o["pathKey"]})

    if mode == "shift":
        for o in occ:
            if o["secIndex"] < start_idx or o["secIndex"] > end_idx:
                continue
            if o["secIndex"] == start_idx and not include_start:
                continue
            if skip_negative and o["value"] < 0:
                continue
            push(o, o["value"] + _to_number(delta))
        return {"changes": changes, "warnings": warnings}

    by_key = {}
    for o in occ:
        by_key.setdefault(_key_of(o["roleName"], o["fieldName"]), []).append(o)
    for k, items in by_key.items():
        nxt = _sequence_start(items, start_idx, "secIndex", include_start, skip_negative, opts, step, warnings, k)
        if nxt is None:
            continue
        for o in items:
            if o["secIndex"] < start_idx or o["secIndex"] > end_idx:
                continue
            if o["secIndex"] == start_idx and not include_start:
                continue
            if skip_negative and o["value"] < 0:
                continue
            push(o, nxt)
            nxt += _to_number(step)
    return {"changes": changes, "warnings": warnings}


def apply_index_changes_to_dsl(text, changes):
    lines = str(text).split("\n")
    by_line = {}
    for c in changes or []:
        by_line.setdefault(c["line"], []).append(c)
    for li, lst in by_line.items():
        s = lines[li]
        for c in sorted(lst, key=lambda c: -c["from"]):
            s = f"{s[:c['from']]}{_js_num(c['toValue'])}{s[c['to']:]}"
        lines[li] = s
    return "\n".join(lines)


def collect_index_fields_in_dsl(text, role_schemas, opts=None):
    include_int = bool((opts or {}).get("includeInt", False))
    found = {}
    for line in str(text).split("\n"):
        for o in _scan_line(line):
            t = _type_of_field(role_schemas, o["roleName"], o["fieldName"])
            if not _is_target_type(t, include_int):
                continue
            k = _key_of(o["roleName"], o["fieldName"])
            cur = found.get(k) or {"roleName": o["roleName"], "fieldName": o["fieldName"], "type": t, "count": 0}
            cur["count"] += 1
            found[k] = cur
    return _sort_fields(found.values())
