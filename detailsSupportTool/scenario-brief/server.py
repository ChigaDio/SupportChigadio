"""シナリオ演出依頼資料集 ローカルサーバー (標準ライブラリのみ)
使い方: python server.py [--data データ保存先] [--port 8765] [--no-browser]
データは  project.json / chapters/ / dictionary/ / users/<名前>/  に1ファイルずつ保存されます。
"""
import argparse, hashlib, json, mimetypes, os, re, secrets, socket, sys, threading, traceback, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

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
ap.add_argument("--key", default="", help="他の端末からのアクセスキー(既定: 自動生成して .local/key.txt に保存)")
ap.add_argument("--image-base", default="", help="指定すると、画像を参照できる場所をそのフォルダ以下に制限する(既定: 制限なし)")
args = ap.parse_args()
if not (RES_DIR / "index.html").exists():
    print("index.html が見つかりません:", RES_DIR / "index.html")
    input("Enter で終了")
    sys.exit(1)

DATA = Path(args.data).resolve()
DATA.mkdir(parents=True, exist_ok=True)
LOCAL = DATA / ".local"  # 自分用の設定(名前)。Git管理しない
BASE = Path(args.image_base).resolve() if args.image_base else None  # None = サーバー上のどこでも選べる


def within(p):
    return BASE is None or any(b == p or b in p.parents for b in (BASE, DATA))


LOCAL.mkdir(exist_ok=True)
KEY = ""
if not args.local_only:
    kf = LOCAL / "key.txt"
    KEY = args.key or (kf.read_text("utf-8").strip() if kf.exists() else "") or secrets.token_hex(6)
    kf.write_text(KEY, "utf-8")


def names():
    try:
        return json.loads((LOCAL / "names.json").read_text("utf-8"))
    except Exception:
        return {}


def set_name(dev, name):  # 名前は端末(Cookieの端末ID)ごとにサーバー側へ保存
    d = names()
    d[dev] = name
    (LOCAL / "names.json").write_text(json.dumps(d, ensure_ascii=False), "utf-8")


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


IMGDIR = DATA / "images"  # 画像は相対パス images/xxx で参照される
IMG_OK = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
ALLOWED = ("chapters/", "dictionary/", "users/", "project.json")


def safe(rel):
    rel = rel.replace("\\", "/")
    if not rel.startswith(ALLOWED) or not rel.endswith(".json") or ".." in rel.split("/"):
        return None
    p = (DATA / rel).resolve()
    return p if DATA in p.parents else None


def rj(p):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def list_imgs():
    pj = rj(DATA / "project.json") or {}
    up = sorted("images/" + f.name for f in IMGDIR.glob("*") if f.suffix.lower() in IMG_OK) if IMGDIR.exists() else []
    refs = []
    for r in pj.get("imgRefs", []):
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


def read_all(dev=""):
    o = {"me": names().get(dev, ""),
         "project": (rj(DATA / "project.json") or {}).get("name", ""),
         "memoW": (rj(DATA / "project.json") or {}).get("memoW"),
         "fs": (rj(DATA / "project.json") or {}).get("fs"),
         "imgRefs": (rj(DATA / "project.json") or {}).get("imgRefs", []),
         "chapters": {}, "dict": {}, "layers": {}}
    for folder, key in (("chapters", "chapters"), ("dictionary", "dict")):
        for f in sorted((DATA / folder).glob("*.json")):
            d = rj(f)
            if d and "id" in d:
                o[key][d["id"]] = d
    for ud in sorted((DATA / "users").glob("*")):
        if ud.is_dir():
            for f in ud.glob("*.json"):
                d = rj(f)
                if d:
                    o["layers"].setdefault(ud.name, {})[f.stem] = d
    return o


