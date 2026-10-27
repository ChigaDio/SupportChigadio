#!/usr/bin/env python3
"""設定資料集エディタ用の軽量サーバー（Python標準ライブラリのみ）

  python3 server.py                 # ./project をデータフォルダにして 0.0.0.0:8000 で起動
  python3 server.py --token 合言葉   # 外部公開するときは合言葉を付ける
  python3 server.py --tunnel        # cloudflared があれば外部URLも発行

データは project/ 以下の「小さなJSONファイル」と images/<セクション>/ の画像。
そのまま git で管理できます（1ページ=1ファイル、画像は内容ハッシュ名）。
"""
import argparse, hashlib, http.server, json, os, re, secrets, shutil, socket, subprocess, threading, time, urllib.parse

APP = os.path.dirname(os.path.abspath(__file__))
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif"}
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".gif": "image/gif", ".svg": "image/svg+xml", ".avif": "image/avif"}
PATH_OK = re.compile(r"^[A-Za-z0-9_\-./]+$")
LOCK = threading.Lock()


def sha(b):
    return hashlib.sha1(b).hexdigest()


class Store:
    def __init__(self, root, browse=None):
        self.root = os.path.abspath(root)
        os.makedirs(os.path.join(self.root, "images"), exist_ok=True)
        self.browse = [os.path.realpath(b) for b in (browse or []) if os.path.isdir(b)]

    # ---- サーバー上のフォルダ参照（エクスプローラー風UI用）
    def roots(self):
        return [{"i": i, "label": os.path.basename(b.rstrip(os.sep)) or b, "abs": b} for i, b in enumerate(self.browse)]

    def inside(self, full):
        full = os.path.realpath(full)
        return any(full == b or full.startswith(b + os.sep) for b in self.browse + [os.path.realpath(self.root)])

    def fs_list(self, i, sub):
        if i < 0 or i >= len(self.browse):
            return None
        root = self.browse[i]
        target = os.path.realpath(os.path.join(root, sub or ""))
        if not (target == root or target.startswith(root + os.sep)) or not os.path.isdir(target):
            return None
        out = []
        try:
            names = sorted(os.listdir(target), key=lambda n: n.lower())
        except OSError:
            names = []
        for n in names[:3000]:
            if n.startswith("."):
                continue
            full = os.path.join(target, n)
            try:
                if os.path.isdir(full):
                    out.append({"name": n, "type": "dir"})
                elif os.path.splitext(n)[1].lower() in IMG_EXT:
                    out.append({"name": n, "type": "img", "size": os.path.getsize(full),
                                "ref": os.path.relpath(os.path.realpath(full), self.root).replace(os.sep, "/")})
            except OSError:
                pass
        out.sort(key=lambda e: (e["type"] != "dir",))
        rel = os.path.relpath(target, root).replace(os.sep, "/")
        return {"root": i, "sub": "" if rel == "." else rel, "entries": out}

    def safe(self, rel):
        if not rel or not PATH_OK.match(rel) or ".." in rel.split("/") or rel.startswith("/"):
            return None
        full = os.path.abspath(os.path.join(self.root, rel))
        return full if full.startswith(self.root + os.sep) else None

    def writable(self, rel):
        top = rel.split("/")[0]
        ext = os.path.splitext(rel)[1]
        if top in ("project.json",):
            return ext == ".json"
        if top in ("sections", "items", "templates"):
            return ext in (".json", ".jsonl")
        return top == "images" and ext == ".json"  # 画像のタグ(サイドカー)

    def read(self, full):
        try:
            with open(full, "rb") as f:
                return f.read()
        except OSError:
            return None

    def text_files(self):
        out = {}
        b = self.read(os.path.join(self.root, "project.json"))
        if b is not None:
            out["project.json"] = b
        for top in ("sections", "items", "templates"):
            for d, _, fs in os.walk(os.path.join(self.root, top)):
                for fn in fs:
                    if fn.endswith((".json", ".jsonl")):
                        full = os.path.join(d, fn)
                        b = self.read(full)
                        if b is not None:
                            out[os.path.relpath(full, self.root).replace(os.sep, "/")] = b
        return out

    def assets(self):
        out = []
        base = os.path.join(self.root, "images")
        for d, _, fs in os.walk(base):
            for fn in fs:
                stem, ext = os.path.splitext(fn)
                if ext.lower() not in IMG_EXT:
                    continue
                full = os.path.join(d, fn)
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                folder = os.path.relpath(d, base).replace(os.sep, "/")
                meta, sh = {}, None
                sb = self.read(os.path.join(d, stem + ".json"))
                if sb is not None:
                    sh = sha(sb)
                    try:
                        meta = json.loads(sb.decode("utf-8"))
                    except Exception:
                        meta = {}
                st = os.stat(full)
                out.append({"path": rel, "folder": folder if folder != "." else "", "name": meta.get("name") or fn,
                            "tags": meta.get("tags") or [], "added": meta.get("added") or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(st.st_mtime)),
                            "sh": sh, "size": st.st_size})
        out.sort(key=lambda a: a["added"], reverse=True)
        return out

    def digest(self):
        h = hashlib.sha1()
        base = os.path.join(self.root, "images")
        for d, _, fs in os.walk(base):
            for fn in sorted(fs):
                st = os.stat(os.path.join(d, fn))
                h.update(f"{d}/{fn}:{st.st_mtime_ns}:{st.st_size}".encode())
        return h.hexdigest()[:12]


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


