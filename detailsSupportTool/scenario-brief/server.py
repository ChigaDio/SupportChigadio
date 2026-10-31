"""シナリオ演出依頼資料集 サーバー (標準ライブラリのみ)
python server.py [--data DIR] [--port 8765] [--no-browser] [--local-only] [--admin-password PW] [--image-base DIR]
データは  <DATA>/projects/<プロジェクトID>/{project.json, scenarios/, chapters/, dictionary/, users/<ユーザー名>/, images/}  に1ファイルずつ保存されます。
(1プロジェクト = 複数シナリオ、1シナリオ = 複数章。章ファイルの "sc" がシナリオIDです)
バックアップは <DATA>/.local/backups/backup-YYYY-MM-DD.zip に毎日1つ作られ、新しい7日分だけ残ります。
アカウント情報(パスワードのハッシュ等)は <DATA>/.local/auth.json (Git管理しない) に保存されます。
"""
import argparse, datetime, hashlib, hmac, json, mimetypes, os, re, secrets, shutil, socket, sys, threading, time, traceback, webbrowser, zipfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote, unquote

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=str(APP_DIR / "scenario-data"))
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--no-browser", action="store_true")
ap.add_argument("--local-only", action="store_true", help="このPCだけで使う(他の端末からは接続不可)")
ap.add_argument("--admin-password", default="", help="管理者(admin)のパスワードを設定/リセットする")
ap.add_argument("--image-base", default="", help="指定すると、画像を参照できる場所をそのフォルダ以下に制限する(既定: 制限なし)")
args = ap.parse_args()
if not (RES_DIR / "index.html").exists():
    print("index.html が見つかりません:", RES_DIR / "index.html")
    input("Enter で終了")
    sys.exit(1)

DATA = Path(args.data).resolve()
DATA.mkdir(parents=True, exist_ok=True)
LOCAL = DATA / ".local"
LOCAL.mkdir(exist_ok=True)
ROOT = DATA / "projects"
ROOT.mkdir(exist_ok=True)
TRASH = DATA / ".trash"
BASE = Path(args.image_base).resolve() if args.image_base else None
IMG_OK = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
ROLES = ("view", "memo", "edit")  # 閲覧のみ / 閲覧+メモ / 編集可
LOCK = threading.RLock()
FAILS = {}
PID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
USER_RE = re.compile(r"^[^\s/\\:.~;,'\"<>|?*%&=+#]{1,32}$")
REL_RE = re.compile(r"^(project\.json|(chapters|dictionary|scenarios)/[\w\-]+\.json|users/[^/\\]+/[\w\-]+\.json)$")
SC_ROLES = ROLES + ("none",)  # シナリオ別の上書き: none=閲覧不可
BAK = LOCAL / "backups"
BAK_KEEP = 7  # 日数(世代数)
BAK_REFRESH = 6 * 3600  # 同じ日のバックアップを更新する最短間隔(秒)


def within(p):
    return BASE is None or any(b == p or b in p.parents for b in (BASE, DATA))


def rj(p):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def wr(p, data):  # 置き換えで保存(複数端末が同時に読んでも壊れない)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def hpw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt, hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), 200_000).hex()


def user_new(pw, admin=False):
    s, h = hpw(pw)
    return {"salt": s, "hash": h, "admin": admin, "must_change": True, "projects": {}, "trust": []}


DBF = LOCAL / "auth.json"


def db_load():
    d = rj(DBF) or {}
    d.setdefault("users", {})
    d.setdefault("sessions", {})
    return d


