"""遷移エディタ(ScenarioEventTransition.js)の「画面に依存しない」ロジック (Qt 非依存)。

JS 側では React の state / ref に埋まっていた計算を、純関数・小さなクラスに切り出したもの。
詳細な対応表は docs/transition_logic_map.md。

方針
- ``tab_data`` = ``{tabId: {"nodes": [...], "edges": [...]}}``。JS と同じく **不変更新**
  (操作関数は新しい tab_data を返し、変更しない部分は同じ参照を共有する)。Undo 履歴が参照を保持するため。
  例外: 「全体編集/Sub編集」の適用 (``apply_edit_sections``) と ``merge_local_role_data_into_tree`` は
  JS と同じくサーバーから取ったツリーを **直接書き換える**。
- 戻り値のオブジェクトのキー名は JS のまま (camelCase)。
- JS の undefined は「キーが無い」、null は None。
"""
from __future__ import annotations

import json
import os
import re
import time

from . import diff as _diff
from . import dsl as _dsl
from . import index_tools as _index_tools
from . import node_utils as _node_utils
from . import subgroup_setting as _sgs
from .dsl import js_json_stringify, js_string, js_truthy
from .subgroup_setting import SUBGROUP_SETTING_NODE_KEY

_WS = _dsl._WS_STRIP


def js_trim(s) -> str:
    return js_string(s).strip(_WS)


def _or(v, default):
    """JS の ``v || default``。"""
    return v if js_truthy(v) else default


def _data(node) -> dict:
    d = node.get("data") if isinstance(node, dict) else None
    return d if isinstance(d, dict) else {}


# ============================================================
# ノードの色分け
# ============================================================
NODE_COLOR_PRESETS = [
    {"key": "red", "label": "赤", "hue": 0},
    {"key": "orange", "label": "オレンジ", "hue": 28},
    {"key": "yellow", "label": "黄", "hue": 50},
    {"key": "green", "label": "緑", "hue": 130},
    {"key": "teal", "label": "青緑", "hue": 175},
    {"key": "blue", "label": "青", "hue": 210},
    {"key": "purple", "label": "紫", "hue": 270},
    {"key": "pink", "label": "ピンク", "hue": 320},
]


def hash_hue(s) -> int:
    """JS の hashHue。charCodeAt は UTF-16 コードユニット単位。"""
    raw = js_string(s).encode("utf-16-le", "surrogatepass")
    h = 0
    for i in range(0, len(raw), 2):
        code = raw[i] | (raw[i + 1] << 8)
        h = (h * 31 + code) & 0xFFFFFFFF
    return (h * 47) % 360


def get_node_tint(node_path, color_key=None):
    """color_key: None=自動 / 'none'=色なし / プリセットの key。"""
    if color_key == "none":
        return None
    preset = next((p for p in NODE_COLOR_PRESETS if p["key"] == color_key), None)
    hue = preset["hue"] if preset else hash_hue(node_path)
    return {
        "hue": hue,
        "bg": f"hsl({hue}, 75%, 96%)",
        "bgStrong": f"hsl({hue}, 65%, 92%)",
        "accent": f"hsl({hue}, 60%, 50%)",
    }


def hue_swatch(hue) -> str:
    return f"hsl({hue}, 60%, 55%)"


class NodeColorStore:
    """サブグループの背景色 (UI 専用)。JS では localStorage('scn-node-colors:{eventId}:{subId}')。
    ここでは設定フォルダの JSON ファイルへ ``{"eventId:subId": {nodePath: colorKey}}`` で保存する。"""

    FILE = "scn-node-colors-v1.json"

    def __init__(self, directory):
        self.path = os.path.join(directory, self.FILE) if directory else None

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def get(self, event_id, sub_id) -> dict:
        if not self.path:
            return {}
        v = self._read().get(f"{event_id}:{sub_id}")
        return dict(v) if isinstance(v, dict) else {}

    def set_paths(self, event_id, sub_id, paths, color_key) -> dict:
        """paths の色を color_key にする。None/空なら自動(=エントリ削除)。更新後の dict を返す。"""
        cur = self.get(event_id, sub_id)
        for p in paths:
            if not color_key:
                cur.pop(p, None)
            else:
                cur[p] = color_key
        if self.path:
            try:
                allv = self._read()
                allv[f"{event_id}:{sub_id}"] = cur
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(allv, f, ensure_ascii=False)
            except OSError:
                pass
        return cur


# ============================================================
# フィールドの type 補完 / ID 採番
# ============================================================
def with_field_types(form_data, schema):
    """フォームの出力 [{name,value,arraySize}] に、Role スキーマの type を補う(既にある type は変更しない)。"""
    if not isinstance(form_data, list) or not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
        return form_data
    types = {}
    for f in schema["fields"]:
        if isinstance(f, dict) and js_truthy(f.get("name")) and js_truthy(f.get("type")):
            types[js_string(f["name"])] = f["type"]
    out_list = []
    for d in form_data:
        if not isinstance(d, dict) or js_truthy(d.get("type")) or not js_truthy(types.get(js_string(d.get("name")))):
            out_list.append(d)
            continue
        out = {}
        for k, v in d.items():
            out[k] = v
            if k == "name":
                out["type"] = types[js_string(d.get("name"))]
        out_list.append(out)
    return out_list


def _parse_int_prefix(s):
    m = re.match(r"[\s﻿]*([+-]?\d+)", js_string(s))
    return int(m.group(1)) if m else None


def get_next_node_id(nodes) -> str:
    ids = [v for v in (_parse_int_prefix(n.get("id")) for n in nodes) if v is not None]
    return str(max(ids) + 1) if ids else "1"


# ============================================================
# CSV 入出力
# ============================================================
CSV_COLUMNS = ["type", "id", "description", "roleIds", "x", "y", "source", "target", "sourceHandle", "targetHandle"]


