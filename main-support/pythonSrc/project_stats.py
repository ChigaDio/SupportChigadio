# -*- coding: utf-8 -*-
"""
pythonSrc/project_stats.py

プロジェクト全体の規模感（クラスデータ数・シナリオイベント数・State数など）
をカテゴリ別に集計し、ダッシュボードで可視化するための統計API。

reference_check.py の CATEGORY_DIRS（1フォルダ=1アイテムの規約に従う
カテゴリ）をそのまま再利用し、それ以外の特殊な格納形式を持つカテゴリ
（ScenarioEvent・Animator・Sound/Texture/GameObject/Material等のAssets・
お知らせ）は個別に集計関数を用意している。
"""
import json
import os

from pythonSrc.reference_check import CATEGORY_DIRS

DATA_DIR = None

_FOLDER_CATEGORY_LABELS = {
    "enum": "Enum",
    "class_data": "ClassData",
    "class_data_id": "ClassDataID",
    "custom_class_data": "CustomClassData",
    "custom_class_data_id": "CustomClassDataID",
    "class_data_matrix_id": "ClassDataMatrixID",
    "state_data": "State",
    "behavior_data": "Behavior",
    "scenario_role": "ScenarioRole",
    "save_data": "SaveData",
    "const_class_data": "ConstClassData",
}


def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir


def _count_subdirs(dir_parts):
    base = os.path.join(DATA_DIR, *dir_parts)
    if not os.path.isdir(base):
        return 0
    return sum(1 for e in os.listdir(base) if os.path.isdir(os.path.join(base, e)))


def _count_scenario_event():
    base = os.path.join(DATA_DIR, "scenario_data", "scenario_event_data")
    list_path = os.path.join(base, "scenario_event_list.json")
    if os.path.isfile(list_path):
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
        except (json.JSONDecodeError, OSError):
            pass
    return _count_subdirs(("scenario_data", "scenario_event_data"))


def _count_animator_data():
    return _count_subdirs(("assets_data", "anim_data"))


def _count_asset_items(rel_parts):
    """groups: { groupName: { items: [...], subgroups: [...] } } 形式の
    アセットJSON(sound/texture/gameobject/material)から、全グループの
    itemsを合計した件数を返す。"""
    path = os.path.join(DATA_DIR, *rel_parts)
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0
    groups = data.get("groups", {}) if isinstance(data, dict) else {}
    return sum(len(g.get("items", [])) for g in groups.values() if isinstance(g, dict))


def _count_announcements():
    base = os.path.join(DATA_DIR, "announcements")
    if not os.path.isdir(base):
        return 0
    return sum(1 for f in os.listdir(base) if f.endswith(".md"))


def collect_stats():
    if DATA_DIR is None:
        return {"categories": [], "totals": {"totalItems": 0, "categoryCount": 0}}

    categories = []
    for category, dir_parts in CATEGORY_DIRS.items():
        label = _FOLDER_CATEGORY_LABELS.get(category, category)
        categories.append({"id": category, "label": label, "count": _count_subdirs(dir_parts)})

    categories.append({"id": "scenario_event", "label": "ScenarioEvent", "count": _count_scenario_event()})
    categories.append({"id": "animator_data", "label": "Animator", "count": _count_animator_data()})
    categories.append({"id": "sound", "label": "Sound",
                        "count": _count_asset_items(("assets_data", "sound", "assets_sound.json"))})
    categories.append({"id": "texture", "label": "Texture",
                        "count": _count_asset_items(("assets_data", "texture", "assets_texture.json"))})
    categories.append({"id": "gameobject", "label": "GameObject",
                        "count": _count_asset_items(("assets_data", "gameobject", "assets_gameobject.json"))})
    categories.append({"id": "material", "label": "Material",
                        "count": _count_asset_items(("assets_data", "material", "assets_material.json"))})
    categories.append({"id": "announcements", "label": "お知らせ", "count": _count_announcements()})

    categories.sort(key=lambda c: c["count"], reverse=True)
    total_items = sum(c["count"] for c in categories)

    return {
        "categories": categories,
        "totals": {
            "totalItems": total_items,
            "categoryCount": sum(1 for c in categories if c["count"] > 0),
        },
    }


def register(app, data_dir):
    from flask import jsonify
    init(data_dir)

    @app.route("/api/project-stats", methods=["GET"])
    def project_stats():
        return jsonify(collect_stats())
