"""DSL(テキスト)を適用する前に見せる「変更内容の差分」 (Qt 非依存)。

`js_ref/src/scenarioDiff.js` の移植。

対応表 (JS -> Python):
    formatValue -> format_value
    diffRoles   -> diff_roles

JS の `undefined` (フィールド自体が無い) と `null` は差分の判定で区別される(`stable` が 'undefined' / 'null' を返す)ので、
このモジュールだけは未設定を表す番兵 `UNDEFINED` を使う。`diff_roles` の結果の changed[].fields[].from/to に
入ることがあり、`format_value(UNDEFINED)` は '(未設定)' を返す。
"""
from __future__ import annotations

from .dsl import js_json_stringify, js_number_to_string, js_string


class _Undefined:
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "UNDEFINED"

    def __bool__(self):
        return False


UNDEFINED = _Undefined()


def stable(v) -> str:
    """順序に依存しない比較用の文字列化 (JS の stable と同じ)。"""
    if v is UNDEFINED:
        return "undefined"
    if v is None or not isinstance(v, (dict, list, tuple)):
        return js_json_stringify(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(stable(e) for e in v) + "]"
    # キーは UTF-16 コード単位順 (JS の既定 sort)。BMP 内なら文字コード順と一致する。
    keys = sorted(v.keys(), key=lambda k: k.encode("utf-16-be"))
    return "{" + ",".join(f"{js_json_stringify(k)}:{stable(v[k])}" for k in keys) + "}"


def _strict_eq(a, b) -> bool:
    """JS の === (True と 1 を区別する。int と float は同じ number)。"""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _to_map(data) -> dict:
    m: dict = {}
    for d in (data if isinstance(data, list) else []):
        if isinstance(d, dict) and "name" in d:
            m[d["name"]] = d.get("value", UNDEFINED)
    return m


def _u16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _u16_slice(s: str, end: int) -> str:
    return s.encode("utf-16-le")[: end * 2].decode("utf-16-le", errors="surrogatepass")


def format_value(v, max_len: int = 60) -> str:
    """値を、差分表示用の短い文字列にする。"""
    if v is UNDEFINED:
        return "(未設定)"
    if isinstance(v, str):
        s = f'"{v}"'
    elif isinstance(v, (dict, list)):
        s = js_json_stringify(v)
    elif v is None:
        s = "null"
    elif isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = js_number_to_string(v)
    else:
        s = js_string(v)
    return s if _u16_len(s) <= max_len else _u16_slice(s, max_len - 1) + "…"


def diff_roles(before, after) -> dict:
    """
    before: 現在のRole [{uniqueId, name, data: [{name, value}]}] / after: DSLをコンパイルした結果
    戻り値: {added, removed, changed, unchangedCount, reordered, totalChanges}
      added   : [{uniqueId, name, fields: [{name, value}]}]
      removed : [{uniqueId, name}]
      changed : [{uniqueId, name, renamedFrom, fields: [{name, from, to}]}]
    """
    before_list = before if isinstance(before, list) else []
    after_list = after if isinstance(after, list) else []
    before_by_id = {js_string(r.get("uniqueId")): r for r in before_list}
    after_ids = {js_string(r.get("uniqueId")) for r in after_list}

    added = []
    changed = []
    unchanged = 0

    for r in after_list:
        prev = before_by_id.get(js_string(r.get("uniqueId")))
        if prev is None:
            added.append({
                "uniqueId": r.get("uniqueId"), "name": r.get("name"),
                "fields": [{"name": d.get("name"), "value": d.get("value", UNDEFINED)} for d in (r.get("data") or [])],
            })
            continue
        a = _to_map(prev.get("data"))
        b = _to_map(r.get("data"))
        names = list(dict.fromkeys(list(a.keys()) + list(b.keys())))
        fields = []
        for n in names:
            av = a.get(n, UNDEFINED)
            bv = b.get(n, UNDEFINED)
            if stable(av) != stable(bv):
                fields.append({"name": n, "from": av, "to": bv})
        if len(fields) > 0 or not _strict_eq(prev.get("name"), r.get("name")):
            changed.append({"uniqueId": r.get("uniqueId"), "name": r.get("name"),
                            "renamedFrom": prev.get("name") if not _strict_eq(prev.get("name"), r.get("name")) else None,
                            "fields": fields})
        else:
            unchanged += 1

    removed = [{"uniqueId": r.get("uniqueId"), "name": r.get("name")}
               for r in before_list if js_string(r.get("uniqueId")) not in after_ids]

    kept_before = [js_string(r.get("uniqueId")) for r in before_list if js_string(r.get("uniqueId")) in after_ids]
    kept_after = [js_string(r.get("uniqueId")) for r in after_list if js_string(r.get("uniqueId")) in before_by_id]
    reordered = "\u0000".join(kept_before) != "\u0000".join(kept_after)

    return {
        "added": added, "removed": removed, "changed": changed, "unchangedCount": unchanged, "reordered": reordered,
        "totalChanges": len(added) + len(removed) + len(changed) + (1 if reordered else 0),
    }
