# -*- coding: utf-8 -*-
"""
pythonSrc/vcs.py

DATA_DIR自体、もしくはその祖先ディレクトリを再帰的に遡った先がGit/SVNの
リポジトリになっている場合に、フェッチ/プル/プッシュ（コミット込み）/
マージ/ブランチ作成・切り替え/コミットグラフをWeb UIから操作できるように
するモジュール。

対応VCS: Git / Subversion（それぞれの公式CLI `git` / `svn` がサーバー環境の
PATHに存在することが前提。存在しない場合は /api/vcs/status で
repo.available=false を返し、フロントエンド側で案内する）。

権限モデル（サーバーモード時のみ適用。ローカルモードでは全操作・全パスを許可）:
  - viewer : 閲覧のみ。状態・ブランチ・コミットグラフ・差分の取得は可、
             いかなる変更操作（fetch/pull/push/commit/merge/
             ブランチ作成・切替）も403で拒否する。
  - editor : DATA_DIR配下のパスのうち、reference_check.CATEGORY_DIRSで
             定義されたカテゴリに属し、かつそのユーザーがそのカテゴリに
             対する編集権限（all、またはアイテム名一致）を持つパスのみが
             変更一覧・選択（コミット対象）に現れる。該当カテゴリを持たない
             パス（DATA_DIR外や、logs/announcements/assets_data等
             カテゴリ化されていないパス）は一覧から除外される（＝見えない）。
             リポジトリ全体に対する操作であるfetch/pull/merge/ブランチ
             作成・切替は、editorであれば実行できる（個々のファイル権限とは
             独立。コミット対象ファイルの絞り込みのみファイル単位の権限が働く。
             commit実行時はフロント側フィルタを信用せず、選択された全パスを
             サーバー側でも再検証する）。
  - admin  : 全操作・全パスが可能。

fetch/pull/push/commit/mergeは失敗し得る・時間がかかりうる操作のため、
pythonSrc/csproj_sync.py や pythonSrc/generate_all.py と同じ
「バックグラウンドスレッド + メモリ上job辞書 + ポーリングAPI」方式で実行し、
実行中のコマンド出力(stdout+stderr)をそのままjobのlogとしてフロントへ
ストリーミング的に見せる（ポーリング間隔でlogが伸びていく）。
"""
import os
import re
import shutil
import subprocess
import threading
import uuid

DATA_DIR = None
SERVER_MODE = False

_jobs_lock = threading.Lock()
_jobs = {}

_GIT_STATUS_LABELS = {
    'M': '変更', 'A': '追加', 'D': '削除', 'R': '名前変更', 'C': 'コピー',
    'U': '衝突', '?': '未追跡', '!': '無視',
}
_SVN_STATUS_LABELS = {
    'M': '変更', 'A': '追加', 'D': '削除', 'C': '衝突', '?': '未追跡',
    '!': '不足', 'R': '置換',
}


# ---------------------------------------------------------------
# リポジトリ検出
# ---------------------------------------------------------------

def _find_repo_root(start_dir):
    """start_dir自身、もしくはその祖先ディレクトリを再帰的に遡って、
    最初に見つかった .git / .svn を持つディレクトリを返す。
    戻り値: (root_abs_path, "git"|"svn") または (None, None)"""
    cur = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")) or os.path.isfile(os.path.join(cur, ".git")):
            return cur, "git"
        if os.path.isdir(os.path.join(cur, ".svn")):
            return cur, "svn"
        parent = os.path.dirname(cur)
        if parent == cur:
            return None, None
        cur = parent


def _vcs_available(vcs_type):
    return shutil.which("git" if vcs_type == "git" else "svn") is not None


def detect_repo():
    if DATA_DIR is None:
        return None
    root, vcs_type = _find_repo_root(DATA_DIR)
    if not vcs_type:
        return None
    return {
        "type": vcs_type,
        "root": root,
        "dataRelPath": os.path.relpath(DATA_DIR, root).replace("\\", "/"),
        "available": _vcs_available(vcs_type),
    }


# ---------------------------------------------------------------
# subprocess共通
# ---------------------------------------------------------------

def _run(cmd, cwd, timeout=25):
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"コマンドが見つかりません: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", "コマンドがタイムアウトしました"


# ---------------------------------------------------------------
# 権限フィルタ
# ---------------------------------------------------------------

def _category_map():
    from pythonSrc.reference_check import CATEGORY_DIRS
    return CATEGORY_DIRS