def csv_escape_cell(value) -> str:
    s = "" if value is None else js_string(value)
    if re.search(r'[",\n\r]', s):
        return '"' + s.replace('"', '""') + '"'
    return s


def rows_to_csv(rows) -> str:
    lines = [",".join(CSV_COLUMNS)]
    for row in rows:
        lines.append(",".join(csv_escape_cell(row.get(c)) for c in CSV_COLUMNS))
    return "\r\n".join(lines)


def parse_csv(text: str) -> list:
    rows, row, field, in_quotes = [], [], "", False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field += '"'
                    i += 1
                else:
                    in_quotes = False
            else:
                field += ch
        elif ch == '"':
            in_quotes = True
        elif ch == ",":
            row.append(field)
            field = ""
        elif ch == "\r":
            pass
        elif ch == "\n":
            row.append(field)
            field = ""
            rows.append(row)
            row = []
        else:
            field += ch
        i += 1
    if len(field) > 0 or len(row) > 0:
        row.append(field)
        rows.append(row)
    return [r for r in rows if len(r) > 1 or (len(r) == 1 and r[0] != "")]


def tab_to_csv_rows(tab_data) -> list:
    rows = []
    for node in tab_data["nodes"]:
        d = _data(node)
        pos = node.get("position") if isinstance(node.get("position"), dict) else {}
        role_ids = []
        for r in d.get("roles") or []:
            v = r.get("roleId")
            if v is None:
                v = r.get("id")
            role_ids.append("" if v is None else js_string(v))
        x = pos.get("x")
        y = pos.get("y")
        rows.append({
            "type": "node", "id": node.get("id"),
            "description": _or(d.get("description"), ""),
            "roleIds": ";".join(role_ids),
            "x": 0 if x is None else x, "y": 0 if y is None else y,
            "source": "", "target": "", "sourceHandle": "", "targetHandle": "",
        })
    for edge in tab_data["edges"]:
        rows.append({
            "type": "edge", "id": _or(edge.get("id"), ""), "description": "", "roleIds": "", "x": "", "y": "",
            "source": edge.get("source"), "target": edge.get("target"),
            "sourceHandle": _or(edge.get("sourceHandle"), ""), "targetHandle": _or(edge.get("targetHandle"), ""),
        })
    return rows


def tab_to_csv(tab_data) -> str:
    """ファイルへ書く文字列 (先頭に BOM を付けるのは呼び出し側。JS: '\\uFEFF' + csv)。"""
    return rows_to_csv(tab_to_csv_rows(tab_data))


_FLOAT_RE = re.compile(r"[\s﻿]*([+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?))")


def js_parse_float(s):
    """JS の parseFloat。数値にならなければ None (NaN)。"""
    m = _FLOAT_RE.match(js_string(s))
    if not m:
        return None
    t = m.group(1)
    if t.endswith("Infinity"):
        return float("-inf") if t.startswith("-") else float("inf")
    v = float(t)
    return int(v) if v == int(v) and abs(v) < 1e21 else v


def parse_csv_to_tab_data(text: str) -> dict:
    table = parse_csv(text)
    if len(table) == 0:
        return {"nodes": [], "edges": []}
    col_index = {}
    for i, h in enumerate(table[0]):
        col_index[js_trim(h)] = i

    def get(row, col):
        if col in col_index:
            i = col_index[col]
            return row[i] if i < len(row) else ""
        return ""

    nodes, edges = [], []
    for row in table[1:]:
        typ = get(row, "type")
        if typ == "node":
            id_ = get(row, "id")
            if not id_:
                continue
            role_ids = get(row, "roleIds")
            nodes.append({
                "id": id_,
                "type": "customGroup",
                "position": {"x": _or(js_parse_float(get(row, "x")), 0), "y": _or(js_parse_float(get(row, "y")), 0)},
                "data": {
                    "label": id_,
                    "description": get(row, "description"),
                    "roles": [{"roleId": rid, "uniqueId": f"{id_}_{rid}"} for rid in role_ids.split(";") if rid]
                    if role_ids else [],
                    "subgroups": {},
                },
                "draggable": True,
            })
        elif typ == "edge":
            source, target = get(row, "source"), get(row, "target")
            if not source or not target:
                continue
            e = {"id": get(row, "id") or f"e-{source}-{target}", "source": source, "target": target}
            if get(row, "sourceHandle"):
                e["sourceHandle"] = get(row, "sourceHandle")
            if get(row, "targetHandle"):
                e["targetHandle"] = get(row, "targetHandle")
            edges.append(e)
    ids = {n["id"] for n in nodes}
    return {"nodes": nodes, "edges": [e for e in edges if e["source"] in ids and e["target"] in ids]}


# ============================================================
# 全体編集 / Sub編集 (DSL テキスト <-> ツリー)
# ============================================================
ALL_EDIT_HEADER_RE = re.compile(r"^#\s*====\s*SUB:(\S+)\s+NODE:(\S+).*?====\s*\Z")
GUIDE_LINE_RE = re.compile(r"^#\s*例\s*[:：]")


class EditContext:
    """全体編集系の関数が必要とする、画面側の状態。JS ではコンポーネントのクロージャ。"""

    def __init__(self, role_form_schemas=None, class_data_schemas=None, setting_schema=None, setting_defaults=None,
                 sub_id=None, current_tab_nodes=None, is_sub=False, parent_id=None, role_data_cache=None):
        self.role_form_schemas = role_form_schemas if role_form_schemas is not None else {}
        self.class_data_schemas = class_data_schemas if class_data_schemas is not None else {}
        self.setting_schema = setting_schema
        self.setting_defaults = setting_defaults if setting_defaults is not None else []
        self.sub_id = sub_id
        self.current_tab_nodes = current_tab_nodes   # currentTabData.nodes (無ければ None)
        self.is_sub = is_sub
        self.parent_id = parent_id
        self.role_data_cache = role_data_cache if role_data_cache is not None else {}


