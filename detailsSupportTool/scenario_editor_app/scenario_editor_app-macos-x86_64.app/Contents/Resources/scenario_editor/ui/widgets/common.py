"""再利用する小さな部品 (ボタン / チップ / スイッチ / トースト / ドロワー / ダイアログ)。"""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLayout, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from .. import icons, theme


# ---------------------------------------------------------------- 基本
def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def set_prop(w, **props) -> None:
    for k, v in props.items():
        w.setProperty(k, v)
    theme.repolish(w)


def label(text="", role=None, wrap=False, selectable=False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lb


def button(text="", variant=None, icon_name=None, tooltip=None, on_click=None, small=False, parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    if variant:
        b.setProperty("variant", variant)
    if small:
        b.setStyleSheet("QPushButton{padding:3px 9px;font-size:12px;}")
    if icon_name:
        b.setIcon(icons.icon(icon_name, theme.color("accentFg") if variant in ("primary", "ok") else None))
        b.setIconSize(QSize(16, 16))
    if tooltip:
        b.setToolTip(tooltip)
    if on_click:
        b.clicked.connect(lambda _=False: on_click())
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def icon_button(name, tooltip="", on_click=None, color=None, size=18, checkable=False, parent=None) -> QToolButton:
    b = QToolButton(parent)
    b.setIcon(icons.icon(name, color))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    if on_click:
        b.clicked.connect(lambda _=False: on_click())
    return b


def separator(vertical=False) -> QFrame:
    f = QFrame()
    f.setProperty("sep", "v" if vertical else "h")
    f.setFrameShape(QFrame.Shape.NoFrame)
    return f


def hbox(*widgets, spacing=8, margins=(0, 0, 0, 0), stretch_end=False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QLayout):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    if stretch_end:
        lay.addStretch(1)
    return lay


def vbox(*widgets, spacing=8, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QLayout):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    return lay


class Card(QFrame):
    def __init__(self, parent=None, flat=False):
        super().__init__(parent)
        self.setProperty("card", "flat" if flat else "true")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(8)


class Chip(QLabel):
    clicked = Signal()

    def __init__(self, text="", kind="true", clickable=False, tooltip=None, parent=None):
        super().__init__(text, parent)
        self.setProperty("chip", kind)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_kind(self, kind):
        set_prop(self, chip=kind)

    def mousePressEvent(self, e):
        if self._clickable and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class Banner(QFrame):
    def __init__(self, text, kind="info", parent=None):
        super().__init__(parent)
        self.setProperty("banner", kind)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.lb = QLabel(text)
        self.lb.setWordWrap(True)
        self.lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.lb)

    def set_text(self, t):
        self.lb.setText(t)


class ElidedLabel(QLabel):
    def __init__(self, text="", mode=Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(20)
        self.set_full_text(text)

    def set_full_text(self, t):
        self._full = t or ""
        self.setToolTip(self._full)
        self._refresh()

    def full_text(self):
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh()

    def _refresh(self):
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, self._mode, max(10, self.width() - 2)))


