# -*- coding: utf-8 -*-
"""
pythonSrc/versioning.py

【重要・設計変更】
以前の実装は「アクティブなバージョンを切り替えるたびに data/ の中身を
versions/<name>/data/ へコピーし直す」方式だったため、
バージョンを切り替えずに編集を続けている間は変更が versions/ 側へ
反映されず、"アクティブにしたのに保存されない" ように見えるバグがあった。

この実装では、`data/` フォルダを **常に「アクティブなバージョンの実体
(`versions/<name>/data/`) を指すディレクトリリンク（Windowsはジャンクション、
POSIXはシンボリックリンク）」** にする。これにより、
アプリのどこで `DATA_DIR` に書き込んでも、書き込みは常にそのまま
アクティブなバージョンの実フォルダへ直接反映される（コピーのタイムラグや
同期漏れが原理的に発生しない）。

- 新しいバージョンを作る = 親バージョンの実フォルダを丸ごとコピーして
  新しい `versions/<name>/data/` を作るだけ（このコピー元は「親バージョンが
  現在アクティブなら＝今まさに編集しているdata/そのもの」なので、
  最新の編集内容が確実に引き継がれる）。
- バージョンを切り替える = `data/` のリンク先を張り替えるだけ（コピー不要）。

【通常モードでは一切動作しない】
`python app.py`（通常起動）のときは、このモジュールは何もしない
（versions/ フォルダも作らない）。従来通り `data/` フォルダへ直接読み書き
するだけの、これまでと同じ挙動になる。バージョン管理はサーバーモード限定の機能。
"""
import os
import platform
import shutil
import subprocess
import json
import threading
import time
from datetime import datetime, timedelta

_lock = threading.Lock()

_DATA_DIR = None
_VERSIONS_DIR = None
_ACTIVE_FILE = None
_SERVER_MODE = False
_ENABLED = False  # 実際にリンク方式が使えたかどうか（失敗時はバージョン機能を無効化する）

AUTO_PREFIX = "_auto_"
AUTO_RETENTION_DAYS = 7
_EXCLUDE_DIR_NAMES = {"logs"}


# ----------------------------------------------------------------------
# ディレクトリリンク（Windows: ジャンクション / POSIX: シンボリックリンク）
# ----------------------------------------------------------------------
def _is_link(path):
    if os.path.islink(path):
        return True
    if platform.system() == "Windows" and os.path.isdir(path):
        # NTFSジャンクションは islink=False になる場合があるため reparse point を確認
        try:
            import ctypes
            FILE_ATTRIBUTE_REPARSE_POINT = 0x400
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            return attrs != -1 and bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
        except Exception:
            return False
    return False


def _remove_link(path):
    if os.path.islink(path):
        os.unlink(path)
        return
    if platform.system() == "Windows" and _is_link(path):
        os.rmdir(path)  # ジャンクションの解除（中身は消えない）
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def _create_link(link_path, target_path):
    target_path = os.path.abspath(target_path)
    if platform.system() == "Windows":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", link_path, target_path],
            check=True, capture_output=True, shell=False,
        )
    else:
        os.symlink(target_path, link_path, target_is_directory=True)


def _relink(link_path, target_path):
    if os.path.exists(link_path) or os.path.islink(link_path):
        _remove_link(link_path)
    os.makedirs(target_path, exist_ok=True)
    _create_link(link_path, target_path)


# ----------------------------------------------------------------------
# バージョンメタ情報
# ----------------------------------------------------------------------
def _meta_path(name):
    return os.path.join(_VERSIONS_DIR, name, "_meta.json")


def _snapshot_target_dir(name):
    return os.path.join(_VERSIONS_DIR, name, "data")


def is_enabled():
    return _SERVER_MODE and _ENABLED


