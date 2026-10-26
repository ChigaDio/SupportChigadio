"""RoleForm の葉っぱの編集部品 (数値 / ビット / カラー / ベジェ / 音声・テキストのインデックス選択 ...)。

すべて ``valueChanged(object)`` / ``value()`` / ``set_value(v)`` を持つ。``set_value`` はシグナルを出さない。
ロジックは core/role_form.py (元JSとの差分テスト済み) に置き、ここは描画と入力だけを担当する。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from ...api.client import ApiError
from ...core import role_form as RF
from ...core.dsl import js_number_to_string, js_string
from .. import icons, theme
from ..async_ import run_async
from . import common as C


# ======================================================================= 数値
class NumericEdit(QLineEdit):
    """マイナス・小数点対応の数値入力 (JS の NumericInput。文字列で保持し、途中入力を許す)。"""
    valueChanged = Signal(object)

    def __init__(self, value=0, is_float=False, placeholder="", parent=None):
        super().__init__(parent)
        self.is_float = is_float
        self._last = ""
        self._value = 0
        self.setPlaceholderText(placeholder)
        self.setMinimumWidth(60)
        self.set_value(value)
        self.textEdited.connect(self._edited)
        self.editingFinished.connect(self._finished)

    def _fmt(self, v):
        try:
            return js_number_to_string(v if v is not None else 0)
        except Exception:  # noqa: BLE001
            return "0"

    def set_value(self, v):
        """外部からの値変化に追従(ただし入力中の途中文字列は上書きしない)。"""
        v = 0 if v is None or isinstance(v, bool) else v
        if not isinstance(v, (int, float)):
            try:
                v = float(v) if self.is_float else int(float(v))
            except (TypeError, ValueError):
                v = 0
        cur = RF._parse_num(self.text(), self.is_float)
        if cur is not None and cur == v and self.text() != "":
            self._value = v
            return
        self._value = v
        self._last = self._fmt(v)
        self.setText(self._last)

    def value(self):
        return self._value

    def _edited(self, raw):
        allowed, (emit, parsed) = RF.numeric_input_change(raw, self.is_float)
        if not allowed:
            pos = self.cursorPosition()
            self.setText(self._last)
            self.setCursorPosition(max(0, pos - 1))
            return
        self._last = raw
        if emit:
            self._value = parsed
            self.valueChanged.emit(parsed)

    def _finished(self):
        text, value = RF.numeric_input_blur(self.text(), self.is_float)
        self._last = text
        self.setText(text)
        if value != self._value:
            self._value = value
            self.valueChanged.emit(value)


class VectorEditor(QWidget):
    valueChanged = Signal(object)

    def __init__(self, type_lower, value, parent=None):
        super().__init__(parent)
        self.labels = RF.VECTOR_AXIS_LABELS[type_lower]
        self._v = list(value) if isinstance(value, list) else [0] * len(self.labels)
        self._v += [0] * (len(self.labels) - len(self._v))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.edits = []
        for i, ax in enumerate(self.labels):
            box = QVBoxLayout()
            box.setSpacing(1)
            lb = QLabel(ax)
            lb.setProperty("role", "muted")
            e = NumericEdit(self._v[i] if i < len(self._v) else 0, True)
            e.valueChanged.connect(lambda val, idx=i: self._chg(idx, val))
            box.addWidget(lb)
            box.addWidget(e)
            lay.addLayout(box, 1)
            self.edits.append(e)

    def _chg(self, i, val):
        self._v[i] = val
        self.valueChanged.emit(list(self._v))

    def value(self):
        return list(self._v)

    def set_value(self, v):
        v = v if isinstance(v, list) else [0] * len(self.labels)
        self._v = [(v[i] if i < len(v) and v[i] is not None else 0) for i in range(len(self.labels))]
        for e, x in zip(self.edits, self._v):
            e.set_value(x)


# ======================================================================= 文字列
class StringEditor(QPlainTextEdit):
    """1〜8行で伸びる複数行テキスト。"""
    valueChanged = Signal(object)

    def __init__(self, value="", parent=None):
        super().__init__(parent)
        self.setTabChangesFocus(True)
        self.setPlainText("" if value is None else js_string(value))
        self.textChanged.connect(self._chg)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._fit()

    def _fit(self):
        fm = self.fontMetrics()
        lines = max(1, min(8, self.document().blockCount()))
        # 折り返しで増える行も考慮して文書の高さを使う
        doc_h = int(self.document().size().height()) if self.viewport().width() > 0 else fm.lineSpacing() * lines
        h = max(fm.lineSpacing() * 1, min(doc_h, fm.lineSpacing() * 8)) + 14
        self.setFixedHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _chg(self):
        self._fit()
        self.valueChanged.emit(self.toPlainText())

    def value(self):
        return self.toPlainText()

    def set_value(self, v):
        t = "" if v is None else js_string(v)
        if t != self.toPlainText():
            self.blockSignals(True)
            self.setPlainText(t)
            self.blockSignals(False)
            self._fit()


class LineValueEditor(QLineEdit):
    valueChanged = Signal(object)

    def __init__(self, value="", max_len=None, parent=None):
        super().__init__(parent)
        self.setText("" if value is None else js_string(value))
        if max_len:
            self.setMaxLength(max_len)
        self.textEdited.connect(lambda t: self.valueChanged.emit(t))

    def value(self):
        return self.text()

    def set_value(self, v):
        t = "" if v is None else js_string(v)
        if t != self.text():
            self.setText(t)


class EnumEditor(QComboBox):
    """enum / class_data_id / custom_class_data_id。値は 'TypeID.member'、先頭は 'TypeID.None'。"""
    valueChanged = Signal(object)

    def __init__(self, type_name, members, value, parent=None):
        super().__init__(parent)
        self.type_name = type_name
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.completer().setCompletionMode(self.completer().CompletionMode.PopupCompletion)
        self.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(14)
        self._none = f"{type_name}ID.None"
        for o in RF.enum_options(type_name, members):
            self.addItem(o["label"], o["value"])
        self._value = value
        self._sync_to(value)
        self.activated.connect(self._activated)
        self.lineEdit().editingFinished.connect(self._text_done)

    def _sync_to(self, v):
        i = self.findData(v)
        self.blockSignals(True)
        if i >= 0:
            self.setCurrentIndex(i)
        else:
            # 候補に無い値(削除/改名されたID)は黙って消さず、そのまま見せる
            self.setCurrentIndex(-1)
            self.lineEdit().setText("" if v in (None, "") else f"⚠ {v}")
        self.blockSignals(False)

    def _activated(self, i):
        v = self.itemData(i) or self._none
        self._value = v
        self.valueChanged.emit(v)

    def _text_done(self):
        t = self.currentText().strip()
        i = self.findText(t, Qt.MatchFlag.MatchFixedString)
        if i >= 0:
            v = self.itemData(i)
            if v != self._value:
                self._value = v
                self.valueChanged.emit(v)
        else:
            self._sync_to(self._value)

    def value(self):
        return self._value

    def set_value(self, v):
        self._value = v
        self._sync_to(v)

    def wheelEvent(self, e):  # スクロール中に値が変わる事故を防ぐ
        e.ignore()


# ======================================================================= ビット
class BitEditor(QFrame):
    valueChanged = Signal(object)

    def __init__(self, value, options, parent=None):
        super().__init__(parent)
        self.setProperty("card", "flat")
        self.options = options or {}
        self._v = value if isinstance(value, dict) else {"size": RF.bit_size(self.options, None), "bits": []}
        self.names = RF.bit_flag_names(self.options, self._v)
        self.size = RF.bit_size(self.options, self._v)
        self.single = self.options.get("mode") == "single"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        left = QFrame()
        left.setFixedWidth(150)
        left.setStyleSheet(f"background:{theme.color('bg1')};border-right:1px solid {theme.color('border')};")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 10, 12, 10)
        ll.setSpacing(6)
        cap = QLabel("選択中")
        cap.setProperty("role", "muted")
        self.count = QLabel()
        self.count.setStyleSheet(f"font-size:20px;font-weight:700;color:{theme.color('accent')};")
        ll.addWidget(cap)
        ll.addWidget(self.count)
        if not self.single and self.options.get("allowSelectAll"):
            ll.addWidget(C.button("全選択", None, on_click=self.select_all, small=True))
        ll.addWidget(C.button("クリア", None, on_click=self.clear, small=True))
        if self.single:
            t = QLabel("単一選択モード")
            t.setProperty("role", "faint")
            ll.addWidget(t)
        ll.addStretch(1)
        lay.addWidget(left)
        right = QVBoxLayout()
        right.setContentsMargins(8, 8, 8, 8)
        right.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"フラグを検索 ({len(self.names)}件)")
        self.search.textChanged.connect(self._fill)
        right.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMaximumHeight(220)
        self.list.setMinimumHeight(110)
        self.list.itemClicked.connect(self._clicked)
        right.addWidget(self.list)
        lay.addLayout(right, 1)
        self._fill()

    def _bits(self):
        b = self._v.get("bits") if isinstance(self._v, dict) else None
        return b if isinstance(b, list) else []

    def _fill(self, *_):
        self.list.blockSignals(True)
        self.list.clear()
        bits = self._bits()
        entries = RF.bit_filter(self.names, self.search.text())
        for label, i in entries:
            it = QListWidgetItem(f"{'☑' if i in bits else '☐'}  {label}    #{i}")
            it.setData(Qt.ItemDataRole.UserRole, i)
            if i in bits:
                it.setForeground(QColor(theme.color("accent")))
            self.list.addItem(it)
        if not entries:
            self.list.addItem("該当するフラグがありません")
        self.list.blockSignals(False)
        self.count.setText(f"{len(bits)} / {self.size}")

    def _clicked(self, item):
        i = item.data(Qt.ItemDataRole.UserRole)
        if i is None:
            return
        self._v = RF.bit_toggle(self._v, self.options, i)
        self._fill()
        self.valueChanged.emit(self._v)

    def select_all(self):
        self._v = {"size": self.size, "bits": list(range(self.size))}
        self._fill()
        self.valueChanged.emit(self._v)

    def clear(self):
        self._v = {"size": self.size, "bits": []}
        self._fill()
        self.valueChanged.emit(self._v)

    def value(self):
        return self._v

    def set_value(self, v):
        self._v = v if isinstance(v, dict) else {"size": self.size, "bits": []}
        self._fill()


# ======================================================================= カラー
class ScreenPicker(QWidget):
    """スポイト: 画面を撮って全画面表示し、クリックした位置の色を返す。Esc でキャンセル。"""
    picked = Signal(object)
    cancelled = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self._shot = screen.grabWindow(0)
        self._img = self._shot.toImage()
        self._dpr = self._shot.devicePixelRatio() or 1.0
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self._pos = QPointF(0, 0)

    def _color_at(self, p):
        x, y = int(p.x() * self._dpr), int(p.y() * self._dpr)
        if 0 <= x < self._img.width() and 0 <= y < self._img.height():
            return QColor(self._img.pixel(x, y))
        return QColor("#000000")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._shot)
        c = self._color_at(self._pos)
        r = QRectF(self._pos.x() + 18, self._pos.y() + 18, 92, 30)
        if r.right() > self.width():
            r.moveRight(self._pos.x() - 18)
        if r.bottom() > self.height():
            r.moveBottom(self._pos.y() - 18)
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.setBrush(QColor(20, 20, 24, 230))
        p.drawRoundedRect(r, 6, 6)
        p.setBrush(c)
        p.drawRect(QRectF(r.left() + 6, r.top() + 6, 18, 18))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(r.left() + 30, r.top(), 60, r.height()), Qt.AlignmentFlag.AlignVCenter, c.name().upper())

    def mouseMoveEvent(self, e):
        self._pos = e.position()
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            c = self._color_at(e.position())
            self.close()
            self.picked.emit(c)
        else:
            self.close()
            self.cancelled.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancelled.emit()

    def start(self):
        self.showFullScreen()
        self.activateWindow()
        self.setFocus()


class Swatch(QFrame):
    """市松模様の上に色を重ねて表示 (アルファが分かる)。"""
    clicked = Signal()

    def __init__(self, size=(34, 28), parent=None):
        super().__init__(parent)
        self.setFixedSize(*size)
        self._c = QColor("#ffffff")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_color(self, c: QColor):
        self._c = c
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        p.setClipPath(path)
        s = 6
        for y in range(0, self.height(), s):
            for x in range(0, self.width(), s):
                p.fillRect(x, y, s, s, QColor("#d0d0d0") if (x // s + y // s) % 2 == 0 else QColor("#ffffff"))
        p.fillRect(self.rect(), self._c)
        p.setClipping(False)
        p.setPen(QPen(QColor(theme.color("border2")), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def _qcolor_of(c) -> QColor:
    a = c.get("a")
    return QColor(round(c["r"] * 255), round(c["g"] * 255), round(c["b"] * 255), round((1 if a is None else a) * 255))


class ColorEditor(QWidget):
    """hex 直接入力 / スポイト / アルファ / 最近使った色。ドラッグ中の連続更新は 150ms で1回に畳んで通知する。"""
    valueChanged = Signal(object)

    def __init__(self, value, recent, parent=None):
        super().__init__(parent)
        self.recent = recent
        ext = value if isinstance(value, dict) and "r" in value else dict(RF.COLOR_DEFAULT)
        self._draft = dict(ext)
        self._dirty = False
        self._picker = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(RF.COLOR_COMMIT_MS)
        self._timer.timeout.connect(self.flush)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.swatch = Swatch()
        self.swatch.clicked.connect(self._open_dialog)
        row.addWidget(self.swatch)
        self.hex = QLineEdit()
        self.hex.setPlaceholderText("#RRGGBB")
        self.hex.setMaxLength(9)
        self.hex.setFixedWidth(104)
        self.hex.setFont(theme.mono_font(10))
        self.hex.setToolTip("#RGB / #RRGGBB / #RRGGBBAA（AAを付けるとアルファも設定）")
        self.hex.textEdited.connect(self._hex_edited)
        self.hex.editingFinished.connect(self._hex_done)
        row.addWidget(self.hex)
        row.addWidget(C.icon_button("eyedropper", "スポイト（画面上の色を取得）", self._pick_screen))
        col = QVBoxLayout()
        col.setSpacing(0)
        self.alpha_lb = QLabel()
        self.alpha_lb.setProperty("role", "muted")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setFixedWidth(150)
        self.slider.valueChanged.connect(self._alpha_changed)
        self.slider.sliderReleased.connect(self.flush)
        col.addWidget(self.alpha_lb)
        col.addWidget(self.slider)
        row.addLayout(col)
        row.addStretch(1)
        lay.addLayout(row)
        self.recent_row = QHBoxLayout()
        self.recent_row.setSpacing(5)
        lay.addLayout(self.recent_row)
        self._refresh(full=True)
        self._build_recent()

    # --- 表示
    def _refresh(self, full=False):
        d = self._draft
        self.swatch.set_color(_qcolor_of(d))
        a = d.get("a")
        a = 1 if a is None else a
        if full or not self.hex.hasFocus():
            self.hex.setText(RF.color_hex(d))
        self.slider.blockSignals(True)
        self.slider.setValue(round(a * 100))
        self.slider.blockSignals(False)
        self.alpha_lb.setText(f"アルファ: {a:.2f}")

    def _build_recent(self):
        C.clear_layout(self.recent_row)
        items = self.recent.get() if self.recent else []
        if not items:
            return
        lb = QLabel("最近:")
        lb.setProperty("role", "muted")
        self.recent_row.addWidget(lb)
        for c in items:
            sw = Swatch((20, 20))
            sw.set_color(_qcolor_of(c))
            sw.setToolTip(f"{RF.color_hex(c)}  α{(1 if c.get('a') is None else c['a']):.2f}")
            sw.clicked.connect(lambda cc=c: self._apply(cc, commit=True))
            self.recent_row.addWidget(sw)
        self.recent_row.addStretch(1)

    # --- 更新
    def _update(self, nxt):
        self._draft = nxt
        self._dirty = True
        self._refresh()
        self._timer.start()

    def flush(self):
        self._timer.stop()
        if not self._dirty:
            return
        self._dirty = False
        self.valueChanged.emit(dict(self._draft))
        if self.recent:
            self.recent.push(self._draft)
            self._build_recent()

    def _apply(self, c, commit=False):
        a = c.get("a")
        self._update({"r": c["r"], "g": c["g"], "b": c["b"], "a": a if a is not None else self._draft.get("a", 1)})
        if commit:
            self.flush()

    def _alpha_changed(self, v):
        self._update({**self._draft, "a": v / 100})

    def _hex_edited(self, t):
        c = RF.parse_hex_color(t)
        self.hex.setProperty("invalid", bool(t) and c is None)
        theme.repolish(self.hex)
        if c:
            self._update({"r": c["r"], "g": c["g"], "b": c["b"], "a": c["a"] if c.get("a") is not None else self._draft.get("a", 1)})

    def _hex_done(self):
        self.flush()
        self.hex.setText(RF.color_hex(self._draft))
        self.hex.setProperty("invalid", False)
        theme.repolish(self.hex)

    def _open_dialog(self):
        init = _qcolor_of(self._draft)
        c = QColorDialog.getColor(init, self, "色を選択", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self._apply({"r": c.redF(), "g": c.greenF(), "b": c.blueF(), "a": c.alphaF()}, commit=True)

    def _pick_screen(self):
        try:
            self._picker = ScreenPicker()
            self._picker.picked.connect(lambda c: self._apply({"r": c.redF(), "g": c.greenF(), "b": c.blueF(), "a": None}, commit=True))
            self._picker.start()
        except Exception:  # noqa: BLE001 Wayland などで画面取得できない場合
            C.message(self, "この環境では画面の色を取得できません。色の枠をクリックして選択してください。", "スポイト")

    def value(self):
        return dict(self._draft)

    def set_value(self, v):
        if self._dirty:
            return  # 編集中は上書きしない
        ext = v if isinstance(v, dict) and "r" in v else dict(RF.COLOR_DEFAULT)
        if all(ext.get(k) == self._draft.get(k) for k in "rgba"):
            return
        self._draft = dict(ext)
        self._refresh(full=True)

    def focusOutEvent(self, e):
        self.flush()
        super().focusOutEvent(e)

    def hideEvent(self, e):
        self.flush()
        super().hideEvent(e)

    def closeEvent(self, e):
        self.flush()
        super().closeEvent(e)


# ======================================================================= ベジェ
class BezierCanvas(QWidget):
    changed = Signal(object)

    def __init__(self, points, options, parent=None):
        super().__init__(parent)
        self.options = options or {}
        self.geo = RF.BezierGeometry(self.options)
        self.points = points
        self.active = None
        self.drag_index = None
        self.drag_handle = None
        self.setMinimumHeight(150)
        self.setMouseTracking(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(190)

    def set_points(self, points):
        self.points = points
        self.update()

    def _scale(self):
        return self.width() / self.geo.W, self.height() / self.geo.H

    def _to_px(self, pos):
        sx, sy = self._scale()
        return pos.x() / sx, pos.y() / sy

    def paintEvent(self, _e):
        g = self.geo
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        sx, sy = self._scale()
        p.fillRect(self.rect(), QColor(theme.color("bg1")))
        p.setPen(QPen(QColor(theme.color("border2")), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.scale(sx, sy)
        axis = QPen(QColor(theme.color("faint")), 1)
        p.setPen(axis)
        p.drawLine(QPointF(g.PAD, g.H - g.PAD), QPointF(g.W - g.PAD, g.H - g.PAD))
        p.drawLine(QPointF(g.PAD, g.PAD), QPointF(g.PAD, g.H - g.PAD))
        pts = g.curve_points(self.points)
        if pts:
            path = QPainterPath(QPointF(*pts[0]))
            for x, y in pts[1:]:
                path.lineTo(x, y)
            p.setPen(QPen(QColor(theme.color("accent")), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        for i, pt in enumerate(self.points):
            cx, cy = g.x_to_px(pt["time"]), g.y_to_px(pt["value"])
            act = self.active == i
            if act:
                for side, col in (("in", "#43a047"), ("out", "#fb8c00")):
                    dx, dy = g.tangent_to_handle_offset(pt.get(f"{side}Tangent") or 0, side)
                    dash = QPen(QColor(col), 1.5, Qt.PenStyle.DashLine)
                    p.setPen(dash)
                    p.drawLine(QPointF(cx, cy), QPointF(cx + dx, cy + dy))
                    dragging = self.drag_handle == (i, side)
                    p.setPen(QPen(QColor("#ffffff"), 1))
                    p.setBrush(QColor({"in": "#2e7d32" if dragging else "#66bb6a", "out": "#e65100" if dragging else "#ffa726"}[side]))
                    p.drawEllipse(QPointF(cx + dx, cy + dy), 5, 5)
            p.setPen(QPen(QColor("#0d47a1"), 2) if act else Qt.PenStyle.NoPen)
            p.setBrush(QColor("#d32f2f") if self.drag_index == i else QColor("#1565c0" if act else theme.color("accent")))
            p.drawEllipse(QPointF(cx, cy), 6 if act else 5, 6 if act else 5)

    def _hit(self, px, py):
        g = self.geo
        if self.active is not None and self.active < len(self.points):
            pt = self.points[self.active]
            cx, cy = g.x_to_px(pt["time"]), g.y_to_px(pt["value"])
            for side in ("in", "out"):
                dx, dy = g.tangent_to_handle_offset(pt.get(f"{side}Tangent") or 0, side)
                if math.hypot(px - (cx + dx), py - (cy + dy)) <= 8:
                    return ("handle", self.active, side)
        for i in range(len(self.points) - 1, -1, -1):
            pt = self.points[i]
            if math.hypot(px - g.x_to_px(pt["time"]), py - g.y_to_px(pt["value"])) <= 9:
                return ("point", i, None)
        return None

    def mousePressEvent(self, e):
        px, py = self._to_px(e.position())
        hit = self._hit(px, py)
        if hit is None:
            self.active = None
        elif hit[0] == "handle":
            self.drag_handle = (hit[1], hit[2])
        else:
            self.active = hit[1]
            self.drag_index = hit[1]
        self.update()

    def mouseMoveEvent(self, e):
        if self.drag_index is None and self.drag_handle is None:
            return
        px, py = self._to_px(e.position())
        g = self.geo
        if self.drag_index is not None:
            patch = {"time": g.px_to_x(px), "value": g.px_to_y(py)}
            self.changed.emit(("update", self.drag_index, patch))
        elif self.drag_handle is not None:
            i, side = self.drag_handle
            pt = self.points[i]
            cx, cy = g.x_to_px(pt["time"]), g.y_to_px(pt["value"])
            t = g.handle_offset_to_tangent(px - cx, py - cy, side)
            self.changed.emit(("update", i, {f"{side}Tangent": t}))

    def mouseReleaseEvent(self, _e):
        self.drag_index = None
        self.drag_handle = None
        self.update()


class BezierEditor(QWidget):
    valueChanged = Signal(object)

    def __init__(self, value, options, parent=None):
        super().__init__(parent)
        self.options = options or {}
        self._v = value if isinstance(value, dict) else None
        self.points = RF.bezier_points(self._v, self.options)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.canvas = BezierCanvas(self.points, self.options)
        self.canvas.changed.connect(self._canvas_changed)
        lay.addWidget(self.canvas)
        hint = QLabel("点をクリックして選択すると、左右にタンジェントハンドル（緑=in / 橙=out）が表示され、ドラッグで傾きを調整できます。")
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        lay.addWidget(hint)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        lay.addLayout(self.rows)
        self.add_btn = C.button("点を追加", None, "plus", None, self._add, small=True)
        lay.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._build_rows()

    def _build_rows(self):
        C.clear_layout(self.rows)
        self._edits = []
        for i, p in enumerate(self.points):
            row = QHBoxLayout()
            row.setSpacing(6)
            chip = C.Chip(f"点{i}", "accent" if self.canvas.active == i else "true", clickable=True)
            chip.clicked.connect(lambda idx=i: self._activate(idx))
            row.addWidget(chip)
            ed = []
            for key in ("time", "value", "inTangent", "outTangent"):
                col = QVBoxLayout()
                col.setSpacing(0)
                lb = QLabel(key)
                lb.setProperty("role", "faint")
                e = NumericEdit(p.get(key) or 0, True)
                e.valueChanged.connect(lambda val, idx=i, k=key: self._field(idx, k, val))
                col.addWidget(lb)
                col.addWidget(e)
                row.addLayout(col, 1)
                ed.append(e)
            rm = C.icon_button("trash", "点を削除", lambda idx=i: self._remove(idx), color="#ef6b73")
            rm.setEnabled(len(self.points) > 2)
            row.addWidget(rm)
            self.rows.addLayout(row)
            self._edits.append(ed)

    def _activate(self, i):
        self.canvas.active = i
        self.canvas.update()
        self._build_rows()

    def _push(self, new_value, rebuild=True):
        self._v = new_value
        self.points = RF.bezier_points(new_value, self.options)
        self.canvas.set_points(self.points)
        if rebuild:
            self._build_rows()
        self.valueChanged.emit(new_value)

    def _canvas_changed(self, msg):
        _, i, patch = msg
        self._v = RF.bezier_update_point(self.points, i, patch)
        self.points = self._v["points"]
        self.canvas.set_points(self.points)
        for e, k in zip(self._edits[i], ("time", "value", "inTangent", "outTangent")):
            e.set_value(self.points[i].get(k) or 0)
        self.valueChanged.emit(self._v)

    def _field(self, i, key, val):
        if key == "time":
            val = max(0, min(1, val))
        self._push(RF.bezier_update_point(self.points, i, {key: val}), rebuild=False)

    def _add(self):
        self._push(RF.bezier_add_point(self.points, self.options))

    def _remove(self, i):
        nv = RF.bezier_remove_point(self.points, i)
        if nv is None:
            return
        if self.canvas.active == i:
            self.canvas.active = None
        self._push(nv)

    def value(self):
        return self._v if self._v is not None else {"points": self.points}

    def set_value(self, v):
        self._v = v if isinstance(v, dict) else None
        self.points = RF.bezier_points(self._v, self.options)
        self.canvas.set_points(self.points)
        self._build_rows()


# ======================================================================= 音声 / テキスト インデックス
class AudioPlayer:
    """1 つだけ共有する試聴プレーヤー (QtMultimedia が無い環境では使えない旨を返す)。"""
    _inst = None

    @classmethod
    def get(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def __init__(self):
        self.ok = True
        self.player = None
        self.playing_key = None
        self.on_state = None
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self.player = QMediaPlayer()
            self.out = QAudioOutput()
            self.player.setAudioOutput(self.out)
            self.player.mediaStatusChanged.connect(self._status)
            self.player.errorOccurred.connect(self._error)
        except Exception:  # noqa: BLE001
            self.ok = False

    def _status(self, st):
        from PySide6.QtMultimedia import QMediaPlayer
        if st == QMediaPlayer.MediaStatus.EndOfMedia:
            self._finish(None)

    def _error(self, *_a):
        self._finish("再生できませんでした。")

    def _finish(self, err):
        self.playing_key = None
        if self.on_state:
            self.on_state(None, err)

    def play(self, key, url, on_state):
        self.stop()
        if not self.ok:
            on_state(None, "この環境では音声を再生できません（QtMultimedia がありません）。")
            return
        self.on_state = on_state
        self.playing_key = key
        self.player.setSource(QUrl(url))
        self.player.play()
        on_state(key, None)

    def stop(self):
        if self.player is not None and self.playing_key is not None:
            self.player.stop()
        was = self.playing_key
        self.playing_key = None
        if was is not None and self.on_state:
            self.on_state(None, None)


class PickerPopup(QFrame):
    """検索付きの一覧ポップアップ。各行に試聴ボタンを出せる。"""
    picked = Signal(int)

    def __init__(self, items, on_play=None, playing_index=None, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setProperty("card", "true")
        self.items = items
        self.on_play = on_play
        self.playing = playing_index
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self.search = C.SearchEdit("検索...")
        self.search.textChanged.connect(self._fill)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMinimumSize(420, 260)
        self.list.itemClicked.connect(self._clicked)
        lay.addWidget(self.list)
        self._fill()

    def _fill(self, *_):
        q = self.search.text().strip().lower()
        self.list.clear()
        for it in self.items:
            if q and q not in it["label"].lower():
                continue
            li = QListWidgetItem()
            li.setData(Qt.ItemDataRole.UserRole, it["index"])
            li.setSizeHint(QSize(100, 32))
            self.list.addItem(li)
            if self.on_play is not None:
                w = QWidget()
                hl = QHBoxLayout(w)
                hl.setContentsMargins(6, 0, 4, 0)
                lb = QLabel(it["label"])
                lb.setWordWrap(False)
                lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                hl.addWidget(lb, 1)
                b = C.icon_button("stop" if self.playing == it["index"] else "play",
                                  "試聴" if it.get("info") else "サウンド定義が見つかりません",
                                  lambda x=it: self.on_play(x), size=14)
                b.setEnabled(bool(it.get("info")))
                hl.addWidget(b)
                self.list.setItemWidget(li, w)
            else:
                li.setText(it["label"])

    def _clicked(self, li):
        self.picked.emit(li.data(Qt.ItemDataRole.UserRole))
        self.close()

    def popup_at(self, widget):
        self.move(widget.mapToGlobal(widget.rect().bottomLeft()))
        self.show()
        self.search.setFocus()


class IndexPickerBar(QWidget):
    """現在の選択を表示するボタン + (任意) 試聴ボタン。クリックで PickerPopup。"""
    picked = Signal(int)

    def __init__(self, caption, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.btn = QPushButton()
        self.btn.setStyleSheet("text-align:left;padding:6px 10px;")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self._open)
        lay.addWidget(self.btn, 1)
        self.clear_btn = C.icon_button("close", "未選択(-1)にする", lambda: self.picked.emit(-1), size=14)
        lay.addWidget(self.clear_btn)
        self.play_btn = C.icon_button("play", "選択中を試聴", None)
        lay.addWidget(self.play_btn)
        self.caption = caption
        self.items = []
        self.on_play = None
        self.playing = None
        self.selected = None
        self._popup = None

    def configure(self, items, value, on_play=None, playing=None):
        self.items = items
        self.on_play = on_play
        self.playing = playing
        self.selected = next((o for o in items if o["index"] == value), None)
        self.btn.setText(self.selected["label"] if self.selected else f"{self.caption}を選択…")
        self.play_btn.setVisible(on_play is not None)
        if on_play is not None:
            self.play_btn.setEnabled(bool(self.selected and self.selected.get("info")))
            self.play_btn.setIcon(icons.icon("stop" if (self.selected and playing == self.selected["index"]) else "play"))
            try:
                self.play_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.play_btn.clicked.connect(lambda: self.selected and on_play(self.selected))

    def _open(self):
        self._popup = PickerPopup(self.items, self.on_play, self.playing, self)
        self._popup.picked.connect(self.picked.emit)
        self._popup.popup_at(self.btn)


_last_voice_language = None


class _MatrixIndexEditor(QWidget):
    """voice_ref / text_list_index 共通の土台: イベント一覧と Matrix を非同期で取得する。"""
    valueChanged = Signal(object)

    def __init__(self, env, value, options, parent=None):
        super().__init__(parent)
        self.env = env
        self.options = options or {}
        self._v = RF.index_value(value)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(3)
        self.status = QLabel("読み込み中...")
        self.status.setProperty("role", "muted")
        self.lay.addWidget(self.status)
        self._dead = False

    def value(self):
        return self._v

    def set_value(self, v):
        self._v = RF.index_value(v)
        self._render()

    def _render(self):
        pass

    def _error(self, msg):
        C.clear_layout(self.lay)
        lb = QLabel(msg)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{theme.color('err')};")
        self.lay.addWidget(lb)

    def _set(self, idx):
        self._v = idx
        self._render()
        self.valueChanged.emit(idx)

    def closeEvent(self, e):
        self._dead = True
        super().closeEvent(e)


class VoiceRefEditor(_MatrixIndexEditor):
    def __init__(self, env, value, options, parent=None):
        super().__init__(env, value, options, parent)
        self.matrix = self.options.get("matrixName") or "ScenarioVoice"
        self.field = self.options.get("fieldName") or "voices"
        self.preview_lang = self.options.get("previewLanguage") or "Ja"
        self.languages, self.sound_lookup, self.scenario_key = [], None, ""
        self.language = _last_voice_language or self.preview_lang
        self.play_error = ""
        self.playing = None
        if not env.event_id or not env.sub_id:
            self._error("シナリオイベント文脈が必要です（eventId / subId）。")
            return
        self._load()

    def _load(self):
        lk = self.env.state.lookups

        def work():
            events = lk.api.list_events()
            key = RF.resolve_scenario_key(events, self.env.event_id, self.env.sub_id)
            table = lk.api.class_data_matrix_id(self.matrix)
            try:
                snd = lk.api.sounds()
            except ApiError:
                snd = None
            return key, table, snd

        def ok(res):
            if self._dead:
                return
            key, table, snd = res
            self.scenario_key = key
            self.languages = RF.voice_languages(table, key, self.field)
            self.sound_lookup = RF.build_sound_lookup(snd) if snd else None
            self._build()

        run_async(work, ok, lambda e: None if self._dead else self._error(str(e)), self)

    def _build(self):
        C.clear_layout(self.lay)
        if not self.languages:
            self._error(f"Matrix {self.matrix} に言語の行がありません。Matrix にボイスを追加してください。")
            return
        self.head = QLabel()
        self.head.setProperty("role", "muted")
        self.lay.addWidget(self.head)
        if len(self.languages) > 1:
            row = QHBoxLayout()
            row.setSpacing(4)
            lb = QLabel("試聴言語")
            lb.setProperty("role", "muted")
            row.addWidget(lb)
            self.lang_btns = {}
            for l in self.languages:
                b = QPushButton(l["label"])
                b.setCheckable(True)
                b.setStyleSheet("padding:1px 9px;font-size:12px;")
                b.clicked.connect(lambda _=False, name=l["label"]: self._set_language(name))
                row.addWidget(b)
                self.lang_btns[l["label"]] = b
            row.addStretch(1)
            self.lay.addLayout(row)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.lay.addWidget(self.warn)
        self.bar = IndexPickerBar("ボイスインデックス")
        self.bar.picked.connect(self._set)
        self.lay.addWidget(self.bar)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.lay.addWidget(self.info)
        self._render()

    def _active(self):
        return RF.active_language(self.languages, self.language)

    def _set_language(self, name):
        global _last_voice_language
        _last_voice_language = name
        self.language = name
        AudioPlayer.get().stop()
        self.play_error = ""
        self._render()

    def _items(self):
        act = self._active()
        return RF.voice_items(act, self.sound_lookup) if act else []

    def _render(self):
        if not hasattr(self, "bar"):
            return
        act = self._active()
        items = self._items()
        self.head.setText(f"{self.matrix}.{self.field}（{act['label'] if act else ''}） / シナリオ {self.scenario_key or self.env.event_id} — {len(items)}件")
        if hasattr(self, "lang_btns"):
            for k, b in self.lang_btns.items():
                b.setChecked(act is not None and k == act["label"])
        warn = []
        if act and act["list"] is None:
            warn.append(f"Matrix {self.matrix}（{act['label']}）に「{self.scenario_key}」の {self.field} がありません。"
                        "scenario_matrix_editor.py のボイス設定などで追加してください。")
        mm = RF.length_mismatch(self.languages)
        if mm:
            warn.append(f"言語ごとのボイス数が一致していません（{mm}）。同じインデックスが別言語で別のセリフを指す恐れがあります。")
        self.warn.setText("\n".join(warn))
        self.warn.setStyleSheet(f"color:{theme.color('warn')};")
        self.warn.setVisible(bool(warn))
        self.bar.configure(items, self._v, self._play, self.playing)
        sel = next((o for o in items if o["index"] == self._v), None)
        msgs = []
        if sel and not sel.get("info"):
            msgs.append(f"SoundID「{sel['soundId']}」に対応するサウンド定義が見つかりません（削除・リネームされた可能性があります）。"
                        if self.sound_lookup else "サウンド定義(/api/sound)を取得できなかったため試聴できません。")
        if self._v >= 0 and not sel and act and act["list"] is not None:
            msgs.append(f"インデックス {self._v} は {act['label']} のボイス一覧（{len(items)}件）の範囲外です。")
        text = "\n".join(msgs)
        if self.play_error:
            text = (text + "\n" if text else "") + self.play_error
        self.info.setText(text)
        self.info.setStyleSheet(f"color:{theme.color('err') if self.play_error else theme.color('warn')};")
        self.info.setVisible(bool(text))

    def _play(self, item):
        pl = AudioPlayer.get()
        if self.playing == item["index"]:
            pl.stop()
            return
        info = item.get("info")
        if not info:
            return
        url = self.env.state.api.sound_serve_url(info["group"], info["index"])
        self.play_error = ""

        def st(key, err):
            self.playing = item["index"] if key is not None else None
            if err:
                self.play_error = f"{item['soundId']} の音声ファイルを再生できませんでした。" if "再生できませんでした" in err else err
            if not self._dead:
                self._render()
        pl.play(item["index"], url, st)

    def closeEvent(self, e):
        AudioPlayer.get().stop()
        super().closeEvent(e)


class TextListIndexEditor(_MatrixIndexEditor):
    def __init__(self, env, value, options, parent=None):
        super().__init__(env, value, options, parent)
        self.matrix = self.options.get("matrixName") or "ScenarioText"
        self.field = self.options.get("fieldName") or "texts"
        self.lang = self.options.get("previewLanguage") or "Ja"
        self.items, self.scenario_key = [], ""
        if not env.event_id or not env.sub_id:
            self._error("シナリオイベント文脈が必要です（eventId / subId）。")
            return
        lk = env.state.lookups

        def work():
            events = lk.api.list_events()
            key = RF.resolve_scenario_key(events, env.event_id, env.sub_id)
            table = lk.api.class_data_matrix_id(self.matrix)
            return key, RF.text_list_items(table, key, self.lang, self.field, self.matrix)

        def ok(res):
            if self._dead:
                return
            self.scenario_key, self.items = res
            C.clear_layout(self.lay)
            self.head = QLabel()
            self.head.setProperty("role", "muted")
            self.lay.addWidget(self.head)
            self.bar = IndexPickerBar("テキストインデックス")
            self.bar.picked.connect(self._set)
            self.lay.addWidget(self.bar)
            self._render()

        run_async(work, ok, lambda e: None if self._dead else self._error(str(e)), self)

    def _render(self):
        if not hasattr(self, "bar"):
            return
        self.head.setText(f"{self.matrix}.{self.field}（{self.lang}） / シナリオ {self.scenario_key or self.env.event_id} — {len(self.items)}件")
        self.bar.configure(self.items, self._v)