def _categorize(rel_from_data_dir):
    """DATA_DIRからの相対パス(posix区切り)を CATEGORY_DIRS と突き合わせ、
    (category, item) を返す。DATA_DIR外、もしくは該当カテゴリなしなら
    (None, None)。"""
    if rel_from_data_dir.startswith(".."):
        return None, None
    parts = rel_from_data_dir.split("/")
    for category, dir_parts in _category_map().items():
        n = len(dir_parts)
        if tuple(parts[:n]) == dir_parts:
            item = parts[n] if len(parts) > n else None
            return category, item
    return None, None


def _user_can_see(user, category, item):
    if user is None:
        return False
    if user.get("role") == "admin":
        return True
    if user.get("role") == "viewer":
        return False
    if category is None:
        return False
    perm = (user.get("permissions") or {}).get(category)
    if not perm:
        return False
    if perm.get("all"):
        return True
    return item is not None and item in (perm.get("items") or [])


def _to_rel_from_data(repo_root, rel_or_abs_path):
    abs_path = rel_or_abs_path if os.path.isabs(rel_or_abs_path) else os.path.join(repo_root, rel_or_abs_path)
    return os.path.relpath(abs_path, DATA_DIR).replace("\\", "/")


def _filter_and_annotate(entries, repo_root, user):
    """変更ファイルエントリ(dict, "path"キーがrepo_root相対)のリストに
    category/item/selectableを付与し、サーバーモード時は非表示にすべき
    項目を除外して返す。"""
    out = []
    for entry in entries:
        rel_from_data = _to_rel_from_data(repo_root, entry["path"])
        category, item = _categorize(rel_from_data)
        visible, selectable = True, True
        if SERVER_MODE:
            if user is not None and user.get("role") == "admin":
                visible, selectable = True, True
            elif user is not None and user.get("role") == "viewer":
                visible, selectable = True, False
            else:
                visible = _user_can_see(user, category, item)
                selectable = visible
        if not visible:
            continue
        out.append({**entry, "category": category, "item": item, "selectable": selectable})
    return out


# ---------------------------------------------------------------
# Git
# ---------------------------------------------------------------

def _git_current_branch(root):
    code, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    return out.strip() if code == 0 else None


def _git_ahead_behind(root):
    code, out, _ = _run(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"], root)
    if code != 0:
        return None
    try:
        ahead_s, behind_s = out.strip().split()
        return {"ahead": int(ahead_s), "behind": int(behind_s)}
    except ValueError:
        return None


def _git_status(root):
    code, out, err = _run(["git", "status", "--porcelain=v1", "-uall"], root)
    if code != 0:
        raise RuntimeError(err or "git status に失敗しました")
    entries = []
    for line in out.splitlines():
        if not line:
            continue
        index_state, wt_state, rest = line[0], line[1], line[3:]
        path = rest.split(" -> ")[-1]
        staged = index_state not in (" ", "?")
        code_char = index_state if index_state != " " else wt_state
        entries.append({
            "path": path,
            "statusCode": code_char,
            "statusLabel": _GIT_STATUS_LABELS.get(code_char, code_char),
            "staged": staged,
        })
    return entries


def _git_branches(root):
    code, out, err = _run(["git", "branch", "-a", "--format=%(refname:short)|%(HEAD)"], root)
    if code != 0:
        raise RuntimeError(err or "ブランチ一覧の取得に失敗しました")
    branches = []
    for line in out.splitlines():
        if not line.strip():
            continue
        name, _, head_marker = line.partition("|")
        branches.append({
            "name": name,
            "current": head_marker.strip() == "*",
            "remote": name.startswith("remotes/"),
        })
    return branches


def _assign_lanes(commits):
    """コミット配列（新しい順）に簡易的なレーン番号を割り当てる。
    「現在アクティブな系譜（レーン）」の配列を管理し、各コミットが
    どのレーンの続きにあたるかで割り当てる単純なアルゴリズム。
    厳密な最適化は行わないが、一般的なブランチ運用であれば
    視覚的に破綻しないグラフになる。"""
    lanes = []  # 各要素は「このレーンが次に期待するコミットid」
    for c in commits:
        lane_idx = None
        for i, expected in enumerate(lanes):
            if expected == c["id"]:
                lane_idx = i
                break
        if lane_idx is None:
            lane_idx = len(lanes)
            lanes.append(c["id"])
        c["lane"] = lane_idx
        parents = c["parents"]
        if parents:
            lanes[lane_idx] = parents[0]
            for extra in parents[1:]:
                if extra not in lanes:
                    lanes.append(extra)
        else:
            lanes[lane_idx] = None
    return commits


def _git_log(root, branch=None, limit=200):
    sep = "\x1f"
    fmt = sep.join(["%H", "%P", "%an", "%ad", "%s", "%D"])
    cmd = ["git", "log", f"--pretty=format:{fmt}", "--date=iso-strict", f"-n{limit}"]
    cmd.append(branch if branch else "--all")
    code, out, err = _run(cmd, root, timeout=25)
    if code != 0:
        raise RuntimeError(err or "コミットログの取得に失敗しました")
    commits = []
    for line in out.splitlines():
        if not line:
            continue
        h, parents, author, date, subject, refs = (line.split(sep) + [""] * 6)[:6]
        commits.append({
            "id": h,
            "parents": [p for p in parents.split(" ") if p],
            "author": author,
            "date": date,
            "message": subject,
            "refs": [r.strip() for r in refs.split(",") if r.strip()],
        })
    return _assign_lanes(commits)


def _git_diff(root, rel_path):
    code, out, err = _run(["git", "diff", "HEAD", "--", rel_path], root)
    if code == 0 and out:
        return out
    # 新規追跡ファイル等でHEAD比較が空になる場合のフォールバック
    code2, out2, _ = _run(["git", "diff", "--no-index", "--", os.devnull, rel_path], root)
    return out2 or "差分はありません（新規ファイル、またはバイナリの可能性があります）"


def _git_fetch(root, log):
    code, out, err = _run(["git", "fetch", "--all", "--prune"], root, timeout=120)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "fetchに失敗しました")


