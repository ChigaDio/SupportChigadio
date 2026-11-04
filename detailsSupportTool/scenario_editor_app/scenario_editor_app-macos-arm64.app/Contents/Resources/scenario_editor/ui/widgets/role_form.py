"""Role のデータ入力フォーム (BaseRoleInputForm.js)。スキーマから全フィールド型の入力部品を組み立てる。"""
from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...core import role_form as RF
from .. import icons, theme
from ..async_ import run_async
from . import common as C
from . import field_editors as FE


class FormEnv:
    """フォーム全体で共有する文脈 (型候補・イベント文脈・デフォルト保存の手段)。ネストしたフォームも同じものを使う。"""

    def __init__(self, state, ctx, event_id=None, sub_id=None, role_name=None, default_saver=None):
        self.state = state
        self.ctx = ctx
        self.event_id = event_id
        self.sub_id = sub_id
        self.role_name = role_name
        self.default_saver = default_saver     # (field_name, value, on_ok, on_err) -> None / None なら栞ボタン無し


def field_label(field) -> str:
    return field.get("label") or field.get("name") or ""


# ======================================================================= 単一値エディタの工場
class BoolEditor(QCheckBox):
    valueChanged = Signal(object)

    def __init__(self, text, value, parent=None):
        super().__init__(text, parent)
        self.setChecked(value is True or value == "true")
        self.toggled.connect(lambda b: self.valueChanged.emit(bool(b)))

    def value(self):
        return self.isChecked()

    def set_value(self, v):
        b = v is True or v == "true"
        if b != self.isChecked():
            self.blockSignals(True)
            self.setChecked(b)
            self.blockSignals(False)


def make_single_editor(env: FormEnv, field: dict, value, label_text=None, title=None):
    """field_editor_kind に従って 1 つの値のエディタを作る。戻り値は valueChanged/value/set_value を持つ QWidget。"""
    kind = RF.field_editor_kind(field, env.ctx)
    t = field.get("type")
    opts = field.get("options") or {}
    if kind == "voice_ref":
        return FE.VoiceRefEditor(env, value, opts)
    if kind == "text_list_index":
        return FE.TextListIndexEditor(env, value, opts)
    if kind == "bit":
        return FE.BitEditor(value, field.get("options"))
    if kind == "color":
        return FE.ColorEditor(value, env.state.recent_colors)
    if kind == "bezier":
        return FE.BezierEditor(value, field.get("options"))
    if kind == "dictionary":
        return DictionaryEditor(env, value, field.get("options"))
    if kind in ("custom_class", "class"):
        return NestedClassEditor(env, field, value, kind, title)
    if kind == "enum":
        return FE.EnumEditor(t, env.ctx["enumValues"].get(t) or [], value)
    if kind == "string":
        return FE.StringEditor(value)
    if kind == "char":
        return FE.LineValueEditor(value)
    if kind == "int":
        return FE.NumericEdit(value if value is not None else 0, False)
    if kind == "float":
        return FE.NumericEdit(value if value is not None else 0, True)
    if kind == "bool":
        return BoolEditor(label_text if label_text is not None else field_label(field), value)
    if kind == "vector":
        return FE.VectorEditor(str(t).lower(), value)
    return FE.LineValueEditor(value)


# ======================================================================= ネスト
class NestedClassEditor(QFrame):
    valueChanged = Signal(object)

    def __init__(self, env, field, value, kind, title=None, parent=None):
        super().__init__(parent)
        self.env = env
        self.setProperty("card", "flat")
        t = field.get("type")
        fields = env.ctx["customClassSchemas"].get(t) if kind == "custom_class" else env.ctx["classDataSchemas"].get(t)
        self.sub_schema = RF.build_sub_schema(fields or [])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        if title is not False:
            head = QHBoxLayout()
            head.setSpacing(6)
            tl = QLabel(title if title else field_label(field))
            tl.setStyleSheet("font-weight:700;")
            head.addWidget(tl)
            head.addWidget(C.Chip("CustomClass" if kind == "custom_class" else "Class", "accent" if kind == "custom_class" else "true"))
            head.addStretch(1)
            lay.addLayout(head)
        self.body = FormBody(env, self.sub_schema, RF.nested_initial_data(value if isinstance(value, dict) else {}, self.sub_schema),
                             bookmarks=False)
        self.body.changed.connect(lambda fd: self.valueChanged.emit(RF.nested_to_value(fd)))
        lay.addWidget(self.body)

    def value(self):
        return RF.nested_to_value(self.body.form_data())

    def set_value(self, v):
        self.body.set_initial(RF.nested_initial_data(v if isinstance(v, dict) else {}, self.sub_schema))


