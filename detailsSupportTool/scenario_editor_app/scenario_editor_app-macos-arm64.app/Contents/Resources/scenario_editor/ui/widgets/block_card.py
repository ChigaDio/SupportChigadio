"""遷移エディタのノード(ブロック)カード (ScenarioEventTransition.js: BlockCardInner)。

カードは見た目だけを持ち、操作はすべて h (ハンドラ集) 経由で TransitionPage へ渡す。
update_view() で既存カードを使い回す(100件超でも編集したカードだけ描き直す)。
"""
from __future__ import annotations


from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QColor, QDrag
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton,
                               QVBoxLayout, QWidget, QWidgetAction)

from ...core import subgroup_setting as SGS
from ...core import transition_ops as T
from ...core import validation as V
from .. import icons, theme
from . import common as C

MIME = "application/x-scenario-node"


def tint_colors(tint, dark=None):
    """core の tint(hsl 文字列) を、テーマに合わせた Qt の色にする。None なら色なし。"""
    if not tint:
        return None
    dark = theme.current_theme() == "dark" if dark is None else dark
    h = tint["hue"] / 360.0
    if dark:
        bg = QColor.fromHslF(h, 0.30, 0.17)
        strong = QColor.fromHslF(h, 0.32, 0.21)
    else:
        bg = QColor.fromHslF(h, 0.75, 0.96)
        strong = QColor.fromHslF(h, 0.65, 0.92)
    accent = QColor.fromHslF(h, 0.60, 0.50)
    return {"bg": bg.name(), "bgStrong": strong.name(), "accent": accent.name(), "hue": tint["hue"]}


def swatch_color(hue):
    return QColor.fromHslF(hue / 360.0, 0.60, 0.55).name()


def sub_header_color():
    return "#7c5cd6" if theme.current_theme() == "dark" else "#6d4acb"


class _Header(QFrame):
    """ドラッグで並び替えを始められるヘッダ。"""

    def __init__(self, card):
        super().__init__()
        self.card = card
        self._press = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            if (e.position().toPoint() - self._press).manhattanLength() >= 8:
                self._press = None
                self.card.start_drag()
                return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._press = None
        super().mouseReleaseEvent(e)


def _hbtn(icon_name, tip, cb):
    b = QToolButton()
    b.setIcon(icons.icon(icon_name, "#ffffff"))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(lambda _=False: cb())
    return b