def _git_pull(root, log):
    code, out, err = _run(["git", "pull"], root, timeout=120)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "pullに失敗しました（コンフリクトの可能性があります）")


def _git_push(root, log, set_upstream=False, branch=None):
    cmd = ["git", "push", "--set-upstream", "origin", branch] if (set_upstream and branch) else ["git", "push"]
    code, out, err = _run(cmd, root, timeout=120)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "pushに失敗しました")


def _git_commit(root, log, message, paths):
    if not message.strip():
        raise ValueError("コミットメッセージは必須です")
    if not paths:
        raise ValueError("コミット対象のファイルが選択されていません")
    code, out, err = _run(["git", "add", "--"] + paths, root)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "git add に失敗しました")
    code, out, err = _run(["git", "commit", "-m", message], root)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "commitに失敗しました")


def _git_merge(root, log, branch):
    code, out, err = _run(["git", "merge", branch], root, timeout=120)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or f"{branch} のマージに失敗しました（コンフリクトの可能性があります）")


def _git_branch_create(root, log, name, start_point=None, checkout=False):
    cmd = ["git", "branch", name] + ([start_point] if start_point else [])
    code, out, err = _run(cmd, root)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "ブランチの作成に失敗しました")
    if checkout:
        _git_checkout(root, log, name)


def _git_checkout(root, log, name):
    code, out, err = _run(["git", "checkout", name], root, timeout=60)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or f"{name} への切り替えに失敗しました")


# ---------------------------------------------------------------
# SVN
# ---------------------------------------------------------------

def _svn_status(root):
    code, out, err = _run(["svn", "status"], root)
    if code != 0:
        raise RuntimeError(err or "svn status に失敗しました")
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        code_char = line[0] if line[0] != ' ' else (line[1] if len(line) > 1 else '?')
        path = line[8:].strip() if len(line) > 8 else line[1:].strip()
        if not path:
            continue
        entries.append({
            "path": path,
            "statusCode": code_char,
            "statusLabel": _SVN_STATUS_LABELS.get(code_char, code_char),
            "staged": False,
        })
    return entries


def _svn_info(root):
    code, out, _ = _run(["svn", "info"], root)
    info = {}
    if code == 0:
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
    return info


def _parse_svn_log_block(block_lines):
    header = block_lines[0] if block_lines else ""
    m = re.match(r"r(\d+)\s*\|\s*([^|]*)\|\s*([^|]*)\|", header)
    if not m:
        return None
    rev, author, date = m.groups()
    message = "\n".join(block_lines[2:]).strip() if len(block_lines) > 2 else ""
    return {
        "id": rev, "author": author.strip(), "date": date.strip(),
        "message": message.splitlines()[0] if message else "", "refs": [],
    }


