# -*- coding: utf-8 -*-
"""
pythonSrc/history.py

activity_log.py に記録される「いつ・誰が・何を」に対して、
「その時どう変わったか（diff）」を紐付けて見られるようにするモジュール。

実装方針:
各カテゴリの書き込み処理（class_data.py, state.py, ...）は、それぞれ
独自にファイルへ直接書き込んでおり、共通の「保存」関数を経由していない
ため、個々の書き込み箇所に手を加えずに変更を捕捉するのは難しい。
そこで、Flaskの before_request / after_request フックを使い、状態変更を
伴うAPIリクエスト（POST/PUT/PATCH/DELETE, /api/*）の前後で DATA_DIR 配下
の全JSONファイルの mtime を比較し、変更されたファイルだけをその時点の
内容で <DATA_DIR>/.history/ 配下にスナップショットとして保存していく
方式にした。既存の書き込みロジックには一切手を加えていない。

diffは、あるスナップショットと「その直前のスナップショット」との差分
（difflib.unified_diff）として算出する。WorkspaceUploadGrid.js の
DiffViewer と同じ表示形式でフロントエンドに返す。

activity_log.py 側には、直近のログエントリに変更ファイル一覧を後から
追記するための `attach_changed_files()` を1つだけ追加している
（既存関数の挙動は変更していない）。

パフォーマンス上の注意:
状態変更を伴うAPIリクエストのたびにDATA_DIR全体をos.walkするため、
ファイル数が非常に多いプロジェクトでは多少のオーバーヘッドが生じる。
社内ツールとしての利用規模であれば実用上問題ないと判断している。
"""
import difflib
import json
import os
from datetime import datetime

DATA_DIR = None
_HISTORY_DIRNAME = ".history"
_EXCLUDE_TOP_DIRS = {"logs", "app_meta", ".trash", _HISTORY_DIRNAME, "announcements"}
_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_MAX_SNAPSHOTS_PER_FILE = 50


def _history_root():
    return os.path.join(DATA_DIR, _HISTORY_DIRNAME) if DATA_DIR else None


def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    os.makedirs(_history_root(), exist_ok=True)


def _iter_json_files():
    for root, dirs, files in os.walk(DATA_DIR):
        rel = os.path.relpath(root, DATA_DIR)
        rel_parts = [] if rel == "." else rel.replace("\\", "/").split("/")
        if rel_parts and rel_parts[0] in _EXCLUDE_TOP_DIRS:
            dirs[:] = []
            continue
        for fname in files:
            if fname.endswith(".json"):
                yield os.path.join(root, fname)


def snapshot_mtimes():
    """DATA_DIR配下の全JSONファイルの{絶対パス: mtime}を返す（内容は読まない、軽量）。"""
    snap = {}
    if DATA_DIR is None:
        return snap
    for path in _iter_json_files():
        try:
            snap[path] = os.path.getmtime(path)
        except OSError:
            continue
    return snap


def _history_dir_for(abs_path):
    rel = os.path.relpath(abs_path, DATA_DIR).replace("\\", "/").replace("/", "__")
    return os.path.join(_history_root(), rel)


def _trim_snapshots(hist_dir, keep=_MAX_SNAPSHOTS_PER_FILE):
    files = sorted(f for f in os.listdir(hist_dir) if f.endswith(".json"))
    if len(files) > keep:
        for fname in files[: len(files) - keep]:
            try:
                os.remove(os.path.join(hist_dir, fname))
            except OSError:
                pass


def _save_snapshot(abs_path):
    """abs_path の現在の内容を新しいスナップショットとして保存し、
    そのスナップショットID（タイムスタンプ文字列）を返す。"""
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    hist_dir = _history_dir_for(abs_path)
    os.makedirs(hist_dir, exist_ok=True)
    snapshot_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    with open(os.path.join(hist_dir, f"{snapshot_id}.json"), "w", encoding="utf-8") as f:
        f.write(content)
    _trim_snapshots(hist_dir)
    return snapshot_id


def _list_snapshot_ids(abs_path):
    hist_dir = _history_dir_for(abs_path)
    if not os.path.isdir(hist_dir):
        return []
    return sorted(f[:-5] for f in os.listdir(hist_dir) if f.endswith(".json"))


def record_changes_for_request(before_mtimes):
    """before_requestで取得したmtimeスナップショットと現在を比較し、変更された
    ファイルだけスナップショットを保存する。
    戻り値: [{"path": "相対パス", "snapshot": "スナップショットID"}, ...]"""
    if DATA_DIR is None:
        return []
    after_mtimes = snapshot_mtimes()
    changed = []
    for abs_path in set(before_mtimes) | set(after_mtimes):
        if before_mtimes.get(abs_path) == after_mtimes.get(abs_path):
            continue
        if not os.path.isfile(abs_path):
            continue  # 削除されたファイル（trashへ移動済み等）はスナップショット対象外
        snapshot_id = _save_snapshot(abs_path)
        if snapshot_id:
            rel_path = os.path.relpath(abs_path, DATA_DIR).replace("\\", "/")
            changed.append({"path": rel_path, "snapshot": snapshot_id})
    return changed


def get_diff(rel_path, snapshot_id):
    """指定したスナップショットと、その「直前」のスナップショットとの差分を返す。
    直前が無い場合（そのファイルの最初の記録）は新規ファイル扱いとして全体を追加差分にする。"""
    abs_path = os.path.join(DATA_DIR, *rel_path.split("/"))
    hist_dir = _history_dir_for(abs_path)
    ids = _list_snapshot_ids(abs_path)
    if snapshot_id not in ids:
        return {"diffText": None, "summary": "指定されたスナップショットは見つかりません（保存件数の上限で削除された可能性があります）"}

    def _read(sid):
        with open(os.path.join(hist_dir, f"{sid}.json"), "r", encoding="utf-8") as f:
            return f.read()

    idx = ids.index(snapshot_id)
    after_text = _read(snapshot_id)
    before_text = _read(ids[idx - 1]) if idx > 0 else ""
    from_label = f"{rel_path} ({ids[idx - 1]})" if idx > 0 else "/dev/null"

    diff_lines = list(difflib.unified_diff(
        before_text.splitlines(keepends=True),
        after_text.splitlines(keepends=True),
        fromfile=from_label,
        tofile=f"{rel_path} ({snapshot_id})",
    ))
    if not diff_lines:
        return {"diffText": "", "summary": "差分はありません（内容は同一です）"}
    return {"diffText": "".join(diff_lines), "summary": None}


def register(app, data_dir):
    from flask import g, request, jsonify
    import pythonSrc.activity_log as activity_log

    init(data_dir)

    @app.before_request
    def _history_before():
        if request.method in _STATE_CHANGING_METHODS and request.path.startswith("/api/"):
            g._history_before_mtimes = snapshot_mtimes()

    @app.after_request
    def _history_after(response):
        before = getattr(g, "_history_before_mtimes", None)
        if before is not None and 200 <= response.status_code < 300:
            changed = record_changes_for_request(before)
            if changed:
                activity_log.attach_changed_files(changed)
        return response

    @app.route("/api/history-diff", methods=["GET"])
    def history_diff():
        rel_path = request.args.get("path")
        snapshot_id = request.args.get("snapshot")
        if not rel_path or not snapshot_id:
            return jsonify({"error": "path と snapshot は必須です"}), 400
        return jsonify(get_diff(rel_path, snapshot_id))
