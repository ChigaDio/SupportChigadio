# -*- coding: utf-8 -*-
"""
pythonSrc/reference_check.py

Enum / ClassData / ClassDataID / CustomClassData / CustomClassDataID /
StateData / BehaviorData / ScenarioRole など、「型」として他のデータから
参照されうるカテゴリを削除・リネームする前に、DATA_DIR配下の全JSONファイルを
横断的に走査し、その型名を参照しているフィールドが無いか警告するための
モジュール。

これまでは無警告で削除でき、生成後のC#コンパイルエラーで初めて気づく形に
なっていた問題への対策。

実装方針:
class_data / class_data_id / custom_class_data / custom_class_data_id /
scenario_role / matrix 等、フィールド定義のスキーマは実装ごとに微妙に異なるが、
共通して「フィールド1件 = dict、'type'キーに型名の文字列（配列の場合は
末尾に'[]'）を持つ」という規約になっている（write_binary_field等の
共通処理がこの規約に依存しているため）。
個々のスキーマを厳密に再現するのではなく、DATA_DIR配下の全JSONを再帰的に
辿って 'type' キーを持つdictを拾う汎用スキャナ方式にすることで、
今後カテゴリが増えても個別対応なしに追従できるようにしている。

トレードオフ: 'type' というキー名が偶然一致するだけの無関係なフィールド
（例: activity_logの'type'等、DATA_DIR外なので対象外だが、behavior_dataの
ノード種別'type':'action'/'condition' 等）を拾ってしまう可能性がある。
本機能はあくまで削除前の「警告」であり自動ブロックではないため、
多少の過検出（false positive）は安全側に倒れるだけで実害が小さい一方、
見逃し（false negative）はコンパイルエラーに直結するため、検出漏れの
少なさを優先している。
"""
import json
import os

DATA_DIR = None

# 探索対象から除外するトップレベルフォルダ
_EXCLUDE_TOP_DIRS = {"logs", "app_meta", "announcements"}
# 除外するファイル名（機微ファイル・一覧インデックスファイル等）
_EXCLUDE_FILENAMES = {"users.json", "local_settings.json"}
_EXCLUDE_SUFFIXES = ("_list.json",)

# カテゴリ名 -> DATA_DIRからの相対フォルダパス（タプル）。
# file_locator.py / download.py の分類と揃えている。
CATEGORY_DIRS = {
    "enum": ("enum",),
    "class_data": ("class_data",),
    "class_data_id": ("class_data_id",),
    "custom_class_data": ("custom_class_data",),
    "custom_class_data_id": ("custom_class_data_id",),
    "class_data_matrix_id": ("class_data_matrix_id",),
    "state_data": ("state_data",),
    "behavior_data": ("behavior_data",),
    "scenario_role": ("scenario_data", "scenario_role"),
    "save_data": ("save_data",),
    "const_class_data": ("const_class_data",),
}


def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir


def _iter_json_files():
    for root, dirs, files in os.walk(DATA_DIR):
        rel = os.path.relpath(root, DATA_DIR)
        rel_parts = [] if rel == "." else rel.replace("\\", "/").split("/")
        if rel_parts and rel_parts[0] in _EXCLUDE_TOP_DIRS:
            dirs[:] = []
            continue
        for fname in files:
            if not fname.endswith(".json"):
                continue
            if fname in _EXCLUDE_FILENAMES or fname.endswith(_EXCLUDE_SUFFIXES):
                continue
            yield os.path.join(root, fname)


def _category_and_name_from_path(path):
    rel = os.path.relpath(path, DATA_DIR).replace("\\", "/")
    parts = rel.split("/")
    for category, dir_parts in CATEGORY_DIRS.items():
        n = len(dir_parts)
        if tuple(parts[:n]) == dir_parts:
            name = parts[n] if len(parts) > n else None
            return category, name
    # 未知のフォルダ構成の場合は先頭2セグメントをそのまま使う（ベストエフォート）
    if len(parts) >= 2:
        return parts[0], parts[1]
    return (parts[0] if parts else None), None


def _strip_array_suffix(type_str):
    if isinstance(type_str, str) and type_str.endswith("[]"):
        return type_str[:-2]
    return type_str


def _walk(node, target_name, matches, file_category, file_name):
    if isinstance(node, dict):
        type_val = node.get("type")
        if isinstance(type_val, str) and _strip_array_suffix(type_val) == target_name:
            field_label = node.get("name") or node.get("property") or "(不明なフィールド)"
            matches.append((file_category, file_name, field_label))
        for v in node.values():
            _walk(v, target_name, matches, file_category, file_name)
    elif isinstance(node, list):
        for item in node:
            _walk(item, target_name, matches, file_category, file_name)


def find_references(target_category, target_name):
    """target_category/target_name という型を、DATA_DIR配下の他のどのデータ
    ファイルが参照しているかを横断的に走査して返す。自分自身のファイル
    （同一カテゴリ・同一名）は除外する。

    戻り値: [{"category": str, "name": str, "fields": [str, ...]}, ...]
    """
    if DATA_DIR is None or not target_name:
        return []
    matches = []
    for path in _iter_json_files():
        file_category, file_name = _category_and_name_from_path(path)
        if file_category == target_category and file_name == target_name:
            continue  # 自分自身は除外
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        _walk(data, target_name, matches, file_category, file_name)

    grouped = {}
    for category, name, field in matches:
        key = (category, name)
        if key not in grouped:
            grouped[key] = {"category": category, "name": name, "fields": []}
        if field not in grouped[key]["fields"]:
            grouped[key]["fields"].append(field)
    return sorted(grouped.values(), key=lambda g: (g["category"] or "", g["name"] or ""))


def register(app, data_dir):
    from flask import jsonify
    init(data_dir)

    @app.route("/api/reference-check/<category>/<path:name>", methods=["GET"])
    def reference_check(category, name):
        references = find_references(category, name)
        return jsonify({"references": references, "count": len(references)})
