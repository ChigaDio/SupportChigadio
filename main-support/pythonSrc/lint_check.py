# -*- coding: utf-8 -*-
"""
pythonSrc/lint_check.py

プロジェクト全体のデータ整合性を一括スキャンし、C#生成前に問題を検出する
「データLint」機能。/workspace や各Gridから個別に気づくのではなく、
1画面でまとめて確認できるようにする。

検出する項目:
1. 命名規則違反   : 各カテゴリのアイテム名（フォルダ名）が有効なC#識別子
                     として使えるか（空白/記号/数字始まり/C#予約語は不可）
2. ID重複・名前重複: 各カテゴリの一覧ファイル(*_list.json)内でid/nameが
                     重複していないか
3. 必須フィールド未入力: フィールド定義にname/typeが未設定
4. 孤立参照       : フィールドのtypeが、実在するどのカテゴリの型にも
                     一致しない（basic/unity/custom値型を除く）。
                     reference_check.py の逆方向のチェックにあたる
                     （reference_check=削除前に「誰が参照しているか」、
                     lint_check=既存データに「参照先が実在しない」箇所が
                     無いか）。

reference_check.py と同じ「フィールド=dict、'type'キーに型名文字列
（配列は'[]'サフィックス）」という規約に基づく汎用スキャン方式を採用して
おり、個々のカテゴリのスキーマを厳密に再現する必要がない。
このため、'type'というキー名が偶然一致するだけの無関係なフィールドを
拾ってしまう可能性はあるが、あくまで生成前の「気づき」を与える機能で
あり、多少の過検出は実害が小さいため許容している。
"""
import json
import os
import re

from pythonSrc.reference_check import CATEGORY_DIRS, _iter_json_files, _strip_array_suffix
import pythonSrc.reference_check as reference_check

DATA_DIR = None

_CS_KEYWORDS = {
    'abstract', 'as', 'base', 'bool', 'break', 'byte', 'case', 'catch', 'char', 'checked',
    'class', 'const', 'continue', 'decimal', 'default', 'delegate', 'do', 'double', 'else',
    'enum', 'event', 'explicit', 'extern', 'false', 'finally', 'fixed', 'float', 'for',
    'foreach', 'goto', 'if', 'implicit', 'in', 'int', 'interface', 'internal', 'is', 'lock',
    'long', 'namespace', 'new', 'null', 'object', 'operator', 'out', 'override', 'params',
    'private', 'protected', 'public', 'readonly', 'ref', 'return', 'sbyte', 'sealed',
    'short', 'sizeof', 'stackalloc', 'static', 'string', 'struct', 'switch', 'this', 'throw',
    'true', 'try', 'typeof', 'uint', 'ulong', 'unchecked', 'unsafe', 'ushort', 'using',
    'virtual', 'void', 'volatile', 'while',
}
_VALID_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

_BASIC_TYPES = {
    'int', 'uint', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long',
    'decimal', 'object',
}
_UNITY_TYPES = {
    'GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion',
    'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite',
    'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject',
}
# CustomClassData系の値型（bit/color/bezier）とDictionary表現
_CUSTOM_VALUE_TYPES = {'bit', 'color', 'bezier', 'dictionary'}


def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    # _iter_json_files() は reference_check モジュール側のグローバルDATA_DIRを
    # 参照するため、こちらの初期化と合わせて確実に設定しておく。
    reference_check.init(data_dir)


def _is_valid_identifier(name):
    return bool(name) and bool(_VALID_IDENTIFIER_RE.match(name)) and name not in _CS_KEYWORDS


def _known_names():
    """DATA_DIR配下の各カテゴリフォルダの直下サブフォルダ名を、そのカテゴリに
    実在する型名の一覧とみなす（フォルダ名=アイテム名、という規約に依拠）。"""
    known = set()
    if DATA_DIR is None:
        return known
    for dir_parts in CATEGORY_DIRS.values():
        base = os.path.join(DATA_DIR, *dir_parts)
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            if os.path.isdir(os.path.join(base, entry)):
                known.add(entry)
    return known


