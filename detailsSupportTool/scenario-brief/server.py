"""シナリオ演出依頼資料集 ローカルサーバー (標準ライブラリのみ)
使い方: python server.py [--data データ保存先] [--port 8765] [--no-browser]
データは  project.json / chapters/ / dictionary/ / users/<名前>/  に1ファイルずつ保存されます。
"""
import argparse, json, sys, threading, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=str(APP_DIR / "scenario-data"))
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--no-browser", action="store_true")
args = ap.parse_args()

DATA = Path(args.data).resolve()
DATA.mkdir(parents=True, exist_ok=True)
LOCAL = DATA / ".local"  # 自分用の設定(名前)。Git管理しない
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


def read_all():
    me = LOCAL / "me.txt"
    o = {"me": me.read_text("utf-8").strip() if me.exists() else "",
         "project": (rj(DATA / "project.json") or {}).get("name", ""),
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


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code=200, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def origin_ok(self):
        o = self.headers.get("Origin")
        return not o or o in (f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}")

    def target(self):
        return safe(parse_qs(urlparse(self.path).query).get("path", [""])[0])

    def do_GET(self):
        u = urlparse(self.path).path
        if u == "/api/all":
            return self.send(body=json.dumps(read_all(), ensure_ascii=False).encode("utf-8"))
        if u in ("/", "/index.html"):
            return self.send(body=(RES_DIR / "index.html").read_bytes(), ctype="text/html")
        self.send(404)

    def do_PUT(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if not self.origin_ok():
            return self.send(403)
        if urlparse(self.path).path == "/api/me":
            LOCAL.mkdir(exist_ok=True)
            (LOCAL / "me.txt").write_bytes(body)
            return self.send()
        p = self.target()
        if not p:
            return self.send(400)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        self.send()

    def do_DELETE(self):
        p = self.target()
        if not p or not self.origin_ok():
            return self.send(400)
        p.unlink(missing_ok=True)
        self.send()


srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
url = f"http://127.0.0.1:{args.port}/"
print("データ保存先:", DATA)
print("起動しました:", url, " (このウィンドウを閉じる / Ctrl+C で終了)")
if not args.no_browser:
    threading.Timer(0.8, webbrowser.open, [url]).start()
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
