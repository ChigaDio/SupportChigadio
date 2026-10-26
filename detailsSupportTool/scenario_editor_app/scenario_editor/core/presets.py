"""Role の「名前付きプリセット」と「Role クリップボード」 (Qt 非依存)。

`js_ref/src/scenarioRolePresets.js` の移植。ブラウザの localStorage の代わりに、設定フォルダ
(既定 ``~/.scenario_editor/``)の JSON ファイルへ保存する。サーバーとの通信は注入された
``request_json(url, method='GET', body=None) -> (ok, status, body)`` で行う(ApiClient が提供)。

対応表 (JS -> Python):
    subscribePresets      -> PresetManager.subscribe
    listPresets           -> PresetManager.list_presets
    getLocalOnlyCount     -> PresetManager.get_local_only_count
    refreshPresets        -> PresetManager.refresh
    savePreset            -> PresetManager.save_preset
    deletePreset          -> PresetManager.delete_preset
    migrateLocalPresets   -> PresetManager.migrate_local_presets
    getPresetData         -> PresetManager.get_preset_data
    getRoleClipboard      -> RoleClipboard.get
    setRoleClipboard      -> RoleClipboard.set
    makeUniqueIds         -> make_unique_ids
保存形式(キー名・値の形)は JS と同じ: {Role名: [{name, data, savedAt, local?}]}。
"""
from __future__ import annotations

import copy
import json
import os
import time
from urllib.parse import quote

PRESET_FILE = "scn-role-presets-v1.json"
CLIPBOARD_FILE = "scn-role-clipboard-v1.json"
MAX_PRESETS_PER_ROLE = 30
PRESET_API = "/api/scenario-role-presets"


def default_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".scenario_editor")


def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def _write_json(path, value) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _as_list(x):
    return x if isinstance(x, list) else []


def _now_ms() -> int:
    return int(time.time() * 1000)