def db_save(d):
    if len(d["sessions"]) > 400:
        keep = sorted(d["sessions"].items(), key=lambda kv: kv[1].get("t", 0))[-300:]
        d["sessions"] = dict(keep)
    wr(DBF, json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8"))


# ---- 旧形式(プロジェクト分割前)のデータを projects/p-main に移す ----
legacy = [n for n in ("project.json", "chapters", "dictionary", "users", "images") if (DATA / n).exists()]
if legacy and not any(ROOT.iterdir()):
    d = ROOT / "p-main"
    d.mkdir()
    for n in legacy:
        shutil.move(str(DATA / n), str(d / n))
    print("以前のデータを projects/p-main に移しました")

# ---- 旧形式(シナリオ階層の導入前)の章を、シナリオ「本編」にまとめる ----
def migrate_scenarios():
    for pid in sorted(d.name for d in ROOT.iterdir() if d.is_dir() and not d.name.startswith(".")):
        P = ROOT / pid
        if not (P / "chapters").exists():
            continue
        loose = [(f, rj(f)) for f in sorted((P / "chapters").glob("*.json"))]
        loose = [(f, d) for f, d in loose if d and not d.get("sc")]
        if not loose:
            continue
        scs = scen_list(P)
        sid = next(iter(sorted(scs, key=lambda s: (scs[s].get("order", 0), s))), None)
        if sid is None:
            sid = "smain"
            wr(P / "scenarios" / (sid + ".json"), json.dumps({"id": sid, "title": "本編", "order": 1}, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
        for f, d in loose:
            d["sc"] = sid
            wr(f, json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
        print(f"プロジェクト {pid}: {len(loose)} 章をシナリオ「{(scs.get(sid) or {}).get('title', '本編')}」に割り当てました")


# ---- 初期管理者 ----
with LOCK:
    _db = db_load()
    if not _db["users"]:
        pw = args.admin_password or secrets.token_urlsafe(6)
        _db["users"]["admin"] = user_new(pw, True)
        db_save(_db)
        print(f"\n★ 初期管理者を作成しました   ユーザー名: admin   パスワード: {pw}\n   （ログイン後、マイページでパスワードを変更してください）\n")
    elif args.admin_password and "admin" in _db["users"]:
        _db["users"]["admin"].update(dict(zip(("salt", "hash"), hpw(args.admin_password))), must_change=False, trust=[])
        db_save(_db)
        print("admin のパスワードを変更しました")


def list_projects():
    return sorted(d.name for d in ROOT.iterdir() if d.is_dir() and not d.name.startswith("."))


def proj_dir(pid):
    return ROOT / pid if pid and PID_RE.match(pid) and (ROOT / pid).is_dir() else None


def role_of(db, user, pid):
    u = db["users"].get(user)
    if not u or not proj_dir(pid):
        return None
    if u.get("admin"):
        return "edit"
    r = u.get("projects", {}).get(pid)
    return r if r in ROLES else None


def pj_of(P):
    return rj(P / "project.json") or {}


def stamp_of(P):
    return max((f.stat().st_mtime_ns for f in P.rglob("*.json")), default=0)


def scen_list(P):  # {シナリオID: {id,title,order}}
    o = {}
    d = P / "scenarios"
    if d.exists():
        for f in sorted(d.glob("*.json")):
            x = rj(f)
            if x and x.get("id"):
                o[x["id"]] = x
    return o


def sc_ov(db, user, pid, scid):  # そのユーザーのシナリオ別設定 {"r":..., "pdf":...}
    return ((db["users"][user].get("scen") or {}).get(pid) or {}).get(scid) or {}


def sc_role(db, user, pid, scid):
    """シナリオ内での権限。None=閲覧不可。シナリオ別の指定がなければプロジェクトの権限を引き継ぐ"""
    base = role_of(db, user, pid)
    if not base:
        return None
    if db["users"][user].get("admin"):
        return "edit"
    r = sc_ov(db, user, pid, scid).get("r") if scid else None
    if r == "none":
        return None
    return r if r in ROLES else base


def sc_pdf(db, user, pid, scid):
    return bool(db["users"][user].get("admin")) or sc_ov(db, user, pid, scid).get("pdf", True) is not False


def access(db, user, pid):
    """プロジェクトに入れるか。入れるときはプロジェクト権限を返す。見られるシナリオが1つもなければ入れない(一覧にも出ない)"""
    base = role_of(db, user, pid)
    if not base:
        return None
    scs = scen_list(ROOT / pid)
    if scs and not any(sc_role(db, user, pid, s) for s in scs):
        return None
    return base


def ch_visible(db, user, pid, d, scs):
    sc = d.get("sc") or ""
    if not sc:
        return True
    return sc in scs and sc_role(db, user, pid, sc) is not None


def info(db, user):
    u = db["users"][user]
    ps = []
    for pid in list_projects():
        r = access(db, user, pid)
        if r:
            P = ROOT / pid
            scs = scen_list(P)
            vis = {s for s in scs if sc_role(db, user, pid, s)}
            nch = 0
            if (P / "chapters").exists():
                for f in (P / "chapters").glob("*.json"):
                    d = rj(f)
                    if d and ch_visible(db, user, pid, d, scs):
                        nch += 1
            ps.append({"id": pid, "name": pj_of(P).get("name") or pid, "role": r,
                       "scenarios": len(vis), "chapters": nch,
                       "updated": stamp_of(P) / 1e9,
                       "members": sum(1 for x in db["users"].values() if x.get("admin") or pid in x.get("projects", {}))})
    return {"user": user, "admin": bool(u.get("admin")), "mustChange": bool(u.get("must_change")), "projects": ps}


def read_all(db, pid, user, role):
    P = ROOT / pid
    pj = pj_of(P)
    scs = scen_list(P)
    vis = {s: x for s, x in scs.items() if sc_role(db, user, pid, s)}
    o = {"me": user, "role": role, "base": role, "project": pj.get("name", ""), "imgRefs": pj.get("imgRefs", []),
         "chapters": {}, "dict": {}, "layers": {}, "scenarios": vis,
         "roles": {s: sc_role(db, user, pid, s) for s in vis}, "pdf": {s: sc_pdf(db, user, pid, s) for s in vis}}
    for k in ("memoW", "fs", "coverOri", "coverWm", "look"):
        o[k] = pj.get(k)
    for f in sorted((P / "chapters").glob("*.json")):
        d = rj(f)
        if d and "id" in d and ch_visible(db, user, pid, d, scs):
            o["chapters"][d["id"]] = d
    every = {f.stem for f in (P / "chapters").glob("*.json")}  # 見られない章に紐づく設定は返さない
    for f in sorted((P / "dictionary").glob("*.json")):
        d = rj(f)
        if not (d and "id" in d):
            continue
        if d.get("sc") and d["sc"] in scs and d["sc"] not in vis:  # 見られないシナリオ限定の設定は返さない
            continue
        if not d.get("ch") or d["ch"] in o["chapters"] or d["ch"] not in every:
            o["dict"][d["id"]] = d
    for ud in sorted((P / "users").glob("*")):
        if ud.is_dir():
            for f in ud.glob("*.json"):
                d = rj(f)
                if d and f.stem in o["chapters"]:
                    o["layers"].setdefault(ud.name, {})[f.stem] = d
    return o


def list_imgs(P):
    IMGDIR = P / "images"
    up = sorted("images/" + f.name for f in IMGDIR.glob("*") if f.suffix.lower() in IMG_OK) if IMGDIR.exists() else []
    refs = []
    for r in pj_of(P).get("imgRefs", []):
        p = (DATA / r).resolve()
        items = []
        if within(p) and p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in IMG_OK:
                    try:
                        items.append(os.path.relpath(f, DATA).replace("\\", "/"))
                    except ValueError:
                        items.append(str(f))
                if len(items) >= 300:
                    break
        elif within(p) and p.is_file() and p.suffix.lower() in IMG_OK:
            items = [r]
        refs.append({"ref": r, "dir": p.is_dir(), "missing": not p.exists(), "items": items})
    return {"uploaded": up, "refs": refs}


def img_path(P, rel, role):
    if rel.startswith("images/"):
        p = (P / rel).resolve()
        ok = (P / "images") in p.parents
    else:
        p = (DATA / rel).resolve()
        ok = within(p) and (role == "edit" or any(p == rp or rp in p.parents for rp in ((DATA / r).resolve() for r in pj_of(P).get("imgRefs", []))))
    return p if ok and p.is_file() and p.suffix.lower() in IMG_OK else None


def can_write(db, user, pid, rel, raw=b""):
    """章はそのシナリオの編集権限が必要 / 自分の書き込みはシナリオの閲覧+メモ以上 / 辞書・設定・シナリオ一覧はプロジェクトの編集権限"""
    if not REL_RE.match(rel):
        return False
    P = ROOT / pid
    parts = rel.split("/")
    if parts[0] == "chapters":
        ids = {(rj(P / rel) or {}).get("sc") or ""}
        if raw:
            try:
                new_sc = (json.loads(raw) or {}).get("sc") or ""
            except Exception:
                return False
            if new_sc not in scen_list(P):  # 存在しないシナリオへの章の作成・移動は不可(どこからも見えなくなるため)
                return False
            ids.add(new_sc)
        return all(sc_role(db, user, pid, s) == "edit" for s in ids)
    if parts[0] == "users":
        if parts[1] != user:
            return False
        sc = (rj(P / "chapters" / (parts[2][:-5] + ".json")) or {}).get("sc") or ""
        return sc_role(db, user, pid, sc) in ("memo", "edit")
    return role_of(db, user, pid) == "edit"


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except Exception:
        pass
    return sorted(i for i in ips if not i.startswith("127."))


class Srv(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"  # Windowsでは同じポートに二重起動できてしまうため無効


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code=200, body=b"", ctype="application/json"):
        self.send_response(code)
        for h in getattr(self, "_hdr", []):
            self.send_header(*h)
        self.send_header("Content-Type", ctype if ctype.startswith(("image/", "application/zip")) else ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=300" if ctype.startswith("image/") else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code=200):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def err(self, msg, code=400):
        self.json({"error": msg}, code)

    def body(self):
        try:
            return json.loads(self.raw or b"{}")
        except Exception:
            return {}

    def cookies(self):
        ck = {}
        for part in self.headers.get("Cookie", "").split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                ck[k] = v
        return ck

    def cookie(self, name, val, age=3 * 365 * 86400):
        self._hdr.append(("Set-Cookie", f"{name}={val}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}"))

    def trust_tokens(self):
        d = {}
        for part in self.cookies().get("sbt", "").split("~"):
            uq, _, tok = part.rpartition(".")
            if uq and tok:
                d[unquote(uq)] = tok
        return d

    def set_trust(self, tokens):
        self.cookie("sbt", "~".join(f"{quote(u, safe='')}.{t}" for u, t in tokens.items()))

    def origin_ok(self):
        o = self.headers.get("Origin")
        return not o or urlparse(o).netloc == self.headers.get("Host")

    def session_user(self, db):
        tok = self.cookies().get("sbs")
        s = db["sessions"].get(sha(tok)) if tok else None
        return s["user"] if s and s["user"] in db["users"] else None

    def do_GET(self):
        self.dispatch("GET")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_POST(self):
        self.dispatch("POST")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method):
        try:
            self._hdr = []
            n = int(self.headers.get("Content-Length", 0) or 0)
            self.raw = self.rfile.read(n) if n else b""
            if method != "GET" and not self.origin_ok():
                return self.err("origin", 403)
            u = urlparse(self.path)
            self.route(method, u.path, parse_qs(u.query))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self.send(500, traceback.format_exc().encode("utf-8"), "text/plain")
            except Exception:
                pass

    # ---------------- ルーティング ----------------
    def route(self, method, path, q):
        if method == "GET" and path in ("/", "/index.html"):
            return self.send(200, (RES_DIR / "index.html").read_bytes(), "text/html")
        if path == "/api/trusted" and method == "GET":  # このデバイスでパスワード不要で入れるユーザー
            with LOCK:
                db = db_load()
                names = [u for u, t in self.trust_tokens().items() if u in db["users"] and sha(t) in db["users"][u].get("trust", [])]
            return self.json(names)
        if path == "/api/login" and method == "POST":
            return self.login(self.body())
        with LOCK:
            db = db_load()
            user = self.session_user(db)
        if not user:
            return self.err("login", 401)
        if path == "/api/session":
            return self.json(info(db, user))
        if path == "/api/logout" and method == "POST":
            with LOCK:
                db = db_load()
                db["sessions"].pop(sha(self.cookies().get("sbs", "")), None)
                db_save(db)
            self.cookie("sbs", "", 0)
            return self.json({"ok": 1})
        if path == "/api/forget" and method == "POST":  # このデバイスの「パスワード不要」を解除
            toks = self.trust_tokens()
            with LOCK:
                db = db_load()
                tok = toks.pop(user, None)
                if tok:
                    t = db["users"][user].get("trust", [])
                    db["users"][user]["trust"] = [x for x in t if x != sha(tok)]
                    db_save(db)
            self.set_trust(toks)
            return self.json({"ok": 1})
        if path == "/api/password" and method == "POST":
            return self.change_password(user, self.body())
        if path == "/api/username" and method == "POST":
            return self.rename_user(user, self.body())
        if path.startswith("/api/admin/"):
            if not db["users"][user].get("admin"):
                return self.err("管理者のみ", 403)
            if method == "GET" and path.startswith("/api/admin/backup/"):  # バックアップzipのダウンロード
                name = unquote(path[len("/api/admin/backup/"):])
                f = BAK / name
                if not BAK_RE.match(name) or not f.is_file():
                    return self.err("バックアップがありません", 404)
                self._hdr.append(("Content-Disposition", f'attachment; filename="scenario-{name}"'))
                return self.send(200, f.read_bytes(), "application/zip")
            return self.admin(user, path[len("/api/admin/"):], method, self.body())
        # ---- ここからプロジェクト単位 ----
        pid = self.headers.get("X-Project") or q.get("proj", [""])[0]
        role = access(db, user, pid)
        if not role:
            return self.err("このプロジェクトの権限がありません", 403)
        P = ROOT / pid
        if path == "/api/all":
            return self.json(read_all(db, pid, user, role))
        if path == "/api/stamp":
            return self.send(200, str(stamp_of(P)).encode(), "text/plain")
        if path == "/api/imgs":
            return self.json(list_imgs(P))
        if path == "/api/img":
            p = img_path(P, q.get("p", [""])[0], role)
            if not p:
                return self.send(404)
            return self.send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        if path == "/api/ls":
            if role != "edit":
                return self.err("編集権限が必要です", 403)
            return self.ls(q.get("p", [""])[0])
        if path == "/api/file" and method in ("PUT", "DELETE"):
            rel = q.get("path", [""])[0].replace("\\", "/")
            if not can_write(db, user, pid, rel, self.raw if method == "PUT" else b""):
                return self.err("この操作の権限がありません", 403)
            p = (P / rel).resolve()
            if P not in p.parents:
                return self.err("bad path")
            if method == "PUT":
                wr(p, self.raw)
            else:
                p.unlink(missing_ok=True)
            return self.json({"ok": 1})
        if path == "/api/chapter/dup" and method == "POST":
            return self.chapter_dup(db, user, pid, P, self.body())
        if path == "/api/image" and method == "POST":
            if role == "view":
                return self.err("権限がありません", 403)
            name = q.get("name", ["image.png"])[0]
            ext = Path(name).suffix.lower()
            if ext not in IMG_OK or len(self.raw) > 30_000_000:
                return self.err("画像のみ(30MBまで)")
            fn = hashlib.sha1(self.raw).hexdigest()[:10] + "_" + re.sub(r"[^\w\-]", "_", Path(name).stem)[:40] + ext
            if not (P / "images" / fn).exists():
                wr(P / "images" / fn, self.raw)
            return self.json({"path": "images/" + fn})
        self.send(404)

    def chapter_dup(self, db, user, pid, P, d):
        """章を複製する。同じシナリオなら元の章の直後、別シナリオへの複製なら末尾に入る。書き込み(各ユーザーのレイヤー)も複製できる"""
        cid = str(d.get("id", ""))
        src = rj(P / "chapters" / (cid + ".json")) if re.fullmatch(r"[\w\-]+", cid) else None
        if not src:
            return self.err("章が見つかりません", 404)
        scs = scen_list(P)
        s0 = src.get("sc") or ""
        to = d.get("sc") or s0
        if to not in scs or s0 not in scs:
            return self.err("シナリオが見つかりません", 404)
        if sc_role(db, user, pid, s0) != "edit" or sc_role(db, user, pid, to) != "edit":
            return self.err("この操作の権限がありません", 403)
        sib = sorted((rj(f) or {}).get("order", 0) for f in (P / "chapters").glob("*.json") if (rj(f) or {}).get("sc") == to and (rj(f) or {}).get("id") != cid)
        o0 = src.get("order", 0)
        if to == s0:
            nx = [x for x in sib if x > o0]
            order = (o0 + nx[0]) / 2 if nx else o0 + 1
        else:
            order = (sib[-1] + 1) if sib else 1
        nid = "c" + format(int(time.time() * 1000), "x") + secrets.token_hex(2)
        new = dict(src)
        new.update({"id": nid, "sc": to, "order": order, "title": str(d.get("title") or (src.get("title", "") + "（コピー）"))[:200]})
        wr(P / "chapters" / (nid + ".json"), (json.dumps(new, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        n = 0
        if d.get("layers"):
            for ud in (P / "users").glob("*"):
                f = ud / (cid + ".json")
                if ud.is_dir() and f.is_file():
                    wr(ud / (nid + ".json"), f.read_bytes())
                    n += 1
        return self.json({"ok": 1, "id": nid, "layers": n})

    def ls(self, q):  # サーバー上のフォルダ一覧(エクスプローラー風UI用)
        p = (DATA / q).resolve() if q else DATA
        if not p.is_dir():
            p = p.parent if p.exists() else DATA
        dirs, files = [], []
        try:
            for f in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                try:
                    if f.is_dir():
                        dirs.append(f.name)
                    elif f.suffix.lower() in IMG_OK:
                        files.append(f.name)
                except OSError:
                    pass
        except OSError:
            pass
        try:
            rel = os.path.relpath(p, DATA).replace("\\", "/")
        except ValueError:
            rel = str(p)
        drives = [f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.name == "nt" and os.path.exists(f"{c}:\\")]
        self.json({"path": str(p), "rel": rel, "sep": os.sep, "parent": str(p.parent) if p.parent != p else None,
                   "dirs": dirs[:2000], "files": files[:2000], "drives": drives})

    # ---------------- 認証 ----------------
    def login(self, d):
        user = str(d.get("user", "")).strip()
        k = (self.client_address[0], user)
        now = time.time()
        f = FAILS.get(k)
        if f and f[0] >= 5 and now - f[1] < 120:
            return self.err("試行回数が多すぎます。しばらく待ってからやり直してください", 429)
        with LOCK:
            db = db_load()
            u = db["users"].get(user)
            toks = self.trust_tokens()
            tok = toks.get(user)
            ok = False
            if u:
                if d.get("trusted"):
                    ok = bool(tok) and sha(tok) in u.get("trust", [])
                else:
                    ok = hmac.compare_digest(hpw(str(d.get("password", "")), u["salt"])[1], u["hash"])
                    if ok:
                        tok = None
            if not ok:
                f = FAILS.get(k)
                FAILS[k] = [(f[0] if f and now - f[1] < 120 else 0) + 1, f[1] if f and now - f[1] < 120 else now]
                return self.err("ユーザー名またはパスワードが違います", 401)
            FAILS.pop(k, None)
            st = secrets.token_hex(24)
            db["sessions"][sha(st)] = {"user": user, "t": now}
            if not tok:  # このデバイスを記憶 → 次回からパスワード不要
                tok = secrets.token_hex(24)
                u["trust"] = (u.get("trust", []) + [sha(tok)])[-12:]
                toks[user] = tok
                self.set_trust(toks)
            db_save(db)
            res = info(db, user)
        self.cookie("sbs", st, 365 * 86400)
        self.json(res)

    def change_password(self, user, d):
        new = str(d.get("new", ""))
        if len(new) < 6:
            return self.err("新しいパスワードは6文字以上にしてください")
        with LOCK:
            db = db_load()
            u = db["users"][user]
            if not hmac.compare_digest(hpw(str(d.get("old", "")), u["salt"])[1], u["hash"]):
                return self.err("現在のパスワードが違います", 401)
            u["salt"], u["hash"] = hpw(new)
            u["must_change"] = False
            cur = sha(self.cookies().get("sbs", ""))
            db["sessions"] = {k: v for k, v in db["sessions"].items() if v["user"] != user or k == cur}  # 他の端末のログインは解除
            tok = secrets.token_hex(24)  # 他の端末の「記憶」も解除し、この端末だけ記憶し直す
            u["trust"] = [sha(tok)]
            toks = self.trust_tokens()
            toks[user] = tok
            self.set_trust(toks)
            db_save(db)
        self.json({"ok": 1})

    def rename_user(self, user, d):
        new = str(d.get("new", "")).strip()
        if not USER_RE.match(new):
            return self.err("ユーザー名に使えない文字が含まれています（空白 / \\ : . ~ ; , など不可・32文字まで）")
        with LOCK:
            db = db_load()
            u = db["users"][user]
            if not hmac.compare_digest(hpw(str(d.get("password", "")), u["salt"])[1], u["hash"]):
                return self.err("パスワードが違います", 401)
            if new == user:
                return self.err("今と同じユーザー名です")
            if new in db["users"] or any((ROOT / p / "users" / new).exists() for p in list_projects()):
                return self.err("そのユーザー名はすでに使われています")
            for p in list_projects():  # 書き込みデータのフォルダも新しい名前に
                if (ROOT / p / "users" / user).exists():
                    (ROOT / p / "users" / user).rename(ROOT / p / "users" / new)
            db["users"][new] = db["users"].pop(user)
            for s in db["sessions"].values():
                if s["user"] == user:
                    s["user"] = new
            toks = self.trust_tokens()
            if user in toks:
                toks[new] = toks.pop(user)
                self.set_trust(toks)
            db_save(db)
            res = info(db, new)
        self.json(res)

    def admin(self, me, act, method, d):
        with LOCK:
            db = db_load()
            users = db["users"]
            if act == "users" and method == "GET":
                return self.json({"users": [{"user": n, "admin": bool(x.get("admin")), "projects": x.get("projects", {}), "scen": x.get("scen", {})} for n, x in users.items()],
                                  "projects": [{"id": p, "name": pj_of(ROOT / p).get("name") or p,
                                                "scenarios": [{"id": s["id"], "title": s.get("title", s["id"])} for s in sorted(scen_list(ROOT / p).values(), key=lambda s: (s.get("order", 0), s["id"]))]}
                                               for p in list_projects()],
                                  "backups": backup_list()})
            if act == "backup_now":
                backup_run(force=True)
                return self.json({"ok": 1, "backups": backup_list()})
            if act == "perm_set":  # 1人分の権限: scid なし=プロジェクト権限 / scid あり=そのシナリオの詳細権限
                name, pid, scid = str(d.get("user", "")), str(d.get("pid", "")), str(d.get("scid") or "")
                u = users.get(name)
                if not u or not proj_dir(pid):
                    return self.err("対象がありません", 404)
                if not scid:
                    r = d.get("r")
                    if r in ROLES:
                        u.setdefault("projects", {})[pid] = r
                    else:
                        u.setdefault("projects", {}).pop(pid, None)
                        u.get("scen", {}).pop(pid, None)
                else:
                    if scid not in scen_list(proj_dir(pid)):
                        return self.err("シナリオがありません", 404)
                    r, pdf = d.get("r") or "", d.get("pdf", True) is not False
                    sc = u.setdefault("scen", {}).setdefault(pid, {})
                    if r in SC_ROLES or not pdf:
                        sc[scid] = {k: v for k, v in (("r", r if r in SC_ROLES else None), ("pdf", False if not pdf else None)) if v is not None}
                    else:
                        sc.pop(scid, None)
                    if not sc:
                        u["scen"].pop(pid, None)
            elif act == "user_add":
                name, pw = str(d.get("user", "")).strip(), str(d.get("password", ""))
                if not USER_RE.match(name):
                    return self.err("ユーザー名に使えない文字が含まれています")
                if name in users or any((ROOT / p / "users" / name).exists() for p in list_projects()):
                    return self.err("そのユーザー名はすでに使われています")
                if len(pw) < 6:
                    return self.err("パスワードは6文字以上にしてください")
                users[name] = user_new(pw, bool(d.get("admin")))
            elif act == "user_set":
                name = str(d.get("user", ""))
                u = users.get(name)
                if not u:
                    return self.err("ユーザーがいません", 404)
                if "admin" in d and not d["admin"] and u.get("admin") and sum(1 for x in users.values() if x.get("admin")) <= 1:
                    return self.err("管理者が0人になるため変更できません")
                if "admin" in d:
                    u["admin"] = bool(d["admin"])
                if isinstance(d.get("projects"), dict):
                    u["projects"] = {k: v for k, v in d["projects"].items() if v in ROLES and proj_dir(k)}
                    u["scen"] = {k: v for k, v in (u.get("scen") or {}).items() if k in u["projects"]}
                if d.get("password"):
                    if len(str(d["password"])) < 6:
                        return self.err("パスワードは6文字以上にしてください")
                    u["salt"], u["hash"] = hpw(str(d["password"]))
                    u["must_change"] = True
                    u["trust"] = []
                    db["sessions"] = {k: v for k, v in db["sessions"].items() if v["user"] != name}
            elif act == "user_del":
                name = str(d.get("user", ""))
                if name == me:
                    return self.err("自分自身は削除できません")
                if name in users:
                    if users[name].get("admin") and sum(1 for x in users.values() if x.get("admin")) <= 1:
                        return self.err("最後の管理者は削除できません")
                    users.pop(name)
                    db["sessions"] = {k: v for k, v in db["sessions"].items() if v["user"] != name}
            elif act == "project_add":
                name = str(d.get("name", "")).strip()
                if not name:
                    return self.err("プロジェクト名を入力してください")
                pid = "p" + secrets.token_hex(4)
                (ROOT / pid).mkdir()
                wr(ROOT / pid / "project.json", json.dumps({"name": name}, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
                sid = "s" + secrets.token_hex(4)  # 最初のシナリオを1つ用意しておく
                wr(ROOT / pid / "scenarios" / (sid + ".json"), json.dumps({"id": sid, "title": "本編", "order": 1}, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
            elif act == "project_rename":
                P = proj_dir(str(d.get("id", "")))
                if not P:
                    return self.err("プロジェクトがありません", 404)
                pj = pj_of(P)
                pj["name"] = str(d.get("name", "")).strip() or pj.get("name", "")
                wr(P / "project.json", json.dumps(pj, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
            elif act == "project_del":
                P = proj_dir(str(d.get("id", "")))
                if not P:
                    return self.err("プロジェクトがありません", 404)
                TRASH.mkdir(exist_ok=True)
                shutil.move(str(P), str(TRASH / f"{P.name}-{int(time.time())}"))
                for x in users.values():
                    x.get("projects", {}).pop(P.name, None)
                    x.get("scen", {}).pop(P.name, None)
            else:
                return self.err("unknown", 404)
            db_save(db)
        self.json({"ok": 1})


# ---- 自動バックアップ (ログローテーション方式: 1日1つのzip、新しい7日分だけ残す) ----
BAK_RE = re.compile(r"^backup-(\d{4}-\d{2}-\d{2})\.zip$")


def backup_list():
    BAK.mkdir(exist_ok=True)
    out = []
    for f in sorted(BAK.glob("backup-*.zip"), reverse=True):
        if BAK_RE.match(f.name):
            st = f.stat()
            out.append({"name": f.name, "size": st.st_size, "time": st.st_mtime})
    return out


def backup_run(force=False):
    """今日の分が無ければ作成。あっても、データが更新されていて最短間隔(6時間)を過ぎていれば作り直す。古いものは7日分だけ残して削除"""
    with LOCK:
        BAK.mkdir(exist_ok=True)
        today = datetime.date.today().isoformat()
        dst = BAK / f"backup-{today}.zip"
        if dst.exists() and not force:
            newest = max([f.stat().st_mtime for f in ROOT.rglob("*") if f.is_file()] + [DBF.stat().st_mtime if DBF.exists() else 0], default=0)
            if newest <= dst.stat().st_mtime or time.time() - dst.stat().st_mtime < BAK_REFRESH:
                return None
        tmp = dst.with_name(dst.name + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(ROOT.rglob("*")):
                if f.is_file() and not f.name.endswith(".tmp"):
                    z.write(f, "projects/" + f.relative_to(ROOT).as_posix())
            if DBF.exists():
                z.write(DBF, ".local/auth.json")
        os.replace(tmp, dst)
        keep = sorted((f for f in BAK.glob("backup-*.zip") if BAK_RE.match(f.name)), reverse=True)
        for f in keep[BAK_KEEP:]:
            f.unlink(missing_ok=True)
        return dst


def backup_loop():
    while True:
        try:
            made = backup_run()
            if made:
                print("バックアップを作成しました:", made.name)
        except Exception:
            traceback.print_exc()
        time.sleep(3600)


try:
    backup_run()  # 章データを書き換える移行の前に、まず今日のバックアップを取っておく
except Exception:
    traceback.print_exc()
migrate_scenarios()  # 旧データの章にシナリオを割り当てる
threading.Thread(target=backup_loop, daemon=True).start()

srv = None
for port in range(args.port, args.port + 20):  # 使用中なら次のポートへ
    try:
        srv = Srv(("127.0.0.1" if args.local_only else "0.0.0.0", port), H)
        break
    except OSError:
        print(f"ポート {port} は使用中です。次を試します…")
if srv is None:
    input("使えるポートがありません。Enter で終了")
    sys.exit(1)
args.port = srv.server_address[1]
url = f"http://127.0.0.1:{args.port}/"
print("データ保存先:", DATA)
print("起動しました:", url, " (このウィンドウを閉じる / Ctrl+C で終了)")
if not args.local_only:
    print("\n【他のPC・iPadなどから使う場合】同じWi-Fi/LAN内で、次のURLを開いてください:")
    for ip in lan_ips():
        print(f"   http://{ip}:{args.port}/")
    print("   ※ユーザー名とパスワードでログインします。開かない場合はOSのファイアウォールで、このアプリの通信（プライベートネットワーク）を許可してください。\n")
if not args.no_browser:
    threading.Timer(0.8, webbrowser.open, [url]).start()
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
