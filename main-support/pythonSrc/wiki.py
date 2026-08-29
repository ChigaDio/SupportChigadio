# -*- coding: utf-8 -*-
"""
pythonSrc/wiki.py

MediaWiki風の社内ドキュメントページ機能。
DATA_DIR配下に素のMarkdownファイルとして保存するため、他のカテゴリと同様に
pythonSrc/vcs.py のGit/SVN操作対象にそのまま含まれる（差分もgit diff等で
そのまま追える）。

保存レイアウト:
  <DATA_DIR>/wiki/pages/<slug>.md    本文（"/"を含むslugはサブフォルダになる。
                                      MediaWikiのサブページのような使い方ができる）
  <DATA_DIR>/wiki/meta/<slugを"__"区切りにflattenした名前>.json
                                      {title, tags, createdAt, createdBy,
                                       updatedAt, updatedBy, viewUsers, editUsers}
                                      viewUsers/editUsersがnullの場合は
                                      既定権限（下記）が適用される。
  <DATA_DIR>/wiki/history/<flatten slug>/<timestamp>.md
                                      上書き前のスナップショット
                                      （pythonSrc/history.pyと同じ「保存前に退避」方式）

権限（サーバーモード時のみ適用。ローカルモードは全操作可）:
  - 未ログイン           : 閲覧・編集とも不可
  - admin                : 常に閲覧・編集・ACL設定可
  - viewUsers/editUsersが
    未設定(null)のページ : 閲覧=ログイン済み全員 / 編集=admin・editorロール
  - viewUsers/editUsersが
    設定済みのページ     : 閲覧/編集ともリスト内usernameのみ（adminは常に可）
  ACLの設定自体はadminのみ実行できる。
"""
import os
import re
import json
import shutil
import difflib
import threading
from datetime import datetime

DATA_DIR = None
SERVER_MODE = False
_lock = threading.Lock()
_MAX_SNAPSHOTS = 50

_SLUG_SEGMENT_RE = re.compile(r'^[^/\\]+$')


def _pages_dir():
    return os.path.join(DATA_DIR, "wiki", "pages")


def _meta_dir():
    return os.path.join(DATA_DIR, "wiki", "meta")


def _history_dir():
    return os.path.join(DATA_DIR, "wiki", "history")


def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    os.makedirs(_pages_dir(), exist_ok=True)
    os.makedirs(_meta_dir(), exist_ok=True)
    os.makedirs(_history_dir(), exist_ok=True)


def _validate_slug(slug):
    if not slug or slug.startswith("/") or "\\" in slug:
        raise ValueError("不正なページ名です")
    for part in slug.split("/"):
        if not part or part in (".", "..") or not _SLUG_SEGMENT_RE.match(part):
            raise ValueError(f"不正なページ名です: {part}")
    return slug


def _flatten(slug):
    return slug.replace("/", "__")


def _page_path(slug):
    return os.path.join(_pages_dir(), *slug.split("/")) + ".md"


def _meta_path(slug):
    return os.path.join(_meta_dir(), _flatten(slug) + ".json")


def _history_slug_dir(slug):
    return os.path.join(_history_dir(), _flatten(slug))


def _slug_from_rel(rel_from_data):
    """DATA_DIRからの相対パス(posix)がwiki配下のものであれば対応する
    ページslugを返す。wiki配下でなければNone。
    pythonSrc/vcs.py が変更ファイルの権限判定に使う。
    （注意: slugに元々"__"が含まれる場合は正しく復元できない簡易実装）"""
    parts = rel_from_data.split("/")
    if len(parts) < 3 or parts[0] != "wiki":
        return None
    sub = parts[1]
    if sub == "pages":
        s = "/".join(parts[2:])
        return s[:-3] if s.endswith(".md") else s
    if sub in ("meta", "history"):
        name = parts[2]
        flat = name[:-5] if name.endswith(".json") else name
        return flat.replace("__", "/")
    return None


# ---------------------------------------------------------------
# メタ・本文の読み書き
# ---------------------------------------------------------------