class Switch(QAbstractButton):
    """iOS 風トグル。ON の色は on_color (既定: アクセント)。"""

    def __init__(self, checked=False, on_color=None, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self._on = on_color
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(40, 22)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        on = self.isChecked()
        track = QColor(self._on or theme.color("accent")) if on else QColor(theme.color("bg4"))
        if not self.isEnabled():
            track.setAlphaF(0.4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.setBrush(QColor("#ffffff"))
        x = self.width() - 19 if on else 3
        p.drawEllipse(QRect(x, 3, 16, 16))


class SearchEdit(QLineEdit):
    def __init__(self, placeholder="検索...", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(icons.icon("search", theme.color("muted")), QLineEdit.ActionPosition.LeadingPosition)


class FlowLayout(QLayout):
    """折り返しレイアウト (チップ / バッジ並べ用)。"""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self._sp = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect, test):
        m = self.contentsMargins()
        x, y = rect.x() + m.left(), rect.y() + m.top()
        right = rect.right() - m.right()
        line_h = 0
        for it in self._items:
            sz = it.sizeHint()
            if x + sz.width() > right and line_h > 0:
                x = rect.x() + m.left()
                y += line_h + self._sp
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x += sz.width() + self._sp
            line_h = max(line_h, sz.height())
        return y + line_h - rect.y() + m.bottom()


# ---------------------------------------------------------------- トースト
class ToastHost(QWidget):
    """親ウィンドウの右下に積み上がる通知。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._lay.addStretch(1)
        self.raise_()
        parent.installEventFilter(self)
        self._reposition()

    def eventFilter(self, obj, ev):
        if obj is self.parent() and ev.type() == ev.Type.Resize:
            self._reposition()
        return False

    def _reposition(self):
        p = self.parentWidget()
        w = 380
        self.setGeometry(p.width() - w - 20, 20, w, max(50, p.height() - 40))

    def show_toast(self, message, level="info", ms=3500):
        f = QFrame()
        f.setProperty("toast", level if level in ("info", "success", "warning", "error") else "info")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 9, 12, 9)
        ic = {"success": "check", "warning": "warn", "error": "error"}.get(level, "info")
        col = {"success": "ok", "warning": "warn", "error": "err"}.get(level, "info")
        il = QLabel()
        il.setPixmap(icons.icon(ic, theme.color(col)).pixmap(18, 18))
        tl = QLabel(message)
        tl.setWordWrap(True)
        lay.addWidget(il, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(tl, 1)
        self._lay.addWidget(f)
        self.raise_()
        QTimer.singleShot(ms if level != "error" else ms + 3000, lambda: self._drop(f))

    def _drop(self, f):
        try:
            self._lay.removeWidget(f)
            f.setParent(None)
            f.deleteLater()
        except RuntimeError:
            pass


# ---------------------------------------------------------------- ドロワー
class Drawer(QWidget):
    """親の右端からスライドインするパネル。背面はスクリムで覆う。close_requested を受けて閉じる側が決める。"""
    close_requested = Signal()

    def __init__(self, parent, width=480):
        super().__init__(parent)
        self._w = width
        self.setObjectName("drawerRoot")
        self.scrim = QFrame(self)
        self.scrim.setObjectName("scrim")
        self.panel = QFrame(self)
        self.panel.setProperty("drawer", True)
        self.body = QVBoxLayout(self.panel)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        self.scrim.mousePressEvent = lambda e: self.close_requested.emit()
        self.hide()
        parent.installEventFilter(self)
        self._anim = QPropertyAnimation(self.panel, b"pos", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._after_anim)
        self._closing = False

    def set_width(self, w):
        self._w = w
        self._layout_children()

    def eventFilter(self, obj, ev):
        if obj is self.parent() and ev.type() == ev.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
            self._layout_children()
        return False

    def _panel_width(self):
        return min(self._w, max(320, self.width()))

    def _layout_children(self):
        self.scrim.setGeometry(self.rect())
        pw = self._panel_width()
        self.panel.setGeometry(self.width() - pw, 0, pw, self.height())

    def is_open(self):
        return self.isVisible() and not self._closing

    def open_(self):
        self._closing = False
        self.setGeometry(self.parentWidget().rect())
        self._layout_children()
        self.show()
        self.raise_()
        pw = self._panel_width()
        self._anim.stop()
        self._anim.setStartValue(QPoint(self.width(), 0))
        self._anim.setEndValue(QPoint(self.width() - pw, 0))
        self._anim.start()

    def close_(self):
        if not self.isVisible():
            return
        self._closing = True
        self._anim.stop()
        self._anim.setStartValue(self.panel.pos())
        self._anim.setEndValue(QPoint(self.width(), 0))
        self._anim.start()

    def _after_anim(self):
        if self._closing:
            self.hide()
            self._closing = False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            return
        super().keyPressEvent(e)

    def header(self, title, icon_name=None, extra_widgets=()):
        bar = QFrame()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 12, 10, 12)
        lay.setSpacing(8)
        if icon_name:
            ic = QLabel()
            ic.setPixmap(icons.icon(icon_name, theme.color("accent")).pixmap(20, 20))
            lay.addWidget(ic)
        t = ElidedLabel(title)
        t.setProperty("role", "h2")
        lay.addWidget(t, 1)
        for w in extra_widgets:
            lay.addWidget(w)
        lay.addWidget(icon_button("close", "閉じる", lambda: self.close_requested.emit()))
        self.body.addWidget(bar)
        self.body.addWidget(separator())
        return t


# ---------------------------------------------------------------- ダイアログ
def _std_box(parent, icon, title, text, buttons, default=None):
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    if default is not None:
        box.setDefaultButton(default)
    return box


def confirm(parent, text, title="確認", ok_text="OK", cancel_text="キャンセル", danger=False) -> bool:
    box = _std_box(parent, QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question, title, text,
                   QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
    box.button(QMessageBox.StandardButton.Ok).setText(ok_text)
    box.button(QMessageBox.StandardButton.Cancel).setText(cancel_text)
    return box.exec() == QMessageBox.StandardButton.Ok


def ask_three(parent, text, title, yes_text, no_text, cancel_text="キャンセル") -> str:
    """'yes' | 'no' | 'cancel'"""
    box = _std_box(parent, QMessageBox.Icon.Question, title, text,
                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                   QMessageBox.StandardButton.Cancel)
    box.button(QMessageBox.StandardButton.Yes).setText(yes_text)
    box.button(QMessageBox.StandardButton.No).setText(no_text)
    box.button(QMessageBox.StandardButton.Cancel).setText(cancel_text)
    r = box.exec()
    return {QMessageBox.StandardButton.Yes: "yes", QMessageBox.StandardButton.No: "no"}.get(r, "cancel")


def message(parent, text, title="お知らせ", error=False) -> None:
    _std_box(parent, QMessageBox.Icon.Critical if error else QMessageBox.Icon.Information, title, text,
             QMessageBox.StandardButton.Ok).exec()


class FormDialog(QDialog):
    """単純な入力ダイアログ。fields = [(key, label, kind, default)] kind: 'text'|'multiline'|'bool'|'choice'(default=(value, [options]))。"""

    def __init__(self, parent, title, fields, info=None, ok_text="OK", width=440):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self._widgets = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)
        if info:
            lay.addWidget(Banner(info, "info"))
        form = QFormLayout()
        form.setSpacing(10)
        for key, lab, kind, default in fields:
            if kind == "bool":
                w = QCheckBox(lab)
                w.setChecked(bool(default))
                form.addRow(w)
            elif kind == "multiline":
                w = QPlainTextEdit()
                w.setPlainText(default or "")
                w.setFixedHeight(90)
                form.addRow(lab, w)
            elif kind == "choice":
                from PySide6.QtWidgets import QComboBox
                w = QComboBox()
                cur, opts = default
                for value, text in opts:
                    w.addItem(text, value)
                i = w.findData(cur)
                w.setCurrentIndex(max(0, i))
                form.addRow(lab, w)
            else:
                w = QLineEdit(default or "")
                form.addRow(lab, w)
            self._widgets[key] = (kind, w)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
        bb.button(QDialogButtonBox.StandardButton.Ok).setProperty("variant", "primary")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        for kind, w in self._widgets.values():
            if kind == "text":
                w.returnPressed.connect(self.accept)
                w.setFocus()
                break

    def set_ok_enabled(self, enabled):
        self._ok.setEnabled(enabled)

    def widget(self, key):
        return self._widgets[key][1]

    def values(self) -> dict:
        out = {}
        for key, (kind, w) in self._widgets.items():
            if kind == "bool":
                out[key] = w.isChecked()
            elif kind == "multiline":
                out[key] = w.toPlainText()
            elif kind == "choice":
                out[key] = w.currentData()
            else:
                out[key] = w.text()
        return out


def confirm_delete_with_reference_check(parent, state, kind, name, on_confirmed, label=None):
    """削除前に参照を調べ、参照があれば一覧付きで確認する (services/api.js の confirmDeleteWithReferenceCheck 相当)。"""
    from ..async_ import run_async
    label = label or name

    def ok(res):
        refs = (res or {}).get("references") or []
        if refs:
            lines = []
            for r in refs[:15]:
                lines.append("・" + (r if isinstance(r, str) else (r.get("label") or r.get("path") or r.get("name") or str(r))))
            more = f"\n…ほか {len(refs) - 15} 件" if len(refs) > 15 else ""
            text = f"「{label}」は {len(refs)} 箇所から参照されています。\n" + "\n".join(lines) + more + "\n\nそれでも削除しますか？"
        else:
            text = f"「{label}」を削除しますか？"
        if confirm(parent, text, "削除の確認", "削除", danger=True):
            on_confirmed()

    run_async(lambda: state.api.check_references(kind, name), ok,
              lambda e: ok({"references": []}), parent)