class BlockCard(QFrame):
    def __init__(self, h, canvas, parent=None):
        super().__init__(parent)
        self.h, self.canvas = h, canvas
        self.setObjectName("blockCard")
        self.setAcceptDrops(True)
        self.node = None
        self.v = None
        self.collapsed = False
        self._drop_hint = False
        self._edges_ref = None
        self._sig = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- ヘッダ
        self.head = _Header(self)
        self.head.setObjectName("blockHead")
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(10, 6, 8, 6)
        hl.setSpacing(6)
        self.check = QCheckBox()
        self.check.toggled.connect(lambda _c: self.h.toggle_select(self.node["id"]))
        hl.addWidget(self.check)
        grip = QLabel()
        grip.setPixmap(icons.icon("drag", "#ffffffaa").pixmap(14, 14))
        hl.addWidget(grip)
        self.id_chip = QPushButton()
        self.id_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.id_chip.setStyleSheet("QPushButton{background:rgba(255,255,255,0.22);color:#fff;border:none;border-radius:9px;"
                                   "padding:1px 9px;font-weight:700;font-size:12px;}QPushButton:hover{background:rgba(255,255,255,0.36);}")
        self.id_chip.clicked.connect(lambda: self.h.edit_id(self.node["id"]))
        hl.addWidget(self.id_chip)
        self.desc = C.ElidedLabel("")
        self.desc.setStyleSheet("color:rgba(255,255,255,0.92);font-size:12px;background:transparent;")
        hl.addWidget(self.desc, 1)
        self.role_chip = self._pill("", "rgba(255,255,255,0.25)")
        self.wait_chip = self._pill("WAIT", "#e0a21b", "keyboard")
        self.issue_chip = self._pill("", "#d14b4b", "warn")
        for w in (self.role_chip, self.wait_chip, self.issue_chip):
            hl.addWidget(w)
        self.btn_setting = _hbtn("tune", "サブグループ設定（入力待ち・追加フィールドを編集）", lambda: self.h.open_setting(self.node["id"]))
        self.btn_up = _hbtn("up", "上へ", lambda: self.h.reorder(self.v.index, self.v.index - 1))
        self.btn_down = _hbtn("down", "下へ", lambda: self.h.reorder(self.v.index, self.v.index + 1))
        self.btn_fold = _hbtn("collapse", "折り畳み", self.toggle_collapsed)
        self.btn_more = _hbtn("more", "メニュー", self.open_menu)
        for b in (self.btn_setting, self.btn_up, self.btn_down, self.btn_fold, self.btn_more):
            hl.addWidget(b)
        lay.addWidget(self.head)

        # --- ボディ
        self.bodyw = QWidget()
        bl = QVBoxLayout(self.bodyw)
        bl.setContentsMargins(12, 8, 12, 10)
        bl.setSpacing(6)
        self.conn_host = QWidget()
        self.conn_lay = C.FlowLayout(self.conn_host, spacing=4)
        self.conn_lay.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.conn_host)
        self.setting_row = QWidget()
        sr = QHBoxLayout(self.setting_row)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.setSpacing(8)
        self.wait_box = QFrame()
        wb = QHBoxLayout(self.wait_box)
        wb.setContentsMargins(8, 2, 4, 2)
        wb.setSpacing(6)
        self.wait_icon = QLabel()
        self.wait_label = QLabel("入力待ち")
        self.wait_switch = C.Switch(False, on_color=theme.color("warn"))
        self.wait_switch.toggled.connect(self._wait_toggled)
        wb.addWidget(self.wait_icon)
        wb.addWidget(self.wait_label)
        wb.addWidget(self.wait_switch)
        sr.addWidget(self.wait_box)
        self.more_btn = C.button("その他の設定", "ghost", "tune", on_click=lambda: self.h.open_setting(self.node["id"]), small=True)
        sr.addWidget(self.more_btn)
        self.group_note = C.label("グループ直下のRole用", "muted")
        self.group_note.setStyleSheet("font-size:10px;")
        sr.addWidget(self.group_note)
        sr.addStretch(1)
        bl.addWidget(self.setting_row)
        self.roles_host = QWidget()
        self.roles_lay = QVBoxLayout(self.roles_host)
        self.roles_lay.setContentsMargins(0, 0, 0, 0)
        self.roles_lay.setSpacing(3)
        bl.addWidget(self.roles_host)
        act = QHBoxLayout()
        act.setSpacing(6)
        self.btn_sub = C.button("SubGroup", icon_name="graph", on_click=lambda: self.h.open_subgroup(self.node["id"]), small=True)
        self.btn_role = C.button("Role追加", icon_name="plus", on_click=lambda: self.h.open_role_select(self.node["id"]), small=True)
        self.btn_data = C.button("データ入力", "primary", on_click=lambda: self.h.open_role_data(self.node["id"]), small=True)
        self.btn_conn = C.button("接続", icon_name="link", on_click=self.connect_dialog, small=True)
        for b in (self.btn_sub, self.btn_role, self.btn_data):
            act.addWidget(b, 1)
        act.addWidget(self.btn_conn)
        bl.addLayout(act)
        lay.addWidget(self.bodyw)

    # ---------------------------------------------------------------- 部品
    def _pill(self, text, bg, icon_name=None):
        lb = QLabel(text)
        lb.setStyleSheet(f"QLabel{{background:{bg};color:#fff;border-radius:8px;padding:0 7px;font-size:10px;font-weight:700;}}")
        lb.hide()
        return lb

    # ---------------------------------------------------------------- 更新
    def update_view(self, node, v):
        """v: SimpleNamespace(index,total,is_sub,edges,all_ids,path,color_key,auto_tint,selected,issues,
                              schema,defaults,has_prev,has_next)"""
        self.node, self.v = node, v
        nid = node["id"]
        d = node.get("data") if isinstance(node.get("data"), dict) else {}
        roles = d.get("roles") or []
        dark = theme.current_theme() == "dark"
        tint = tint_colors(T.get_node_tint(v.path, v.color_key), dark)
        self.tint = tint
        head_bg = sub_header_color() if v.is_sub else theme.color("accent")
        head_fg = "#ffffff"
        border = head_bg
        css = f"QFrame#blockCard{{background:{tint['bg'] if tint else theme.color('bg2')};border:2px solid {border};border-radius:10px;"
        if tint:
            css += f"border-left:8px solid {tint['accent']};"
        css += "}"
        if v.selected:
            css = css.replace(f"border:2px solid {border}", f"border:3px solid {theme.color('text')}")
        if self._drop_hint:
            css += f"QFrame#blockCard{{border:2px dashed {theme.color('ok')};}}"
        self.setStyleSheet(css + f"QFrame#blockHead{{background:{head_bg};border-top-left-radius:7px;border-top-right-radius:7px;}}"
                           "QFrame#blockHead QCheckBox{background:transparent;}")
        self.check.blockSignals(True)
        self.check.setChecked(bool(v.selected))
        self.check.blockSignals(False)
        self.id_chip.setText(str(nid))
        text = d.get("description") or ("SubGroup Node" if v.is_sub else "Group Node")
        self.desc.set_full_text(text.replace("\n", " / "))
        self.desc.setToolTip(d.get("description") if d.get("description") and "\n" in d["description"] else "")
        self.role_chip.setVisible(bool(roles))
        self.role_chip.setText(f"{len(roles)} Role")
        enabled = bool(v.schema)
        setting = SGS.get_node_setting(node, v.schema, v.defaults) if enabled else []
        wait = enabled and bool(SGS.get_setting_value(setting, SGS.IS_WAIT_KEY_FIELD, False))
        self.wait_chip.setVisible(wait)
        extra = enabled and len((v.schema or {}).get("fields") or []) > 1
        issues = v.issues or []
        self.issue_chip.setVisible(bool(issues))
        if issues:
            lv = V.worst_level(issues)
            self.issue_chip.setText(str(len(issues)))
            col = {"error": theme.color("err"), "warn": theme.color("warn")}.get(lv, theme.color("info"))
            self.issue_chip.setStyleSheet(f"QLabel{{background:{col};color:#fff;border-radius:8px;padding:0 7px;font-size:10px;font-weight:700;}}")
            self.issue_chip.setToolTip("\n".join(f"{'✖' if i['level'] == 'error' else '▲' if i['level'] == 'warn' else 'ℹ'} {i['message']}" for i in issues))
        self.btn_setting.setVisible(enabled)
        self.btn_setting.setIcon(icons.icon("settings" if extra else "tune", "#ffd54f" if wait else "#ffffff"))
        self.btn_up.setEnabled(v.index > 0)
        self.btn_down.setEnabled(v.index < v.total - 1)

        # 接続バッジ
        C.clear_layout(self.conn_lay)
        mine = [e for e in v.edges if e.get("source") == nid]
        self.conn_host.setVisible(bool(mine))
        for e in mine:
            chip = C.Chip(f"→{e.get('target')}", "info", clickable=True, tooltip="クリックで接続を削除")
            chip.clicked.connect(lambda e=e: self.h.remove_edge(e))
            self.conn_lay.addWidget(chip)

        # 設定行
        self.setting_row.setVisible(enabled)
        if enabled:
            self.wait_switch.blockSignals(True)
            self.wait_switch.setChecked(wait)
            self.wait_switch.blockSignals(False)
            self._style_wait(wait)
            self.more_btn.setVisible(extra)
            self.group_note.setVisible(not v.is_sub)

        # Role 行
        C.clear_layout(self.roles_lay)
        self.roles_host.setVisible(bool(roles))
        for r in roles:
            row = QFrame()
            row.setProperty("card", "flat")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 3, 4, 3)
            rl.setSpacing(6)
            nm = C.ElidedLabel(r.get("name") or "")
            nm.setStyleSheet("font-weight:700;font-size:12px;")
            rl.addWidget(nm, 1)
            if r.get("branchType") and r["branchType"] != "General":
                rl.addWidget(C.Chip(str(r["branchType"]), "true"))
            rl.addWidget(C.icon_button("trash", "削除", lambda uid=r.get("uniqueId"): self.h.delete_role(nid, uid), color=theme.color("err"), size=13))
            self.roles_lay.addWidget(row)

        self.btn_sub.setVisible(not v.is_sub)
        self.btn_role.setVisible(v.is_sub)
        self.btn_data.setVisible(v.is_sub and bool(roles))
        self.bodyw.setVisible(not self.collapsed)
        self.btn_fold.setIcon(icons.icon("expand" if self.collapsed else "collapse", "#ffffff"))
        self.btn_fold.setToolTip("展開" if self.collapsed else "折り畳み")

    def _style_wait(self, on):
        c = theme.color("warn")
        self.wait_box.setStyleSheet(
            f"QFrame{{border:1px solid {c if on else theme.color('border')};border-radius:12px;"
            f"background:{theme.color('warnSoft') if on else 'transparent'};}}QLabel{{border:none;background:transparent;}}")
        self.wait_icon.setPixmap(icons.icon("keyboard", c if on else theme.color("faint")).pixmap(16, 16))
        self.wait_label.setStyleSheet(f"font-size:11px;font-weight:{700 if on else 500};color:{c if on else theme.color('muted')};")
        self.wait_switch.setToolTip("入力待ちON：このサブグループの実行中/後にキー入力を待ちます（is_wait_key=true）" if on
                                    else "入力待ちOFF（is_wait_key=false）。ONにするとキー入力を待ちます")

    def _wait_toggled(self, on):
        v = self.v
        setting = SGS.get_node_setting(self.node, v.schema, v.defaults)
        self.h.save_setting(self.node["id"], SGS.set_setting_value(setting, SGS.IS_WAIT_KEY_FIELD, on, v.schema, v.defaults))

    # ---------------------------------------------------------------- 折り畳み
    def toggle_collapsed(self):
        self.set_collapsed(not self.collapsed)

    def set_collapsed(self, value):
        self.collapsed = bool(value)
        self.bodyw.setVisible(not self.collapsed)
        self.btn_fold.setIcon(icons.icon("expand" if self.collapsed else "collapse", "#ffffff"))
        self.btn_fold.setToolTip("展開" if self.collapsed else "折り畳み")

    # ---------------------------------------------------------------- メニュー
    def open_menu(self):
        nid = self.node["id"]
        m = QMenu(self)
        m.addAction(icons.icon("copy"), "コピー", lambda: self.h.copy(nid))
        m.addAction(icons.icon("edit"), "ID / 説明を編集", lambda: self.h.edit_id(nid))
        m.addAction(icons.icon("link"), "接続を追加", self.connect_dialog)
        m.addAction(icons.icon("right"), "別グループへ移動", self.move_dialog)
        m.addAction(icons.icon("build"), "ここから以降のインデックスを調整…", lambda: self.h.open_index_tools(nid))
        clip = self.h.clipboard_count()
        a = m.addAction(icons.icon("paste"), f"Roleを貼り付け{f'（{clip}件）' if clip else ''}", lambda: self.h.paste_roles(nid))
        a.setEnabled(clip > 0)
        m.addSeparator()
        wa = QWidgetAction(m)
        wa.setDefaultWidget(color_palette(self.v.color_key, lambda key: (m.close(), self.h.set_colors([self.v.path], key)),
                                          "背景色（この画面のみ・このPCに保存）"))
        m.addAction(wa)
        m.addSeparator()
        d = m.addAction(icons.icon("trash", theme.color("err")), "削除", lambda: self.h.delete(nid))
        m.exec(self.btn_more.mapToGlobal(QPoint(0, self.btn_more.height())))

    def connect_dialog(self):
        nid = self.node["id"]
        others = [i for i in self.v.all_ids if i != nid]
        dlg = C.FormDialog(self, f"接続先を指定（ノード {nid} から）", [("target", "接続先ノードID", "text", "")],
                           info=f"利用可能: {', '.join(others) or 'なし'}", ok_text="接続")
        if dlg.exec():
            self.h.connect(nid, dlg.values()["target"])

    def move_dialog(self):
        dlg = C.FormDialog(self, "別グループへ移動", [("target", "移動先 グループID", "text", "")],
                           info="移動するとIDが更新されます", ok_text="移動")
        if dlg.exec():
            tid = dlg.values()["target"].strip()
            if tid:
                self.h.move_to_group(self.node["id"], tid)

    # ---------------------------------------------------------------- ドラッグ&ドロップ
    def start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME, str(self.node["id"]).encode("utf-8"))
        drag.setMimeData(mime)
        pm = self.grab()
        pm = pm.scaledToWidth(min(pm.width(), 520), Qt.TransformationMode.SmoothTransformation)
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(20, 14))
        drag.exec(Qt.DropAction.MoveAction)

    def _set_hint(self, on):
        if self._drop_hint != on:
            self._drop_hint = on
            if self.node is not None:
                self.update_view(self.node, self.v)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME) and bytes(e.mimeData().data(MIME)).decode("utf-8") != str(self.node["id"]):
            e.acceptProposedAction()
            self._set_hint(True)
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
            self.canvas.autoscroll(self.mapToGlobal(e.position().toPoint()))

    def dragLeaveEvent(self, e):
        self._set_hint(False)

    def dropEvent(self, e):
        self._set_hint(False)
        if not e.mimeData().hasFormat(MIME):
            return
        dragged = bytes(e.mimeData().data(MIME)).decode("utf-8")
        e.acceptProposedAction()
        if dragged != str(self.node["id"]):
            self.h.reorder_by_id(dragged, self.node["id"])


