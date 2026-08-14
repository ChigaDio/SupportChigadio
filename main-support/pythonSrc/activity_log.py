# -*- coding: utf-8 -*-
"""
pythonSrc/activity_log.py

各ユーザーの編集操作ログを日付別ファイル(JSON Lines)に記録し、
サーバー起動中は直近7日分だけを「logs/」直下に残すログローテーションを
提供する。7日より古いログはこれまで削除していたが、「全体を後から検索・
閲覧したい」という要望に対応するため、削除ではなく logs/archive/ へ
移動して長期保存するように変更した。

- 記録先: <DATA_DIR>/logs/edit_log_YYYY-MM-DD.jsonl
- アーカイブ先: <DATA_DIR>/logs/archive/edit_log_YYYY-MM-DD.jsonl
- 1行 = 1操作: {"time","user","role","method","path","category","item","status"}

read_recent() は直近分（logs/直下のみ）を素早く返すための既存API。
read_all() は logs/ と logs/archive/ の両方を横断し、ユーザー・操作種別・
カテゴリ・日付範囲・キーワードでの絞り込みとページネーションに対応した
「全体ログ」閲覧用のAPI。
"""
import os
import json
import shutil
import threading
import time
from datetime import datetime, timedelta

LOG_RETENTION_DAYS = 7

_lock = threading.Lock()
_LOGS_DIR = None


def _archive_dir():
    return os.path.join(_LOGS_DIR, "archive") if _LOGS_DIR else None


def init(data_dir):
    global _LOGS_DIR
    _LOGS_DIR = os.path.join(data_dir, "logs")
    os.makedirs(_LOGS_DIR, exist_ok=True)
    os.makedirs(_archive_dir(), exist_ok=True)


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


def _iter_all_log_files():
    """logs/ 直下（直近分）と logs/archive/（7日より古い分）の両方の
    ログファイルパスを返す。"""
    paths = []
    for base_dir in (_LOGS_DIR, _archive_dir()):
        if base_dir is None or not os.path.isdir(base_dir):
            continue
        for fname in os.listdir(base_dir):
            if not fname.startswith("edit_log_") or not fname.endswith(".jsonl"):
                continue
            full_path = os.path.join(base_dir, fname)
            if os.path.isfile(full_path):
                paths.append(full_path)
    return paths


def _iter_all_entries():
    for path in _iter_all_log_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def read_all(user=None, method=None, category=None, date_from=None, date_to=None,
             keyword=None, offset=0, limit=200):
    """logs/ と logs/archive/ を横断して、条件に合うログを新しい順に返す。
    「全体ログ」画面向けのフィルタ・検索・ページネーション対応API。

    date_from / date_to は "YYYY-MM-DD" 形式を想定。date_to はその日の
    最後まで(23:59:59)を含める。
    戻り値: (entries, total)  ※ entries は offset〜offset+limit のページ分のみ
    """
    date_from_key = f"{date_from}T00:00:00" if date_from else None
    date_to_key = f"{date_to}T23:59:59" if date_to else None
    keyword_lower = keyword.lower().strip() if keyword else None

    def match(e):
        if user and e.get("user") != user:
            return False
        if method and e.get("method") != method:
            return False
        if category and e.get("category") != category:
            return False
        t = e.get("time", "")
        if date_from_key and t < date_from_key:
            return False
        if date_to_key and t > date_to_key:
            return False
        if keyword_lower:
            haystack = " ".join(
                str(e.get(k, "") or "") for k in ("path", "item", "user", "category")
            ).lower()
            if keyword_lower not in haystack:
                return False
        return True

    filtered = [e for e in _iter_all_entries() if match(e)]
    filtered.sort(key=lambda e: e.get("time", ""), reverse=True)
    total = len(filtered)
    page = filtered[offset:offset + limit]
    return page, total


def list_users():
    """全期間のログに登場するユーザー名一覧（フィルタのプルダウン用）。"""
    users = {e.get("user") for e in _iter_all_entries() if e.get("user")}
    return sorted(users)


def list_categories():
    """全期間のログに登場するカテゴリ一覧（フィルタのプルダウン用）。"""
    cats = {e.get("category") for e in _iter_all_entries() if e.get("category")}
    return sorted(cats)


def rotate(retention_days=LOG_RETENTION_DAYS):
    """retention_days より古いログファイルを logs/ 直下から logs/archive/ へ
    移動する（削除はしない）。これにより「直近ログ」は軽量なまま保ちつつ、
    read_all() で過去分も含めた全体を検索・閲覧できるようにする。"""
    if _LOGS_DIR is None or not os.path.isdir(_LOGS_DIR):
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    archive_dir = _archive_dir()
    os.makedirs(archive_dir, exist_ok=True)
    with _lock:
        for fname in os.listdir(_LOGS_DIR):
            src_path = os.path.join(_LOGS_DIR, fname)
            if not os.path.isfile(src_path):
                continue
            if not fname.startswith("edit_log_") or not fname.endswith(".jsonl"):
                continue
            date_str = fname[len("edit_log_"):-len(".jsonl")]
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if file_date >= cutoff:
                continue
            dest_path = os.path.join(archive_dir, fname)
            try:
                if os.path.exists(dest_path):
                    # 同名ファイルが既にアーカイブにある場合は行を追記してマージする
                    with open(src_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    with open(dest_path, "a", encoding="utf-8") as f:
                        f.write(content)
                    os.remove(src_path)
                else:
                    shutil.move(src_path, dest_path)
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
