"""物語設定 (ScenarioStorySettingGrid.js の純粋ロジック, Qt 非依存)。"""
from __future__ import annotations

KIND_DEFS = {
    "img": {"prefix": "img", "label": "画像(Texture)"},
    "se": {"prefix": "sound_se", "label": "SE"},
    "bgm": {"prefix": "sound_bgm", "label": "BGM"},
    "effect": {"prefix": "effect", "label": "エフェクト(GameObject)"},
}
KIND_ORDER = ["img", "se", "bgm", "effect"]


def flatten_asset_groups(groups, filter_fn=None) -> list:
    out = []
    for group_name, group_value in (groups or {}).items():
        for item in (group_value or {}).get("items") or []:
            if filter_fn and not filter_fn(item):
                continue
            out.append({"group": group_name, **item})
    return out


def option_label(opt) -> str:
    sub = f'{opt["subgroup"]} / ' if opt.get("subgroup") else ""
    return f'{opt.get("group")} / {sub}{opt.get("name")}'


def build_options(texture_data, sound_data, gameobject_data) -> dict:
    """-> {img, se, bgm, effect, voiceSeries}"""
    tex = flatten_asset_groups((texture_data or {}).get("groups"))
    snd_groups = (sound_data or {}).get("groups")
    eff = flatten_asset_groups((gameobject_data or {}).get("groups"))
    series, order = {}, []
    for it in flatten_asset_groups(snd_groups, lambda i: i.get("type") == "VOICE"):
        if not it.get("subgroup"):
            continue
        key = f'{it["group"]}::{it["subgroup"]}'
        if key not in series:
            series[key] = {"group": it["group"], "subGroup": it["subgroup"], "count": 0}
            order.append(key)
        series[key]["count"] += 1
    return {"img": tex,
            "se": flatten_asset_groups(snd_groups, lambda i: i.get("type") == "SE"),
            "bgm": flatten_asset_groups(snd_groups, lambda i: i.get("type") == "BGM"),
            "effect": eff,
            "voiceSeries": [series[k] for k in order]}


def voice_series_label(o) -> str:
    return f'Sound_{o["group"]}_{o["subGroup"]}（VOICE {o["count"]}件）'


def used_slot_names(slots, prefix) -> set:
    return {s["slot"] for s in slots if str(s.get("slot", "")).startswith(f"{prefix}_")}


def available_slot_names(slot_defs, slots, kind) -> list:
    prefix = KIND_DEFS[kind]["prefix"]
    d = next((x for x in slot_defs if x.get("prefix") == prefix), None)
    if not d:
        return []
    used = used_slot_names(slots, prefix)
    return [n for n in d.get("names") or [] if n not in used]


def slots_for_kind(slots, kind) -> list:
    return [s for s in slots if s.get("kind") == kind]


def add_slot(slots, kind, slot_name, asset, sprite_name=None, retain=False) -> list:
    if not slot_name or not asset:
        return slots
    row = {"slot": slot_name, "kind": kind, "group": asset.get("group"), "subGroup": asset.get("subgroup") or None,
           "id": asset.get("name")}
    if kind == "img":
        row["spriteName"] = sprite_name or None
    row["retain"] = bool(retain)
    return [*slots, row]


def remove_slot(slots, slot_name) -> list:
    return [s for s in slots if s.get("slot") != slot_name]


def toggle_retain(slots, slot_name) -> list:
    return [{**s, "retain": not s.get("retain")} if s.get("slot") == slot_name else s for s in slots]


def slot_summary(s) -> str:
    sp = f' (Sprite: {s["spriteName"]})' if s.get("spriteName") else ""
    return f'{s.get("group")} / {s.get("id")}{sp}'


def select_voice_series(current, option):
    """Autocomplete 選択。None でクリア。retain は現在値を引き継ぐ。"""
    if not option:
        return None
    return {"group": option["group"], "subGroup": option["subGroup"], "retain": bool((current or {}).get("retain"))}


def set_voice_retain(current, retain):
    return {**current, "retain": bool(retain)} if current else None


def find_voice_option(current, options):
    if not current:
        return None
    return next((o for o in options if o["group"] == current.get("group") and o["subGroup"] == current.get("subGroup")), None)


def save_body(slots, voice_series_id) -> dict:
    return {"slots": slots, "voiceSeriesId": voice_series_id}
