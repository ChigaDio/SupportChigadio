"""サブグループ設定(ScenarioSubGroupSetting)の値の読み書きヘルパー (Qt 非依存)。

`js_ref/src/scenarioSubGroupSetting.js` の移植。スキーマの取得(fetch)は api 層
(`ApiClient.subgroup_setting_form_schema`) の仕事なので、ここでは取得済みのレスポンスを受け取る。

対応表 (JS -> Python):
    SUBGROUP_SETTING_NODE_KEY / IS_WAIT_KEY_FIELD / SUBGROUP_SETTING_API / SUBGROUP_SETTING_ROLE_NAME -> 同名
    fetchSubGroupSettingSchema -> parse_subgroup_setting_response(res_json)  (HTTP は ApiClient)
    getNodeSetting             -> get_node_setting
    getSettingValue            -> get_setting_value
    setSettingValue            -> set_setting_value
    formDataToSetting          -> form_data_to_setting
    buildInitialSetting        -> build_initial_setting
    buildDefaultSettingLine    -> build_default_setting_line
"""
from __future__ import annotations

from .dsl import decompile_sub_group_setting, normalize_sub_group_setting

SUBGROUP_SETTING_NODE_KEY = "subGroupSetting"
IS_WAIT_KEY_FIELD = "is_wait_key"
SUBGROUP_SETTING_API = "/api/scenario-subgroup-setting"
SUBGROUP_SETTING_ROLE_NAME = "ScenarioSubGroupSetting"

_UNSET = object()


def parse_subgroup_setting_response(res_json) -> dict:
    """GET {API}/form-schema の本文 {schema, defaults} -> {"schema": ... | None, "defaults": [...]}"""
    body = res_json if isinstance(res_json, dict) else {}
    schema = body.get("schema")
    ok = isinstance(schema, dict) and not schema.get("error") and isinstance(schema.get("fields"), list)
    defaults = body.get("defaults")
    return {"schema": schema if ok else None, "defaults": defaults if isinstance(defaults, list) else []}


def get_node_setting(node, schema, defaults):
    data = (node or {}).get("data") if isinstance(node, dict) else None
    cur = data.get(SUBGROUP_SETTING_NODE_KEY) if isinstance(data, dict) else None
    return normalize_sub_group_setting(cur, schema, defaults)


def get_setting_value(setting, name, fallback=None):
    for d in setting or []:
        if d and d.get("name") == name:
            v = d.get("value")
            return v if v is not None else fallback
    return fallback


def set_setting_value(setting, name, value, schema, defaults):
    base = normalize_sub_group_setting(setting, schema, defaults)
    if not any(d.get("name") == name for d in base):
        return [*base, {"name": name, "type": None, "value": value}]
    return [({**d, "value": value} if d.get("name") == name else d) for d in base]


def form_data_to_setting(form_data, schema):
    out = []
    for f in (schema or {}).get("fields") or []:
        found = next((d for d in form_data or [] if d and d.get("name") == f.get("name")), None)
        out.append({"name": f.get("name"), "type": f.get("type"), "value": found.get("value") if found else None})
    return out


def build_initial_setting(defaults):
    return [dict(d) for d in defaults or []]


def build_default_setting_line(schema, defaults, class_data_schemas=None):
    return decompile_sub_group_setting(defaults, schema, class_data_schemas or {})
