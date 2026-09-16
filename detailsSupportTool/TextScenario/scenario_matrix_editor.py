#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ScenarioMatrix 高速編集ツール（モダンUI）

起動:
  python scenario_matrix_editor.py
  python scenario_matrix_editor.py /path/to/ScenarioText.json

主な機能:
  - JSON パスを自動保持（再起動しても前回のファイル/行/列/フィールドを復元）
  - 設定・タグ定義は  <このファイルの2つ上>/data/editor_config/  に自動生成
  - テキスト取込時は空行を捨てる
  - 選択行の左の「＋」から「上に追加 / 下に追加」
  - ドラッグ＆ドロップは「行間に挿入」（挿入位置をラインで表示）
  - 行ごとの演出メモ（コメント）を保存（サイドカー JSON）
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict, List, Optional, Tuple

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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FOLDER_NAME = "editor_config"


def _resolve_data_dir() -> str:
    """<script>/../../data を最優先。無ければ上位を遡って data を探す。"""
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


def set_cell_list(matrix: dict, row_key: str, col_key: str, items: List[str], field_name: str = "texts") -> None:
    data = matrix.setdefault("data", {})
    row = data.setdefault(row_key, {})
    cell = row.setdefault(col_key, {})
    existing = cell.get(field_name)
    if isinstance(existing, dict) and "value" in existing:
        existing["value"] = list(items)
        existing.setdefault("type", "string")
    else:
        cell[field_name] = {"value": list(items), "type": "string"}


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
# メインウィンドウ
# ---------------------------------------------------------------------------

class ScenarioMatrixEditor(tk.Tk):
    def __init__(self, initial_path: Optional[str] = None):
        super().__init__()
        self.title("Scenario Matrix Editor")
        self.minsize(900, 560)
        self.configure(bg=C["bg"])

        self.settings = load_settings()
        self.tags_path = self.settings.get("tags_path") or TAGS_PATH
        if not os.path.isfile(self.tags_path):
            self.tags_path = TAGS_PATH
        ensure_tag_file(self.tags_path)
        self.settings["tags_path"] = self.tags_path

        self.comments_store = CommentStore()

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
            last = self.settings.get("last_matrix_path") or ""
            if last and os.path.isfile(last):
                startup = last
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
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(header, text="Scenario Matrix Editor", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="  高速 · 配列編集 · 行コメント · テキストI/O · 翻訳", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text=f"設定: {CONFIG_DIR}", style="Muted.TLabel").pack(side=tk.RIGHT)

        # パスバー
        path_card = tk.Frame(self, bg=C["surface"], highlightbackground=C["border"], highlightthickness=1)
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
        sel = tk.Frame(self, bg=C["bg"])
        sel.pack(fill=tk.X, padx=16, pady=8)
        self._labeled_combo(sel, "行 (Language)", "row")
        self._labeled_combo(sel, "列 (Scenario)", "col", width=36)
        self._labeled_entry(sel, "フィールド", "field", default="texts", width=12)
        self._btn(sel, "読込", self._reload_list, accent=True).pack(side=tk.LEFT, padx=(8, 0))

        # ツールバー
        tools = tk.Frame(self, bg=C["bg"])
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
        self._btn(tools, "Ja→En 翻訳追記", self.translate_ja_to_en).pack(side=tk.LEFT, padx=2)
        self._btn(tools, "全文プレビュー", self.preview_all).pack(side=tk.LEFT, padx=2)
        tk.Frame(tools, bg=C["border"], width=1).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
        self._btn(tools, "タグ定義の編集…", self.open_tag_editor, accent=True).pack(side=tk.LEFT, padx=2)

        # 分割
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
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

        tk.Label(
            right,
            text="  この行のコメント（演出メモ・JSON には書き出さずサイドカー保存）",
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

        self.status = ttk.Label(self, text="「参照…」で JSON を開くか、パスを入力して Enter", style="Status.TLabel")
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

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
        if self.path:
            self.settings["last_matrix_path"] = self.path
            recents: List[str] = [p for p in (self.settings.get("recent_paths") or []) if p != self.path]
            recents.insert(0, self.path)
            self.settings["recent_paths"] = recents[:12]
        self.settings["last_row"] = self.row_var.get()
        self.settings["last_col"] = self.col_var.get()
        self.settings["last_field"] = self.field_var.get() or "texts"
        self.settings["tags_path"] = self.tags_path
        try:
            self.settings["geometry"] = self.winfo_geometry()
        except tk.TclError:
            pass
        save_settings(self.settings)
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        recents = [p for p in (self.settings.get("recent_paths") or []) if os.path.isfile(p)]
        self.settings["recent_paths"] = recents
        self.recent_combo["values"] = recents
        if self.path and self.path in recents:
            self.recent_var.set(self.path)

    def _on_recent_selected(self, _e=None) -> None:
        p = self.recent_var.get()
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

        # 空白のみの行 / 空行は取り込まない
        lines: List[str] = []
        skipped = 0
        for ln in raw.splitlines():
            s = ln.rstrip()
            if not s.strip():
                skipped += 1
                continue
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
    def translate_ja_to_en(self) -> None:
        if not self.matrix:
            return
        rows = list_row_keys(self.matrix)
        ja_key = next((r for r in rows if normalize_row_key(r).lower() in ("ja", "jp", "japanese")), None)
        en_key = next((r for r in rows if normalize_row_key(r).lower() in ("en", "eng", "english")), None)
        if not ja_key:
            messagebox.showwarning("翻訳", "日本語行（Ja）が見つかりません")
            return
        if not en_key:
            en_key = "En"
            self.matrix.setdefault("data", {})[en_key] = {}
            self._refresh_combos({"row": self.row_var.get(), "col": self.col_var.get(), "field": self.field_var.get()})
        col = self.col_var.get()
        field = self.field_var.get() or "texts"
        if not col:
            messagebox.showwarning("翻訳", "列を選択してください")
            return
        ja_list = get_cell_list(self.matrix, ja_key, col, field)
        if not ja_list:
            messagebox.showinfo("翻訳", "日本語側にテキストがありません")
            return
        if not messagebox.askyesno(
            "翻訳確認",
            f"{ja_key} → {en_key}\n列: {col}\n{len(ja_list)} 件を翻訳して英語配列へ追記します。\n"
            "（Text Animator タグは翻訳しません）\n続行しますか？",
        ):
            return
        en_list = get_cell_list(self.matrix, en_key, col, field)
        translated: List[str] = []
        for i, src in enumerate(ja_list):
            self._set_status(f"翻訳中… {i + 1}/{len(ja_list)}")
            self.update_idletasks()
            translated.append(try_translate(src, "ja", "en"))
        en_list.extend(translated)
        set_cell_list(self.matrix, en_key, col, en_list, field)
        self._dirty = True
        self.row_var.set(en_key)
        self._reload_list()
        self._set_status(f"翻訳完了: {len(translated)} 件を {en_key} に追記")

    # -- タグ定義 -----------------------------------------------------------
    def open_tag_editor(self) -> None:
        """Text Animator タグ定義 JSON（自動生成済み）を開く。"""
        path = ensure_tag_file(self.tags_path)
        TagDefinitionEditor(self, initial_path=path, on_path_changed=self._on_tags_path_changed)

    def _on_tags_path_changed(self, new_path: str) -> None:
        self.tags_path = os.path.abspath(new_path)
        self._remember()

    def _set_status(self, msg: str) -> None:
        self.status.config(text=msg)


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