# -*- coding: utf-8 -*-
"""
pythonSrc/documents.py

仕様書などのファイル（PDF/Word/Excel/テキスト等）をアップロード・閲覧・
ダウンロードするための、DATA_DIR配下のシンプルなドキュメントリポジトリ。
サブフォルダ、検索・タグでの絞り込み、アップロード後のタグ編集に対応する。

保存レイアウト:
  <DATA_DIR>/documents/                        ルート
  <DATA_DIR>/documents/<...任意のサブフォルダ.../ファイル本体>
  <同フォルダ>/.<ファイル名>.tags.json           サイドカーメタ
                                                {tags, description,
                                                 uploadedBy, uploadedAt}
  <folder>/.acl.json                           そのフォルダ配下（サブフォルダ込み、
                                                より近い階層の.acl.jsonが優先）の
                                                閲覧・編集を制限するACL。
                                                {viewUsers, editUsers}
                                                （nullなら制限なし）

ファイル本体は普通のファイルとしてそのまま保存するため、他のカテゴリ同様に
pythonSrc/vcs.py のGit/SVN操作対象にそのまま含まれる。

削除は誤操作対策のため pythonSrc/trash.py 経由で行う（ゴミ箱ページから復元可能）。

権限（サーバーモード時のみ適用。ローカルモードは全操作可）:
  admin=常に可 / 未ログイン=不可 / それ以外は直近の祖先フォルダの.acl.json
  （無ければ 閲覧=ログイン済み全員・編集=admin/editorロール）に従う。
"""
import os
import io
import json
import mimetypes
import zipfile
from datetime import datetime

DATA_DIR = None
SERVER_MODE = False

_TAGS_SUFFIX = ".tags.json"
_ACL_FILENAME = ".acl.json"


def _root():
    return os.path.join(DATA_DIR, "documents")


def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    os.makedirs(_root(), exist_ok=True)


def _validate_rel(rel_path):
    """documentsルートからの相対パス(posix)を検証し、絶対パスを返す。
    正規化後にルート外へ出ないことを確認し、パストラバーサルを防ぐ。"""
    rel_path = (rel_path or "").strip().strip("/")
    abs_path = os.path.normpath(os.path.join(_root(), *rel_path.split("/"))) if rel_path else _root()
    if os.path.commonpath([abs_path, _root()]) != os.path.normpath(_root()):
        raise ValueError("不正なパスです")
    return abs_path


def _rel(abs_path):
    return os.path.relpath(abs_path, _root()).replace("\\", "/")


def _is_hidden(name):
    return name.startswith(".")


def _tags_sidecar_path(file_abs_path):
    d = os.path.dirname(file_abs_path)
    return os.path.join(d, "." + os.path.basename(file_abs_path) + _TAGS_SUFFIX)


def _load_sidecar(file_abs_path):
    p = _tags_sidecar_path(file_abs_path)
    if not os.path.isfile(p):
        return {"tags": [], "description": ""}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"tags": [], "description": ""}