def make_handler(store, token):
    class H(http.server.BaseHTTPRequestHandler):
        server_version = "SettingBook/1"

        def log_message(self, fmt, *a):
            if "/api/stat" not in (a[0] if a else ""):
                print("  ", self.address_string(), fmt % a)

        # ---- helpers
        def send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def authed(self):
            if not token:
                return True
            ck = self.headers.get("Cookie", "")
            return f"sb={token}" in [c.strip() for c in ck.split(";")]

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 80 * 1024 * 1024:
                return None
            return self.rfile.read(n)

        # ---- routes
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if token and q.get("t", [""])[0] == token:  # ?t=合言葉 でCookieを付けて入り直す
                return self.send(302, b"", extra={"Location": u.path or "/", "Set-Cookie": f"sb={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000"})
            if not self.authed():
                return self.send(401, "合言葉が必要です。URLの末尾に ?t=合言葉 を付けてアクセスしてください。".encode(), "text/plain; charset=utf-8")
            p = urllib.parse.unquote(u.path)
            if p.startswith("/api/"):
                return self.api_get(p[5:], q)
            if p == "/":
                p = "/index.html"
            if p.startswith("/images/"):
                full = store.safe(p[1:])
                cache = "public, max-age=86400"
            elif p == "/index.html" or p.startswith("/lib/"):
                full = os.path.abspath(os.path.join(APP, p.lstrip("/")))
                full = full if full.startswith(APP + os.sep) else None
                cache = "no-cache"
            else:
                full, cache = None, ""
            if not full or not os.path.isfile(full):
                return self.send(404, b"not found", "text/plain")
            with open(full, "rb") as f:
                data = f.read()
            self.send(200, data, MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream"), {"Cache-Control": cache})

        def api_get(self, name, q):
            if name == "ping":
                return self.send(200, {"ok": True, "ver": 1})
            if name in ("state", "stat"):
                files = store.text_files()
                if name == "stat":
                    return self.send(200, {"files": {k: sha(v) for k, v in files.items()}, "digest": store.digest()})
                return self.send(200, {"files": {k: {"t": v.decode("utf-8", "replace"), "h": sha(v)} for k, v in files.items()},
                                       "assets": store.assets(), "digest": store.digest()})
            if name == "assets":
                return self.send(200, {"assets": store.assets(), "digest": store.digest()})
            if name == "fs/roots":
                return self.send(200, {"roots": store.roots()})
            if name == "fs/list":
                r = store.fs_list(int((q.get("root") or ["0"])[0] or 0), (q.get("sub") or [""])[0])
                return self.send(200, r) if r is not None else self.send(404, {"error": "not found"})
            if name == "fs/file":
                ref = (q.get("p") or [""])[0]
                full = os.path.realpath(os.path.join(store.root, ref))
                if (not store.browse and not full.startswith(os.path.realpath(store.root) + os.sep)) or not store.inside(full) \
                        or os.path.splitext(full)[1].lower() not in IMG_EXT or not os.path.isfile(full):
                    return self.send(404, b"not found", "text/plain")
                with open(full, "rb") as f:
                    data = f.read()
                return self.send(200, data, MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream"), {"Cache-Control": "private, max-age=300"})
            self.send(404, {"error": "unknown"})

        def do_POST(self):
            self.route_write()

        def do_PUT(self):
            self.route_write()

        def route_write(self):
            if not self.authed():
                return self.send(401, {"error": "auth"})
            u = urllib.parse.urlparse(self.path)
            name = urllib.parse.unquote(u.path)[5:] if u.path.startswith("/api/") else ""
            q = urllib.parse.parse_qs(u.query)
            raw = self.body()
            if raw is None:
                return self.send(413, {"error": "too large"})
            try:
                if name == "file":
                    return self.put_file(json.loads(raw.decode("utf-8")))
                if name == "delete":
                    return self.del_file(json.loads(raw.decode("utf-8")))
                if name == "upload":
                    return self.upload(q, raw)
                if name == "fs/import":
                    return self.fs_import(json.loads(raw.decode("utf-8")))
            except Exception as e:  # noqa
                return self.send(400, {"error": str(e)})
            self.send(404, {"error": "unknown"})

        def put_file(self, j):
            rel, text, base = j.get("path"), j.get("text", ""), j.get("base")
            full = store.safe(rel or "")
            if not full or not store.writable(rel):
                return self.send(400, {"error": "bad path"})
            with LOCK:
                cur = store.read(full)
                ch = sha(cur) if cur is not None else None
                if ch != base and not (cur is None and base is None):
                    return self.send(409, {"t": cur.decode("utf-8", "replace") if cur is not None else None, "h": ch})
                os.makedirs(os.path.dirname(full), exist_ok=True)
                data = text.encode("utf-8")
                tmp = full + ".tmp" + secrets.token_hex(3)
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, full)
            self.send(200, {"h": sha(data)})

        def del_file(self, j):
            rel, base = j.get("path"), j.get("base")
            full = store.safe(rel or "")
            if not full or not store.writable(rel):
                return self.send(400, {"error": "bad path"})
            with LOCK:
                cur = store.read(full)
                if cur is None:
                    return self.send(200, {"ok": True})
                if sha(cur) != base:
                    return self.send(409, {"t": cur.decode("utf-8", "replace"), "h": sha(cur)})
                os.remove(full)
                d = os.path.dirname(full)
                try:
                    while d != store.root and not os.listdir(d):
                        os.rmdir(d)
                        d = os.path.dirname(d)
                except OSError:
                    pass
            self.send(200, {"ok": True})

        def save_image(self, raw, name, folder, tags):
            folder = re.sub(r"[^a-z0-9_\-]", "", (folder or "misc").lower()) or "misc"
            ext = os.path.splitext(name)[1].lower()
            if raw[:8] == b"\x89PNG\r\n\x1a\n":
                ext = ".png"
            elif raw[:3] == b"\xff\xd8\xff":
                ext = ".jpg"
            elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
                ext = ".webp"
            elif raw[:4] == b"GIF8":
                ext = ".gif"
            if ext not in IMG_EXT:
                return None
            h = sha(raw)[:16]
            rel = f"images/{folder}/{h}{ext}"
            full = store.safe(rel)
            dup = os.path.exists(full)
            if not dup:
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "wb") as f:
                    f.write(raw)
            side = full[: -len(ext)] + ".json"
            if not os.path.exists(side):
                tl = [t.strip() for t in re.split(r"[,、\s]+", tags or "") if t.strip()]
                meta = {"added": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "name": name, "tags": tl}
                with open(side, "w", encoding="utf-8") as f:
                    f.write(json.dumps(meta, ensure_ascii=False, sort_keys=True) + "\n")
            return {"path": rel, "dup": dup}

        def upload(self, q, raw):
            r = self.save_image(raw, q.get("name", ["image"])[0], q.get("folder", ["misc"])[0], q.get("tags", [""])[0])
            self.send(200, r) if r else self.send(400, {"error": "image only"})

        def fs_import(self, j):
            full = os.path.realpath(os.path.join(store.root, j.get("ref", "")))
            if not store.inside(full) or os.path.splitext(full)[1].lower() not in IMG_EXT or not os.path.isfile(full):
                return self.send(404, {"error": "not found"})
            with open(full, "rb") as f:
                raw = f.read()
            r = self.save_image(raw, os.path.basename(full), j.get("folder", "misc"), j.get("tags", ""))
            self.send(200, r) if r else self.send(400, {"error": "image only"})

    return H


