"""シナリオイベント一覧 (ScenarioEventGrid.js)。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from ...core import event_ops as E
from ..async_ import run_async
from ..widgets import common as C
from .base import Page


class SubRow(QFrame):
    def __init__(self, page, event, sub):
        super().__init__()
        self.page, self.event, self.sub = page, event, sub
        self.setProperty("card", "flat")
        self._edit = False
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(28, 6, 10, 6)
        self.lay.setSpacing(10)
        self.build()

    def build(self):
        C.clear_layout(self.lay)
        ev, sub = self.event, self.sub
        bar = QFrame()
        bar.setFixedSize(3, 22)
        bar.setStyleSheet("background:#7aa2ff;border-radius:1px;")
        self.lay.addWidget(bar)
        self.lay.addWidget(C.Chip(f"#{sub['subId']}", "mono"))
        if self._edit:
            self.name = QLineEdit(sub.get("name", ""))
            self.desc = QLineEdit(sub.get("description") or "")
            self.desc.setPlaceholderText("説明")
            self.name.returnPressed.connect(self.commit)
            self.desc.returnPressed.connect(self.commit)
            self.lay.addWidget(self.name, 2)
            self.lay.addWidget(self.desc, 3)
            self.lay.addWidget(C.button("確定", "primary", on_click=self.commit, small=True))
            self.lay.addWidget(C.button("取消", "ghost", on_click=self.cancel, small=True))
            self.name.setFocus()
        else:
            nm = QLabel(sub.get("name", ""))
            nm.setStyleSheet("font-weight:600;")
            ds = QLabel(sub.get("description") or "—")
            ds.setProperty("role", "muted")
            self.lay.addWidget(nm, 2)
            self.lay.addWidget(ds, 3)
            self.lay.addWidget(C.button("遷移図", None, "graph", "遷移図を開く",
                                        lambda: self.page.state.go("transition", eventId=ev["id"], subId=sub["subId"]), small=True))
            self.lay.addWidget(C.button("物語設定", None, "book", "物語設定を開く",
                                        lambda: self.page.state.go("story_setting", eventId=ev["id"], subId=sub["subId"]), small=True))
            self.lay.addWidget(C.icon_button("edit", "編集", self.start_edit))
            self.lay.addWidget(C.icon_button("copy", "コピー", lambda: self.page.copy_sub_dialog(ev["id"], sub["subId"])))
            self.lay.addWidget(C.icon_button("trash", "削除", lambda: self.page.delete_sub(ev["id"], sub["subId"]), color="#ef6b73"))

    def start_edit(self):
        self._edit = True
        self.build()

    def cancel(self):
        self._edit = False
        self.build()

    def commit(self):
        name, desc = self.name.text(), self.desc.text()
        self._edit = False
        self.page.edit_sub(self.event["id"], self.sub["subId"], name, desc)


class EventCard(C.Card):
    def __init__(self, page, event, expanded=True):
        super().__init__()
        self.page, self.event = page, event
        self.expanded = expanded
        self._edit = False
        self.body.setSpacing(6)
        self.head = QHBoxLayout()
        self.head.setSpacing(10)
        self.body.addLayout(self.head)
        self.subs_box = QVBoxLayout()
        self.subs_box.setSpacing(4)
        self.subs_holder = QWidget()
        self.subs_holder.setLayout(self.subs_box)
        self.body.addWidget(self.subs_holder)
        self.build()

    def build(self):
        C.clear_layout(self.head)
        C.clear_layout(self.subs_box)
        ev = self.event
        self.head.addWidget(C.icon_button("down" if self.expanded else "right", "開閉", self.toggle))
        self.head.addWidget(C.Chip(str(ev["id"]), "accent"))
        if self._edit:
            self.name = QLineEdit(ev.get("name", ""))
            self.desc = QLineEdit(ev.get("description") or "")
            self.desc.setPlaceholderText("説明")
            self.name.returnPressed.connect(self.commit)
            self.desc.returnPressed.connect(self.commit)
            self.head.addWidget(self.name, 2)
            self.head.addWidget(self.desc, 3)
            self.head.addWidget(C.button("確定", "primary", on_click=self.commit, small=True))
            self.head.addWidget(C.button("取消", "ghost", on_click=self.cancel, small=True))
            self.name.setFocus()
        else:
            nm = QLabel(ev.get("name", ""))
            nm.setStyleSheet("font-weight:700;font-size:14px;")
            ds = QLabel(ev.get("description") or "—")
            ds.setProperty("role", "muted")
            self.head.addWidget(nm, 2)
            self.head.addWidget(ds, 3)
            self.head.addWidget(C.Chip(f"サブ {len(ev.get('subEvents') or [])}件"))
            self.head.addWidget(C.icon_button("edit", "編集", self.start_edit))
            self.head.addWidget(C.icon_button("plus", "サブイベント追加", lambda: self.page.add_sub_dialog(ev["id"]),
                                              color="#7aa2ff"))
            self.head.addWidget(C.icon_button("copy", "コピー", lambda: self.page.copy_event_dialog(ev["id"])))
            self.head.addWidget(C.icon_button("trash", "削除", lambda: self.page.delete_event(ev["id"]), color="#ef6b73"))
        for sub in ev.get("subEvents") or []:
            self.subs_box.addWidget(SubRow(self.page, ev, sub))
        self.subs_holder.setVisible(self.expanded and bool(ev.get("subEvents")))

    def toggle(self):
        self.expanded = not self.expanded
        self.page.expanded[self.event["id"]] = self.expanded
        self.build()

    def start_edit(self):
        self._edit = True
        self.build()

    def cancel(self):
        self._edit = False
        self.build()

    def commit(self):
        name, desc = self.name.text(), self.desc.text()
        self._edit = False
        self.page.edit_event(self.event["id"], name, desc)


class EventListPage(Page):
    PAGE_ID = "event_list"

    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self.events = []
        self.expanded = {}
        self.loading = True
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.count_chip = C.Chip("0 イベント", "accent")
        hdr, _ = self.make_header("シナリオイベント", "イベントとサブイベントの管理。遷移図・物語設定はサブイベントから開きます。", widgets=[self.count_chip])
        root.addWidget(hdr)

        tools = QFrame()
        tools.setProperty("toolbar", True)
        tl = QHBoxLayout(tools)
        tl.setContentsMargins(20, 8, 20, 8)
        tl.setSpacing(8)
        self.search = C.SearchEdit("IDまたは名前で検索...")
        self.search.setMinimumWidth(260)
        self.search.textChanged.connect(self.render)
        tl.addWidget(self.search)
        tl.addWidget(C.separator(True))
        tl.addWidget(C.button("イベント追加", "primary", "plus", "新しいイベントを追加（IDは自動採番）", self.add_event_dialog))
        tl.addWidget(C.button("Fix All", "warn", "build", "全Roleデータを修正", self.fix_all))
        tl.addWidget(C.button("旧形式を一括更新", None, "refresh",
                              "旧形式のまま残っているイベントデータを、新しい保存形式(イベント名フォルダ + Subごとの個別ファイル)へ一括更新します",
                              self.migrate_legacy))
        tl.addWidget(C.button("全bin生成", None, "download", "全バイナリを生成", self.generate_all_bin))
        tl.addStretch(1)
        tl.addWidget(C.icon_button("refresh", "再読み込み", self.reload))
        root.addWidget(tools)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        self.list_lay = QVBoxLayout(self.inner)
        self.list_lay.setContentsMargins(20, 16, 20, 20)
        self.list_lay.setSpacing(10)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(self.inner)
        root.addWidget(self.scroll, 1)

    def page_title(self):
        return "シナリオイベント"

    def load(self, params):
        super().load(params)
        self.reload()

    def on_activated(self):
        self.reload()

    # --- データ
    def reload(self):
        self.loading = True
        self.render()

        def work():
            return self.state.api.list_events()

        def ok(data):
            self.loading = False
            if isinstance(data, list):
                self.events = data
            self.state.lookups.invalidate("events")
            self.render()

        def err(e):
            self.loading = False
            self.render()
            self.fail("イベントの取得に失敗", e)
        run_async(work, ok, err, self)

    def render(self, *_):
        while self.list_lay.count() > 1:
            it = self.list_lay.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
                it.widget().deleteLater()
        self.count_chip.setText(f"{len(self.events)} イベント")
        if self.loading and not self.events:
            self.list_lay.insertWidget(0, self._empty("読み込み中..."))
            return
        shown = E.filter_events(self.events, self.search.text())
        if not shown:
            msg = "検索結果がありません" if self.search.text() else "イベントがありません。「イベント追加」から作成してください。"
            self.list_lay.insertWidget(0, self._empty(msg))
            return
        for i, ev in enumerate(shown):
            card = EventCard(self, ev, self.expanded.get(ev["id"], True))
            self.list_lay.insertWidget(i, card)

    def _empty(self, text):
        lb = QLabel(text)
        lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb.setProperty("role", "muted")
        lb.setMinimumHeight(140)
        return lb

    # --- 操作
    def add_event_dialog(self):
        nid = E.next_event_id(self.events)
        dlg = C.FormDialog(self, "新しいイベントを作成", [("name", "イベント名 *", "text", ""), ("description", "説明", "text", "")],
                           info=f"IDは自動で採番されます（現在: {nid}）", ok_text="作成")
        dlg.set_ok_enabled(False)
        dlg.widget("name").textChanged.connect(lambda t: dlg.set_ok_enabled(bool(t.strip())))
        if dlg.exec():
            v = dlg.values()
            name, desc = v["name"], v["description"]
            if not name.strip():
                self.toast("イベント名を入力してください", "error")
                return

            def ok(res):
                self.toast((res or {}).get("message") or "イベントを追加しました", "success")
                self.events = E.add_event(self.events, {"id": nid, "name": name, "description": desc})
                self.state.lookups.invalidate("events")
                self.render()
            run_async(lambda: self.state.api.create_event({"id": nid, "name": name, "description": desc}), ok,
                      lambda e: self.fail("イベント追加エラー", e), self)

    def edit_event(self, event_id, name, desc):
        def ok(_):
            self.events = E.edit_event(self.events, event_id, name, desc)
            self.state.lookups.invalidate("events")
            self.toast("更新しました", "success")
            self.render()
        run_async(lambda: self.state.api.update_event(event_id, {"name": name, "description": desc}), ok,
                  lambda e: (self.fail("更新エラー", e), self.render()), self)

    def delete_event(self, event_id):
        if not C.confirm(self, f"イベント「{event_id}」を削除しますか？", "削除の確認", "削除", danger=True):
            return

        def ok(res):
            self.toast((res or {}).get("message") or "削除しました", "success")
            self.events = E.delete_event(self.events, event_id)
            self.state.lookups.invalidate("events")
            self.render()
        run_async(lambda: self.state.api.delete_event(event_id), ok, lambda e: self.fail("削除エラー", e), self)

    def add_sub_dialog(self, event_id):
        dlg = C.FormDialog(self, "サブイベントを追加", [("name", "サブイベント名 *", "text", ""), ("description", "説明", "text", "")],
                           info="サブイベントIDは自動で採番されます。", ok_text="追加")
        dlg.set_ok_enabled(False)
        dlg.widget("name").textChanged.connect(lambda t: dlg.set_ok_enabled(bool(t.strip())))
        if dlg.exec():
            v = dlg.values()
            if not v["name"].strip():
                self.toast("サブイベント名を入力してください", "error")
                return

            def ok(res):
                self.toast((res or {}).get("message") or "サブイベントを追加しました", "success")
                self.events = E.add_sub(self.events, event_id, {"subId": (res or {}).get("subId"), "name": v["name"],
                                                                "description": v["description"]})
                self.state.lookups.invalidate("events")
                self.render()
            run_async(lambda: self.state.api.create_sub(event_id, {"name": v["name"], "description": v["description"]}), ok,
                      lambda e: self.fail("サブイベント追加エラー", e), self)

    def edit_sub(self, event_id, sub_id, name, desc):
        def ok(_):
            self.events = E.edit_sub(self.events, event_id, sub_id, name, desc)
            self.state.lookups.invalidate("events")
            self.toast("更新しました", "success")
            self.render()
        run_async(lambda: self.state.api.update_sub(event_id, sub_id, {"name": name, "description": desc}), ok,
                  lambda e: (self.fail("更新エラー", e), self.render()), self)

    def delete_sub(self, event_id, sub_id):
        if not C.confirm(self, f"サブイベント #{sub_id} を削除しますか？", "削除の確認", "削除", danger=True):
            return

        def ok(res):
            self.toast((res or {}).get("message") or "削除しました", "success")
            self.events = E.delete_sub(self.events, event_id, sub_id)
            self.state.lookups.invalidate("events")
            self.render()
        run_async(lambda: self.state.api.delete_sub(event_id, sub_id), ok, lambda e: self.fail("削除エラー", e), self)

    def copy_event_dialog(self, event_id):
        dlg = C.FormDialog(self, "イベントをコピー", [("copySubs", "サブイベントもコピーする", "bool", True)],
                           info="新しいIDで複製します。名前には「のコピー」が付きます。", ok_text="コピー")
        if dlg.exec():
            copy_subs = dlg.values()["copySubs"]

            def ok(res):
                self.toast((res or {}).get("message") or "コピーしました", "success")
                self.reload()
            run_async(lambda: self.state.api.copy_event(event_id, {"copySubs": copy_subs}), ok,
                      lambda e: self.fail("コピーエラー", e), self)

    def copy_sub_dialog(self, event_id, sub_id):
        opts = [(e["id"], e.get("name", "") + ("（元の親）" if e["id"] == event_id else "")) for e in self.events]
        dlg = C.FormDialog(self, "サブイベントをコピー", [("target", "コピー先の親イベント", "choice", (event_id, opts))],
                           info="元と同じ親イベントを選ぶと、その親の中に複製されます", ok_text="コピー")
        if dlg.exec():
            target = dlg.values()["target"] or event_id

            def ok(res):
                self.toast((res or {}).get("message") or "コピーしました", "success")
                self.reload()
            run_async(lambda: self.state.api.copy_sub(event_id, sub_id, {"targetEventId": target}), ok,
                      lambda e: self.fail("コピーエラー", e), self)

    def fix_all(self):
        if not C.confirm(self, "全てのイベントの Role データを修正しますか？", "Fix All", "修正する"):
            return

        def ok(res):
            self.toast((res or {}).get("message") or "修正完了", "success")
            self.reload()
        run_async(lambda: self.state.api.fix_all_events(), ok, lambda e: self.fail("修正エラー", e), self)

    def generate_all_bin(self):
        if not C.confirm(self, "全てのイベントバイナリを生成しますか？", "全bin生成", "生成する"):
            return
        run_async(lambda: self.state.api.generate_all_event_bin(),
                  lambda res: self.toast((res or {}).get("message") or "生成完了", "success"),
                  lambda e: self.fail("生成エラー", e), self)

    def migrate_legacy(self):
        if not C.confirm(self, "旧形式のまま残っているイベントデータを、新しい保存形式へ一括更新しますか？", "旧形式を一括更新", "更新する"):
            return

        def ok(res):
            msg, level = E.migrate_message(res)
            self.toast(msg, level)
        run_async(lambda: self.state.api.migrate_legacy_events(), ok, lambda e: self.fail("更新エラー", e), self)
