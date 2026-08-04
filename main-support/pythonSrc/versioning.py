# -*- coding: utf-8 -*-
"""
pythonSrc/versioning.py

`data/` ディレクトリ全体を1つの「バージョン」として、
`versions/` ディレクトリにスナップショットを保存・切替・ロールバックする。

- 手動バージョン: 管理人が明示的に作成。基本削除されず履歴として残る。
- 自動バージョン(_auto_YYYYMMDD_HHMMSS): サーバー起動中、定期的に自動作成され、
  直近7日分のみ保持（ログローテーション）。

既存の各モジュールは `DATA_DIR` を直接参照する設計のため、
バージョン切替時は `versions/<name>/` の内容を丸ごと `data/` にコピーし直す
（既存コードの改修を最小限にするための方式）。
"""
import os
import shutil
import json
import threading
import time
from datetime import datetime, timedelta

_lock = threading.Lock()

_DATA_DIR = None
_VERSIONS_DIR = None
_ACTIVE_FILE = None

AUTO_PREFIX = "_auto_"
AUTO_RETENTION_DAYS = 7

# バージョンスナップショットに含めない（無限ループ/巨大化防止）
_EXCLUDE_DIR_NAMES = {"logs"}


def _meta_path(name):
    return os.path.join(_VERSIONS_DIR, name, "_meta.json")


def _snapshot_target_dir(name):
    return os.path.join(_VERSIONS_DIR, name, "data")


def init(data_dir, base_dir):
    global _DATA_DIR, _VERSIONS_DIR, _ACTIVE_FILE
    _DATA_DIR = data_dir
    _VERSIONS_DIR = os.path.join(base_dir, "..", "versions")
    _VERSIONS_DIR = os.path.abspath(_VERSIONS_DIR)
    os.makedirs(_VERSIONS_DIR, exist_ok=True)
    _ACTIVE_FILE = os.path.join(_VERSIONS_DIR, "_active.json")

    if not os.path.exists(_ACTIVE_FILE):
        # 初回起動: 現在の data/ を "v1" として登録し、アクティブにする
        create_version("v1", parent=None, created_by="system", snapshot_from_live=True)
        _set_active("v1")


def _copy_data_dir(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(*_EXCLUDE_DIR_NAMES)
    )


def list_versions(include_auto=True):
    if not os.path.isdir(_VERSIONS_DIR):
        return []
    result = []
    for name in os.listdir(_VERSIONS_DIR):
        full = os.path.join(_VERSIONS_DIR, name)
        if not os.path.isdir(full):
            continue
        if not include_auto and name.startswith(AUTO_PREFIX):
            continue
        meta_path = _meta_path(name)
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        else:
            meta = {"name": name}
        result.append(meta)
    result.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return result


def get_active():
    if not os.path.exists(_ACTIVE_FILE):
        return None
    with open(_ACTIVE_FILE, "r", encoding="utf-8") as f:
        active = json.load(f)
    name = active.get("active")
    meta_path = _meta_path(name)
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        active.update(meta)
    return active


def _set_active(name):
    with open(_ACTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"active": name, "activated_at": datetime.now().isoformat(timespec="seconds")}, f, ensure_ascii=False)