class PresetManager:
    """プリセット。サーバー(チーム共有)が正で、未接続時だけローカルファイルへ退避する。"""

    def __init__(self, request_json=None, directory=None):
        self._request = request_json
        self._dir = directory or default_dir()
        self._path = os.path.join(self._dir, PRESET_FILE)
        self._server = None          # {Role名: [..]} / 未取得は None
        self._local = None
        self._listeners = []

    # -- 通知
    def subscribe(self, fn):
        self._listeners.append(fn)
        return lambda: self._listeners.remove(fn) if fn in self._listeners else None

    def _notify(self):
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:  # noqa: BLE001  購読側のエラーは無視(JS と同じ)
                pass

    # -- ローカル
    def _load_local(self):
        if self._local is None:
            raw = _read_json(self._path, {})
            self._local = raw if isinstance(raw, dict) else {}
        return self._local

    def _save_local(self, obj) -> bool:
        if not _write_json(self._path, obj):
            return False
        self._local = obj
        return True

    # -- 参照
    def list_presets(self, role_name):
        server = _as_list(self._server.get(role_name)) if self._server else []
        names = {p.get("name") for p in server}
        local = [{**p, "local": True} for p in _as_list(self._load_local().get(role_name)) if p.get("name") not in names]
        return [*server, *local]

    def get_local_only_count(self) -> int:
        local = self._load_local()
        n = 0
        for role, items in local.items():
            names = {p.get("name") for p in _as_list(self._server.get(role))} if self._server else set()
            n += len([p for p in _as_list(items) if p.get("name") not in names])
        return n

    def get_preset_data(self, role_name, preset_name):
        p = next((x for x in self.list_presets(role_name) if x.get("name") == preset_name), None)
        return copy.deepcopy(p["data"]) if p else None

    # -- 通信
    def _req(self, url, method="GET", body=None):
        try:
            return self._request(url, method, body)
        except Exception:  # noqa: BLE001  未接続
            return None

    def refresh(self) -> bool:
        if self._request is None:
            return False
        r = self._req(PRESET_API)
        if not r:
            return False
        ok, _status, body = r
        if not ok or not isinstance(body, dict) or not isinstance(body.get("presets"), dict):
            return False
        self._server = body["presets"] or {}
        self._notify()
        return True

    def save_preset(self, role_name, preset_name, data) -> dict:
        name = str(preset_name or "").strip()
        if not role_name or not name or not isinstance(data, list):
            return {"ok": False, "shared": False}
        r = self._req(PRESET_API, "POST", {"roleName": role_name, "name": name, "data": data}) if self._request else None
        if r:
            ok, status, body = r
            if ok and isinstance(body, dict) and isinstance(body.get("presets"), list):
                self._server = {**(self._server or {}), role_name: body["presets"]}
                local = dict(self._load_local())
                if local.get(role_name):
                    local[role_name] = [p for p in local[role_name] if p.get("name") != name]
                    if not local[role_name]:
                        del local[role_name]
                    self._save_local(local)
                self._notify()
                return {"ok": True, "shared": True}
            if 400 <= status < 500:
                return {"ok": False, "shared": False, "error": (body or {}).get("error") if isinstance(body, dict) and body.get("error") else f"HTTP {status}"}
        local = dict(self._load_local())
        others = [p for p in _as_list(local.get(role_name)) if p.get("name") != name]
        local[role_name] = [{"name": name, "data": copy.deepcopy(data), "savedAt": _now_ms()}, *others][:MAX_PRESETS_PER_ROLE]
        if not self._save_local(local):
            return {"ok": False, "shared": False}
        self._notify()
        return {"ok": True, "shared": False}

    def delete_preset(self, role_name, preset_name) -> bool:
        removed = False
        on_server = bool(self._server) and any(p.get("name") == preset_name for p in _as_list(self._server.get(role_name)))
        if on_server:
            r = self._req(f"{PRESET_API}?roleName={quote(role_name, safe='')}&name={quote(preset_name, safe='')}", "DELETE")
            if r and (r[0] or r[1] == 404):
                nxt = dict(self._server)
                lst = [p for p in _as_list(nxt.get(role_name)) if p.get("name") != preset_name]
                if lst:
                    nxt[role_name] = lst
                else:
                    nxt.pop(role_name, None)
                self._server = nxt
                removed = True
            else:
                return False
        local = dict(self._load_local())
        if local.get(role_name) and any(p.get("name") == preset_name for p in local[role_name]):
            local[role_name] = [p for p in local[role_name] if p.get("name") != preset_name]
            if not local[role_name]:
                del local[role_name]
            self._save_local(local)
            removed = True
        if removed:
            self._notify()
        return removed

    def migrate_local_presets(self) -> dict:
        local = self._load_local()
        payload = {}
        for role, items in local.items():
            names = {p.get("name") for p in _as_list(self._server.get(role))} if self._server else set()
            its = [p for p in _as_list(items) if p.get("name") not in names]
            if its:
                payload[role] = its
        if not payload:
            return {"ok": True, "imported": 0, "skipped": 0}
        r = self._req(f"{PRESET_API}/import", "POST", {"presets": payload}) if self._request else None
        if not r or not r[0] or not r[2]:
            return {"ok": False, "imported": 0, "skipped": 0}
        body = r[2]
        self._server = body.get("presets") or self._server
        remaining = {}
        for role, items in local.items():
            names = {p.get("name") for p in _as_list((self._server or {}).get(role))}
            rest = [p for p in _as_list(items) if p.get("name") not in names]
            if rest:
                remaining[role] = rest
        self._save_local(remaining)
        self._notify()
        return {"ok": True, "imported": body.get("imported") or 0, "skipped": body.get("skipped") or 0}


class RoleClipboard:
    """Role を値ごとコピーするための一時置き場。ファイルに保存するので、アプリを複数起動しても貼り付けられる。"""

    def __init__(self, directory=None):
        self._path = os.path.join(directory or default_dir(), CLIPBOARD_FILE)

    def get(self):
        raw = _read_json(self._path, [])      # JS はキャッシュだが、別プロセス共有のため毎回ファイルを見る(小さい)
        return raw if isinstance(raw, list) else []

    def set(self, roles) -> int:
        items = [{"id": r.get("id"), "name": r.get("name"), "branchType": r.get("branchType") or "General",
                  "data": copy.deepcopy(r.get("data") or [])} for r in roles or []]
        _write_json(self._path, items)
        return len(items)


def make_unique_ids(count, existing_ids=None):
    """貼り付け用の uniqueId を count 個、重複しないように採番する(JS の makeUniqueIds と同じ規則)。"""
    base = _now_ms()
    for id_ in existing_ids or []:
        try:
            n = float(id_)
        except (TypeError, ValueError):
            continue
        if n == n and n not in (float("inf"), float("-inf")) and n >= base:
            base = int(n) + 1
    return [str(base + i) for i in range(count)]