# ======================================================================= dictionary
class DictionaryEditor(QFrame):
    valueChanged = Signal(object)

    def __init__(self, env, value, options, parent=None):
        super().__init__(parent)
        self.env = env
        self.setProperty("card", "flat")
        self.opt = RF.dictionary_options(options)
        self.raw_options = options
        self._v = value if isinstance(value, dict) else {"entries": []}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setProperty("role", "muted")
        head.addWidget(self.summary, 1)
        head.addWidget(C.button("エントリを追加", None, "plus", None, self._add, small=True))
        lay.addLayout(head)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(6)
        lay.addLayout(self.rows)
        self._build()

    def _entries(self):
        return RF.dictionary_entries(self._v)

    def _scalar_field(self):
        return {"name": "", "type": self.opt["valueType"], "options": self.opt["valueOptions"], "arraySize": 0}

    def _build(self):
        C.clear_layout(self.rows)
        entries = self._entries()
        key_type, val_type = self.opt["keyType"], self.opt["valueType"]
        self.summary.setText(f"{len(entries)}件 / Dictionary<{key_type}, {val_type}{'[]' if self.opt['valueIsArray'] else ''}>")
        if not entries:
            em = QLabel("エントリがありません")
            em.setProperty("role", "faint")
            em.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rows.addWidget(em)
        for i, ent in enumerate(entries):
            card = QFrame()
            card.setProperty("card", "true")
            hl = QHBoxLayout(card)
            hl.setContentsMargins(8, 6, 8, 6)
            hl.setSpacing(8)
            hl.addWidget(self._key_editor(i, ent.get("key")), 0, Qt.AlignmentFlag.AlignTop)
            hl.addWidget(QLabel(":"), 0, Qt.AlignmentFlag.AlignTop)
            if self.opt["valueIsArray"]:
                hl.addWidget(self._array_value(i, ent.get("value")), 1)
            else:
                ed = make_single_editor(self.env, self._scalar_field(), ent.get("value"), label_text="", title=False)
                ed.valueChanged.connect(lambda v, idx=i: self._set_val(idx, v))
                hl.addWidget(ed, 1)
            hl.addWidget(C.icon_button("trash", "エントリを削除", lambda idx=i: self._remove(idx), color="#ef6b73"), 0, Qt.AlignmentFlag.AlignTop)
            self.rows.addWidget(card)

    def _key_editor(self, i, key):
        kt = self.opt["keyType"]
        if kt.lower() == "int":
            e = FE.NumericEdit(key if key is not None else 0, False)
            e.setFixedWidth(100)
        else:
            e = FE.EnumEditor(kt, self.env.ctx["enumValues"].get(kt) or [], key)
            e.setMinimumWidth(170)
        e.valueChanged.connect(lambda v, idx=i: self._set_key(idx, v))
        return e

    def _array_value(self, i, arr):
        arr = arr if isinstance(arr, list) else []
        box = QWidget()
        vl = QVBoxLayout(box)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(4)
        for j, item in enumerate(arr):
            r = QHBoxLayout()
            r.setSpacing(6)
            lb = QLabel(f"[{j}]")
            lb.setProperty("role", "muted")
            r.addWidget(lb)
            ed = make_single_editor(self.env, self._scalar_field(), item, label_text="", title=False)
            ed.valueChanged.connect(lambda v, ei=i, ij=j: self._set_array_item(ei, ij, v))
            r.addWidget(ed, 1)
            r.addWidget(C.icon_button("trash", "要素を削除", lambda ei=i, ij=j: self._remove_array_item(ei, ij), color="#ef6b73", size=14))
            vl.addLayout(r)
        vl.addWidget(C.button("要素を追加", None, "plus", None, lambda ei=i: self._add_array_item(ei), small=True), 0, Qt.AlignmentFlag.AlignLeft)
        return box

    def _emit(self, rebuild=True):
        if rebuild:
            self._build()
        self.valueChanged.emit(self._v)

    def _add(self):
        self._v = RF.dictionary_add_entry(self._v, self.raw_options, self.env.ctx)
        self._emit()

    def _remove(self, i):
        self._v = RF.dictionary_remove(self._v, i)
        self._emit()

    def _set_key(self, i, k):
        self._v = RF.dictionary_update(self._v, i, key=k, set_key=True)
        self._emit(False)

    def _set_val(self, i, v):
        self._v = RF.dictionary_update(self._v, i, val=v, set_val=True)
        self._emit(False)

    def _arr(self, i):
        v = self._entries()[i].get("value")
        return list(v) if isinstance(v, list) else []

    def _add_array_item(self, i):
        a = self._arr(i)
        a.append(RF.default_dict_scalar(self.opt["valueType"], self.env.ctx))
        self._v = RF.dictionary_update(self._v, i, val=a, set_val=True)
        self._emit()

    def _remove_array_item(self, i, j):
        a = self._arr(i)
        a = [x for k, x in enumerate(a) if k != j]
        self._v = RF.dictionary_update(self._v, i, val=a, set_val=True)
        self._emit()

    def _set_array_item(self, i, j, v):
        a = self._arr(i)
        while len(a) <= j:
            a.append(None)
        a[j] = v
        self._v = RF.dictionary_update(self._v, i, val=a, set_val=True)
        self._emit(False)

    def value(self):
        return self._v

    def set_value(self, v):
        self._v = v if isinstance(v, dict) else {"entries": []}
        self._build()


