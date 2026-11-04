"""遷移エディタの右ドロワー群: Role選択 / サブグループ設定 / データ入力 (ScenarioEventTransition.js, SubGroupSettingControls.js)。"""
from __future__ import annotations

import json

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QInputDialog, QMenu, QScrollArea, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from ...core import diff as D
from ...core import dsl as DSL
from ...core import subgroup_setting as SGS
from ...core.dsl import js_json_stringify
from .. import icons, theme
from ..async_ import run_async
from ..widgets import common as C
from ..widgets.dsl_editor import DslEditor
from ..widgets.role_form import RoleForm
from .diff_dialog import RolePreviewDialog


def _frame_scroll(inner: QWidget) -> QScrollArea:
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.Shape.NoFrame)
    sc.setWidget(inner)
    return sc


# ======================================================================== Role 選択
class RoleSelectDrawer(C.Drawer):
    """ノードへ追加する Role を選ぶ。Role名・説明で絞り込み。"""

    def __init__(self, parent):
        super().__init__(parent, 360)
        self.close_requested.connect(self.close_)
        self.on_pick = None
        self.roles = []
        self.title = self.header("Role 追加", "role")
        self.sub = C.label("", "muted")
        self.sub.setContentsMargins(16, 6, 16, 0)
        self.body.addWidget(self.sub)
        self.search = C.SearchEdit("Role名・説明で検索...")
        self.search.setContentsMargins(0, 0, 0, 0)
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(12, 8, 12, 4)
        wl.addWidget(self.search)
        self.body.addWidget(w)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(12, 4, 12, 12)
        self.list_lay.setSpacing(6)
        self.body.addWidget(_frame_scroll(self.list_host), 1)
        self.search.textChanged.connect(self._render)

    def open_for(self, node_id, roles, on_pick):
        self.on_pick = on_pick
        self.roles = list(roles or [])
        self.sub.setText(f"ノード {node_id}")
        self.search.setText("")
        self._render()
        self.open_()
        self.search.setFocus()

    def set_roles(self, roles):
        self.roles = list(roles or [])
        self._render()

    def _render(self, *_):
        C.clear_layout(self.list_lay)
        q = self.search.text().strip().lower()
        roles = [r for r in self.roles if not q or q in (r.get("name") or "").lower() or q in (r.get("description") or "").lower()]
        if not self.roles:
            self.list_lay.addWidget(C.label("Roleが登録されていません", "muted"))
        elif not roles:
            self.list_lay.addWidget(C.label(f"「{self.search.text()}」に一致するRoleが見つかりません", "muted"))
        for r in roles:
            card = C.Card(flat=True)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            nm = C.label(r.get("name") or "")
            nm.setStyleSheet("font-weight:700;")
            card.body.addWidget(nm)
            if r.get("description"):
                card.body.addWidget(C.label(r["description"], "muted", wrap=True))
            card.mousePressEvent = (lambda e, r=r: self._pick(r))
            self.list_lay.addWidget(card)
        self.list_lay.addStretch(1)

    def _pick(self, role):
        cb = self.on_pick
        self.close_()
        if cb:
            cb(role)


