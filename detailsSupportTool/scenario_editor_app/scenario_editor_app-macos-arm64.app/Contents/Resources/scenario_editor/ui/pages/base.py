"""全ページの基底クラス。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..widgets import common as C


class Page(QWidget):
    """ページ共通の契約。MainWindow が load(params) を呼び、離れる前に can_leave() を呼ぶ。"""
    PAGE_ID = ""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.params = {}

    def load(self, params: dict) -> None:  # noqa: D401
        self.params = dict(params or {})

    def page_title(self) -> str:
        return ""

    def can_leave(self) -> bool:
        return True

    def on_activated(self) -> None:
        """タブ/ページに戻ってきたとき。"""

    def shutdown(self) -> None:
        """アプリ終了/ページ破棄の直前 (タイマー停止など)。"""

    # --- 共通部品
    def toast(self, msg, level="info"):
        self.state.show_toast(msg, level)

    def fail(self, prefix, e):
        self.state.show_toast(f"{prefix}: {e}", "error")

    def make_header(self, title, subtitle=None, back=None, widgets=()):
        bar = QFrame()
        bar.setProperty("toolbar", True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(10)
        if back:
            lay.addWidget(C.icon_button("left", "戻る", back))
        box = QVBoxLayout()
        box.setSpacing(0)
        t = QLabel(title)
        t.setProperty("role", "title")
        box.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setProperty("role", "muted")
            s.setWordWrap(True)
            box.addWidget(s)
        lay.addLayout(box, 1)
        for w in widgets:
            lay.addWidget(w)
        return bar, t


def align_top():
    return Qt.AlignmentFlag.AlignTop
