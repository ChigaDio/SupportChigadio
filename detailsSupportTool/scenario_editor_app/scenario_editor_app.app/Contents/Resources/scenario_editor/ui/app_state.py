"""アプリ全体の共有状態 (API クライアント / マスタキャッシュ / 設定 / 通知)。"""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, Signal

from ..api.client import DEFAULT_BASE_URL, ApiClient
from ..api.lookups import LookupCache
from ..core import presets as presets_mod
from ..core.role_form import RecentColors
from ..core.transition_ops import NodeColorStore

SETTINGS_FILE = "settings.json"
DEFAULT_SETTINGS = {"baseUrl": DEFAULT_BASE_URL, "theme": "dark", "recent": [], "window": None}


class AppState(QObject):
    toast = Signal(str, str)            # (message, level: info|success|warning|error)
    navigate = Signal(str, dict)        # (page, params)
    themeChanged = Signal(str)
    connectionChanged = Signal(bool)

    def __init__(self, directory: str | None = None, parent=None):
        super().__init__(parent)
        self.directory = directory or presets_mod.default_dir()
        self.settings = self._load_settings()
        self.api = ApiClient(self.settings["baseUrl"])
        self.lookups = LookupCache(self.api)
        self.presets = presets_mod.PresetManager(self.api.request_json, self.directory)
        self.clipboard = presets_mod.RoleClipboard(self.directory)
        self.node_colors = NodeColorStore(self.directory)
        self.recent_colors = RecentColors(self.directory)
        self.connected = False

    # --- 設定
    def _path(self) -> str:
        return os.path.join(self.directory, SETTINGS_FILE)

    def _load_settings(self) -> dict:
        s = dict(DEFAULT_SETTINGS)
        try:
            with open(self._path(), "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                s.update(raw)
        except (OSError, ValueError):
            pass
        return s

    def save_settings(self) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def set_base_url(self, url: str) -> None:
        url = (url or "").strip().rstrip("/") or DEFAULT_BASE_URL
        self.settings["baseUrl"] = url
        self.api = ApiClient(url)
        self.lookups = LookupCache(self.api)
        self.presets = presets_mod.PresetManager(self.api.request_json, self.directory)
        self.save_settings()

    def add_recent(self, kind: str, params: dict, label: str) -> None:
        rec = [r for r in self.settings.get("recent", []) if not (r.get("kind") == kind and r.get("params") == params)]
        rec.insert(0, {"kind": kind, "params": params, "label": label})
        self.settings["recent"] = rec[:12]
        self.save_settings()

    # --- 通知 / 遷移
    def show_toast(self, msg: str, level: str = "info") -> None:
        self.toast.emit(str(msg), level)

    def go(self, page: str, **params) -> None:
        self.navigate.emit(page, params)

    def error_message(self, e: BaseException, prefix: str = "") -> str:
        return f"{prefix}{e}" if prefix else str(e)
