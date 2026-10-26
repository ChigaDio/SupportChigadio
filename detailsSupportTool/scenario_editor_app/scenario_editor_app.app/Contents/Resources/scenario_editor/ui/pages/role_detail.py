"""Role のフィールド定義編集 (ScenarioRoleDetailGrid.js)。settingMode でサブグループ設定(全イベント共通)も兼ねる。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QScrollArea, QTableWidget, QVBoxLayout, QWidget)

from ...core import role_detail_ops as D
from ..async_ import run_async
from ..widgets import common as C
from ..widgets import option_editors as OE
from ..widgets.field_editors import NumericEdit
from ..widgets.role_form import RoleForm
from .base import Page

COLS = ["順序", "必須", "タイプ", "名前", "説明", "配列サイズ", "オプション", "依存関係", "アクション"]
WIDTHS = [84, 56, 170, 150, 200, 96, 90, 250, 96]


class AddFieldDialog(QDialog):
    def __init__(self, parent, page):
        super().__init__(parent)
        self.page = page
        self.setWindowTitle("新しい変数を追加")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(8)
        self.type = OE.make_combo(page.type_info.get("all", []), None, editable=True)
        self.type.setCurrentIndex(-1)
        self.type.setEditText("")
        self.type.lineEdit().setPlaceholderText("例: int / FadeID / color ...")
        self.name = QLineEdit()
        self.desc = QLineEdit()
        self.array = NumericEdit(0, False)
        self.required = QCheckBox("必須（鍵マーク・DSLで省略不可にする）")
        self.required.setChecked(True)
        form.addRow("タイプ", self.type)
        form.addRow("名前", self.name)
        form.addRow("説明", self.desc)
        form.addRow("配列サイズ", self.array)
        form.addRow(self.required)
        lay.addLayout(form)
        self.opt_holder = QVBoxLayout()
        lay.addLayout(self.opt_holder)
        self.options = {}
        self.opt_editor = None
        self.type.activated.connect(lambda _i: self._type_changed())
        self.type.lineEdit().editingFinished.connect(self._type_changed)
        lay.addWidget(C.separator())
        cap = QLabel("依存関係（親フィールド）")
        cap.setStyleSheet("font-weight:700;")
        hint = QLabel("enum / bool / class_data_id を親に指定。条件値は OR（いずれか一致）。")
        hint.setProperty("role", "muted")
        lay.addWidget(cap)
        lay.addWidget(hint)
        self.parent_combo = QComboBox()
        self.parent_combo.addItem("なし（独立）", None)
        for f in D.parent_candidates(page.data, page.type_info.get("enum", []), page.type_info.get("classDataId", [])):
            self.parent_combo.addItem(f"{f['name']} ({f['type']})", f["name"])
        self.parent_combo.currentIndexChanged.connect(self._parent_changed)
        lay.addWidget(self.parent_combo)
        self.dep_holder = QVBoxLayout()
        lay.addLayout(self.dep_holder)
        self.dep_values = []
        self.dep_editor = None
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("追加")
        bb.button(QDialogButtonBox.StandardButton.Ok).setProperty("variant", "primary")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _type_changed(self):
        t = self.type.currentText().strip()
        self.options = D.default_options_for_type(t) if t in D.OPTION_EDITABLE_TYPES else {}
        C.clear_layout(self.opt_holder)
        self.opt_editor = None
        if t in D.OPTION_EDITABLE_TYPES:
            self.opt_editor = OE.make_options_editor(t, self.options, self.page.type_info)
            if self.opt_editor:
                self.opt_editor.changed.connect(lambda v: setattr(self, "options", v))
                self.opt_holder.addWidget(self.opt_editor)

    def _parent_changed(self, _i):
        name = self.parent_combo.currentData()
        C.clear_layout(self.dep_holder)
        self.dep_editor = None
        self.dep_values = []
        if not name:
            return
        parent = next((f for f in self.page.data if f.get("name") == name), None)
        self.dep_values = D.default_dep_values_for_parent(parent)
        ptype = parent.get("type") if parent else None

        def show(members):
            C.clear_layout(self.dep_holder)
            ed = OE.DependencyValuesEditor(ptype, self.dep_values, members)
            ed.changed.connect(lambda v: setattr(self, "dep_values", v))
            self.dep_editor = ed
            self.dep_holder.addWidget(ed)
        self.page.parent_member_options(ptype, show)

    def result_fields(self) -> dict:
        t = self.type.currentText().strip()
        return {"type_": t, "name": self.name.text(), "description": self.desc.text(), "array_size": self.array.value(),
                "options": self.options if t in D.OPTION_EDITABLE_TYPES else None, "required": self.required.isChecked(),
                "dep_parent": self.parent_combo.currentData(), "dep_values": self.dep_values}


class OptionsDialog(QDialog):
    def __init__(self, parent, page, row):
        super().__init__(parent)
        self.setWindowTitle("オプション編集")
        self.setMinimumWidth(640)
        self.options = row.get("options") or D.default_options_for_type(row["type"])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        ed = OE.make_options_editor(row["type"], self.options, page.type_info)
        if ed:
            ed.changed.connect(lambda v: setattr(self, "options", v))
            lay.addWidget(ed)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        bb.button(QDialogButtonBox.StandardButton.Save).setProperty("variant", "primary")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class DependencyDialog(QDialog):
    def __init__(self, parent, page, row):
        super().__init__(parent)
        self.page, self.row = page, row
        self.setWindowTitle(f"依存関係の編集 — {row.get('name')}")
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(8)
        hint = QLabel("親は enum / bool / class_data_id のみ。子は親を1人だけ持てます。条件値は OR です。")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        dep = row.get("dependency") or {}
        self.parent_name = dep.get("parentFieldName")
        self.values = [str(v) for v in dep.get("enableValues") or []] if isinstance(dep.get("enableValues"), list) else []
        self.combo = QComboBox()
        self.combo.addItem("なし（独立）", None)
        for f in D.parent_candidates(page.data, page.type_info.get("enum", []), page.type_info.get("classDataId", []), exclude_id=row.get("id")):
            self.combo.addItem(f"{f['name']} ({f['type']})", f["name"])
        i = self.combo.findData(self.parent_name)
        self.combo.setCurrentIndex(max(0, i))
        self.combo.currentIndexChanged.connect(self._changed)
        lay.addWidget(self.combo)
        self.holder = QVBoxLayout()
        lay.addLayout(self.holder)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        bb.button(QDialogButtonBox.StandardButton.Save).setProperty("variant", "primary")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._show_values()

    def _changed(self, _i):
        self.parent_name = self.combo.currentData()
        parent = next((f for f in self.page.data if f.get("name") == self.parent_name), None)
        self.values = D.default_dep_values_for_parent(parent) if parent else []
        self._show_values()

    def _show_values(self):
        C.clear_layout(self.holder)
        if not self.parent_name:
            return
        parent = next((f for f in self.page.data if f.get("name") == self.parent_name), None)
        ptype = parent.get("type") if parent else None

        def show(members):
            C.clear_layout(self.holder)
            ed = OE.DependencyValuesEditor(ptype, self.values, members)
            ed.changed.connect(lambda v: setattr(self, "values", v))
            self.holder.addWidget(ed)
        self.page.parent_member_options(ptype, show)


class RoleDetailPage(Page):
    PAGE_ID = "role_detail"
    setting_mode = False

    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self.name = ""
        self.data = []
        self.branch_type = "General"
        self.type_info = {"all": [], "enum": [], "classDataId": [], "customClassDataId": []}
        self.dirty = False
        self.loading = True
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_chip = C.Chip("", "warn")
        self.title_chip.setText("未保存の変更")
        self.title_chip.hide()
        hdr, self.title_lb = self.make_header("", None, back=lambda: self.state.go("role_list") if not self.setting_mode else self.state.go("role_list"),
                                              widgets=[self.title_chip])
        root.addWidget(hdr)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.body_lay = QVBoxLayout(body)
        self.body_lay.setContentsMargins(20, 14, 20, 20)
        self.body_lay.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        if self.setting_mode:
            self.body_lay.addWidget(C.Banner(
                "サブグループ（ロールを追加する各グループ）ごとに持たせる設定のフィールド定義です。全イベント・全サブグループで共通です。"
                "先頭の is_wait_key（入力待ち）は組み込みで、削除・改名はできません（デフォルト値は下で変更できます）。"
                "フィールドを追加・削除して「保存」すると、既存のすべてのサブグループへ反映され（追加はデフォルト値、削除は除去）、"
                "C#（ScenarioSubGroupSetting.cs）も再生成されます。", "info"))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.branch_combo = QComboBox()
        self.branch_combo.addItems(["General", "Branch"])
        self.branch_combo.currentTextChanged.connect(self._branch_changed)
        if not self.setting_mode:
            lb = QLabel("ロールタイプ")
            lb.setProperty("role", "muted")
            bar.addWidget(lb)
            bar.addWidget(self.branch_combo)
        bar.addWidget(C.button("新しい変数を追加", "primary", "plus", None, self.add_dialog))
        bar.addWidget(C.button("保存", "ok", "save", None, self.save))
        bar.addWidget(C.button("C#を生成", None, "build", None, self.generate_cs))
        if not self.setting_mode:
            bar.addWidget(C.button("削除", "danger", "trash", None, self.delete_role))
        bar.addStretch(1)
        bar.addWidget(C.icon_button("refresh", "再読み込み", self.reload))
        self.body_lay.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(260)
        for i, w in enumerate(WIDTHS):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.body_lay.addWidget(self.table, 1)
        self.defaults_box = QVBoxLayout()
        self.body_lay.addLayout(self.defaults_box)
        self.body_lay.addStretch(0)

    # ---------------------------------------------------------------- 読み込み
    def page_title(self):
        return "サブグループ設定" if self.setting_mode else f"ロール: {self.name}"

    def load(self, params):
        super().load(params)
        self.name = D.SETTING_NAME if self.setting_mode else params.get("name", "")
        self.title_lb.setText("サブグループ設定（全イベント共通）" if self.setting_mode else f"シナリオロール詳細: {self.name}")
        self.reload()

    def can_leave(self):
        if not self.dirty:
            return True
        return C.confirm(self, "保存していない変更があります。破棄して移動しますか？", "未保存の変更", "破棄して移動", danger=True)

    def reload(self):
        self.loading = True
        api = self.state.api

        def work():
            res = api.get_subgroup_setting() if self.setting_mode else api.get_role(self.name)
            info = self.state.lookups.type_options(self.setting_mode)
            return res, info

        def ok(r):
            res, info = r
            self.loading = False
            self.data, self.branch_type = D.normalize_loaded(res or {})
            self.type_info = info
            self.branch_combo.blockSignals(True)
            self.branch_combo.setCurrentText(self.branch_type)
            self.branch_combo.blockSignals(False)
            self._set_dirty(False)
            self.render()
            if self.setting_mode:
                self.load_defaults_panel()

        run_async(work, ok, lambda e: (setattr(self, "loading", False), self.fail("フィールド定義の取得に失敗", e)), self)

    def parent_member_options(self, ptype, cb):
        """親フィールドの候補値 (enum / class_data_id のみ非同期取得、bool は固定)。"""
        if not ptype or D.is_bool_type(ptype):
            cb([])
            return
        lk = self.state.lookups
        if ptype in self.type_info.get("enum", []):
            fn = lambda: lk.enum_members(ptype)  # noqa: E731
        elif ptype in self.type_info.get("classDataId", []):
            fn = lambda: lk.class_data_id_members(ptype)  # noqa: E731
        else:
            cb([])
            return
        run_async(fn, lambda ms: cb([{"value": str(m), "label": str(m)} for m in ms]), lambda e: cb([]), self)

    # ---------------------------------------------------------------- 状態
    def _set_dirty(self, d):
        self.dirty = d
        self.title_chip.setVisible(d)

    def _mutate(self, new_data, rebuild=True):
        self.data = new_data
        self._set_dirty(True)
        if rebuild:
            self.render()

    def _branch_changed(self, t):
        self.branch_type = t or "General"
        self._set_dirty(True)

    # ---------------------------------------------------------------- 描画
    def render(self):
        t = self.table
        t.setRowCount(len(self.data))
        kids = D.children_by_parent(self.data)
        for r, row in enumerate(self.data):
            builtin = self.setting_mode and bool(row.get("builtin"))
            t.setRowHeight(r, 64 if (row.get("dependency") or kids.get(row.get("name"))) else 46)
            rid = row.get("id")
            # 順序
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(2, 0, 2, 0)
            hl.setSpacing(0)
            up = C.icon_button("up", "上へ", lambda i=rid: self._mutate(D.move_field(self.data, i, -1, self.setting_mode)))
            dn = C.icon_button("down", "下へ", lambda i=rid: self._mutate(D.move_field(self.data, i, 1, self.setting_mode)))
            up.setEnabled(r > 0)
            dn.setEnabled(r < len(self.data) - 1)
            hl.addWidget(up)
            hl.addWidget(dn)
            t.setCellWidget(r, 0, w)
            # 必須
            req = row.get("required") is not False
            t.setCellWidget(r, 1, C.icon_button(
                "lock" if req else "unlock",
                "必須（DSLで省略不可）。クリックで任意に切り替え" if req else "任意（DSLで省略可・省略時はデフォルト値）。クリックで必須に切り替え",
                lambda i=rid: self._mutate(D.toggle_required(self.data, i)), color="#f2b84b" if req else "#5d667a"))
            # タイプ
            cb = OE.make_combo(self.type_info.get("all", []), row.get("type"), editable=True)
            cb.setEnabled(not builtin)
            cb.activated.connect(lambda _i, c=cb, i=rid: self._edit(i, "type", c.currentText().strip(), rebuild=True))
            cb.lineEdit().editingFinished.connect(lambda c=cb, i=rid: self._edit(i, "type", c.currentText().strip(), rebuild=True))
            t.setCellWidget(r, 2, cb)
            # 名前 / 説明
            for col, key in ((3, "name"), (4, "description")):
                e = QLineEdit(row.get(key) or "")
                e.setProperty("flat", True)
                e.setEnabled(not builtin)
                e.editingFinished.connect(lambda ed=e, k=key, i=rid: self._edit(i, k, ed.text()))
                t.setCellWidget(r, col, e)
            # 配列サイズ
            ne = NumericEdit(row.get("arraySize") or 0, False)
            ne.setEnabled(not builtin)
            ne.valueChanged.connect(lambda v, i=rid: self._edit(i, "arraySize", v))
            t.setCellWidget(r, 5, ne)
            # オプション
            if row.get("type") in D.OPTION_EDITABLE_TYPES:
                t.setCellWidget(r, 6, C.button("編集", "ghost", "edit", None, lambda rw=row: self.edit_options(rw), small=True))
            else:
                t.setCellWidget(r, 6, QWidget())
            # 依存関係
            t.setCellWidget(r, 7, self._dep_cell(row, kids))
            # アクション
            lbl = "組み込み" if builtin else "削除"
            db = C.button(lbl, "danger", None, None, lambda i=rid: self._mutate(D.delete_field(self.data, i, self.setting_mode)), small=True)
            db.setEnabled(not builtin)
            t.setCellWidget(r, 8, db)

    def _dep_cell(self, row, kids):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 2, 4, 2)
        vl.setSpacing(2)
        dep = row.get("dependency") or {}
        k = kids.get(row.get("name")) or []
        if dep.get("parentFieldName"):
            c = C.Chip("↳ " + D.dependency_summary(row), "accent", clickable=True, tooltip=D.dependency_tooltip(row))
            c.clicked.connect(lambda rw=row: self.edit_dependency(rw))
            vl.addWidget(c)
        if k:
            vl.addWidget(C.Chip("→ " + ", ".join(k), "info", tooltip="子: " + ", ".join(k)))
        if not dep.get("parentFieldName") and not k:
            b = C.button("設定", "ghost", None, None, lambda rw=row: self.edit_dependency(rw), small=True)
            vl.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        return w

    def _edit(self, row_id, key, value, rebuild=False):
        row = next((f for f in self.data if f.get("id") == row_id), None)
        if row is None or (key != "arraySize" and row.get(key) == value) or (key == "arraySize" and (row.get(key) or 0) == value):
            return
        self._mutate(D.edit_cell(self.data, row_id, key, value, self.setting_mode), rebuild=rebuild)

    # ---------------------------------------------------------------- ダイアログ
    def add_dialog(self):
        dlg = AddFieldDialog(self, self)
        if dlg.exec():
            nd, err = D.add_field(self.data, setting_mode=self.setting_mode, **dlg.result_fields())
            if err:
                C.message(self, err, "追加できません", error=True)
                return
            self._mutate(nd)

    def edit_options(self, row):
        dlg = OptionsDialog(self, self, row)
        if dlg.exec():
            self._mutate(D.set_options(self.data, row["id"], dlg.options))

    def edit_dependency(self, row):
        dlg = DependencyDialog(self, self, row)
        if dlg.exec():
            self._mutate(D.set_dependency(self.data, row["id"], dlg.parent_name, dlg.values))

    # ---------------------------------------------------------------- 保存など
    def save(self):
        payload = D.save_payload(self.data, self.branch_type)
        api = self.state.api

        def work():
            return api.save_subgroup_setting(payload["data"], payload["branchType"]) if self.setting_mode \
                else api.save_role_definition(self.name, payload["data"], payload["branchType"])

        def ok(res):
            self._set_dirty(False)
            self.state.lookups.invalidate("schema")
            self.toast(D.format_save_message(res or {}, self.setting_mode) or "保存しました", "success")
            if self.setting_mode:
                self.load_defaults_panel()
        run_async(work, ok, lambda e: self.fail("データ保存エラー", e), self)

    def generate_cs(self):
        payload = D.save_payload(self.data, self.branch_type)
        api = self.state.api
        run_async(lambda: api.generate_subgroup_setting_cs(payload["data"], payload["branchType"]) if self.setting_mode
                  else api.generate_role_cs(self.name, payload["data"], payload["branchType"]),
                  lambda res: self.toast((res or {}).get("message") or "C#を生成しました", "success"),
                  lambda e: self.fail("C#生成エラー", e), self)

    def delete_role(self):
        if not C.confirm(self, f"ロール {self.name} を削除しますか？", "削除の確認", "削除", danger=True):
            return

        def ok(res):
            self.toast((res or {}).get("message") or "削除しました", "success")
            self._set_dirty(False)
            self.state.lookups.invalidate("roles")
            self.state.go("role_list")
        run_async(lambda: self.state.api.delete_role_definition(self.name), ok, lambda e: self.fail("ロール削除エラー", e), self)

    # ---------------------------------------------------------------- サブグループ設定のデフォルト値パネル
    def load_defaults_panel(self):
        C.clear_layout(self.defaults_box)
        api = self.state.api

        def ok(res):
            sc, defaults = res.get("schema"), res.get("defaults") or []
            if not sc or sc.get("error"):
                self.defaults_box.addWidget(C.label(f"デフォルト値の読み込みエラー: {(sc or {}).get('error') or 'schema がありません'}"))
                return
            card = C.Card()
            card.body.addWidget(C.label("デフォルト値", "h2"))
            card.body.addWidget(C.label(
                "新しいサブグループに最初に入る値です。各項目右のブックマークで項目ごとに、下のボタンで全項目をまとめて保存できます"
                "（未保存の項目は型ごとの自動デフォルト）。フィールドを追加・削除した直後は、上の「保存」を先に押してください。"
                "既にあるサブグループの値は変わりません。", "muted", wrap=True))
            self._draft = defaults
            form = RoleForm(self.state, sc, defaults, role_name=D.SETTING_NAME, default_saver=self._save_field_default)
            form.changed.connect(lambda d: setattr(self, "_draft", d))
            self._defaults_form = form
            card.body.addWidget(form)
            card.body.addWidget(C.button("全項目をデフォルトとして保存", "primary", None, None, self._save_all_defaults), 0, Qt.AlignmentFlag.AlignLeft)
            self.defaults_box.addWidget(card)
        run_async(lambda: api.subgroup_setting_form_schema(), ok,
                  lambda e: self.defaults_box.addWidget(C.label(f"デフォルト値の読み込みエラー: {e}")), self)

    def _save_field_default(self, field_name, value, on_ok, on_err):
        run_async(lambda: self.state.api.save_subgroup_setting_field_default(field_name, value), lambda _r: on_ok(), on_err, self)

    def _save_all_defaults(self):
        draft = self._defaults_form.form_data() if getattr(self, "_defaults_form", None) else getattr(self, "_draft", [])
        values = {d["name"]: d["value"] for d in draft or []}
        run_async(lambda: self.state.api.save_subgroup_setting_defaults(values),
                  lambda res: self.toast((res or {}).get("message") or (res or {}).get("error") or "保存しました", "success"),
                  lambda e: self.fail("デフォルト値の保存エラー", e), self)


class SubGroupSettingPage(RoleDetailPage):
    PAGE_ID = "subgroup_setting"
    setting_mode = True
