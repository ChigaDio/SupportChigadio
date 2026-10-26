"""シナリオの遷移グラフ(ノード/エッジ/Role)の整合性チェック (Qt 非依存)。

`js_ref/src/scenarioValidation.js` の移植。

対応表 (JS -> Python):
    worstLevel    -> worst_level
    validateGraph -> validate_graph

issue の code: non-numeric-id / dup-node-id / role-no-uid / dup-role-uid / role-undefined /
               role-fields-missing / role-fields-extra / empty-node / dangling-edge
level: 'error' | 'warn' | 'info'
"""
from __future__ import annotations

import re

from .diff import UNDEFINED
from .dsl import _order_keys, js_string

LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2}

_DIGITS_RE = re.compile(r"[0-9]+\Z")


def worst_level(issues):
    if not issues:
        return None
    w = "info"
    for i in issues:
        if LEVEL_ORDER[i["level"]] < LEVEL_ORDER[w]:
            w = i["level"]
    return w


def _count_inner_nodes(node) -> int:
    data = node.get("data") if isinstance(node, dict) else None
    sgs = (data.get("subgroups") if isinstance(data, dict) else None) or {}
    n = 0
    for sg in sgs.values():
        if isinstance(sg, dict) and sg.get("nodes"):
            n += len(sg["nodes"])
    return n


def _join5(names) -> str:
    # Array.prototype.join は undefined / null を空文字にする
    return ", ".join("" if (x is None or x is UNDEFINED) else js_string(x) for x in names[:5]) \
        + (" …" if len(names) > 5 else "")


def _name_of(d):
    """JS の `d && d.name`: d が falsy ならそれ自身、dict で name が無ければ undefined (UNDEFINED)。"""
    if isinstance(d, dict):
        return d["name"] if "name" in d else UNDEFINED
    if d is None or d is False or d == 0 or d == "":
        return d
    return UNDEFINED  # 文字列など truthy な非オブジェクトの .name は undefined


def _field_name(f):
    return f["name"] if isinstance(f, dict) and "name" in f else UNDEFINED


def validate_graph(nodes, edges, ctx=None) -> dict:
    """
    ctx: {"isSub": bool, "roleNames": set[str] | None, "roleSchemas": {roleName: {"fields": [{"name"}]}}}
    戻り値: {"byNode": {nodeId: [issue]}, "edgeIssues": [issue], "counts": {error,warn,info}, "total": int}
    """
    ctx = ctx or {}
    is_sub = ctx["isSub"] if "isSub" in ctx and ctx["isSub"] is not None else False
    role_names = ctx.get("roleNames")
    role_schemas = ctx["roleSchemas"] if "roleSchemas" in ctx and ctx["roleSchemas"] is not None else {}
    by_node: dict = {}

    def add(id_, level, code, message):
        by_node.setdefault(id_, []).append({"level": level, "code": code, "message": message})

    id_count: dict = {}
    for n in nodes:
        k = js_string(n.get("id"))
        id_count[k] = id_count.get(k, 0) + 1

    dup_reported = set()
    for n in nodes:
        id_ = js_string(n.get("id"))
        if id_count[id_] > 1 and id_ not in dup_reported:
            dup_reported.add(id_)
            add(id_, "error", "dup-node-id", f'ID "{id_}" が同じ階層で重複しています')
        if not _DIGITS_RE.match(id_):
            add(id_, "warn", "non-numeric-id", f'ID "{id_}" は数値ではないため、出力では 0 になります')

        data = n.get("data")
        roles = (data.get("roles") if isinstance(data, dict) else None) or []
        uid_count: dict = {}
        for r in roles:
            uid = r.get("uniqueId")
            if uid is None or uid == "":
                add(id_, "error", "role-no-uid", f'Role「{js_string(r.get("name"))}」に uniqueId がありません（データを保存できません）')
            else:
                k = js_string(uid)
                uid_count[k] = uid_count.get(k, 0) + 1
        for uid, c in uid_count.items():
            if c > 1:
                add(id_, "error", "dup-role-uid", f'uniqueId "{uid}" のRoleが {c} 件あります（保存時に取り違えます）')

        for r in roles:
            if role_names is not None and len(role_names) > 0 and r.get("name") not in role_names:
                add(id_, "error", "role-undefined", f'Role「{js_string(r.get("name"))}」の定義が見つかりません（削除された可能性）')
                continue
            schema = role_schemas.get(r.get("name"))
            if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
                continue
            have = list(dict.fromkeys(_name_of(d) for d in (r.get("data") or [])))
            want = list(dict.fromkeys(_field_name(f) for f in schema["fields"]))
            want_set = set(want)
            have_set = set(have)
            missing = [x for x in want if x not in have_set]
            extra = [x for x in have if x is not UNDEFINED and x not in want_set]
            if len(missing) > 0:
                add(id_, "info", "role-fields-missing", f'Role「{js_string(r.get("name"))}」に未保存のフィールド: {_join5(missing)}')
            if len(extra) > 0:
                add(id_, "info", "role-fields-extra", f'Role「{js_string(r.get("name"))}」に定義に無いフィールド: {_join5(extra)}')

        if len(roles) == 0 and (is_sub or _count_inner_nodes(n) == 0):
            add(id_, "info", "empty-node", "Roleがありません")

    id_set = {js_string(n.get("id")) for n in nodes}
    edge_issues = []
    for e in (edges or []):
        if js_string(e.get("source")) not in id_set or js_string(e.get("target")) not in id_set:
            edge_issues.append({"level": "warn", "code": "dangling-edge",
                                "message": f'接続 {js_string(e.get("source"))} → {js_string(e.get("target"))} の端が存在しません'})

    counts = {"error": 0, "warn": 0, "info": 0}
    for lst in by_node.values():
        for i in lst:
            counts[i["level"]] += 1
    for i in edge_issues:
        counts[i["level"]] += 1
    by_node = _order_keys(by_node)  # JS のオブジェクトは整数様のキーが先に昇順で並ぶ
    return {"byNode": by_node, "edgeIssues": edge_issues, "counts": counts,
            "total": counts["error"] + counts["warn"] + counts["info"]}