def _svn_log(root, limit=200):
    code, out, err = _run(["svn", "log", "-l", str(limit)], root, timeout=25)
    if code != 0:
        raise RuntimeError(err or "svn log の取得に失敗しました")
    commits, block = [], []
    for line in out.splitlines():
        if line.startswith("---"):
            if block:
                parsed = _parse_svn_log_block(block)
                if parsed:
                    commits.append(parsed)
                block = []
            continue
        block.append(line)
    if block:
        parsed = _parse_svn_log_block(block)
        if parsed:
            commits.append(parsed)
    for i, c in enumerate(commits):
        c["parents"] = [commits[i + 1]["id"]] if i + 1 < len(commits) else []
        c["lane"] = 0
    return commits


def _svn_diff(root, rel_path):
    code, out, err = _run(["svn", "diff", rel_path], root)
    if code != 0:
        raise RuntimeError(err or "diffの取得に失敗しました")
    return out or "差分はありません"


def _svn_branches(root):
    """標準的な trunk/branches/tags レイアウトを仮定し、^/branches を
    一覧する（レイアウトが異なるリポジトリでは trunk のみ返る。
    その場合でも switch はURLを直接指定すれば利用できる）。"""
    info = _svn_info(root)
    repo_root_url = info.get("Repository Root")
    if not repo_root_url:
        return []
    current_url = info.get("URL", "")
    branches = [{"name": "trunk", "url": f"{repo_root_url}/trunk", "current": current_url == f"{repo_root_url}/trunk"}]
    code, out, _ = _run(["svn", "list", f"{repo_root_url}/branches"], root, timeout=15)
    if code == 0:
        for line in out.splitlines():
            name = line.strip().rstrip("/")
            if name:
                url = f"{repo_root_url}/branches/{name}"
                branches.append({"name": name, "url": url, "current": url == current_url})
    return branches


def _svn_update(root, log):
    code, out, err = _run(["svn", "update"], root, timeout=120)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "updateに失敗しました")


def _svn_commit(root, log, message, paths):
    if not message.strip():
        raise ValueError("コミットメッセージは必須です")
    if not paths:
        raise ValueError("コミット対象のファイルが選択されていません")
    code, out, err = _run(["svn", "commit", "-m", message, "--"] + paths, root, timeout=120)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "commitに失敗しました")


def _svn_merge(root, log, source_url):
    code, out, err = _run(["svn", "merge", source_url], root, timeout=120)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "マージに失敗しました（コンフリクトの可能性があります）")


def _svn_branch_create(root, log, name):
    info = _svn_info(root)
    repo_root_url = info.get("Repository Root")
    if not repo_root_url:
        raise RuntimeError("リポジトリURLの取得に失敗しました")
    code, out, err = _run(
        ["svn", "copy", f"{repo_root_url}/trunk", f"{repo_root_url}/branches/{name}", "-m", f"Create branch {name}"],
        root, timeout=60,
    )
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "ブランチの作成に失敗しました")


def _svn_switch(root, log, url):
    code, out, err = _run(["svn", "switch", url], root, timeout=120)
    log(out + err)
    if code != 0:
        raise RuntimeError(err or "switchに失敗しました")


# ---------------------------------------------------------------
# ジョブ管理（fetch/pull/push/commit/merge/branch操作を非同期実行）
# ---------------------------------------------------------------

def _start_job(fn):
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "log": "", "message": "実行中...", "error": None}

    def log(text):
        if not text:
            return
        with _jobs_lock:
            _jobs[job_id]["log"] += text if text.endswith("\n") else text + "\n"

    def _runner():
        try:
            fn(log)
            with _jobs_lock:
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["message"] = "完了しました"
        except Exception as e:
            with _jobs_lock:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["message"] = str(e)
                _jobs[job_id]["error"] = str(e)

    threading.Thread(target=_runner, daemon=True).start()
    return job_id


def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


# ---------------------------------------------------------------
# 初期化・ルート登録
# ---------------------------------------------------------------

def init(data_dir):
    global DATA_DIR
    DATA_DIR = os.path.abspath(data_dir)