def _save_sidecar(file_abs_path, data):
    with open(_tags_sidecar_path(file_abs_path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------
# ACL（フォルダ単位、直近の祖先が優先）
# ---------------------------------------------------------------

def _find_acl(dir_abs_path):
    cur = os.path.abspath(dir_abs_path)
    root = os.path.abspath(_root())
    while True:
        acl_path = os.path.join(cur, _ACL_FILENAME)
        if os.path.isfile(acl_path):
            try:
                with open(acl_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return None
        if cur == root:
            return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _can_view(acl, user):
    if user is None:
        return not SERVER_MODE
    if user.get("role") == "admin":
        return True
    view_users = (acl or {}).get("viewUsers")
    if view_users is None:
        return True
    return user.get("username") in view_users


def _can_edit(acl, user):
    if not SERVER_MODE:
        return True
    if user is None:
        return False
    if user.get("role") == "admin":
        return True
    edit_users = (acl or {}).get("editUsers")
    if edit_users is not None:
        return user.get("username") in edit_users
    return user.get("role") == "editor"


def _dir_of(rel_path):
    abs_path = _validate_rel(rel_path)
    return abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)


def can_manage_path(rel_from_data, user):
    """pythonSrc/vcs.py から呼ばれる、Git/SVN差分一覧でのパス単位可視判定。
    documents配下でなければNoneを返す。"""
    parts = rel_from_data.split("/")
    if not parts or parts[0] != "documents":
        return None
    rel_in_docs = "/".join(parts[1:])
    if not rel_in_docs:
        return True
    try:
        target_dir = _dir_of(rel_in_docs)
    except ValueError:
        return False
    return _can_edit(_find_acl(target_dir), user)


# ---------------------------------------------------------------
# 一覧・検索
# ---------------------------------------------------------------

def _entry_info(abs_path, user):
    is_dir = os.path.isdir(abs_path)
    acl = _find_acl(abs_path if is_dir else os.path.dirname(abs_path))
    if not _can_view(acl, user):
        return None
    sidecar = {} if is_dir else _load_sidecar(abs_path)
    stat = os.stat(abs_path)
    return {
        "name": os.path.basename(abs_path),
        "path": _rel(abs_path),
        "type": "folder" if is_dir else "file",
        "ext": "" if is_dir else os.path.splitext(abs_path)[1].lower().lstrip("."),
        "sizeBytes": None if is_dir else stat.st_size,
        "modifiedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "tags": sidecar.get("tags", []),
        "description": sidecar.get("description", ""),
        "editable": _can_edit(acl, user),
    }


def list_dir(rel_path, user):
    abs_dir = _validate_rel(rel_path)
    if not os.path.isdir(abs_dir):
        raise FileNotFoundError("フォルダが見つかりません")
    if not _can_view(_find_acl(abs_dir), user):
        raise PermissionError("このフォルダを閲覧する権限がありません")
    entries = []
    for name in sorted(os.listdir(abs_dir)):
        if _is_hidden(name):
            continue
        info = _entry_info(os.path.join(abs_dir, name), user)
        if info:
            entries.append(info)
    entries.sort(key=lambda e: (e["type"] != "folder", e["name"].lower()))
    return entries


def search(query, tag, user):
    results = []
    q = (query or "").lower().strip()
    for root, dirs, files in os.walk(_root()):
        dirs[:] = [d for d in dirs if not _is_hidden(d)]
        for name in files:
            if _is_hidden(name):
                continue
            info = _entry_info(os.path.join(root, name), user)
            if not info:
                continue
            if tag and tag not in info["tags"]:
                continue
            if q and q not in info["name"].lower() and not any(q in t.lower() for t in info["tags"]):
                continue
            results.append(info)
    results.sort(key=lambda e: e["modifiedAt"], reverse=True)
    return results


def list_all_tags():
    tags = set()
    for root, dirs, files in os.walk(_root()):
        dirs[:] = [d for d in dirs if not _is_hidden(d)]
        for name in files:
            if name.endswith(_TAGS_SUFFIX):
                try:
                    with open(os.path.join(root, name), "r", encoding="utf-8") as f:
                        tags.update(json.load(f).get("tags", []))
                except (OSError, json.JSONDecodeError):
                    continue
    return sorted(tags)


# ---------------------------------------------------------------
# アップロード・タグ編集・フォルダ作成・削除・ダウンロード
# ---------------------------------------------------------------

def mkdir(rel_path, user):
    abs_path = _validate_rel(rel_path)
    if not _can_edit(_find_acl(os.path.dirname(abs_path) or _root()), user):
        raise PermissionError("このフォルダにアイテムを作成する権限がありません")
    os.makedirs(abs_path, exist_ok=True)


def save_upload(rel_dir, file_storage, tags, description, user):
    abs_dir = _validate_rel(rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    if not _can_edit(_find_acl(abs_dir), user):
        raise PermissionError("このフォルダへアップロードする権限がありません")
    from werkzeug.utils import secure_filename
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        raise ValueError("ファイル名が不正です")
    dest = os.path.join(abs_dir, filename)
    file_storage.save(dest)
    _save_sidecar(dest, {
        "tags": tags or [],
        "description": description or "",
        "uploadedBy": (user or {}).get("username") if SERVER_MODE else "local",
        "uploadedAt": datetime.now().isoformat(timespec="seconds"),
    })
    return _rel(dest)


def update_meta(rel_path, tags, description, user):
    abs_path = _validate_rel(rel_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError("ファイルが見つかりません")
    if not _can_edit(_find_acl(os.path.dirname(abs_path)), user):
        raise PermissionError("このファイルのタグを編集する権限がありません")
    sidecar = _load_sidecar(abs_path)
    if tags is not None:
        sidecar["tags"] = tags
    if description is not None:
        sidecar["description"] = description
    _save_sidecar(abs_path, sidecar)
    return sidecar


def delete_item(rel_path, user):
    import pythonSrc.trash as trash
    abs_path = _validate_rel(rel_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError("見つかりません")
    is_dir = os.path.isdir(abs_path)
    if not _can_edit(_find_acl(abs_path if is_dir else os.path.dirname(abs_path)), user):
        raise PermissionError("削除する権限がありません")
    if not is_dir:
        sidecar_path = _tags_sidecar_path(abs_path)
        if os.path.isfile(sidecar_path):
            try:
                os.remove(sidecar_path)
            except OSError:
                pass
    trash.move_to_trash("documents", os.path.basename(abs_path), abs_path)


def build_zip(rel_path):
    abs_path = _validate_rel(rel_path)
    if not os.path.isdir(abs_path):
        raise FileNotFoundError("フォルダが見つかりません")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(abs_path):
            dirs[:] = [d for d in dirs if not _is_hidden(d)]
            for name in files:
                if _is_hidden(name):
                    continue
                full = os.path.join(root, name)
                zf.write(full, os.path.relpath(full, abs_path))
    buf.seek(0)
    return buf


def set_acl(rel_path, view_users, edit_users, user):
    if SERVER_MODE and (user is None or user.get("role") != "admin"):
        raise PermissionError("閲覧・編集権限の設定は管理人のみ行えます")
    abs_dir = _validate_rel(rel_path)
    if not os.path.isdir(abs_dir):
        raise FileNotFoundError("フォルダが見つかりません")
    acl_path = os.path.join(abs_dir, _ACL_FILENAME)
    if view_users is None and edit_users is None:
        if os.path.isfile(acl_path):
            os.remove(acl_path)
        return None
    data = {"viewUsers": view_users, "editUsers": edit_users}
    with open(acl_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


# ---------------------------------------------------------------
# ルート登録
# ---------------------------------------------------------------

def register(app, data_dir, server_mode=False):
    from flask import jsonify, request, send_file
    import pythonSrc.auth as auth

    global SERVER_MODE
    init(data_dir)
    SERVER_MODE = server_mode

    def _user():
        return auth.current_user() if SERVER_MODE else None

    @app.route("/api/documents/list", methods=["GET"])
    def documents_list():
        rel_path = request.args.get("path", "")
        try:
            entries = list_dir(rel_path, _user())
            return jsonify({"path": rel_path, "entries": entries})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/documents/search", methods=["GET"])
    def documents_search():
        return jsonify({"entries": search(request.args.get("q"), request.args.get("tag"), _user())})

    @app.route("/api/documents/tags", methods=["GET"])
    def documents_tags():
        return jsonify(list_all_tags())

    @app.route("/api/documents/raw/<path:rel_path>", methods=["GET"])
    def documents_raw(rel_path):
        try:
            abs_path = _validate_rel(rel_path)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if not os.path.isfile(abs_path):
            return jsonify({"error": "ファイルが見つかりません"}), 404
        if not _can_view(_find_acl(os.path.dirname(abs_path)), _user()):
            return jsonify({"error": "閲覧権限がありません"}), 403
        mimetype = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
        download = request.args.get("download") == "1"
        return send_file(abs_path, mimetype=mimetype, as_attachment=download,
                          download_name=os.path.basename(abs_path))

    @app.route("/api/documents/download-zip", methods=["GET"])
    def documents_download_zip():
        rel_path = request.args.get("path", "")
        try:
            abs_dir = _validate_rel(rel_path)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if not _can_view(_find_acl(abs_dir), _user()):
            return jsonify({"error": "閲覧権限がありません"}), 403
        try:
            buf = build_zip(rel_path)
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        name = os.path.basename(abs_dir.rstrip(os.sep)) or "documents"
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{name}.zip")

    @app.route("/api/documents/mkdir", methods=["POST"])
    def documents_mkdir():
        body = request.get_json(silent=True) or {}
        try:
            mkdir(body.get("path", ""), _user())
            return jsonify({"message": "フォルダを作成しました"})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

    @app.route("/api/documents/upload", methods=["POST"])
    def documents_upload():
        rel_dir = request.form.get("path", "")
        tags = [t.strip() for t in (request.form.get("tags") or "").split(",") if t.strip()]
        description = request.form.get("description", "")
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "アップロードするファイルが選択されていません"}), 400
        saved, errors = [], []
        for fs in files:
            try:
                saved.append(save_upload(rel_dir, fs, tags, description, _user()))
            except (ValueError, PermissionError) as e:
                errors.append(str(e))
        if not saved and errors:
            return jsonify({"error": errors[0]}), 403
        return jsonify({"message": f"{len(saved)}件アップロードしました", "saved": saved, "errors": errors})

    @app.route("/api/documents/meta", methods=["PUT"])
    def documents_meta():
        rel_path = request.args.get("path", "")
        body = request.get_json(silent=True) or {}
        try:
            sidecar = update_meta(rel_path, body.get("tags"), body.get("description"), _user())
            return jsonify({"message": "更新しました", "meta": sidecar})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

    @app.route("/api/documents/item", methods=["DELETE"])
    def documents_delete():
        rel_path = request.args.get("path", "")
        try:
            delete_item(rel_path, _user())
            return jsonify({"message": "ゴミ箱へ移動しました"})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

    @app.route("/api/documents/acl", methods=["PUT"])
    def documents_set_acl():
        rel_path = request.args.get("path", "")
        body = request.get_json(silent=True) or {}
        try:
            data = set_acl(rel_path, body.get("viewUsers"), body.get("editUsers"), _user())
            return jsonify({"message": "権限を更新しました", "acl": data})
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