# ======================================================================= 配列
class DragHandle(QLabel):
    def __init__(self, owner, index):
        super().__init__()
        self.owner, self.index = owner, index
        self.setPixmap(icons.icon("drag", theme.color("faint")).pixmap(16, 16))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("ドラッグで並べ替え")

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData("application/x-scn-array", f"{id(self.owner)}:{self.index}".encode())
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)


class ArrayEditor(QFrame):
    """固定長 / 可変長の配列。可変長は追加・削除・ドラッグ並べ替え。"""
    valueChanged = Signal(object)

    def __init__(self, env, field, value, parent=None):
        super().__init__(parent)
        self.env, self.field = env, field
        self.info = RF.field_array_info(field)
        self.dynamic = self.info["kind"] == "dynamic"
        self.setProperty("card", "flat")
        self.setAcceptDrops(self.dynamic)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        tl = QLabel(field_label(field))
        tl.setStyleSheet("font-weight:700;")
        head.addWidget(tl)
        self.chip = C.Chip("", "accent" if self.dynamic else "true")
        head.addWidget(self.chip)
        head.addStretch(1)
        lay.addLayout(head)
        self.empty = QLabel("アイテムがありません。下の＋ボタンで追加してください。")
        self.empty.setProperty("role", "muted")
        lay.addWidget(self.empty)
        self.items_lay = QVBoxLayout()
        self.items_lay.setSpacing(4)
        lay.addLayout(self.items_lay)
        if self.dynamic:
            lay.addWidget(C.icon_button("plus", "アイテムを追加", self._add, color=theme.color("accent")), 0, Qt.AlignmentFlag.AlignLeft)
        self.editors = []
        self._rebuild(RF.array_value_of(field, value, env.ctx))

    def _single_field(self):
        return {**self.field, "arraySize": 0}

    def _rebuild(self, values):
        C.clear_layout(self.items_lay)
        self.editors = []
        self.rows = []
        for i, v in enumerate(values):
            row = QFrame()
            row.setProperty("card", "true")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(6, 4, 6, 4)
            hl.setSpacing(6)
            if self.dynamic:
                hl.addWidget(DragHandle(self, i), 0, Qt.AlignmentFlag.AlignTop)
            ed = make_single_editor(self.env, self._single_field(), v)
            ed.valueChanged.connect(lambda _v: self.valueChanged.emit(self.value()))
            hl.addWidget(ed, 1)
            if self.dynamic:
                hl.addWidget(C.icon_button("minus", "削除", lambda idx=i: self._remove(idx), color="#ef6b73"), 0, Qt.AlignmentFlag.AlignTop)
            self.items_lay.addWidget(row)
            self.editors.append(ed)
            self.rows.append(row)
        n = len(values)
        self.chip.setText(f"Dynamic Array ({n})" if self.dynamic else f"Array[{self.info['length']}]")
        self.empty.setVisible(self.dynamic and n == 0)

    def value(self):
        return [e.value() for e in self.editors]

    def set_value(self, v):
        self._rebuild(RF.array_value_of(self.field, v, self.env.ctx))

    def _add(self):
        vals = self.value()
        vals.append(RF.get_default_value(self.field.get("type"), 0, None, self.env.ctx))
        self._rebuild(vals)
        self.valueChanged.emit(vals)

    def _remove(self, i):
        vals = [v for k, v in enumerate(self.value()) if k != i]
        self._rebuild(vals)
        self.valueChanged.emit(vals)

    # --- DnD
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat("application/x-scn-array") and bytes(e.mimeData().data("application/x-scn-array")).decode().startswith(f"{id(self)}:"):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        try:
            src = int(bytes(e.mimeData().data("application/x-scn-array")).decode().split(":")[1])
        except (ValueError, IndexError):
            return
        y = e.position().y()
        dst = len(self.rows) - 1
        for i, r in enumerate(self.rows):
            top = r.mapTo(self, r.rect().topLeft()).y()
            if y < top + r.height() / 2:
                dst = i if i <= src else i - 1
                break
        if dst == src:
            return
        vals = RF.move_item(self.value(), src, dst)
        self._rebuild(vals)
        self.valueChanged.emit(vals)
        e.acceptProposedAction()


