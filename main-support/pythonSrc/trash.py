# -*- coding: utf-8 -*-
"""
pythonSrc/trash.py

即時削除ではなく、一時退避（ゴミ箱）+復元を提供する共通ユーティリティ。
各カテゴリの削除処理（enum/class_data/class_data_id/custom_class_data/
custom_class_data_id/class_data_matrix_id/state_data/behavior_data/
scenario_role）が実データフォルダを直接 shutil.rmtree() する代わりに、
本モジュールの move_to_trash() を呼ぶことで、削除内容を
<DATA_DIR>/.trash/ 配下へ移動する。

一定期間（デフォルト30日）経過したものは自動的に完全削除される
（activity_log.py のログローテーションと同様のバックグラウンドスレッド方式）。

ゴミ箱エントリの構造:
  <DATA_DIR>/.trash/<trash_id>/
      __meta.json     # {category, name, original_path, deleted_at, list_entry, ...}
      payload/        # 元のフォルダをそのまま退避したもの

list_entry: 削除時に *_list.json から取り除かれた該当行(dict)のコピー。
復元時に、対象の *_list.json に同名の行がまだ無ければ再度追記する
（既存の一覧管理ロジックとは独立して、ゴミ箱側で完結させている）。

注意: 復元は「元の場所に何も無い場合のみ」許可する。元の場所に既に
同名の新しいデータが作られていた場合は、事故防止のため復元を拒否する。
"""
import json
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta

DATA_DIR = None
TRASH_RETENTION_DAYS = 30

_lock = threading.Lock()


def _trash_root():
    return os.path.join(DATA_DIR, ".trash") if DATA_DIR else None


def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    os.makedirs(_trash_root(), exist_ok=True)


def move_to_trash(category, name, original_path, list_entry=None):
    """original_path（フォルダ）をゴミ箱へ移動する。
    original_path が存在しない場合は何もせず None を返す（呼び出し側の
    既存の `if os.path.exists(...)` チェックと組み合わせて使う想定）。
    戻り値: trash_id（移動できた場合）"""
    if DATA_DIR is None or not original_path or not os.path.exists(original_path):
        return None
    with _lock:
        trash_id = f"{category}__{name}__{datetime.now().strftime('%Y%m%d%H%M%S%f')}__{uuid.uuid4().hex[:6]}"
        entry_dir = os.path.join(_trash_root(), trash_id)
        os.makedirs(entry_dir, exist_ok=True)
        payload_path = os.path.join(entry_dir, "payload")
        shutil.move(original_path, payload_path)
        meta = {
            "trash_id": trash_id,
            "category": category,
            "name": name,
            "original_path": os.path.abspath(original_path),
            "deleted_at": datetime.now().isoformat(timespec="seconds"),
            "list_entry": list_entry,
        }
        with open(os.path.join(entry_dir, "__meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    return trash_id


def list_trash():
    if DATA_DIR is None or not os.path.isdir(_trash_root()):
        return []
    items = []
    for entry in os.listdir(_trash_root()):
        meta_path = os.path.join(_trash_root(), entry, "__meta.json")
        if not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                items.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    items.sort(key=lambda m: m.get("deleted_at", ""), reverse=True)
    return items


def _list_json_path_for(original_path):
    """original_path（"<category_dir>/<name>"というフォルダ想定）の親フォルダ
    から、対応する *_list.json のパスを逆算する。見つからなければNone。"""
    category_dir = os.path.dirname(original_path)
    if not os.path.isdir(category_dir):
        return None
    for fname in os.listdir(category_dir):
        if fname.endswith("_list.json"):
            return os.path.join(category_dir, fname)
    return None


def restore_from_trash(trash_id):
    """ゴミ箱のエントリを元の場所へ復元する。
    元の場所に既に同名のものが存在する場合は、事故防止のため復元しない。"""
    if DATA_DIR is None:
        raise ValueError("初期化されていません")
    entry_dir = os.path.join(_trash_root(), trash_id)
    meta_path = os.path.join(entry_dir, "__meta.json")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError("ゴミ箱にそのアイテムは見つかりません")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    payload_path = os.path.join(entry_dir, "payload")
    original_path = meta["original_path"]
    if os.path.exists(original_path):
        raise FileExistsError(f"復元先に既に同名のデータが存在するため復元できません: {original_path}")

    os.makedirs(os.path.dirname(original_path), exist_ok=True)
    shutil.move(payload_path, original_path)

    list_entry = meta.get("list_entry")
    if list_entry:
        list_json_path = _list_json_path_for(original_path)
        if list_json_path and os.path.isfile(list_json_path):
            try:
                with open(list_json_path, "r", encoding="utf-8") as f:
                    items = json.load(f)
                if isinstance(items, list) and not any(
                    isinstance(it, dict) and it.get("name") == meta.get("name") for it in items
                ):
                    items.append(list_entry)
                    with open(list_json_path, "w", encoding="utf-8") as f:
                        json.dump(items, f, ensure_ascii=False, indent=2)
            except (json.JSONDecodeError, OSError):
                pass  # list.json側の復元に失敗しても、実データの復元自体は成功させる

    with _lock:
        shutil.rmtree(entry_dir, ignore_errors=True)
    return meta


def purge_from_trash(trash_id):
    """ゴミ箱のエントリを完全に削除する（元に戻せない）。"""
    entry_dir = os.path.join(_trash_root(), trash_id)
    if not os.path.isdir(entry_dir):
        raise FileNotFoundError("ゴミ箱にそのアイテムは見つかりません")
    with _lock:
        shutil.rmtree(entry_dir, ignore_errors=True)


def purge_expired(retention_days=TRASH_RETENTION_DAYS):
    if DATA_DIR is None or not os.path.isdir(_trash_root()):
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    for meta in list_trash():
        try:
            deleted_at = datetime.fromisoformat(meta.get("deleted_at", ""))
        except (ValueError, TypeError):
            continue
        if deleted_at < cutoff:
            try:
                purge_from_trash(meta["trash_id"])
            except FileNotFoundError:
                pass


def start_purge_thread(interval_seconds=3600, retention_days=TRASH_RETENTION_DAYS):
    def _loop():
        while True:
            purge_expired(retention_days)
            time.sleep(interval_seconds)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


def register(app, data_dir):
    from flask import jsonify
    init(data_dir)
    start_purge_thread()

    @app.route("/api/trash", methods=["GET"])
    def trash_list():
        return jsonify(list_trash())

    @app.route("/api/trash/<trash_id>/restore", methods=["POST"])
    def trash_restore(trash_id):
        try:
            meta = restore_from_trash(trash_id)
            return jsonify({"message": f"{meta.get('name')} を復元しました"})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except FileExistsError as e:
            return jsonify({"error": str(e)}), 409
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/trash/<trash_id>", methods=["DELETE"])
    def trash_purge(trash_id):
        try:
            purge_from_trash(trash_id)
            return jsonify({"message": "完全に削除しました"})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500