def init(data_dir, base_dir, server_mode):
    global _DATA_DIR, _VERSIONS_DIR, _ACTIVE_FILE, _SERVER_MODE, _ENABLED
    _DATA_DIR = data_dir
    _SERVER_MODE = server_mode

    if not server_mode:
        # 通常モードでは versions/ フォルダを一切作らず、何もしない。
        _ENABLED = False
        return

    _VERSIONS_DIR = os.path.abspath(os.path.join(base_dir, "..", "versions"))
    os.makedirs(_VERSIONS_DIR, exist_ok=True)
    _ACTIVE_FILE = os.path.join(_VERSIONS_DIR, "_active.json")

    try:
        if not os.path.exists(_ACTIVE_FILE):
            # 初回サーバーモード起動: 既存の data/ フォルダの中身を v1 として取り込み、
            # data/ を v1 の実フォルダへのリンクに置き換える。
            v1_dir = os.path.join(_VERSIONS_DIR, "v1")
            os.makedirs(v1_dir, exist_ok=True)
            v1_data = _snapshot_target_dir("v1")

            if _is_link(_DATA_DIR):
                # 想定外だが、既にリンクになっている場合はそのまま採用
                pass
            elif os.path.isdir(_DATA_DIR):
                shutil.move(_DATA_DIR, v1_data)
            else:
                os.makedirs(v1_data, exist_ok=True)

            meta = {
                "name": "v1", "parent": None,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "created_by": "system",
            }
            with open(_meta_path("v1"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            if not _is_link(_DATA_DIR):
                _relink(_DATA_DIR, v1_data)
            _set_active("v1")
        else:
            # 既にバージョン管理済み: data/ が正しくアクティブバージョンへ
            # リンクされているか確認し、ズレていれば張り直す。
            active = get_active()
            if active:
                target = _snapshot_target_dir(active["name"])
                if not _is_link(_DATA_DIR):
                    # 何らかの理由でリンクが失われ、実フォルダに戻ってしまっている場合は
                    # 現在の中身を優先し、アクティブバージョン側へ取り込んでからリンクし直す。
                    if os.path.isdir(_DATA_DIR):
                        if os.path.isdir(target):
                            shutil.rmtree(target)
                        shutil.move(_DATA_DIR, target)
                    _relink(_DATA_DIR, target)
        _ENABLED = True
    except Exception as e:
        # ジャンクション/シンボリックリンクが作成できない環境（権限不足等）では
        # バージョン管理機能を無効化し、通常の data/ フォルダとして動作させる
        # （アプリ全体は落とさない）。
        print(f"[versioning] ディレクトリリンクを作成できなかったため、バージョン管理機能は無効化されます: {e}")
        _ENABLED = False


def list_versions(include_auto=True):
    if not is_enabled() or not os.path.isdir(_VERSIONS_DIR):
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
    if not is_enabled() or not os.path.exists(_ACTIVE_FILE):
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


def create_version(name, parent=None, created_by="system"):
    """新バージョンを作成する。親バージョン(省略時は現在アクティブなバージョン)の
    実フォルダをそのままコピーする。親が現在アクティブなら、コピー元は
    まさに今 data/ として編集中の内容そのものなので、最新の変更が確実に含まれる。
    """
    if not is_enabled():
        raise RuntimeError("バージョン管理はサーバーモードでのみ利用できます")
    with _lock:
        version_dir = os.path.join(_VERSIONS_DIR, name)
        if os.path.exists(version_dir):
            raise ValueError(f"バージョン '{name}' は既に存在します")

        if parent is None:
            active = get_active()
            parent = active["name"] if active else None
        if parent is None:
            raise ValueError("親バージョンが指定されていません")
        parent_dir = _snapshot_target_dir(parent)
        if not os.path.isdir(parent_dir):
            raise ValueError(f"親バージョン '{parent}' が見つかりません")

        os.makedirs(version_dir, exist_ok=True)
        target = _snapshot_target_dir(name)
        shutil.copytree(parent_dir, target, ignore=shutil.ignore_patterns(*_EXCLUDE_DIR_NAMES))

        meta = {
            "name": name, "parent": parent,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "created_by": created_by,
        }
        with open(_meta_path(name), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta


def activate_version(name):
    """data/ のリンク先を、指定バージョンの実フォルダへ張り替える（コピーは発生しない）。
    切り替え前の編集内容は、切り替え前のバージョンの実フォルダに
    そのまま残っている（常時リンクされているため、既に保存済み）。
    """
    if not is_enabled():
        raise RuntimeError("バージョン管理はサーバーモードでのみ利用できます")
    with _lock:
        target = _snapshot_target_dir(name)
        if not os.path.isdir(target):
            raise ValueError(f"バージョン '{name}' が見つかりません")
        _relink(_DATA_DIR, target)
        _set_active(name)
        return get_active()


def rollback_version(name):
    return activate_version(name)


def auto_snapshot():
    if not is_enabled():
        return
    name = AUTO_PREFIX + datetime.now().strftime("%Y%m%d_%H%M%S")
    active = get_active()
    parent_name = active["name"] if active else None
    try:
        version_dir = os.path.join(_VERSIONS_DIR, name)
        os.makedirs(version_dir, exist_ok=True)
        target = _snapshot_target_dir(name)
        shutil.copytree(_DATA_DIR, target, ignore=shutil.ignore_patterns(*_EXCLUDE_DIR_NAMES))
        meta = {
            "name": name, "parent": parent_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "created_by": "auto", "auto": True,
        }
        with open(_meta_path(name), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def rotate_auto_versions(retention_days=AUTO_RETENTION_DAYS):
    if not is_enabled() or not os.path.isdir(_VERSIONS_DIR):
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
    """サーバー起動中のみ呼び出すこと。定期的に自動スナップショット＋7日ローテーションを行う。"""
    if not is_enabled():
        return None

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

    init(data_dir, base_dir, server_mode)

    @app.route("/api/current-version", methods=["GET"])
    def current_version():
        if not is_enabled():
            return jsonify(None)
        return jsonify(get_active() or {})

    @app.route("/api/versions", methods=["GET"])
    def versions_list():
        return jsonify(list_versions())

    @app.route("/api/versions", methods=["POST"])
    def versions_create():
        if not is_enabled():
            return jsonify({"error": "バージョン管理はサーバーモードでのみ利用できます"}), 400
        user = auth.current_user()
        if user is None or user["role"] != "admin":
            return jsonify({"error": "管理人のみバージョンを作成できます"}), 403
        body = request.get_json() or {}
        name = (body.get("name") or "").strip()
        parent = body.get("parent")
        if not name:
            return jsonify({"error": "バージョン名は必須です"}), 400
        try:
            meta = create_version(name, parent=parent, created_by=user["username"])
            return jsonify({"message": f"バージョン '{name}' を作成しました", "data": meta}), 201
        except (ValueError, RuntimeError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/versions/<name>/activate", methods=["POST"])
    def versions_activate(name):
        if not is_enabled():
            return jsonify({"error": "バージョン管理はサーバーモードでのみ利用できます"}), 400
        user = auth.current_user()
        if user is None or user["role"] != "admin":
            return jsonify({"error": "管理人のみバージョンを切り替えられます"}), 403
        try:
            active = activate_version(name)
            return jsonify({"message": f"バージョン '{name}' をアクティブにしました", "data": active})
        except (ValueError, RuntimeError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/versions/<name>/rollback", methods=["POST"])
    def versions_rollback(name):
        if not is_enabled():
            return jsonify({"error": "バージョン管理はサーバーモードでのみ利用できます"}), 400
        user = auth.current_user()
        if user is None or user["role"] != "admin":
            return jsonify({"error": "管理人のみロールバックできます"}), 403
        try:
            active = rollback_version(name)
            return jsonify({"message": f"バージョン '{name}' へロールバックしました", "data": active})
        except (ValueError, RuntimeError) as e:
            return jsonify({"error": str(e)}), 400
