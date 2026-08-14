# -*- coding: utf-8 -*-
"""
pythonSrc/announcements.py

管理人・編集者が作成できるお知らせページ（Markdown形式）。
`<DATA_DIR>/announcements/<id>.md` に、先頭にJSONメタデータ行、
続けて本文(Markdown)を保存するシンプルな形式で保存する。
"""
import os
import json
import threading
from datetime import datetime

from flask import request, jsonify

_lock = threading.Lock()
_DIR = None

META_MARK = "<!--META:"
META_MARK_END = "-->"


def _dir():
    return _DIR


def _path(ann_id):
    return os.path.join(_DIR, f"{ann_id}.md")


def _write(ann_id, meta, body):
    with open(_path(ann_id), "w", encoding="utf-8") as f:
        f.write(META_MARK + json.dumps(meta, ensure_ascii=False) + META_MARK_END + "\n")
        f.write(body)


def _read(ann_id):
    path = _path(ann_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if content.startswith(META_MARK):
        # メタ情報は常に1行目のみに書き込まれる（_write参照）。
        # 以前は「本文全体から最初に見つかった META_MARK_END("-->") まで」を
        # メタ情報として扱っていたため、タイトルなどメタの値自体に "-->" と
        # いう文字列（矢印表記などでありがち）が含まれると、そこで誤って
        # JSON文字列が途中で打ち切られ、JSONDecodeErrorでお知らせ自体が
        # 読み込めなくなる不具合があった。
        # メタ行は必ず1行目にあり、末尾は必ず META_MARK_END で終わる
        # （_writeが常にその形式で書き込むため）。よって「本文中を検索する」
        # のではなく「1行目の末尾から固定長で切り取る」方式にすることで、
        # メタの値に "-->" が何度含まれても安全にパースできるようにする。
        first_newline = content.find("\n")
        meta_line = content if first_newline == -1 else content[:first_newline]
        body = "" if first_newline == -1 else content[first_newline + 1:]
        if meta_line.endswith(META_MARK_END):
            meta_json = meta_line[len(META_MARK):-len(META_MARK_END)]
            try:
                meta = json.loads(meta_json)
            except json.JSONDecodeError:
                meta = {"id": ann_id, "title": ann_id}
        else:
            meta = {"id": ann_id, "title": ann_id}
    else:
        meta = {"id": ann_id, "title": ann_id}
        body = content
    meta["id"] = ann_id
    meta["body"] = body
    return meta


def _list_ids():
    if not os.path.isdir(_DIR):
        return []
    return [f[:-3] for f in os.listdir(_DIR) if f.endswith(".md")]


def list_all(query=None):
    items = []
    for ann_id in _list_ids():
        data = _read(ann_id)
        if data is None:
            continue
        if query:
            q = query.lower()
            if q not in data.get("title", "").lower() and q not in data.get("body", "").lower():
                continue
        items.append(data)
    items.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return items


def register(app, data_dir):
    global _DIR
    _DIR = os.path.join(data_dir, "announcements")
    os.makedirs(_DIR, exist_ok=True)

    import pythonSrc.auth as auth

    def _can_write(user):
        return user is not None and user["role"] in ("admin", "editor")

    @app.route("/api/announcements", methods=["GET"])
    def announcements_list():
        query = request.args.get("q")
        items = list_all(query)
        # 一覧では本文は概要のみ返す
        summary = []
        for it in items:
            body = it.get("body", "")
            summary.append({
                "id": it["id"],
                "title": it.get("title", it["id"]),
                "author": it.get("author"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "excerpt": body.strip().splitlines()[0][:120] if body.strip() else "",
            })
        return jsonify(summary)

    @app.route("/api/announcements/<ann_id>", methods=["GET"])
    def announcements_get(ann_id):
        data = _read(ann_id)
        if data is None:
            return jsonify({"error": "見つかりません"}), 404
        return jsonify(data)

    @app.route("/api/announcements", methods=["POST"])
    def announcements_create():
        user = auth.current_user()
        if not _can_write(user):
            return jsonify({"error": "お知らせを作成する権限がありません"}), 403
        body = request.get_json() or {}
        title = (body.get("title") or "").strip()
        content = body.get("body", "")
        if not title:
            return jsonify({"error": "タイトルは必須です"}), 400
        with _lock:
            ann_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
            meta = {
                "title": title,
                "author": user["username"] if user else "system",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            _write(ann_id, meta, content)
        return jsonify({"message": "お知らせを作成しました", "id": ann_id}), 201

    @app.route("/api/announcements/<ann_id>", methods=["PUT"])
    def announcements_update(ann_id):
        user = auth.current_user()
        existing = _read(ann_id)
        if existing is None:
            return jsonify({"error": "見つかりません"}), 404
        if not _can_write(user):
            return jsonify({"error": "編集する権限がありません"}), 403
        if user["role"] == "editor" and existing.get("author") != user["username"]:
            return jsonify({"error": "自分が作成したお知らせのみ編集できます"}), 403
        body = request.get_json() or {}
        meta = {
            "title": body.get("title", existing.get("title")),
            "author": existing.get("author"),
            "created_at": existing.get("created_at"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write(ann_id, meta, body.get("body", existing.get("body", "")))
        return jsonify({"message": "更新しました"})

    @app.route("/api/announcements/<ann_id>", methods=["DELETE"])
    def announcements_delete(ann_id):
        user = auth.current_user()
        existing = _read(ann_id)
        if existing is None:
            return jsonify({"error": "見つかりません"}), 404
        if not _can_write(user):
            return jsonify({"error": "削除する権限がありません"}), 403
        if user["role"] == "editor" and existing.get("author") != user["username"]:
            return jsonify({"error": "自分が作成したお知らせのみ削除できます"}), 403
        os.remove(_path(ann_id))
        return jsonify({"message": "削除しました"})