def register(app, data_dir, server_mode=False):
    from flask import jsonify, request
    import pythonSrc.auth as auth
    import pythonSrc.activity_log as activity_log

    global SERVER_MODE
    init(data_dir)
    SERVER_MODE = server_mode

    def _require_actor():
        """変更操作の実行者を返す。ローカルモードでは常に許可 (None, None)。
        サーバーモードではログイン必須・viewerロールは拒否する。"""
        if not SERVER_MODE:
            return None, None
        user = auth.current_user()
        if user is None:
            return None, (jsonify({"error": "ログインが必要です"}), 401)
        if user.get("role") == "viewer":
            return None, (jsonify({"error": "閲覧者はこの操作を実行できません"}), 403)
        return user, None

    def _repo_or_404():
        repo = detect_repo()
        if repo is None:
            return None, (jsonify({"error": "data フォルダはGit/SVNリポジトリ配下にありません"}), 404)
        if not repo["available"]:
            return None, (jsonify({"error": f"{repo['type']} コマンドがサーバーに見つかりません"}), 500)
        return repo, None

    def _log_and_record(user, action, detail=""):
        activity_log.record(
            user=(user or {}).get("username") if SERVER_MODE else "local",
            role=(user or {}).get("role") if SERVER_MODE else "local",
            method="POST", path=f"/api/vcs/{action}", category="vcs", item=detail, status=200,
        )

    @app.route("/api/vcs/status", methods=["GET"])
    def vcs_status():
        repo = detect_repo()
        if repo is None:
            return jsonify({"repo": None})
        user = auth.current_user() if SERVER_MODE else None
        result = {"repo": repo}
        if not repo["available"]:
            result["error"] = f"{repo['type']} コマンドが見つかりません"
            result["files"] = []
        else:
            try:
                if repo["type"] == "git":
                    raw = _git_status(repo["root"])
                    result["branch"] = _git_current_branch(repo["root"])
                    result["aheadBehind"] = _git_ahead_behind(repo["root"])
                else:
                    raw = _svn_status(repo["root"])
                    info = _svn_info(repo["root"])
                    result["branch"] = (info.get("URL", "").rstrip("/").rsplit("/", 1)[-1]) or "trunk"
                    result["aheadBehind"] = None
                result["files"] = _filter_and_annotate(raw, repo["root"], user)
            except RuntimeError as e:
                result["error"] = str(e)
                result["files"] = []
        role = (user or {}).get("role") if SERVER_MODE else "admin"
        can_act = (not SERVER_MODE) or role in ("admin", "editor")
        result["capabilities"] = {
            "canFetch": can_act, "canPull": can_act, "canPush": can_act,
            "canCommit": can_act, "canMerge": can_act, "canBranch": can_act,
        }
        return jsonify(result)

    @app.route("/api/vcs/branches", methods=["GET"])
    def vcs_branches():
        repo, err = _repo_or_404()
        if err:
            return err
        try:
            branches = _git_branches(repo["root"]) if repo["type"] == "git" else _svn_branches(repo["root"])
            return jsonify({"branches": branches})
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/vcs/log", methods=["GET"])
    def vcs_log():
        repo, err = _repo_or_404()
        if err:
            return err
        branch = request.args.get("branch")
        limit = int(request.args.get("limit", 200))
        try:
            commits = _git_log(repo["root"], branch, limit) if repo["type"] == "git" else _svn_log(repo["root"], limit)
            return jsonify({"commits": commits})
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/vcs/diff", methods=["GET"])
    def vcs_diff():
        repo, err = _repo_or_404()
        if err:
            return err
        rel_path = request.args.get("path")
        if not rel_path:
            return jsonify({"error": "path は必須です"}), 400
        user = auth.current_user() if SERVER_MODE else None
        if SERVER_MODE:
            if user is None:
                return jsonify({"error": "ログインが必要です"}), 401
            # viewerは読み取り専用操作として差分閲覧のみ許可する
            if user.get("role") != "admin":
                category, item = _categorize(_to_rel_from_data(repo["root"], rel_path))
                allowed = _user_can_see(user, category, item) or user.get("role") == "viewer"
                if not allowed:
                    return jsonify({"error": "この差分を閲覧する権限がありません"}), 403
        try:
            diff_text = _git_diff(repo["root"], rel_path) if repo["type"] == "git" else _svn_diff(repo["root"], rel_path)
            return jsonify({"diffText": diff_text})
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/vcs/fetch", methods=["POST"])
    def vcs_fetch():
        user, err = _require_actor()
        if err:
            return err
        repo, err = _repo_or_404()
        if err:
            return err
        if repo["type"] != "git":
            return jsonify({"error": "fetchはGitリポジトリのみ対応しています（SVNはupdateをご利用ください）"}), 400
        job_id = _start_job(lambda log: _git_fetch(repo["root"], log))
        _log_and_record(user, "fetch")
        return jsonify({"jobId": job_id})

    @app.route("/api/vcs/pull", methods=["POST"])
    def vcs_pull():
        user, err = _require_actor()
        if err:
            return err
        repo, err = _repo_or_404()
        if err:
            return err
        if repo["type"] == "git":
            job_id = _start_job(lambda log: _git_pull(repo["root"], log))
        else:
            job_id = _start_job(lambda log: _svn_update(repo["root"], log))
        _log_and_record(user, "pull")
        return jsonify({"jobId": job_id})

    @app.route("/api/vcs/push", methods=["POST"])
    def vcs_push():
        user, err = _require_actor()
        if err:
            return err
        repo, err = _repo_or_404()
        if err:
            return err
        if repo["type"] != "git":
            return jsonify({"error": "pushはGitリポジトリのみ対応しています（SVNはcommitで直接反映されます）"}), 400
        body = request.get_json(silent=True) or {}
        set_upstream = bool(body.get("setUpstream"))
        branch = body.get("branch") or _git_current_branch(repo["root"])
        job_id = _start_job(lambda log: _git_push(repo["root"], log, set_upstream, branch))
        _log_and_record(user, "push", branch)
        return jsonify({"jobId": job_id})

    @app.route("/api/vcs/commit", methods=["POST"])
    def vcs_commit():
        user, err = _require_actor()
        if err:
            return err
        repo, err = _repo_or_404()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        message = body.get("message", "")
        rel_paths = body.get("paths") or []
        if not rel_paths:
            return jsonify({"error": "コミット対象のファイルが選択されていません"}), 400

        # フロント側フィルタは信用せず、選択された各パスの権限をここでも検証する
        if SERVER_MODE and user.get("role") != "admin":
            for rp in rel_paths:
                category, item = _categorize(_to_rel_from_data(repo["root"], rp))
                if not _user_can_see(user, category, item):
                    return jsonify({"error": f"'{rp}' をコミットする権限がありません"}), 403

        if repo["type"] == "git":
            job_id = _start_job(lambda log: _git_commit(repo["root"], log, message, rel_paths))
        else:
            job_id = _start_job(lambda log: _svn_commit(repo["root"], log, message, rel_paths))
        _log_and_record(user, "commit", f"{len(rel_paths)}件")
        return jsonify({"jobId": job_id})

    @app.route("/api/vcs/merge", methods=["POST"])
    def vcs_merge():
        user, err = _require_actor()
        if err:
            return err
        repo, err = _repo_or_404()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        target = body.get("branch") or body.get("url")
        if not target:
            return jsonify({"error": "マージ元のブランチ（またはURL）を指定してください"}), 400
        if repo["type"] == "git":
            job_id = _start_job(lambda log: _git_merge(repo["root"], log, target))
        else:
            job_id = _start_job(lambda log: _svn_merge(repo["root"], log, target))
        _log_and_record(user, "merge", target)
        return jsonify({"jobId": job_id})

    @app.route("/api/vcs/branch", methods=["POST"])
    def vcs_branch_create():
        user, err = _require_actor()
        if err:
            return err
        repo, err = _repo_or_404()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        if not name:
            return jsonify({"error": "ブランチ名は必須です"}), 400
        if repo["type"] == "git":
            checkout = bool(body.get("checkout"))
            start_point = body.get("from")
            job_id = _start_job(lambda log: _git_branch_create(repo["root"], log, name, start_point, checkout))
        else:
            job_id = _start_job(lambda log: _svn_branch_create(repo["root"], log, name))
        _log_and_record(user, "branch-create", name)
        return jsonify({"jobId": job_id})

    @app.route("/api/vcs/checkout", methods=["POST"])
    def vcs_checkout():
        user, err = _require_actor()
        if err:
            return err
        repo, err = _repo_or_404()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        if repo["type"] == "git":
            name = body.get("name")
            if not name:
                return jsonify({"error": "切り替え先のブランチ名を指定してください"}), 400
            job_id = _start_job(lambda log: _git_checkout(repo["root"], log, name))
        else:
            url = body.get("url")
            if not url:
                return jsonify({"error": "切り替え先のURLを指定してください"}), 400
            job_id = _start_job(lambda log: _svn_switch(repo["root"], log, url))
        _log_and_record(user, "checkout", body.get("name") or body.get("url"))
        return jsonify({"jobId": job_id})

    @app.route("/api/vcs/progress/<job_id>", methods=["GET"])
    def vcs_progress(job_id):
        job = get_job(job_id)
        if job is None:
            return jsonify({"error": "指定されたジョブが見つかりません"}), 404
        return jsonify(job)
