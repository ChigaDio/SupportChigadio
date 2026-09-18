#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ScenarioMatrix 高速編集ツール（モダンUI）

起動:
  python scenario_matrix_editor.py
  python scenario_matrix_editor.py /path/to/ScenarioText.json

主な機能:
  - JSON パス／タグ定義パスを相対パスで自動保持（再起動しても前回のファイル/行/列/フィールドを復元）
  - 設定・タグ定義は  <このファイルの2つ上>/data/editor_config/  に自動生成
  - テキスト取込時は空行を捨てる
  - 選択行の左の「＋」から「上に追加 / 下に追加」
  - ドラッグ＆ドロップは「行間に挿入」（挿入位置をラインで表示）
  - 行ごとの演出メモ（コメント）を保存（サイドカー JSON）
  - 本文入力中のタグ補完（Ctrl+Space）と / による自動閉じタグ
    （既存の日本語・英語本文の途中でも <s などで候補が出る）
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict, List, Optional, Tuple

# PyInstaller で exe 化すると certifi の証明書バンドルの場所が変わり、
# 翻訳機能の HTTPS 通信が SSL エラーで失敗することがある
# （例外は握り潰されて「翻訳が反映されない」だけに見える）。
# 明示的に certifi の証明書を指すよう環境変数を設定しておく。
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass

C = {
    "bg": "#0f1419",
    "surface": "#1a2332",
    "surface2": "#243044",
    "border": "#2d3a4f",
    "accent": "#3d8bfd",
    "accent_hover": "#5ba0ff",
    "accent_dim": "#1e3a5f",
    "text": "#e7ecf3",
    "text_muted": "#8b9bb4",
    "success": "#3dd68c",
    "danger": "#f07178",
    "list_sel": "#2a4a7a",
    "input_bg": "#0d1117",
    "comment": "#f0c674",
}

# ---------------------------------------------------------------------------
# 設定フォルダ（このファイルの2つ上の data フォルダ配下に専用フォルダを作る）
# ---------------------------------------------------------------------------


def _resolve_script_dir() -> str:
    """
    通常の .py 実行なら __file__ の場所。
    PyInstaller で exe 化した場合、__file__ は一時展開フォルダ
    (AppData\\Local\\Temp\\_MEIxxxxx) を指してしまうため、その場合は
    sys.executable（実際に置いた .exe の場所）を使う。
    """
    if getattr(sys, "frozen", False):
        # PyInstaller (onefile/onedir 共通): exe の実際の場所
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


SCRIPT_DIR = _resolve_script_dir()
CONFIG_FOLDER_NAME = "editor_config"
DATA_DIR_OVERRIDE_FILENAME = "data_dir_override.txt"


def _read_data_dir_override() -> Optional[str]:
    """
    scenario_matrix_editor.py（または .exe）と同じフォルダに
    data_dir_override.txt があれば、その1行目に書かれたパスを
    data フォルダとして最優先で使う。起動方法（.py / exe / 展開先の
    変化）に一切依存させたくない場合の明示的な逃げ道。
    """
    override_path = os.path.join(SCRIPT_DIR, DATA_DIR_OVERRIDE_FILENAME)
    try:
        with open(override_path, "r", encoding="utf-8") as f:
            line = f.readline().strip().strip('"')
        if line:
            return os.path.normpath(line)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[config] {DATA_DIR_OVERRIDE_FILENAME} の読込に失敗: {e}", file=sys.stderr)
    return None


def _resolve_data_dir() -> str:
    """
    優先順位:
      1. data_dir_override.txt に書かれたパス
      2. <script/exe>/../../data （既存なら使う）
      3. <script/exe> から上へ5階層まで data を探す
      4. どれも無ければ 2. の位置に新規作成
    """
    override = _read_data_dir_override()
    if override:
        print(f"[config] data_dir_override.txt を使用: {override}")
        return override

    primary = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..","..", "data"))
    if os.path.isdir(primary):
        return primary
    cur = SCRIPT_DIR
    for _ in range(5):
        cand = os.path.join(cur, "data")
        if os.path.isdir(cand):
            return os.path.normpath(cand)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return primary  # 見つからなければ規定位置に作る


def _resolve_config_dir() -> str:
    d = os.path.join(_resolve_data_dir(), CONFIG_FOLDER_NAME)
    try:
        os.makedirs(d, exist_ok=True)
        return os.path.normpath(d)
    except Exception as e:
        print(f"[config] data 配下に作成できません: {e}", file=sys.stderr)
        fallback = os.path.join(SCRIPT_DIR, CONFIG_FOLDER_NAME)
        os.makedirs(fallback, exist_ok=True)
        return os.path.normpath(fallback)


CONFIG_DIR = _resolve_config_dir()
SETTINGS_PATH = os.path.join(CONFIG_DIR, "editor_settings.json")
TAGS_PATH = os.path.join(CONFIG_DIR, "text_animator_tags.json")
COMMENTS_PATH = os.path.join(CONFIG_DIR, "row_comments.json")

# ---------------------------------------------------------------------------
# シナリオイベント／ロール／トランザクション(DSL) 関連データ
# ---------------------------------------------------------------------------
# CONFIG_DIR と同じ「_resolve_data_dir() の下」に置く。
# _resolve_data_dir() は PyInstaller で exe 化しても sys.executable の実際の
# 場所を基準に解決される(_resolve_script_dir 参照)ので、ここから作る
# scenario/ 配下のファイルパスもすべて exe を置いた場所からの相対パスとして
# 一貫して扱える(= 「ちゃんと相対パスで」の対象に含める)。
SCENARIO_DIR = os.path.join(_resolve_data_dir(), "scenario")
SCENARIO_EVENTS_PATH = os.path.join(SCENARIO_DIR, "scenario_events.json")
SCENARIO_ROLES_PATH = os.path.join(SCENARIO_DIR, "scenario_roles.json")
SCENARIO_ROLE_SCHEMA_DIR = os.path.join(SCENARIO_DIR, "role_schemas")
SCENARIO_CLASS_DATA_DIR = os.path.join(SCENARIO_DIR, "class_data")
SCENARIO_TRANSACTION_DIR = os.path.join(SCENARIO_DIR, "transactions")
for _d in (SCENARIO_DIR, SCENARIO_ROLE_SCHEMA_DIR, SCENARIO_CLASS_DATA_DIR, SCENARIO_TRANSACTION_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except Exception as _e:
        print(f"[scenario] フォルダ作成に失敗: {_d}: {_e}", file=sys.stderr)

print(f"[config] frozen={getattr(sys, 'frozen', False)}  SCRIPT_DIR={SCRIPT_DIR}")
print(f"[config] CONFIG_DIR={CONFIG_DIR}")


def to_relative_path(path: str) -> str:
    """設定ファイルへの保存用: 可能なら SCRIPT_DIR（実行環境の基準位置）からの
    相対パスに変換する。ドライブが違う等で相対化できない場合のみ絶対パスのまま返す。
    これにより D:\\...\\TextScenario 一式をどこへ移しても設定が有効なままになる。"""
    if not path:
        return path
    try:
        return os.path.relpath(os.path.abspath(path), SCRIPT_DIR)
    except ValueError:
        return os.path.abspath(path)


def from_stored_path(stored: str) -> str:
    """設定ファイルに保存されていたパス（相対 or 旧形式の絶対）を絶対パスに戻す。"""
    if not stored:
        return stored
    if os.path.isabs(stored):
        return stored
    return os.path.normpath(os.path.join(SCRIPT_DIR, stored))


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(default))


def _write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


DEFAULT_SETTINGS = {
    "version": 1,
    "last_matrix_path": "",
    "last_row": "",
    "last_col": "",
    "last_field": "texts",
    "tags_path": "",
    "geometry": "",
    "recent_paths": [],
}


def load_settings() -> dict:
    s = _read_json(SETTINGS_PATH, DEFAULT_SETTINGS)
    if not isinstance(s, dict):
        s = json.loads(json.dumps(DEFAULT_SETTINGS))
    for k, v in DEFAULT_SETTINGS.items():
        s.setdefault(k, json.loads(json.dumps(v)))
    return s