def guard(fn):
    # 例外で接続が切れて「空の応答」になるのを防ぎ、原因をブラウザとコンソールに出す
    def w(self):
        try:
            self._hdr = []
            ck = {}
            for part in self.headers.get("Cookie", "").split(";"):
                if "=" in part:
                    k, val = part.strip().split("=", 1)
                    ck[k] = val
            self.dev = ck.get("sbd") or secrets.token_hex(8)
            if "sbd" not in ck:
                self._hdr.append(("Set-Cookie", f"sbd={self.dev}; Path=/; HttpOnly; SameSite=Lax; Max-Age=315360000"))
            loop = self.client_address[0] in ("127.0.0.1", "::1") and self.headers.get("Host", "").rsplit(":", 1)[0] in ("127.0.0.1", "localhost")
            u = urlparse(self.path)
            if KEY and u.path == "/" and parse_qs(u.query).get("key", [""])[0] == KEY:  # キー付きURL → Cookieに保存して通常URLへ
                self._hdr += [("Set-Cookie", f"sbk={KEY}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000"), ("Location", "/")]
                return self.send(302)
            if not (loop or (KEY and ck.get("sbk") == KEY)):
                return self.send(401, "アクセスキーが必要です。サーバー起動画面に表示された「他の端末から」のURL（?key=...付き）で開いてください。".encode("utf-8"), "text/plain")
            fn(self)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            try:
                self.send(500, traceback.format_exc().encode("utf-8"), "text/plain")
            except Exception:
                pass
    return w


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
        self.send_header("Content-Type", ctype if ctype.startswith("image/") else ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=300" if ctype.startswith("image/") else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def origin_ok(self):
        o = self.headers.get("Origin")
        return not o or urlparse(o).netloc == self.headers.get("Host")  # 同一オリジンのみ

    def target(self):
        return safe(parse_qs(urlparse(self.path).query).get("path", [""])[0])

    @guard
    def do_GET(self):
        u = urlparse(self.path).path
        if u == "/api/all":
            return self.send(body=json.dumps(read_all(self.dev), ensure_ascii=False).encode("utf-8"))
        if u == "/api/ls":  # サーバー上のフォルダ一覧(エクスプローラー風UI用)
            q = parse_qs(urlparse(self.path).query).get("p", [""])[0]
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
                rel = str(p)  # 別ドライブなど相対にできない場合は絶対パス
            drives = [f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.name == "nt" and os.path.exists(f"{c}:\\")]
            out = {"path": str(p), "rel": rel, "sep": os.sep, "parent": str(p.parent) if p.parent != p else None,
                   "dirs": dirs[:2000], "files": files[:2000], "drives": drives}
            return self.send(body=json.dumps(out, ensure_ascii=False).encode("utf-8"))
        if u == "/api/imgs":
            return self.send(body=json.dumps(list_imgs(), ensure_ascii=False).encode("utf-8"))
        if u == "/api/img":  # データフォルダからの相対パスで画像を返す(コピーしない)
            p = (DATA / parse_qs(urlparse(self.path).query).get("p", [""])[0]).resolve()
            if within(p) and p.is_file() and p.suffix.lower() in IMG_OK:
                return self.send(body=p.read_bytes(), ctype=mimetypes.guess_type(p.name)[0] or "application/octet-stream")
            return self.send(404)
        if u.startswith("/images/"):
            p = (DATA / unquote(u[1:])).resolve()
            if IMGDIR in p.parents and p.is_file() and p.suffix.lower() in IMG_OK:
                return self.send(body=p.read_bytes(), ctype=mimetypes.guess_type(p.name)[0] or "application/octet-stream")
            return self.send(404)
        if u == "/api/stamp":
            m = max((f.stat().st_mtime_ns for f in DATA.rglob("*.json") if ".local" not in f.parts), default=0)
            return self.send(body=str(m).encode(), ctype="text/plain")
        if u in ("/", "/index.html"):
            return self.send(body=(RES_DIR / "index.html").read_bytes(), ctype="text/html")
        self.send(404)

    @guard
    def do_PUT(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if not self.origin_ok():
            return self.send(403)
        if urlparse(self.path).path == "/api/me":
            set_name(self.dev, body.decode("utf-8", "replace").strip())
            return self.send()
        p = self.target()
        if not p:
            return self.send(400)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")  # 複数端末が同時に読んでも壊れないよう置き換えで保存
        tmp.write_bytes(body)
        os.replace(tmp, p)
        self.send()

    @guard
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        u = urlparse(self.path)
        if u.path != "/api/image" or not self.origin_ok():
            return self.send(400)
        name = parse_qs(u.query).get("name", ["image.png"])[0]
        ext = Path(name).suffix.lower()
        if ext not in IMG_OK or len(body) > 30_000_000:
            return self.send(400)
        fn = hashlib.sha1(body).hexdigest()[:10] + "_" + re.sub(r"[^\w\-]", "_", Path(name).stem)[:40] + ext
        IMGDIR.mkdir(exist_ok=True)
        if not (IMGDIR / fn).exists():
            (IMGDIR / fn).write_bytes(body)
        self.send(body=json.dumps({"path": "images/" + fn}).encode())

    @guard
    def do_DELETE(self):
        p = self.target()
        if not p or not self.origin_ok():
            return self.send(400)
        p.unlink(missing_ok=True)
        self.send()


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
    print("\n【他のPC・iPadなどから使う場合】同じWi-Fi/LAN内で、次のURLを開いてください（初回だけ ?key= 付き）:")
    for ip in lan_ips():
        print(f"   http://{ip}:{args.port}/?key={KEY}")
    print("   ※キーを知っている端末だけが開けます。開かない場合はOSのファイアウォールで、このアプリの通信（プライベートネットワーク）を許可してください。\n")
if not args.no_browser:
    threading.Timer(0.8, webbrowser.open, [url]).start()
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