def create_version(name, parent=None, created_by="system", snapshot_from_live=False):
    """新バージョンを作成する。

    - snapshot_from_live=True の場合、現在の `data/` の内容をそのままスナップショットする
      (初回起動用)。
    - それ以外は `parent` バージョンのスナップショットをコピーして新バージョンを作る。
      parent省略時は現在アクティブなバージョンを親とする。
    """
    with _lock:
        version_dir = os.path.join(_VERSIONS_DIR, name)
        if os.path.exists(version_dir):
            raise ValueError(f"バージョン '{name}' は既に存在します")

        os.makedirs(version_dir, exist_ok=True)
        target = _snapshot_target_dir(name)

        if snapshot_from_live:
            _copy_data_dir(_DATA_DIR, target)
        else:
            if parent is None:
                active = get_active()
                parent = active["name"] if active else None
            if parent is None:
                raise ValueError("親バージョンが指定されていません")
            parent_dir = _snapshot_target_dir(parent)
            if not os.path.isdir(parent_dir):
                raise ValueError(f"親バージョン '{parent}' が見つかりません")
            _copy_data_dir(parent_dir, target)

        meta = {
            "name": name,
            "parent": parent,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "created_by": created_by,
        }
        with open(_meta_path(name), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta


def activate_version(name):
    """指定バージョンを現在の作業データ(data/)に反映し、アクティブにする。

    切替前に、現在アクティブなバージョンへ今の作業データの変更を保存(上書き)しておく
    （編集内容を失わないため）。
    """
    with _lock:
        target = _snapshot_target_dir(name)
        if not os.path.isdir(target):
            raise ValueError(f"バージョン '{name}' が見つかりません")

        active = get_active()
        if active is not None:
            current_snapshot = _snapshot_target_dir(active["name"])
            _copy_data_dir(_DATA_DIR, current_snapshot)

        _copy_data_dir(target, _DATA_DIR)
        _set_active(name)
        return get_active()


def rollback_version(name):
    """activate_versionと同義（過去バージョンへ戻す操作の別名エンドポイント用）。"""
    return activate_version(name)


def auto_snapshot():
    name = AUTO_PREFIX + datetime.now().strftime("%Y%m%d_%H%M%S")
    active = get_active()
    parent_name = active["name"] if active else None
    try:
        version_dir = os.path.join(_VERSIONS_DIR, name)
        os.makedirs(version_dir, exist_ok=True)
        target = _snapshot_target_dir(name)
        _copy_data_dir(_DATA_DIR, target)
        meta = {
            "name": name,
            "parent": parent_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "created_by": "auto",
            "auto": True,
        }
        with open(_meta_path(name), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def rotate_auto_versions(retention_days=AUTO_RETENTION_DAYS):
    if not os.path.isdir(_VERSIONS_DIR):
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    for name in os.listdir(_VERSIONS_DIR):
        if not name.startswith(AUTO_PREFIX):
            continue
        meta_path = _meta_path(name)
        created_at = None
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    created_at = json.load(f).get("created_at")
            except Exception:
                created_at = None
        try:
            dt = datetime.fromisoformat(created_at) if created_at else None
        except Exception:
            dt = None
        if dt is None or dt < cutoff:
            shutil.rmtree(os.path.join(_VERSIONS_DIR, name), ignore_errors=True)


def start_rotation_thread(interval_seconds=6 * 3600, retention_days=AUTO_RETENTION_DAYS):
    """サーバー起動中、定期的に自動スナップショット＋7日ローテーションを行うスレッド。"""
    def _loop():
        while True:
            auto_snapshot()
            rotate_auto_versions(retention_days)
            time.sleep(interval_seconds)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


def register(app, data_dir, base_dir, server_mode):
    from flask import request, jsonify
    import pythonSrc.auth as auth

    init(data_dir, base_dir)

    @app.route("/api/current-version", methods=["GET"])
    def current_version():
        active = get_active()
        return jsonify(active or {})

    @app.route("/api/versions", methods=["GET"])
    def versions_list():
        return jsonify(list_versions())

    @app.route("/api/versions", methods=["POST"])
    def versions_create():
        user = auth.current_user()
        if server_mode and (user is None or user["role"] != "admin"):
            return jsonify({"error": "管理人のみバージョンを作成できます"}), 403
        body = request.get_json() or {}
        name = (body.get("name") or "").strip()
        parent = body.get("parent")
        if not name:
            return jsonify({"error": "バージョン名は必須です"}), 400
        try:
            meta = create_version(name, parent=parent,
                                   created_by=(user["username"] if user else "system"))
            return jsonify({"message": f"バージョン '{name}' を作成しました", "data": meta}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/versions/<name>/activate", methods=["POST"])
    def versions_activate(name):
        user = auth.current_user()
        if server_mode and (user is None or user["role"] != "admin"):
            return jsonify({"error": "管理人のみバージョンを切り替えられます"}), 403
        try:
            active = activate_version(name)
            return jsonify({"message": f"バージョン '{name}' をアクティブにしました", "data": active})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/versions/<name>/rollback", methods=["POST"])
    def versions_rollback(name):
        user = auth.current_user()
        if server_mode and (user is None or user["role"] != "admin"):
            return jsonify({"error": "管理人のみロールバックできます"}), 403
        try:
            active = rollback_version(name)
            return jsonify({"message": f"バージョン '{name}' へロールバックしました", "data": active})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