def collect_all_edit_targets(nodes, path_ids, out):
    for node in nodes or []:
        path = [*path_ids, js_string(node.get("id"))]
        d = node.get("data")
        out.append({"path": path, "node": node, "label": (d.get("description") if isinstance(d, dict) else None) or ""})
        sgs = (d.get("subgroups") if isinstance(d, dict) else None) or {}
        for sg_id in list(sgs.keys()):
            inner = (sgs[sg_id] or {}).get("nodes") if isinstance(sgs[sg_id], dict) else None
            collect_all_edit_targets(inner or [], path, out)


def ensure_all_edit_node_path(tree, path_segments, ctx: EditContext):
    """pathSegments が指すノードを返す。無ければ途中の階層も含めて新規作成する。"""
    lst = tree.get("nodes")
    if not isinstance(lst, list):
        lst = []
        tree["nodes"] = lst
    node = None
    for i, id_ in enumerate(path_segments):
        is_sub = i > 0
        parent_id = path_segments[i - 1] if i > 0 else None
        is_target_level = i == len(path_segments) - 1
        existing = next((k for k, n in enumerate(lst) if js_string(n.get("id")) == id_), -1)
        if existing == -1:
            data = {
                "label": f"Group: {parent_id} / Sub: {id_}" if is_sub else id_,
                "description": "",
                "roles": [],
                "subgroups": {},
                "isSubGroup": is_sub,
            }
            if ctx.setting_schema:
                data[SUBGROUP_SETTING_NODE_KEY] = _sgs.build_initial_setting(ctx.setting_defaults)
            node = {
                "id": id_,
                "type": "subGroupNode" if is_sub else "customGroup",
                "draggable": True,
                "position": {"x": 120 + (len(lst) % 5) * 180, "y": 120 + (len(lst) // 5) * 140},
                "data": data,
            }
            lst.append(node)
        elif is_target_level:
            node = lst.pop(existing)
            lst.append(node)
        else:
            node = lst[existing]
        if i < len(path_segments) - 1:
            if not js_truthy(node.get("data")):
                node["data"] = {}
            d = node["data"]
            if not js_truthy(d.get("subgroups")):
                d["subgroups"] = {}
            sg_key = js_string(node.get("id"))
            if not js_truthy(d["subgroups"].get(sg_key)):
                d["subgroups"][sg_key] = {"nodes": [], "edges": []}
            if not isinstance(d["subgroups"][sg_key].get("nodes"), list):
                d["subgroups"][sg_key]["nodes"] = []
            lst = d["subgroups"][sg_key]["nodes"]
    return node


def merge_local_role_data_into_tree(tree, sid, ctx: EditContext):
    """ローカル(画面)側の最新 Role データ / サブグループ設定を、サーバーから取ったツリーへ上書きマージする。tree を直接書き換える。"""
    if not tree or not isinstance(tree.get("nodes"), list):
        return tree
    if js_string(sid) != js_string(ctx.sub_id) or ctx.current_tab_nodes is None:
        return tree

    local_roles_by_path = {}
    local_setting_by_path = {}
    path_prefix = [js_string(ctx.parent_id)] if (ctx.is_sub and js_truthy(ctx.parent_id)) else []

    def collect_local(nodes, path_ids):
        for n in nodes or []:
            if not n:
                continue
            path = [*path_ids, js_string(n.get("id"))]
            path_key = "/".join(path)
            d = n.get("data")
            roles = d.get("roles") if isinstance(d, dict) else None
            local_roles_by_path[path_key] = [dict(r) for r in roles] if js_truthy(roles) else []
            if isinstance(d, dict) and isinstance(d.get(SUBGROUP_SETTING_NODE_KEY), list):
                local_setting_by_path[path_key] = [dict(x) for x in d[SUBGROUP_SETTING_NODE_KEY]]
            cached = ctx.role_data_cache.get(path_key) if isinstance(ctx.role_data_cache, dict) else None
            if cached and path_key in local_roles_by_path:
                local_roles_by_path[path_key] = [
                    ({**r, "data": cached[js_string(r.get("uniqueId"))]} if js_string(r.get("uniqueId")) in cached else r)
                    for r in local_roles_by_path[path_key]
                ]
            sgs = (d.get("subgroups") if isinstance(d, dict) else None) or {}
            for k in list(sgs.keys()):
                collect_local((sgs[k] or {}).get("nodes") if isinstance(sgs[k], dict) else None, path)

    collect_local(ctx.current_tab_nodes, path_prefix)

    def apply_local(nodes, path_ids):
        for node in nodes or []:
            if not node:
                continue
            path = [*path_ids, js_string(node.get("id"))]
            path_key = "/".join(path)
            local_roles = local_roles_by_path.get(path_key)
            if path_key in local_setting_by_path:
                if not js_truthy(node.get("data")):
                    node["data"] = {}
                node["data"][SUBGROUP_SETTING_NODE_KEY] = local_setting_by_path[path_key]
            if local_roles is not None:
                if not js_truthy(node.get("data")):
                    node["data"] = {}
                by_uid = {js_string(r.get("uniqueId")): r for r in local_roles}
                server_roles = _or(node["data"].get("roles"), [])
                merged = []
                for r in server_roles:
                    lr = by_uid.get(js_string(r.get("uniqueId")))
                    merged.append({**r, "data": lr["data"]} if lr is not None and "data" in lr else r)
                node["data"]["roles"] = merged
                for lr in local_roles:
                    if not any(_strict_eq(r.get("uniqueId"), lr.get("uniqueId")) for r in node["data"]["roles"]):
                        node["data"]["roles"].append(dict(lr))
            d = node.get("data")
            sgs = (d.get("subgroups") if isinstance(d, dict) else None) or {}
            for k in list(sgs.keys()):
                apply_local((sgs[k] or {}).get("nodes") if isinstance(sgs[k], dict) else None, path)

    apply_local(tree["nodes"], [])
    return tree


def _strict_eq(a, b) -> bool:
    """JS の ===。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return a is b


def build_edit_lines_for_sub(sid, tree, targets_out: dict, ctx: EditContext) -> list:
    """1つの Sub のツリーから、編集用テキスト行を組み立てる。targets_out に "subId::path" -> ノード を書き込む。"""
    lines = []
    targets = []
    collect_all_edit_targets(tree.get("nodes"), [], targets)
    for t in targets:
        path_key = "/".join(t["path"])
        targets_out[f"{sid}::{path_key}"] = t["node"]
        label_suffix = f" ({t['label']})" if t["label"] else ""
        lines.append(f"# ==== SUB:{sid} NODE:{path_key}{label_suffix} ====")
        if ctx.setting_schema:
            setting_line = _dsl.decompile_sub_group_setting(
                _sgs.get_node_setting(t["node"], ctx.setting_schema, ctx.setting_defaults),
                ctx.setting_schema, ctx.class_data_schemas)
            if setting_line:
                lines.append(setting_line)
        roles = _data(t["node"]).get("roles") or []
        body = _dsl.decompile_roles(roles, ctx.role_form_schemas, ctx.class_data_schemas)
        if body:
            lines.append(body)
        lines.append("")
    lines.append("# 例: 新しいグループを追加したい場合は、下の「新しいグループの追加を許可する」に")
    lines.append("# 例: チェックを入れたうえで、下記のような見出しを書いてください（この案内行自体は無視されます）")
    lines.append(f"# 例: ==== SUB:{sid} NODE:新しいノードID ====")
    lines.append(f"# 例: ==== SUB:{sid} NODE:既存または新規の親ID/新しいサブグループのノードID ====")
    if ctx.setting_schema:
        lines.append("# 例: 見出しの直下に「#@ is_wait_key=true」のように書くと、そのサブグループの設定(入力待ち等)になります")
    lines.append("")
    return lines


def parse_edit_sections(text: str) -> list:
    sections, current = [], None
    for line in text.split("\n"):
        if GUIDE_LINE_RE.search(line):
            continue
        m = ALL_EDIT_HEADER_RE.match(line)
        if m:
            if current:
                sections.append(current)
            current = {"subId": m.group(1), "pathKey": m.group(2), "bodyLines": []}
        elif current:
            current["bodyLines"].append(line)
    if current:
        sections.append(current)
    sections.sort(key=lambda s: len(s["pathKey"].split("/")))
    return sections


def apply_edit_sections(sections, sub_trees: dict, targets: dict, allow_new_groups: bool, ctx: EditContext,
                        dry_run: bool = False) -> dict:
    """セクション列を、対応するツリーへ適用する。dry_run=True ではツリーを変更せず差分(changes)だけ返す。

    sub_trees: {subId: {nodes, edges}} / targets: {"subId::path": node} (どちらも直接書き換える)
    戻り値: {"diagnostics": [{message, subId, path}], "touchedSubIds": set, "changes": [...]}
    """
    diagnostics, touched, changes = [], set(), []
    schema, defaults = ctx.setting_schema, ctx.setting_defaults

    for section in sections:
        key = f"{section['subId']}::{section['pathKey']}"
        target = targets.get(key)
        is_new = False
        if target is None:
            tree = sub_trees.get(section["subId"])
            if not tree:
                diagnostics.append({"message": f"存在しないSubです: SUB:{section['subId']}",
                                    "subId": section["subId"], "path": section["pathKey"]})
                continue
            if not allow_new_groups:
                diagnostics.append({
                    "message": f"未知の見出しです（新しいグループは作成されません）: SUB:{section['subId']} NODE:{section['pathKey']} ／ 新しいグループを追加したい場合は「新しいグループの追加を許可する」にチェックを入れてから適用してください",
                    "subId": section["subId"], "path": section["pathKey"]})
                continue
            if dry_run:
                is_new = True
            else:
                target = ensure_all_edit_node_path(tree, section["pathKey"].split("/"), ctx)
                targets[key] = target
        base_node = target if target is not None else {"data": {}}

        next_setting = None
        base_setting = None
        setting_has_error = False
        if schema:
            next_setting = _sgs.get_node_setting(base_node, schema, defaults)
            base_setting = next_setting
            for line_text in _dsl.extract_sub_group_setting_lines(section["bodyLines"]):
                res = _dsl.compile_sub_group_setting(line_text, schema, ctx.class_data_schemas)
                written = res["data"]
                for d in res["diagnostics"]:
                    if d.severity == "error":
                        setting_has_error = True
                        diagnostics.append({
                            "message": f"SUB:{section['subId']} NODE:{section['pathKey']} - #@ {d.message}",
                            "subId": section["subId"], "path": section["pathKey"]})
                new_list = []
                for cur in next_setting:
                    w = next((x for x in written if x.get("name") == cur.get("name")), None)
                    new_list.append({**cur, "value": w["value"]} if w and w.get("value") is not None else cur)
                next_setting = new_list

        existing_roles = _data(base_node).get("roles") or []
        comp = _dsl.compile_document("\n".join(section["bodyLines"]), ctx.role_form_schemas, existing_roles,
                                     ctx.class_data_schemas)
        compiled_roles, sec_diags = comp["roles"], comp["diagnostics"]
        for d in sec_diags:
            if d.severity == "error":
                diagnostics.append({"message": f"SUB:{section['subId']} NODE:{section['pathKey']} - {d.message}",
                                    "subId": section["subId"], "path": section["pathKey"]})
        if any(d.severity == "error" for d in sec_diags) or setting_has_error:
            continue

        if dry_run:
            setting_changes = []
            if next_setting is not None:
                for i, n in enumerate(next_setting):
                    frm = base_setting[i].get("value") if i < len(base_setting) and base_setting[i] else _diff.UNDEFINED
                    if frm is not _diff.UNDEFINED and js_json_stringify(frm) == js_json_stringify(n.get("value")):
                        continue
                    setting_changes.append({"name": n.get("name"), "from": frm, "to": n.get("value")})
            changes.append({"subId": section["subId"], "pathKey": section["pathKey"], "isNew": is_new,
                            "diff": _diff.diff_roles(existing_roles, compiled_roles),
                            "settingChanges": setting_changes})
            continue

        if not js_truthy(target.get("data")):
            target["data"] = {}
        target["data"]["roles"] = compiled_roles
        if next_setting is not None:
            target["data"][SUBGROUP_SETTING_NODE_KEY] = next_setting
        touched.add(section["subId"])

    return {"diagnostics": diagnostics, "touchedSubIds": touched, "changes": changes}


def summarize_changes(changes) -> int:
    return sum(c["diff"]["totalChanges"] + len(c["settingChanges"]) + (1 if c["isNew"] else 0) for c in changes)


def split_sections_for_sub(text: str, sub_id):
    """Sub編集: 現在の Sub 用セクションと、別 Sub の見出し(エラー扱い)に分ける。"""
    all_sections = parse_edit_sections(text)
    mine = [s for s in all_sections if js_string(s["subId"]) == js_string(sub_id)]
    foreign = [s for s in all_sections if js_string(s["subId"]) != js_string(sub_id)]
    return mine, foreign


def foreign_section_diagnostics(foreign) -> list:
    return [{
        "message": f"このSub編集では別Subの見出しは扱えません（SUB:{s['subId']} NODE:{s['pathKey']}）。複数Subをまたいで編集する場合は「全体編集(全Sub一括)」を使ってください",
        "subId": s["subId"], "path": s["pathKey"]} for s in foreign]


# ============================================================
# タブデータ(nodes/edges)の操作。すべて不変更新。
# ============================================================
def empty_tab():
    return {"nodes": [], "edges": []}


def node_path_of(is_sub: bool, parent_id, node_id) -> str:
    return f"{parent_id}/{node_id}" if is_sub else js_string(node_id)


def parent_of_tab(tab_id: str):
    return tab_id[len("subgroup-"):] if tab_id.startswith("subgroup-") else None


def normalize_loaded_tab(result) -> dict:
    """サーバーの {nodes, edges} から、存在しないノードを参照するエッジを除いた tab を作る。"""
    result = result if isinstance(result, dict) else {}
    nodes = result.get("nodes") or []
    ids = {n.get("id") for n in nodes}
    edges = [e for e in (result.get("edges") or []) if e.get("source") in ids and e.get("target") in ids]
    return {"nodes": nodes, "edges": edges}


def _set_tab(tab_data, tab_id, tab):
    return {**tab_data, tab_id: tab}


def _map_node(tab_data, tab_id, node_id, fn):
    cur = tab_data[tab_id]
    return _set_tab(tab_data, tab_id, {**cur, "nodes": [fn(n) if n.get("id") == node_id else n for n in cur["nodes"]]})


def _label(is_sub, parent_id, node_id):
    return f"Group: {parent_id} / Sub: {node_id}" if is_sub else node_id


def make_new_node(node_id, is_sub, parent_id, description="", setting_schema=None, setting_defaults=None) -> dict:
    data = {
        "label": _label(is_sub, parent_id, node_id),
        "description": js_trim(description),
        "roles": [],
        "subgroups": {},
        "isSubGroup": is_sub,
    }
    if setting_schema:
        data[SUBGROUP_SETTING_NODE_KEY] = _sgs.build_initial_setting(setting_defaults)
    return {"id": node_id, "type": "subGroupNode" if is_sub else "customGroup", "position": {"x": 0, "y": 0}, "data": data}


def add_node(tab_data, tab_id, is_sub, parent_id, description="", setting_schema=None, setting_defaults=None):
    """-> (new_tab_data, new_id)"""
    cur = tab_data[tab_id]
    new_id = get_next_node_id(cur["nodes"])
    node = make_new_node(new_id, is_sub, parent_id, description, setting_schema, setting_defaults)
    return _set_tab(tab_data, tab_id, {**cur, "nodes": [*cur["nodes"], node]}), new_id


def delete_node(tab_data, tab_id, node_id):
    cur = tab_data[tab_id]
    return _set_tab(tab_data, tab_id, {
        "nodes": [n for n in cur["nodes"] if n.get("id") != node_id],
        "edges": [e for e in cur["edges"] if e.get("source") != node_id and e.get("target") != node_id],
    })


def paste_node(tab_data, tab_id, copied, is_sub, parent_id, now_ms=None):
    """-> (new_tab_data, new_id)。copied: handleCopyNode で控えたノード。"""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    cur = tab_data[tab_id]
    new_id = get_next_node_id(cur["nodes"])
    cd = copied.get("data") if isinstance(copied.get("data"), dict) else {}
    roles = [{**r, "uniqueId": f"{now_ms}-{js_string(r.get('uniqueId'))}"} for r in cd.get("roles") or []]
    node = {**copied, "id": new_id, "type": "subGroupNode" if is_sub else "customGroup",
            "data": {**cd, "label": _label(is_sub, parent_id, new_id), "isSubGroup": is_sub, "subgroups": {}, "roles": roles}}
    return _set_tab(tab_data, tab_id, {**cur, "nodes": [*cur["nodes"], node]}), new_id


def edit_node(tab_data, tab_id, edit_node_id, new_id_raw, description_raw, is_sub, parent_id):
    """-> (new_tab_data, error_message)。ID 重複なら (tab_data, 'IDが重複しています')。"""
    new_id = js_trim(new_id_raw)
    cur = tab_data[tab_id]
    if new_id and new_id != edit_node_id and any(n.get("id") == new_id for n in cur["nodes"]):
        return tab_data, "IDが重複しています"
    final_id = new_id or edit_node_id
    nodes = []
    for n in cur["nodes"]:
        if n.get("id") != edit_node_id:
            nodes.append(n)
            continue
        nodes.append({**n, "id": final_id, "data": {
            **_data(n), "description": js_trim(description_raw), "label": _label(is_sub, parent_id, final_id)}})
    edges = []
    for e in cur["edges"]:
        s = final_id if e.get("source") == edit_node_id else e.get("source")
        t = final_id if e.get("target") == edit_node_id else e.get("target")
        edges.append({**e, "source": s, "target": t, "id": f"{s}-{t}"})
    return _set_tab(tab_data, tab_id, {"nodes": nodes, "edges": edges}), None


def reorder_nodes(tab_data, tab_id, frm, to):
    """上へ/下へボタン。範囲外は None。"""
    cur = tab_data[tab_id]
    if to < 0 or to >= len(cur["nodes"]):
        return None
    nodes = list(cur["nodes"])
    moved = nodes.pop(frm)
    nodes.insert(to, moved)
    return _set_tab(tab_data, tab_id, {**cur, "nodes": nodes})


def reorder_by_id(tab_data, tab_id, dragged_id, target_id):
    """ドラッグ&ドロップ。どちらかが無ければ None。"""
    cur = tab_data.get(tab_id) or empty_tab()
    frm = next((i for i, n in enumerate(cur["nodes"]) if n.get("id") == dragged_id), -1)
    to = next((i for i, n in enumerate(cur["nodes"]) if n.get("id") == target_id), -1)
    if frm < 0 or to < 0:
        return None
    nodes = list(cur["nodes"])
    moved = nodes.pop(frm)
    nodes.insert(to, moved)
    return _set_tab(tab_data, tab_id, {**cur, "nodes": nodes})


def set_node_subgroup_setting(tab_data, tab_id, node_id, setting):
    return _map_node(tab_data, tab_id, node_id,
                     lambda n: {**n, "data": {**_data(n), SUBGROUP_SETTING_NODE_KEY: setting}})


def add_role_to_tab(tab_data, tab_id, node_id, role):
    return _map_node(tab_data, tab_id, node_id,
                     lambda n: {**n, "data": {**_data(n), "roles": [*(_data(n).get("roles") or []), role]}})


def delete_role_from_tab(tab_data, tab_id, node_id, unique_id):
    return _map_node(tab_data, tab_id, node_id, lambda n: {**n, "data": {
        **_data(n), "roles": [r for r in _data(n).get("roles") or [] if not _strict_eq(r.get("uniqueId"), unique_id)]}})


def apply_saved_role_data(tab_data, tab_id, node_id, by_uid: dict):
    """role-data-batch の保存後に、ローカルの Role.data をそろえる。by_uid: {str(uniqueId): formData}"""
    def fn(n):
        roles = [({**r, "data": by_uid[js_string(r.get("uniqueId"))]} if js_string(r.get("uniqueId")) in by_uid else r)
                 for r in _data(n).get("roles") or []]
        return {**n, "data": {**_data(n), "roles": roles}}
    return _map_node(tab_data, tab_id, node_id, fn)


def typed_role_items(items, node, role_form_schemas):
    """handleSaveRoles: type の無いフィールドにスキーマの type を補う。items: [{uniqueId, formData}]"""
    cur_roles = _data(node).get("roles") or []
    out = []
    for it in items:
        role = next((r for r in cur_roles if js_string(r.get("uniqueId")) == js_string(it["uniqueId"])), None)
        out.append({"uniqueId": it["uniqueId"],
                    "formData": with_field_types(it["formData"], role_form_schemas.get(role.get("name"))) if role else it["formData"]})
    return out


def add_edge(tab_data, tab_id, edge):
    """-> (new_tab_data, error)。既に同じ接続があれば (tab_data, '既に接続済み')。"""
    cur = tab_data[tab_id]
    if any(e.get("source") == edge["source"] and e.get("target") == edge["target"] for e in cur["edges"]):
        return tab_data, "既に接続済み"
    return _set_tab(tab_data, tab_id, {**cur, "edges": [*cur["edges"], edge]}), None


def validate_connect(node_id, target_raw, all_node_ids, edges):
    """接続ダイアログの入力検証。-> (target, error_message, level)"""
    target = js_trim(target_raw)
    if not target or target == node_id:
        return None, "接続先が無効", "warning"
    if target not in all_node_ids:
        return None, "存在しないノードID", "error"
    if any(e.get("source") == node_id and e.get("target") == target for e in edges):
        return None, "既に接続済み", "warning"
    return target, None, None


def make_edge(source, target):
    return {"source": source, "target": target, "id": f"{source}-{target}"}


def remove_edge(tab_data, tab_id, edge):
    cur = tab_data[tab_id]
    return _set_tab(tab_data, tab_id, {**cur, "edges": [
        e for e in cur["edges"] if not (e.get("source") == edge["source"] and e.get("target") == edge["target"])]})


def move_to_group(tab_data, tab_id, node_id, target_group_id):
    """別グループ(サブグループタブ)へ移動。-> (new_tab_data, new_id) / ノードが無ければ (tab_data, None)"""
    cur = tab_data[tab_id]
    node = next((n for n in cur["nodes"] if n.get("id") == node_id), None)
    if node is None:
        return tab_data, None
    target_tab_id = f"subgroup-{target_group_id}"
    target_cur = tab_data.get(target_tab_id) or empty_tab()
    new_id = get_next_node_id(target_cur["nodes"])
    new_node = {**node, "id": new_id, "data": {**_data(node), "label": f"Group: {target_group_id} / Sub: {new_id}", "isSubGroup": True}}
    out = {
        **tab_data,
        tab_id: {"nodes": [n for n in cur["nodes"] if n.get("id") != node_id],
                 "edges": [e for e in cur["edges"] if e.get("source") != node_id and e.get("target") != node_id]},
        target_tab_id: {"nodes": [*target_cur["nodes"], new_node], "edges": target_cur["edges"]},
    }
    return out, new_id


def apply_index_changes_to_tab(tab_data, tab_id, changes):
    cur = tab_data[tab_id]
    return _set_tab(tab_data, tab_id, {**cur, "nodes": _index_tools.apply_index_changes(cur["nodes"], changes)})


def renumber_duplicates_in_tab(tab_data, tab_id, open_tab_ids):
    """重複 ID の振り直し。-> {"tabData", "renamed", "skipped", "blocked": bool}
    メインタブでサブグループのタブが開いていれば blocked=True (先に閉じてもらう)。"""
    cur = tab_data.get(tab_id)
    if cur is None:
        return {"tabData": tab_data, "renamed": [], "skipped": [], "blocked": False}
    is_main = tab_id == "main"
    if is_main and any(js_string(t).startswith("subgroup-") for t in open_tab_ids):
        return {"tabData": tab_data, "renamed": [], "skipped": [], "blocked": True}
    r = _node_utils.renumber_duplicate_nodes(cur["nodes"], rekey_subgroups=is_main)
    if not r["renamed"]:
        return {"tabData": tab_data, "renamed": [], "skipped": r["skipped"], "blocked": False}
    return {"tabData": _set_tab(tab_data, tab_id, {**cur, "nodes": r["nodes"]}),
            "renamed": r["renamed"], "skipped": r["skipped"], "blocked": False}


def _node_to_save(n, tab_id):
    d = _data(n)
    data = {}
    if "label" in d:
        data["label"] = d["label"]
    data["description"] = _or(d.get("description"), "")
    data["roles"] = _or(d.get("roles"), [])
    data["subgroups"] = _or(d.get("subgroups"), {})
    if "isSubGroup" in d:
        data["isSubGroup"] = d["isSubGroup"]
    if SUBGROUP_SETTING_NODE_KEY in d:
        data[SUBGROUP_SETTING_NODE_KEY] = d[SUBGROUP_SETTING_NODE_KEY]
    return {
        "id": n.get("id"),
        "type": _or(n.get("type"), "customGroup" if tab_id == "main" else "subGroupNode"),
        "position": _or(n.get("position"), {"x": 0, "y": 0}),
        "data": data,
        "draggable": True,
    }


def build_save_data(tab_data, tab_id) -> dict:
    """performSave が送る本文 {nodes, edges}。"""
    cur = tab_data[tab_id]
    return {"nodes": [_node_to_save(n, tab_id) for n in cur["nodes"]], "edges": cur["edges"]}


def sync_main_subgroup(tab_data, pid):
    """サブグループタブの内容を、メインタブの node.data.subgroups[pid] へ反映する。"""
    sub = tab_data.get(f"subgroup-{pid}")
    main = tab_data.get("main")
    if not sub or not main:
        return tab_data
    sg = {"nodes": [_node_to_save(n, f"subgroup-{pid}") for n in sub["nodes"]], "edges": sub["edges"]}
    pid_s = js_string(pid)

    def fn(n):
        if n.get("id") != pid_s:
            return n
        d = _data(n)
        return {**n, "data": {**d, "subgroups": {**(d.get("subgroups") or {}), pid_s: sg}}}

    return {**tab_data, "main": {**main, "nodes": [fn(n) for n in main["nodes"]]}}


# ============================================================
# 検索・フィルタ・ナビゲーション
# ============================================================
def filter_visible(nodes, query="", only_wait=False, only_roles=False, only_issues=False,
                   issues_by_node=None, is_wait_node=None):
    """表示するカード [(node, index)]。query はスペース区切りの AND (ID・説明・Role名)。"""
    terms = [t for t in re.split(r"\s+", js_trim(query).lower()) if t]
    issues_by_node = issues_by_node or {}
    out = []
    for index, node in enumerate(nodes):
        d = _data(node)
        node_roles = d.get("roles") or []
        if only_roles and len(node_roles) == 0:
            continue
        if only_issues and not any(i.get("level") != "info" for i in issues_by_node.get(js_string(node.get("id")), [])):
            continue
        if only_wait and not (is_wait_node(node) if is_wait_node else False):  # lint: ignore
            continue
        if terms:
            hay = "\n".join([js_string(node.get("id")), _or(d.get("description"), ""),
                             *[js_string(r.get("name")) for r in node_roles]]).lower()
            if not all(t in hay for t in terms):
                continue
        out.append((node, index))
    return out


def is_wait_node(node, schema, defaults) -> bool:
    return bool(schema) and bool(_sgs.get_setting_value(_sgs.get_node_setting(node, schema, defaults),
                                                        _sgs.IS_WAIT_KEY_FIELD, False))


def nav_list(visible, is_sub):
    """データ入力の「前へ/次へ」の順序 (サブグループ内で Role を持つ表示中ノードの id)。"""
    return [n.get("id") for n, _ in visible if len(_data(n).get("roles") or []) > 0] if is_sub else []


def navigate_target(nav_ids, node_id, direction):
    if node_id not in nav_ids:
        return None
    i = nav_ids.index(node_id) + (1 if direction == "next" else -1)
    return nav_ids[i] if 0 <= i < len(nav_ids) else None


def split_description_first_line(description, limit=24):
    return js_string(description).split("\n")[0][:limit]


# ============================================================
# Undo / Redo
# ============================================================
class History:
    """タブごとに最大 50 件まで遡れる履歴 (スナップショットは不変更新で共有構造)。"""

    MAX = 50
    COALESCE_MS = 400

    def __init__(self, clock=None):
        self._h = {}
        self._clock = clock or (lambda: int(time.time() * 1000))

    def _get(self, tab_id):
        return self._h.get(tab_id)

    def push(self, tab_id, snap):
        if snap is None:
            return
        h = self._h.get(tab_id)
        if h is None:
            h = {"undo": [], "redo": [], "at": 0}
            self._h[tab_id] = h
        now = self._clock()
        if len(h["undo"]) > 0 and now - h["at"] < self.COALESCE_MS:
            h["at"] = now
            return
        if h["undo"] and h["undo"][-1] is snap:
            return
        h["undo"].append(snap)
        if len(h["undo"]) > self.MAX:
            h["undo"].pop(0)
        h["redo"] = []
        h["at"] = now

    def counts(self, tab_id):
        h = self._h.get(tab_id)
        return (len(h["undo"]), len(h["redo"])) if h else (0, 0)

    def apply(self, tab_id, direction, current):
        """direction: 'undo' | 'redo'。戻す先のスナップショット(無ければ None)。current は戻す前の内容。"""
        h = self._h.get(tab_id)
        if not h:
            return None
        src, dst = (h["undo"], h["redo"]) if direction == "undo" else (h["redo"], h["undo"])
        if not src:
            return None
        target = src.pop()
        if current is not None:
            dst.append(current)
        h["at"] = 0
        return target

    def clear(self, tab_id=None):
        if tab_id is None:
            self._h.clear()
        else:
            self._h.pop(tab_id, None)


# ============================================================
# 保存の排他制御 / リビジョン監視
# ============================================================
class SaveCoordinator:
    """performSave の状態管理。実際の通信は呼び出し側 (UI) がやる。

        if sc.begin(tab_id): ...送信...; next_tab = sc.finish(ok)   # next_tab があれば続けて begin する
    """

    def __init__(self):
        self.status = "saved"       # 'saved' | 'dirty' | 'saving' | 'error'
        self.loaded = set()         # 読み込み完了済みタブ (未完了は保存しない)
        self.saving = False
        self.pending = None
        self.dirty = False

    def mark_loaded(self, tab_id):
        self.loaded.add(tab_id)

    def mark_unloaded(self, tab_id):
        self.loaded.discard(tab_id)

    def mark_dirty(self):
        self.dirty = True
        if self.status != "saving":
            self.status = "dirty"

    def begin(self, tab_id) -> bool:
        if not tab_id or tab_id not in self.loaded:
            return False
        if self.saving:
            self.pending = tab_id
            return False
        self.saving = True
        self.dirty = False
        self.status = "saving"
        return True

    def finish(self, ok: bool):
        """-> 続けて保存すべきタブ (保存中に来た要求)。無ければ None。"""
        self.saving = False
        self.status = ("dirty" if self.dirty else "saved") if ok else "error"
        nxt, self.pending = self.pending, None
        return nxt

    def should_confirm_leave(self) -> bool:
        return self.status != "saved"


class RevTracker:
    """他のタブ/ユーザーによる更新の検知 (X-Sub-Rev / GET .../rev)。"""

    def __init__(self):
        self.known = None
        self.external = None

    def note(self, rev):
        if rev:
            self.known = rev

    def should_check(self, hidden=False, saving=False) -> bool:
        return bool(self.known) and not hidden and not saving

    def observe(self, server_rev, saving=False) -> bool:
        """サーバーの rev を見て、外部更新があれば True (external に記録)。"""
        if server_rev and server_rev != self.known and not saving:
            self.external = server_rev
            return True
        return False

    def ignore_external(self):
        if self.external:
            self.known = self.external
        self.external = None


# ============================================================
# Drawer 入力中の値 (draft) / キャッシュ
# ============================================================
class RoleDataDrafts:
    """roleDataDraftRef / roleDataCache。キーは nodePath (階層込み)。"""

    def __init__(self):
        self.draft = {}
        self.cache = {}

    def update(self, node_path, new_state: dict):
        self.draft[node_path] = {**self.draft.get(node_path, {}), **new_state}

    def flush(self, node_path):
        d = self.draft.pop(node_path, None)
        if d:
            self.cache[node_path] = {**self.cache.get(node_path, {}), **d}

    def after_save(self, node_path, by_uid: dict, items):
        """保存成功後: キャッシュを更新し、保存した内容と同じ draft は破棄(その後さらに編集された分は残す)。"""
        self.cache[node_path] = {**self.cache.get(node_path, {}), **by_uid}
        d = self.draft.get(node_path)
        if d:
            for it in items:
                k = js_string(it["uniqueId"])
                if k in d and js_json_stringify(d[k]) == js_json_stringify(it["formData"]):
                    del d[k]

    def reset(self):
        self.draft = {}
        self.cache = {}

    def initial_for_drawer(self, roles, node_path):
        """データ入力 Drawer を開く時の初期値 {uniqueId: formData}。"""
        cache = self.cache.get(node_path) or {}
        init = {}
        for r in roles:
            k = js_string(r.get("uniqueId"))
            v = cache.get(k)
            init[k] = v if js_truthy(v) else _or(r.get("data"), [])
        return init
