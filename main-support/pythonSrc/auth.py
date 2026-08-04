# -*- coding: utf-8 -*-
"""
pythonSrc/auth.py

サーバーモード(`python app.py Server`)専用の認証・ロール(役職)・
編集権限モジュール。

役職:
- admin  : 全操作可能。ユーザー作成/役職変更/バージョン管理が可能。
- editor : 管理人が許可したカテゴリ(またはカテゴリ内の特定データ)のみ編集可能。
- viewer : 閲覧のみ。書き込み系(POST/PUT/PATCH/DELETE)は一切不可。

通常起動(`python app.py`)時は SERVER_MODE=False となり、
認証チェックは完全にスキップされ、これまで通り誰でも編集できる。
"""
import os
import json
import threading
import secrets
from datetime import datetime

from flask import request, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

import pythonSrc.activity_log as activity_log

_lock = threading.Lock()

USERS_FILE_NAME = "users.json"
DEFAULT_ADMIN_USERNAME = "root"
DEFAULT_ADMIN_PASSWORD = "root"

# URL prefix -> カテゴリ名 のマッピング。
# 長いプレフィックスから優先的にマッチさせるため、後段でソートする。
# (app.py および pythonSrc/class_data.py, class_data_id.py, matrix.py, state.py,
#  behavior_routes.py, customclassdata.py, debugcommand.py の全APIルートを網羅)
CATEGORY_ROUTE_PREFIXES = {
    # Enum
    "/api/enum-id": "enum",
    "/api/enum/": "enum",
    "/api/generate-enum/": "enum",
    "/api/generate-all-enums": "enum",

    # ConstClassData
    "/api/const-class-data": "const_class_data",
    "/api/generate-const-class/": "const_class_data",
    "/api/generate-all-const-class": "const_class_data",

    # ClassDataID（"class-data" より長いので先にマッチする）
    "/api/class-data-id-tags": "class_data_id",
    "/api/class-data-id": "class_data_id",
    "/api/generate-class-data-id/": "class_data_id",
    "/api/generate-binary/": "class_data_id",
    "/api/generate-all-binary-matrix": "class_data_matrix_id",  # matrix優先のため上で明示
    "/api/generate-all-binary": "class_data_id",
    "/api/generate-table-id": "class_data_id",
    "/api/generate-all-cs-header": "class_data_id",

    # ClassDataMatrixID
    "/api/class-data-matrix-id-tags": "class_data_matrix_id",
    "/api/class-data-matrix-id": "class_data_matrix_id",
    "/api/generate-class-data-matrix-id/": "class_data_matrix_id",
    "/api/generate-binary-matrix/": "class_data_matrix_id",
    "/api/generate-all-cs-matrix-header": "class_data_matrix_id",
    "/api/generate-matrix-table-id": "class_data_matrix_id",
    "/api/generate-class-data-memory-viewer": "class_data_matrix_id",

    # ClassData（末尾に短いプレフィックスとして配置）
    "/api/class-data": "class_data",
    "/api/generate-class/": "class_data",

    # CustomClassDataID
    "/api/custom-class-data-id-tags": "custom_class_data_id",
    "/api/custom-class-data-id": "custom_class_data_id",
    "/api/generate-custom-class-data-id/": "custom_class_data_id",
    "/api/generate-all-custom-binary": "custom_class_data_id",
    "/api/generate-custom-table-id": "custom_class_data_id",
    "/api/generate-custom-cs-header": "custom_class_data_id",

    # CustomClassData
    "/api/custom-class-data": "custom_class_data",
    "/api/generate-custom-class/": "custom_class_data",

    # State
    "/api/state-data": "state",
    "/api/generate-state/": "state",
    "/api/open-code/": "state",

    # Behavior
    "/api/behavior-data": "behavior",
    "/api/behavior-generate": "behavior",

    # Scenario
    "/api/scenario-role": "scenario_role",
    "/api/generate-scenario-role/": "scenario_role",
    "/api/scenario-event": "scenario_event",
    "/api/save-role-data/": "scenario_event",
    "/api/fix-all-events": "scenario_event",
    "/api/scenario-conditions": "scenario_conditions",

    # Assets
    "/api/sound": "assets_sound",
    "/api/texture": "assets_texture",
    "/api/gameobject": "assets_gameobject",
    "/api/material": "assets_material",
    "/api/scene": "assets_scene",

    # Animator
    "/api/animator-data": "animator",
    "/api/animator-create": "animator",
    "/api/generate-animator/": "animator",
    "/api/generate-all-animator": "animator",

    # SaveData
    "/api/save-data": "save_data",
    "/api/generate-save-data/": "save_data",

    # DebugCommand（Debugメニュー。既定では権限0。管理人が必要に応じ許可する）
    "/api/debug-command-full": "debug_command",
    "/api/debug-command": "debug_command",
    "/api/generate-debug-command/": "debug_command",
    "/api/generate-all-debug-command": "debug_command",
}
# 長いプレフィックス順に並び替え（"class-data-id" が "class-data" より先にマッチするように）
_SORTED_PREFIXES = sorted(CATEGORY_ROUTE_PREFIXES.keys(), key=len, reverse=True)