# ======================================================================== サブグループ設定
class SubGroupSettingDrawer(C.Drawer):
    """入力中の値は内部にだけ持ち、閉じたときに変更があった場合だけ onApply する。"""

    def __init__(self, parent, state):
        super().__init__(parent, 480)
        self.state = state
        self.close_requested.connect(self.finish)
        self.form = None
        self.on_apply = None
        self.schema = None
        self.initial_json = "[]"
        self.title = self.header("サブグループ設定", "tune")
        self.scroll_host = QWidget()
        self.lay = QVBoxLayout(self.scroll_host)
        self.lay.setContentsMargins(16, 12, 16, 12)
        self.lay.setSpacing(10)
        self.body.addWidget(_frame_scroll(self.scroll_host), 1)
        self.body.addWidget(C.separator())
        foot = QHBoxLayout()
        foot.setContentsMargins(12, 10, 12, 10)
        foot.addStretch(1)
        foot.addWidget(C.button("閉じる（変更を反映）", "primary", on_click=self.finish))
        self.body.addLayout(foot)

    def open_for(self, title, schema, setting, defaults, on_apply, event_id, sub_id):
        self.on_apply, self.schema = on_apply, schema
        self.title.set_full_text(title or "サブグループ設定")
        C.clear_layout(self.lay)
        self.form = None
        if not schema:
            self.lay.addWidget(C.label("設定のフィールド定義を読み込めませんでした。", "muted"))
        else:
            init = DSL.normalize_sub_group_setting(setting, schema, defaults)
            self.initial_json = js_json_stringify(init)
            self.draft = init
            self.lay.addWidget(C.label(
                f"全イベント共通のサブグループ設定です（フィールドの追加は「サブグループ設定」ページから）。{SGS.IS_WAIT_KEY_FIELD} は入力待ちフラグです。"
                "ブックマークで、その値を新規サブグループのデフォルトにできます。", "muted", wrap=True))
            api = self.state.api

            def saver(field, value, ok, err):
                run_async(lambda: api.save_subgroup_setting_field_default(field, value), lambda _r: ok(), err, self)

            self.form = RoleForm(self.state, schema, init, role_name=SGS.SUBGROUP_SETTING_ROLE_NAME, event_id=event_id,
                                 sub_id=sub_id, default_saver=saver)
            self.form.changed.connect(lambda data: setattr(self, "draft", SGS.form_data_to_setting(data, self.schema)))
            self.lay.addWidget(self.form)
        self.lay.addStretch(1)
        self.open_()

    def finish(self):
        if self.form is not None and self.on_apply and js_json_stringify(self.draft) != self.initial_json:
            self.on_apply(self.draft)
        self.on_apply = None
        self.close_()


# ======================================================================== データ入力
class _Collapsible(QFrame):
    def __init__(self, title_widgets, expanded=True):
        super().__init__()
        self.setProperty("card", "flat")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.arrow = C.icon_button("down" if expanded else "right", "開閉", self.toggle, size=14)
        head.addWidget(self.arrow)
        for w in title_widgets:
            head.addWidget(w)
        lay.addLayout(head)
        self.content = QWidget()
        self.cl = QVBoxLayout(self.content)
        self.cl.setContentsMargins(0, 0, 0, 0)
        self.content.setVisible(expanded)
        lay.addWidget(self.content)

    def toggle(self):
        v = not self.content.isVisible()
        self.content.setVisible(v)
        self.arrow.setIcon(icons.icon("down" if v else "right"))


