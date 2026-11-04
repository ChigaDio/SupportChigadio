"""差分(diff_roles の結果)の表示。DSL適用前の確認ダイアログで共用する (ScenarioEventTransition.js: DiffSummary / 適用内容の確認)。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget)

from ...core import diff as D
from ...core.transition_ops import summarize_changes
from ..widgets import common as C
from ..widgets.common import clear_layout
from .. import theme


def _mono(text, role=None):
    lb = QLabel(text)
    lb.setFont(theme.mono_font(9))
    lb.setWordWrap(True)
    lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if role:
        lb.setProperty("role", role)
    return lb


class DiffSummary(QWidget):
    """削除/追加/変更/サブグループ設定の差分を並べる。"""

    def __init__(self, diff=None, setting_changes=None, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(8)
        if diff is not None:
            self.set_diff(diff, setting_changes)

    def set_diff(self, diff, setting_changes=None):
        clear_layout(self.lay)
        lay = self.lay
        if diff["removed"]:
            lay.addWidget(C.Chip(f"削除 {len(diff['removed'])}件", "err"))
            for r in diff["removed"]:
                lay.addWidget(C.label(f"  − {r['name']}（この行がテキストから消えたため、Roleごと削除されます）"))
        if diff["added"]:
            lay.addWidget(C.Chip(f"追加 {len(diff['added'])}件", "ok"))
            for r in diff["added"]:
                fields = r["fields"]
                s = "".join(f" {f['name']}={D.format_value(f['value'], 24)}" for f in fields[:4]) + (" …" if len(fields) > 4 else "")
                lay.addWidget(_mono(f"  ＋ {r['name']}{s}"))
        if diff["changed"]:
            lay.addWidget(C.Chip(f"変更 {len(diff['changed'])}件", "warn"))
            for r in diff["changed"]:
                title = r["name"] + (f"（旧: {r['renamedFrom']}）" if r.get("renamedFrom") else "")
                t = C.label("  " + title)
                t.setStyleSheet("font-weight:700;")
                lay.addWidget(t)
                for f in r["fields"]:
                    lay.addWidget(_mono(f"      {f['name']}: {D.format_value(f['from'])} → {D.format_value(f['to'])}", "muted"))
        if setting_changes:
            lay.addWidget(C.Chip(f"サブグループ設定 {len(setting_changes)}件", "info"))
            for c in setting_changes:
                lay.addWidget(_mono(f"      {c['name']}: {D.format_value(c['from'])} → {D.format_value(c['to'])}", "muted"))
        if diff.get("reordered"):
            lay.addWidget(C.label("Roleの並び順が変わります", "muted"))
        lay.addWidget(C.label(f"変更のないRole: {diff['unchangedCount']}件", "muted"))


class EditPreviewDialog(QDialog):
    """「適用内容の確認」。承認(accept)されたら呼び出し側が実際の適用と保存を行う。"""

    def __init__(self, parent, changes):
        super().__init__(parent)
        self.changes = changes
        visible = [c for c in changes if summarize_changes([c]) > 0]
        total = summarize_changes(changes)
        self.setWindowTitle(f"適用内容の確認（{total}件の変更 / {len(visible)}グループ）")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)
        head = C.label(f"適用内容の確認（{total}件の変更 / {len(visible)}グループ）", "h2")
        lay.addWidget(head)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 6, 0)
        hl.setSpacing(10)
        for c in visible:
            card = C.Card(flat=True)
            row = C.hbox(spacing=8)
            t = QLabel(f"SUB:{c['subId']} NODE:{c['pathKey']}")
            t.setFont(theme.mono_font(10))
            t.setStyleSheet("font-weight:700;")
            row.addWidget(t)
            if c["isNew"]:
                row.addWidget(C.Chip("新規グループ", "ok"))
            row.addStretch(1)
            card.body.addLayout(row)
            card.body.addWidget(DiffSummary(c["diff"], c["settingChanges"]))
            hl.addWidget(card)
        unchanged = len(changes) - len(visible)
        hl.addWidget(C.label(f"変更のないグループ: {unchanged}件（保存されません）", "muted"))
        hl.addStretch(1)
        sc.setWidget(host)
        lay.addWidget(sc, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("適用して保存")
        ok.setProperty("variant", "ok")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class RolePreviewDialog(QDialog):
    """データ入力のテキスト(DSL)適用前の確認。"""

    def __init__(self, parent, diff):
        super().__init__(parent)
        self.setWindowTitle(f"適用内容の確認（{diff['totalChanges']}件の変更）")
        self.resize(560, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)
        lay.addWidget(C.label(self.windowTitle(), "h2"))
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(DiffSummary(diff))
        lay.addWidget(sc, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("適用して保存")
        ok.setProperty("variant", "ok")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
