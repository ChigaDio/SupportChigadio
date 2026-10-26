"""Role / サブグループ設定のフィールド定義編集ロジック (ScenarioRoleDetailGrid.js の純粋部分, Qt 非依存)。

データは JS と同じ形 (dict): {id, type, name, description, arraySize, options, required, dependency, builtin}
すべて不変操作 (新しいリストを返す)。
"""
from __future__ import annotations

import copy

OPTION_EDITABLE_TYPES = ["bit", "bezier", "dictionary", "text_list_index"]
DEFAULT_TEXT_LIST_INDEX_OPTIONS = {"matrixName": "ScenarioText", "fieldName": "texts", "previewLanguage": "Ja"}
DEFAULT_VOICE_REF_OPTIONS = {"matrixName": "ScenarioVoice", "fieldName": "voices", "previewLanguage": "Ja"}
SETTING_NAME = "ScenarioSubGroupSetting"
BIT_SIZE_MODES = [("manual", "手動指定"), ("enum", "Enumの要素数から"),
                  ("classDataId", "ClassDataIDの要素数から"), ("customClassDataId", "CustomClassDataIDの要素数から")]


def default_options_for_type(type_: str) -> dict:
    if type_ == "bit":
        return {"sizeMode": "manual", "sizeSourceName": None, "size": 8, "mode": "multiple", "allowSelectAll": True,
                "flagNames": [f"Flag{i}" for i in range(8)]}
    if type_ == "bezier":
        return {"valueType": "float", "min": 0, "max": 1}
    if type_ == "dictionary":
        return {"keyType": "int", "valueType": "int", "valueArraySize": 0, "valueOptions": {}}
    if type_ == "text_list_index":
        return dict(DEFAULT_TEXT_LIST_INDEX_OPTIONS)
    if type_ == "voice_ref":
        return dict(DEFAULT_VOICE_REF_OPTIONS)
    return {}


def js_int(v, default=0) -> int:
    """parseInt(v,10) || default"""
    import re
    m = re.match(r"\s*([+-]?\d+)", str(v if v is not None else ""))
    if not m:
        return default
    n = int(m.group(1))
    return n or default


def normalize_loaded(response: dict) -> tuple:
    """GET の応答 {data:[...], branchType} -> (fields, branchType)。id 欠落は連番、required 未指定は True。"""
    out = []
    for i, item in enumerate(response.get("data") or []):
        row = dict(item)
        row["id"] = item.get("id") or i + 1
        row["required"] = item.get("required") is not False
        out.append(row)
    return out, response.get("branchType") or "General"


def is_parent_candidate_type(type_, enum_names, class_data_id_names) -> bool:
    if not type_:
        return False
    t = str(type_).lower()
    if t in ("bool", "boolean"):
        return True
    return type_ in (enum_names or []) or type_ in (class_data_id_names or [])


def parent_candidates(data, enum_names, class_data_id_names, exclude_id=None) -> list:
    return [f for f in data if f.get("id") != exclude_id and is_parent_candidate_type(f.get("type"), enum_names, class_data_id_names)]


def is_bool_type(t) -> bool:
    return str(t).lower() in ("bool", "boolean")


def build_dependency(parent_name, values, data, exclude_id=None):
    """親名と値(文字列配列) -> dependency dict | None。値が空で親が bool のときは [True]。"""
    if not parent_name:
        return None
    parent = next((f for f in data if f.get("name") == parent_name and f.get("id") != exclude_id), None)
    ev = list(values) if values else ([True] if parent and str(parent.get("type")).lower() == "bool" else [])
    return {"parentFieldName": parent_name, "enableValues": ev, "hideWhenDisabled": True}


def default_dep_values_for_parent(parent_field) -> list:
    """親を選んだ直後の初期値: bool なら ['true']、それ以外は []。"""
    return ["true"] if parent_field and is_bool_type(parent_field.get("type")) else []


def next_field_id(data) -> int:
    return max([f.get("id") or 0 for f in data] + [0]) + 1


def add_field(data, *, type_, name, description="", array_size=0, options=None, required=True,
              dep_parent=None, dep_values=None, setting_mode=False):
    """-> (new_data, error_message|None)"""
    type_, name = (type_ or "").strip(), (name or "").strip()
    if not type_ or not name:
        return data, "タイプと名前は必須です"
    if setting_mode and any(i.get("name") == name for i in data):
        return data, f"「{name}」は既に存在します"
    dep = build_dependency(dep_parent, dep_values or [], data)
    row = {"id": next_field_id(data), "type": type_, "name": name, "description": description,
           "arraySize": js_int(array_size), "required": required}
    if type_ in OPTION_EDITABLE_TYPES:
        row["options"] = options if options is not None else {}
    if dep:
        row["dependency"] = dep
    return [*data, row], None


def set_options(data, row_id, options) -> list:
    return [{**f, "options": options} if f.get("id") == row_id else f for f in data]