def color_palette(current_key, on_pick, title):
    """背景色パレット (自動 / プリセット / 色なし)。"""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(12, 6, 12, 8)
    lay.setSpacing(4)
    lay.addWidget(C.label(title, "muted"))
    host = QWidget()
    fl = C.FlowLayout(host, spacing=5)
    fl.setContentsMargins(0, 0, 0, 0)

    def dot(bg, tip, key, border_on):
        b = QPushButton()
        b.setFixedSize(22, 22)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{bg};border-radius:11px;border:2px solid {theme.color('text') if border_on else theme.color('border')};}}")
        b.clicked.connect(lambda _=False: on_pick(key))
        fl.addWidget(b)
    conic = ("qconicalgradient(cx:0.5, cy:0.5, angle:0, stop:0 #e5645a, stop:0.17 #e5d25a, stop:0.33 #6ee55a, stop:0.5 #5ae5d9, "
             "stop:0.67 #5a6ee5, stop:0.83 #d25ae5, stop:1 #e5645a)")
    dot(conic, "自動", None, not current_key)
    for p in T.NODE_COLOR_PRESETS:
        dot(swatch_color(p["hue"]), p["label"], p["key"], current_key == p["key"])
    dot("#ffffff", "色なし", "none", current_key == "none")
    lay.addWidget(host)
    w.setFixedWidth(240)
    return w