def main():
    ap = argparse.ArgumentParser(description="設定資料集エディタ サーバー")
    ap.add_argument("--project", default=os.path.join(os.getcwd(), "project"), help="データフォルダ（gitで管理するフォルダ）")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--browse", action="append", help="画像を選べるサーバー側フォルダ（複数指定可・カレントからの相対でも絶対でも）。既定は一つ上の階層")
    ap.add_argument("--no-browse", action="store_true", help="サーバー側フォルダの参照を無効にする")
    ap.add_argument("--token", default="", help="合言葉（外部公開時は必ず指定）")
    ap.add_argument("--tunnel", action="store_true", help="cloudflared があれば外部URLも発行")
    a = ap.parse_args()
    token = a.token or (secrets.token_urlsafe(9) if a.tunnel else "")
    browse = [] if a.no_browse else (a.browse or [".."])
    store = Store(a.project, [os.path.abspath(b) for b in browse])
    srv = http.server.ThreadingHTTPServer((a.host, a.port), make_handler(store, token))
    suffix = f"/?t={token}" if token else "/"
    print("\n設定資料集エディタを起動しました")
    print(f"  データフォルダ : {store.root}")
    print(f"  画像の参照範囲 : " + (", ".join(b["abs"] for b in store.roots()) or "なし（--no-browse）"))
    print(f"  このPC        : http://localhost:{a.port}{suffix}")
    for ip in lan_ips():
        print(f"  同じWi-Fi内   : http://{ip}:{a.port}{suffix}   （iPadなどはこちら）")
    if not token:
        print("  ※ 外部に公開するなら --token 合言葉 を付けてください")
    if a.tunnel:
        exe = shutil.which("cloudflared")
        if exe:
            print("  外部URLを発行中…（表示される https://....trycloudflare.com の末尾に ?t=合言葉 を付けて開く）")
            subprocess.Popen([exe, "tunnel", "--url", f"http://localhost:{a.port}"])
        else:
            print("  cloudflared が見つかりません。 https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/ から入れるか、ngrok / Tailscale を使ってください。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します")


if __name__ == "__main__":
    main()