class RoleDataDrawer(C.Drawer):
    """ノード内の Role の値を、GUI フォーム / テキスト(DSL) で編集する。

    ops (SimpleNamespace) が必要とするもの:
      get_roles() / role_schemas() / class_schemas() / initial_state() -> {uid: formData}
      save_many(items, on_ok, on_err) / delete_role(uid) / add_role(role) / flush_structure(on_done(ok))
      update_draft(state) / paste_roles() / navigate(dir) / closed()
    """

    def __init__(self, parent, state):
        super().__init__(parent, 660)
        self.state = state
        self.close_requested.connect(self.request_close)
        self.ops = None
        self.node_id = self.node_path = ""
        self.roles = []
        self.forms, self.ready, self.baseline, self.form_state = {}, {}, {}, {}
        self.cards = {}
        self._empty = None
        self.fresh = {}
        self.mode = "gui"
        self.batch_saving = False
        self.has_prev = self.has_next = False
        self._unsub = state.presets.subscribe(self._presets_changed)

        # --- ヘッダ
        self.head = QFrame()
        hl = QVBoxLayout(self.head)
        hl.setContentsMargins(16, 12, 10, 10)
        hl.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(6)
        tb = QVBoxLayout()
        tb.setSpacing(0)
        self.title = C.label("データ入力", "h2")
        self.subtitle = C.ElidedLabel("")
        self.subtitle.setProperty("role", "muted")
        tb.addWidget(self.title)
        tb.addWidget(self.subtitle)
        top.addLayout(tb, 1)
        top.addWidget(C.icon_button("close", "閉じる", lambda: self.request_close()))
        hl.addLayout(top)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.prev_btn = C.icon_button("up", "前のサブグループ（保存して移動 / Alt+↑）", lambda: self.navigate("prev"))
        self.next_btn = C.icon_button("down", "次のサブグループ（保存して移動 / Alt+↓）", lambda: self.navigate("next"))
        self.mode_btn = C.button("テキスト入力へ", on_click=self.toggle_mode, small=True)
        self.apply_btn = C.button("適用して保存", "ok", "save", on_click=self.apply_dsl, small=True)
        self.save_btn = C.button("一括保存", "ok", "save", on_click=self.batch_save, small=True)
        for w in (self.prev_btn, self.next_btn, self.mode_btn, self.apply_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self.save_btn)
        hl.addLayout(bar)
        self.body.addWidget(self.head)
        self.accent_bar = QFrame()
        self.accent_bar.setFixedHeight(4)
        self.body.addWidget(self.accent_bar)

        # --- 本体
        self.stack = QStackedWidget()
        self.gui_host = QWidget()
        gl = QVBoxLayout(self.gui_host)
        gl.setContentsMargins(12, 10, 12, 12)
        gl.setSpacing(8)
        tools = QHBoxLayout()
        self.copy_all_btn = C.button("全Roleをコピー", icon_name="copy", on_click=self.copy_all, small=True)
        self.paste_btn = C.button("貼り付け", icon_name="paste", on_click=self.paste, small=True)
        tools.addWidget(self.copy_all_btn)
        tools.addWidget(self.paste_btn)
        tools.addStretch(1)
        gl.addLayout(tools)
        self.cards_lay = QVBoxLayout()
        self.cards_lay.setSpacing(8)
        gl.addLayout(self.cards_lay)
        gl.addStretch(1)
        self.stack.addWidget(_frame_scroll(self.gui_host))

        self.dsl_host = QWidget()
        dl = QVBoxLayout(self.dsl_host)
        dl.setContentsMargins(12, 10, 12, 12)
        dl.setSpacing(8)
        dl.addWidget(C.Banner("1行1コマンド形式: RoleName field1=値 field2=値。文字列は \"...\"、ベクトルは (x, y, z)、配列は [a, b, c]、"
                              "行頭 # はコメントです。入力中はRole名・フィールド名・値の候補が自動的に表示されます。", "info"))
        self.dsl = DslEditor(state, show_utils=False)
        dl.addWidget(self.dsl, 1)
        self.dsl_diag = C.Banner("", "err")
        self.dsl_diag.hide()
        dl.addWidget(self.dsl_diag)
        self.stack.addWidget(self.dsl_host)
        self.body.addWidget(self.stack, 1)

        for key, d in (("Alt+Up", "prev"), ("Alt+Down", "next")):
            QShortcut(QKeySequence(key), self, activated=lambda d=d: self._key_nav(d), context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # ---------------------------------------------------------------- 開く
    def open_for(self, node, node_path, tint, has_prev, has_next, ops):
        self.ops, self.node_id, self.node_path = ops, node.get("id"), node_path
        self.has_prev, self.has_next = has_prev, has_next
        d = node.get("data") if isinstance(node.get("data"), dict) else {}
        desc = (d.get("description") or "").split("\n")[0]
        self.roles = list(ops.get_roles())
        self.subtitle.set_full_text(f"ノード {self.node_id} / {len(self.roles)} Role" + (f" — {desc}" if desc else ""))
        self.accent_bar.setStyleSheet(f"background:{tint['accent'] if tint else 'transparent'};")
        self.forms, self.ready, self.baseline, self.cards, self.fresh = {}, {}, {}, {}, {}
        self.form_state = dict(ops.initial_state())
        self.mode = "gui"
        self.stack.setCurrentIndex(0)
        self._update_buttons()
        C.clear_layout(self.cards_lay)
        self._sync_cards()
        self.open_()
        self._refresh_schemas()

    def _update_buttons(self):
        gui = self.mode == "gui"
        self.prev_btn.setVisible(gui and self.ops is not None)
        self.next_btn.setVisible(gui and self.ops is not None)
        self.prev_btn.setEnabled(self.has_prev and not self.batch_saving)
        self.next_btn.setEnabled(self.has_next and not self.batch_saving)
        self.mode_btn.setText("テキスト入力へ" if gui else "GUI入力へ")
        self.apply_btn.setVisible(not gui)
        self.save_btn.setEnabled(gui and not self.batch_saving)
        self.save_btn.setText("保存中..." if self.batch_saving else "一括保存")
        clip = self.state.clipboard.get()
        self.paste_btn.setText(f"貼り付け（{len(clip)}件）" if clip else "貼り付け")
        self.paste_btn.setEnabled(bool(clip))
        self.paste_btn.setToolTip(", ".join(c.get("name", "") for c in clip) if clip else "コピーしたRoleがありません")
        self.copy_all_btn.setEnabled(bool(self.roles))

    def _presets_changed(self):
        try:
            self._update_buttons()
        except RuntimeError:   # 破棄済み
            pass

    def _effective_schemas(self):
        return {**(self.ops.role_schemas() if self.ops else {}), **self.fresh}

    # ---------------------------------------------------------------- カード
    def _sync_cards(self):
        """self.roles に合わせてカードを作る/消す。既にあるカードとフォームは保つ。"""
        wanted = [str(r.get("uniqueId")) for r in self.roles]
        for uid in list(self.cards):
            if uid not in wanted:
                w = self.cards.pop(uid)
                self.forms.pop(uid, None)
                self.ready.pop(uid, None)
                w.setParent(None)
                w.deleteLater()
        for i, r in enumerate(self.roles):
            uid = str(r.get("uniqueId"))
            if uid not in self.cards:
                self.cards[uid] = self._make_card(r, expanded=(i == 0))
            idx = self.cards_lay.indexOf(self.cards[uid])
            if idx != i:
                self.cards_lay.insertWidget(i, self.cards[uid])
        if not self.roles:
            self._empty = self._empty or C.Banner("Roleがありません", "info")
            if self.cards_lay.indexOf(self._empty) < 0:
                self.cards_lay.addWidget(self._empty)
            self._empty.show()
        elif self._empty is not None:
            self._empty.hide()

    def _make_card(self, role, expanded):
        uid = str(role.get("uniqueId"))
        name = C.label(role.get("name") or "")
        name.setStyleSheet("font-weight:700;")
        items = [name]
        bt = role.get("branchType")
        if bt and bt != "General":
            items.append(C.Chip(str(bt), "accent"))
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        items.append(spacer)
        items.append(C.icon_button("copy", "このRoleをコピー（値ごと。別のサブグループへ貼り付けできます）", lambda r=role: self.copy_role(r), size=15))
        pb = C.icon_button("bookmark", "プリセット（保存 / 呼び出し）", size=15)
        pb.clicked.connect(lambda _=False, r=role, b=pb: self.preset_menu(r, b))
        items.append(pb)
        items.append(C.icon_button("save", "保存", lambda u=uid: self.save_one(u), size=15, color=theme.color("accent")))
        items.append(C.icon_button("trash", "削除", lambda u=uid: self.delete_role(u), size=15, color=theme.color("err")))
        card = _Collapsible(items, expanded)
        card.slot = card.cl
        card.slot.addWidget(C.label("フォームを読み込み中...", "muted"))
        return card

    def _refresh_schemas(self):
        """開くたびに最新スキーマを取り、フォームを(再)作成する。"""
        roles = [r for r in self.roles if str(r.get("uniqueId")) not in self.forms]
        lookups = self.state.lookups
        names = sorted({r.get("name") for r in roles})

        def work():
            out = {}
            for n in names:
                try:
                    out[n] = lookups.role_form_schema(n, True)
                except Exception as e:  # noqa: BLE001
                    out[n] = e
            return out

        def ok(res):
            for n, v in res.items():
                if not isinstance(v, Exception):
                    self.fresh[n] = v
            if self.ops is None:
                return
            if self.mode == "text":
                self._apply_schemas_to_dsl()
            for r in roles:
                uid = str(r.get("uniqueId"))
                if uid in self.forms or uid not in self.cards:
                    continue
                v = res.get(r.get("name"))
                if isinstance(v, Exception) or not v:
                    self._form_error(uid, str(v))
                    continue
                self._make_form(r, v)

        run_async(work, ok, lambda e: None, self)

    def _form_error(self, uid, msg):
        card = self.cards.get(uid)
        if card:
            C.clear_layout(card.slot)
            card.slot.addWidget(C.Banner(f"エラー: {msg}", "err"))

    def _default_saver(self, role_name):
        api = self.state.api

        def saver(field, value, ok, err):
            run_async(lambda: api.save_role_field_default(role_name, field, value), lambda _r: ok(), err, self)
        return saver

    def _make_form(self, role, schema, initial=None):
        uid = str(role.get("uniqueId"))
        card = self.cards[uid]
        init = initial if initial is not None else (self.form_state.get(uid) or role.get("data") or [])
        self.baseline[uid] = json.dumps(self.form_state.get(uid) or role.get("data") or [], ensure_ascii=False, sort_keys=True)
        form = RoleForm(self.state, schema, init, role_name=role.get("name"), event_id=self.ops.event_id, sub_id=self.ops.sub_id,
                        default_saver=self._default_saver(role.get("name")))
        self.forms[uid] = form
        self.ready[uid] = False
        form.changed.connect(lambda data, u=uid: self._on_form(u, data))
        form.ready.connect(lambda u=uid, f=form: self._on_form(u, f.form_data()))
        C.clear_layout(card.slot)
        card.slot.addWidget(form)

    def _on_form(self, uid, data):
        self.form_state[uid] = data
        self.ready[uid] = True
        if self.ops:
            self.ops.update_draft({uid: data})

    @staticmethod
    def _j(v):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)

    def _current_data(self, role):
        return self.form_state.get(str(role.get("uniqueId"))) or role.get("data") or []

    # ---------------------------------------------------------------- 保存
    def _to_save(self):
        return [r for r in self.roles if self.ready.get(str(r.get("uniqueId")))
                and self.form_state.get(str(r.get("uniqueId"))) is not None
                and self._j(self.form_state[str(r.get("uniqueId"))]) != self.baseline.get(str(r.get("uniqueId")))]

    def save_one(self, uid):
        if not self.ready.get(uid):
            self.state.show_toast("フォームの読み込み中です。少し待ってから保存してください", "warning")
            return
        data = self.form_state[uid]
        j = self._j(data)

        def ok():
            self.baseline[uid] = j
        self.ops.save_many([{"uniqueId": uid, "formData": data}], ok, lambda e: None)
        self.state.show_toast("保存しました", "success")

    def batch_save(self):
        if any(not self.ready.get(str(r.get("uniqueId"))) for r in self.roles):
            self.state.show_toast("フォームの読み込み中のRoleがあります。少し待ってから保存してください", "warning")
            return
        snap = dict(self.form_state)
        items = [{"uniqueId": str(r.get("uniqueId")), "formData": snap[str(r.get("uniqueId"))]}
                 for r in self.roles if snap.get(str(r.get("uniqueId"))) is not None]
        self.batch_saving = True
        self._update_buttons()

        def done(ok):
            self.batch_saving = False
            self._update_buttons()
            if ok:
                for it in items:
                    self.baseline[it["uniqueId"]] = self._j(it["formData"])
                self.state.show_toast("一括保存しました", "success")
        self.ops.save_many(items, lambda: done(True), lambda e: done(False))

    # ---------------------------------------------------------------- 閉じる
    def request_close(self, after=None):
        """変更のあった Role だけ保存してから閉じる。after があれば閉じた後に呼ぶ。"""
        if self.batch_saving or self.ops is None:
            return
        ops = self.ops
        todo = self._to_save() if self.mode == "gui" else []
        items = [{"uniqueId": str(r.get("uniqueId")), "formData": self.form_state[str(r.get("uniqueId"))]} for r in todo]

        def finish():
            self.batch_saving = False
            self.forms, self.ready, self.cards = {}, {}, {}
            C.clear_layout(self.cards_lay)
            self.close_()
            self._update_buttons()
            ops.closed()
            self.ops = None
            if after:
                after()
        if items:
            self.batch_saving = True
            self._update_buttons()
            ops.save_many(items, finish, lambda e: finish())   # 失敗しても閉じる(閉じられなくなるのを避ける)
        else:
            finish()

    def navigate(self, d):
        if self.batch_saving or self.ops is None or self.mode != "gui":
            return
        ops = self.ops
        self.request_close(after=lambda: ops.navigate(d))

    def _key_nav(self, d):
        if (d == "prev" and self.has_prev) or (d == "next" and self.has_next):
            self.navigate(d)

    # ---------------------------------------------------------------- コピー / プリセット
    def _clip_item(self, role):
        return {"id": role.get("id"), "name": role.get("name"), "branchType": role.get("branchType"), "data": self._current_data(role)}

    def copy_role(self, role):
        self.state.clipboard.set([self._clip_item(role)])
        self._update_buttons()
        self.state.show_toast(f"{role.get('name')} をコピーしました")

    def copy_all(self):
        self.state.clipboard.set([self._clip_item(r) for r in self.roles])
        self._update_buttons()
        self.state.show_toast(f"{len(self.roles)}件のRoleをコピーしました")

    def paste(self):
        if self.ops:
            self.ops.paste_roles()

    def refresh_roles(self):
        """Role の追加・削除(貼り付けや DSL 適用)を反映する。"""
        if self.ops is None:
            return
        self.roles = list(self.ops.get_roles())
        self._sync_cards()
        self._refresh_schemas()
        self._update_buttons()

    def delete_role(self, uid):
        self.ops.delete_role(uid)
        self.form_state.pop(uid, None)
        self.refresh_roles()

    def preset_menu(self, role, anchor):
        pm = self.state.presets
        run_async(pm.refresh, lambda _r: None, lambda e: None, self)
        m = QMenu(self)
        m.addAction(icons.icon("bookmark"), "現在の値をプリセットとして保存…", lambda: self.save_preset(role))
        items = pm.list_presets(role.get("name"))
        if not items:
            a = m.addAction(f"「{role.get('name')}」のプリセットはまだありません")
            a.setEnabled(False)
        for p in items:
            from datetime import datetime
            try:
                when = datetime.fromtimestamp((p.get("savedAt") or 0) / 1000).strftime("%Y/%m/%d %H:%M")
            except (OSError, ValueError, OverflowError):
                when = ""
            sub = m.addMenu(f"{p['name']}　（{'このPCのみ（未共有）' if p.get('local') else '共有'} ・ {when}）")
            sub.addAction("適用", lambda n=p["name"]: self.apply_preset(role, n))
            sub.addAction(icons.icon("trash"), "削除", lambda n=p["name"], loc=p.get("local"): self.delete_preset(role, n, loc))
        n_local = pm.get_local_only_count()
        if n_local > 0:
            m.addSeparator()
            m.addAction(f"このPC内のプリセット {n_local}件をサーバーへ移行", self.migrate_presets)
        m.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))

    def save_preset(self, role):
        name, ok = QInputDialog.getText(self, "プリセットの保存", f"「{role.get('name')}」の現在の値を、プリセットとして保存します（チームで共有されます）。\nプリセット名:")
        if not ok:
            return
        data = self._current_data(role)
        pm = self.state.presets

        def done(r):
            if not r.get("ok"):
                self.state.show_toast(r.get("error") or "プリセットを保存できませんでした（名前が空、または保存領域がいっぱいです）", "error")
            elif r.get("shared"):
                self.state.show_toast(f"プリセット「{name.strip()}」を共有プリセットとして保存しました", "success")
            else:
                self.state.show_toast(f"サーバーに接続できなかったため、「{name.strip()}」はこのPCにだけ保存しました（後でサーバーへ移行できます）", "warning")
        run_async(lambda: pm.save_preset(role.get("name"), name, data), done, lambda e: self.state.show_toast(str(e), "error"), self)

    def delete_preset(self, role, name, local):
        if not C.confirm(self, f"プリセット「{name}」を削除しますか？{'' if local else '（チーム全員から消えます）'}", "確認", "削除", danger=True):
            return
        pm = self.state.presets

        def done(ok):
            if not ok:
                self.state.show_toast("削除できませんでした。サーバーとの接続を確認してください", "error")
        run_async(lambda: pm.delete_preset(role.get("name"), name), done, lambda e: self.state.show_toast(str(e), "error"), self)

    def migrate_presets(self):
        pm = self.state.presets

        def done(r):
            if not r.get("ok"):
                self.state.show_toast("サーバーへ移行できませんでした。接続を確認してください", "error")
                return
            self.state.show_toast(f"このPC内のプリセットを共有しました（取り込み {r.get('imported')}件"
                                  + (f" / 同名のためスキップ {r.get('skipped')}件" if r.get("skipped") else "") + "）", "success")
        run_async(pm.migrate_local_presets, done, lambda e: self.state.show_toast(str(e), "error"), self)

    def apply_preset(self, role, name):
        data = self.state.presets.get_preset_data(role.get("name"), name)
        if data is None:
            return
        uid = str(role.get("uniqueId"))
        f = self.forms.get(uid)
        if f is None:
            return
        f.set_initial(data)
        self._on_form(uid, f.form_data())
        self.state.show_toast(f"プリセット「{name}」を適用しました（保存で確定）")

    # ---------------------------------------------------------------- テキスト(DSL)モード
    def _apply_schemas_to_dsl(self):
        schemas = self._effective_schemas()
        self.dsl.set_schemas(list(schemas.keys()), schemas, self.ops.class_schemas())

    def toggle_mode(self):
        if self.mode == "gui":
            roles = [{"uniqueId": r.get("uniqueId"), "name": r.get("name"), "data": self._current_data(r)} for r in self.roles]
            self._apply_schemas_to_dsl()
            self.dsl.set_text(DSL.decompile_roles(roles, self._effective_schemas(), self.ops.class_schemas()))
            self.dsl_diag.hide()
            self.mode = "text"
            self.stack.setCurrentIndex(1)
        else:
            if any(d.severity != "warning" for d in self.dsl.diagnostics()):
                if not C.confirm(self, "未適用のエラーがあります。GUIモードへ切り替えると、テキストの変更内容は破棄されます。よろしいですか？", "確認", "切り替える"):
                    return
            self.mode = "gui"
            self.stack.setCurrentIndex(0)
        self._update_buttons()

    def apply_dsl(self):
        res = DSL.compile_document(self.dsl.text(), self._effective_schemas(), self.roles, self.ops.class_schemas())
        diags = res["diagnostics"]
        if diags:
            self.dsl_diag.set_text("\n".join(f"{d.line + 1}行目: {d.message}" for d in diags))
            self.dsl_diag.setProperty("banner", "err" if any(d.severity == "error" for d in diags) else "warn")
            theme.repolish(self.dsl_diag)
            self.dsl_diag.show()
        else:
            self.dsl_diag.hide()
        if any(d.severity == "error" for d in diags):
            self.state.show_toast("エラーがあるため適用できません。赤波線の箇所を確認してください。", "error")
            return
        before = [{"uniqueId": r.get("uniqueId"), "name": r.get("name"), "data": self._current_data(r)} for r in self.roles]
        diff = D.diff_roles(before, res["roles"])
        if diff["totalChanges"] == 0:
            self.state.show_toast("変更はありません")
            self.mode = "gui"
            self.stack.setCurrentIndex(0)
            self._update_buttons()
            return
        if RolePreviewDialog(self, diff).exec():
            self.commit_dsl(res["roles"])

    def commit_dsl(self, compiled):
        ops = self.ops
        existing = {str(r.get("uniqueId")) for r in self.roles}
        compiled_ids = {str(r.get("uniqueId")) for r in compiled}
        has_new = any(str(r.get("uniqueId")) not in existing for r in compiled)
        for r in list(self.roles):
            if str(r.get("uniqueId")) not in compiled_ids:
                ops.delete_role(str(r.get("uniqueId")))
        for r in compiled:
            if str(r.get("uniqueId")) not in existing:
                ops.add_role({"uniqueId": r["uniqueId"], "id": r["uniqueId"], "name": r["name"], "branchType": "General", "data": []})
        items = [{"uniqueId": str(r["uniqueId"]), "formData": r["data"]} for r in compiled]

        def proceed(ok=True):
            if not ok:
                self.state.show_toast("構造の保存に失敗したため適用を中断しました", "error")
                return
            for r in compiled:
                self.form_state[str(r["uniqueId"])] = r["data"]
                ops.update_draft({str(r["uniqueId"]): r["data"]})
            # 既存フォームの値を差し替え、新規分はフォームを作り直す
            self.roles = list(ops.get_roles())
            for r in compiled:
                uid = str(r["uniqueId"])
                if uid in existing and uid in self.forms:
                    self.forms[uid].set_initial(r["data"])
            self._sync_cards()
            self._refresh_schemas()

            def saved():
                for it in items:
                    self.baseline[it["uniqueId"]] = self._j(it["formData"])
            ops.save_many(items, saved, lambda e: None)
            self.state.show_toast(f"テキストの内容を適用しました（{len(compiled)}件）", "success")
            self.mode = "gui"
            self.stack.setCurrentIndex(0)
            self._update_buttons()
        if has_new:
            ops.flush_structure(proceed)   # 新規Roleの値は、構造の保存がサーバーに反映されてから保存する
        else:
            proceed(True)