ALL_CATEGORIES = sorted(set(CATEGORY_ROUTE_PREFIXES.values()))

# 認証なしでアクセスできるAPI（ログイン画面表示のため）
PUBLIC_API_PATHS = {"/api/login", "/api/server-config"}

_DATA_DIR = None
_SERVER_MODE = False


def resolve_category_and_item(path):
    """リクエストパスから (category, item名) を推定する。"""
    for prefix in _SORTED_PREFIXES:
        if path.startswith(prefix):
            category = CATEGORY_ROUTE_PREFIXES[prefix]
            remainder = path[len(prefix):].strip("/")
            item = None
            if remainder:
                # 例: /api/class-data-id/PlayerParam/tag -> PlayerParam
                item = remainder.split("/")[0]
                try:
                    from urllib.parse import unquote
                    item = unquote(item)
                except Exception:
                    pass
            return category, item
    return None, None


def _resolve_item_with_body(category, item):
    """作成/削除系のAPIはアイテム名がURLではなくJSONボディの `name` に入っていることが
    多い（本プロジェクトの既存フロントエンドの規約）ため、URLから取れない場合は
    ボディも見る。"""
    if item is not None or category is None:
        return item
    try:
        body = request.get_json(silent=True) or {}
        return body.get("name")
    except Exception:
        return None


def _users_path():
    return os.path.join(_DATA_DIR, USERS_FILE_NAME)


def _default_permissions():
    return {cat: {"all": False, "items": []} for cat in ALL_CATEGORIES}


