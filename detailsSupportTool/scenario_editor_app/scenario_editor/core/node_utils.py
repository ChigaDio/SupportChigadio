"""ノード配列に対する整理系の処理 (Qt 非依存)。

`js_ref/src/scenarioNodeUtils.js` の移植。

対応表 (JS -> Python):
    renumberDuplicateNodes -> renumber_duplicate_node (複数形: renumber_duplicate_nodes)

規約は docs/ARCHITECTURE.md のとおり。JS の undefined/null は None。
JS のオブジェクトは配列インデックス風のキー("1","10"...)が先に昇順で並ぶため、
`data.subgroups` を組み替えるときは同じ並びにする。
"""
from __future__ import annotations

import re

from .dsl import _order_keys, js_number_to_string, js_string

_NUMERIC_ID_RE = re.compile(r"[0-9]+\Z")


def _is_numeric_id(id_) -> bool:
    return bool(_NUMERIC_ID_RE.match(js_string(id_)))


def _js_number(digits: str):
    v = int(digits)
    return v if v < 2 ** 53 else float(digits)


def renumber_duplicate_nodes(nodes, rekey_subgroups: bool = False) -> dict:
    """同じ配列内でIDが重複しているノードのうち、2番目以降に新しい未使用IDを割り当てる。

    - 最初に現れたノードのIDはそのまま。
    - 新IDは「重複しているIDより大きい、最小の未使用の整数」。
    - 数値でないIDは対象外 (skipped に入る)。
    - rekey_subgroups=True のとき、node["data"]["subgroups"] が自分自身のIDをキーに持っていれば新IDのキーへ付け替える。

    戻り値: {"nodes", "renamed": [{index, from, to}], "skipped": [id...]}
    (変更が無ければ nodes は **同じ参照**)。入力の dict は変更しない。
    """
    lst = nodes if nodes is not None else []
    used = {js_string(n.get("id")) for n in lst}
    seen = set()
    renamed = []
    skipped = []
    out = []
    for index, node in enumerate(lst):
        id_ = js_string(node.get("id"))
        if id_ not in seen:
            seen.add(id_)
            out.append(node)
            continue
        if not _is_numeric_id(id_):
            if id_ not in skipped:
                skipped.append(id_)
            out.append(node)
            continue
        # JS は Number (倍精度) で計算する。2**53 を超える巨大な数字列は精度が落ちる点まで合わせる
        n = _js_number(id_) + 1
        while js_number_to_string(n) in used:
            n += 1
        new_id = js_number_to_string(n)
        used.add(new_id)
        seen.add(new_id)
        renamed.append({"index": index, "from": id_, "to": new_id})
        data = node.get("data")
        if rekey_subgroups and isinstance(data, dict) and isinstance(data.get("subgroups"), dict) \
                and id_ in data["subgroups"]:
            sgs = data["subgroups"]
            moved = sgs[id_]
            rest = {k: v for k, v in sgs.items() if k != id_}
            rest[new_id] = moved
            data = {**data, "subgroups": _order_keys(rest)}
        new_node = {**node, "id": new_id}
        if "data" in node or data is not None:
            new_node["data"] = data
        out.append(new_node)
    return {"nodes": out if len(renamed) > 0 else lst, "renamed": renamed, "skipped": skipped}


# 規約どおりの機械変換名 (renumberDuplicateNodes -> renumber_duplicate_nodes) も公開する
renumber_duplicate_node = renumber_duplicate_nodes