def _iter_list_files():
    if DATA_DIR is None:
        return
    for root, dirs, files in os.walk(DATA_DIR):
        rel = os.path.relpath(root, DATA_DIR)
        rel_parts = [] if rel == "." else rel.replace("\\", "/").split("/")
        if rel_parts and rel_parts[0] in {"logs", "app_meta", "announcements"}:
            dirs[:] = []
            continue
        for fname in files:
            if fname.endswith("_list.json"):
                yield os.path.join(root, fname)


def _add(issues, severity, issue_type, category, name, message):
    issues.append({
        "severity": severity,
        "type": issue_type,
        "category": category or "",
        "name": name or "",
        "message": message,
    })


def _check_naming(issues):
    for category, dir_parts in CATEGORY_DIRS.items():
        base = os.path.join(DATA_DIR, *dir_parts)
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            if not os.path.isdir(os.path.join(base, entry)):
                continue
            if not _is_valid_identifier(entry):
                _add(issues, "error", "naming", category, entry,
                     f"名前 '{entry}' は有効なC#識別子として使用できません"
                     "（空白・記号・数字始まり・C#予約語は不可）")


def _check_duplicates(issues):
    for path in _iter_list_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, list):
            continue
        rel = os.path.relpath(path, DATA_DIR).replace("\\", "/")
        category = rel.split("/")[0]

        seen_ids = {}
        seen_names = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            item_name = item.get("name")
            if item_id is not None:
                seen_ids.setdefault(item_id, []).append(item_name or "?")
            if item_name:
                seen_names.setdefault(item_name, 0)
                seen_names[item_name] += 1

        for id_val, names in seen_ids.items():
            if len(names) > 1:
                _add(issues, "error", "duplicate_id", category, ", ".join(names),
                     f"ID {id_val} が {rel} 内で重複しています（対象: {', '.join(names)}）")
        for name_val, count in seen_names.items():
            if count > 1:
                _add(issues, "error", "duplicate_name", category, name_val,
                     f"名前 '{name_val}' が {rel} 内で {count} 回重複しています")


def _walk_fields(node, category, rel_path, issues, all_known_types):
    if isinstance(node, dict):
        if "type" in node:
            type_val = node.get("type")
            name_val = node.get("name") or node.get("property")
            if not name_val:
                _add(issues, "warning", "missing_field", category, rel_path,
                     f"type='{type_val}' のフィールドに name が設定されていません（{rel_path}）")
            if type_val in (None, ""):
                _add(issues, "warning", "missing_field", category, name_val or rel_path,
                     f"フィールド '{name_val}' に type が設定されていません（{rel_path}）")
            elif isinstance(type_val, str):
                base_type = _strip_array_suffix(type_val)
                if base_type not in all_known_types:
                    _add(issues, "error", "orphan_reference", category, name_val or rel_path,
                         f"フィールド '{name_val}' の型 '{type_val}' は、"
                         f"どのカテゴリにも実在しません（孤立参照・{rel_path}）")
        for v in node.values():
            _walk_fields(v, category, rel_path, issues, all_known_types)
    elif isinstance(node, list):
        for item in node:
            _walk_fields(item, category, rel_path, issues, all_known_types)


def _check_fields(issues):
    all_known_types = _BASIC_TYPES | _UNITY_TYPES | _CUSTOM_VALUE_TYPES | _known_names()
    for path in _iter_json_files():
        rel = os.path.relpath(path, DATA_DIR).replace("\\", "/")
        category = rel.split("/")[0]
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        _walk_fields(data, category, rel, issues, all_known_types)


def run_lint():
    if DATA_DIR is None:
        return []
    issues = []
    _check_naming(issues)
    _check_duplicates(issues)
    _check_fields(issues)
    # エラー優先、カテゴリ/名前順で安定ソート
    severity_order = {"error": 0, "warning": 1}
    issues.sort(key=lambda i: (severity_order.get(i["severity"], 9), i["category"], i["name"]))
    return issues


def register(app, data_dir):
    from flask import jsonify
    init(data_dir)

    @app.route("/api/lint-check", methods=["GET"])
    def lint_check():
        issues = run_lint()
        counts = {"error": 0, "warning": 0}
        for issue in issues:
            counts[issue["severity"]] = counts.get(issue["severity"], 0) + 1
        return jsonify({"issues": issues, "counts": counts, "total": len(issues)})