def set_dependency(data, row_id, parent_name, values) -> list:
    dep = build_dependency(parent_name, values, data, exclude_id=row_id)
    out = []
    for f in data:
        if f.get("id") != row_id:
            out.append(f)
        elif dep:
            out.append({**f, "dependency": dep})
        else:
            out.append({k: v for k, v in f.items() if k != "dependency"})
    return out


def delete_field(data, row_id, setting_mode=False) -> list:
    """親を消した場合は子の dependency もクリア。組み込みフィールドは設定モードで削除不可。"""
    target = next((f for f in data if f.get("id") == row_id), None)
    if target is None or (setting_mode and target.get("builtin")):
        return data
    name = target.get("name")
    out = []
    for f in data:
        if f.get("id") == row_id:
            continue
        if name and (f.get("dependency") or {}).get("parentFieldName") == name:
            f = {k: v for k, v in f.items() if k != "dependency"}
        out.append(f)
    return out


def move_field(data, row_id, direction, setting_mode=False) -> list:
    idx = next((i for i, f in enumerate(data) if f.get("id") == row_id), -1)
    tgt = idx + direction
    if idx == -1 or tgt < 0 or tgt >= len(data):
        return data
    if setting_mode and (data[idx].get("builtin") or data[tgt].get("builtin")):
        return data
    out = list(data)
    item = out.pop(idx)
    out.insert(tgt, item)
    return out


def toggle_required(data, row_id) -> list:
    return [{**f, "required": not (f.get("required") is not False)} if f.get("id") == row_id else f for f in data]


def edit_cell(data, row_id, key, value, setting_mode=False) -> list:
    """グリッド内編集 (type/name/description/arraySize)。設定モードの組み込み行は編集不可。arraySize は数値化。"""
    out = []
    for f in data:
        if f.get("id") != row_id or (setting_mode and f.get("builtin")):
            out.append(f)
            continue
        if key == "arraySize":
            value = js_int(value)
        out.append({**f, key: value})
    return out


def children_by_parent(data) -> dict:
    m = {}
    for f in data:
        p = (f.get("dependency") or {}).get("parentFieldName")
        if p:
            m.setdefault(p, []).append(f.get("name"))
    return m


def dependency_summary(field) -> str:
    dep = field.get("dependency") or {}
    if not dep.get("parentFieldName"):
        return ""
    vals = " | ".join(str(v) for v in (dep.get("enableValues") or [])) or "…"
    return f'{dep["parentFieldName"]} = {vals}'


def dependency_tooltip(field) -> str:
    dep = field.get("dependency") or {}
    vals = " | ".join(str(v) for v in (dep.get("enableValues") or []))
    return f'親「{dep.get("parentFieldName")}」が [{vals}] のとき編集可能'


def dependency_value_options(parent_type, member_options) -> list:
    """DependencyValuesEditor の選択肢。bool は True/False 固定。"""
    if parent_type and is_bool_type(parent_type):
        return [{"value": "true", "label": "True"}, {"value": "false", "label": "False"}]
    return list(member_options or [])


def add_dependency_value(selected, v) -> list:
    if v is None or v == "":
        return list(selected)
    s = str(v)
    return list(selected) if s in selected else [*selected, s]


def remove_dependency_value(selected, v) -> list:
    return [x for x in selected if x != v]


def key_type_options(enum_names, class_data_id_names, custom_class_data_id_names) -> list:
    out = []
    for t in ["int", *enum_names, *class_data_id_names, *custom_class_data_id_names]:
        if t not in out:
            out.append(t)
    return out


def bit_set_size(options, n) -> dict:
    """ビット数を変更。フラグ名は既存を残し、足りない分を FlagN で補う (最小1)。"""
    try:
        n = max(1, int(float(n)))
    except (TypeError, ValueError):
        n = 1
    flags = options.get("flagNames") or []
    return {**options, "size": n, "flagNames": [(flags[i] if i < len(flags) and flags[i] else f"Flag{i}") for i in range(n)]}


def bit_set_flag_name(options, index, value) -> dict:
    flags = list(options.get("flagNames") or [])
    while len(flags) <= index:
        flags.append("")
    flags[index] = value
    return {**options, "flagNames": flags}


def bit_size_mode_source_names(mode, enum_names, class_data_id_names, custom_names) -> list:
    return {"enum": enum_names, "classDataId": class_data_id_names, "customClassDataId": custom_names}.get(mode, [])


def bit_effective_size(options) -> int:
    if options.get("size") is not None:
        return options["size"]
    return len(options.get("flagNames") or []) or 8


def save_payload(data, branch_type) -> dict:
    """POST/generate に送る本文 (JS: { data, branchType })。UI専用の id は残す (JS も残している)。"""
    return {"data": copy.deepcopy(data), "branchType": branch_type}


def format_save_message(result: dict, setting_mode: bool) -> str:
    msg = result.get("message") or result.get("error") or ""
    if setting_mode and result.get("sync"):
        msg += f"\n（既存シナリオの {result['sync'].get('nodes_touched')} 個のサブグループへ反映）"
    if setting_mode and result.get("error_detail"):
        msg += f"\n⚠ {result['error_detail']}"
    return msg