# ======================================================================= 本体
class FormBody(QWidget):
    """スキーマのフィールドを縦に並べる。ネストしたフォームも同じクラス (bookmarks=False)。"""
    changed = Signal(object)

    def __init__(self, env: FormEnv, schema: dict, initial_data, bookmarks=True, parent=None):
        super().__init__(parent)
        self.env = env
        self.schema = schema
        self.bookmarks = bookmarks and env.default_saver is not None
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(10)
        self.entries = []    # [{field, editor, row, bookmark}]
        self.set_initial(initial_data)

    def set_initial(self, initial_data):
        C.clear_layout(self.lay)
        self.entries = []
        data = RF.build_initial_form_data(self.schema, initial_data, self.env.ctx)
        for field, item in zip(self.schema["fields"], data):
            self._add_field(field, item["value"])
        self.lay.addStretch(1)
        self._update_visibility()

    def _add_field(self, field, value):
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        if field.get("warning"):
            w = C.Banner(field["warning"], "err")
            hl.addWidget(w, 1)
            self.lay.addWidget(row)
            self.entries.append({"field": field, "editor": None, "row": row, "value": value})
            return
        info = RF.field_array_info(field)
        if info["kind"] == "single":
            ed = make_single_editor(self.env, field, value)
            kind = RF.field_editor_kind(field, self.env.ctx)
            holder = QWidget()
            vl = QVBoxLayout(holder)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(2)
            if kind not in ("bool", "custom_class", "class"):
                cap = QLabel(field_label(field))
                cap.setProperty("role", "muted")
                if field.get("description"):
                    cap.setToolTip(field["description"])
                vl.addWidget(cap)
            vl.addWidget(ed)
            hl.addWidget(holder, 1)
        else:
            ed = ArrayEditor(self.env, field, value)
            hl.addWidget(ed, 1)
        ed.valueChanged.connect(lambda _v: self._on_change())
        bm = None
        if self.bookmarks:
            bm = C.icon_button("bookmark_fill" if field.get("default") is not None else "bookmark", "", None,
                               color=theme.color("accent") if field.get("default") is not None else theme.color("muted"))
            bm.clicked.connect(lambda _=False, f=field: self._save_default(f))
            self._bookmark_tip(bm, field)
            hl.addWidget(bm, 0, Qt.AlignmentFlag.AlignTop)
        self.lay.addWidget(row)
        self.entries.append({"field": field, "editor": ed, "row": row, "bookmark": bm})

    @staticmethod
    def _bookmark_tip(btn, field):
        btn.setToolTip("デフォルト保存済み（現在の値で更新できます）" if field.get("default") is not None
                       else "今の値をこのフィールドのデフォルト値として保存（次にこのRoleを追加した時の初期値になります）")

    def _save_default(self, field):
        entry = next(e for e in self.entries if e["field"] is field)
        value = RF.js_normalize_numbers(entry["editor"].value())
        btn = entry["bookmark"]
        btn.setEnabled(False)

        def ok():
            btn.setEnabled(True)
            field["default"] = value
            btn.setIcon(icons.icon("bookmark_fill", theme.color("accent")))
            self._bookmark_tip(btn, field)
            self.env.state.show_toast(f"「{field_label(field)}」をデフォルトとして保存しました", "success")

        def err(e):
            btn.setEnabled(True)
            C.message(self, f"デフォルト値の保存に失敗しました: {e}", "デフォルト保存", error=True)
        self.env.default_saver(field["name"], value, ok, err)

    def form_data(self) -> list:
        out = []
        for e in self.entries:
            f = e["field"]
            v = e["editor"].value() if e["editor"] is not None else e.get("value")
            out.append({"name": f["name"], "value": RF.js_normalize_numbers(v),
                        "arraySize": f["arraySize"] if f.get("arraySize") is not None else 0})
        return out

    def _update_visibility(self):
        fd = self.form_data()
        for e in self.entries:
            e["row"].setVisible(RF.is_field_enabled_by_dependency(e["field"], fd))

    def _on_change(self):
        self._update_visibility()
        self.changed.emit(self.form_data())


