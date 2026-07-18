#!/usr/bin/env python3
"""
Sprite Sheet Editor - ゲーム用スプライトシート作成ツール
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import json
import os
import math
from PIL import Image, ImageTk, ImageDraw
import copy



from typing import Optional


# ============================================================
# Data Classes
# ============================================================

class Crop:
    """一つの切り取り領域"""
    def __init__(self, cid, source_file, x, y, w, h):
        self.id = cid
        self.source_file = source_file
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.label = f"Crop {cid}"

    def to_dict(self):
        return {
            "id": self.id,
            "source_file": self.source_file,
            "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
            "label": self.label
        }

    @classmethod
    def from_dict(cls, d):
        c = cls(d["id"], d["source_file"], d["x"], d["y"], d["w"], d["h"])
        c.label = d.get("label", f"Crop {d['id']}")
        return c


class SpriteCell:
    """スプライトシート上の1マス"""
    def __init__(self, row, col, crop_id=None, offset_x=0, offset_y=0, scale=1.0):
        self.row = row
        self.col = col
        self.crop_id = crop_id
        self.offset_x = offset_x  # 微調整オフセット
        self.offset_y = offset_y
        self.scale = scale

    def to_dict(self):
        return {
            "row": self.row, "col": self.col,
            "crop_id": self.crop_id,
            "offset_x": self.offset_x, "offset_y": self.offset_y,
            "scale": self.scale
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            d["row"], d["col"], d.get("crop_id"),
            d.get("offset_x", 0), d.get("offset_y", 0),
            d.get("scale", 1.0)
        )


class Project:
    """プロジェクト全体のデータ"""
    def __init__(self):
        self.sheet_w = 1000
        self.sheet_h = 1000
        self.cols = 10
        self.rows = 10
        self.loaded_files = []   # 読み込み済み画像パス
        self.crops: list[Crop] = []
        self.cells: list[SpriteCell] = []
        self._next_crop_id = 1

    def new_crop_id(self):
        cid = self._next_crop_id
        self._next_crop_id += 1
        return cid

    def cell_size(self):
        return self.sheet_w / self.cols, self.sheet_h / self.rows

    def get_cell(self, row, col) -> Optional[SpriteCell]:
        for c in self.cells:
            if c.row == row and c.col == col:
                return c
        return None

    def set_cell(self, row, col, crop_id, offset_x=0, offset_y=0, scale=1.0):
        existing = self.get_cell(row, col)
        if existing:
            existing.crop_id = crop_id
            existing.offset_x = offset_x
            existing.offset_y = offset_y
            existing.scale = scale
        else:
            self.cells.append(SpriteCell(row, col, crop_id, offset_x, offset_y, scale))

    def clear_cell(self, row, col):
        self.cells = [c for c in self.cells if not (c.row == row and c.col == col)]

    def get_crop(self, cid) -> Optional[Crop]:
        for c in self.crops:
            if c.id == cid:
                return c
        return None

    def to_dict(self):
        return {
            "sheet_w": self.sheet_w,
            "sheet_h": self.sheet_h,
            "cols": self.cols,
            "rows": self.rows,
            "loaded_files": self.loaded_files,
            "crops": [c.to_dict() for c in self.crops],
            "cells": [c.to_dict() for c in self.cells],
            "_next_crop_id": self._next_crop_id
        }

    @classmethod
    def from_dict(cls, d):
        p = cls()
        p.sheet_w = d["sheet_w"]
        p.sheet_h = d["sheet_h"]
        p.cols = d["cols"]
        p.rows = d["rows"]
        p.loaded_files = d.get("loaded_files", [])
        p.crops = [Crop.from_dict(c) for c in d.get("crops", [])]
        p.cells = [SpriteCell.from_dict(c) for c in d.get("cells", [])]
        p._next_crop_id = d.get("_next_crop_id", 1)
        return p


# ============================================================
# Image Manager
# ============================================================

class ImageManager:
    """PILイメージのキャッシュ管理"""
    def __init__(self):
        self._cache: dict[str, Image.Image] = {}

    def load(self, path) -> Optional[Image.Image]:
        if path not in self._cache:
            try:
                img = Image.open(path).convert("RGBA")
                self._cache[path] = img
            except Exception as e:
                print(f"Load error {path}: {e}")
                return None
        return self._cache[path]

    def get_crop_image(self, crop: Crop) -> Optional[Image.Image]:
        img = self.load(crop.source_file)
        if img is None:
            return None
        return img.crop((crop.x, crop.y, crop.x + crop.w, crop.y + crop.h))

    def reload(self, path):
        if path in self._cache:
            del self._cache[path]
        return self.load(path)


# ============================================================
# Crop Editor Panel
# ============================================================

class CropEditorPanel(tk.Toplevel):
    """画像から矩形を切り取るウィンドウ"""
    def __init__(self, parent, project: Project, img_man: ImageManager, source_file: str, on_done):
        super().__init__(parent)
        self.title(f"切り取りエディター: {os.path.basename(source_file)}")
        self.project = project
        self.img_man = img_man
        self.source_file = source_file
        self.on_done = on_done

        self.orig_img = img_man.load(source_file)
        if self.orig_img is None:
            messagebox.showerror("エラー", "画像を読み込めません")
            self.destroy()
            return

        self.ow, self.oh = self.orig_img.size
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0

        # ドラッグ状態
        self.drag_start = None
        self.drag_rect = None  # (x0,y0,x1,y1) canvas座標
        self.drag_action = None
        self.drag_handle = None
        self.drag_crop = None
        self.drag_orig = None

        # 既存crops (この画像のもの)
        self.crops_here = [c for c in project.crops if c.source_file == source_file]
        self.selected_crop = None

        self._build_ui()
        self._fit_zoom()
        self._redraw()

    def _build_ui(self):
        self.configure(bg="#1a1a2e")
        self.resizable(True, True)

        top = tk.Frame(self, bg="#1a1a2e")
        top.pack(fill=tk.X, padx=8, pady=4)

        btn_style = {"bg": "#4a90d9", "fg": "white", "relief": tk.FLAT,
                     "padx": 8, "pady": 4, "cursor": "hand2", "font": ("Consolas", 9)}

        tk.Button(top, text="🔍+ ズームイン", **btn_style,
                  command=lambda: self._zoom(1.25)).pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="🔍- ズームアウト", **btn_style,
                  command=lambda: self._zoom(0.8)).pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="⊡ フィット", **btn_style,
                  command=self._fit_zoom).pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="🗑 選択削除", bg="#c0392b", fg="white", relief=tk.FLAT,
                  padx=8, pady=4, cursor="hand2", font=("Consolas", 9),
                  command=self._delete_selected).pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="✓ 完了", bg="#27ae60", fg="white", relief=tk.FLAT,
                  padx=8, pady=4, cursor="hand2", font=("Consolas", 9),
                  command=self._finish).pack(side=tk.RIGHT, padx=2)

        self.info_label = tk.Label(top, text="ドラッグで矩形を選択", bg="#1a1a2e",
                                   fg="#aaaaaa", font=("Consolas", 9))
        self.info_label.pack(side=tk.LEFT, padx=8)

        main = tk.Frame(self, bg="#1a1a2e")
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))

        # Canvas
        canvas_frame = tk.Frame(main, bg="#0d0d1a", relief=tk.FLAT, bd=1)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#0d0d1a", cursor="crosshair",
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # スクロール
        hbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL,
                            command=self.canvas.xview)
        vbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL,
                            command=self.canvas.yview)

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)

        # 右パネル: crops一覧
        right = tk.Frame(main, bg="#1a1a2e", width=180)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(6,0))
        right.pack_propagate(False)

        tk.Label(right, text="切り取り一覧", bg="#1a1a2e", fg="#e0e0e0",
                 font=("Consolas", 10, "bold")).pack(pady=(4,2))

        list_frame = tk.Frame(right, bg="#1a1a2e")
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.crop_listbox = tk.Listbox(list_frame, bg="#0d0d1a", fg="#e0e0e0",
                                       selectbackground="#4a90d9",
                                       font=("Consolas", 9), relief=tk.FLAT,
                                       highlightthickness=0)
        self.crop_listbox.pack(fill=tk.BOTH, expand=True)
        self.crop_listbox.bind("<<ListboxSelect>>", lambda e: self._on_crop_select())
        self._refresh_listbox()

        self.geometry("900x650")

    def _refresh_listbox(self):
        self.crop_listbox.delete(0, tk.END)
        for c in self.crops_here:
            self.crop_listbox.insert(tk.END, f"{c.label} ({c.w}×{c.h})")
        if self.selected_crop in self.crops_here:
            idx = self.crops_here.index(self.selected_crop)
            self.crop_listbox.select_set(idx)

    def _on_crop_select(self):
        sel = self.crop_listbox.curselection()
        if sel:
            self.selected_crop = self.crops_here[sel[0]]
        else:
            self.selected_crop = None
        self._redraw()

    def _is_near(self, a, b, tol=8):
        return abs(a - b) <= tol / self.zoom

    def _find_crop_at(self, ix, iy):
        for idx, crop in enumerate(self.crops_here):
            x0, y0 = crop.x, crop.y
            x1, y1 = crop.x + crop.w, crop.y + crop.h
            handle = None
            if self._is_near(ix, x0) and self._is_near(iy, y0):
                handle = "nw"
            elif self._is_near(ix, x1) and self._is_near(iy, y0):
                handle = "ne"
            elif self._is_near(ix, x0) and self._is_near(iy, y1):
                handle = "sw"
            elif self._is_near(ix, x1) and self._is_near(iy, y1):
                handle = "se"
            elif self._is_near(ix, x0) and y0 < iy < y1:
                handle = "w"
            elif self._is_near(ix, x1) and y0 < iy < y1:
                handle = "e"
            elif self._is_near(iy, y0) and x0 < ix < x1:
                handle = "n"
            elif self._is_near(iy, y1) and x0 < ix < x1:
                handle = "s"
            elif x0 < ix < x1 and y0 < iy < y1:
                handle = "inside"
            if handle:
                return crop, idx, handle
        return None, None, None

    def _clamp_crop(self, crop):
        crop.x = max(0, min(crop.x, self.ow - 1))
        crop.y = max(0, min(crop.y, self.oh - 1))
        crop.w = max(1, min(crop.w, self.ow - crop.x))
        crop.h = max(1, min(crop.h, self.oh - crop.y))

    def _fit_zoom(self):
        self.update_idletasks()
        cw = self.canvas.winfo_width() or 700
        ch = self.canvas.winfo_height() or 500
        self.zoom = min(cw / self.ow, ch / self.oh, 1.0) * 0.9
        self.offset_x = 10
        self.offset_y = 10
        self._redraw()

    def _zoom(self, factor):
        self.zoom = max(0.05, min(self.zoom * factor, 20))
        self._redraw()

    def _on_wheel(self, event):
        if event.num == 4 or event.delta > 0:
            self._zoom(1.15)
        else:
            self._zoom(0.87)

    def _canvas_to_img(self, cx, cy):
        return (cx - self.offset_x) / self.zoom, (cy - self.offset_y) / self.zoom

    def _img_to_canvas(self, ix, iy):
        return ix * self.zoom + self.offset_x, iy * self.zoom + self.offset_y

    def _on_mouse_down(self, event):
        ix, iy = self._canvas_to_img(event.x, event.y)
        crop, idx, handle = self._find_crop_at(ix, iy)
        if crop:
            self.selected_crop = crop
            self.crop_listbox.selection_clear(0, tk.END)
            self.crop_listbox.select_set(idx)
            self.drag_action = "move" if handle == "inside" else "resize"
            self.drag_handle = handle
            self.drag_crop = crop
            self.drag_orig = (crop.x, crop.y, crop.w, crop.h)
            self.drag_start = (ix, iy)
            self.drag_rect = None
            self._redraw()
            return

        self.selected_crop = None
        self.drag_action = None
        self.drag_handle = None
        self.drag_crop = None
        self.drag_orig = None
        self.drag_start = (event.x, event.y)
        self.drag_rect = None

    def _on_mouse_drag(self, event):
        if self.drag_action and self.drag_crop and self.drag_start:
            ix, iy = self._canvas_to_img(event.x, event.y)
            x0, y0, w0, h0 = self.drag_orig
            x1 = x0 + w0
            y1 = y0 + h0
            if self.drag_action == "move":
                dx = ix - self.drag_start[0]
                dy = iy - self.drag_start[1]
                self.drag_crop.x = int(max(0, min(self.ow - self.drag_crop.w, x0 + dx)))
                self.drag_crop.y = int(max(0, min(self.oh - self.drag_crop.h, y0 + dy)))
            else:
                nx0, ny0, nx1, ny1 = x0, y0, x1, y1
                if "w" in self.drag_handle:
                    nx0 = min(max(0, ix), x1 - 1)
                if "e" in self.drag_handle:
                    nx1 = max(x0 + 1, min(self.ow, ix))
                if "n" in self.drag_handle:
                    ny0 = min(max(0, iy), y1 - 1)
                if "s" in self.drag_handle:
                    ny1 = max(y0 + 1, min(self.oh, iy))
                self.drag_crop.x = int(nx0)
                self.drag_crop.y = int(ny0)
                self.drag_crop.w = int(max(1, nx1 - nx0))
                self.drag_crop.h = int(max(1, ny1 - ny0))
            self._clamp_crop(self.drag_crop)
            self._refresh_listbox()
            self._redraw()
            return

        if self.drag_start:
            x0, y0 = self.drag_start
            self.drag_rect = (x0, y0, event.x, event.y)
            self._redraw()

    def _on_mouse_up(self, event):
        if self.drag_action and self.drag_crop:
            self.drag_action = None
            self.drag_handle = None
            self.drag_crop = None
            self.drag_orig = None
        elif self.drag_start and self.drag_rect:
            x0, y0, x1, y1 = self.drag_rect
            if abs(x1-x0) > 5 and abs(y1-y0) > 5:
                ix0, iy0 = self._canvas_to_img(min(x0,x1), min(y0,y1))
                ix1, iy1 = self._canvas_to_img(max(x0,x1), max(y0,y1))
                ix0 = max(0, int(ix0)); iy0 = max(0, int(iy0))
                ix1 = min(self.ow, int(ix1)); iy1 = min(self.oh, int(iy1))
                if ix1 > ix0 and iy1 > iy0:
                    self._add_crop(ix0, iy0, ix1-ix0, iy1-iy0)
        self.drag_start = None
        self.drag_rect = None
        self._redraw()

    def _add_crop(self, x, y, w, h):
        cid = self.project.new_crop_id()
        crop = Crop(cid, self.source_file, x, y, w, h)
        label = simpledialog.askstring("ラベル", "この切り取りのラベルを入力:",
                                       initialvalue=f"sprite_{cid}", parent=self)
        if label:
            crop.label = label
        self.project.crops.append(crop)
        self.crops_here.append(crop)
        self._refresh_listbox()
        self._redraw()

    def _delete_selected(self):
        sel = self.crop_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        crop = self.crops_here[idx]
        if messagebox.askyesno("削除確認", f"'{crop.label}' を削除しますか？"):
            self.project.crops.remove(crop)
            self.crops_here.pop(idx)
            # セルからも除去
            self.project.cells = [c for c in self.project.cells if c.crop_id != crop.id]
            self._refresh_listbox()
            self._redraw()

    def _redraw(self):
        self.canvas.delete("all")
        # チェッカーボード背景
        cs = 16
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        for row in range(0, ch // cs + 1):
            for col in range(0, cw // cs + 1):
                color = "#2a2a2a" if (row+col) % 2 == 0 else "#1e1e1e"
                self.canvas.create_rectangle(col*cs, row*cs,
                                             (col+1)*cs, (row+1)*cs,
                                             fill=color, outline="")

        # 画像
        disp_w = int(self.ow * self.zoom)
        disp_h = int(self.oh * self.zoom)
        disp_img = self.orig_img.resize((max(1,disp_w), max(1,disp_h)), Image.NEAREST)
        self._tk_img = ImageTk.PhotoImage(disp_img)
        self.canvas.create_image(self.offset_x, self.offset_y,
                                 anchor=tk.NW, image=self._tk_img)

        sel = self.crop_listbox.curselection()
        sel_idx = sel[0] if sel else -1
        if self.selected_crop:
            self.info_label.config(text=f"選択: {self.selected_crop.label} {self.selected_crop.w}×{self.selected_crop.h}")
        else:
            self.info_label.config(text="ドラッグで矩形を選択。既存矩形をクリックして移動/リサイズ")

        # 既存crops
        for i, c in enumerate(self.crops_here):
            cx0, cy0 = self._img_to_canvas(c.x, c.y)
            cx1, cy1 = self._img_to_canvas(c.x+c.w, c.y+c.h)
            color = "#f0c040" if c == self.selected_crop else "#4a90d9"
            self.canvas.create_rectangle(cx0, cy0, cx1, cy1,
                                         outline=color, width=2, dash=(4,3))
            self.canvas.create_text(cx0+2, cy0+2, text=c.label,
                                    anchor=tk.NW, fill=color,
                                    font=("Consolas", 8))
            if c == self.selected_crop:
                for px, py in [(cx0, cy0), (cx1, cy0), (cx0, cy1), (cx1, cy1)]:
                    self.canvas.create_rectangle(px-4, py-4, px+4, py+4,
                                                 fill="#f0c040", outline="")

        # ドラッグ中
        if self.drag_rect:
            x0, y0, x1, y1 = self.drag_rect
            self.canvas.create_rectangle(min(x0,x1), min(y0,y1),
                                         max(x0,x1), max(y0,y1),
                                         outline="#ff6b6b", width=2, dash=(2,2))

    def _finish(self):
        self.on_done()
        self.destroy()


# ============================================================
# Sheet Editor Panel
# ============================================================

class SheetEditorPanel(tk.Frame):
    """スプライトシートの配置エディター"""
    def __init__(self, parent, project: Project, img_man: ImageManager, on_update):
        super().__init__(parent, bg="#0d0d1a")
        self.project = project
        self.img_man = img_man
        self.on_update = on_update
        self.zoom = 0.6
        self.selected_cell = None   # (row,col)
        self.drag_info = None
        self._tk_img = None
        self._build_ui()

    def _build_ui(self):
        top = tk.Frame(self, bg="#1a1a2e")
        top.pack(fill=tk.X, padx=4, pady=4)

        btn = {"bg": "#4a90d9", "fg": "white", "relief": tk.FLAT,
               "padx": 6, "pady": 3, "cursor": "hand2", "font": ("Consolas", 9)}

        tk.Button(top, text="🔍+", **btn, command=lambda: self._zoom(1.2)).pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="🔍-", **btn, command=lambda: self._zoom(0.83)).pack(side=tk.LEFT, padx=2)

        self.coord_label = tk.Label(top, text="", bg="#1a1a2e", fg="#888",
                                    font=("Consolas", 9))
        self.coord_label.pack(side=tk.LEFT, padx=8)

        canvas_frame = tk.Frame(self, bg="#0d0d1a")
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        hbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        vbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = tk.Canvas(canvas_frame, bg="#0d0d1a",
                                xscrollcommand=hbar.set,
                                yscrollcommand=vbar.set,
                                highlightthickness=0,
                                cursor="hand2")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        hbar.config(command=self.canvas.xview)
        vbar.config(command=self.canvas.yview)

        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)

    def _zoom(self, f):
        self.zoom = max(0.1, min(self.zoom * f, 5.0))
        self.redraw()

    def _on_wheel(self, event):
        if event.num == 4 or event.delta > 0:
            self._zoom(1.15)
        else:
            self._zoom(0.87)

    def _canvas_to_cell(self, cx, cy):
        p = self.project
        cw, ch = p.cell_size()
        col = int(cx / (cw * self.zoom))
        row = int(cy / (ch * self.zoom))
        if 0 <= row < p.rows and 0 <= col < p.cols:
            return row, col
        return None

    def _on_motion(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        rc = self._canvas_to_cell(cx, cy)
        if rc:
            self.coord_label.config(text=f"行{rc[0]+1}, 列{rc[1]+1}")
        else:
            self.coord_label.config(text="")

    def _on_click(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        rc = self._canvas_to_cell(cx, cy)
        if rc:
            self.selected_cell = rc
            self.on_update("cell_select", rc)
            p = self.project
            cell = p.get_cell(*rc)
            if cell and cell.crop_id is not None:
                self.drag_info = {
                    "start_x": cx,
                    "start_y": cy,
                    "cell": rc,
                    "orig_offset": (cell.offset_x, cell.offset_y)
                }
            else:
                self.drag_info = None
            self.redraw()

    def _on_mouse_drag(self, event):
        if not self.drag_info:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        dx = cx - self.drag_info["start_x"]
        dy = cy - self.drag_info["start_y"]
        row, col = self.drag_info["cell"]
        cell = self.project.get_cell(row, col)
        if cell is None:
            return
        orig_x, orig_y = self.drag_info["orig_offset"]
        cell.offset_x = int(orig_x + dx / self.zoom)
        cell.offset_y = int(orig_y + dy / self.zoom)
        self.on_update("cell_select", (row, col))
        self.redraw()

    def _on_mouse_up(self, event):
        self.drag_info = None

    def redraw(self):
        self.canvas.delete("all")
        p = self.project
        cw, ch = p.cell_size()
        zw = cw * self.zoom
        zh = ch * self.zoom
        total_w = p.sheet_w * self.zoom
        total_h = p.sheet_h * self.zoom

        # チェッカーボード
        cs = 12
        for r in range(int(total_h / cs) + 1):
            for c in range(int(total_w / cs) + 1):
                color = "#2a2a2a" if (r+c) % 2 == 0 else "#1e1e1e"
                self.canvas.create_rectangle(c*cs, r*cs, (c+1)*cs, (r+1)*cs,
                                             fill=color, outline="")

        # シート外枠
        self.canvas.create_rectangle(0, 0, total_w, total_h,
                                     outline="#333355", width=2)

        # セル描画
        for row in range(p.rows):
            for col in range(p.cols):
                x0 = col * zw
                y0 = row * zh
                x1 = x0 + zw
                y1 = y0 + zh

                cell = p.get_cell(row, col)
                is_sel = self.selected_cell == (row, col)

                # 背景
                bg = "#252540" if is_sel else "#111122"
                self.canvas.create_rectangle(x0, y0, x1, y1,
                                             fill=bg, outline="#2a2a4a", width=1)

                if cell and cell.crop_id is not None:
                    crop = p.get_crop(cell.crop_id)
                    if crop:
                        ci = self.img_man.get_crop_image(crop)
                        if ci:
                            # セル中央に配置 + オフセット
                            disp_w = int(ci.width * cell.scale * self.zoom)
                            disp_h = int(ci.height * cell.scale * self.zoom)
                            cix = int(x0 + zw/2 - disp_w/2 + cell.offset_x*self.zoom)
                            ciy = int(y0 + zh/2 - disp_h/2 + cell.offset_y*self.zoom)
                            disp = ci.resize((max(1, disp_w), max(1, disp_h)), Image.NEAREST)
                            tk_ci = ImageTk.PhotoImage(disp)
                            self.canvas.create_image(cix, ciy, anchor=tk.NW, image=tk_ci)
                            # キャッシュ保持
                            if not hasattr(self, '_cell_imgs'):
                                self._cell_imgs = []
                            self._cell_imgs.append(tk_ci)

                # 選択ハイライト
                if is_sel:
                    self.canvas.create_rectangle(x0+1, y0+1, x1-1, y1-1,
                                                 outline="#f0c040", width=2)

                # 番号
                self.canvas.create_text(x0+3, y0+2,
                                        text=f"{row*p.cols+col}",
                                        anchor=tk.NW, fill="#444466",
                                        font=("Consolas", 7))

        # スクロール範囲
        self.canvas.config(scrollregion=(0, 0, total_w + 20, total_h + 20))
        if hasattr(self, '_cell_imgs'):
            self._cell_imgs = self._cell_imgs[-500:]  # メモリ管理


# ============================================================
# Main Application
# ============================================================

class SpriteSheetApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🎮 Sprite Sheet Editor")
        self.configure(bg="#1a1a2e")
        self.geometry("1280x820")

        self.project = Project()
        self.img_man = ImageManager()
        self.project_path = None

        self._build_menu()
        self._build_ui()
        self._refresh_all()

    # ------ Menu ------

    def _build_menu(self):
        menubar = tk.Menu(self, bg="#1a1a2e", fg="#e0e0e0",
                          activebackground="#4a90d9")
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0, bg="#1a1a2e", fg="#e0e0e0",
                            activebackground="#4a90d9")
        menubar.add_cascade(label="ファイル", menu=file_menu)
        file_menu.add_command(label="新規プロジェクト", command=self._new_project)
        file_menu.add_command(label="プロジェクトを開く", command=self._open_project)
        file_menu.add_command(label="プロジェクトを保存", command=self._save_project)
        file_menu.add_command(label="名前を付けて保存", command=self._save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="スプライトシートを出力", command=self._export_sheet)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self.quit)

        edit_menu = tk.Menu(menubar, tearoff=0, bg="#1a1a2e", fg="#e0e0e0",
                            activebackground="#4a90d9")
        menubar.add_cascade(label="編集", menu=edit_menu)
        edit_menu.add_command(label="シート設定", command=self._sheet_settings)
        edit_menu.add_command(label="自動配置 (全crops)", command=self._auto_arrange)
        edit_menu.add_command(label="選択セルをクリア", command=self._clear_selected_cell)
        edit_menu.add_command(label="全セルクリア", command=self._clear_all_cells)

    # ------ UI Build ------

    def _build_ui(self):
        # 左: コントロールパネル
        left = tk.Frame(self, bg="#1a1a2e", width=240)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=0)
        left.pack_propagate(False)
        self._build_left_panel(left)

        # セパレーター
        sep = tk.Frame(self, bg="#2a2a4a", width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y)

        # 右: シートエディター
        right = tk.Frame(self, bg="#0d0d1a")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_right_panel(right)

    def _build_left_panel(self, parent):
        # タイトル
        tk.Label(parent, text="🎮 SPRITE EDITOR", bg="#1a1a2e", fg="#4a90d9",
                 font=("Consolas", 12, "bold")).pack(pady=(12,4))

        # --- 画像読み込み ---
        sec = self._section(parent, "📁 画像ファイル")

        tk.Button(sec, text="+ 画像を追加", bg="#4a90d9", fg="white",
                  relief=tk.FLAT, padx=6, pady=5, cursor="hand2",
                  font=("Consolas", 9), command=self._add_images).pack(fill=tk.X, pady=2)

        self.file_listbox = tk.Listbox(sec, bg="#0d0d1a", fg="#c0c0e0",
                                        selectbackground="#4a90d9",
                                        font=("Consolas", 8), height=5,
                                        relief=tk.FLAT, highlightthickness=0)
        self.file_listbox.pack(fill=tk.X, pady=2)

        btn_row = tk.Frame(sec, bg="#1a1a2e")
        btn_row.pack(fill=tk.X)
        tk.Button(btn_row, text="✂ 切り取り編集", bg="#6a5acd", fg="white",
                  relief=tk.FLAT, padx=4, pady=3, cursor="hand2",
                  font=("Consolas", 8), command=self._open_crop_editor).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,1))
        tk.Button(btn_row, text="✕ 削除", bg="#c0392b", fg="white",
                  relief=tk.FLAT, padx=4, pady=3, cursor="hand2",
                  font=("Consolas", 8), command=self._remove_file).pack(side=tk.LEFT)

        # --- Crops一覧 ---
        sec2 = self._section(parent, "✂ 切り取り一覧")

        self.crop_listbox = tk.Listbox(sec2, bg="#0d0d1a", fg="#c0c0e0",
                                        selectbackground="#4a90d9",
                                        font=("Consolas", 8), height=8,
                                        relief=tk.FLAT, highlightthickness=0)
        self.crop_listbox.pack(fill=tk.X, pady=2)
        self.crop_listbox.bind("<Double-Button-1>", self._assign_crop_to_cell)

        tk.Label(sec2, text="↑ ダブルクリックで選択セルに配置", bg="#1a1a2e",
                 fg="#666688", font=("Consolas", 7)).pack()

        btn_row2 = tk.Frame(sec2, bg="#1a1a2e")
        btn_row2.pack(fill=tk.X, pady=2)
        tk.Button(btn_row2, text="配置", bg="#27ae60", fg="white",
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  font=("Consolas", 9), command=self._assign_crop_to_cell).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,1))
        tk.Button(btn_row2, text="自動全配置", bg="#e67e22", fg="white",
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  font=("Consolas", 9), command=self._auto_arrange).pack(side=tk.LEFT)

        # --- セル微調整 ---
        sec3 = self._section(parent, "🎯 選択セル 微調整")

        self.sel_info = tk.Label(sec3, text="セルを選択してください", bg="#1a1a2e",
                                  fg="#888", font=("Consolas", 8))
        self.sel_info.pack()

        adj = tk.Frame(sec3, bg="#1a1a2e")
        adj.pack(pady=4)

        btn2 = {"bg": "#2a2a4a", "fg": "#e0e0e0", "relief": tk.FLAT,
                "width": 3, "height": 1, "cursor": "hand2", "font": ("Consolas", 10)}

        tk.Button(adj, text="▲", **btn2,
                  command=lambda: self._adjust_offset(0,-1)).grid(row=0, column=1, padx=1, pady=1)
        tk.Button(adj, text="◄", **btn2,
                  command=lambda: self._adjust_offset(-1,0)).grid(row=1, column=0, padx=1, pady=1)
        tk.Button(adj, text="●", **btn2,
                  command=lambda: self._reset_offset()).grid(row=1, column=1, padx=1, pady=1)
        tk.Button(adj, text="►", **btn2,
                  command=lambda: self._adjust_offset(1,0)).grid(row=1, column=2, padx=1, pady=1)
        tk.Button(adj, text="▼", **btn2,
                  command=lambda: self._adjust_offset(0,1)).grid(row=2, column=1, padx=1, pady=1)

        step_frame = tk.Frame(sec3, bg="#1a1a2e")
        step_frame.pack()
        tk.Label(step_frame, text="移動量:", bg="#1a1a2e", fg="#aaa",
                 font=("Consolas", 8)).pack(side=tk.LEFT)
        self.step_var = tk.IntVar(value=1)
        tk.Spinbox(step_frame, from_=1, to=50, textvariable=self.step_var,
                   width=4, bg="#0d0d1a", fg="#e0e0e0", relief=tk.FLAT,
                   font=("Consolas", 9)).pack(side=tk.LEFT, padx=2)
        tk.Label(step_frame, text="px", bg="#1a1a2e", fg="#aaa",
                 font=("Consolas", 8)).pack(side=tk.LEFT)

        self.offset_label = tk.Label(sec3, text="offset: (0, 0)", bg="#1a1a2e",
                                      fg="#666688", font=("Consolas", 8))
        self.offset_label.pack()

        scale_frame = tk.Frame(sec3, bg="#1a1a2e")
        scale_frame.pack(pady=4)
        tk.Button(scale_frame, text="拡大", bg="#2a2a4a", fg="#e0e0e0",
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  font=("Consolas", 8), command=lambda: self._adjust_scale(10)).pack(side=tk.LEFT, padx=2)
        tk.Button(scale_frame, text="縮小", bg="#2a2a4a", fg="#e0e0e0",
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  font=("Consolas", 8), command=lambda: self._adjust_scale(-10)).pack(side=tk.LEFT, padx=2)
        tk.Button(scale_frame, text="リセット", bg="#555577", fg="white",
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  font=("Consolas", 8), command=self._reset_scale).pack(side=tk.LEFT, padx=2)

        self.scale_label = tk.Label(sec3, text="scale: 100%", bg="#1a1a2e",
                                    fg="#666688", font=("Consolas", 8))
        self.scale_label.pack()

        # --- シート情報 ---
        sec4 = self._section(parent, "📐 シート設定")
        self.sheet_info = tk.Label(sec4, text="", bg="#1a1a2e", fg="#888",
                                    font=("Consolas", 8), justify=tk.LEFT)
        self.sheet_info.pack(anchor=tk.W)
        tk.Button(sec4, text="⚙ 設定変更", bg="#555577", fg="white",
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  font=("Consolas", 9), command=self._sheet_settings).pack(fill=tk.X, pady=2)

        # --- 出力 ---
        sec5 = self._section(parent, "💾 出力")
        tk.Button(sec5, text="📤 スプライトシート出力", bg="#27ae60", fg="white",
                  relief=tk.FLAT, padx=6, pady=6, cursor="hand2",
                  font=("Consolas", 9, "bold"), command=self._export_sheet).pack(fill=tk.X, pady=2)

    def _section(self, parent, title):
        f = tk.Frame(parent, bg="#1a1a2e")
        f.pack(fill=tk.X, padx=8, pady=(8,2))
        tk.Label(f, text=title, bg="#1a1a2e", fg="#6a8abf",
                 font=("Consolas", 9, "bold")).pack(anchor=tk.W)
        sep = tk.Frame(f, bg="#2a2a4a", height=1)
        sep.pack(fill=tk.X, pady=(0,4))
        return f

    def _build_right_panel(self, parent):
        tk.Label(parent, text="スプライトシート", bg="#0d0d1a", fg="#4a90d9",
                 font=("Consolas", 10, "bold")).pack(anchor=tk.W, padx=8, pady=4)

        self.sheet_editor = SheetEditorPanel(parent, self.project, self.img_man,
                                              self._on_sheet_update)
        self.sheet_editor.pack(fill=tk.BOTH, expand=True)

    # ------ Event Handlers ------

    def _on_sheet_update(self, event, data):
        if event == "cell_select":
            row, col = data
            self._update_sel_info(row, col)

    def _update_sel_info(self, row, col):
        p = self.project
        cell = p.get_cell(row, col)
        if cell and cell.crop_id is not None:
            crop = p.get_crop(cell.crop_id)
            name = crop.label if crop else "?"
            self.sel_info.config(text=f"[行{row+1}, 列{col+1}] {name}",
                                 fg="#f0c040")
            self.offset_label.config(text=f"offset: ({cell.offset_x}, {cell.offset_y})")
            self.scale_label.config(text=f"scale: {int(cell.scale*100)}%")
        else:
            self.sel_info.config(text=f"[行{row+1}, 列{col+1}] 空", fg="#888")
            self.offset_label.config(text="offset: (0, 0)")
            self.scale_label.config(text="scale: 100%")

    def _adjust_offset(self, dx, dy):
        if self.sheet_editor.selected_cell is None:
            return
        row, col = self.sheet_editor.selected_cell
        cell = self.project.get_cell(row, col)
        if cell is None or cell.crop_id is None:
            return
        step = self.step_var.get()
        cell.offset_x += dx * step
        cell.offset_y += dy * step
        self._update_sel_info(row, col)
        self.sheet_editor.redraw()

    def _reset_offset(self):
        if self.sheet_editor.selected_cell is None:
            return
        row, col = self.sheet_editor.selected_cell
        cell = self.project.get_cell(row, col)
        if cell:
            cell.offset_x = 0
            cell.offset_y = 0
            self._update_sel_info(row, col)
            self.sheet_editor.redraw()

    def _adjust_scale(self, delta_percent):
        if self.sheet_editor.selected_cell is None:
            return
        row, col = self.sheet_editor.selected_cell
        cell = self.project.get_cell(row, col)
        if cell is None or cell.crop_id is None:
            return
        cell.scale = max(0.1, min(10.0, cell.scale * (1 + delta_percent / 100.0)))
        self._update_sel_info(row, col)
        self.sheet_editor.redraw()

    def _reset_scale(self):
        if self.sheet_editor.selected_cell is None:
            return
        row, col = self.sheet_editor.selected_cell
        cell = self.project.get_cell(row, col)
        if cell:
            cell.scale = 1.0
            self._update_sel_info(row, col)
            self.sheet_editor.redraw()

    # ------ File Operations ------

    def _add_images(self):
        paths = filedialog.askopenfilenames(
            title="画像ファイルを選択",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("全て", "*.*")]
        )
        for p in paths:
            if p not in self.project.loaded_files:
                self.project.loaded_files.append(p)
        self._refresh_all()

    def _remove_file(self):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        path = self.project.loaded_files[idx]
        if messagebox.askyesno("確認", f"'{os.path.basename(path)}' をプロジェクトから削除しますか？\n関連する切り取りも削除されます。"):
            # 関連crops削除
            removed_ids = {c.id for c in self.project.crops if c.source_file == path}
            self.project.crops = [c for c in self.project.crops if c.source_file != path]
            self.project.cells = [c for c in self.project.cells if c.crop_id not in removed_ids]
            self.project.loaded_files.pop(idx)
            self._refresh_all()

    def _open_crop_editor(self):
        sel = self.file_listbox.curselection()
        if not sel:
            messagebox.showinfo("情報", "画像ファイルを選択してください")
            return
        path = self.project.loaded_files[sel[0]]
        CropEditorPanel(self, self.project, self.img_man, path, self._refresh_all)

    def _assign_crop_to_cell(self, event=None):
        sel_crop = self.crop_listbox.curselection()
        if not sel_crop:
            messagebox.showinfo("情報", "Cropを選択してください")
            return
        if self.sheet_editor.selected_cell is None:
            messagebox.showinfo("情報", "シートのセルを選択してください")
            return
        crop = self.project.crops[sel_crop[0]]
        row, col = self.sheet_editor.selected_cell
        self.project.set_cell(row, col, crop.id)
        self._update_sel_info(row, col)
        self.sheet_editor.redraw()

    def _auto_arrange(self):
        p = self.project
        if not p.crops:
            messagebox.showinfo("情報", "切り取りがありません")
            return
        if not messagebox.askyesno("自動配置", f"{len(p.crops)}個のCropを左上から順に自動配置しますか？"):
            return
        p.cells.clear()
        for i, crop in enumerate(p.crops):
            row = i // p.cols
            col = i % p.cols
            if row < p.rows:
                ci = self.img_man.get_crop_image(crop)
                scale = 1.0
                if ci is not None:
                    cw, ch = p.cell_size()
                    scale = min(1.0, cw / ci.width, ch / ci.height)
                p.set_cell(row, col, crop.id, scale=scale)
        self.sheet_editor.redraw()
        messagebox.showinfo("完了", f"{min(len(p.crops), p.rows*p.cols)}個のCropを配置しました")

    def _clear_selected_cell(self):
        if self.sheet_editor.selected_cell is None:
            return
        row, col = self.sheet_editor.selected_cell
        self.project.clear_cell(row, col)
        self._update_sel_info(row, col)
        self.sheet_editor.redraw()

    def _clear_all_cells(self):
        if messagebox.askyesno("確認", "全セルをクリアしますか？"):
            self.project.cells.clear()
            self.sheet_editor.redraw()

    # ------ Sheet Settings ------

    def _sheet_settings(self):
        dlg = tk.Toplevel(self)
        dlg.title("シート設定")
        dlg.configure(bg="#1a1a2e")
        dlg.grab_set()
        dlg.resizable(False, False)

        p = self.project
        fields = [
            ("シート幅 (px)", p.sheet_w),
            ("シート高さ (px)", p.sheet_h),
            ("列数", p.cols),
            ("行数", p.rows),
        ]
        vars_ = []
        for i, (label, val) in enumerate(fields):
            tk.Label(dlg, text=label, bg="#1a1a2e", fg="#c0c0e0",
                     font=("Consolas", 9)).grid(row=i, column=0, padx=12, pady=4, sticky=tk.W)
            v = tk.IntVar(value=val)
            tk.Entry(dlg, textvariable=v, bg="#0d0d1a", fg="#e0e0e0",
                     relief=tk.FLAT, font=("Consolas", 10), width=8).grid(row=i, column=1, padx=8, pady=4)
            vars_.append(v)

        def apply():
            try:
                p.sheet_w = max(1, vars_[0].get())
                p.sheet_h = max(1, vars_[1].get())
                p.cols = max(1, vars_[2].get())
                p.rows = max(1, vars_[3].get())
                self._refresh_all()
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("エラー", str(e))

        btn_f = tk.Frame(dlg, bg="#1a1a2e")
        btn_f.grid(row=len(fields), column=0, columnspan=2, pady=8)
        tk.Button(btn_f, text="適用", bg="#27ae60", fg="white",
                  relief=tk.FLAT, padx=12, pady=4, command=apply).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_f, text="キャンセル", bg="#555577", fg="white",
                  relief=tk.FLAT, padx=12, pady=4, command=dlg.destroy).pack(side=tk.LEFT, padx=4)

    # ------ Project Save/Load ------

    def _new_project(self):
        if messagebox.askyesno("新規", "現在のプロジェクトを破棄して新規作成しますか？"):
            self.project = Project()
            self.project_path = None
            self.title("🎮 Sprite Sheet Editor")
            self._refresh_all()

    def _save_project(self):
        if self.project_path:
            self._do_save(self.project_path)
        else:
            self._save_project_as()

    def _save_project_as(self):
        path = filedialog.asksaveasfilename(
            title="プロジェクトを保存",
            defaultextension=".ssep",
            filetypes=[("Sprite Sheet Editor Project", "*.ssep"), ("JSON", "*.json")]
        )
        if path:
            self._do_save(path)

    def _do_save(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.project.to_dict(), f, ensure_ascii=False, indent=2)
            self.project_path = path
            self.title(f"🎮 Sprite Sheet Editor - {os.path.basename(path)}")
            messagebox.showinfo("保存完了", f"保存しました:\n{path}")
        except Exception as e:
            messagebox.showerror("保存エラー", str(e))

    def _open_project(self):
        path = filedialog.askopenfilename(
            title="プロジェクトを開く",
            filetypes=[("Sprite Sheet Editor Project", "*.ssep"), ("JSON", "*.json")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.project = Project.from_dict(data)
            self.project_path = path
            self.title(f"🎮 Sprite Sheet Editor - {os.path.basename(path)}")
            self.sheet_editor.project = self.project
            self.sheet_editor.img_man = self.img_man
            self._refresh_all()
            messagebox.showinfo("読み込み完了", f"読み込みました:\n{path}")
        except Exception as e:
            messagebox.showerror("読み込みエラー", str(e))

    # ------ Export ------

    def _export_sheet(self):
        p = self.project
        path = filedialog.asksaveasfilename(
            title="スプライトシートを出力",
            defaultextension=".png",
            filetypes=[("PNG (透明)", "*.png")]
        )
        if not path:
            return
        try:
            sheet = Image.new("RGBA", (p.sheet_w, p.sheet_h), (0, 0, 0, 0))
            cw, ch = p.cell_size()

            placed = 0
            for cell in p.cells:
                if cell.crop_id is None:
                    continue
                crop = p.get_crop(cell.crop_id)
                if crop is None:
                    continue
                ci = self.img_man.get_crop_image(crop)
                if ci is None:
                    continue
                if cell.scale != 1.0:
                    ci = ci.resize((max(1, int(ci.width * cell.scale)),
                                    max(1, int(ci.height * cell.scale))), Image.NEAREST)

                # セル中央座標
                cx = cell.col * cw + cw / 2
                cy = cell.row * ch + ch / 2

                # 配置位置（中央揃え + オフセット）
                px = int(cx - ci.width / 2 + cell.offset_x)
                py = int(cy - ci.height / 2 + cell.offset_y)

                sheet.paste(ci, (px, py), ci)
                placed += 1

            sheet.save(path, "PNG")
            messagebox.showinfo("出力完了",
                                f"スプライトシートを出力しました:\n{path}\n\n"
                                f"サイズ: {p.sheet_w}×{p.sheet_h}px\n"
                                f"配置数: {placed}")
        except Exception as e:
            messagebox.showerror("出力エラー", str(e))

    # ------ Refresh ------

    def _refresh_all(self):
        p = self.project
        # ファイルリスト
        self.file_listbox.delete(0, tk.END)
        for f in p.loaded_files:
            self.file_listbox.insert(tk.END, os.path.basename(f))

        # Cropリスト
        self.crop_listbox.delete(0, tk.END)
        for c in p.crops:
            src = os.path.basename(c.source_file)
            self.crop_listbox.insert(tk.END, f"{c.label} [{src}] {c.w}×{c.h}")

        # シート情報
        cw, ch = p.cell_size()
        self.sheet_info.config(
            text=f"サイズ: {p.sheet_w}×{p.sheet_h}px\n"
                 f"グリッド: {p.cols}×{p.rows}\n"
                 f"セルサイズ: {cw:.0f}×{ch:.0f}px\n"
                 f"Crops: {len(p.crops)}\n"
                 f"配置済み: {len([c for c in p.cells if c.crop_id])}"
        )

        self.sheet_editor.project = p
        self.sheet_editor.redraw()


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    try:
        from PIL import Image, ImageTk
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
        from PIL import Image, ImageTk

    app = SpriteSheetApp()
    app.mainloop()