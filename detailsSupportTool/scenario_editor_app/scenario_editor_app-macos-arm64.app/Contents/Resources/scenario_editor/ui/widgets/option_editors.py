"""フィールド定義のオプション編集 (bit / bezier / dictionary / text_list_index) と依存関係の値編集。
ScenarioRoleDetailGrid.js の *OptionsEditor / DependencyValuesEditor。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QVBoxLayout, QWidget)

from ...core import role_detail_ops as D
from . import common as C
from .field_editors import NumericEdit


def make_combo(options, current=None, editable=False) -> QComboBox:
    cb = QComboBox()
    cb.setEditable(editable)
    for o in options:
        if isinstance(o, tuple):
            cb.addItem(o[1], o[0])
        else:
            cb.addItem(str(o), o)
    if current is not None:
        i = cb.findData(current)
        if i >= 0:
            cb.setCurrentIndex(i)
        elif editable:
            cb.setEditText(str(current))
    if editable:
        cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        cb.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        cb.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    return cb


class _Base(QWidget):
    changed = Signal(object)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.options = dict(options or {})

    def value(self):
        return self.options

    def _set(self, new):
        self.options = new
        self.changed.emit(new)


class BitOptionsEditor(_Base):
    def __init__(self, options, enum_names, class_data_id_names, custom_names, parent=None):
        super().__init__(options, parent)
        self.enum_names, self.cid_names, self.custom_names = enum_names, class_data_id_names, custom_names
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 4, 0, 0)
        self.lay.setSpacing(8)
        self._build()

    def _build(self):
        C.clear_layout(self.lay)
        o = self.options
        mode = o.get("sizeMode") or "manual"
        row = QHBoxLayout()
        row.setSpacing(10)
        cb = make_combo(D.BIT_SIZE_MODES, mode)
        cb.currentIndexChanged.connect(lambda _i, c=cb: self._set({**self.options, "sizeMode": c.currentData(), "sizeSourceName": None}) or self._build())
        row.addLayout(self._labeled("ビット数の決め方", cb))
        if mode == "manual":
            ne = NumericEdit(D.bit_effective_size(o), False)
            ne.setFixedWidth(90)
            ne.valueChanged.connect(lambda v: self._set(D.bit_set_size(self.options, v)) or self._build_flags())
            row.addLayout(self._labeled("ビット数", ne))
        else:
            src = make_combo(D.bit_size_mode_source_names(mode, self.enum_names, self.cid_names, self.custom_names),
                             o.get("sizeSourceName"), editable=True)
            if not o.get("sizeSourceName"):
                src.setCurrentIndex(-1)
                src.setEditText("")
            src.activated.connect(lambda _i, c=src: self._set({**self.options, "sizeSourceName": c.currentText() or None}))
            row.addLayout(self._labeled("参照元", src))
        sel = make_combo([("multiple", "複数選択可"), ("single", "1つだけ選択（排他）")], o.get("mode") or "multiple")
        sel.currentIndexChanged.connect(lambda _i, c=sel: self._set({**self.options, "mode": c.currentData()}) or self._build())
        row.addLayout(self._labeled("選択モード", sel))
        if o.get("mode") != "single":
            chk = QCheckBox("全選択ボタンを許可")
            chk.setChecked(bool(o.get("allowSelectAll")))
            chk.toggled.connect(lambda b: self._set({**self.options, "allowSelectAll": b}))
            row.addWidget(chk, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.flags_box = QWidget()
        self.lay.addWidget(self.flags_box)
        if mode == "manual":
            self._build_flags()
        else:
            n = QLabel("※ 参照元を選択して保存すると、要素数からビット数・フラグ名が自動生成されます")
            n.setProperty("role", "muted")
            self.lay.addWidget(n)

    def _build_flags(self):
        if not hasattr(self, "flags_box") or (self.options.get("sizeMode") or "manual") != "manual":
            return
        old = self.flags_box
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        cap = QLabel("フラグ名（各ビットのラベル）")
        cap.setProperty("role", "muted")
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, name in enumerate(self.options.get("flagNames") or []):
            e = QLineEdit(name)
            e.setPlaceholderText(f"bit {i}")
            e.setToolTip(f"bit {i}")
            e.textEdited.connect(lambda t, idx=i: self._set(D.bit_set_flag_name(self.options, idx, t)))
            grid.addWidget(e, i // 4, i % 4)
        w = QWidget()
        lay.addWidget(cap)
        lay.addLayout(grid)
        w.setLayout(lay)
        self.lay.replaceWidget(old, w)
        old.setParent(None)
        old.deleteLater()
        self.flags_box = w

    @staticmethod
    def _labeled(text, widget):
        box = QVBoxLayout()
        box.setSpacing(2)
        lb = QLabel(text)
        lb.setProperty("role", "muted")
        box.addWidget(lb)
        box.addWidget(widget)
        return box


class BezierOptionsEditor(_Base):
    def __init__(self, options, parent=None):
        super().__init__(options, parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(10)
        vt = make_combo(["float", "int"], self.options.get("valueType") or "float")
        vt.currentIndexChanged.connect(lambda _i: self._set({**self.options, "valueType": vt.currentData()}))
        mn = NumericEdit(self.options.get("min", 0) if self.options.get("min") is not None else 0, True)
        mx = NumericEdit(self.options.get("max", 1) if self.options.get("max") is not None else 1, True)
        mn.valueChanged.connect(lambda v: self._set({**self.options, "min": v}))
        mx.valueChanged.connect(lambda v: self._set({**self.options, "max": v}))
        for text, w in (("値の型", vt), ("グラフの最小値", mn), ("グラフの最大値", mx)):
            row.addLayout(BitOptionsEditor._labeled(text, w))
        row.addStretch(1)


class TextListIndexOptionsEditor(_Base):
    def __init__(self, options, parent=None):
        super().__init__(options, parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(10)
        d = D.DEFAULT_TEXT_LIST_INDEX_OPTIONS
        for key, text, hint in (("matrixName", "Matrix名", "例: ScenarioText"),
                                ("fieldName", "フィールド名", "List<string> のフィールド。例: texts"),
                                ("previewLanguage", "プレビュー言語", "候補表示に使う行。例: Ja")):
            e = QLineEdit(self.options.get(key, d[key]))
            e.setToolTip(hint)
            e.textEdited.connect(lambda t, k=key: self._set({**self.options, k: t}))
            box = BitOptionsEditor._labeled(text, e)
            h = QLabel(hint)
            h.setProperty("role", "faint")
            box.addWidget(h)
            row.addLayout(box, 1)


class DictionaryOptionsEditor(_Base):
    def __init__(self, options, key_type_options, value_type_options, enum_names, cid_names, custom_names, parent=None):
        super().__init__(options, parent)
        self.kt, self.vt = key_type_options, value_type_options
        self.names = (enum_names, cid_names, custom_names)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 4, 0, 0)
        self.lay.setSpacing(8)
        self._build()

    def _build(self):
        C.clear_layout(self.lay)
        o = self.options
        row = QHBoxLayout()
        row.setSpacing(10)
        kt = make_combo(self.kt, o.get("keyType") or "int")
        kt.currentIndexChanged.connect(lambda _i: self._set({**self.options, "keyType": kt.currentData()}))
        vt = make_combo(self.vt, o.get("valueType") or "int", editable=True)
        vt.activated.connect(lambda _i: self._value_type(vt.currentText()))
        vt.lineEdit().editingFinished.connect(lambda: self._value_type(vt.currentText()))
        sz = NumericEdit(o.get("valueArraySize") or 0, False)
        sz.setFixedWidth(110)
        sz.valueChanged.connect(lambda v: self._set({**self.options, "valueArraySize": v or 0}))
        row.addLayout(BitOptionsEditor._labeled("キーの型", kt))
        row.addLayout(BitOptionsEditor._labeled("値の型", vt))
        row.addLayout(BitOptionsEditor._labeled("値の配列サイズ（0=単一, -1=可変長, N>0=固定長）", sz))
        row.addStretch(1)
        self.lay.addLayout(row)
        n = QLabel("キーは数値のみ（int / Enum / ClassDataID / CustomClassDataID）です。値はどの型でも指定できます。")
        n.setProperty("role", "muted")
        self.lay.addWidget(n)
        vtype = o.get("valueType") or "int"
        if vtype in ("bit", "bezier"):
            box = QFrame()
            box.setProperty("card", "flat")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 8, 10, 8)
            cap = QLabel("値の型オプション")
            cap.setProperty("role", "muted")
            bl.addWidget(cap)
            vo = o.get("valueOptions") or {}
            ed = BitOptionsEditor(vo, *self.names) if vtype == "bit" else BezierOptionsEditor(vo)
            ed.changed.connect(lambda v: self._set({**self.options, "valueOptions": v}))
            bl.addWidget(ed)
            self.lay.addWidget(box)

    def _value_type(self, text):
        text = (text or "").strip() or "int"
        if text == self.options.get("valueType"):
            return
        self._set({**self.options, "valueType": text, "valueOptions": {}})
        self._build()


def make_options_editor(type_, options, type_info, setting_modes=None):
    """型に応じたオプション編集部品 (無ければ None)。type_info = lookups.type_options() の結果。"""
    enum_names = type_info.get("enum", [])
    cid = type_info.get("classDataId", [])
    custom = type_info.get("customClassDataId", [])
    if type_ == "bit":
        return BitOptionsEditor(options, enum_names, cid, custom)
    if type_ == "bezier":
        return BezierOptionsEditor(options)
    if type_ == "text_list_index":
        return TextListIndexOptionsEditor(options)
    if type_ == "dictionary":
        keys = D.key_type_options(enum_names, cid, custom)
        vals = [t for t in type_info.get("all", []) if t != "dictionary"]
        return DictionaryOptionsEditor(options, keys, vals, enum_names, cid, custom)
    return None


class DependencyValuesEditor(QWidget):
    """依存関係の「有効になる値」。選択済みチップ + 追加ドロップダウン (OR)。"""
    changed = Signal(object)

    def __init__(self, parent_type, values, member_options, parent=None):
        super().__init__(parent)
        self.selected = [str(v) for v in values or []]
        self.is_bool = bool(parent_type) and D.is_bool_type(parent_type)
        self.options = D.dependency_value_options(parent_type, member_options)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)
        self.chips_box = QWidget()
        self.chips_lay = C.FlowLayout(self.chips_box)
        lay.addWidget(self.chips_box)
        row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.combo.lineEdit().setPlaceholderText("True または False" if self.is_bool else "値を検索して選択...")
        row.addWidget(self.combo, 1)
        row.addWidget(C.button("追加", None, "plus", None, self._add))
        lay.addLayout(row)
        note = QLabel("親がこれらの値のいずれかと一致するとき編集可能（OR）")
        note.setProperty("role", "muted")
        lay.addWidget(note)
        self._refresh()

    def _refresh(self):
        C.clear_layout(self.chips_lay)
        if not self.selected:
            t = QLabel("まだ条件がありません。下から追加してください")
            t.setProperty("role", "faint")
            self.chips_lay.addWidget(t)
        for v in self.selected:
            label = next((o["label"] for o in self.options if o["value"] == v or o["label"] == v), v)
            chip = C.Chip(f"{label}  ✕", "accent", clickable=True, tooltip="クリックで削除")
            chip.clicked.connect(lambda val=v: self._remove(val))
            self.chips_lay.addWidget(chip)
        self.combo.clear()
        for o in self.options:
            if o["value"] not in self.selected:
                self.combo.addItem(o["label"], o["value"])
        self.combo.setCurrentIndex(-1)
        self.chips_box.updateGeometry()

    def _add(self):
        i = self.combo.currentIndex()
        v = self.combo.itemData(i) if i >= 0 else None
        if v is None:
            t = self.combo.currentText().strip()
            j = self.combo.findText(t, Qt.MatchFlag.MatchFixedString)
            v = self.combo.itemData(j) if j >= 0 else None
        self.selected = D.add_dependency_value(self.selected, v)
        self._refresh()
        self.changed.emit(list(self.selected))

    def _remove(self, v):
        self.selected = D.remove_dependency_value(self.selected, v)
        self._refresh()
        self.changed.emit(list(self.selected))

    def value(self):
        return list(self.selected)
