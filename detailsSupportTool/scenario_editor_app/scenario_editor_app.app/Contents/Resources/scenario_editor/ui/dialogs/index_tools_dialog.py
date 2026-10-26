"""インデックス一括調整ダイアログ (ScenarioIndexToolsDialog.js)。GUI / DSL で共用。"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QRadioButton, QScrollArea, QVBoxLayout, QWidget)

from ...core.dsl import js_number_to_string
from ..widgets import common as C

MAX_PREVIEW_ROWS = 300


def _num(text, default=None):
    """Number(text) 相当 (空は 0)。"""
    t = (text or "").strip()
    if t == "":
        return 0 if default is None else default
    try:
        v = float(t)
    except ValueError:
        return float("nan")
    return int(v) if v == int(v) else v


class IndexToolsDialog(QDialog):
    """
    start_options : [{value, label}]   起点/終点に選べるサブグループ
    initial_start : 起点の初期値
    get_fields    : (include_int) -> [{roleName, fieldName, type, count}]
    make_plan     : (opts dict) -> {changes, warnings, error?}   opts: start,end,mode,delta,step,base,includeStart,includeInt,target
    describe_change: (change) -> {where, field}
    """

    def __init__(self, parent, start_options, initial_start, get_fields, make_plan, describe_change,
                 title="インデックス一括調整"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(760, 640)
        self.start_options, self.get_fields, self.make_plan, self.describe = start_options, get_fields, make_plan, describe_change
        self.plan = {"changes": [], "warnings": []}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 12)
        lay.setSpacing(10)
        lay.addWidget(C.label("元のMatrixで行が増減したときなどに、サブグループをまたいで番号をまとめて直します。"
                              "-1（未選択）は変更しません。適用前に変更内容を確認できます。", "muted", wrap=True))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.start = QComboBox()
        for o in start_options:
            self.start.addItem(o["label"], o["value"])
        i = self.start.findData(initial_start)
        self.start.setCurrentIndex(max(0, i))
        self.end = QComboBox()
        self.target = QComboBox()
        self.target.setMinimumWidth(280)
        for text, w in (("起点のサブグループ", self.start), ("終点（含む）", self.end), ("対象フィールド", self.target)):
            col = QVBoxLayout()
            col.setSpacing(2)
            lb = QLabel(text)
            lb.setProperty("role", "muted")
            col.addWidget(lb)
            col.addWidget(w)
            row.addLayout(col, 1)
        lay.addLayout(row)
        self.include_int = QCheckBox("int 型のフィールドも対象に含める")
        lay.addWidget(self.include_int)
        mode_row = QHBoxLayout()
        self.rb_shift = QRadioButton("ずらす（+N / −N）")
        self.rb_seq = QRadioButton("連番にする")
        self.rb_shift.setChecked(True)
        mode_row.addWidget(self.rb_shift)
        mode_row.addWidget(self.rb_seq)
        mode_row.addStretch(1)
        lay.addLayout(mode_row)
        opts = QHBoxLayout()
        opts.setSpacing(10)
        self.delta = QLineEdit("1")
        self.delta.setFixedWidth(120)
        self.delta.setToolTip("例: 3 / -2")
        self.base = QLineEdit()
        self.base.setPlaceholderText("空=起点の値から")
        self.base.setFixedWidth(160)
        self.step = QLineEdit("1")
        self.step.setFixedWidth(100)
        self.include_start = QCheckBox()
        self.cols = {}
        for key, text, w in (("delta", "増減量", self.delta), ("base", "開始値", self.base), ("step", "増分", self.step)):
            box = QWidget()
            col = QVBoxLayout(box)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(2)
            lb = QLabel(text)
            lb.setProperty("role", "muted")
            col.addWidget(lb)
            col.addWidget(w)
            opts.addWidget(box)
            self.cols[key] = box
        opts.addWidget(self.include_start)
        opts.addStretch(1)
        lay.addLayout(opts)
        self.err = C.Banner("", "err")
        self.warns = QVBoxLayout()
        lay.addWidget(self.err)
        lay.addLayout(self.warns)
        self.preview_title = QLabel()
        self.preview_title.setStyleSheet("font-weight:700;")
        lay.addWidget(self.preview_title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.StyledPanel)
        self.pv = QWidget()
        self.pv_lay = QVBoxLayout(self.pv)
        self.pv_lay.setContentsMargins(0, 0, 0, 0)
        self.pv_lay.setSpacing(0)
        self.scroll.setWidget(self.pv)
        lay.addWidget(self.scroll, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.apply_btn = bb.addButton("適用（0件）", QDialogButtonBox.ButtonRole.AcceptRole)
        self.apply_btn.setProperty("variant", "ok")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.start.currentIndexChanged.connect(self._start_changed)
        self.include_int.toggled.connect(self._fields_changed)
        self.target.currentIndexChanged.connect(self._recalc)
        self.end.currentIndexChanged.connect(self._recalc)
        self.rb_shift.toggled.connect(self._mode_changed)
        for w in (self.delta, self.base, self.step):
            w.textChanged.connect(self._recalc)
        self.include_start.toggled.connect(self._recalc)
        self._start_changed(silent=True)
        self._fields_changed(silent=True)
        self._mode_changed(silent=True)
        self._recalc()

    # --- 入力の連動
    def _start_changed(self, *_a, silent=False):
        self.end.blockSignals(True)
        self.end.clear()
        self.end.addItem("最後まで", "")
        idx = max(0, self.start.currentIndex())
        for o in self.start_options[idx:]:
            self.end.addItem(o["label"], o["value"])
        self.end.blockSignals(False)
        if not silent:
            self._recalc()

    def _fields_changed(self, *_a, silent=False):
        self.fields = self.get_fields(self.include_int.isChecked())
        self.target.blockSignals(True)
        self.target.clear()
        self.target.addItem(f"すべて（text_list_index / voice_ref{' / int系' if self.include_int.isChecked() else ''}）", "all")
        for f in self.fields:
            self.target.addItem(f"{f['roleName']}.{f['fieldName']}（{f['type']} / {f['count']}箇所）", f"{f['roleName']}.{f['fieldName']}")
        self.target.blockSignals(False)
        if not silent:
            self._recalc()

    def _mode_changed(self, *_a, silent=False):
        shift = self.rb_shift.isChecked()
        self.cols["delta"].setVisible(shift)
        self.cols["base"].setVisible(not shift)
        self.cols["step"].setVisible(not shift)
        self.include_start.blockSignals(True)
        self.include_start.setChecked(shift)     # ずらす: 起点も含める / 連番: 起点の値から続けるので既定では含めない
        self.include_start.blockSignals(False)
        self.include_start.setText("起点のサブグループ自体も変更する" if shift else "起点のサブグループ自体も連番に含める")
        if not silent:
            self._recalc()

    def _target(self):
        key = self.target.currentData()
        if key in (None, "all"):
            return "all"
        f = next((x for x in self.fields if f"{x['roleName']}.{x['fieldName']}" == key), None)
        return {"roleName": f["roleName"], "fieldName": f["fieldName"]} if f else "all"

    def _recalc(self, *_a):
        base_t = self.base.text().strip()
        self.plan = self.make_plan({
            "start": self.start.currentData(), "end": self.end.currentData() or None,
            "mode": "shift" if self.rb_shift.isChecked() else "sequence",
            "delta": _num(self.delta.text()), "step": _num(self.step.text()),
            "base": None if base_t == "" else _num(base_t), "includeStart": self.include_start.isChecked(),
            "includeInt": self.include_int.isChecked(), "target": self._target()})
        p = self.plan
        self.err.setVisible(bool(p.get("error")))
        self.err.set_text(p.get("error") or "")
        C.clear_layout(self.warns)
        ws = p.get("warnings") or []
        for w in ws[:5]:
            self.warns.addWidget(C.Banner(w, "warn"))
        if len(ws) > 5:
            self.warns.addWidget(C.label(f"ほか {len(ws) - 5} 件の警告", "muted"))
        changes = p.get("changes") or []
        C.clear_layout(self.pv_lay)
        self.preview_title.setVisible(not p.get("error"))
        self.preview_title.setText(f"変更内容のプレビュー（{len(changes)}件）")
        if not p.get("error"):
            if not changes:
                self.pv_lay.addWidget(C.label("変更される値はありません。", "muted"))
            for c in changes[:MAX_PREVIEW_ROWS]:
                d = self.describe(c)
                # GUI版の変更は from/to が「値」、DSL版は from/to が「行内の文字位置」で値は fromValue/toValue
                fv = c["fromValue"] if "fromValue" in c else c.get("from")
                tv = c["toValue"] if "toValue" in c else c.get("to")
                r = QHBoxLayout()
                r.setContentsMargins(8, 2, 8, 2)
                r.setSpacing(12)
                a = QLabel(d["where"])
                a.setFixedWidth(120)
                r.addWidget(a)
                r.addWidget(QLabel(d["field"]), 1)
                r.addWidget(QLabel(f"{js_number_to_string(fv) if isinstance(fv, (int, float)) else fv} → <b>{js_number_to_string(tv) if isinstance(tv, (int, float)) else tv}</b>"))
                w = QWidget()
                w.setLayout(r)
                self.pv_lay.addWidget(w)
            if len(changes) > MAX_PREVIEW_ROWS:
                self.pv_lay.addWidget(C.label(f"… ほか {len(changes) - MAX_PREVIEW_ROWS} 件", "muted"))
        self.pv_lay.addStretch(1)
        self.apply_btn.setText(f"適用（{len(changes)}件）")
        self.apply_btn.setEnabled(not p.get("error") and len(changes) > 0)