def _load_meta(slug):
    path = _meta_path(slug)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _save_meta(slug, meta):
    with open(_meta_path(slug), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_body(slug):
    path = _page_path(slug)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _can_view(meta, user):
    if user is None:
        return not SERVER_MODE
    if user.get("role") == "admin":
        return True
    view_users = (meta or {}).get("viewUsers")
    if view_users is None:
        return True
    return user.get("username") in view_users


def _can_edit(meta, user):
    if not SERVER_MODE:
        return True
    if user is None:
        return False
    if user.get("role") == "admin":
        return True
    edit_users = (meta or {}).get("editUsers")
    if edit_users is not None:
        return user.get("username") in edit_users
    return user.get("role") == "editor"


def can_manage_path(rel_from_data, user):
    """pythonSrc/vcs.py から呼ばれる、Git/SVN差分一覧でのパス単位可視判定。
    wiki配下でなければNoneを返す（＝呼び出し側で従来通り扱わせる）。"""
    slug = _slug_from_rel(rel_from_data)
    if slug is None:
        return None
    return _can_edit(_load_meta(slug), user)


# ---------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------

def list_pages(query=None, tag=None, user=None):
    items = []
    if not os.path.isdir(_meta_dir()):
        return items
    for fname in os.listdir(_meta_dir()):
        if not fname.endswith(".json"):
            continue
        slug = fname[:-5].replace("__", "/")
        meta = _load_meta(slug)
        if meta is None or not _can_view(meta, user):
            continue
        if tag and tag not in (meta.get("tags") or []):
            continue
        if query:
            q = query.lower()
            body = _load_body(slug) or ""
            hay_title = (meta.get("title") or "").lower()
            hay_tags = " ".join(meta.get("tags") or []).lower()
            if q not in hay_title and q not in body.lower() and q not in hay_tags:
                continue
        items.append({
            "slug": slug, "title": meta.get("title", slug), "tags": meta.get("tags", []),
            "updatedAt": meta.get("updatedAt"), "updatedBy": meta.get("updatedBy"),
            "restricted": meta.get("viewUsers") is not None or meta.get("editUsers") is not None,
        })
    items.sort(key=lambda p: p.get("updatedAt") or "", reverse=True)
    return items


def list_tags():
    tags = set()
    if os.path.isdir(_meta_dir()):
        for fname in os.listdir(_meta_dir()):
            if fname.endswith(".json"):
                meta = _load_meta(fname[:-5].replace("__", "/"))
                if meta:
                    tags.update(meta.get("tags") or [])
    return sorted(tags)


def get_page(slug, user):
    _validate_slug(slug)
    meta = _load_meta(slug)
    if meta is None:
        return None, "not_found"
    if not _can_view(meta, user):
        return None, "forbidden"
    body = _load_body(slug) or ""
    return {**meta, "slug": slug, "body": body, "canEdit": _can_edit(meta, user)}, None


def _snapshot(slug):
    body = _load_body(slug)
    if body is None:
        return
    hist_dir = _history_slug_dir(slug)
    os.makedirs(hist_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    with open(os.path.join(hist_dir, f"{ts}.md"), "w", encoding="utf-8") as f:
        f.write(body)
    files = sorted(f for f in os.listdir(hist_dir) if f.endswith(".md"))
    if len(files) > _MAX_SNAPSHOTS:
        for f in files[: len(files) - _MAX_SNAPSHOTS]:
            try:
                os.remove(os.path.join(hist_dir, f))
            except OSError:
                pass


def save_page(slug, title, body, tags, user):
    _validate_slug(slug)
    with _lock:
        meta = _load_meta(slug)
        is_new = meta is None
        if not is_new and not _can_edit(meta, user):
            raise PermissionError("このページを編集する権限がありません")
        if is_new and SERVER_MODE and user is not None and user.get("role") not in ("admin", "editor"):
            raise PermissionError("ページを作成する権限がありません")
        if is_new and SERVER_MODE and user is None:
            raise PermissionError("ログインが必要です")

        if not is_new:
            _snapshot(slug)

        page_path = _page_path(slug)
        os.makedirs(os.path.dirname(page_path), exist_ok=True)
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(body or "")

        now = datetime.now().isoformat(timespec="seconds")
        username = (user or {}).get("username") if SERVER_MODE else "local"
        new_meta = {
            "title": (title or slug).strip(),
            "tags": tags or [],
            "createdAt": meta.get("createdAt") if meta else now,
            "createdBy": meta.get("createdBy") if meta else username,
            "updatedAt": now,
            "updatedBy": username,
            "viewUsers": meta.get("viewUsers") if meta else None,
            "editUsers": meta.get("editUsers") if meta else None,
        }
        _save_meta(slug, new_meta)
    return new_meta


def delete_page(slug, user):
    _validate_slug(slug)
    meta = _load_meta(slug)
    if meta is None:
        raise FileNotFoundError("ページが見つかりません")
    if not _can_edit(meta, user):
        raise PermissionError("このページを削除する権限がありません")
    page_path = _page_path(slug)
    if os.path.isfile(page_path):
        os.remove(page_path)
    meta_path = _meta_path(slug)
    if os.path.isfile(meta_path):
        os.remove(meta_path)
    hist_dir = _history_slug_dir(slug)
    if os.path.isdir(hist_dir):
        shutil.rmtree(hist_dir, ignore_errors=True)


def set_acl(slug, view_users, edit_users, user):
    if SERVER_MODE and (user is None or user.get("role") != "admin"):
        raise PermissionError("閲覧・編集権限の設定は管理人のみ行えます")
    meta = _load_meta(slug)
    if meta is None:
        raise FileNotFoundError("ページが見つかりません")
    meta["viewUsers"] = view_users
    meta["editUsers"] = edit_users
    _save_meta(slug, meta)
    return meta


def list_history(slug, user):
    meta = _load_meta(slug)
    if meta is None or not _can_view(meta, user):
        raise PermissionError("閲覧権限がありません")
    hist_dir = _history_slug_dir(slug)
    if not os.path.isdir(hist_dir):
        return []
    return sorted((f[:-3] for f in os.listdir(hist_dir) if f.endswith(".md")), reverse=True)


def get_history_diff(slug, snapshot_id, user):
    meta = _load_meta(slug)
    if meta is None or not _can_view(meta, user):
        raise PermissionError("閲覧権限がありません")
    hist_dir = _history_slug_dir(slug)
    snapshots = sorted(f[:-3] for f in os.listdir(hist_dir)) if os.path.isdir(hist_dir) else []
    if snapshot_id not in snapshots:
        return None, "指定されたスナップショットは見つかりません"
    idx = snapshots.index(snapshot_id)

    def _read(sid):
        with open(os.path.join(hist_dir, f"{sid}.md"), "r", encoding="utf-8") as f:
            return f.read()

    after = _read(snapshot_id)
    before = _read(snapshots[idx - 1]) if idx > 0 else ""
    diff_lines = list(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"{slug} ({snapshots[idx-1]})" if idx > 0 else "/dev/null",
        tofile=f"{slug} ({snapshot_id})",
    ))
    if not diff_lines:
        return "", "差分はありません"
    return "".join(diff_lines), None


def restore_snapshot(slug, snapshot_id, user):
    meta = _load_meta(slug)
    if meta is None:
        raise FileNotFoundError("ページが見つかりません")
    if not _can_edit(meta, user):
        raise PermissionError("編集権限がありません")
    hist_dir = _history_slug_dir(slug)
    snap_path = os.path.join(hist_dir, f"{snapshot_id}.md")
    if not os.path.isfile(snap_path):
        raise FileNotFoundError("指定されたスナップショットが見つかりません")
    _snapshot(slug)
    with open(snap_path, "r", encoding="utf-8") as f:
        content = f.read()
    with open(_page_path(slug), "w", encoding="utf-8") as f:
        f.write(content)
    meta["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    meta["updatedBy"] = (user or {}).get("username") if SERVER_MODE else "local"
    _save_meta(slug, meta)


# ---------------------------------------------------------------
# ルート登録
# ---------------------------------------------------------------

def register(app, data_dir, server_mode=False):
    from flask import jsonify, request
    import pythonSrc.auth as auth

    global SERVER_MODE
    init(data_dir)
    SERVER_MODE = server_mode

    def _user():
        return auth.current_user() if SERVER_MODE else None

    @app.route("/api/wiki/pages", methods=["GET"])
    def wiki_list():
        return jsonify(list_pages(request.args.get("q"), request.args.get("tag"), _user()))

    @app.route("/api/wiki/tags", methods=["GET"])
    def wiki_tags():
        return jsonify(list_tags())

    @app.route("/api/wiki/pages/<path:slug>", methods=["GET"])
    def wiki_get(slug):
        try:
            page, err = get_page(slug, _user())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if err == "not_found":
            return jsonify({"error": "ページが見つかりません", "exists": False}), 404
        if err == "forbidden":
            return jsonify({"error": "このページを閲覧する権限がありません"}), 403
        return jsonify(page)

    @app.route("/api/wiki/pages/<path:slug>", methods=["POST"])
    def wiki_save(slug):
        body = request.get_json(silent=True) or {}
        try:
            meta = save_page(slug, body.get("title"), body.get("body", ""), body.get("tags"), _user())
            return jsonify({"message": "保存しました", "meta": meta})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

    @app.route("/api/wiki/pages/<path:slug>", methods=["DELETE"])
    def wiki_delete(slug):
        try:
            delete_page(slug, _user())
            return jsonify({"message": "削除しました"})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

    @app.route("/api/wiki/pages/<path:slug>/acl", methods=["PUT"])
    def wiki_acl(slug):
        body = request.get_json(silent=True) or {}
        try:
            meta = set_acl(slug, body.get("viewUsers"), body.get("editUsers"), _user())
            return jsonify({"message": "権限を更新しました", "meta": meta})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

    @app.route("/api/wiki/pages/<path:slug>/history", methods=["GET"])
    def wiki_history(slug):
        try:
            return jsonify(list_history(slug, _user()))
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

    @app.route("/api/wiki/pages/<path:slug>/history/<snapshot_id>/diff", methods=["GET"])
    def wiki_history_diff(slug, snapshot_id):
        try:
            diff_text, summary = get_history_diff(slug, snapshot_id, _user())
            return jsonify({"diffText": diff_text, "summary": summary})
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

    @app.route("/api/wiki/pages/<path:slug>/restore", methods=["POST"])
    def wiki_restore(slug):
        body = request.get_json(silent=True) or {}
        try:
            restore_snapshot(slug, body.get("snapshot"), _user())
            return jsonify({"message": "復元しました"})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