class RoleForm(QWidget):
    """Role データ入力フォーム。型候補を非同期で読み込んでから FormBody を作る。

    changed(list)  : ユーザー操作で値が変わったとき form_data を通知 (初期化では通知しない)
    ready()        : 型候補の読み込みが終わり、入力できる状態になった
    """
    changed = Signal(object)
    ready = Signal()

    def __init__(self, state, schema, initial=None, role_name=None, event_id=None, sub_id=None,
                 default_saver=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.schema = schema
        self.role_name, self.event_id, self.sub_id = role_name, event_id, sub_id
        self.default_saver = default_saver
        self._initial = initial or []
        self._ready = False
        self.body = None
        self.env = None
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.loading = QLabel("読み込み中...")
        self.loading.setProperty("role", "muted")
        self.lay.addWidget(self.loading)
        fields = schema.get("fields") or []
        run_async(lambda: RF.load_type_context(state.lookups, fields), self._loaded,
                  lambda e: self._loaded(RF.make_type_context()), self)

    def _loaded(self, ctx):
        self.env = FormEnv(self.state, ctx, self.event_id, self.sub_id, self.role_name, self.default_saver)
        self.loading.setVisible(False)
        self.body = FormBody(self.env, self.schema, self._initial, bookmarks=True)
        self.body.changed.connect(self.changed.emit)
        self.lay.addWidget(self.body)
        self._ready = True
        self.ready.emit()

    def is_ready(self) -> bool:
        return self._ready

    def form_data(self) -> list:
        if self.body is None:
            return list(self._initial)
        return self.body.form_data()

    def set_initial(self, initial):
        """外部から値を差し替える (DSL 適用・リセットなど)。通知は出さない。"""
        self._initial = initial or []
        if self.body is not None:
            self.body.set_initial(self._initial)
