"""シナリオイベント一覧 (ScenarioEventGrid.js の純粋ロジック, Qt 非依存)。"""
from __future__ import annotations

import re


def _parse_int(s):
    m = re.match(r"\s*([+-]?\d+)", str(s))
    return int(m.group(1)) if m else None


def next_event_id(events) -> str:
    """既存の数値IDの最大値+1 (無ければ '1')。"""
    nums = [n for n in (_parse_int(e.get("id")) for e in events) if n is not None]
    return str(max(nums) + 1) if nums else "1"


def filter_events(events, text) -> list:
    q = (text or "").strip().lower()
    if not q:
        return list(events)
    out = []
    for e in events:
        if (str(e.get("id", "")).lower().find(q) >= 0 or str(e.get("name", "")).lower().find(q) >= 0
                or any(q in str(s.get("name", "")).lower() for s in e.get("subEvents") or [])):
            out.append(e)
    return out


def add_event(events, ev) -> list:
    return [*events, {**ev, "subEvents": ev.get("subEvents", [])}]


def edit_event(events, event_id, name, description) -> list:
    return [{**e, "name": name, "description": description} if e.get("id") == event_id else e for e in events]


def delete_event(events, event_id) -> list:
    return [e for e in events if e.get("id") != event_id]


def add_sub(events, event_id, sub) -> list:
    return [{**e, "subEvents": [*(e.get("subEvents") or []), sub]} if e.get("id") == event_id else e for e in events]


def edit_sub(events, event_id, sub_id, name, description) -> list:
    return [{**e, "subEvents": [{**s, "name": name, "description": description} if s.get("subId") == sub_id else s
                                for s in e.get("subEvents") or []]} if e.get("id") == event_id else e for e in events]


def delete_sub(events, event_id, sub_id) -> list:
    return [{**e, "subEvents": [s for s in e.get("subEvents") or [] if s.get("subId") != sub_id]} if e.get("id") == event_id else e
            for e in events]


def migrate_message(result) -> tuple:
    """-> (message, level)"""
    migrated = len((result or {}).get("migrated") or [])
    failed = len((result or {}).get("failed") or [])
    if failed > 0:
        return f"更新完了: {migrated}件更新（{failed}件失敗。詳細はサーバーログを確認してください）", "warning"
    if migrated > 0:
        return f"{migrated}件のイベントを新しい形式に更新しました", "success"
    return "更新が必要なイベントはありませんでした（すでに最新形式です）", "success"