def _load_users_raw():
    path = _users_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_users_raw(users):
    with _lock:
        with open(_users_path(), "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)


def _ensure_default_admin():
    users = _load_users_raw()
    if not users:
        admin = {
            "id": 1,
            "username": DEFAULT_ADMIN_USERNAME,
            "password_hash": generate_password_hash(DEFAULT_ADMIN_PASSWORD),
            "role": "admin",
            "permissions": _default_permissions(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        _save_users_raw([admin])


LOCAL_SETTINGS_FILE = "local_settings.json"


def _local_settings_path():
    return os.path.join(_DATA_DIR, LOCAL_SETTINGS_FILE)


def _load_local_settings():
    path = _local_settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_local_settings(settings):
    with _lock:
        with open(_local_settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


def _public_user(u):
    return {
        "id": u["id"],
        "username": u["username"],
        "role": u["role"],
        "permissions": u.get("permissions", _default_permissions()),
        "download_path": u.get("download_path"),
    }


def find_user_by_username(username):
    for u in _load_users_raw():
        if u["username"] == username:
            return u
    return None


def find_user_by_id(user_id):
    for u in _load_users_raw():
        if u["id"] == user_id:
            return u
    return None


def current_user():
    """現在ログイン中のユーザー(公開情報のみ)。未ログイン/非サーバーモードならNone。"""
    if not _SERVER_MODE:
        local = _load_local_settings()
        return {
            "id": 0,
            "username": local.get("username", "local"),
            "role": "admin",
            "permissions": _default_permissions(),
            "download_path": local.get("download_path"),
        }
    uid = session.get("user_id")
    if uid is None:
        return None
    u = find_user_by_id(uid)
    if not u:
        return None
    return _public_user(u)


def has_edit_permission(user, category, item):
    if user is None:
        return False
    if user["role"] == "admin":
        return True
    if user["role"] == "viewer":
        return False
    # editor
    perm = (user.get("permissions") or {}).get(category)
    if not perm:
        return False
    if perm.get("all"):
        return True
    if item and item in (perm.get("items") or []):
        return True
    return False


def _is_public_asset_request(path):
    """API以外(静的ファイル/SPAシェル)へのアクセスは未ログインでも通す。"""
    return not path.startswith("/api/")


def _before_request():
    if not _SERVER_MODE:
        return None
    path = request.path

    if _is_public_asset_request(path):
        return None
    if path in PUBLIC_API_PATHS:
        return None

    user = current_user()
    if user is None:
        return jsonify({"error": "ログインが必要です", "code": "auth_required"}), 401

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        category, item = resolve_category_and_item(path)
        if category is not None:
            item = _resolve_item_with_body(category, item)
            if not has_edit_permission(user, category, item):
                activity_log.record(user["username"], user["role"], request.method, path,
                                     category, item, status=403)
                return jsonify({"error": "この操作を行う権限がありません", "code": "forbidden"}), 403
    return None


def _after_request(response):
    if not _SERVER_MODE:
        return response
    path = request.path
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/"):
        user = current_user()
        if user is not None:
            category, item = resolve_category_and_item(path)
            if category is not None and response.status_code < 400:
                item = _resolve_item_with_body(category, item)
                activity_log.record(user["username"], user["role"], request.method, path,
                                     category, item, status=response.status_code)
    return response


def register(app, data_dir, server_mode):
    """app.py から呼び出す初期化関数。"""
    global _DATA_DIR, _SERVER_MODE
    _DATA_DIR = data_dir
    _SERVER_MODE = server_mode

    # セッション用secret_keyをdata_dir配下に永続化（再起動してもログインが切れすぎないように）
    secret_path = os.path.join(data_dir, ".flask_secret")
    if os.path.exists(secret_path):
        with open(secret_path, "r", encoding="utf-8") as f:
            app.secret_key = f.read().strip()
    else:
        key = secrets.token_hex(32)
        with open(secret_path, "w", encoding="utf-8") as f:
            f.write(key)
        app.secret_key = key

    if server_mode:
        _ensure_default_admin()

    app.before_request(_before_request)
    app.after_request(_after_request)

    # ------------------------------------------------------------
    # ルート
    # ------------------------------------------------------------
    @app.route("/api/server-config", methods=["GET"])
    def server_config():
        return jsonify({
            "serverMode": _SERVER_MODE,
            "categories": ALL_CATEGORIES,
        })

    @app.route("/api/login", methods=["POST"])
    def login():
        if not _SERVER_MODE:
            return jsonify({"error": "サーバーモードではありません"}), 400
        body = request.get_json() or {}
        username = body.get("username", "")
        password = body.get("password", "")
        user = find_user_by_username(username)
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "IDまたはパスワードが違います"}), 401
        session["user_id"] = user["id"]
        return jsonify({"message": "ログインしました", "user": _public_user(user)})

    @app.route("/api/logout", methods=["POST"])
    def logout():
        session.pop("user_id", None)
        return jsonify({"message": "ログアウトしました"})

    @app.route("/api/me", methods=["GET"])
    def me():
        user = current_user()
        if user is None:
            return jsonify({"error": "未ログイン"}), 401
        return jsonify(user)

    @app.route("/api/me", methods=["PUT"])
    def update_me():
        user = current_user()
        if user is None:
            return jsonify({"error": "未ログイン"}), 401
        body = request.get_json() or {}
        if not _SERVER_MODE:
            settings = _load_local_settings()
            if body.get("username"):
                settings["username"] = body["username"]
            _save_local_settings(settings)
            return jsonify({"message": "更新しました", "user": current_user()})
        users = _load_users_raw()
        for u in users:
            if u["id"] == user["id"]:
                new_username = body.get("username")
                new_password = body.get("password")
                if new_username:
                    if any(x["username"] == new_username and x["id"] != u["id"] for x in users):
                        return jsonify({"error": "そのIDは既に使われています"}), 400
                    u["username"] = new_username
                if new_password:
                    u["password_hash"] = generate_password_hash(new_password)
                _save_users_raw(users)
                return jsonify({"message": "更新しました", "user": _public_user(u)})
        return jsonify({"error": "ユーザーが見つかりません"}), 404

    @app.route("/api/me/download-path", methods=["PUT"])
    def update_download_path():
        user = current_user()
        if user is None:
            return jsonify({"error": "未ログイン"}), 401
        body = request.get_json() or {}
        path = body.get("path") or None
        if not _SERVER_MODE:
            settings = _load_local_settings()
            settings["download_path"] = path
            _save_local_settings(settings)
            return jsonify({"message": "ダウンロード先を保存しました", "user": current_user()})
        users = _load_users_raw()
        for u in users:
            if u["id"] == user["id"]:
                u["download_path"] = path
                _save_users_raw(users)
                return jsonify({"message": "ダウンロード先を保存しました", "user": _public_user(u)})
        return jsonify({"error": "ユーザーが見つかりません"}), 404

    def _require_admin():
        user = current_user()
        if user is None:
            return None, (jsonify({"error": "未ログイン"}), 401)
        if user["role"] != "admin":
            return None, (jsonify({"error": "管理人のみ実行できます"}), 403)
        return user, None

    @app.route("/api/users", methods=["GET"])
    def list_users():
        _, err = _require_admin()
        if err:
            return err
        return jsonify([_public_user(u) for u in _load_users_raw()])

    @app.route("/api/users", methods=["POST"])
    def create_user():
        _, err = _require_admin()
        if err:
            return err
        body = request.get_json() or {}
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        role = body.get("role", "viewer")
        if role not in ("admin", "editor", "viewer"):
            return jsonify({"error": "不正な役職です"}), 400
        if not username or not password:
            return jsonify({"error": "IDとパスワードは必須です"}), 400
        users = _load_users_raw()
        if any(u["username"] == username for u in users):
            return jsonify({"error": "そのIDは既に使われています"}), 400
        new_id = max([u["id"] for u in users], default=0) + 1
        new_user = {
            "id": new_id,
            "username": username,
            "password_hash": generate_password_hash(password),
            "role": role,
            "permissions": body.get("permissions") or _default_permissions(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        users.append(new_user)
        _save_users_raw(users)
        return jsonify({"message": "ユーザーを作成しました", "user": _public_user(new_user)}), 201

    @app.route("/api/users/<int:user_id>", methods=["PUT"])
    def update_user(user_id):
        _, err = _require_admin()
        if err:
            return err
        body = request.get_json() or {}
        users = _load_users_raw()
        for u in users:
            if u["id"] == user_id:
                if "role" in body and body["role"] in ("admin", "editor", "viewer"):
                    u["role"] = body["role"]
                if "permissions" in body:
                    u["permissions"] = body["permissions"]
                if body.get("password"):
                    u["password_hash"] = generate_password_hash(body["password"])
                if body.get("username"):
                    if any(x["username"] == body["username"] and x["id"] != u["id"] for x in users):
                        return jsonify({"error": "そのIDは既に使われています"}), 400
                    u["username"] = body["username"]
                _save_users_raw(users)
                return jsonify({"message": "更新しました", "user": _public_user(u)})
        return jsonify({"error": "ユーザーが見つかりません"}), 404

    @app.route("/api/users/<int:user_id>", methods=["DELETE"])
    def delete_user(user_id):
        _, err = _require_admin()
        if err:
            return err
        users = _load_users_raw()
        target = next((u for u in users if u["id"] == user_id), None)
        if not target:
            return jsonify({"error": "ユーザーが見つかりません"}), 404
        if target["username"] == DEFAULT_ADMIN_USERNAME:
            return jsonify({"error": "デフォルト管理者は削除できません"}), 400
        users = [u for u in users if u["id"] != user_id]
        _save_users_raw(users)
        return jsonify({"message": "削除しました"})

    @app.route("/api/categories", methods=["GET"])
    def categories():
        return jsonify(ALL_CATEGORIES)
