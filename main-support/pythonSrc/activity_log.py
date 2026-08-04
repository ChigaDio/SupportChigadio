# -*- coding: utf-8 -*-
"""
pythonSrc/activity_log.py

各ユーザーの編集操作ログを日付別ファイル(JSON Lines)に記録し、
サーバー起動中は直近7日分だけを残すログローテーションを提供する。

- 記録先: <DATA_DIR>/logs/edit_log_YYYY-MM-DD.jsonl
- 1行 = 1操作: {"time","user","role","method","path","category","item","status"}
"""
import os
import json
import threading
import time
from datetime import datetime, timedelta

LOG_RETENTION_DAYS = 7

_lock = threading.Lock()
_LOGS_DIR = None


def init(data_dir):
    global _LOGS_DIR
    _LOGS_DIR = os.path.join(data_dir, "logs")
    os.makedirs(_LOGS_DIR, exist_ok=True)


def _today_path():
    fname = f"edit_log_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    return os.path.join(_LOGS_DIR, fname)


def record(user, role, method, path, category=None, item=None, status=200):
    """1件の編集操作ログを追記する。"""
    if _LOGS_DIR is None:
        return
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "user": user,
        "role": role,
        "method": method,
        "path": path,
        "category": category,
        "item": item,
        "status": status,
    }
    try:
        with _lock:
            with open(_today_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_recent(limit=100, user=None, days=LOG_RETENTION_DAYS):
    """直近 `days` 日分のログを新しい順に読み出す。"""
    if _LOGS_DIR is None or not os.path.isdir(_LOGS_DIR):
        return []
    entries = []
    cutoff = datetime.now() - timedelta(days=days)
    try:
        for fname in sorted(os.listdir(_LOGS_DIR), reverse=True):
            if not fname.startswith("edit_log_") or not fname.endswith(".jsonl"):
                continue
            date_str = fname[len("edit_log_"):-len(".jsonl")]
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if file_date < cutoff.replace(hour=0, minute=0, second=0, microsecond=0):
                continue
            with open(os.path.join(_LOGS_DIR, fname), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if user and entry.get("user") != user:
                        continue
                    entries.append(entry)
    except Exception:
        pass
    entries.sort(key=lambda e: e.get("time", ""), reverse=True)
    return entries[:limit]


def rotate(retention_days=LOG_RETENTION_DAYS):
    """retention_days より古いログファイルを削除する。"""
    if _LOGS_DIR is None or not os.path.isdir(_LOGS_DIR):
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    for fname in os.listdir(_LOGS_DIR):
        if not fname.startswith("edit_log_") or not fname.endswith(".jsonl"):
            continue
        date_str = fname[len("edit_log_"):-len(".jsonl")]
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                os.remove(os.path.join(_LOGS_DIR, fname))
            except OSError:
                pass


def start_rotation_thread(interval_seconds=3600, retention_days=LOG_RETENTION_DAYS):
    """バックグラウンドで定期的にログローテーションを実行するスレッドを開始する。"""
    def _loop():
        while True:
            rotate(retention_days)
            time.sleep(interval_seconds)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