def save_settings(s: dict) -> None:
    try:
        _write_json(SETTINGS_PATH, s)
    except Exception as e:
        print(f"[settings] 保存失敗: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Text Animator タグ定義（初回起動時に自動生成）
# ---------------------------------------------------------------------------

DEFAULT_TAG_CONFIG = {
    "version": 1,
    "description": "Unity Text Animator タグ定義。ユーザーが自由に追加・編集可能。",
    "behavior_tags": [
        {"id": "shake", "label": "Shake", "modifiers": ["a", "d"], "example": "<shake a=1.5>"},
        {"id": "wiggle", "label": "Wiggle", "modifiers": ["a", "f"], "example": "<wiggle a=2>"},
        {"id": "wave", "label": "Wave", "modifiers": ["a", "f", "w"], "example": "<wave f=3>"},
        {"id": "bounce", "label": "Bounce", "modifiers": ["a", "f", "w"], "example": "<bounce>"},
        {"id": "slide", "label": "Slide", "modifiers": ["a", "f", "w"], "example": "<slide>"},
        {"id": "swing", "label": "Swing", "modifiers": ["a", "f", "w"], "example": "<swing>"},
        {"id": "pend", "label": "Pendulum", "modifiers": ["a", "f", "w"], "example": "<pend>"},
        {"id": "dangle", "label": "Dangle", "modifiers": ["a", "f", "w"], "example": "<dangle>"},
        {"id": "fade", "label": "Fade", "modifiers": ["d"], "example": "<fade d=0.5>"},
        {"id": "rainb", "label": "Rainbow", "modifiers": ["f", "w"], "example": "<rainb>"},
        {"id": "rot", "label": "Rotate", "modifiers": ["f", "w"], "example": "<rot>"},
        {"id": "incr", "label": "Increase Size", "modifiers": ["a", "f", "w"], "example": "<incr>"},
        {"id": "size", "label": "Size (TMP)", "modifiers": [], "example": "<size=120%>"},
        {"id": "color", "label": "Color (TMP)", "modifiers": [], "example": "<color=#FF0000>"},
        {"id": "b", "label": "Bold", "modifiers": [], "example": "<b>"},
        {"id": "i", "label": "Italic", "modifiers": [], "example": "<i>"},
        {"id": "noparse", "label": "No Parse", "modifiers": [], "example": "<noparse>"},
    ],
    "appearance_tags": [
        {"id": "rot", "label": "Rotating", "modifiers": ["a", "d"], "open": "{rot}", "close": "{/rot}"},
        {"id": "diagexp", "label": "Diagonal Expand", "modifiers": ["bot", "d"], "open": "{diagexp}", "close": "{/diagexp}"},
        {"id": "horiexp", "label": "Horizontal Expand", "modifiers": ["d", "x"], "open": "{horiexp}", "close": "{/horiexp}"},
        {"id": "vertexp", "label": "Vertical Expand", "modifiers": ["bot", "d"], "open": "{vertexp}", "close": "{/vertexp}"},
        {"id": "offset", "label": "Offset", "modifiers": ["a", "d"], "open": "{offset}", "close": "{/offset}"},
        {"id": "fade", "label": "Fade", "modifiers": ["d"], "open": "{fade}", "close": "{/fade}"},
    ],
    "close_all": {"behavior": "</>", "appearance": "{/}", "disappearance": "{/#}"},
    "modifier_help": {
        "a": "amplitude（強度）",
        "f": "frequency / speed（速さ）",
        "w": "wave size（均一さ）",
        "d": "delay（秒）",
        "s": "speed",
        "bot": "from bottom",
        "x": "horizontal factor",
    },
}


def ensure_tag_file(path: str) -> str:
    """タグ定義 JSON が無ければ既定値で自動生成し、そのパスを返す。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.isfile(path):
            _write_json(path, DEFAULT_TAG_CONFIG)
            print(f"[tags] 自動生成: {path}")
    except Exception as e:
        print(f"[tags] 生成失敗: {e}", file=sys.stderr)
    return path


# ---------------------------------------------------------------------------
# 行コメント（演出メモ）のサイドカー保存
# ---------------------------------------------------------------------------

class CommentStore:
    """matrix ファイル / 行 / 列 / フィールド ごとに、行インデックス順のコメントを保持。"""

    def __init__(self, path: str = COMMENTS_PATH):
        self.path = path
        self.data: dict = _read_json(path, {"version": 1, "files": {}})
        if not isinstance(self.data, dict) or "files" not in self.data:
            self.data = {"version": 1, "files": {}}

    @staticmethod
    def _cell_key(row: str, col: str, field: str) -> str:
        return f"{row}\u0001{col}\u0001{field}"

    def get(self, matrix_path: Optional[str], row: str, col: str, field: str, count: int) -> List[str]:
        if not matrix_path:
            return [""] * count
        files = self.data.get("files") or {}
        cells = files.get(os.path.normcase(os.path.abspath(matrix_path))) or {}
        vals = cells.get(self._cell_key(row, col, field)) or []
        out = [str(v) for v in vals][:count]
        out += [""] * (count - len(out))
        return out

    def set(self, matrix_path: Optional[str], row: str, col: str, field: str, comments: List[str]) -> None:
        if not matrix_path:
            return
        key = os.path.normcase(os.path.abspath(matrix_path))
        files = self.data.setdefault("files", {})
        cells = files.setdefault(key, {})
        ck = self._cell_key(row, col, field)
        if any(c.strip() for c in comments):
            cells[ck] = list(comments)
        else:
            cells.pop(ck, None)
            if not cells:
                files.pop(key, None)

    def save(self) -> None:
        try:
            _write_json(self.path, self.data)
        except Exception as e:
            print(f"[comments] 保存失敗: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# JSON ユーティリティ
# ---------------------------------------------------------------------------

def protect_tags(text: str) -> Tuple[str, List[str]]:
    tag_re = re.compile(
        r"</?[a-zA-Z0-9_#]+(?:\s+[a-zA-Z0-9_]+\s*[=*]\s*[^>\s]+)*\s*/?>|"
        r"\{/?#?[a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+\s*[=*]\s*[^}\s]+)*\s*\}"
    )
    tags: List[str] = []

    def _repl(m: re.Match) -> str:
        tags.append(m.group(0))
        return f"\x00TAG{len(tags) - 1}\x00"

    return tag_re.sub(_repl, text), tags


def restore_tags(text: str, tags: List[str]) -> str:
    for i, tag in enumerate(tags):
        text = text.replace(f"\x00TAG{i}\x00", tag)
    return text


def try_translate(text: str, source: str = "ja", target: str = "en") -> str:
    """後方互換用（失敗時は元のテキストを返す・単発呼び出し向け）。
    バッチ翻訳では translate_text() + 共有 translator を使う。"""
    protected, tags = protect_tags(text)
    if not protected.strip():
        return text
    try:
        from deep_translator import GoogleTranslator  # type: ignore

        out = GoogleTranslator(source=source, target=target).translate(protected)
        return restore_tags(out or text, tags)
    except Exception as e:
        print(f"[translate] skip: {e}", file=sys.stderr)
        return text


def translate_text(text: str, translator) -> str:
    """1件を翻訳する。タグは保護し、失敗時は例外をそのまま呼び出し側に投げる
    （バッチ処理側で件数を数えて後から報告するため、ここでは握り潰さない）。"""
    protected, tags = protect_tags(text)
    if not protected.strip():
        return text
    out = translator.translate(protected)
    return restore_tags(out or text, tags)


# 選択できる翻訳先言語（表示名, deep_translator/Google 用の言語コード）
TRANSLATE_LANGUAGES: List[Tuple[str, str]] = [
    ("English", "en"),
    ("日本語", "ja"),
    ("中文（簡体字）", "zh-CN"),
    ("中文（繁体字）", "zh-TW"),
    ("한국어", "ko"),
    ("Français", "fr"),
    ("Español", "es"),
    ("Deutsch", "de"),
    ("Português", "pt"),
    ("Русский", "ru"),
    ("Italiano", "it"),
    ("ภาษาไทย", "th"),
    ("Tiếng Việt", "vi"),
    ("Bahasa Indonesia", "id"),
]

# 行キーの見た目から言語コードを推測するための表
_LANG_CODE_GUESS = {
    "ja": "ja", "jp": "ja", "japanese": "ja",
    "en": "en", "eng": "en", "english": "en",
    "zh": "zh-CN", "cn": "zh-CN", "chinese": "zh-CN", "zhcn": "zh-CN",
    "zhtw": "zh-TW", "tw": "zh-TW",
    "ko": "ko", "kr": "ko", "korean": "ko",
    "fr": "fr", "french": "fr",
    "es": "es", "spanish": "es",
    "de": "de", "german": "de",
    "pt": "pt", "portuguese": "pt",
    "ru": "ru", "russian": "ru",
    "it": "it", "italian": "it",
    "th": "th", "thai": "th",
    "vi": "vi", "vietnamese": "vi",
    "id": "id", "indonesian": "id",
}

# 言語コードから新規行キーを提案するための表
_ROW_NAME_SUGGESTION = {
    "en": "En", "ja": "Ja", "zh-CN": "ZhCN", "zh-TW": "ZhTW", "ko": "Ko",
    "fr": "Fr", "es": "Es", "de": "De", "pt": "Pt", "ru": "Ru", "it": "It",
    "th": "Th", "vi": "Vi", "id": "Id",
}


def guess_lang_code(row_key: str) -> Optional[str]:
    key = re.sub(r"[^a-z]", "", normalize_row_key(row_key).lower())
    return _LANG_CODE_GUESS.get(key)


def suggest_row_name(lang_code: str) -> str:
    return _ROW_NAME_SUGGESTION.get(lang_code, lang_code.replace("-", ""))


def _is_rate_limit_error(e: Exception) -> bool:
    """deep_translator の TooManyRequests（Google側 429）かどうかを、
    例外クラスが取れない場合でもメッセージから判定する。"""
    if "TooManyRequests" in type(e).__name__:
        return True
    msg = str(e).lower()
    return "too many requests" in msg or "429" in msg


_TRANSLATOR_CHECKED = False
_TRANSLATOR_OK = False
_TRANSLATOR_IMPORT_ERROR: Optional[str] = None


def ensure_translator_available(force: bool = False) -> bool:
    """deep_translator が import できるかどうかだけを確認する。

    以前は実際に1件翻訳してテストしていたが、無料の Google 翻訳エンドポイントは
    5リクエスト/秒までしか許容しないため、ダイアログを開くたびにテスト通信を
    行うとそれだけでレート制限を消費・悪化させてしまっていた。
    そのためここでは import 可否のみを見る。ネットワーク不通やレート制限は
    実際の翻訳実行時（_start_translation_job）で検出し、レート制限は自動リトライする。
    """
    global _TRANSLATOR_CHECKED, _TRANSLATOR_OK, _TRANSLATOR_IMPORT_ERROR
    if _TRANSLATOR_CHECKED and not force:
        return _TRANSLATOR_OK
    _TRANSLATOR_CHECKED = True
    try:
        from deep_translator import GoogleTranslator  # noqa: F401

        _TRANSLATOR_OK = True
        _TRANSLATOR_IMPORT_ERROR = None
    except Exception as e:
        _TRANSLATOR_OK = False
        _TRANSLATOR_IMPORT_ERROR = f"{type(e).__name__}: {e}"
    return _TRANSLATOR_OK


def load_matrix(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_matrix(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_cell_list(matrix: dict, row_key: str, col_key: str, field_name: str = "texts") -> List[str]:
    data = matrix.get("data") or {}
    cell = (data.get(row_key) or {}).get(col_key) or {}
    raw = cell.get(field_name)
    if raw is None:
        return []
    if isinstance(raw, dict) and "value" in raw:
        val = raw["value"]
        return list(val) if isinstance(val, list) else []
    if isinstance(raw, list):
        return list(raw)
    return []


def set_cell_list(
    matrix: dict,
    row_key: str,
    col_key: str,
    items: List[str],
    field_name: str = "texts"
) -> None:
    data = matrix.setdefault("data", {})
    row = data.setdefault(row_key, {})
    cell = row.setdefault(col_key, {})

    # texts は配列そのものとして保存する
    # 旧形式 {"value": [...], "type": "string"} が残っていても
    # 保存時に新しい正しい形式へ変換する。
    cell[field_name] = list(items)


def list_row_keys(matrix: dict) -> List[str]:
    return sorted((matrix.get("data") or {}).keys())


def list_col_keys(matrix: dict, row_key: Optional[str] = None) -> List[str]:
    data = matrix.get("data") or {}
    if row_key and row_key in data:
        return sorted(data[row_key].keys())
    keys = set()
    for row in data.values():
        if isinstance(row, dict):
            keys.update(row.keys())
    return sorted(keys)


def normalize_row_key(key: str) -> str:
    return key.split(".")[-1] if "." in key else key


def open_in_explorer(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"[open] {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Listbox ドラッグ＆ドロップ（行間に挿入するタイプ）
# ---------------------------------------------------------------------------

class ListboxDragInsert:
    """
    tk.Listbox 上でドラッグして「行と行の間」に挿入する。
    ドラッグ中は挿入位置に区切りラインを表示する。

    on_move(from_index, to_index): 実データ上で from を to へ移動する。
    """

    MARK = "  ──────────────── ここに挿入 ────────────────"
    THRESHOLD = 4  # px

    def __init__(self, listbox: tk.Listbox, on_move, get_count):
        self.lb = listbox
        self.on_move = on_move
        self.get_count = get_count
        self._press_index: Optional[int] = None
        self._press_y: int = 0
        self._dragging = False
        self._marker: Optional[int] = None
        listbox.bind("<Button-1>", self._on_press, add="+")
        listbox.bind("<B1-Motion>", self._on_drag, add="+")
        listbox.bind("<ButtonRelease-1>", self._on_release, add="+")
        listbox.bind("<Escape>", lambda e: self._cancel(), add="+")

    # -- 内部 ---------------------------------------------------------------
    def _gap_at(self, y: int) -> int:
        """y 座標に対応する「挿入位置（gap index）」を返す。0 = 先頭の上。"""
        count = self.get_count()
        if count <= 0:
            return 0
        idx = self.lb.nearest(y)
        idx = max(0, min(idx, count - 1))
        bbox = self.lb.bbox(idx)
        if bbox:
            _, by, _, bh = bbox
            if y > by + bh / 2:
                idx += 1
        return max(0, min(idx, count))

    def _clear_marker(self) -> None:
        if self._marker is not None:
            try:
                self.lb.delete(self._marker)
            except tk.TclError:
                pass
            self._marker = None

    def _show_marker(self, gap: int) -> None:
        self._clear_marker()
        self.lb.insert(gap, self.MARK)
        try:
            self.lb.itemconfig(gap, foreground=C["accent"], background=C["accent_dim"])
        except tk.TclError:
            pass
        self._marker = gap

    def _cancel(self) -> None:
        self._clear_marker()
        self._press_index = None
        self._dragging = False

    # -- イベント -----------------------------------------------------------
    def _on_press(self, event):
        self._clear_marker()
        self._dragging = False
        self._press_y = event.y
        count = self.get_count()
        self._press_index = self.lb.nearest(event.y) if count else None
        if self._press_index is not None and not (0 <= self._press_index < count):
            self._press_index = None

    def _on_drag(self, event):
        if self._press_index is None:
            return
        if not self._dragging:
            if abs(event.y - self._press_y) < self.THRESHOLD:
                return
            self._dragging = True
            self.lb.config(cursor="hand2")
        self._clear_marker()  # gap 計算は marker を消した状態で行う
        gap = self._gap_at(event.y)
        self._show_marker(gap)
        # 端まで来たら自動スクロール
        if event.y < 12:
            self.lb.yview_scroll(-1, "units")
        elif event.y > self.lb.winfo_height() - 12:
            self.lb.yview_scroll(1, "units")

    def _on_release(self, event):
        if self._press_index is None:
            return
        frm = self._press_index
        dragging = self._dragging
        self._press_index = None
        self._dragging = False
        self.lb.config(cursor="")
        self._clear_marker()
        if not dragging:
            return
        gap = self._gap_at(event.y)
        to = gap - 1 if gap > frm else gap
        if to == frm or to < 0:
            return
        self.on_move(frm, to)


def ask_swap_indices(parent, max_index: int, title: str = "インデックス指定で入れ替え") -> Optional[Tuple[int, int]]:
    """0 .. max_index の範囲で A/B を入力させる。キャンセル時は None。"""
    if max_index < 1:
        messagebox.showinfo("情報", "入れ替える要素が足りません（2件以上必要）", parent=parent)
        return None

    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=C["bg"])
    win.transient(parent)
    win.grab_set()
    win.geometry("360x200")

    tk.Label(
        win,
        text=f"入れ替える2つのインデックスを指定（0 〜 {max_index}）",
        bg=C["bg"],
        fg=C["text"],
        font=("Segoe UI", 10),
    ).pack(pady=(16, 8), padx=16)

    row = tk.Frame(win, bg=C["bg"])
    row.pack(pady=8)
    va = tk.StringVar(value="0")
    vb = tk.StringVar(value=str(min(1, max_index)))

    def _entry(parent_, var, label):
        box = tk.Frame(parent_, bg=C["bg"])
        box.pack(side=tk.LEFT, padx=12)
        tk.Label(box, text=label, bg=C["bg"], fg=C["text_muted"]).pack()
        e = tk.Entry(
            box,
            textvariable=var,
            width=8,
            bg=C["input_bg"],
            fg=C["text"],
            insertbackground=C["text"],
            relief=tk.FLAT,
            font=("Consolas", 12),
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
            justify=tk.CENTER,
        )
        e.pack(ipady=4)
        return e

    _entry(row, va, "A")
    tk.Label(row, text="⟷", bg=C["bg"], fg=C["accent"], font=("Segoe UI", 14)).pack(side=tk.LEFT, padx=4)
    _entry(row, vb, "B")

    result: List[Optional[Tuple[int, int]]] = [None]

    def ok():
        try:
            a = int(va.get().strip())
            b = int(vb.get().strip())
        except ValueError:
            messagebox.showerror("エラー", "整数を入力してください", parent=win)
            return
        if not (0 <= a <= max_index and 0 <= b <= max_index):
            messagebox.showerror("エラー", f"0 〜 {max_index} の範囲で指定してください", parent=win)
            return
        if a == b:
            messagebox.showinfo("情報", "同じインデックス同士は入れ替え不要です", parent=win)
            return
        result[0] = (a, b)
        win.destroy()

    btns = tk.Frame(win, bg=C["bg"])
    btns.pack(pady=16)
    ttk.Button(btns, text="入れ替え", command=ok, style="Accent.TButton").pack(side=tk.LEFT, padx=6)
    ttk.Button(btns, text="キャンセル", command=win.destroy, style="Ghost.TButton").pack(side=tk.LEFT, padx=6)

    win.bind("<Return>", lambda e: ok())
    win.bind("<Escape>", lambda e: win.destroy())
    parent.wait_window(win)
    return result[0]


def ask_insert_index(parent, max_index: int, title: str = "位置指定で挿入") -> Optional[int]:
    """0 .. max_index（max_index = 末尾）の挿入位置を入力。キャンセル時 None。"""
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=C["bg"])
    win.transient(parent)
    win.grab_set()
    win.geometry("380x180")

    tk.Label(
        win,
        text=f"挿入するインデックスを指定（0 = 先頭、{max_index} = 末尾）",
        bg=C["bg"],
        fg=C["text"],
        font=("Segoe UI", 10),
    ).pack(pady=(16, 8), padx=16)

    var = tk.StringVar(value=str(max_index))
    e = tk.Entry(
        win,
        textvariable=var,
        width=12,
        bg=C["input_bg"],
        fg=C["text"],
        insertbackground=C["text"],
        relief=tk.FLAT,
        font=("Consolas", 14),
        highlightthickness=1,
        highlightbackground=C["border"],
        highlightcolor=C["accent"],
        justify=tk.CENTER,
    )
    e.pack(ipady=6, pady=8)
    e.select_range(0, tk.END)
    e.focus_set()

    result: List[Optional[int]] = [None]

    def ok():
        try:
            n = int(var.get().strip())
        except ValueError:
            messagebox.showerror("エラー", "整数を入力してください", parent=win)
            return
        if not (0 <= n <= max_index):
            messagebox.showerror("エラー", f"0 〜 {max_index} の範囲で指定してください", parent=win)
            return
        result[0] = n
        win.destroy()

    btns = tk.Frame(win, bg=C["bg"])
    btns.pack(pady=12)
    ttk.Button(btns, text="挿入", command=ok, style="Accent.TButton").pack(side=tk.LEFT, padx=6)
    ttk.Button(btns, text="キャンセル", command=win.destroy, style="Ghost.TButton").pack(side=tk.LEFT, padx=6)
    win.bind("<Return>", lambda ev: ok())
    win.bind("<Escape>", lambda ev: win.destroy())
    parent.wait_window(win)
    return result[0]


# ---------------------------------------------------------------------------
# 翻訳用ダイアログ（進捗バー / 言語・出力先の選択）
# ---------------------------------------------------------------------------

class ProgressDialog(tk.Toplevel):
    """バックグラウンドスレッドで動く処理の進捗（件数・％）を表示するモーダル。
    キャンセルボタンを押すと self.cancelled が True になる（実際の停止は
    呼び出し側が threading.Event 等でスレッドに伝える）。"""

    def __init__(self, parent, title: str, total: int):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=C["bg"])
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.geometry("440x170")
        self.cancelled = False

        self.label = tk.Label(
            self, text="準備中…", bg=C["bg"], fg=C["text"], font=("Segoe UI", 10), wraplength=400, justify=tk.LEFT
        )
        self.label.pack(pady=(20, 10), padx=20, fill=tk.X)

        self.pbar = ttk.Progressbar(self, orient=tk.HORIZONTAL, length=380, mode="determinate", maximum=max(total, 1))
        self.pbar.pack(pady=4)

        self.pct_label = tk.Label(self, text=f"0%  (0/{total})", bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 9))
        self.pct_label.pack(pady=(2, 0))

        self.cancel_btn = ttk.Button(self, text="キャンセル", command=self._on_cancel, style="Ghost.TButton")
        self.cancel_btn.pack(pady=(14, 0))

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def update_progress(self, done: int, total: int, text: str = "") -> None:
        total = max(total, 1)
        pct = int(done / total * 100)
        self.pbar["maximum"] = total
        self.pbar["value"] = done
        self.pct_label.config(text=f"{pct}%  ({done}/{total})")
        if text:
            self.label.config(text=text)

    def _on_cancel(self) -> None:
        self.cancelled = True
        self.cancel_btn.config(state=tk.DISABLED, text="キャンセル中…")
        self.label.config(text="キャンセル中… 現在の処理が終わったら停止します")


class TranslateOptionsDialog(tk.Toplevel):
    """翻訳元の行・翻訳先の言語・出力先の行・追記/置換 を選ぶダイアログ。
    OK で self.result に dict をセットして閉じる（キャンセル時は None）。"""

    def __init__(self, parent, rows: List[str], current_row: str, current_col: str, current_field: str):
        super().__init__(parent)
        self.title("翻訳")
        self.configure(bg=C["bg"])
        self.transient(parent)
        self.grab_set()
        self.geometry("480x460")
        self.resizable(False, False)
        self.result: Optional[dict] = None
        self._rows = rows

        pad = dict(padx=18, pady=(12, 0))

        tk.Label(
            self,
            text=f"対象: 列「{current_col}」 / フィールド「{current_field}」",
            bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 9),
        ).pack(anchor=tk.W, **pad)

        tk.Label(self, text="元の行（翻訳元）", bg=C["bg"], fg=C["text"], font=("Segoe UI", 10)).pack(anchor=tk.W, **pad)
        self.src_var = tk.StringVar(value=current_row)
        src_combo = ttk.Combobox(self, textvariable=self.src_var, values=rows, state="readonly", width=32)
        src_combo.pack(anchor=tk.W, padx=18, pady=(2, 0))
        src_combo.bind("<<ComboboxSelected>>", lambda e: self._on_src_changed())

        tk.Label(
            self, text="元の言語コード（自動判定・変更可 / 'auto' で自動検出）",
            bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 8),
        ).pack(anchor=tk.W, **pad)
        self.src_lang_var = tk.StringVar(value=guess_lang_code(current_row) or "ja")
        tk.Entry(
            self, textvariable=self.src_lang_var, width=14,
            bg=C["input_bg"], fg=C["text"], insertbackground=C["text"], relief=tk.FLAT,
            highlightthickness=1, highlightbackground=C["border"], highlightcolor=C["accent"],
            font=("Consolas", 10),
        ).pack(anchor=tk.W, padx=18, pady=(2, 0))

        tk.Label(self, text="翻訳先の言語", bg=C["bg"], fg=C["text"], font=("Segoe UI", 10)).pack(anchor=tk.W, **pad)
        self.lang_var = tk.StringVar(value=TRANSLATE_LANGUAGES[0][0])
        lang_combo = ttk.Combobox(
            self, textvariable=self.lang_var, values=[lbl for lbl, _ in TRANSLATE_LANGUAGES],
            state="readonly", width=32,
        )
        lang_combo.pack(anchor=tk.W, padx=18, pady=(2, 0))
        lang_combo.bind("<<ComboboxSelected>>", lambda e: self._on_lang_changed())

        tk.Label(self, text="出力先の行（既存を選ぶ / 新しい名前を直接入力）", bg=C["bg"], fg=C["text"], font=("Segoe UI", 10)).pack(
            anchor=tk.W, **pad
        )
        self.dst_var = tk.StringVar()
        self.dst_combo = ttk.Combobox(self, textvariable=self.dst_var, values=rows, width=32)
        self.dst_combo.pack(anchor=tk.W, padx=18, pady=(2, 0))

        mode_frame = tk.Frame(self, bg=C["bg"])
        mode_frame.pack(anchor=tk.W, padx=18, pady=(14, 0))
        self.mode_var = tk.StringVar(value="append")
        ttk.Radiobutton(mode_frame, text="末尾に追記", value="append", variable=self.mode_var).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="全体を置換", value="replace", variable=self.mode_var).pack(side=tk.LEFT, padx=(16, 0))

        tk.Label(
            self, text="※ Text Animator タグ（<...> / {...}）は翻訳対象から保護されます",
            bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 8),
        ).pack(anchor=tk.W, padx=18, pady=(10, 0))

        btn_row = tk.Frame(self, bg=C["bg"])
        btn_row.pack(pady=18)
        ttk.Button(btn_row, text="翻訳開始", command=self._ok, style="Accent.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="キャンセル", command=self.destroy, style="Ghost.TButton").pack(side=tk.LEFT, padx=6)

        self._on_lang_changed()
        self.bind("<Escape>", lambda e: self.destroy())

    def _selected_lang_code(self) -> str:
        label = self.lang_var.get()
        for lbl, code in TRANSLATE_LANGUAGES:
            if lbl == label:
                return code
        return "en"

    def _on_src_changed(self) -> None:
        code = guess_lang_code(self.src_var.get())
        if code:
            self.src_lang_var.set(code)

    def _on_lang_changed(self) -> None:
        code = self._selected_lang_code()
        existing = next((r for r in self._rows if guess_lang_code(r) == code and r != self.src_var.get()), None)
        self.dst_var.set(existing or suggest_row_name(code))

    def _ok(self) -> None:
        src_row = self.src_var.get().strip()
        dst_row = self.dst_var.get().strip()
        if not src_row:
            messagebox.showerror("エラー", "元の行を選択してください", parent=self)
            return
        if not dst_row:
            messagebox.showerror("エラー", "出力先の行を入力してください", parent=self)
            return
        if dst_row == src_row:
            messagebox.showerror("エラー", "出力先の行は元の行と別にしてください", parent=self)
            return
        self.result = {
            "src_row": src_row,
            "src_lang": self.src_lang_var.get().strip() or "auto",
            "dst_row": dst_row,
            "dst_lang": self._selected_lang_code(),
            "mode": self.mode_var.get(),
        }
        self.destroy()


# ---------------------------------------------------------------------------
# メインウィンドウ
# ---------------------------------------------------------------------------


# ============================================================================
# シナリオイベント／ロール／トランザクションDSL データストア
#
# 元になった React/Node 実装(ScenarioEventGrid.js, RoleInputFactory.js,
# BaseRoleInputForm.js, scenarioTransactionDsl.js)はバックエンドAPI
# (/api/scenario-event, /api/role-form-schema/:name 等)経由でデータを
# 読み書きしていたが、この Python ツールにはそのAPIサーバーが無いため、
# 同じ考え方(Event > SubEvent、RoleごとのフィールドSchema、Role呼び出しを
# 1行1コマンドで書くDSL)を、SCENARIO_DIR 配下のJSONファイルへの直接読み書き
# として実装しなおしたもの。ファイル形式:
#
#   scenario_events.json : { "events": [ { "id", "name", "description",
#                              "subEvents": [ { "subId", "name", "description" } ] } ] }
#   scenario_roles.json  : { "roles": [ { "name", "description", "branchType" } ] }
#   role_schemas/<RoleName>.json : { "fields": [ FieldDef, ... ] }
#   class_data/<TypeName>.json   :
#       ID参照型(class_data_id/enum相当):  { "kind": "id_list", "members": ["Foo_01", ...] }
#       ネスト構造体(class_data相当):      { "kind": "struct", "subFields": [FieldDef, ...] }
#   transactions/<eventId>_<subId>.txt : DSLテキスト本体(1行1コマンド)
#
#   FieldDef = { "name": str,
#                "type": str,   # 末尾 "[]" で配列。ビルトイン型は
#                                # scenarioTransactionDsl.js と同じ小文字名
#                                # (int/uint/short/long/byte/float/double/decimal/
#                                #  char/bool/string/vector2/vector3/vector4/
#                                #  bit/color/bezier/dictionary/text_list_index/
#                                #  voice_ref)。それ以外の型名は class_data/ 配下の
#                                # 同名ファイルを参照する(id_list or struct)。
#                "options": {...} }  # bit の size 等
# ============================================================================

BUILTIN_TYPES_NUMERIC = {"int", "uint", "short", "long", "byte"}
BUILTIN_TYPES_FLOAT = {"float", "double", "decimal"}
BUILTIN_VECTOR_FIELDS = {"vector2": ["x", "y"], "vector3": ["x", "y", "z"], "vector4": ["x", "y", "z", "w"]}
BUILTIN_STRUCT_SUBFIELDS = {
    "bit": [{"name": "size", "type": "int"}, {"name": "bits", "type": "int[]"}],
    "color": [{"name": "r", "type": "float"}, {"name": "g", "type": "float"},
              {"name": "b", "type": "float"}, {"name": "a", "type": "float"}],
    "bezier": [{"name": "points", "type": "bezierpoint[]", "subFields": [
        {"name": "time", "type": "float"}, {"name": "value", "type": "float"},
        {"name": "inTangent", "type": "float"}, {"name": "outTangent", "type": "float"},
    ]}],
}
BUILTIN_SCALAR_TYPES = (
    BUILTIN_TYPES_NUMERIC | BUILTIN_TYPES_FLOAT
    | {"char", "bool", "string", "text_list_index", "voice_ref"}
)


def base_type_of(field_type: str) -> str:
    t = (field_type or "").strip()
    if t.endswith("[]"):
        t = t[:-2]
    return t


def is_array_type(field_type: str) -> bool:
    return (field_type or "").strip().endswith("[]")


# --- トークナイザ (scenarioTransactionDsl.js の tokenizeLine を移植) -------
_TOKEN_RE = re.compile(r'#.*$|"(?:[^"\\]|\\.)*"|[(){}\[\],=:]|-?\d+(?:\.\d+)?|[^\s(){}\[\],="#:]+')


def tokenize_line(line: str) -> List[dict]:
    tokens = []
    for m in _TOKEN_RE.finditer(line):
        raw = m.group(0)
        frm, to = m.start(), m.end()
        if raw.startswith('#'):
            typ = 'COMMENT'
        elif raw.startswith('"'):
            typ = 'STRING'
        elif raw == '(':
            typ = 'LPAREN'
        elif raw == ')':
            typ = 'RPAREN'
        elif raw == '[':
            typ = 'LBRACKET'
        elif raw == ']':
            typ = 'RBRACKET'
        elif raw == '{':
            typ = 'LBRACE'
        elif raw == '}':
            typ = 'RBRACE'
        elif raw == ':':
            typ = 'COLON'
        elif raw == ',':
            typ = 'COMMA'
        elif raw == '=':
            typ = 'EQUALS'
        elif re.match(r'^-?\d', raw):
            typ = 'NUMBER'
        else:
            typ = 'IDENT'
        tokens.append({"type": typ, "value": raw, "from": frm, "to": to})
    return tokens


class DslIssue:
    def __init__(self, message, frm, to, line, severity="error"):
        self.message = message
        self.frm = frm
        self.to = to
        self.line = line
        self.severity = severity


def _collect_value_tokens(tokens: List[dict], start: int):
    if start >= len(tokens):
        return [], start, "値が指定されていません"
    t = tokens[start]
    open_close = {"LPAREN": "RPAREN", "LBRACKET": "RBRACKET", "LBRACE": "RBRACE"}
    if t["type"] in open_close:
        close_type = open_close[t["type"]]
        depth = 1
        j = start + 1
        collected = [t]
        while j < len(tokens) and depth > 0:
            if tokens[j]["type"] == t["type"]:
                depth += 1
            if tokens[j]["type"] == close_type:
                depth -= 1
            collected.append(tokens[j])
            j += 1
        if depth != 0:
            return collected, j, "括弧が閉じられていません"
        return collected, j, None
    if t["type"] in ("STRING", "NUMBER", "IDENT"):
        return [t], start + 1, None
    return [t], start + 1, f"予期しないトークンです: {t['value']}"


def parse_line(raw_line: str, line_number: int) -> dict:
    """1行をパースして {'type': 'blank'|'comment'|'call', 'name', 'args', 'errors'} を返す。
    args = [{'key': str, 'valueTokens': [...], 'from':int, 'to':int}]"""
    tokens = tokenize_line(raw_line)
    errors: List[DslIssue] = []
    if not tokens:
        return {"type": "blank", "line": line_number, "raw": raw_line, "name": None, "args": [], "errors": errors}
    if tokens[0]["type"] == "COMMENT":
        return {"type": "comment", "line": line_number, "raw": raw_line, "name": None, "args": [], "errors": errors}

    if tokens[-1]["type"] == "COMMENT":
        tokens = tokens[:-1]

    name_token = tokens[0]
    if name_token["type"] != "IDENT":
        errors.append(DslIssue("Role名を指定してください", name_token["from"], name_token["to"], line_number))
        return {"type": "call", "line": line_number, "raw": raw_line, "name": None, "args": [], "errors": errors}

    args = []
    i = 1
    while i < len(tokens):
        key_token = tokens[i]
        if key_token["type"] != "IDENT":
            errors.append(DslIssue("引数名を指定してください（fieldName=value 形式）", key_token["from"], key_token["to"], line_number))
            i += 1
            continue
        eq_token = tokens[i + 1] if i + 1 < len(tokens) else None
        if not eq_token or eq_token["type"] != "EQUALS":
            errors.append(DslIssue(f"'=' が必要です: {key_token['value']}=...", key_token["from"], key_token["to"], line_number))
            i += 1
            continue
        value_tokens, next_index, err = _collect_value_tokens(tokens, i + 2)
        if err:
            errors.append(DslIssue(err, key_token["from"], eq_token["to"], line_number))
        args.append({"key": key_token["value"], "keyToken": key_token, "valueTokens": value_tokens,
                     "from": key_token["from"],
                     "to": (value_tokens[-1]["to"] if value_tokens else eq_token["to"])})
        i = next_index

    return {"type": "call", "line": line_number, "raw": raw_line, "name": name_token["value"], "args": args, "errors": errors}


def parse_document(text: str) -> List[dict]:
    return [parse_line(line, idx) for idx, line in enumerate(text.split("\n"))]


class ScenarioDataStore:
    """scenario_events.json / scenario_roles.json / role_schemas / class_data /
    transactions を読み書きする薄いラッパー。書き込みは原子的(tmp→replace)。"""

    def __init__(self):
        self.events_path = SCENARIO_EVENTS_PATH
        self.roles_path = SCENARIO_ROLES_PATH

    # -- events --------------------------------------------------------
    def load_events(self) -> List[dict]:
        data = _read_json(self.events_path, {"events": []})
        events = data.get("events") if isinstance(data, dict) else None
        if not isinstance(events, list):
            events = []
        for ev in events:
            ev.setdefault("subEvents", [])
            ev.setdefault("description", "")
        return events

    def save_events(self, events: List[dict]) -> None:
        _write_json(self.events_path, {"events": events})

    def next_event_id(self, events: List[dict]) -> str:
        ids = [int(e["id"]) for e in events if str(e.get("id", "")).isdigit()]
        return str(max(ids) + 1) if ids else "1"

    def next_sub_id(self, event: dict) -> str:
        ids = [int(s["subId"]) for s in event.get("subEvents", []) if str(s.get("subId", "")).isdigit()]
        return str(max(ids) + 1) if ids else "1"

    # -- roles -----------------------------------------------------------
    def load_roles(self) -> List[dict]:
        data = _read_json(self.roles_path, {"roles": []})
        roles = data.get("roles") if isinstance(data, dict) else None
        if not isinstance(roles, list):
            roles = []
        return roles

    def save_roles(self, roles: List[dict]) -> None:
        _write_json(self.roles_path, {"roles": roles})

    def role_names(self) -> List[str]:
        return sorted(r["name"] for r in self.load_roles() if r.get("name"))

    # -- role schema (フィールド定義) -------------------------------------
    def _role_schema_path(self, role_name: str) -> str:
        safe = re.sub(r'[^A-Za-z0-9_\-]', '_', role_name)
        return os.path.join(SCENARIO_ROLE_SCHEMA_DIR, f"{safe}.json")

    def load_role_schema(self, role_name: str) -> dict:
        return _read_json(self._role_schema_path(role_name), {"fields": []})

    def save_role_schema(self, role_name: str, schema: dict) -> None:
        _write_json(self._role_schema_path(role_name), schema)

    def all_role_schemas(self) -> Dict[str, dict]:
        return {name: self.load_role_schema(name) for name in self.role_names()}

    # -- class data (enum/ID参照 or ネスト構造体) --------------------------
    def _class_data_path(self, type_name: str) -> str:
        safe = re.sub(r'[^A-Za-z0-9_\-]', '_', type_name)
        return os.path.join(SCENARIO_CLASS_DATA_DIR, f"{safe}.json")

    def list_class_data_types(self) -> List[str]:
        try:
            names = [os.path.splitext(f)[0] for f in os.listdir(SCENARIO_CLASS_DATA_DIR) if f.endswith(".json")]
            return sorted(names)
        except FileNotFoundError:
            return []

    def load_class_data(self, type_name: str) -> Optional[dict]:
        path = self._class_data_path(type_name)
        if not os.path.isfile(path):
            return None
        return _read_json(path, None)

    def save_class_data(self, type_name: str, data: dict) -> None:
        _write_json(self._class_data_path(type_name), data)

    # -- transactions (DSL本文) -------------------------------------------
    def _transaction_path(self, event_id: str, sub_id: str) -> str:
        safe = re.sub(r'[^A-Za-z0-9_\-]', '_', f"{event_id}_{sub_id}")
        return os.path.join(SCENARIO_TRANSACTION_DIR, f"{safe}.txt")

    def load_transaction_text(self, event_id: str, sub_id: str) -> str:
        path = self._transaction_path(event_id, sub_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def save_transaction_text(self, event_id: str, sub_id: str, text: str) -> None:
        path = self._transaction_path(event_id, sub_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)

    # -- 型解決 ------------------------------------------------------------
    def resolve_subfields(self, field_type: str, field_def: dict) -> Optional[List[dict]]:
        """ネスト型(class_data相当)のサブフィールド一覧を返す。ビルトイン
        構造体(bit/color/bezier/vectorN)はここで固定値を補い、それ以外は
        class_data/<type>.json (kind=struct)を参照する。"""
        explicit = field_def.get("subFields")
        if explicit:
            return explicit
        base = base_type_of(field_type).lower()
        if base in BUILTIN_STRUCT_SUBFIELDS:
            return BUILTIN_STRUCT_SUBFIELDS[base]
        if base in BUILTIN_VECTOR_FIELDS:
            return [{"name": n, "type": "float"} for n in BUILTIN_VECTOR_FIELDS[base]]
        cd = self.load_class_data(base_type_of(field_type))
        if cd and cd.get("kind") == "struct":
            return cd.get("subFields", [])
        return None

    def resolve_id_members(self, field_type: str) -> Optional[List[str]]:
        """class_data_id / enum 相当(ID参照型)のメンバー一覧を返す(無ければNone)。"""
        cd = self.load_class_data(base_type_of(field_type))
        if cd and cd.get("kind") == "id_list":
            return cd.get("members", [])
        return None

    def default_value_for(self, field_type: str, field_def: Optional[dict] = None) -> object:
        field_def = field_def or {}
        if is_array_type(field_type):
            return []
        base = base_type_of(field_type).lower()
        if base in BUILTIN_TYPES_NUMERIC:
            return 0
        if base in BUILTIN_TYPES_FLOAT:
            return 0.0
        if base == "char":
            return ""
        if base == "bool":
            return False
        if base == "string":
            return ""
        if base in BUILTIN_VECTOR_FIELDS:
            return {n: 0 for n in BUILTIN_VECTOR_FIELDS[base]}
        if base == "bit":
            size = (field_def.get("options") or {}).get("size", 8)
            return {"size": size, "bits": []}
        if base == "color":
            return {"r": 1, "g": 1, "b": 1, "a": 1}
        if base == "bezier":
            return {"points": [{"time": 0, "value": 0, "inTangent": 0, "outTangent": 0},
                                {"time": 1, "value": 1, "inTangent": 0, "outTangent": 0}]}
        if base == "dictionary":
            return {"entries": []}
        if base == "text_list_index":
            return -1
        if base == "voice_ref":
            return ""
        # class_data_id (id_list) or class_data(struct) or unknown → 空文字/空オブジェクト
        subfields = self.resolve_subfields(field_type, field_def)
        if subfields is not None:
            return {f["name"]: self.default_value_for(f["type"], f) for f in subfields}
        return ""


# --- 値 ⇔ DSLソーステキスト の変換 -----------------------------------------

def format_scalar_for_dsl(value, field_type: str) -> str:
    base = base_type_of(field_type).lower()
    if base == "string":
        s = str(value if value is not None else "")
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if base == "bool":
        return "true" if value else "false"
    if base in BUILTIN_TYPES_FLOAT | BUILTIN_TYPES_NUMERIC | {"text_list_index"}:
        return str(value)
    # char / voice_ref / enum / class_data_id / bareword 系はそのまま裸で出す
    return str(value if value is not None else "")


def format_value_for_dsl(store: "ScenarioDataStore", value, field_type: str, field_def: Optional[dict] = None, depth: int = 0) -> str:
    field_def = field_def or {}
    if is_array_type(field_type):
        base = base_type_of(field_type)
        items = value if isinstance(value, list) else []
        inner = ", ".join(format_value_for_dsl(store, it, base, field_def, depth + 1) for it in items)
        return f"[{inner}]"
    subfields = store.resolve_subfields(field_type, field_def)
    if subfields is not None:
        value = value if isinstance(value, dict) else {}
        parts = []
        for sf in subfields:
            v = value.get(sf["name"], store.default_value_for(sf["type"], sf))
            parts.append(f"{sf['name']}: {format_value_for_dsl(store, v, sf['type'], sf, depth + 1)}")
        return "{ " + ", ".join(parts) + " }"
    return format_scalar_for_dsl(value, field_type)


def build_role_call_line(store: "ScenarioDataStore", role_name: str, schema: dict) -> str:
    """スキーマのデフォルト値付きで `RoleName field1=... field2=...` 行を組み立てる
    (ScenarioTransactionCodeEditor.js の「Role名を選ぶと既定値ごと挿入される」補完と同じ役割)。"""
    parts = [role_name]
    for f in schema.get("fields", []):
        default = f.get("default", store.default_value_for(f["type"], f))
        parts.append(f"{f['name']}={format_value_for_dsl(store, default, f['type'], f)}")
    return " ".join(parts)


# --- カーソル位置に応じた補完候補 (getCompletionsAt の簡易移植) ------------
# 完全な入れ子オブジェクトリテラル内補完までは行わず、実用上重要な
# 「行頭=Role名」「Role名の後ろ=未使用フィールド名」「field=の後ろ=型に応じた値」
# の3段カスケードを提供する(bool/enum/class_data_idはここで確定候補を出し、
# それ以外の型はダイアログでの入力に誘導する)。
def get_completions_at(store: "ScenarioDataStore", line_text: str, cursor_ch: int, role_names: List[str]) -> List[dict]:
    tokens = tokenize_line(line_text[:cursor_ch])
    if not tokens:
        return [{"label": n, "type": "role", "insertText": n} for n in role_names]

    first = tokens[0]
    # カーソルがまだ1トークン目(Role名)を打っている途中
    if len(tokens) == 1 and first["type"] == "IDENT" and cursor_ch <= first["to"]:
        prefix = first["value"]
        return [{"label": n, "type": "role", "insertText": n}
                for n in role_names if n.lower().startswith(prefix.lower())]

    role_name = first["value"] if first["type"] == "IDENT" else None
    if not role_name or role_name not in role_names:
        return []
    schema = store.load_role_schema(role_name)
    used_fields = set()
    for t in tokens[1:]:
        pass
    # 既に使われているフィールド名を、tokensをキー/イコールのペアで見て集計
    i = 1
    while i < len(tokens) - 1:
        if tokens[i]["type"] == "IDENT" and tokens[i + 1]["type"] == "EQUALS":
            used_fields.add(tokens[i]["value"])
            i += 2
        else:
            i += 1

    last = tokens[-1]
    prev = tokens[-2] if len(tokens) >= 2 else None

    def _value_candidates(field_name: Optional[str], typed_prefix: str) -> List[dict]:
        field_def = next((f for f in schema.get("fields", []) if f["name"] == field_name), None)
        if not field_def:
            return []
        base = base_type_of(field_def["type"]).lower()
        if base == "bool":
            return [{"label": v, "type": "value", "insertText": v} for v in ("true", "false")
                    if v.startswith(typed_prefix)]
        members = store.resolve_id_members(field_def["type"])
        if members:
            type_name = base_type_of(field_def["type"])
            prefix = typed_prefix.lower()
            out = []
            for mem in members:
                display = f"{type_name}.{mem}"
                if display.lower().startswith(prefix) or mem.lower().startswith(prefix):
                    out.append({"label": display, "type": "value", "insertText": display})
            return out
        return []

    # 直前が '=' (値をまだ何も打っていない) → 値の候補(bool/enum/class_data_id)
    if last["type"] == "EQUALS":
        field_name = tokens[-2]["value"] if len(tokens) >= 2 else None
        return _value_candidates(field_name, "")
    if last["type"] == "IDENT" and prev and prev["type"] == "EQUALS":
        field_name = tokens[-3]["value"] if len(tokens) >= 3 else None
        return _value_candidates(field_name, last["value"])

    # 直前がRole名 or フィールド値の続き → 未使用フィールド名の候補
    if last["type"] == "IDENT" and (prev is None or prev["type"] != "EQUALS"):
        prefix = last["value"] if cursor_ch <= last["to"] else ""
        candidates = [f for f in schema.get("fields", []) if f["name"] not in used_fields]
        return [{"label": f["name"] + "=", "type": "field", "insertText": f["name"] + "=",
                 "detail": f["type"]}
                for f in candidates if f["name"].lower().startswith(prefix.lower())]

    # スペースの直後など、次に来るべきものがフィールド名
    candidates = [f for f in schema.get("fields", []) if f["name"] not in used_fields]
    return [{"label": f["name"] + "=", "type": "field", "insertText": f["name"] + "=", "detail": f["type"]}
            for f in candidates]


def _split_top_level(tokens: List[dict], sep_type: str = "COMMA") -> List[List[dict]]:
    """トークン列を、深さ0の COMMA で分割する(括弧の中のCOMMAでは分割しない)。"""
    groups: List[List[dict]] = []
    cur: List[dict] = []
    depth = 0
    openers = {"LPAREN", "LBRACKET", "LBRACE"}
    closers = {"RPAREN", "RBRACKET", "RBRACE"}
    for t in tokens:
        if t["type"] in openers:
            depth += 1
        elif t["type"] in closers:
            depth -= 1
        if depth == 0 and t["type"] == sep_type:
            groups.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        groups.append(cur)
    return [g for g in groups if g]


def coerce_value_tokens(store: "ScenarioDataStore", tokens: List[dict], field_type: str, field_def: Optional[dict] = None):
    """DSLのトークン列を、フィールド型に従って実際のPython値へ変換する
    (scenarioTransactionDsl.js の coerceValueTokens の簡易移植。
    未知の形は極力ベストエフォートで読み、失敗時は None を返す)。"""
    field_def = field_def or {}
    if not tokens:
        return store.default_value_for(field_type, field_def)

    if is_array_type(field_type):
        base = base_type_of(field_type)
        if tokens[0]["type"] != "LBRACKET":
            return []
        inner = tokens[1:-1] if tokens[-1]["type"] == "RBRACKET" else tokens[1:]
        return [coerce_value_tokens(store, g, base, field_def) for g in _split_top_level(inner, "COMMA")]

    subfields = store.resolve_subfields(field_type, field_def)
    if subfields is not None:
        if tokens[0]["type"] != "LBRACE":
            return {f["name"]: store.default_value_for(f["type"], f) for f in subfields}
        inner = tokens[1:-1] if tokens[-1]["type"] == "RBRACE" else tokens[1:]
        result = {f["name"]: store.default_value_for(f["type"], f) for f in subfields}
        for grp in _split_top_level(inner, "COMMA"):
            colon_idx = next((i for i, t in enumerate(grp) if t["type"] == "COLON"), None)
            if colon_idx is None:
                continue
            key = grp[0]["value"]
            value_tokens = grp[colon_idx + 1:]
            sub_def = next((f for f in subfields if f["name"] == key), None)
            if sub_def:
                result[key] = coerce_value_tokens(store, value_tokens, sub_def["type"], sub_def)
        return result

    # スカラー
    tok = tokens[0]
    base = base_type_of(field_type).lower()
    if base == "string":
        if tok["type"] == "STRING":
            return tok["value"][1:-1].replace('\\"', '"').replace('\\\\', '\\')
        return tok["value"]
    if base == "bool":
        return tok["value"] == "true"
    if base in BUILTIN_TYPES_NUMERIC or base == "text_list_index":
        try:
            return int(float(tok["value"]))
        except ValueError:
            return 0
    if base in BUILTIN_TYPES_FLOAT:
        try:
            return float(tok["value"])
        except ValueError:
            return 0.0
    # enum / class_data_id は "TypeName.member" の完全修飾形式で保存する規約
    # (scenarioTransactionDsl.js コメント参照)。短縮形("In"等)で入力された
    # 場合はここで正規化する。
    v = tok["value"]
    if tok["type"] == "STRING":
        v = v[1:-1]
    if "." not in v:
        type_name = base_type_of(field_type)
        members = store.resolve_id_members(field_type) or []
        if v in members:
            v = f"{type_name}.{v}"
    return v


def parse_call_line_values(store: "ScenarioDataStore", line_text: str, schema: dict) -> Tuple[Optional[str], Dict[str, object]]:
    """`RoleName field1=val1 field2=val2` 形式の1行を、role名と
    { フィールド名: Python値 } の辞書にパースする(フォーム編集用)。"""
    parsed = parse_line(line_text, 0)
    if parsed["type"] != "call" or not parsed["name"]:
        return None, {}
    values: Dict[str, object] = {}
    fields_by_name = {f["name"]: f for f in schema.get("fields", [])}
    for arg in parsed["args"]:
        f = fields_by_name.get(arg["key"])
        if not f:
            continue
        values[arg["key"]] = coerce_value_tokens(store, arg["valueTokens"], f["type"], f)
    return parsed["name"], values


def build_role_call_line_from_values(store: "ScenarioDataStore", role_name: str, schema: dict, values: Dict[str, object]) -> str:
    parts = [role_name]
    for f in schema.get("fields", []):
        v = values.get(f["name"], store.default_value_for(f["type"], f))
        parts.append(f"{f['name']}={format_value_for_dsl(store, v, f['type'], f)}")
    return " ".join(parts)


class FieldValueEditor(tk.Frame):
    """1つのフィールド値を、型に応じたウィジェットで編集させる再帰コンポーネント。
    BaseRoleInputForm.js の「fieldType→適切な入力UIを出し分ける」を Tkinter で
    再現したもの:
      - bool                → Checkbutton
      - int/uint/short/long/byte/float/double/decimal → 数値Entry(バリデーション付き)
      - string/char/voice_ref → 文字列Entry
      - text_list_index      → 数値Entry + 「テキスト行列から選択…」ボタン
                                (= このツール自身が扱っているMatrixの行を直接選べる)
      - enum / class_data_id (class_data/<Type>.json kind=id_list) → 読み取り専用Combobox
      - vector2/3/4 / bit / color / bezier / class_data(struct)    → ネストしたサブフィールドを
                                再帰的に同じFieldValueEditorで描画(何段ネストしていても同じ)
      - 配列 (型名の末尾が "[]")  → Listbox + 追加/編集/削除(要素は同じ型のFieldValueEditorで編集)
    """

    def __init__(self, parent, app: "ScenarioMatrixEditor", field_def: dict, initial_value=None, depth: int = 0):
        super().__init__(parent, bg=C["surface2"] if depth % 2 else C["surface"])
        self.app = app
        self.store: ScenarioDataStore = app.store
        self.field_def = field_def
        self.ftype = field_def.get("type", "string")
        self.depth = depth
        self._kind = None
        self._widgets = {}
        self._array_values: List[object] = []
        self._array_listbox: Optional[tk.Listbox] = None
        self._sub_editors: Dict[str, "FieldValueEditor"] = {}

        if initial_value is None:
            initial_value = self.store.default_value_for(self.ftype, self.field_def)

        if is_array_type(self.ftype):
            self._build_array(initial_value)
        else:
            subfields = self.store.resolve_subfields(self.ftype, self.field_def)
            members = None if subfields is not None else self.store.resolve_id_members(self.ftype)
            if subfields is not None:
                self._build_struct(subfields, initial_value)
            elif members is not None:
                self._build_enum(members, initial_value)
            else:
                self._build_scalar(initial_value)

    # -- 配列 ------------------------------------------------------------
    def _build_array(self, initial_value):
        self._kind = "array"
        base_type = base_type_of(self.ftype)
        self._array_base_field = dict(self.field_def, type=base_type)
        self._array_values = list(initial_value) if isinstance(initial_value, list) else []

        tk.Label(self, text=f"{self.field_def['name']}（配列: {base_type}）", bg=self["bg"],
                 fg=C["text_muted"], font=("Segoe UI", 9)).pack(anchor=tk.W, padx=4, pady=(4, 0))
        row = tk.Frame(self, bg=self["bg"])
        row.pack(fill=tk.X, padx=4, pady=(2, 4))
        self._array_listbox = tk.Listbox(row, height=4, bg=C["input_bg"], fg=C["text"],
                                          selectbackground=C["list_sel"], exportselection=False)
        self._array_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        btns = tk.Frame(row, bg=self["bg"])
        btns.pack(side=tk.LEFT, padx=4)
        self.app._btn(btns, "＋追加", self._array_add).pack(fill=tk.X)
        self.app._btn(btns, "編集", self._array_edit).pack(fill=tk.X, pady=2)
        self.app._btn(btns, "削除", self._array_remove, danger=True).pack(fill=tk.X)
        self._array_refresh()

    def _array_refresh(self):
        self._array_listbox.delete(0, tk.END)
        for v in self._array_values:
            self._array_listbox.insert(tk.END, self._short_repr(v))

    def _short_repr(self, v) -> str:
        try:
            s = format_value_for_dsl(self.store, v, self._array_base_field["type"], self._array_base_field)
        except Exception:
            s = str(v)
        return s if len(s) <= 80 else s[:77] + "..."

    def _array_add(self):
        v = open_single_value_dialog(self, self.app, self._array_base_field,
                                      self.store.default_value_for(self._array_base_field["type"], self._array_base_field))
        if v is not None:
            self._array_values.append(v)
            self._array_refresh()

    def _array_edit(self):
        sel = self._array_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        v = open_single_value_dialog(self, self.app, self._array_base_field, self._array_values[idx])
        if v is not None:
            self._array_values[idx] = v
            self._array_refresh()

    def _array_remove(self):
        sel = self._array_listbox.curselection()
        if not sel:
            return
        del self._array_values[sel[0]]
        self._array_refresh()

    # -- ネスト構造体(class_data/vectorN/bit/color/bezier) ------------------
    def _build_struct(self, subfields: List[dict], initial_value):
        self._kind = "struct"
        initial_value = initial_value if isinstance(initial_value, dict) else {}
        box = tk.LabelFrame(self, text=f"{self.field_def['name']}（{base_type_of(self.ftype)}）",
                             bg=self["bg"], fg=C["text_muted"], font=("Segoe UI", 9))
        box.pack(fill=tk.X, padx=4, pady=4)
        base_lower = base_type_of(self.ftype).lower()
        if base_lower == "bit":
            self._build_bit_editor(box, subfields, initial_value)
            return
        if base_lower == "color":
            self._build_color_editor(box, initial_value)
            return
        for sf in subfields:
            sub_val = initial_value.get(sf["name"])
            editor = FieldValueEditor(box, self.app, sf, sub_val, depth=self.depth + 1)
            editor.pack(fill=tk.X, padx=2, pady=1)
            self._sub_editors[sf["name"]] = editor

    def _build_bit_editor(self, box, subfields, initial_value):
        # bit = { size:int, bits:int[] } を「サイズ分のチェックボックス」で編集
        size = int(initial_value.get("size", (self.field_def.get("options") or {}).get("size", 8)) or 8)
        bits = set(initial_value.get("bits", []) or [])
        self._bit_size_var = tk.IntVar(value=size)
        top = tk.Frame(box, bg=box["bg"])
        top.pack(fill=tk.X, padx=4, pady=2)
        tk.Label(top, text="サイズ:", bg=box["bg"], fg=C["text"]).pack(side=tk.LEFT)
        size_spin = tk.Spinbox(top, from_=1, to=64, width=4, textvariable=self._bit_size_var,
                                command=lambda: self._bit_rebuild(check_frame))
        size_spin.pack(side=tk.LEFT, padx=4)
        check_frame = tk.Frame(box, bg=box["bg"])
        check_frame.pack(fill=tk.X, padx=4, pady=2)
        self._bit_vars: Dict[int, tk.BooleanVar] = {}

        def rebuild():
            for w in check_frame.winfo_children():
                w.destroy()
            self._bit_vars = {}
            n = max(1, min(64, int(self._bit_size_var.get() or 1)))
            for i in range(n):
                var = tk.BooleanVar(value=(i in bits))
                self._bit_vars[i] = var
                cb = tk.Checkbutton(check_frame, text=str(i), variable=var, bg=box["bg"], fg=C["text"],
                                     selectcolor=C["input_bg"], activebackground=box["bg"])
                cb.grid(row=i // 8, column=i % 8, sticky=tk.W)

        self._bit_rebuild = lambda _f: rebuild()
        rebuild()
        self._kind = "bit_custom"

    def _build_color_editor(self, box, initial_value):
        vals = {k: float(initial_value.get(k, 1.0)) for k in ("r", "g", "b", "a")}
        row = tk.Frame(box, bg=box["bg"])
        row.pack(fill=tk.X, padx=4, pady=2)
        self._color_vars = {}
        for k in ("r", "g", "b", "a"):
            tk.Label(row, text=k + ":", bg=box["bg"], fg=C["text"]).pack(side=tk.LEFT)
            var = tk.DoubleVar(value=vals[k])
            self._color_vars[k] = var
            tk.Spinbox(row, from_=0.0, to=1.0, increment=0.05, width=5, textvariable=var,
                       command=lambda: self._color_update_preview()).pack(side=tk.LEFT, padx=(2, 8))
        self._color_preview = tk.Label(row, text="　　", bg="#ffffff", relief=tk.SUNKEN, width=4)
        self._color_preview.pack(side=tk.LEFT, padx=6)
        self._color_update_preview()
        self._kind = "color_custom"

    def _color_update_preview(self):
        if not self.winfo_exists():
            return
        def clamp(x):
            return max(0, min(255, int(round(x * 255))))
        try:
            r, g, b = (clamp(self._color_vars[k].get()) for k in ("r", "g", "b"))
            self._color_preview.configure(bg=f"#{r:02x}{g:02x}{b:02x}")
        except Exception:
            return
        self.after(150, self._color_update_preview)

    # -- ID参照(enum / class_data_id) ---------------------------------------
    def _build_enum(self, members: List[str], initial_value):
        self._kind = "enum"
        type_name = base_type_of(self.ftype)
        row = tk.Frame(self, bg=self["bg"])
        row.pack(fill=tk.X, padx=4, pady=2)
        tk.Label(row, text=f"{self.field_def['name']} ({type_name}):", bg=self["bg"], fg=C["text"],
                 width=22, anchor=tk.W).pack(side=tk.LEFT)
        display_values = [f"{type_name}.{m}" for m in members]
        var = tk.StringVar()
        cur = str(initial_value) if initial_value else ""
        var.set(cur if cur in display_values else (display_values[0] if display_values else ""))
        combo = ttk.Combobox(row, textvariable=var, values=display_values, state="readonly", width=30)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._widgets["enum_var"] = var

    # -- スカラー --------------------------------------------------------
    def _build_scalar(self, initial_value):
        self._kind = "scalar"
        base = base_type_of(self.ftype).lower()
        row = tk.Frame(self, bg=self["bg"])
        row.pack(fill=tk.X, padx=4, pady=2)
        tk.Label(row, text=f"{self.field_def['name']} ({self.ftype}):", bg=self["bg"], fg=C["text"],
                 width=22, anchor=tk.W).pack(side=tk.LEFT)

        if base == "bool":
            var = tk.BooleanVar(value=bool(initial_value))
            tk.Checkbutton(row, variable=var, bg=self["bg"], selectcolor=C["input_bg"],
                           activebackground=self["bg"]).pack(side=tk.LEFT)
            self._widgets["var"] = var
            return

        if base == "text_list_index":
            var = tk.IntVar(value=int(initial_value) if str(initial_value).lstrip("-").isdigit() else -1)
            tk.Entry(row, textvariable=var, width=8, bg=C["input_bg"], fg=C["text"],
                     insertbackground=C["text"], relief=tk.FLAT).pack(side=tk.LEFT)

            def pick():
                idx = self.app._pick_matrix_row_index()
                if idx is not None:
                    var.set(idx)

            self.app._btn(row, "行列から選択…", pick).pack(side=tk.LEFT, padx=6)
            self._widgets["var"] = var
            return

        var = tk.StringVar(value="" if initial_value is None else str(initial_value))
        entry = tk.Entry(row, textvariable=var, bg=C["input_bg"], fg=C["text"], insertbackground=C["text"],
                          relief=tk.FLAT, highlightthickness=1, highlightbackground=C["border"])
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._widgets["var"] = var

    # -- 値の取得 ----------------------------------------------------------
    def get_value(self):
        if self._kind == "array":
            return list(self._array_values)
        if self._kind == "bit_custom":
            n = max(1, min(64, int(self._bit_size_var.get() or 1)))
            bits = [i for i, v in self._bit_vars.items() if v.get()]
            return {"size": n, "bits": sorted(bits)}
        if self._kind == "color_custom":
            return {k: self._color_vars[k].get() for k in ("r", "g", "b", "a")}
        if self._kind == "struct":
            return {name: ed.get_value() for name, ed in self._sub_editors.items()}
        if self._kind == "enum":
            return self._widgets["enum_var"].get()
        # scalar
        base = base_type_of(self.ftype).lower()
        var = self._widgets["var"]
        if base == "bool":
            return bool(var.get())
        if base == "text_list_index":
            try:
                return int(var.get())
            except Exception:
                return -1
        if base in BUILTIN_TYPES_NUMERIC:
            try:
                return int(float(var.get()))
            except Exception:
                return 0
        if base in BUILTIN_TYPES_FLOAT:
            try:
                return float(var.get())
            except Exception:
                return 0.0
        return var.get()


def open_single_value_dialog(parent, app: "ScenarioMatrixEditor", field_def: dict, initial_value):
    """配列の要素1つぶんなど、単一の値をその場でダイアログ編集する。"""
    win = tk.Toplevel(parent)
    win.title(f"値を編集 — {field_def.get('name', field_def.get('type'))}")
    win.configure(bg=C["bg"])
    win.transient(parent)
    win.grab_set()
    editor = FieldValueEditor(win, app, dict(field_def, name=field_def.get("name", "value")), initial_value)
    editor.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    result = {"value": None, "ok": False}

    def ok():
        result["value"] = editor.get_value()
        result["ok"] = True
        win.destroy()

    btns = tk.Frame(win, bg=C["bg"])
    btns.pack(fill=tk.X, padx=10, pady=(0, 10))
    app._btn(btns, "OK", ok, accent=True).pack(side=tk.RIGHT)
    app._btn(btns, "キャンセル", win.destroy).pack(side=tk.RIGHT, padx=6)
    win.wait_window()
    return result["value"] if result["ok"] else None


def open_role_call_form(parent, app: "ScenarioMatrixEditor", role_name: str, schema: dict,
                         initial_values: Optional[Dict[str, object]] = None) -> Optional[Dict[str, object]]:
    """Role呼び出し1行ぶんの全フィールドを、型に応じたフォームでまとめて編集する
    (BaseRoleInputForm.js 相当)。OKなら { フィールド名: 値 } を返す。"""
    initial_values = initial_values or {}
    win = tk.Toplevel(parent)
    win.title(f"ロール入力 — {role_name}")
    win.configure(bg=C["bg"])
    win.geometry("560x600")
    win.transient(parent)
    win.grab_set()

    tk.Label(win, text=f"Role: {role_name}", bg=C["bg"], fg=C["text"], font=("Segoe UI Semibold", 12)).pack(
        anchor=tk.W, padx=10, pady=(10, 4))

    canvas = tk.Canvas(win, bg=C["bg"], highlightthickness=0)
    vsb = ttk.Scrollbar(win, orient=tk.VERTICAL, command=canvas.yview)
    inner = tk.Frame(canvas, bg=C["bg"])
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=4)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    fields = schema.get("fields", [])
    if not fields:
        tk.Label(inner, text="このロールにはフィールドが定義されていません。\n"
                              "「ロール」タブでフィールドを追加してください。",
                 bg=C["bg"], fg=C["text_muted"], justify=tk.LEFT).pack(padx=8, pady=8)

    editors: Dict[str, FieldValueEditor] = {}
    for f in fields:
        ed = FieldValueEditor(inner, app, f, initial_values.get(f["name"]))
        ed.pack(fill=tk.X, padx=4, pady=3)
        editors[f["name"]] = ed

    result = {"values": None}

    def ok():
        result["values"] = {name: ed.get_value() for name, ed in editors.items()}
        win.destroy()

    btns = tk.Frame(win, bg=C["bg"])
    btns.pack(fill=tk.X, padx=10, pady=10)
    app._btn(btns, "OK", ok, accent=True).pack(side=tk.RIGHT)
    app._btn(btns, "キャンセル", win.destroy).pack(side=tk.RIGHT, padx=6)
    win.wait_window()
    return result["values"]


class ScenarioMatrixEditor(tk.Tk):
    def __init__(self, initial_path: Optional[str] = None):
        super().__init__()
        self.title("Scenario Matrix Editor")
        self.minsize(900, 560)
        self.configure(bg=C["bg"])

        self.settings = load_settings()
        tags_path_stored = self.settings.get("tags_path") or ""
        self.tags_path = from_stored_path(tags_path_stored) if tags_path_stored else TAGS_PATH
        if not os.path.isfile(self.tags_path):
            self.tags_path = TAGS_PATH
        ensure_tag_file(self.tags_path)
        self.settings["tags_path"] = to_relative_path(self.tags_path)
        self.tag_config = _read_json(self.tags_path, DEFAULT_TAG_CONFIG)
        self._completion_popup: Optional[tk.Toplevel] = None

        self.comments_store = CommentStore()
        self.store = ScenarioDataStore()
        self._dsl_popup: Optional[tk.Toplevel] = None
        self._dsl_popup_list: Optional[tk.Listbox] = None
        self._dsl_popup_items: List[dict] = []
        self._dsl_current_event_id: Optional[str] = None
        self._dsl_current_sub_id: Optional[str] = None
        self._dsl_dirty = False

        geo = self.settings.get("geometry") or "1200x820"
        try:
            self.geometry(geo)
        except tk.TclError:
            self.geometry("1200x820")

        self.matrix: Optional[dict] = None
        self.path: Optional[str] = None
        self._items: List[str] = []
        self._comments: List[str] = []
        self._loaded_keys: Tuple[Optional[str], Optional[str], Optional[str]] = (None, None, None)
        self._dirty = False
        self._loading = False

        self._setup_style()
        self._build_ui()

        startup = initial_path if (initial_path and os.path.isfile(initial_path)) else None
        if not startup:
            last_stored = self.settings.get("last_matrix_path") or ""
            if last_stored:
                candidate = from_stored_path(last_stored)
                if os.path.isfile(candidate):
                    startup = candidate
        if startup:
            self._open_path(
                startup,
                restore={
                    "row": self.settings.get("last_row") or "",
                    "col": self.settings.get("last_col") or "",
                    "field": self.settings.get("last_field") or "texts",
                },
            )

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-o>", lambda e: self.open_file())
        self.bind("<Control-s>", lambda e: self.save_file())
        self.bind("<Control-Return>", lambda e: self.apply_editor())

    # -- スタイル -----------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=C["bg"], foreground=C["text"])
        style.configure("TFrame", background=C["bg"])
        style.configure("TLabel", background=C["bg"], foreground=C["text"], font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=C["bg"], foreground=C["text"], font=("Segoe UI Semibold", 14))
        style.configure("Muted.TLabel", background=C["bg"], foreground=C["text_muted"], font=("Segoe UI", 9))
        style.configure(
            "Accent.TButton",
            background=C["accent"],
            foreground="#ffffff",
            font=("Segoe UI Semibold", 10),
            padding=(12, 6),
            borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", C["accent_hover"]), ("disabled", C["accent_dim"])])
        style.configure(
            "Ghost.TButton",
            background=C["surface2"],
            foreground=C["text"],
            font=("Segoe UI", 9),
            padding=(10, 5),
            borderwidth=0,
        )
        style.map("Ghost.TButton", background=[("active", C["border"])])
        style.configure(
            "Danger.TButton",
            background=C["danger"],
            foreground="#ffffff",
            font=("Segoe UI", 9),
            padding=(10, 5),
            borderwidth=0,
        )
        style.configure(
            "TCombobox",
            fieldbackground=C["input_bg"],
            background=C["surface2"],
            foreground=C["text"],
            arrowcolor=C["text"],
            padding=4,
        )
        style.map("TCombobox", fieldbackground=[("readonly", C["input_bg"])], foreground=[("readonly", C["text"])])
        style.configure(
            "Status.TLabel",
            background=C["surface"],
            foreground=C["text_muted"],
            font=("Segoe UI", 9),
            padding=(10, 6),
        )

    def _btn(self, parent, text, command, accent=False, danger=False):
        style = "Accent.TButton" if accent else ("Danger.TButton" if danger else "Ghost.TButton")
        return ttk.Button(parent, text=text, command=command, style=style)

    # -- UI 構築 ------------------------------------------------------------
    def _build_ui(self) -> None:
        """ウィンドウ全体を、複数タブ(テキスト行列／シナリオイベント／ロール／
        トランザクションDSL)を持つ ttk.Notebook として構築する。
        既存のテキスト行列編集機能は _build_text_matrix_tab に切り出し、
        Notebookの1タブとしてそのまま収容する(内部ロジックは無変更)。"""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        tab_matrix = tk.Frame(self.notebook, bg=C["bg"])
        tab_event = tk.Frame(self.notebook, bg=C["bg"])
        tab_role = tk.Frame(self.notebook, bg=C["bg"])
        tab_dsl = tk.Frame(self.notebook, bg=C["bg"])

        self.notebook.add(tab_matrix, text="テキスト行列")
        self.notebook.add(tab_event, text="シナリオイベント")
        self.notebook.add(tab_role, text="ロール")
        self.notebook.add(tab_dsl, text="トランザクション(DSL)")

        self._build_text_matrix_tab(tab_matrix)
        self._build_event_tab(tab_event)
        self._build_role_tab(tab_role)
        self._build_dsl_tab(tab_dsl)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, _e=None) -> None:
        try:
            idx = self.notebook.index(self.notebook.select())
        except Exception:
            return
        # イベント/ロールタブを開いた際に最新のディスク内容へ更新しておく
        if idx == 1:
            self._event_refresh_tree()
        elif idx == 2:
            self._role_refresh_list()
        elif idx == 3:
            self._dsl_refresh_selectors()

    def _build_text_matrix_tab(self, parent: tk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(header, text="Scenario Matrix Editor", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="  高速 · 配列編集 · 行コメント · テキストI/O · 翻訳 · タグ補完", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text=f"設定: {CONFIG_DIR}", style="Muted.TLabel").pack(side=tk.RIGHT)

        # パスバー
        path_card = tk.Frame(parent, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        path_card.pack(fill=tk.X, padx=16, pady=6)
        path_inner = tk.Frame(path_card, bg=C["surface"])
        path_inner.pack(fill=tk.X, padx=12, pady=10)
        tk.Label(
            path_inner,
            text="JSON パス（一度開けば次回起動時も自動で復元されます）",
            bg=C["surface"],
            fg=C["text_muted"],
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W)

        path_row = tk.Frame(path_inner, bg=C["surface"])
        path_row.pack(fill=tk.X, pady=(4, 0))
        self.path_var = tk.StringVar(value="")
        self.path_entry = tk.Entry(
            path_row,
            textvariable=self.path_var,
            bg=C["input_bg"],
            fg=C["accent"],
            insertbackground=C["accent"],
            relief=tk.FLAT,
            font=("Consolas", 10),
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))
        self.path_entry.bind("<Return>", lambda e: self._open_from_entry())
        self._btn(path_row, "参照…", self.open_file, accent=True).pack(side=tk.LEFT, padx=2)
        self._btn(path_row, "保存", self.save_file).pack(side=tk.LEFT, padx=2)
        self._btn(path_row, "別名…", self.save_as).pack(side=tk.LEFT, padx=2)
        self._btn(path_row, "再読込", self.reload_current).pack(side=tk.LEFT, padx=2)
        self._btn(path_row, "設定フォルダ", lambda: open_in_explorer(CONFIG_DIR)).pack(side=tk.LEFT, padx=2)

        # 履歴
        recent_row = tk.Frame(path_inner, bg=C["surface"])
        recent_row.pack(fill=tk.X, pady=(6, 0))
        tk.Label(recent_row, text="最近使ったファイル:", bg=C["surface"], fg=C["text_muted"], font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self.recent_var = tk.StringVar()
        self.recent_combo = ttk.Combobox(recent_row, textvariable=self.recent_var, state="readonly", width=70)
        self.recent_combo.pack(side=tk.LEFT, padx=8)
        self.recent_combo.bind("<<ComboboxSelected>>", self._on_recent_selected)
        self._refresh_recent()

        # セレクタ
        sel = tk.Frame(parent, bg=C["bg"])
        sel.pack(fill=tk.X, padx=16, pady=8)
        self._labeled_combo(sel, "行 (Language)", "row")
        self._labeled_combo(sel, "列 (Scenario)", "col", width=36)
        self._labeled_entry(sel, "フィールド", "field", default="texts", width=12)
        self._btn(sel, "読込", self._reload_list, accent=True).pack(side=tk.LEFT, padx=(8, 0))

        # ツールバー
        tools = tk.Frame(parent, bg=C["bg"])
        tools.pack(fill=tk.X, padx=16, pady=(0, 6))
        for label, cmd, kw in [
            ("↑ 上へ", self.move_up, {}),
            ("↓ 下へ", self.move_down, {}),
            ("入れ替え…", self.swap_items, {}),
            ("上に追加", lambda: self.add_relative(-1), {}),
            ("下に追加", lambda: self.add_relative(1), {}),
            ("位置指定挿入…", self.insert_at_index, {}),
            ("末尾に追加", self.append_item, {"accent": True}),
            ("複製", self.duplicate_item, {}),
            ("削除", self.delete_item, {"danger": True}),
        ]:
            self._btn(tools, label, cmd, **kw).pack(side=tk.LEFT, padx=2)
        tk.Frame(tools, bg=C["border"], width=1).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
        self._btn(tools, "テキスト取込…", self.import_text).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "テキスト出力…", self.export_text).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "翻訳…", self.open_translate_dialog).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "全文プレビュー", self.preview_all).pack(side=tk.LEFT, padx=2)
        tk.Frame(tools, bg=C["border"], width=1).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
        self._btn(tools, "タグ定義の編集…", self.open_tag_editor, accent=True).pack(side=tk.LEFT, padx=2)

        # 分割
        paned = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)
        left = tk.Frame(paned, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        right = tk.Frame(paned, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        paned.add(left, weight=2)
        paned.add(right, weight=3)

        tk.Label(
            left,
            text="  配列一覧 ／ 選択行の左「＋」で上下に追加・ドラッグで行間に挿入",
            bg=C["surface"],
            fg=C["text_muted"],
            font=("Segoe UI", 9),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(8, 4))
        list_wrap = tk.Frame(left, bg=C["surface"])
        list_wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # 左ガター（＋ボタン置き場）
        self.gutter = tk.Frame(list_wrap, bg=C["surface"], width=26)
        self.gutter.pack(side=tk.LEFT, fill=tk.Y)
        self.gutter.pack_propagate(False)
        self.plus_btn = tk.Button(
            self.gutter,
            text="＋",
            command=self._show_add_menu,
            bg=C["accent"],
            fg="#ffffff",
            activebackground=C["accent_hover"],
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        # 選択時のみ place される

        self.listbox = tk.Listbox(
            list_wrap,
            bg=C["input_bg"],
            fg=C["text"],
            selectbackground=C["list_sel"],
            selectforeground="#ffffff",
            activestyle="none",
            font=("Consolas", 11),
            relief=tk.FLAT,
            highlightthickness=0,
            borderwidth=0,
            exportselection=False,
        )
        sb = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self.listbox.yview)

        def _yscroll(*args):
            sb.set(*args)
            self._update_plus_button()

        self.listbox.configure(yscrollcommand=_yscroll)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Double-Button-1>", lambda e: self.editor.focus_set())
        self.listbox.bind("<Configure>", lambda e: self._update_plus_button())
        self.listbox.bind("<MouseWheel>", lambda e: self.after(10, self._update_plus_button), add="+")
        self.listbox.bind("<Button-3>", self._on_list_right_click, add="+")
        # ドラッグ＆ドロップ（行間に挿入）
        self._array_dnd = ListboxDragInsert(self.listbox, self._reorder_array, lambda: len(self._items))

        # 右: 本文 + コメント
        tk.Label(right, text="  選択行の本文", bg=C["surface"], fg=C["text_muted"], font=("Segoe UI", 9), anchor=tk.W).pack(fill=tk.X, pady=(8, 4))
        edit_wrap = tk.Frame(right, bg=C["surface"])
        edit_wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        self.editor = tk.Text(
            edit_wrap,
            wrap=tk.WORD,
            bg=C["input_bg"],
            fg=C["text"],
            insertbackground=C["accent"],
            selectbackground=C["list_sel"],
            font=("Meiryo UI", 12),
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
            padx=10,
            pady=10,
        )
        esb = ttk.Scrollbar(edit_wrap, orient=tk.VERTICAL, command=self.editor.yview)
        self.editor.configure(yscrollcommand=esb.set)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        esb.pack(side=tk.RIGHT, fill=tk.Y)
        # タグ補完・自動閉じ（既存本文の途中でも動作）
        self.editor.bind("<Control-space>", self._on_tag_complete)
        self.editor.bind("<Control-Key-space>", self._on_tag_complete)
        self.editor.bind("<KeyPress-slash>", self._on_slash_auto_close)
        self.editor.bind("<KeyPress>", self._on_editor_keypress, add="+")
        self.editor.bind("<FocusOut>", lambda e: self._close_completion_popup(), add="+")
        self.editor.bind("<Escape>", lambda e: self._close_completion_popup() or None, add="+")

        tk.Label(
            right,
            text="  この行のコメント（演出メモ）  ※本文で Ctrl+Space = タグ補完 / で自動閉じ",
            bg=C["surface"],
            fg=C["comment"],
            font=("Segoe UI", 9),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(6, 2))
        cmt_wrap = tk.Frame(right, bg=C["surface"])
        cmt_wrap.pack(fill=tk.X, padx=8, pady=(0, 4))
        self.comment_box = tk.Text(
            cmt_wrap,
            wrap=tk.WORD,
            height=5,
            bg=C["input_bg"],
            fg=C["comment"],
            insertbackground=C["comment"],
            selectbackground=C["list_sel"],
            font=("Meiryo UI", 10),
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["comment"],
            padx=10,
            pady=8,
        )
        csb = ttk.Scrollbar(cmt_wrap, orient=tk.VERTICAL, command=self.comment_box.yview)
        self.comment_box.configure(yscrollcommand=csb.set)
        self.comment_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        csb.pack(side=tk.RIGHT, fill=tk.Y)

        btn_row = tk.Frame(right, bg=C["surface"])
        btn_row.pack(fill=tk.X, padx=8, pady=(0, 10))
        self._btn(btn_row, "本文＋コメントを反映  (Ctrl+Enter)", self.apply_editor, accent=True).pack(side=tk.LEFT)
        self._btn(btn_row, "コメントだけ反映", self.apply_comment).pack(side=tk.LEFT, padx=6)
        self._btn(btn_row, "コメント削除", self.clear_comment, danger=True).pack(side=tk.LEFT)

        self.status = ttk.Label(parent, text="「参照…」で JSON を開くか、パスを入力して Enter", style="Status.TLabel")
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    # ------------------------------------------------------------------
    # 共通: ロール名を「文字入力ではなく選択」させるためのピッカー
    # ------------------------------------------------------------------
    def _pick_role_name(self, title: str = "ロールを選択") -> Optional[str]:
        names = self.store.role_names()
        if not names:
            messagebox.showinfo("ロールが未登録", "先に「ロール」タブでロールを作成してください。", parent=self)
            return None
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=C["bg"])
        win.geometry("360x420")
        win.transient(self)
        win.grab_set()
        tk.Label(win, text="ロール名を選択してください(一覧から選択・ダブルクリックで決定)",
                 bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 9), anchor=tk.W, wraplength=340).pack(fill=tk.X, padx=10, pady=(10, 4))
        filt_var = tk.StringVar()
        filt = tk.Entry(win, textvariable=filt_var, bg=C["input_bg"], fg=C["text"], relief=tk.FLAT,
                         insertbackground=C["text"])
        filt.pack(fill=tk.X, padx=10)
        lb = tk.Listbox(win, bg=C["input_bg"], fg=C["text"], selectbackground=C["list_sel"],
                         activestyle="none", exportselection=False)
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        def refresh_list(*_a):
            lb.delete(0, tk.END)
            q = filt_var.get().lower()
            for n in names:
                if q in n.lower():
                    lb.insert(tk.END, n)
            if lb.size():
                lb.selection_set(0)

        filt_var.trace_add("write", refresh_list)
        refresh_list()
        lb.focus_set()

        result = {"value": None}

        def confirm(_e=None):
            sel = lb.curselection()
            if sel:
                result["value"] = lb.get(sel[0])
                win.destroy()

        lb.bind("<Double-Button-1>", confirm)
        lb.bind("<Return>", confirm)
        win.bind("<Escape>", lambda e: win.destroy())
        btns = tk.Frame(win, bg=C["bg"])
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._btn(btns, "選択", confirm, accent=True).pack(side=tk.RIGHT)
        self._btn(btns, "キャンセル", win.destroy).pack(side=tk.RIGHT, padx=6)
        self.wait_window(win)
        return result["value"]

    def _pick_matrix_row_index(self) -> Optional[int]:
        """text_list_index型: 現在「テキスト行列」タブで開いている matrix の
        選択中の列(Scenario)の行(List<string>)から、対象のインデックスを
        一覧から選んでもらう。行列タブ側と同じ self._items をそのまま使う。"""
        if not self._items:
            messagebox.showinfo(
                "行列が未読込",
                "「テキスト行列」タブで対象の行(Language)・列(Scenario)を読み込んでから使ってください。",
                parent=self,
            )
            return None
        win = tk.Toplevel(self)
        win.title(f"行列から選択 — {self.row_var.get()} / {self.col_var.get()}")
        win.configure(bg=C["bg"])
        win.geometry("520x420")
        win.transient(self)
        win.grab_set()
        lb = tk.Listbox(win, bg=C["input_bg"], fg=C["text"], selectbackground=C["list_sel"],
                         activestyle="none", font=("Consolas", 10))
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for i, text in enumerate(self._items):
            preview = (text or "").replace("\n", " ")[:60]
            lb.insert(tk.END, f"{i} : {preview}")
        result = {"value": None}

        def confirm(_e=None):
            sel = lb.curselection()
            if sel:
                result["value"] = sel[0]
                win.destroy()

        lb.bind("<Double-Button-1>", confirm)
        lb.bind("<Return>", confirm)
        btns = tk.Frame(win, bg=C["bg"])
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._btn(btns, "選択", confirm, accent=True).pack(side=tk.RIGHT)
        self._btn(btns, "キャンセル", win.destroy).pack(side=tk.RIGHT, padx=6)
        self.wait_window(win)
        return result["value"]

    # ------------------------------------------------------------------
    # フィールド定義1件を編集するダイアログ(型は必ずComboboxから「選択」)
    # ------------------------------------------------------------------
    def _open_field_def_dialog(self, initial: Optional[dict] = None) -> Optional[dict]:
        builtin = ["string", "int", "uint", "short", "long", "byte", "float", "double", "decimal",
                   "char", "bool", "vector2", "vector3", "vector4", "bit", "color", "bezier",
                   "dictionary", "text_list_index", "voice_ref"]
        class_types = self.store.list_class_data_types()
        all_types = builtin + [t for t in class_types if t not in builtin]

        win = tk.Toplevel(self)
        win.title("フィールド定義")
        win.configure(bg=C["bg"])
        win.transient(self)
        win.grab_set()
        win.geometry("380x260")

        initial = initial or {}
        base_initial = base_type_of(initial.get("type", "string"))
        was_array = is_array_type(initial.get("type", ""))

        form = tk.Frame(win, bg=C["bg"])
        form.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        tk.Label(form, text="フィールド名:", bg=C["bg"], fg=C["text"]).grid(row=0, column=0, sticky=tk.W, pady=4)
        name_var = tk.StringVar(value=initial.get("name", ""))
        tk.Entry(form, textvariable=name_var, bg=C["input_bg"], fg=C["text"], insertbackground=C["text"],
                 relief=tk.FLAT).grid(row=0, column=1, sticky=tk.EW, pady=4)

        tk.Label(form, text="型(一覧から選択):", bg=C["bg"], fg=C["text"]).grid(row=1, column=0, sticky=tk.W, pady=4)
        type_var = tk.StringVar(value=base_initial if base_initial in all_types else (all_types[0] if all_types else "string"))
        type_combo = ttk.Combobox(form, textvariable=type_var, values=all_types, state="readonly")
        type_combo.grid(row=1, column=1, sticky=tk.EW, pady=4)

        array_var = tk.BooleanVar(value=was_array)
        tk.Checkbutton(form, text="配列にする ( [] )", variable=array_var, bg=C["bg"], fg=C["text"],
                       selectcolor=C["input_bg"], activebackground=C["bg"]).grid(row=2, column=1, sticky=tk.W, pady=4)

        tk.Label(form, text="bit のサイズ(bit型のみ):", bg=C["bg"], fg=C["text"]).grid(row=3, column=0, sticky=tk.W, pady=4)
        size_var = tk.IntVar(value=(initial.get("options") or {}).get("size", 8))
        tk.Spinbox(form, from_=1, to=64, textvariable=size_var, width=6).grid(row=3, column=1, sticky=tk.W, pady=4)

        form.columnconfigure(1, weight=1)
        result = {"value": None}

        def ok():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("入力エラー", "フィールド名を入力してください。", parent=win)
                return
            t = type_var.get() + ("[]" if array_var.get() else "")
            field_def = {"name": name, "type": t}
            if base_type_of(t).lower() == "bit":
                field_def["options"] = {"size": int(size_var.get())}
            result["value"] = field_def
            win.destroy()

        btns = tk.Frame(win, bg=C["bg"])
        btns.pack(fill=tk.X, padx=12, pady=(0, 12))
        self._btn(btns, "OK", ok, accent=True).pack(side=tk.RIGHT)
        self._btn(btns, "キャンセル", win.destroy).pack(side=tk.RIGHT, padx=6)
        win.wait_window()
        return result["value"]

    def _open_field_list_editor(self, title: str, fields: List[dict]) -> List[dict]:
        """フィールド定義のリストを一覧編集する(Role schema / class_data struct
        の両方で共用)。返り値は編集結果の新しいリスト(キャンセル時は元のまま)。"""
        fields = [dict(f) for f in fields]
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=C["bg"])
        win.transient(self)
        win.grab_set()
        win.geometry("480x420")

        tree = ttk.Treeview(win, columns=("type",), show="tree headings", height=14)
        tree.heading("#0", text="フィールド名")
        tree.heading("type", text="型")
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def refresh():
            tree.delete(*tree.get_children())
            for i, f in enumerate(fields):
                tree.insert("", tk.END, iid=str(i), text=f["name"], values=(f["type"],))

        refresh()

        def add():
            fd = self._open_field_def_dialog()
            if fd:
                fields.append(fd)
                refresh()

        def edit():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            fd = self._open_field_def_dialog(fields[idx])
            if fd:
                fields[idx] = fd
                refresh()

        def delete():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            if messagebox.askyesno("確認", f"フィールド「{fields[idx]['name']}」を削除しますか？", parent=win):
                del fields[idx]
                refresh()

        def move(d):
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            j = idx + d
            if 0 <= j < len(fields):
                fields[idx], fields[j] = fields[j], fields[idx]
                refresh()
                tree.selection_set(str(j))

        btns = tk.Frame(win, bg=C["bg"])
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._btn(btns, "追加…", add, accent=True).pack(side=tk.LEFT)
        self._btn(btns, "編集…", edit).pack(side=tk.LEFT, padx=4)
        self._btn(btns, "削除", delete, danger=True).pack(side=tk.LEFT, padx=4)
        self._btn(btns, "↑", lambda: move(-1)).pack(side=tk.LEFT, padx=(12, 2))
        self._btn(btns, "↓", lambda: move(1)).pack(side=tk.LEFT)
        tree.bind("<Double-Button-1>", lambda e: edit())

        result = {"ok": False}

        def close_ok():
            result["ok"] = True
            win.destroy()

        self._btn(btns, "完了", close_ok, accent=True).pack(side=tk.RIGHT)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.wait_window()
        return fields if result["ok"] else [dict(f) for f in fields]

    # ------------------------------------------------------------------
    # クラスデータ(class_data / class_data_id)管理
    # ------------------------------------------------------------------
    def _open_class_data_manager(self) -> None:
        win = tk.Toplevel(self)
        win.title("クラスデータ管理 (class_data / class_data_id)")
        win.configure(bg=C["bg"])
        win.transient(self)
        win.grab_set()
        win.geometry("520x460")

        tk.Label(
            win,
            text="ID参照型(class_data_id/enum相当)は「候補メンバー一覧」を、\n"
                 "構造体型(class_data相当)は「サブフィールド一覧」を持ちます。\n"
                 "ここで定義した型名は、ロールのフィールド型として選択できるようになります。",
            bg=C["bg"], fg=C["text_muted"], justify=tk.LEFT, font=("Segoe UI", 9),
        ).pack(fill=tk.X, padx=12, pady=(12, 6))

        body = tk.Frame(win, bg=C["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        lb = tk.Listbox(body, bg=C["input_bg"], fg=C["text"], selectbackground=C["list_sel"], width=28)
        lb.pack(side=tk.LEFT, fill=tk.Y)
        detail = tk.Frame(body, bg=C["bg"])
        detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        detail_label = tk.Label(detail, text="(型を選択してください)", bg=C["bg"], fg=C["text_muted"], justify=tk.LEFT, anchor=tk.NW)
        detail_label.pack(fill=tk.BOTH, expand=True)

        def refresh_types(select: Optional[str] = None):
            lb.delete(0, tk.END)
            names = self.store.list_class_data_types()
            for n in names:
                lb.insert(tk.END, n)
            if select and select in names:
                lb.selection_set(names.index(select))
                show_detail()

        def show_detail(_e=None):
            sel = lb.curselection()
            for w in detail.winfo_children():
                w.destroy()
            if not sel:
                return
            type_name = lb.get(sel[0])
            data = self.store.load_class_data(type_name) or {"kind": "id_list", "members": []}
            if data.get("kind") == "id_list":
                tk.Label(detail, text=f"{type_name}  (ID参照型 / メンバー一覧)", bg=C["bg"], fg=C["text"],
                         font=("Segoe UI Semibold", 10)).pack(anchor=tk.W)
                members_lb = tk.Listbox(detail, bg=C["input_bg"], fg=C["text"], height=10)
                members_lb.pack(fill=tk.BOTH, expand=True, pady=6)
                for m in data.get("members", []):
                    members_lb.insert(tk.END, m)

                add_row = tk.Frame(detail, bg=C["bg"])
                add_row.pack(fill=tk.X)
                new_var = tk.StringVar()
                tk.Entry(add_row, textvariable=new_var, bg=C["input_bg"], fg=C["text"],
                         insertbackground=C["text"], relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True)

                def add_member():
                    v = new_var.get().strip()
                    if v:
                        members_lb.insert(tk.END, v)
                        new_var.set("")

                def del_member():
                    s = members_lb.curselection()
                    if s:
                        members_lb.delete(s[0])

                def save_members():
                    data["members"] = list(members_lb.get(0, tk.END))
                    self.store.save_class_data(type_name, data)
                    messagebox.showinfo("保存しました", f"{type_name} を保存しました。", parent=win)

                self._btn(add_row, "追加", add_member, accent=True).pack(side=tk.LEFT, padx=4)
                self._btn(add_row, "削除", del_member, danger=True).pack(side=tk.LEFT)
                self._btn(detail, "保存", save_members, accent=True).pack(anchor=tk.E, pady=6)
            else:
                tk.Label(detail, text=f"{type_name}  (構造体 / サブフィールド一覧)", bg=C["bg"], fg=C["text"],
                         font=("Segoe UI Semibold", 10)).pack(anchor=tk.W)
                subfields = data.get("subFields", [])
                summary = "\n".join(f"・{f['name']} : {f['type']}" for f in subfields) or "(フィールドなし)"
                tk.Label(detail, text=summary, bg=C["bg"], fg=C["text"], justify=tk.LEFT, anchor=tk.NW).pack(
                    fill=tk.BOTH, expand=True, pady=6)

                def edit_fields():
                    new_fields = self._open_field_list_editor(f"{type_name} のサブフィールド", subfields)
                    data["subFields"] = new_fields
                    self.store.save_class_data(type_name, data)
                    show_detail()

                self._btn(detail, "サブフィールドを編集…", edit_fields, accent=True).pack(anchor=tk.E)

        lb.bind("<<ListboxSelect>>", show_detail)

        def add_type():
            name_win = tk.Toplevel(win)
            name_win.title("新しいクラスデータ型")
            name_win.configure(bg=C["bg"])
            name_win.transient(win)
            name_win.grab_set()
            tk.Label(name_win, text="型名:", bg=C["bg"], fg=C["text"]).grid(row=0, column=0, padx=8, pady=8, sticky=tk.W)
            name_var = tk.StringVar()
            tk.Entry(name_win, textvariable=name_var, bg=C["input_bg"], fg=C["text"],
                     insertbackground=C["text"]).grid(row=0, column=1, padx=8, pady=8)
            tk.Label(name_win, text="種類:", bg=C["bg"], fg=C["text"]).grid(row=1, column=0, padx=8, pady=8, sticky=tk.W)
            kind_var = tk.StringVar(value="id_list")
            ttk.Combobox(name_win, textvariable=kind_var, state="readonly",
                         values=["id_list", "struct"]).grid(row=1, column=1, padx=8, pady=8)

            def create():
                n = name_var.get().strip()
                if not n:
                    return
                data = {"kind": kind_var.get()}
                data["members" if data["kind"] == "id_list" else "subFields"] = []
                self.store.save_class_data(n, data)
                name_win.destroy()
                refresh_types(select=n)

            btn_row = tk.Frame(name_win, bg=C["bg"])
            btn_row.grid(row=2, column=0, columnspan=2, pady=8)
            self._btn(btn_row, "作成", create, accent=True).pack(side=tk.LEFT, padx=4)
            self._btn(btn_row, "キャンセル", name_win.destroy).pack(side=tk.LEFT)

        def delete_type():
            sel = lb.curselection()
            if not sel:
                return
            type_name = lb.get(sel[0])
            if messagebox.askyesno("確認", f"クラスデータ型「{type_name}」を削除しますか？", parent=win):
                try:
                    os.remove(self.store._class_data_path(type_name))
                except FileNotFoundError:
                    pass
                refresh_types()

        btns = tk.Frame(win, bg=C["bg"])
        btns.pack(fill=tk.X, padx=12, pady=(0, 12))
        self._btn(btns, "型を追加…", add_type, accent=True).pack(side=tk.LEFT)
        self._btn(btns, "型を削除", delete_type, danger=True).pack(side=tk.LEFT, padx=6)
        self._btn(btns, "閉じる", win.destroy).pack(side=tk.RIGHT)

        refresh_types()

    # ==================================================================
    # タブ: シナリオイベント (Event > SubEvent を選択形式で表示・編集)
    # ==================================================================
    def _build_event_tab(self, parent: tk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(header, text="シナリオイベント", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text=f"  保存先: {to_relative_path(SCENARIO_EVENTS_PATH)}", style="Muted.TLabel").pack(side=tk.LEFT)

        tools = tk.Frame(parent, bg=C["bg"])
        tools.pack(fill=tk.X, padx=16, pady=(0, 6))
        self._btn(tools, "イベント追加…", self._event_add_event, accent=True).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "サブイベント追加…", self._event_add_sub).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "編集…", self._event_edit_selected).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "複製…", self._event_copy_selected).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "削除", self._event_delete_selected, danger=True).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "更新", self._event_refresh_tree).pack(side=tk.LEFT, padx=(12, 2))
        self._btn(tools, "選択をDSLタブへ", self._event_open_in_dsl, accent=True).pack(side=tk.LEFT, padx=2)

        tree_wrap = tk.Frame(parent, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        tree_wrap.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)

        columns = ("id", "description")
        self.event_tree = ttk.Treeview(tree_wrap, columns=columns, show="tree headings")
        self.event_tree.heading("#0", text="イベント / サブイベント名")
        self.event_tree.heading("id", text="ID")
        self.event_tree.heading("description", text="説明")
        self.event_tree.column("#0", width=280)
        self.event_tree.column("id", width=140)
        self.event_tree.column("description", width=380)
        vsb = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self.event_tree.yview)
        self.event_tree.configure(yscrollcommand=vsb.set)
        self.event_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.event_tree.bind("<Double-Button-1>", lambda e: self._event_edit_selected())

        self.event_status = ttk.Label(parent, text="", style="Status.TLabel")
        self.event_status.pack(fill=tk.X, side=tk.BOTTOM)

        self._event_refresh_tree()

    def _event_refresh_tree(self) -> None:
        """イベント/サブイベントを Treeview に展開して表示する。
        (旧不具合「サブイベントが表示されない」対策: 親行に必ず子アイテムとして
        subEvents を insert し、open=True で最初から展開状態にする)"""
        if not hasattr(self, "event_tree"):
            return
        tree = self.event_tree
        open_ids = {iid for iid in tree.get_children("") if tree.item(iid, "open")}
        tree.delete(*tree.get_children())
        events = self.store.load_events()
        for ev in events:
            eid = str(ev.get("id"))
            parent_iid = f"ev:{eid}"
            tree.insert("", tk.END, iid=parent_iid, text=ev.get("name", ""),
                        values=(eid, ev.get("description", "")), open=True)
            for sub in ev.get("subEvents", []):
                sid = str(sub.get("subId"))
                tree.insert(parent_iid, tk.END, iid=f"{parent_iid}:sub:{sid}",
                            text=sub.get("name", ""), values=(sid, sub.get("description", "")))
        self.event_status.configure(
            text=f"イベント {len(events)} 件 / サブイベント合計 {sum(len(e.get('subEvents', [])) for e in events)} 件")

    def _event_selected_ids(self) -> Tuple[Optional[str], Optional[str]]:
        """選択中のツリーアイテムから (eventId, subId or None) を返す。"""
        sel = self.event_tree.selection()
        if not sel:
            return None, None
        iid = sel[0]
        parts = iid.split(":")
        # "ev:<id>" または "ev:<id>:sub:<subId>"
        if len(parts) == 2:
            return parts[1], None
        if len(parts) == 4:
            return parts[1], parts[3]
        return None, None

    def _event_add_event(self) -> None:
        name = self._ask_text("新しいイベント", "イベント名:")
        if not name:
            return
        desc = self._ask_text("新しいイベント", "説明(省略可):", required=False) or ""
        events = self.store.load_events()
        new_id = self.store.next_event_id(events)
        events.append({"id": new_id, "name": name, "description": desc, "subEvents": []})
        self.store.save_events(events)
        self._event_refresh_tree()

    def _event_add_sub(self) -> None:
        event_id, _ = self._event_selected_ids()
        if event_id is None:
            messagebox.showinfo("選択してください", "先にツリーで親イベントを選択してください。", parent=self)
            return
        name = self._ask_text("新しいサブイベント", "サブイベント名:")
        if not name:
            return
        desc = self._ask_text("新しいサブイベント", "説明(省略可):", required=False) or ""
        events = self.store.load_events()
        ev = next((e for e in events if str(e["id"]) == str(event_id)), None)
        if not ev:
            return
        new_sub_id = self.store.next_sub_id(ev)
        ev.setdefault("subEvents", []).append({"subId": new_sub_id, "name": name, "description": desc})
        self.store.save_events(events)
        self._event_refresh_tree()

    def _event_edit_selected(self) -> None:
        event_id, sub_id = self._event_selected_ids()
        if event_id is None:
            return
        events = self.store.load_events()
        ev = next((e for e in events if str(e["id"]) == str(event_id)), None)
        if not ev:
            return
        target = ev if sub_id is None else next((s for s in ev.get("subEvents", []) if str(s["subId"]) == str(sub_id)), None)
        if target is None:
            return
        name = self._ask_text("編集", "名前:", default=target.get("name", ""))
        if name is None:
            return
        desc = self._ask_text("編集", "説明:", default=target.get("description", ""), required=False)
        target["name"] = name
        target["description"] = desc or ""
        self.store.save_events(events)
        self._event_refresh_tree()

    def _event_copy_selected(self) -> None:
        event_id, sub_id = self._event_selected_ids()
        if event_id is None:
            return
        events = self.store.load_events()
        ev = next((e for e in events if str(e["id"]) == str(event_id)), None)
        if not ev:
            return
        if sub_id is None:
            new_id = self.store.next_event_id(events)
            clone = json.loads(json.dumps(ev))
            clone["id"] = new_id
            clone["name"] = clone.get("name", "") + " のコピー"
            events.append(clone)
        else:
            sub = next((s for s in ev.get("subEvents", []) if str(s["subId"]) == str(sub_id)), None)
            if not sub:
                return
            clone = json.loads(json.dumps(sub))
            clone["subId"] = self.store.next_sub_id(ev)
            clone["name"] = clone.get("name", "") + " のコピー"
            ev.setdefault("subEvents", []).append(clone)
        self.store.save_events(events)
        self._event_refresh_tree()

    def _event_delete_selected(self) -> None:
        event_id, sub_id = self._event_selected_ids()
        if event_id is None:
            return
        if not messagebox.askyesno("確認", "選択中のアイテムを削除しますか？(元に戻せません)", parent=self):
            return
        events = self.store.load_events()
        if sub_id is None:
            events = [e for e in events if str(e["id"]) != str(event_id)]
        else:
            ev = next((e for e in events if str(e["id"]) == str(event_id)), None)
            if ev:
                ev["subEvents"] = [s for s in ev.get("subEvents", []) if str(s["subId"]) != str(sub_id)]
        self.store.save_events(events)
        self._event_refresh_tree()

    def _event_open_in_dsl(self) -> None:
        event_id, sub_id = self._event_selected_ids()
        if event_id is None or sub_id is None:
            messagebox.showinfo("選択してください", "ツリーでサブイベントを選択してください。", parent=self)
            return
        self.notebook.select(3)
        self._dsl_refresh_selectors()
        self.dsl_event_var.set(self._event_label_for(event_id))
        self._dsl_on_event_selected()
        self.dsl_sub_var.set(self._event_sub_label_for(event_id, sub_id))
        self._dsl_on_sub_selected()

    def _ask_text(self, title: str, label: str, default: str = "", required: bool = True) -> Optional[str]:
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=C["bg"])
        win.transient(self)
        win.grab_set()
        tk.Label(win, text=label, bg=C["bg"], fg=C["text"]).pack(anchor=tk.W, padx=12, pady=(12, 2))
        var = tk.StringVar(value=default)
        entry = tk.Entry(win, textvariable=var, bg=C["input_bg"], fg=C["text"], insertbackground=C["text"],
                          relief=tk.FLAT, width=40)
        entry.pack(padx=12, pady=(0, 8), fill=tk.X)
        entry.focus_set()
        entry.selection_range(0, tk.END)
        result = {"value": None}

        def ok(_e=None):
            v = var.get().strip()
            if required and not v:
                messagebox.showwarning("入力エラー", "値を入力してください。", parent=win)
                return
            result["value"] = v
            win.destroy()

        entry.bind("<Return>", ok)
        win.bind("<Escape>", lambda e: win.destroy())
        btns = tk.Frame(win, bg=C["bg"])
        btns.pack(fill=tk.X, padx=12, pady=(0, 12))
        self._btn(btns, "OK", ok, accent=True).pack(side=tk.RIGHT)
        self._btn(btns, "キャンセル", win.destroy).pack(side=tk.RIGHT, padx=6)
        win.wait_window()
        return result["value"]

    # ==================================================================
    # タブ: ロール (一覧は選択形式／フィールドはネスト・配列・class_data_id・
    #        bits・color対応の型付きフォームで編集)
    # ==================================================================
    def _build_role_tab(self, parent: tk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(header, text="ロール", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text=f"  保存先: {to_relative_path(SCENARIO_ROLES_PATH)}", style="Muted.TLabel").pack(side=tk.LEFT)

        paned = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)
        left = tk.Frame(paned, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        right = tk.Frame(paned, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        paned.add(left, weight=1)
        paned.add(right, weight=2)

        tk.Label(left, text="  ロール一覧(選択式)", bg=C["surface"], fg=C["text_muted"], font=("Segoe UI", 9), anchor=tk.W).pack(fill=tk.X, pady=(8, 4))
        self.role_listbox = tk.Listbox(left, bg=C["input_bg"], fg=C["text"], selectbackground=C["list_sel"],
                                        exportselection=False)
        self.role_listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self.role_listbox.bind("<<ListboxSelect>>", lambda e: self._role_on_select())

        role_btns = tk.Frame(left, bg=C["surface"])
        role_btns.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._btn(role_btns, "追加…", self._role_add, accent=True).pack(side=tk.LEFT, padx=2)
        self._btn(role_btns, "名前変更…", self._role_rename).pack(side=tk.LEFT, padx=2)
        self._btn(role_btns, "削除", self._role_delete, danger=True).pack(side=tk.LEFT, padx=2)
        self._btn(left, "クラスデータ管理…", self._open_class_data_manager, accent=True).pack(fill=tk.X, padx=8, pady=(0, 8))

        tk.Label(right, text="  選択中ロールの詳細", bg=C["surface"], fg=C["text_muted"], font=("Segoe UI", 9), anchor=tk.W).pack(fill=tk.X, pady=(8, 4))
        detail = tk.Frame(right, bg=C["surface"])
        detail.pack(fill=tk.X, padx=8)
        tk.Label(detail, text="説明:", bg=C["surface"], fg=C["text"]).grid(row=0, column=0, sticky=tk.W)
        self.role_desc_var = tk.StringVar()
        desc_entry = tk.Entry(detail, textvariable=self.role_desc_var, bg=C["input_bg"], fg=C["text"],
                               insertbackground=C["text"], relief=tk.FLAT)
        desc_entry.grid(row=0, column=1, sticky=tk.EW, padx=6)
        desc_entry.bind("<FocusOut>", lambda e: self._role_save_meta())
        tk.Label(detail, text="タイプ:", bg=C["surface"], fg=C["text"]).grid(row=0, column=2, sticky=tk.W, padx=(12, 0))
        self.role_branch_var = tk.StringVar()
        branch_combo = ttk.Combobox(detail, textvariable=self.role_branch_var, state="readonly",
                                     values=["General", "Branch"], width=10)
        branch_combo.grid(row=0, column=3, sticky=tk.W, padx=6)
        branch_combo.bind("<<ComboboxSelected>>", lambda e: self._role_save_meta())
        detail.columnconfigure(1, weight=1)

        tk.Label(right, text="  フィールドschema(型は必ずドロップダウンから選択)", bg=C["surface"], fg=C["text_muted"],
                 font=("Segoe UI", 9), anchor=tk.W).pack(fill=tk.X, pady=(10, 4))
        field_wrap = tk.Frame(right, bg=C["surface"])
        field_wrap.pack(fill=tk.BOTH, expand=True, padx=8)
        self.role_field_tree = ttk.Treeview(field_wrap, columns=("type",), show="tree headings")
        self.role_field_tree.heading("#0", text="フィールド名")
        self.role_field_tree.heading("type", text="型")
        self.role_field_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fsb = ttk.Scrollbar(field_wrap, orient=tk.VERTICAL, command=self.role_field_tree.yview)
        self.role_field_tree.configure(yscrollcommand=fsb.set)
        fsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.role_field_tree.bind("<Double-Button-1>", lambda e: self._role_field_edit())

        field_btns = tk.Frame(right, bg=C["surface"])
        field_btns.pack(fill=tk.X, padx=8, pady=8)
        self._btn(field_btns, "フィールド追加…", self._role_field_add, accent=True).pack(side=tk.LEFT, padx=2)
        self._btn(field_btns, "編集…", self._role_field_edit).pack(side=tk.LEFT, padx=2)
        self._btn(field_btns, "削除", self._role_field_delete, danger=True).pack(side=tk.LEFT, padx=2)
        self._btn(field_btns, "↑", lambda: self._role_field_move(-1)).pack(side=tk.LEFT, padx=(12, 2))
        self._btn(field_btns, "↓", lambda: self._role_field_move(1)).pack(side=tk.LEFT)
        self._btn(field_btns, "入力フォームをプレビュー…", self._role_preview_form, accent=True).pack(side=tk.RIGHT, padx=2)

        self._role_refresh_list()

    def _role_refresh_list(self, select: Optional[str] = None) -> None:
        if not hasattr(self, "role_listbox"):
            return
        self.role_listbox.delete(0, tk.END)
        names = self.store.role_names()
        for n in names:
            self.role_listbox.insert(tk.END, n)
        if select and select in names:
            self.role_listbox.selection_set(names.index(select))
        self._role_on_select()

    def _role_selected_name(self) -> Optional[str]:
        sel = self.role_listbox.curselection()
        if not sel:
            return None
        return self.role_listbox.get(sel[0])

    def _role_on_select(self) -> None:
        name = self._role_selected_name()
        self.role_field_tree.delete(*self.role_field_tree.get_children())
        if not name:
            self.role_desc_var.set("")
            self.role_branch_var.set("")
            return
        roles = self.store.load_roles()
        meta = next((r for r in roles if r.get("name") == name), {})
        self.role_desc_var.set(meta.get("description", ""))
        self.role_branch_var.set(meta.get("branchType", "General"))
        schema = self.store.load_role_schema(name)
        for i, f in enumerate(schema.get("fields", [])):
            self.role_field_tree.insert("", tk.END, iid=str(i), text=f["name"], values=(f["type"],))

    def _role_save_meta(self) -> None:
        name = self._role_selected_name()
        if not name:
            return
        roles = self.store.load_roles()
        meta = next((r for r in roles if r.get("name") == name), None)
        if meta is None:
            return
        meta["description"] = self.role_desc_var.get()
        meta["branchType"] = self.role_branch_var.get() or "General"
        self.store.save_roles(roles)

    def _role_add(self) -> None:
        name = self._ask_text("新しいロール", "ロール名:")
        if not name:
            return
        roles = self.store.load_roles()
        if any(r.get("name") == name for r in roles):
            messagebox.showwarning("重複", "同名のロールが既にあります。", parent=self)
            return
        roles.append({"name": name, "description": "", "branchType": "General"})
        self.store.save_roles(roles)
        self.store.save_role_schema(name, {"fields": []})
        self._role_refresh_list(select=name)

    def _role_rename(self) -> None:
        old = self._role_selected_name()
        if not old:
            return
        new = self._ask_text("名前変更", "新しいロール名:", default=old)
        if not new or new == old:
            return
        roles = self.store.load_roles()
        if any(r.get("name") == new for r in roles):
            messagebox.showwarning("重複", "同名のロールが既にあります。", parent=self)
            return
        for r in roles:
            if r.get("name") == old:
                r["name"] = new
        self.store.save_roles(roles)
        schema = self.store.load_role_schema(old)
        self.store.save_role_schema(new, schema)
        try:
            os.remove(self.store._role_schema_path(old))
        except FileNotFoundError:
            pass
        self._role_refresh_list(select=new)

    def _role_delete(self) -> None:
        name = self._role_selected_name()
        if not name:
            return
        if not messagebox.askyesno("確認", f"ロール「{name}」を削除しますか？", parent=self):
            return
        roles = [r for r in self.store.load_roles() if r.get("name") != name]
        self.store.save_roles(roles)
        try:
            os.remove(self.store._role_schema_path(name))
        except FileNotFoundError:
            pass
        self._role_refresh_list()

    def _role_field_add(self) -> None:
        name = self._role_selected_name()
        if not name:
            messagebox.showinfo("選択してください", "先にロールを選択してください。", parent=self)
            return
        fd = self._open_field_def_dialog()
        if not fd:
            return
        schema = self.store.load_role_schema(name)
        schema.setdefault("fields", []).append(fd)
        self.store.save_role_schema(name, schema)
        self._role_on_select()

    def _role_field_edit(self) -> None:
        name = self._role_selected_name()
        if not name:
            return
        sel = self.role_field_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        schema = self.store.load_role_schema(name)
        fields = schema.get("fields", [])
        fd = self._open_field_def_dialog(fields[idx])
        if fd:
            fields[idx] = fd
            self.store.save_role_schema(name, schema)
            self._role_on_select()

    def _role_field_delete(self) -> None:
        name = self._role_selected_name()
        if not name:
            return
        sel = self.role_field_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        schema = self.store.load_role_schema(name)
        fields = schema.get("fields", [])
        if messagebox.askyesno("確認", f"フィールド「{fields[idx]['name']}」を削除しますか？", parent=self):
            del fields[idx]
            self.store.save_role_schema(name, schema)
            self._role_on_select()

    def _role_field_move(self, d: int) -> None:
        name = self._role_selected_name()
        if not name:
            return
        sel = self.role_field_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        schema = self.store.load_role_schema(name)
        fields = schema.get("fields", [])
        j = idx + d
        if 0 <= j < len(fields):
            fields[idx], fields[j] = fields[j], fields[idx]
            self.store.save_role_schema(name, schema)
            self._role_on_select()
            self.role_field_tree.selection_set(str(j))

    def _role_preview_form(self) -> None:
        name = self._role_selected_name()
        if not name:
            return
        schema = self.store.load_role_schema(name)
        values = open_role_call_form(self, self, name, schema)
        if values is not None:
            line = build_role_call_line_from_values(self.store, name, schema, values)
            messagebox.showinfo("生成されるDSL行(プレビュー)", line, parent=self)

    # ==================================================================
    # タブ: トランザクション(DSL) — どのイベント/サブイベントのDSLかを
    #        必ず選択式で指定してから編集する。予測変換はscenarioTransactionDsl.js
    #        のgetCompletionsAtを移植したカスケード(Role名→未使用フィールド名→
    #        bool/enum/class_data_idの値)で行う。
    # ==================================================================
    def _build_dsl_tab(self, parent: tk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(header, text="トランザクション (DSL)", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="  Role名 → フィールド名 → 値 の順にCtrl+Spaceで予測変換", style="Muted.TLabel").pack(side=tk.LEFT)

        sel_row = tk.Frame(parent, bg=C["bg"])
        sel_row.pack(fill=tk.X, padx=16, pady=(0, 6))
        tk.Label(sel_row, text="イベント:", bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self.dsl_event_var = tk.StringVar()
        self.dsl_event_combo = ttk.Combobox(sel_row, textvariable=self.dsl_event_var, state="readonly", width=30)
        self.dsl_event_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.dsl_event_combo.bind("<<ComboboxSelected>>", lambda e: self._dsl_on_event_selected())

        tk.Label(sel_row, text="サブイベント:", bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self.dsl_sub_var = tk.StringVar()
        self.dsl_sub_combo = ttk.Combobox(sel_row, textvariable=self.dsl_sub_var, state="readonly", width=30)
        self.dsl_sub_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.dsl_sub_combo.bind("<<ComboboxSelected>>", lambda e: self._dsl_on_sub_selected())

        self._btn(sel_row, "読込", self._dsl_load, accent=True).pack(side=tk.LEFT, padx=2)
        self._btn(sel_row, "保存 (Ctrl+S)", self._dsl_save, accent=True).pack(side=tk.LEFT, padx=2)
        self.dsl_status_label = ttk.Label(sel_row, text="", style="Muted.TLabel")
        self.dsl_status_label.pack(side=tk.LEFT, padx=8)

        tools = tk.Frame(parent, bg=C["bg"])
        tools.pack(fill=tk.X, padx=16, pady=(0, 6))
        self._btn(tools, "ロールを挿入(選択)…", self._dsl_insert_role, accent=True).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "選択行をフォームで編集…", self._dsl_edit_current_line_as_form).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "新しいグループ見出し", lambda: self._dsl_insert_text_at_cursor("# ==== GROUP ====\n")).pack(side=tk.LEFT, padx=(12, 2))
        ttk.Label(tools, text="  (Ctrl+Space: 予測変換 / ダブルクリック: 行をフォームで編集)", style="Muted.TLabel").pack(side=tk.LEFT, padx=8)

        text_wrap = tk.Frame(parent, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        text_wrap.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)
        self.dsl_text = tk.Text(
            text_wrap, wrap=tk.NONE, bg=C["input_bg"], fg=C["text"], insertbackground=C["accent"],
            selectbackground=C["list_sel"], font=("Consolas", 11), relief=tk.FLAT,
            highlightthickness=0, padx=10, pady=10, undo=True,
        )
        dsb = ttk.Scrollbar(text_wrap, orient=tk.VERTICAL, command=self.dsl_text.yview)
        hsb = ttk.Scrollbar(text_wrap, orient=tk.HORIZONTAL, command=self.dsl_text.xview)
        self.dsl_text.configure(yscrollcommand=dsb.set, xscrollcommand=hsb.set)
        self.dsl_text.grid(row=0, column=0, sticky="nsew")
        dsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        text_wrap.rowconfigure(0, weight=1)
        text_wrap.columnconfigure(0, weight=1)

        self.dsl_text.tag_configure("comment", foreground="#6a9955")
        self.dsl_text.tag_configure("string", foreground="#ce9178")
        self.dsl_text.tag_configure("number", foreground="#b5cea8")
        self.dsl_text.tag_configure("role", foreground="#4fc1ff", font=("Consolas", 11, "bold"))
        self.dsl_text.tag_configure("field", foreground="#c586c0")
        self.dsl_text.tag_configure("punct", foreground=C["text_muted"])

        self.dsl_text.bind("<KeyRelease>", self._dsl_on_keyrelease)
        self.dsl_text.bind("<Control-space>", self._dsl_on_ctrl_space)
        self.dsl_text.bind("<Control-Key-space>", self._dsl_on_ctrl_space)
        self.dsl_text.bind("<Double-Button-1>", lambda e: self._dsl_edit_current_line_as_form())
        self.dsl_text.bind("<Control-s>", lambda e: (self._dsl_save(), "break"))

        self._dsl_refresh_selectors()

    # -- イベント/サブイベント選択の同期 -----------------------------------
    def _event_label_for(self, event_id: str) -> str:
        events = self.store.load_events()
        ev = next((e for e in events if str(e["id"]) == str(event_id)), None)
        return f"{event_id}: {ev['name']}" if ev else str(event_id)

    def _event_sub_label_for(self, event_id: str, sub_id: str) -> str:
        events = self.store.load_events()
        ev = next((e for e in events if str(e["id"]) == str(event_id)), None)
        sub = next((s for s in (ev.get("subEvents", []) if ev else []) if str(s["subId"]) == str(sub_id)), None)
        return f"{sub_id}: {sub['name']}" if sub else str(sub_id)

    def _dsl_refresh_selectors(self) -> None:
        if not hasattr(self, "dsl_event_combo"):
            return
        events = self.store.load_events()
        self._dsl_events_cache = events
        labels = [f"{e['id']}: {e['name']}" for e in events]
        self.dsl_event_combo.configure(values=labels)
        if labels and self.dsl_event_var.get() not in labels:
            self.dsl_event_var.set(labels[0])
        if labels:
            self._dsl_on_event_selected()

    def _dsl_on_event_selected(self) -> None:
        label = self.dsl_event_var.get()
        if not label:
            self.dsl_sub_combo.configure(values=[])
            self.dsl_sub_var.set("")
            return
        event_id = label.split(":", 1)[0].strip()
        ev = next((e for e in self._dsl_events_cache if str(e["id"]) == event_id), None)
        subs = ev.get("subEvents", []) if ev else []
        labels = [f"{s['subId']}: {s['name']}" for s in subs]
        self.dsl_sub_combo.configure(values=labels)
        if labels:
            self.dsl_sub_var.set(labels[0])
            self._dsl_on_sub_selected()
        else:
            self.dsl_sub_var.set("")
            self.dsl_text.delete("1.0", tk.END)

    def _dsl_on_sub_selected(self) -> None:
        self._dsl_load()

    def _dsl_current_ids(self) -> Tuple[Optional[str], Optional[str]]:
        ev_label, sub_label = self.dsl_event_var.get(), self.dsl_sub_var.get()
        if not ev_label or not sub_label:
            return None, None
        return ev_label.split(":", 1)[0].strip(), sub_label.split(":", 1)[0].strip()

    # -- 読込/保存 -----------------------------------------------------------
    def _dsl_load(self) -> None:
        event_id, sub_id = self._dsl_current_ids()
        if event_id is None:
            return
        self._dsl_current_event_id, self._dsl_current_sub_id = event_id, sub_id
        text = self.store.load_transaction_text(event_id, sub_id)
        self.dsl_text.delete("1.0", tk.END)
        self.dsl_text.insert("1.0", text)
        self._dsl_highlight_all()
        self._dsl_dirty = False
        self.dsl_status_label.configure(text=f"読込済み: event {event_id} / sub {sub_id}")

    def _dsl_save(self) -> None:
        if self._dsl_current_event_id is None:
            messagebox.showinfo("未選択", "イベント/サブイベントを選択してください。", parent=self)
            return
        text = self.dsl_text.get("1.0", "end-1c")
        self.store.save_transaction_text(self._dsl_current_event_id, self._dsl_current_sub_id, text)
        self._dsl_dirty = False
        self.dsl_status_label.configure(text=f"保存しました: event {self._dsl_current_event_id} / sub {self._dsl_current_sub_id}")

    # -- シンタックスハイライト (tokenizeLineを利用) --------------------------
    def _dsl_highlight_line(self, line_index: int) -> None:
        line_start = f"{line_index}.0"
        line_end = f"{line_index}.end"
        line_text = self.dsl_text.get(line_start, line_end)
        for tag in ("comment", "string", "number", "role", "field", "punct"):
            self.dsl_text.tag_remove(tag, line_start, line_end)
        tokens = tokenize_line(line_text)
        for i, tok in enumerate(tokens):
            frm, to = f"{line_index}.{tok['from']}", f"{line_index}.{tok['to']}"
            if tok["type"] == "COMMENT":
                self.dsl_text.tag_add("comment", frm, to)
            elif tok["type"] == "STRING":
                self.dsl_text.tag_add("string", frm, to)
            elif tok["type"] == "NUMBER":
                self.dsl_text.tag_add("number", frm, to)
            elif tok["type"] in ("LPAREN", "RPAREN", "LBRACKET", "RBRACKET", "LBRACE", "RBRACE", "COMMA", "COLON", "EQUALS"):
                self.dsl_text.tag_add("punct", frm, to)
            elif tok["type"] == "IDENT":
                if i == 0:
                    self.dsl_text.tag_add("role", frm, to)
                elif i + 1 < len(tokens) and tokens[i + 1]["type"] == "EQUALS":
                    self.dsl_text.tag_add("field", frm, to)

    def _dsl_highlight_all(self) -> None:
        n = int(self.dsl_text.index("end-1c").split(".")[0])
        for i in range(1, n + 1):
            self._dsl_highlight_line(i)

    def _dsl_on_keyrelease(self, event) -> None:
        self._dsl_dirty = True
        if event.keysym in ("space", "Control_L", "Control_R"):
            return
        line_index = int(self.dsl_text.index(tk.INSERT).split(".")[0])
        self._dsl_highlight_line(line_index)

    # -- 予測変換 (Ctrl+Space): Role名 → 未使用フィールド名 → 値 のカスケード --
    def _dsl_on_ctrl_space(self, event) -> str:
        line_index_str = self.dsl_text.index(tk.INSERT)
        line_no, cursor_ch = (int(x) for x in line_index_str.split("."))
        line_text = self.dsl_text.get(f"{line_no}.0", f"{line_no}.end")
        role_names = self.store.role_names()
        items = get_completions_at(self.store, line_text, cursor_ch, role_names)
        self._dsl_show_popup(items, line_no, cursor_ch, line_text)
        return "break"

    def _dsl_show_popup(self, items: List[dict], line_no: int, cursor_ch: int, line_text: str) -> None:
        self._dsl_close_popup()
        if not items:
            return
        self._dsl_popup_items = items
        self._dsl_popup_line = line_no
        self._dsl_popup_cursor = cursor_ch
        self._dsl_popup_line_text = line_text
        bbox = self.dsl_text.bbox(f"{line_no}.{cursor_ch}")
        x = self.dsl_text.winfo_rootx() + (bbox[0] if bbox else 0)
        y = self.dsl_text.winfo_rooty() + (bbox[1] + bbox[3] if bbox else 0)
        win = tk.Toplevel(self)
        win.wm_overrideredirect(True)
        win.geometry(f"+{x}+{y}")
        lb = tk.Listbox(win, bg=C["surface2"], fg=C["text"], selectbackground=C["list_sel"], height=min(8, len(items)))
        for it in items:
            detail = f"  ({it['detail']})" if it.get("detail") else ""
            lb.insert(tk.END, it["label"] + detail)
        lb.selection_set(0)
        lb.pack()
        lb.bind("<Return>", lambda e: self._dsl_confirm_popup(lb))
        lb.bind("<Double-Button-1>", lambda e: self._dsl_confirm_popup(lb))
        lb.bind("<Escape>", lambda e: self._dsl_close_popup())
        lb.focus_set()
        self._dsl_popup = win
        self._dsl_popup_list = lb

    def _dsl_confirm_popup(self, lb: tk.Listbox) -> None:
        sel = lb.curselection()
        if not sel:
            self._dsl_close_popup()
            return
        item = self._dsl_popup_items[sel[0]]
        insert_text = item.get("insertText", item["label"])
        line_no, cursor_ch = self._dsl_popup_line, self._dsl_popup_cursor
        # 編集中の単語(直前のIDENT/一部)を、確定候補で置き換える
        before = self._dsl_popup_line_text[:cursor_ch]
        m = re.search(r'[A-Za-z0-9_.]*$', before)
        word_start = cursor_ch - (len(m.group(0)) if m else 0)
        self.dsl_text.delete(f"{line_no}.{word_start}", f"{line_no}.{cursor_ch}")
        self.dsl_text.insert(f"{line_no}.{word_start}", insert_text)
        self._dsl_close_popup()
        self._dsl_highlight_line(line_no)
        self.dsl_text.mark_set(tk.INSERT, f"{line_no}.{word_start + len(insert_text)}")
        self.dsl_text.focus_set()

    def _dsl_close_popup(self) -> None:
        if self._dsl_popup is not None:
            try:
                self._dsl_popup.destroy()
            except Exception:
                pass
        self._dsl_popup = None
        self._dsl_popup_list = None

    # -- ロールを選択して挿入(自由入力ではなく _pick_role_name で選ぶ) --------
    def _dsl_insert_role(self) -> None:
        role_name = self._pick_role_name("挿入するロールを選択")
        if not role_name:
            return
        schema = self.store.load_role_schema(role_name)
        line = build_role_call_line(self.store, role_name, schema)
        self._dsl_insert_text_at_cursor(line + "\n")

    def _dsl_insert_text_at_cursor(self, text: str) -> None:
        self.dsl_text.insert(tk.INSERT, text)
        self._dsl_highlight_all()
        self._dsl_dirty = True

    # -- 現在行をフォーム(型ごとの入力UI)で編集 -------------------------------
    def _dsl_edit_current_line_as_form(self) -> None:
        line_no = int(self.dsl_text.index(tk.INSERT).split(".")[0])
        line_text = self.dsl_text.get(f"{line_no}.0", f"{line_no}.end")
        parsed = parse_line(line_text, 0)
        if parsed["type"] != "call" or not parsed["name"]:
            messagebox.showinfo("この行は編集できません", "カーソルを `RoleName field=value ...` の行に置いてください。", parent=self)
            return
        role_name = parsed["name"]
        if role_name not in self.store.role_names():
            messagebox.showwarning("未登録のロール", f"ロール「{role_name}」は登録されていません。", parent=self)
            return
        schema = self.store.load_role_schema(role_name)
        _, values = parse_call_line_values(self.store, line_text, schema)
        new_values = open_role_call_form(self, self, role_name, schema, values)
        if new_values is None:
            return
        new_line = build_role_call_line_from_values(self.store, role_name, schema, new_values)
        self.dsl_text.delete(f"{line_no}.0", f"{line_no}.end")
        self.dsl_text.insert(f"{line_no}.0", new_line)
        self._dsl_highlight_line(line_no)
        self._dsl_dirty = True

    def _labeled_combo(self, parent, label, key, width=18):
        box = tk.Frame(parent, bg=C["bg"])
        box.pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(box, text=label, bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 8)).pack(anchor=tk.W)
        var = tk.StringVar()
        combo = ttk.Combobox(box, textvariable=var, width=width, state="readonly")
        combo.pack()
        combo.bind("<<ComboboxSelected>>", lambda e: self._reload_list())
        setattr(self, f"{key}_var", var)
        setattr(self, f"{key}_combo", combo)

    def _labeled_entry(self, parent, label, key, default="", width=12):
        box = tk.Frame(parent, bg=C["bg"])
        box.pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(box, text=label, bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 8)).pack(anchor=tk.W)
        var = tk.StringVar(value=default)
        entry = tk.Entry(
            box,
            textvariable=var,
            width=width,
            bg=C["input_bg"],
            fg=C["text"],
            insertbackground=C["text"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
            font=("Segoe UI", 10),
        )
        entry.pack(ipady=3)
        setattr(self, f"{key}_var", var)

    # -- 設定の保持 ---------------------------------------------------------
    def _remember(self) -> None:
        # 設定ファイルへの保存は、この実行環境（SCRIPT_DIR）からの相対パスにする。
        # プロジェクト一式（exe含む）をまるごと別の場所へ移しても設定が有効なままになる。
        if self.path:
            rel = to_relative_path(self.path)
            self.settings["last_matrix_path"] = rel
            recents: List[str] = [p for p in (self.settings.get("recent_paths") or []) if p != rel]
            recents.insert(0, rel)
            self.settings["recent_paths"] = recents[:12]
        self.settings["last_row"] = self.row_var.get()
        self.settings["last_col"] = self.col_var.get()
        self.settings["last_field"] = self.field_var.get() or "texts"
        self.settings["tags_path"] = to_relative_path(self.tags_path)
        try:
            self.settings["geometry"] = self.winfo_geometry()
        except tk.TclError:
            pass
        save_settings(self.settings)
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        stored = self.settings.get("recent_paths") or []
        valid_stored = [p for p in stored if os.path.isfile(from_stored_path(p))]
        self.settings["recent_paths"] = valid_stored
        abs_list = [from_stored_path(p) for p in valid_stored]
        self.recent_combo["values"] = abs_list
        if self.path and self.path in abs_list:
            self.recent_var.set(self.path)

    def _on_recent_selected(self, _e=None) -> None:
        p = self.recent_var.get()  # コンボには絶対パスを表示している
        if p and os.path.isfile(p) and p != self.path:
            self._open_path(p)

    # -- ファイル操作 -------------------------------------------------------
    def open_file(self) -> None:
        initial = os.path.dirname(self.path) if self.path else os.getcwd()
        path = filedialog.askopenfilename(
            title="Matrix JSON を開く",
            initialdir=initial,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._open_path(path)

    def _open_from_entry(self) -> None:
        path = self.path_var.get().strip().strip('"')
        if path and os.path.isfile(path):
            self._open_path(path)
        elif path:
            messagebox.showerror("エラー", f"ファイルが見つかりません:\n{path}")

    def _open_path(self, path: str, restore: Optional[Dict[str, str]] = None) -> None:
        try:
            self.matrix = load_matrix(path)
            self.path = os.path.abspath(path)
            self.path_var.set(self.path)
            self._refresh_combos(restore)
            self._dirty = False
            self._remember()
            self._set_status(f"読込完了  ·  {self.path}")
        except Exception as e:
            messagebox.showerror("読込エラー", str(e))

    def reload_current(self) -> None:
        if self.path and os.path.isfile(self.path):
            if self._dirty and not messagebox.askyesno("確認", "未保存の変更があります。再読込しますか？"):
                return
            self._open_path(
                self.path,
                restore={"row": self.row_var.get(), "col": self.col_var.get(), "field": self.field_var.get()},
            )
        else:
            self.open_file()

    def save_file(self) -> None:
        if not self.matrix:
            return
        if not self.path:
            self.save_as()
            return
        self._flush_current_cell()
        try:
            save_matrix(self.path, self.matrix)
            self.comments_store.save()
            self._dirty = False
            self._remember()
            self._set_status(f"保存しました  ·  {self.path}")
        except Exception as e:
            messagebox.showerror("保存エラー", str(e))

    def save_as(self) -> None:
        if not self.matrix:
            return
        initial = os.path.dirname(self.path) if self.path else os.getcwd()
        path = filedialog.asksaveasfilename(
            title="別名で保存",
            initialdir=initial,
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            self.path = os.path.abspath(path)
            self.path_var.set(self.path)
            self.save_file()

    def _on_close(self) -> None:
        if self._dirty and not messagebox.askyesno("確認", "未保存の変更があります。終了しますか？"):
            return
        self._flush_current_cell(mark_dirty=False)
        self.comments_store.save()
        self._remember()
        self.destroy()

    # -- セル操作 -----------------------------------------------------------
    def _refresh_combos(self, restore: Optional[Dict[str, str]] = None) -> None:
        if not self.matrix:
            return
        restore = restore or {}
        rows = list_row_keys(self.matrix)
        self.row_combo["values"] = rows
        if rows:
            want = restore.get("row")
            if want in rows:
                self.row_var.set(want)
            else:
                preferred = next(
                    (r for r in rows if normalize_row_key(r).lower() in ("ja", "jp", "japanese")),
                    rows[0],
                )
                self.row_var.set(preferred)
        cols = list_col_keys(self.matrix, self.row_var.get() or None)
        self.col_combo["values"] = cols
        if cols:
            want = restore.get("col")
            self.col_var.set(want if want in cols else cols[0])
        fields = [f.get("name") for f in (self.matrix.get("fields") or []) if f.get("name")]
        want_field = restore.get("field")
        if want_field:
            self.field_var.set(want_field)
        elif fields and self.field_var.get() not in fields:
            self.field_var.set(fields[0])
        self._reload_list()

    def _current_keys(self) -> Tuple[str, str, str]:
        return self.row_var.get(), self.col_var.get(), self.field_var.get() or "texts"

    def _reload_list(self) -> None:
        if not self.matrix:
            return
        # 直前に self._items へ読み込んでいた「実際のセル」に対してのみ書き戻す。
        # コンボボックスは既に新しいセルを指している場合があるため、
        # _current_keys() (= 表示先) をそのまま使うと新セルへ古い内容を
        # 上書きしてしまう（初回読込時は空リストで潰れる、列切替時は
        # 前の列の内容が新しい列にコピーされる、というバグの原因だった）。
        self._flush_loaded_cell(mark_dirty=False)
        row = self.row_var.get()
        cols = list_col_keys(self.matrix, row or None)
        self.col_combo["values"] = cols
        if self.col_var.get() not in cols and cols:
            self.col_var.set(cols[0])
        row, col, field = self._current_keys()
        self._items = get_cell_list(self.matrix, row, col, field) if row and col else []
        self._comments = self.comments_store.get(self.path, row, col, field, len(self._items))
        self._loaded_keys = (row, col, field)
        self._redraw_listbox()
        self.editor.delete("1.0", tk.END)
        self.comment_box.delete("1.0", tk.END)
        n_cmt = sum(1 for c in self._comments if c.strip())
        self._set_status(f"{row}  /  {col}  /  {field}  —  {len(self._items)} 件（コメント {n_cmt} 件）")
        self._remember()

    def _redraw_listbox(self, select: Optional[int] = None) -> None:
        self.listbox.delete(0, tk.END)
        self._sync_comment_length()
        for i, text in enumerate(self._items):
            preview = text.replace("\n", "↵")
            if len(preview) > 80:
                preview = preview[:77] + "…"
            cmt = self._comments[i].strip().replace("\n", " ")
            mark = "●" if cmt else " "
            line = f" {mark} {i:4d} │ {preview}"
            if cmt:
                short = cmt if len(cmt) <= 40 else cmt[:37] + "…"
                line += f"   ⟨{short}⟩"
            self.listbox.insert(tk.END, line)
            if cmt:
                self.listbox.itemconfig(tk.END, foreground=C["comment"])
        if select is not None and 0 <= select < len(self._items):
            self.listbox.selection_set(select)
            self.listbox.see(select)
            self.listbox.activate(select)
        self._update_plus_button()

    def _sync_comment_length(self) -> None:
        if len(self._comments) < len(self._items):
            self._comments += [""] * (len(self._items) - len(self._comments))
        elif len(self._comments) > len(self._items):
            del self._comments[len(self._items):]

    def _selected_index(self) -> Optional[int]:
        sel = self.listbox.curselection()
        return int(sel[0]) if sel else None

    def _on_select(self, _event=None) -> None:
        idx = self._selected_index()
        self._update_plus_button()
        if idx is None or idx >= len(self._items):
            return
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", self._items[idx])
        self.comment_box.delete("1.0", tk.END)
        self.comment_box.insert("1.0", self._comments[idx])

    def _flush_loaded_cell(self, mark_dirty: bool = True) -> None:
        """self._items/self._comments を「実際に読み込んだセル」(_loaded_keys) へ書き戻す。"""
        if not self.matrix:
            return
        row, col, field = getattr(self, "_loaded_keys", (None, None, None))
        if row and col:
            set_cell_list(self.matrix, row, col, self._items, field)
            self._sync_comment_length()
            self.comments_store.set(self.path, row, col, field, self._comments)
            if mark_dirty:
                self._dirty = True

    def _flush_current_cell(self, mark_dirty: bool = True) -> None:
        """編集操作（追加・削除・並べ替え等）の直後に呼ぶ。
        この時点ではコンボボックスと _loaded_keys は一致しているはず。"""
        if not self.matrix:
            return
        row, col, field = self._current_keys()
        if row and col:
            set_cell_list(self.matrix, row, col, self._items, field)
            self._sync_comment_length()
            self.comments_store.set(self.path, row, col, field, self._comments)
            self._loaded_keys = (row, col, field)
            if mark_dirty:
                self._dirty = True

    # -- ＋ボタン -----------------------------------------------------------
    def _update_plus_button(self) -> None:
        idx = self._selected_index()
        if idx is None or not self._items:
            self.plus_btn.place_forget()
            return
        bbox = self.listbox.bbox(idx)
        if not bbox:
            self.plus_btn.place_forget()
            return
        _, by, _, bh = bbox
        h = max(16, bh)
        self.plus_btn.place(x=2, y=max(0, by - 1), width=22, height=h)

    def _show_add_menu(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=C["surface2"],
            fg=C["text"],
            activebackground=C["accent"],
            activeforeground="#ffffff",
            bd=0,
        )
        menu.add_command(label=f"#{idx} の上に追加", command=lambda: self.add_relative(-1))
        menu.add_command(label=f"#{idx} の下に追加", command=lambda: self.add_relative(1))
        menu.add_separator()
        menu.add_command(label="この行を複製", command=self.duplicate_item)
        menu.add_command(label="この行を削除", command=self.delete_item)
        try:
            x = self.plus_btn.winfo_rootx()
            y = self.plus_btn.winfo_rooty() + self.plus_btn.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _on_list_right_click(self, event):
        idx = self.listbox.nearest(event.y)
        if 0 <= idx < len(self._items):
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(idx)
            self.listbox.activate(idx)
            self._on_select()
            self._show_add_menu()

    # -- 配列編集 -----------------------------------------------------------
    def _insert_row(self, pos: int, text: str = "", comment: str = "") -> None:
        pos = max(0, min(pos, len(self._items)))
        self._items.insert(pos, text)
        self._sync_comment_length()
        self._comments.insert(pos, comment)
        self._flush_current_cell()
        self._redraw_listbox(select=pos)
        self._on_select()
        self.editor.focus_set()

    def add_relative(self, direction: int) -> None:
        """direction: -1 = 選択行の上、 +1 = 選択行の下"""
        idx = self._selected_index()
        if idx is None:
            self.append_item()
            return
        pos = idx if direction < 0 else idx + 1
        self._insert_row(pos)
        self._set_status(f"追加: 位置 #{pos}（{'上' if direction < 0 else '下'}）")

    def insert_at_index(self) -> None:
        pos = ask_insert_index(self, len(self._items), title="配列への位置指定挿入")
        if pos is None:
            return
        self._insert_row(pos)
        self._set_status(f"挿入: 位置 #{pos}")

    def append_item(self) -> None:
        self._insert_row(len(self._items))

    def delete_item(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        del self._items[idx]
        self._sync_comment_length()
        if idx < len(self._comments):
            del self._comments[idx]
        self._flush_current_cell()
        new_sel = min(idx, len(self._items) - 1) if self._items else None
        self._redraw_listbox(select=new_sel)
        self.editor.delete("1.0", tk.END)
        self.comment_box.delete("1.0", tk.END)
        if new_sel is not None:
            self._on_select()

    def duplicate_item(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self._insert_row(idx + 1, self._items[idx], self._comments[idx])

    def apply_editor(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("情報", "左のリストから行を選択してください")
            return
        self._items[idx] = self.editor.get("1.0", "end-1c")
        self._sync_comment_length()
        self._comments[idx] = self.comment_box.get("1.0", "end-1c")
        self._flush_current_cell()
        self._redraw_listbox(select=idx)
        self._set_status(f"#{idx} を更新")

    def apply_comment(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self._sync_comment_length()
        self._comments[idx] = self.comment_box.get("1.0", "end-1c")
        self._flush_current_cell()
        self._redraw_listbox(select=idx)
        self._set_status(f"#{idx} のコメントを更新")

    def clear_comment(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self._sync_comment_length()
        self._comments[idx] = ""
        self.comment_box.delete("1.0", tk.END)
        self._flush_current_cell()
        self._redraw_listbox(select=idx)
        self._set_status(f"#{idx} のコメントを削除")

    def move_up(self) -> None:
        idx = self._selected_index()
        if idx is None or idx <= 0:
            return
        self._reorder_array(idx, idx - 1)

    def move_down(self) -> None:
        idx = self._selected_index()
        if idx is None or idx >= len(self._items) - 1:
            return
        self._reorder_array(idx, idx + 1)

    def _reorder_array(self, frm: int, to: int) -> None:
        """DnD / 上下移動: 配列要素を from → to へ移動（コメントも一緒に動く）。"""
        if frm < 0 or to < 0 or frm >= len(self._items) or to >= len(self._items) or frm == to:
            return
        self._sync_comment_length()
        item = self._items.pop(frm)
        cmt = self._comments.pop(frm)
        self._items.insert(to, item)
        self._comments.insert(to, cmt)
        self._flush_current_cell()
        self._redraw_listbox(select=to)
        self._on_select()
        self._set_status(f"移動: #{frm} → #{to}")

    def swap_items(self) -> None:
        if len(self._items) < 2:
            messagebox.showinfo("情報", "入れ替える要素が2件以上必要です")
            return
        pair = ask_swap_indices(self, len(self._items) - 1, title="配列の入れ替え")
        if not pair:
            return
        a, b = pair
        self._sync_comment_length()
        self._items[a], self._items[b] = self._items[b], self._items[a]
        self._comments[a], self._comments[b] = self._comments[b], self._comments[a]
        self._flush_current_cell()
        self._redraw_listbox(select=b)
        self._on_select()
        self._set_status(f"入れ替え: #{a} ⟷ #{b}")

    # -- テキスト I/O -------------------------------------------------------
    def import_text(self) -> None:
        initial = os.path.dirname(self.path) if self.path else os.getcwd()
        path = filedialog.askopenfilename(
            title="テキスト取込（1行1レコード・空行は無視）",
            initialdir=initial,
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except UnicodeDecodeError:
            try:
                with open(path, "r", encoding="cp932") as f:
                    raw = f.read()
            except Exception as e:
                messagebox.showerror("読込エラー", str(e))
                return
        except Exception as e:
            messagebox.showerror("読込エラー", str(e))
            return

        # 空白のみの行 / 空行は取り込まない。先頭が空白（全角スペース含む）の場合は詰める。
        lines: List[str] = []
        skipped = 0
        for ln in raw.splitlines():
            s = ln.rstrip()
            if not s.strip():
                skipped += 1
                continue
            if s[:1] in (" ", "\t", "\u3000"):
                s = s.lstrip(" \t\u3000")
            lines.append(s)
        if not lines:
            messagebox.showinfo("情報", "取り込める行がありませんでした（すべて空行）")
            return

        mode = messagebox.askyesnocancel(
            "インポート方式",
            "はい = 末尾に追加\nいいえ = 現在の配列を置き換え\nキャンセル = 中止",
        )
        if mode is None:
            return
        self._sync_comment_length()
        if mode:
            self._items = self._items + lines
            self._comments = self._comments + [""] * len(lines)
        else:
            self._items = lines
            self._comments = [""] * len(lines)
        self._flush_current_cell()
        self._redraw_listbox(select=len(self._items) - 1 if self._items else None)
        self._on_select()
        self._set_status(f"テキストから {len(lines)} 件取り込み（空行 {skipped} 行をスキップ）")

    def export_text(self) -> None:
        initial = os.path.dirname(self.path) if self.path else os.getcwd()
        path = filedialog.asksaveasfilename(
            title="テキスト出力",
            initialdir=initial,
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
        )
        if not path:
            return
        with_comments = messagebox.askyesno(
            "出力オプション",
            "コメントも一緒に出力しますか？\n（はい = 「本文\\t# コメント」形式 / いいえ = 本文のみ）",
        )
        try:
            with open(path, "w", encoding="utf-8") as f:
                for i, line in enumerate(self._items):
                    cmt = self._comments[i].replace("\n", " ") if i < len(self._comments) else ""
                    if with_comments and cmt.strip():
                        f.write(f"{line}\t# {cmt}\n")
                    else:
                        f.write(f"{line}\n")
            self._set_status(f"出力: {path}  ({len(self._items)} 件)")
        except Exception as e:
            messagebox.showerror("書出エラー", str(e))

    def preview_all(self) -> None:
        win = tk.Toplevel(self)
        win.title("全文プレビュー")
        win.geometry("760x560")
        win.configure(bg=C["bg"])
        txt = tk.Text(win, wrap=tk.WORD, bg=C["input_bg"], fg=C["text"], font=("Consolas", 11), relief=tk.FLAT, padx=12, pady=12)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.tag_configure("cmt", foreground=C["comment"])
        for i, line in enumerate(self._items):
            txt.insert(tk.END, f"[{i}] {line}\n")
            cmt = self._comments[i].strip() if i < len(self._comments) else ""
            if cmt:
                txt.insert(tk.END, f"      # {cmt}\n", "cmt")
        txt.configure(state=tk.DISABLED)

    # -- 翻訳 ---------------------------------------------------------------
    def open_translate_dialog(self) -> None:
        """翻訳ダイアログを開く。実行はバックグラウンドスレッドで行い、
        進捗バー（％表示）とキャンセルボタン付きのダイアログを出す。"""
        if not self.matrix:
            return
        if not ensure_translator_available():
            messagebox.showerror(
                "翻訳エンジンが利用できません",
                "翻訳機能を使うには 'deep-translator' パッケージと、\n"
                "インターネット経由でのHTTPS通信が必要です。\n\n"
                f"詳細: {_TRANSLATOR_IMPORT_ERROR}\n\n"
                "exe化している場合によくある原因:\n"
                "  ・PyInstaller のビルドに deep_translator が同梱されていない\n"
                "    （--hidden-import=deep_translator や --collect-all=deep_translator を検討）\n"
                "  ・certifi の証明書ファイル (cacert.pem) が同梱されていない\n"
                "  ・実行環境から translate.google.com へ到達できない\n"
                "    （社内ネットワークやプロキシ設定の可能性）",
            )
            return

        row, col, field = self._current_keys()
        if not row or not col:
            messagebox.showwarning("翻訳", "行と列を選択してください")
            return

        # 現在編集中のセルの内容を確実に反映してから翻訳元を読む
        self._flush_loaded_cell(mark_dirty=True)

        rows = list_row_keys(self.matrix)
        dlg = TranslateOptionsDialog(self, rows, row, col, field)
        self.wait_window(dlg)
        opts = dlg.result
        if not opts:
            return

        src_list = get_cell_list(self.matrix, opts["src_row"], col, field)
        if not src_list:
            messagebox.showinfo("翻訳", "元の行にテキストがありません")
            return

        if not messagebox.askyesno(
            "翻訳確認",
            f"{opts['src_row']} → {opts['dst_row']}\n"
            f"列: {col}\n{len(src_list)} 件を翻訳します。\n"
            "（Text Animator タグは翻訳しません）\n続行しますか？",
        ):
            return

        self._start_translation_job(opts, col, field, src_list)

    def _start_translation_job(self, opts: dict, col: str, field: str, src_list: List[str]) -> None:
        total = len(src_list)
        progress = ProgressDialog(self, "翻訳中…", total)
        q: "queue.Queue" = queue.Queue()
        cancel_event = threading.Event()

        def worker() -> None:
            try:
                from deep_translator import GoogleTranslator  # type: ignore

                translator = GoogleTranslator(source=opts["src_lang"] or "auto", target=opts["dst_lang"])
            except Exception as e:
                q.put(("error", str(e)))
                return
            results: List[str] = []
            fail_count = 0
            # Google の無料エンドポイントは 5 req/秒までしか許容しないため、
            # 1件ごとに間隔を空けて余裕を持たせる（既定 0.4 秒 ≒ 最大 2.5 req/秒）。
            min_interval = 0.4
            max_retries = 4
            last_call = 0.0
            for i, text in enumerate(src_list):
                if cancel_event.is_set():
                    q.put(("cancelled", i, results, fail_count))
                    return

                out = text
                attempt = 0
                while True:
                    if cancel_event.is_set():
                        q.put(("cancelled", i, results, fail_count))
                        return
                    wait = min_interval - (time.monotonic() - last_call)
                    if wait > 0:
                        time.sleep(wait)
                    last_call = time.monotonic()
                    try:
                        out = translate_text(text, translator)
                        break
                    except Exception as e:
                        if _is_rate_limit_error(e) and attempt < max_retries:
                            attempt += 1
                            backoff = min(2.0 * attempt, 8.0)
                            q.put(("progress", i, total, f"レート制限のため {backoff:.0f} 秒待機中…（再試行 {attempt}/{max_retries}）"))
                            time.sleep(backoff)
                            continue
                        out = text
                        fail_count += 1
                        print(f"[translate] #{i} failed: {e}", file=sys.stderr)
                        break

                results.append(out)
                preview = text if len(text) <= 28 else text[:25] + "…"
                q.put(("progress", i + 1, total, f"翻訳中… {preview}"))
            q.put(("done", results, fail_count))

        threading.Thread(target=worker, daemon=True).start()

        def poll() -> None:
            try:
                while True:
                    item = q.get_nowait()
                    kind = item[0]
                    if kind == "progress":
                        _, done, tot, text = item
                        progress.update_progress(done, tot, text)
                    elif kind == "error":
                        progress.destroy()
                        messagebox.showerror("翻訳エラー", item[1])
                        return
                    elif kind == "cancelled":
                        _, done, results, fail_count = item
                        progress.destroy()
                        self._apply_translation_results(opts, col, field, results, fail_count, cancelled=True, done=done, total=total)
                        return
                    elif kind == "done":
                        _, results, fail_count = item
                        progress.destroy()
                        self._apply_translation_results(opts, col, field, results, fail_count, cancelled=False, done=total, total=total)
                        return
            except queue.Empty:
                pass
            if progress.cancelled and not cancel_event.is_set():
                cancel_event.set()
            if progress.winfo_exists():
                self.after(80, poll)

        self.after(80, poll)

    def _apply_translation_results(
        self, opts: dict, col: str, field: str, results: List[str], fail_count: int,
        cancelled: bool, done: int, total: int,
    ) -> None:
        dst_row = opts["dst_row"]
        self.matrix.setdefault("data", {}).setdefault(dst_row, {})
        existing = get_cell_list(self.matrix, dst_row, col, field)
        merged = list(results) if opts["mode"] == "replace" else existing + results
        set_cell_list(self.matrix, dst_row, col, merged, field)
        self._dirty = True
        self.row_var.set(dst_row)
        self._refresh_combos({"row": dst_row, "col": col, "field": field})

        msg = f"翻訳完了: {done}/{total} 件を {dst_row} に反映"
        if fail_count:
            msg += f"（失敗 {fail_count} 件は元の文言のまま）"
        if cancelled:
            msg += "（キャンセル：途中まで反映）"
        self._set_status(msg)
        if fail_count and not cancelled:
            messagebox.showwarning(
                "翻訳",
                f"{fail_count} 件は翻訳に失敗し、元のテキストのまま反映されました。\n"
                "ネットワーク状況や文字数制限などをご確認ください。",
            )


    # -- タグ定義 -----------------------------------------------------------
    def open_tag_editor(self) -> None:
        """Text Animator タグ定義 JSON（自動生成済み）を開く。"""
        path = ensure_tag_file(self.tags_path)
        TagDefinitionEditor(self, initial_path=path, on_path_changed=self._on_tags_path_changed)

    def _on_tags_path_changed(self, new_path: str) -> None:
        self.tags_path = os.path.abspath(new_path)
        self.tag_config = _read_json(self.tags_path, DEFAULT_TAG_CONFIG)
        self._remember()

    def _set_status(self, msg: str) -> None:
        self.status.config(text=msg)

    # -- タグ補完・自動閉じ -------------------------------------------------
    def _get_all_behavior_tags(self) -> List[dict]:
        tags = self.tag_config.get("behavior_tags") or []
        return [t for t in tags if isinstance(t, dict) and t.get("id")]

    def _get_all_appearance_tags(self) -> List[dict]:
        tags = self.tag_config.get("appearance_tags") or []
        return [t for t in tags if isinstance(t, dict) and t.get("id")]

    def _find_open_tag_before_cursor(self) -> Optional[Tuple[str, str, int]]:
        """カーソル直前の未閉じ開始タグを探す。
        戻り値: (style, tag_id, open_start_char_offset)  style は 'angle' or 'brace'
        """
        try:
            idx = self.editor.index("insert")
            text = self.editor.get("1.0", idx)
        except tk.TclError:
            return None
        stack: List[Tuple[str, str, int]] = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "<":
                m = re.match(r"</([a-zA-Z0-9_#]+)[^>]*>", text[i:])
                if m:
                    tid = m.group(1)
                    for j in range(len(stack) - 1, -1, -1):
                        if stack[j][0] == "angle" and stack[j][1] == tid:
                            stack.pop(j)
                            break
                    i += m.end()
                    continue
                m = re.match(r"<([a-zA-Z0-9_#]+)([^>]*)>", text[i:])
                if m:
                    tid = m.group(1)
                    if not tid.startswith("/"):
                        stack.append(("angle", tid, i))
                    i += m.end()
                    continue
            elif ch == "{":
                m = re.match(r"\{/([a-zA-Z0-9_#]+)[^}]*\}", text[i:])
                if m:
                    tid = m.group(1)
                    for j in range(len(stack) - 1, -1, -1):
                        if stack[j][0] == "brace" and stack[j][1] == tid:
                            stack.pop(j)
                            break
                    i += m.end()
                    continue
                m = re.match(r"\{([a-zA-Z0-9_#]+)([^}]*)\}", text[i:])
                if m:
                    tid = m.group(1)
                    if not tid.startswith("/") and not tid.startswith("#"):
                        stack.append(("brace", tid, i))
                    i += m.end()
                    continue
            i += 1
        if stack:
            return stack[-1]
        return None

    def _on_slash_auto_close(self, event) -> Optional[str]:
        """`/` 入力時: 未閉じ開始タグがあれば対応する閉じタグを挿入する。
        例: <shake>AAA| で / → </shake>
        タグ内部（未完了の <...> 中）では通常の / のまま。
        """
        try:
            idx = self.editor.index("insert")
            before = self.editor.get("1.0", idx)
            last_lt = before.rfind("<")
            last_gt = before.rfind(">")
            last_lb = before.rfind("{")
            last_rb = before.rfind("}")
            inside_angle = last_lt > last_gt
            inside_brace = last_lb > last_rb
            if inside_angle or inside_brace:
                return None

            found = self._find_open_tag_before_cursor()
            if not found:
                return None
            style, tid, _ = found
            close = f"</{tid}>" if style == "angle" else f"{{/{tid}}}"
            self.editor.insert("insert", close)
            return "break"
        except Exception:
            return None

    def _cursor_context(self) -> Tuple[str, str, str, Optional[str]]:
        """カーソル位置の文脈を返す。
        戻り値: (mode, partial, tag_id, name_start_index)
          mode: 'param' | 'tag_angle' | 'tag_brace' | 'free'
          partial: 入力途中の文字列（タグ名 or パラメータ名）
          tag_id: param 時のタグ id
          name_start_index: tag_angle/tag_brace 時、タグ名の開始位置（Text index）。
            既存本文の途中で <sあいさつ… となっていても、タグ名部分だけを置換できるようにする。
        """
        try:
            idx = self.editor.index("insert")
            before = self.editor.get("1.0", idx)
        except tk.TclError:
            return ("free", "", "", None)

        last_lt = before.rfind("<")
        last_gt = before.rfind(">")
        last_lb = before.rfind("{")
        last_rb = before.rfind("}")

        # --- 未閉じ < ... の内部 ---
        if last_lt > last_gt:
            # before 内での文字オフセット → Text index に変換
            frag = before[last_lt + 1 :]
            m = re.match(r"^([a-zA-Z0-9_#]*)", frag)
            name_part = m.group(1) if m else ""
            after_name = frag[len(name_part) :]
            # タグ名の開始位置（< の次）
            name_start = self.editor.index(f"1.0 + {last_lt + 1}c")

            if after_name == "":
                # 純粋にタグ名の途中: <sha|
                return ("tag_angle", name_part, "", name_start)
            if after_name[0].isspace() or after_name[0] == "=":
                # パラメータ領域: <shake |  or <shake a=|
                pm = re.search(r"([a-zA-Z0-9_]*)$", before)
                partial = pm.group(1) if pm else ""
                return ("param", partial, name_part, None)
            # <sあいさつ… のようにタグ名の直後に本文が続いている
            # → タグ名補完として扱い、name_part だけを置換対象にする
            return ("tag_angle", name_part, "", name_start)

        # --- 未閉じ { ... の内部 ---
        if last_lb > last_rb:
            frag = before[last_lb + 1 :]
            m = re.match(r"^/?#?([a-zA-Z0-9_]*)", frag)
            name_part = m.group(1) if m else ""
            prefix_len = len(frag) - len(frag.lstrip("/#")) if frag else 0
            # 実際の id 開始位置
            name_start = self.editor.index(f"1.0 + {last_lb + 1 + prefix_len}c")
            after_name = frag[prefix_len + len(name_part) :] if m else frag

            if after_name == "" or after_name[0].isspace():
                if after_name == "":
                    return ("tag_brace", name_part, "", name_start)
                pm = re.search(r"([a-zA-Z0-9_]*)$", before)
                partial = pm.group(1) if pm else ""
                return ("param", partial, name_part, None)
            else:
                return ("tag_brace", name_part, "", name_start)

        # --- タグ外 ---
        # 直前が英数字なら partial に（英語本文の単語末尾）。日本語なら空。
        m = re.search(r"([a-zA-Z0-9_#]+)$", before)
        partial = m.group(1) if m else ""
        return ("free", partial, "", None)

    def _candidates_for_context(self, mode: str, partial: str, tag_id: str) -> List[Tuple[str, str]]:
        """(表示ラベル, 挿入文字列) のリスト。"""
        partial_l = partial.lower()
        out: List[Tuple[str, str]] = []
        help_map = self.tag_config.get("modifier_help") or {}

        if mode == "param":
            mods: List[str] = []
            for t in self._get_all_behavior_tags() + self._get_all_appearance_tags():
                if t.get("id") == tag_id:
                    mods = list(t.get("modifiers") or [])
                    break
            for m in mods:
                if partial_l and not m.lower().startswith(partial_l):
                    continue
                label = f"{m}  —  {help_map.get(m, '')}" if help_map.get(m) else m
                out.append((label, f"{m}="))
            return out

        if mode in ("tag_angle", "free"):
            for t in self._get_all_behavior_tags():
                tid = str(t.get("id", ""))
                lab = str(t.get("label", tid))
                if partial_l and not (tid.lower().startswith(partial_l) or lab.lower().startswith(partial_l)):
                    continue
                out.append((f"<{tid}>  {lab}", f"<{tid}>"))

        if mode in ("tag_brace", "free"):
            for t in self._get_all_appearance_tags():
                tid = str(t.get("id", ""))
                lab = str(t.get("label", tid))
                if partial_l and not (tid.lower().startswith(partial_l) or lab.lower().startswith(partial_l)):
                    continue
                op = t.get("open") or f"{{{tid}}}"
                out.append((f"{op}  {lab}", op))

        return out

    def _close_completion_popup(self) -> None:
        if self._completion_popup is not None:
            try:
                self._completion_popup.destroy()
            except tk.TclError:
                pass
            self._completion_popup = None

    def _on_editor_keypress(self, event) -> None:
        if self._completion_popup is None:
            return
        if event.keysym in ("Up", "Down", "Return", "Escape", "Control_L", "Control_R", "space"):
            return
        if len(event.char) == 1 and event.char.isprintable():
            self._close_completion_popup()

    def _on_tag_complete(self, event) -> str:
        """Ctrl+Space: 文脈に応じたタグ／パラメータ候補をポップアップ表示。
        既存の日本語・英語本文の途中で <s と打っている場合も、タグ名部分だけを正しく置換する。
        """
        self._close_completion_popup()
        mode, partial, tag_id, name_start = self._cursor_context()
        candidates = self._candidates_for_context(mode, partial, tag_id)
        if not candidates:
            self._set_status("補完候補なし（タグ定義を確認・Ctrl+Space）")
            return "break"

        try:
            bbox = self.editor.bbox("insert")
            if bbox:
                x, y, _, h = bbox
                abs_x = self.editor.winfo_rootx() + x
                abs_y = self.editor.winfo_rooty() + y + h + 2
            else:
                abs_x = self.editor.winfo_rootx() + 20
                abs_y = self.editor.winfo_rooty() + 40
        except tk.TclError:
            abs_x, abs_y = 100, 100

        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.configure(bg=C["border"])
        try:
            popup.attributes("-topmost", True)
        except tk.TclError:
            pass
        self._completion_popup = popup

        lb = tk.Listbox(
            popup,
            bg=C["surface2"],
            fg=C["text"],
            selectbackground=C["accent"],
            selectforeground="#ffffff",
            activestyle="none",
            font=("Consolas", 11),
            relief=tk.FLAT,
            highlightthickness=0,
            borderwidth=0,
            exportselection=False,
            height=min(12, max(1, len(candidates))),
            width=42,
        )
        lb.pack(padx=1, pady=1)
        for label, _ in candidates:
            lb.insert(tk.END, f"  {label}")
        lb.selection_set(0)
        lb.activate(0)

        def do_insert(sel_idx: int) -> None:
            if not (0 <= sel_idx < len(candidates)):
                return
            _, insert_str = candidates[sel_idx]
            self._close_completion_popup()
            try:
                if mode == "tag_angle" and name_start is not None:
                    # <partial…本文 のとき: タグ名部分だけ消して id> を入れる
                    # 例: <sあいさつ| → <shake>あいさつ
                    # name_start から name_start+len(partial) までがタグ名
                    name_end = self.editor.index(f"{name_start} + {len(partial)}c")
                    self.editor.delete(name_start, name_end)
                    to_insert = insert_str[1:] if insert_str.startswith("<") else insert_str  # shake>
                    self.editor.insert(name_start, to_insert)
                    # カーソルを > の直後へ（本文の前）
                    self.editor.mark_set("insert", f"{name_start} + {len(to_insert)}c")
                elif mode == "tag_brace" and name_start is not None:
                    name_end = self.editor.index(f"{name_start} + {len(partial)}c")
                    self.editor.delete(name_start, name_end)
                    to_insert = insert_str[1:] if insert_str.startswith("{") else insert_str
                    self.editor.insert(name_start, to_insert)
                    self.editor.mark_set("insert", f"{name_start} + {len(to_insert)}c")
                elif mode == "param":
                    if partial:
                        start = self.editor.index(f"insert - {len(partial)}c")
                        self.editor.delete(start, "insert")
                    self.editor.insert("insert", insert_str)
                else:
                    # free: 直前の英数字 partial があれば消してフル挿入
                    if partial:
                        start = self.editor.index(f"insert - {len(partial)}c")
                        self.editor.delete(start, "insert")
                    self.editor.insert("insert", insert_str)
            except tk.TclError:
                self.editor.insert("insert", insert_str)
            self.editor.focus_set()

        def on_key(e):
            if e.keysym == "Escape":
                self._close_completion_popup()
                self.editor.focus_set()
                return "break"
            if e.keysym == "Return":
                sel = lb.curselection()
                if sel:
                    do_insert(int(sel[0]))
                return "break"
            if e.keysym == "Up":
                cur = lb.curselection()
                i = max(0, (int(cur[0]) if cur else 0) - 1)
                lb.selection_clear(0, tk.END)
                lb.selection_set(i)
                lb.activate(i)
                lb.see(i)
                return "break"
            if e.keysym == "Down":
                cur = lb.curselection()
                i = min(len(candidates) - 1, (int(cur[0]) if cur else 0) + 1)
                lb.selection_clear(0, tk.END)
                lb.selection_set(i)
                lb.activate(i)
                lb.see(i)
                return "break"
            return None

        def on_dbl(_e):
            sel = lb.curselection()
            if sel:
                do_insert(int(sel[0]))

        lb.bind("<KeyPress>", on_key)
        lb.bind("<Double-Button-1>", on_dbl)
        lb.bind("<Return>", on_key)
        popup.bind("<Escape>", lambda e: (self._close_completion_popup(), self.editor.focus_set()))
        popup.geometry(f"+{abs_x}+{abs_y}")
        lb.focus_set()
        return "break"


# ---------------------------------------------------------------------------
# タグ定義エディタ
# ---------------------------------------------------------------------------

class TagDefinitionEditor(tk.Toplevel):
    """text_animator_tags.json の読み込み・編集・保存。"""

    def __init__(self, master, initial_path: Optional[str] = None, on_path_changed=None):
        super().__init__(master)
        self.title("Text Animator タグ定義")
        self.geometry("940x640")
        self.minsize(720, 480)
        self.configure(bg=C["bg"])
        self.transient(master)

        self.on_path_changed = on_path_changed
        self.path: Optional[str] = None
        self.data: dict = json.loads(json.dumps(DEFAULT_TAG_CONFIG))
        self._dirty = False
        self._kind = tk.StringVar(value="behavior")  # behavior | appearance

        self._build()
        target = initial_path or ensure_tag_file(TAGS_PATH)
        if os.path.isfile(target):
            self._load(target)
        else:
            self._refresh_list()
            self.path_var.set("")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _btn(self, parent, text, command, accent=False, danger=False):
        style = "Accent.TButton" if accent else ("Danger.TButton" if danger else "Ghost.TButton")
        return ttk.Button(parent, text=text, command=command, style=style)

    def _build(self) -> None:
        path_card = tk.Frame(self, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        path_card.pack(fill=tk.X, padx=12, pady=10)
        inner = tk.Frame(path_card, bg=C["surface"])
        inner.pack(fill=tk.X, padx=10, pady=8)
        tk.Label(
            inner,
            text="タグ定義 JSON パス（初回起動時に設定フォルダへ自動生成されます）",
            bg=C["surface"],
            fg=C["text_muted"],
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W)

        row = tk.Frame(inner, bg=C["surface"])
        row.pack(fill=tk.X, pady=(4, 0))
        self.path_var = tk.StringVar()
        ent = tk.Entry(
            row,
            textvariable=self.path_var,
            bg=C["input_bg"],
            fg=C["accent"],
            insertbackground=C["accent"],
            relief=tk.FLAT,
            font=("Consolas", 10),
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 8))
        ent.bind("<Return>", lambda e: self._open_from_entry())
        self._btn(row, "参照…", self.browse_open, accent=True).pack(side=tk.LEFT, padx=2)
        self._btn(row, "保存", self.save).pack(side=tk.LEFT, padx=2)
        self._btn(row, "別名…", self.save_as).pack(side=tk.LEFT, padx=2)
        self._btn(row, "既定に戻す", self.reset_default, danger=True).pack(side=tk.LEFT, padx=2)

        kind_row = tk.Frame(self, bg=C["bg"])
        kind_row.pack(fill=tk.X, padx=12, pady=(0, 6))
        tk.Label(kind_row, text="種別:", bg=C["bg"], fg=C["text_muted"]).pack(side=tk.LEFT)
        for label, val in [("Behavior  <tag>", "behavior"), ("Appearance  {tag}", "appearance")]:
            ttk.Radiobutton(
                kind_row,
                text=label,
                value=val,
                variable=self._kind,
                command=self._refresh_list,
            ).pack(side=tk.LEFT, padx=8)

        self._btn(kind_row, "追加", self.add_tag, accent=True).pack(side=tk.LEFT, padx=(16, 2))
        self._btn(kind_row, "削除", self.delete_tag, danger=True).pack(side=tk.LEFT, padx=2)
        self._btn(kind_row, "上へ", self.move_up).pack(side=tk.LEFT, padx=2)
        self._btn(kind_row, "下へ", self.move_down).pack(side=tk.LEFT, padx=2)
        self._btn(kind_row, "入れ替え…", self.swap_tags).pack(side=tk.LEFT, padx=2)
        self._btn(kind_row, "位置指定挿入…", self.insert_tag_at).pack(side=tk.LEFT, padx=2)

        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        left = tk.Frame(paned, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        right = tk.Frame(paned, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
        paned.add(left, weight=2)
        paned.add(right, weight=3)

        tk.Label(left, text="  タグ一覧（ドラッグで行間に挿入）", bg=C["surface"], fg=C["text_muted"], font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(6, 2))
        lw = tk.Frame(left, bg=C["surface"])
        lw.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.listbox = tk.Listbox(
            lw,
            bg=C["input_bg"],
            fg=C["text"],
            selectbackground=C["list_sel"],
            selectforeground="#fff",
            activestyle="none",
            font=("Consolas", 11),
            relief=tk.FLAT,
            highlightthickness=0,
            exportselection=False,
        )
        sb = ttk.Scrollbar(lw, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self._tag_dnd = ListboxDragInsert(self.listbox, self._reorder_tags, lambda: len(self._tags()))

        tk.Label(right, text="  選択タグの編集", bg=C["surface"], fg=C["text_muted"], font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(6, 2))
        form = tk.Frame(right, bg=C["surface"])
        form.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        self.f_id = self._field(form, "id（タグ名）")
        self.f_label = self._field(form, "label（表示名）")
        self.f_mods = self._field(form, "modifiers（カンマ区切り 例: a,f,w）")
        self.f_example = self._field(form, "example")
        self.f_open = self._field(form, "open（Appearance用 例: {fade}）")
        self.f_close = self._field(form, "close（Appearance用 例: {/fade}）")

        self._btn(form, "この内容を反映", self.apply_form, accent=True).pack(anchor=tk.W, pady=(12, 0))

        self.status = tk.Label(
            self,
            text="タグ定義 JSON を開くか、追加して保存",
            bg=C["surface"],
            fg=C["text_muted"],
            anchor=tk.W,
            font=("Segoe UI", 9),
            padx=12,
            pady=6,
        )
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    def _field(self, parent, label: str) -> tk.StringVar:
        tk.Label(parent, text=label, bg=C["surface"], fg=C["text_muted"], font=("Segoe UI", 8)).pack(anchor=tk.W, pady=(8, 0))
        var = tk.StringVar()
        e = tk.Entry(
            parent,
            textvariable=var,
            bg=C["input_bg"],
            fg=C["text"],
            insertbackground=C["text"],
            relief=tk.FLAT,
            font=("Segoe UI", 11),
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        e.pack(fill=tk.X, ipady=4)
        return var

    def _tag_list_key(self) -> str:
        return "behavior_tags" if self._kind.get() == "behavior" else "appearance_tags"

    def _tags(self) -> list:
        key = self._tag_list_key()
        if key not in self.data or not isinstance(self.data[key], list):
            self.data[key] = []
        return self.data[key]

    def _refresh_list(self, select: Optional[int] = None) -> None:
        self.listbox.delete(0, tk.END)
        for t in self._tags():
            tid = str(t.get("id", "?"))
            lab = str(t.get("label", ""))
            mods = ",".join(t.get("modifiers") or [])
            self.listbox.insert(tk.END, f"  {tid:12s}  {lab:16s}  [{mods}]")
        if select is not None and 0 <= select < len(self._tags()):
            self.listbox.selection_set(select)
            self.listbox.see(select)
            self._on_select()

    def _selected(self) -> Optional[int]:
        sel = self.listbox.curselection()
        return int(sel[0]) if sel else None

    def _on_select(self, _e=None) -> None:
        idx = self._selected()
        if idx is None or idx >= len(self._tags()):
            return
        t = self._tags()[idx]
        self.f_id.set(t.get("id", ""))
        self.f_label.set(t.get("label", ""))
        self.f_mods.set(",".join(t.get("modifiers") or []))
        self.f_example.set(t.get("example", ""))
        self.f_open.set(t.get("open", ""))
        self.f_close.set(t.get("close", ""))

    def apply_form(self) -> None:
        idx = self._selected()
        if idx is None:
            messagebox.showinfo("情報", "左からタグを選択するか、「追加」してください", parent=self)
            return
        tid = self.f_id.get().strip()
        if not tid:
            messagebox.showerror("エラー", "id は必須です", parent=self)
            return
        mods = [m.strip() for m in self.f_mods.get().split(",") if m.strip()]
        tag = {"id": tid, "label": self.f_label.get().strip() or tid, "modifiers": mods}
        ex = self.f_example.get().strip()
        if ex:
            tag["example"] = ex
        if self._kind.get() == "appearance":
            op = self.f_open.get().strip()
            cl = self.f_close.get().strip()
            if op:
                tag["open"] = op
            if cl:
                tag["close"] = cl
        self._tags()[idx] = tag
        self._dirty = True
        self._refresh_list(select=idx)
        self.status.config(text=f"反映: {tid}")

    def _new_tag(self) -> dict:
        if self._kind.get() == "behavior":
            return {"id": "newtag", "label": "New Tag", "modifiers": [], "example": "<newtag>"}
        return {"id": "newtag", "label": "New Tag", "modifiers": [], "open": "{newtag}", "close": "{/newtag}"}

    def add_tag(self) -> None:
        self._tags().append(self._new_tag())
        self._dirty = True
        self._refresh_list(select=len(self._tags()) - 1)

    def delete_tag(self) -> None:
        idx = self._selected()
        if idx is None:
            return
        del self._tags()[idx]
        self._dirty = True
        self._refresh_list(select=min(idx, len(self._tags()) - 1) if self._tags() else None)

    def _reorder_tags(self, frm: int, to: int) -> None:
        tags = self._tags()
        if frm < 0 or to < 0 or frm >= len(tags) or to >= len(tags) or frm == to:
            return
        item = tags.pop(frm)
        tags.insert(to, item)
        self._dirty = True
        self._refresh_list(select=to)
        self.status.config(text=f"移動: #{frm} → #{to}")

    def insert_tag_at(self) -> None:
        tags = self._tags()
        pos = ask_insert_index(self, len(tags), title="タグの位置指定挿入")
        if pos is None:
            return
        tags.insert(pos, self._new_tag())
        self._dirty = True
        self._refresh_list(select=pos)
        self.status.config(text=f"挿入: 位置 #{pos}")

    def swap_tags(self) -> None:
        tags = self._tags()
        if len(tags) < 2:
            messagebox.showinfo("情報", "入れ替えるタグが2件以上必要です", parent=self)
            return
        pair = ask_swap_indices(self, len(tags) - 1, title="タグの入れ替え")
        if not pair:
            return
        a, b = pair
        tags[a], tags[b] = tags[b], tags[a]
        self._dirty = True
        self._refresh_list(select=b)
        self.status.config(text=f"入れ替え: #{a} ⟷ #{b}")

    def move_up(self) -> None:
        idx = self._selected()
        if idx is None or idx <= 0:
            return
        self._reorder_tags(idx, idx - 1)

    def move_down(self) -> None:
        idx = self._selected()
        if idx is None or idx >= len(self._tags()) - 1:
            return
        self._reorder_tags(idx, idx + 1)

    def reset_default(self) -> None:
        if not messagebox.askyesno("確認", "タグ定義を既定値に戻しますか？", parent=self):
            return
        self.data = json.loads(json.dumps(DEFAULT_TAG_CONFIG))
        self._dirty = True
        self._refresh_list()
        self.status.config(text="既定のタグ定義に戻しました（保存で確定）")

    def browse_open(self) -> None:
        initial = os.path.dirname(self.path) if self.path else CONFIG_DIR
        p = filedialog.askopenfilename(
            parent=self,
            title="タグ定義 JSON を開く",
            initialdir=initial,
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if p:
            self._load(p)

    def _open_from_entry(self) -> None:
        p = self.path_var.get().strip().strip('"')
        if p and os.path.isfile(p):
            self._load(p)
        elif p:
            messagebox.showerror("エラー", f"ファイルが見つかりません:\n{p}", parent=self)

    def _load(self, p: str) -> None:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("JSON のルートはオブジェクトである必要があります")
            for k, v in DEFAULT_TAG_CONFIG.items():
                if k not in data:
                    data[k] = json.loads(json.dumps(v))
            self.data = data
            self.path = os.path.abspath(p)
            self.path_var.set(self.path)
            self._dirty = False
            self._refresh_list()
            self.status.config(text=f"読込: {self.path}")
            if self.on_path_changed:
                self.on_path_changed(self.path)
        except Exception as e:
            messagebox.showerror("読込エラー", str(e), parent=self)

    def save(self) -> None:
        if not self.path:
            self.save_as()
            return
        try:
            _write_json(self.path, self.data)
            self._dirty = False
            self.status.config(text=f"保存しました: {self.path}")
            if self.on_path_changed:
                self.on_path_changed(self.path)
        except Exception as e:
            messagebox.showerror("保存エラー", str(e), parent=self)

    def save_as(self) -> None:
        initial = os.path.dirname(self.path) if self.path else CONFIG_DIR
        p = filedialog.asksaveasfilename(
            parent=self,
            title="タグ定義を保存",
            initialdir=initial,
            defaultextension=".json",
            initialfile="text_animator_tags.json",
            filetypes=[("JSON", "*.json")],
        )
        if p:
            self.path = os.path.abspath(p)
            self.path_var.set(self.path)
            self.save()

    def _on_close(self) -> None:
        if self._dirty and not messagebox.askyesno("確認", "未保存の変更があります。閉じますか？", parent=self):
            return
        self.destroy()


def main() -> None:
    initial = sys.argv[1] if len(sys.argv) > 1 else None
    app = ScenarioMatrixEditor(initial)
    app.mainloop()


if __name__ == "__main__":
    main()