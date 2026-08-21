# -*- coding: utf-8 -*-
"""
アプリ設定の永続化管理。
作業フォルダパスなどを ~/.sound_ext_converter/config.json に保存する。
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any

CONFIG_DIR = Path.home() / ".sound_ext_converter"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(data: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_work_dir() -> Optional[str]:
    cfg = load_config()
    path = cfg.get("work_dir")
    if path and Path(path).is_dir():
        return path
    return None


def set_work_dir(path: str) -> None:
    cfg = load_config()
    cfg["work_dir"] = str(path)
    save_config(cfg)


def get_last_target_ext() -> str:
    cfg = load_config()
    return cfg.get("last_target_ext", "mp3")


def set_last_target_ext(key: str) -> None:
    cfg = load_config()
    cfg["last_target_ext"] = key
    save_config(cfg)


def get_delete_original() -> bool:
    cfg = load_config()
    return bool(cfg.get("delete_original", False))


def set_delete_original(value: bool) -> None:
    cfg = load_config()
    cfg["delete_original"] = bool(value)
    save_config(cfg)
