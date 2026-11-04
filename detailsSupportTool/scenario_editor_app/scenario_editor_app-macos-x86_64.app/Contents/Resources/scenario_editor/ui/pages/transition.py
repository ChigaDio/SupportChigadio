"""遷移エディタ (ScenarioEventTransition.js)。イベント/Sub の遷移グラフ(ノード+接続)と、各ノードの Role を編集する。

構成:  タブ(Group遷移 / サブグループ) → ツールバー → BlockCanvas(カード一覧)
保存:  変更→600ms 後に自動保存 (SaveCoordinator で排他/取りこぼし防止)、Undo/Redo は core.History。
別タブ/別ユーザーの更新は 30 秒ごと+ウィンドウ復帰時に rev を見て警告する。
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QProgressBar, QTabBar, QVBoxLayout, QWidget

from ...core import presets as P
from ...core import subgroup_setting as SGS
from ...core import transition_ops as T
from ...core.dsl import js_string
from ..async_ import run_async
from ..dialogs.edit_dialog import DslEditDialog
from ..dialogs.role_drawers import RoleDataDrawer, RoleSelectDrawer, SubGroupSettingDrawer
from ..widgets import common as C
from ..widgets.block_canvas import BlockCanvas
from .base import Page

AUTOSAVE_MS = 600
REV_POLL_MS = 30000


class TransitionPage(Page):
    PAGE_ID = "transition"

    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self.event_id = self.sub_id = None
        self._reset_state()
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(AUTOSAVE_MS)
        self.autosave.timeout.connect(lambda: self.perform_save(self.active))
        self.rev_timer = QTimer(self)
        self.rev_timer.setInterval(REV_POLL_MS)
        self.rev_timer.timeout.connect(self.check_rev)
        QGuiApplication.instance().applicationStateChanged.connect(self._app_state_changed)
        self.h = SimpleNamespace(
            toggle_select=lambda i: self.canvas.toggle_select(i), edit_id=self.edit_node_dialog, open_setting=self.open_setting,
            reorder=self.reorder, reorder_by_id=self.reorder_by_id, remove_edge=self.remove_edge, delete_role=self.delete_role,
            open_subgroup=lambda nid: self.switch_tab(f"subgroup-{nid}", nid), open_role_select=self.open_role_select,
            open_role_data=self.open_role_data, connect=self.connect_nodes, move_to_group=self.move_to_group,
            copy=self.copy_node, open_index_tools=lambda nid: self.canvas.open_index_tools(nid),
            clipboard_count=lambda: len(self.state.clipboard.get()), paste_roles=self.paste_roles, set_colors=self.set_colors,
            delete=lambda nid: self.delete_nodes([nid]), delete_many=self.delete_nodes, save_setting=self.save_setting,
            renumber_duplicates=self.renumber_duplicates, apply_index_changes=self.apply_index_changes)
        self._build()
        for keys, d in ((("Ctrl+Z", "Meta+Z"), "undo"), (("Ctrl+Y", "Ctrl+Shift+Z", "Meta+Shift+Z"), "redo")):
            for k in keys:
                QShortcut(QKeySequence(k), self, activated=lambda d=d: self._key_history(d),
                          context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # ------------------------------------------------------------------ 状態
    def _reset_state(self):
        self.tabs = [{"id": "main", "label": "Group遷移", "type": "group"}]
        self.active = "main"
        self.tab_data = {"main": T.empty_tab()}
        self.history = T.History()
        self.save = T.SaveCoordinator()
        self.rev = T.RevTracker()
        self.drafts = T.RoleDataDrafts()
        self.copied = None
        self.global_roles, self.role_schemas, self.class_schemas = [], {}, {}
        self.setting_schema, self.setting_defaults = None, []
        self.node_colors = {}
        self.last_saved = None
        self.loading = False
        self._waiters = []
        self._gen = 0

    def cur(self):
        return self.tab_data.get(self.active) or T.empty_tab()

    @property
    def is_sub(self):
        return self.active.startswith("subgroup-")

    @property
    def parent_id(self):
        return T.parent_of_tab(self.active)

    def page_title(self):
        return f"遷移 {self.event_id}/{self.sub_id}" if self.event_id is not None else "遷移エディタ"

    def _default_setting_line(self):
        if not self.setting_schema:
            return ""
        return SGS.build_default_setting_line(self.setting_schema, self.setting_defaults, self.class_schemas)

    # ------------------------------------------------------------------ UI 構築
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        hdr, self.title_lb = self.make_header("遷移エディタ", None, back=lambda: self.state.go("event_list"))
        root.addWidget(hdr)

        self.tabbar = QTabBar()
        self.tabbar.setTabsClosable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setDrawBase(False)
        self.tabbar.currentChanged.connect(self._tab_changed)
        self.tabbar.tabCloseRequested.connect(self._tab_close_requested)
        tw = QFrame()
        tl = QHBoxLayout(tw)
        tl.setContentsMargins(16, 4, 16, 0)
        tl.addWidget(self.tabbar, 1)
        root.addWidget(tw)

        tb = QFrame()
        tb.setProperty("toolbar", True)
        bl = QHBoxLayout(tb)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(6)
        self.btn_add = C.button("ノード追加", "primary", "plus", on_click=self.add_node_dialog, small=True)
        self.btn_paste = C.button("ペースト", icon_name="paste", on_click=self.paste_node, small=True)
        self.chip_copied = C.Chip("", "true", clickable=True, tooltip="クリックでコピーを解除")
        self.chip_copied.clicked.connect(self.clear_copied)
        self.btn_schema = C.button("Roleスキーマ再取得", icon_name="refresh", on_click=self.reload_schemas, small=True,
                                   tooltip="Role定義(型・オプション)を変更した場合、ここを押すと最新のスキーマを取り直します")
        self.btn_all = C.button("全体編集(全Sub一括)", icon_name="edit", on_click=self.open_all_edit, small=True,
                                tooltip="このイベントに属する全Sub・全ノードのTransactionを1つのテキストでまとめて編集します")
        self.btn_sub = C.button("このSubのみ編集", icon_name="edit", on_click=self.open_sub_edit, small=True,
                                tooltip="現在開いているSubだけを、テキストで編集します")
        for w in (self.btn_add, self.btn_paste, self.chip_copied, self.btn_schema, self.btn_all, self.btn_sub):
            bl.addWidget(w)
        bl.addStretch(1)
        self.summary = C.label("", "muted")
        bl.addWidget(self.summary)
        bl.addWidget(C.button("CSV出力", icon_name="download", on_click=self.export_csv, small=True,
                              tooltip="現在のタブのノード・接続をCSVとして保存します"))
        self.btn_csv_in = C.button("CSV入力", icon_name="upload", on_click=self.import_csv, small=True,
                                   tooltip="CSVを読み込んで現在のタブへ反映します（内容は上書きされます）")
        bl.addWidget(self.btn_csv_in)
        self.btn_undo = C.icon_button("undo", "元に戻す (Ctrl+Z)", lambda: self.apply_history("undo"))
        self.btn_redo = C.icon_button("redo", "やり直す (Ctrl+Shift+Z / Ctrl+Y)", lambda: self.apply_history("redo"))
        bl.addWidget(self.btn_undo)
        bl.addWidget(self.btn_redo)
        self.status_chip = C.Chip("保存済み", "true", clickable=True)
        self.status_chip.clicked.connect(self._status_clicked)
        bl.addWidget(self.status_chip)
        self.btn_save = C.button("保存", "ok", "save", on_click=self.save_current_tab, small=True)
        bl.addWidget(self.btn_save)
        root.addWidget(tb)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        root.addWidget(self.progress)

        self.rev_banner = C.Banner("別のタブまたは別のユーザーが、このSubを更新した可能性があります。このまま保存すると、相手の変更を上書きすることがあります。", "warn")
        rb = self.rev_banner.layout()
        rb.addWidget(C.button("再読み込み", small=True, on_click=self.reload_from_banner))
        rb.addWidget(C.button("無視（自分の内容で上書き）", small=True, on_click=self.ignore_external))
        self.rev_wrap = QWidget()
        rw = QVBoxLayout(self.rev_wrap)
        rw.setContentsMargins(16, 8, 16, 0)
        rw.addWidget(self.rev_banner)
        self.rev_wrap.hide()
        root.addWidget(self.rev_wrap)

        self.conn_wrap = QFrame()
        cl = QVBoxLayout(self.conn_wrap)
        cl.setContentsMargins(16, 6, 16, 0)
        cl.setSpacing(2)
        cl.addWidget(C.label("接続一覧", "muted"))
        self.conn_host = QWidget()
        self.conn_lay = C.FlowLayout(self.conn_host, spacing=4)
        self.conn_lay.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.conn_host)
        self.conn_wrap.hide()
        root.addWidget(self.conn_wrap)

        self.canvas = BlockCanvas(self.state, self.h)
        root.addWidget(self.canvas, 1)

        self.role_select = RoleSelectDrawer(self)
        self.setting_drawer = SubGroupSettingDrawer(self, self.state)
        self.data_drawer = RoleDataDrawer(self, self.state)
        self._edges_sig = None

    # ------------------------------------------------------------------ ページ契約
    def load(self, params):
        super().load(params)
        eid, sid = params.get("eventId"), params.get("subId")
        self.autosave.stop()
        self._gen += 1
        self._reset_state()
        self.event_id, self.sub_id = eid, sid
        self.title_lb.setText(f"遷移エディタ — {eid} / Sub {sid}")
        self.node_colors = self.state.node_colors.get(eid, sid)
        self._rebuild_tabs()
        self.rev_wrap.hide()
        self.canvas.selected = set()
        self.canvas._tab_key = None
        self.refresh_view()
        if eid is None or sid is None:
            return
        self.state.add_recent("transition", {"eventId": eid, "subId": sid}, f"遷移 {eid}/{sid}")
        self._set_loading(True)
        gen = self._gen
        api = self.state.api

        def ok(res):
            if gen != self._gen:
                return
            result, rev = res
            self.tab_data = {"main": T.normalize_loaded_tab(result)}
            self.rev.note(rev)
            self.save.mark_loaded("main")
            self._set_loading(False)
            self.refresh_view()

        def err(e):
            if gen != self._gen:
                return
            self._set_loading(False)
            self.fail("データの読み込みに失敗しました。保存はできません", e)
        run_async(lambda: api.get_transition(eid, sid), ok, err, self)
        self.reload_schemas(silent=True)
        self.rev_timer.start()

    def can_leave(self):
        if self.event_id is not None and self.save.should_confirm_leave():
            return C.confirm(self, "未保存の変更、または保存に失敗した変更があります。このまま移動すると失われることがあります。移動しますか？",
                             "確認", "移動する", danger=True)
        return True

    def shutdown(self):
        self.autosave.stop()
        self.rev_timer.stop()

    def on_activated(self):
        self.check_rev()

    def _set_loading(self, v):
        self.loading = v
        self.progress.setVisible(v)
        for w in (self.btn_add, self.btn_paste, self.btn_schema, self.btn_all, self.btn_sub, self.btn_csv_in, self.btn_save):
            w.setEnabled(not v)

    # ------------------------------------------------------------------ 描画更新
    def refresh_view(self):
        cur = self.cur()
        ctx = SimpleNamespace(role_names=({r["name"] for r in self.global_roles} if self.global_roles else None),
                              role_schemas=self.role_schemas, class_schemas=self.class_schemas,
                              setting_schema=self.setting_schema, setting_defaults=self.setting_defaults,
                              node_colors=self.node_colors)
        self.canvas.set_data(cur["nodes"], cur["edges"], self.is_sub, self.parent_id, ctx)
        self.summary.setText(f"{len(cur['nodes'])} ノード / {len(cur['edges'])} 接続")
        self._refresh_connections(cur)
        self.btn_paste.setEnabled(bool(self.copied) and not self.loading)
        self.btn_paste.setToolTip(f"ペースト: ノード {self.copied['id']}" if self.copied else "コピーなし")
        self.chip_copied.setVisible(bool(self.copied))
        if self.copied:
            self.chip_copied.setText(f"コピー中: {self.copied['id']}  ✕")
        self._refresh_status()
        self._refresh_history_buttons()

    def _refresh_connections(self, cur):
        edges = cur["edges"]
        if self._edges_sig is edges:
            return
        self._edges_sig = edges
        C.clear_layout(self.conn_lay)
        self.conn_wrap.setVisible(bool(edges))
        for e in edges:
            chip = C.Chip(f"{e.get('source')} → {e.get('target')}  ✕", "info", clickable=True, tooltip="クリックで接続を削除")
            chip.clicked.connect(lambda e=e: self.remove_edge(e))
            self.conn_lay.addWidget(chip)

    def _refresh_status(self):
        st = self.save.status
        if st == "saving":
            self.status_chip.setText("保存中…")
            self.status_chip.set_kind("info")
        elif st == "dirty":
            self.status_chip.setText("未保存の変更")
            self.status_chip.set_kind("warn")
            self.status_chip.setToolTip("自動保存待ち（クリックで今すぐ保存）")
        elif st == "error":
            self.status_chip.setText("保存失敗（再試行）")
            self.status_chip.set_kind("err")
            self.status_chip.setToolTip("クリックで再保存")
        else:
            at = time.strftime("%H:%M:%S", time.localtime(self.last_saved)) if self.last_saved else ""
            self.status_chip.setText(f"保存済み {at}".strip())
            self.status_chip.set_kind("true")
            self.status_chip.setToolTip("")

    def _status_clicked(self):
        if self.save.status in ("dirty", "error"):
            self.save_current_tab()

    def _refresh_history_buttons(self):
        u, r = self.history.counts(self.active)
        self.btn_undo.setEnabled(u > 0)
        self.btn_redo.setEnabled(r > 0)

    def _rebuild_tabs(self):
        self.tabbar.blockSignals(True)
        while self.tabbar.count():
            self.tabbar.removeTab(0)
        for t in self.tabs:
            i = self.tabbar.addTab(t["label"])
            self.tabbar.setTabData(i, t["id"])
            if t["id"] == "main":
                self.tabbar.setTabButton(i, QTabBar.ButtonPosition.RightSide, None)
        ids = [t["id"] for t in self.tabs]
        self.tabbar.setCurrentIndex(ids.index(self.active) if self.active in ids else 0)
        self.tabbar.blockSignals(False)

    # ------------------------------------------------------------------ 状態更新の共通口
    def push_history(self):
        snap = self.tab_data.get(self.active)
        if snap is not None:
            self.history.push(self.active, snap)

    def update_tab_data(self, new_tab_data):
        """JS の updateTabData: 履歴に積んでから差し替える。"""
        self.push_history()
        self.tab_data = new_tab_data

    def schedule_save(self):
        self.save.mark_dirty()
        self.autosave.start()
        self.refresh_view()

    # ------------------------------------------------------------------ 保存
    def perform_save(self, tab_id):
        if not tab_id or self.event_id is None or self.sub_id is None or tab_id not in self.save.loaded:
            return
        if tab_id not in self.tab_data:
            return
        if not self.save.begin(tab_id):
            return
        self._refresh_status()
        data = T.build_save_data(self.tab_data, tab_id)
        pid = T.parent_of_tab(tab_id)
        api, e, s = self.state.api, self.event_id, self.sub_id
        gen = self._gen

        def work():
            if pid:
                return api.save_subgroup(e, s, pid, data["nodes"], data["edges"])
            return api.save_transition(e, s, data["nodes"], data["edges"])

        def ok(res):
            if gen != self._gen:
                return
            if isinstance(res, dict):
                self.rev.note(res.get("rev"))
            if pid:
                self.tab_data = T.sync_main_subgroup(self.tab_data, pid)
            self.last_saved = time.time()
            self._after_save(True)

        def err(ex):
            if gen != self._gen:
                return
            self.toast("保存に失敗しました。再度お試しください", "error")
            self._after_save(False)
        run_async(work, ok, err, self)

    def _after_save(self, ok):
        nxt = self.save.finish(ok)
        self._refresh_status()
        if nxt:
            self.perform_save(nxt)
            if self.save.saving:
                return
        waiters, self._waiters = self._waiters, []
        for w in waiters:
            w(ok)
        self.refresh_view()

    def save_now(self, on_done=None, tab=None):
        """保留中の自動保存を確定させて保存。on_done(ok) は保存の列が終わったとき。"""
        self.autosave.stop()
        if on_done:
            self._waiters.append(on_done)
        tab_id = tab or self.active
        before = self.save.saving
        self.perform_save(tab_id)
        if not self.save.saving and not before:   # 開始できなかった(未読み込みなど)
            waiters, self._waiters = self._waiters, []
            for w in waiters:
                w(False)

    def save_current_tab(self):
        self.save_now()

    # ------------------------------------------------------------------ タブ
    def _tab_changed(self, i):
        tid = self.tabbar.tabData(i)
        if tid and tid != self.active:
            self.switch_tab(tid)

    def _tab_close_requested(self, i):
        tid = self.tabbar.tabData(i)
        if not tid or tid == "main":
            return
        self.tabs = [t for t in self.tabs if t["id"] != tid]
        self.tab_data.pop(tid, None)
        self.history.clear(tid)
        self.save.mark_unloaded(tid)
        if self.active == tid:
            self.active = "main"
        self._rebuild_tabs()
        self.refresh_view()

    def switch_tab(self, tab_id, pid=None):
        if tab_id == self.active:
            return
        if self.event_id is None or self.sub_id is None:
            self.toast("Event/Sub IDが未定義", "error")
            return
        if self.autosave.isActive():          # 切り替える前に「今のタブ」の保存を確定させる
            self.autosave.stop()
            self.perform_save(self.active)
        if tab_id.startswith("subgroup-"):
            pid = pid or tab_id[len("subgroup-"):]
            if any(t["id"] == tab_id for t in self.tabs) and tab_id in self.tab_data:
                self.active = tab_id
                self._rebuild_tabs()
                self.refresh_view()
                return
            self._set_loading(True)
            if not any(t["id"] == tab_id for t in self.tabs):
                self.tabs.append({"id": tab_id, "label": f"Sub: {pid}", "type": "subgroup", "parentId": pid})
            api, e, s, gen = self.state.api, self.event_id, self.sub_id, self._gen

            def ok(res):
                if gen != self._gen:
                    return
                self.tab_data = {**self.tab_data, tab_id: T.normalize_loaded_tab(res)}
                self.save.mark_loaded(tab_id)
                self.active = tab_id
                self._set_loading(False)
                self._rebuild_tabs()
                self.refresh_view()

            def err(ex):
                if gen != self._gen:
                    return
                self._set_loading(False)
                self.tabs = [t for t in self.tabs if t["id"] != tab_id or tab_id in self.tab_data]
                self._rebuild_tabs()
                self.fail("SubGroupロードエラー", ex)
            run_async(lambda: api.get_subgroup(e, s, pid), ok, err, self)
        else:
            self.active = tab_id
            self._rebuild_tabs()
            self.refresh_view()

    # ------------------------------------------------------------------ ノード操作
    def add_node_dialog(self):
        if self.event_id is None:
            return self.toast("Event/Sub IDが未定義", "error")
        nxt = T.get_next_node_id(self.cur()["nodes"])
        dlg = C.FormDialog(self, "ノード追加", [("description", "説明（任意）", "multiline", "")],
                           info=f"次のID: {nxt}（自動採番）　改行して複数行入力できます", ok_text="追加")
        if dlg.exec():
            td, new_id = T.add_node(self.tab_data, self.active, self.is_sub, self.parent_id, dlg.values()["description"],
                                    self.setting_schema, self.setting_defaults)
            self.update_tab_data(td)
            self.schedule_save()
            self.toast(f"ノード {new_id} を追加")
            self.canvas.reveal(new_id)

    def delete_nodes(self, ids):
        td = self.tab_data
        for nid in ids:
            td = T.delete_node(td, self.active, nid)
        self.update_tab_data(td)
        self.schedule_save()
        self.toast(f"ノード {', '.join(map(str, ids))} を削除" if len(ids) <= 3 else f"{len(ids)} 件のノードを削除")

    def copy_node(self, node_id):
        node = next((n for n in self.cur()["nodes"] if n["id"] == node_id), None)
        if node:
            self.copied = node
            self.toast(f"ノード {node_id} をコピー")
            self.refresh_view()

    def clear_copied(self):
        self.copied = None
        self.refresh_view()

    def paste_node(self):
        if not self.copied:
            return self.toast("コピーなし", "warning")
        td, new_id = T.paste_node(self.tab_data, self.active, self.copied, self.is_sub, self.parent_id)
        self.update_tab_data(td)
        self.schedule_save()
        self.toast(f"ノード {new_id} としてペースト")
        self.canvas.reveal(new_id)

    def edit_node_dialog(self, node_id):
        node = next((n for n in self.cur()["nodes"] if n["id"] == node_id), None)
        if not node:
            return
        d = node.get("data") or {}
        dlg = C.FormDialog(self, "ノード編集", [("id", "ノードID", "text", node_id), ("description", "説明", "multiline", d.get("description") or "")],
                           info="IDを変更すると接続(エッジ)のIDも自動更新されます。改行して複数行入力できます。", ok_text="保存")
        if dlg.exec():
            v = dlg.values()
            td, err = T.edit_node(self.tab_data, self.active, node_id, v["id"], v["description"], self.is_sub, self.parent_id)
            if err:
                return self.toast(err, "error")
            self.update_tab_data(td)
            self.schedule_save()
            self.toast("更新しました")

    def reorder(self, frm, to):
        td = T.reorder_nodes(self.tab_data, self.active, frm, to)
        if td is not None:
            self.update_tab_data(td)
            self.schedule_save()

    def reorder_by_id(self, dragged, target):
        td = T.reorder_by_id(self.tab_data, self.active, dragged, target)
        if td is not None:
            self.update_tab_data(td)
            self.schedule_save()

    def save_setting(self, node_id, setting):
        self.update_tab_data(T.set_node_subgroup_setting(self.tab_data, self.active, node_id, setting))
        self.schedule_save()

    def connect_nodes(self, node_id, target_raw):
        cur = self.cur()
        target, err, level = T.validate_connect(node_id, target_raw, [n["id"] for n in cur["nodes"]], cur["edges"])
        if err:
            return self.toast(err, level)
        td, err2 = T.add_edge(self.tab_data, self.active, T.make_edge(node_id, target))
        if err2:
            return self.toast(err2, "warning")
        self.update_tab_data(td)
        self.schedule_save()
        self.toast(f"→{target} 接続")

    def remove_edge(self, edge):
        self.update_tab_data(T.remove_edge(self.tab_data, self.active, edge))
        self.schedule_save()
        self.toast(f"接続 {edge['source']}→{edge['target']} を削除")

    def move_to_group(self, node_id, target_gid):
        """別グループ(サブグループタブ)へ移動。移動先が未読み込みなら先に読み込み、両方のタブを保存する。"""
        target_tab = f"subgroup-{target_gid}"
        if target_tab == self.active:
            return self.toast("移動先が今のグループと同じです", "warning")
        if not any(n["id"] == js_string(target_gid) for n in (self.tab_data.get("main") or T.empty_tab())["nodes"]):
            return self.toast(f"移動先のグループ {target_gid} が見つかりません", "error")

        def do_move():
            td, new_id = T.move_to_group(self.tab_data, self.active, node_id, target_gid)
            if new_id is None:
                return
            src = self.active
            self.update_tab_data(td)
            self.save.mark_dirty()
            self.toast(f"ノード {node_id} → グループ {target_gid} に移動 (新ID: {new_id})")
            self.autosave.stop()
            self.refresh_view()
            # JS では移動先タブが保存されず内容が失われうるため、両方を順に保存する
            self.save_now(lambda ok: self.save_now(tab=target_tab) if ok else None, tab=src)

        if target_tab in self.tab_data:
            return do_move()
        api, e, s, gen = self.state.api, self.event_id, self.sub_id, self._gen

        def ok(res):
            if gen != self._gen:
                return
            self.tab_data = {**self.tab_data, target_tab: T.normalize_loaded_tab(res)}
            self.save.mark_loaded(target_tab)
            do_move()
        run_async(lambda: api.get_subgroup(e, s, target_gid), ok, lambda ex: self.fail("移動先の読み込みに失敗しました", ex), self)

    def set_colors(self, paths, color_key):
        self.node_colors = self.state.node_colors.set_paths(self.event_id, self.sub_id, paths, color_key)
        for c in self.canvas.cards.values():
            c._sig = None
        self.refresh_view()

    def apply_index_changes(self, changes):
        if not changes:
            return
        self.update_tab_data(T.apply_index_changes_to_tab(self.tab_data, self.active, changes))
        self.drafts.reset()
        self.schedule_save()
        self.toast(f"{len(changes)}件のインデックスを更新しました（Ctrl+Zで元に戻せます）")

    def renumber_duplicates(self):
        r = T.renumber_duplicates_in_tab(self.tab_data, self.active, [t["id"] for t in self.tabs])
        if r["blocked"]:
            return self.toast("グループのIDを振り直す前に、開いているサブグループのタブをすべて閉じてください", "warning")
        if not r["renamed"]:
            msg = f"数値でないIDの重複は自動では振り直せません: {', '.join(map(str, r['skipped']))}" if r["skipped"] else "重複しているIDは見つかりませんでした"
            return self.toast(msg)
        self.update_tab_data(r["tabData"])
        self.drafts.reset()
        self.schedule_save()
        self.toast("ID重複を解消しました: " + ", ".join(f"{x['from']} → {x['to']}" for x in r["renamed"]) + "（Ctrl+Zで元に戻せます）")

    # ------------------------------------------------------------------ Role 操作
    def _find_node(self, node_id, tab=None):
        return next((n for n in (self.tab_data.get(tab or self.active) or T.empty_tab())["nodes"] if n["id"] == node_id), None)

    def add_role_local(self, node_id, role):
        self.update_tab_data(T.add_role_to_tab(self.tab_data, self.active, node_id, role))
        self.schedule_save()

    def delete_role(self, node_id, uid):
        self.update_tab_data(T.delete_role_from_tab(self.tab_data, self.active, node_id, uid))
        self.schedule_save()

    def add_role_with_server(self, node_id, role, unique_id=None, data=None, on_ok=None, on_err=None):
        """サーバーへ Role を追加(デフォルト値で初期化された data が返る) → 画面へ反映。data 指定時はその値で保存まで行う。"""
        node_path = self.canvas.node_path(node_id)
        uid = unique_id or str(int(time.time() * 1000))
        api, e, s, gen = self.state.api, self.event_id, self.sub_id, self._gen

        def ok(res):
            if gen != self._gen:
                return
            res = res if isinstance(res, dict) else {}
            self.rev.note(res.get("rev"))
            final = data if data is not None else (res.get("data") or [])
            self.add_role_local(node_id, {"uniqueId": uid, "id": role.get("id"), "name": role.get("name"),
                                          "branchType": role.get("branchType"), "data": final})
            if data is not None:
                self.save_roles(node_path, node_id, [{"uniqueId": uid, "formData": data}])
            if on_ok:
                on_ok(uid)

        def err(ex):
            if on_err:
                on_err(ex)
        run_async(lambda: api.add_role_to_node(e, s, node_path, role.get("id"), role.get("name"),
                                               role.get("branchType") or "General", uid), ok, err, self)

    def paste_roles(self, node_id, then=None):
        clip = self.state.clipboard.get()
        if not clip:
            return self.toast("貼り付けるRoleがありません", "warning")
        node = self._find_node(node_id)
        existing = [r.get("uniqueId") for r in ((node or {}).get("data") or {}).get("roles") or []]
        ids = P.make_unique_ids(len(clip), existing)

        def step(i):
            if i >= len(clip):
                self.toast(f"{len(clip)}件のRoleを貼り付けました", "success")
                if then:
                    then()
                elif self.data_drawer.is_open():
                    self.data_drawer.refresh_roles()
                return
            c = clip[i]
            self.add_role_with_server(node_id, {"id": c.get("id"), "name": c.get("name"), "branchType": c.get("branchType")},
                                      unique_id=ids[i], data=c.get("data"), on_ok=lambda _u: step(i + 1),
                                      on_err=lambda ex: self.fail("貼り付けエラー", ex))   # 順番を保つため1件ずつ
        step(0)

    def save_roles(self, node_path, node_id, items, on_ok=None, on_err=None):
        """複数 Role の値を role-data-batch で1リクエストにまとめて保存する。"""
        if self.event_id is None or self.sub_id is None:
            return self.toast("Event/Sub IDが未定義", "error")
        if not items:
            if on_ok:
                on_ok()
            return
        tab = self.active
        node = self._find_node(node_id, tab) or {}
        typed = T.typed_role_items(items, node, self.role_schemas)
        self.save.status = "saving"
        self._refresh_status()
        api, e, s, gen = self.state.api, self.event_id, self.sub_id, self._gen
        updates = [{"nodePath": node_path, "uniqueId": it["uniqueId"], "formData": it["formData"]} for it in typed]

        def ok(res):
            if gen != self._gen:
                return
            res = res if isinstance(res, dict) else {}
            self.rev.note(res.get("rev"))
            by_uid = {js_string(it["uniqueId"]): it["formData"] for it in typed}
            self.drafts.after_save(node_path, by_uid, items)
            self.update_tab_data(T.apply_saved_role_data(self.tab_data, tab, node_id, by_uid))
            if tab.startswith("subgroup-"):
                self.tab_data = T.sync_main_subgroup(self.tab_data, T.parent_of_tab(tab))
            if res.get("missed"):
                self.schedule_save()     # サーバーのファイルにまだ無いRoleは、通常のツリー保存で書き込む
            else:
                self.save.status = "dirty" if self.save.dirty else "saved"
                self.last_saved = time.time()
                self.refresh_view()
            if on_ok:
                on_ok()

        def err(ex):
            if gen != self._gen:
                return
            self.toast(f"保存エラー: {ex}", "error")
            self.save.status = "error"
            self._refresh_status()
            if on_err:
                on_err(ex)
        run_async(lambda: api.save_role_data_batch(e, s, updates), ok, err, self)

    # ------------------------------------------------------------------ ドロワー
    def open_role_select(self, node_id):
        self.role_select.open_for(node_id, self.global_roles, lambda role: self._pick_role(node_id, role))
        self.reload_schemas(silent=True, then=lambda: self.role_select.isVisible() and self.role_select.set_roles(self.global_roles))

    def _pick_role(self, node_id, role):
        self.add_role_with_server(node_id, role, on_ok=lambda _u: self.toast(f"{role.get('name')} を追加"),
                                  on_err=lambda ex: self.fail("追加エラー", ex))

    def open_role_data(self, node_id):
        node = self._find_node(node_id)
        if node is None:
            return
        node_path = self.canvas.node_path(node_id)
        tint = getattr(self.canvas.cards.get(node_id), "tint", None)
        roles = (node.get("data") or {}).get("roles") or []
        ops = SimpleNamespace(
            event_id=self.event_id, sub_id=self.sub_id,
            get_roles=lambda: ((self._find_node(node_id) or {}).get("data") or {}).get("roles") or [],
            role_schemas=lambda: self.role_schemas, class_schemas=lambda: self.class_schemas,
            initial_state=lambda: self.drafts.initial_for_drawer(
                ((self._find_node(node_id) or {}).get("data") or {}).get("roles") or [], node_path),
            save_many=lambda items, ok, err: self.save_roles(node_path, node_id, items, ok, err),
            delete_role=lambda uid: self.delete_role(node_id, uid), add_role=lambda r: self.add_role_local(node_id, r),
            flush_structure=lambda cb: self.save_now(cb), update_draft=lambda st: self.drafts.update(node_path, st),
            paste_roles=lambda: self.paste_roles(node_id), navigate=lambda d: self.navigate(node_id, d),
            closed=lambda: self.drafts.flush(node_path))
        has_prev = self.canvas.nav_target(node_id, "prev") is not None
        has_next = self.canvas.nav_target(node_id, "next") is not None
        self.data_drawer.open_for(node, node_path, tint, has_prev, has_next, ops)
        if roles:
            self.reload_schemas(silent=True)

    def navigate(self, node_id, direction):
        target = self.canvas.nav_target(node_id, direction)
        if target is not None:
            self.canvas.reveal(target)
            self.open_role_data(target)

    def open_setting(self, node_id):
        node = self._find_node(node_id)
        if node is None or not self.setting_schema:
            return
        d = node.get("data") or {}
        first = (d.get("description") or "").split("\n")[0]
        title = f"サブグループ設定 — ノード {node_id}" + (f"（{first}）" if first else "")
        setting = SGS.get_node_setting(node, self.setting_schema, self.setting_defaults)
        self.setting_drawer.open_for(title, self.setting_schema, setting, self.setting_defaults,
                                    lambda data: self.save_setting(node_id, data), self.event_id, self.sub_id)

    # ------------------------------------------------------------------ スキーマ
    def reload_schemas(self, silent=False, then=None):
        """Role 一覧・全スキーマ・class_data スキーマ・サブグループ設定を取り直す。"""
        lookups, api = self.state.lookups, self.state.api
        gen = self._gen

        def work():
            roles = lookups.roles(refresh=True) or []
            fresh = {}
            for r in roles:
                try:
                    fresh[r["name"]] = lookups.role_form_schema(r["name"], True)
                except Exception:  # noqa: BLE001
                    pass
            classes = lookups.all_class_data_schemas(force=True)
            try:
                setting = SGS.parse_subgroup_setting_response(api.subgroup_setting_form_schema())
            except Exception:  # noqa: BLE001   旧サーバー(APIなし)は設定UIを出さない
                setting = None
            return roles, fresh, classes, setting

        def ok(res):
            if gen != self._gen:
                return
            roles, fresh, classes, setting = res
            self.global_roles, self.role_schemas, self.class_schemas = roles, fresh, classes
            if setting is not None:
                self.setting_schema, self.setting_defaults = setting["schema"], setting["defaults"]
            for c in self.canvas.cards.values():
                c._sig = None
            self.refresh_view()
            if not silent:
                self.toast("Roleスキーマを再取得しました", "success")
            if then:
                then()

        def err(ex):
            if not silent:
                self.fail("スキーマの再取得に失敗しました", ex)
        run_async(work, ok, err, self)

    # ------------------------------------------------------------------ 全体編集 / Sub編集
    def _edit_env(self):
        cur = self.cur()
        ctx = T.EditContext(role_form_schemas=self.role_schemas, class_data_schemas=self.class_schemas,
                            setting_schema=self.setting_schema, setting_defaults=self.setting_defaults,
                            sub_id=js_string(self.sub_id), current_tab_nodes=cur["nodes"], is_sub=self.is_sub,
                            parent_id=self.parent_id, role_data_cache=self.drafts.cache)
        return {"ctx": ctx, "role_names": [r["name"] for r in self.global_roles], "setting_default_line": self._default_setting_line()}

    def _open_edit(self, kind):
        def go(_ok=True):
            def applied(touched):
                if js_string(self.sub_id) in touched or kind == "sub":
                    self.load(self.params)         # 表示中のデータが古くなるので読み直す
            DslEditDialog(self, self.state, kind, self.event_id, self.sub_id, self._edit_env, applied).exec()
        # 画面の変更をサーバーへ反映してから開く(ローカルの未保存ノードもテキストに出すため)
        self.reload_schemas(silent=True)
        self.save_now(go) if self.save.status != "saved" else go()

    def open_all_edit(self):
        if self.event_id is not None:
            self._open_edit("all")

    def open_sub_edit(self):
        if self.event_id is not None and self.sub_id is not None:
            self._open_edit("sub")

    # ------------------------------------------------------------------ Undo / Redo
    def _modal_open(self):
        return any(d.is_open() for d in (self.role_select, self.setting_drawer, self.data_drawer))

    def _key_history(self, d):
        if self._modal_open():
            return
        fw = QGuiApplication.focusObject()
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit
        if isinstance(fw, (QLineEdit, QPlainTextEdit, QTextEdit)):
            return
        self.apply_history(d)

    def apply_history(self, direction):
        target = self.history.apply(self.active, direction, self.tab_data.get(self.active))
        if target is None:
            return
        self.tab_data = {**self.tab_data, self.active: target}
        self.drafts.reset()
        if self.is_sub:
            self.tab_data = T.sync_main_subgroup(self.tab_data, self.parent_id)
        self.schedule_save()
        self.toast("元に戻しました" if direction == "undo" else "やり直しました")

    # ------------------------------------------------------------------ rev 監視
    def _app_state_changed(self, st):
        if st == Qt.ApplicationState.ApplicationActive and self.isVisible():
            self.check_rev()

    def check_rev(self):
        if self.event_id is None or self.sub_id is None:
            return
        hidden = not self.isVisible() or not self.window().isActiveWindow()
        if not self.rev.should_check(hidden=hidden, saving=self.save.saving):
            return
        api, e, s, gen = self.state.api, self.event_id, self.sub_id, self._gen

        def ok(res):
            if gen != self._gen or not isinstance(res, dict):
                return
            if self.rev.observe(res.get("rev"), saving=self.save.saving):
                self.rev_wrap.show()
        run_async(lambda: api.get_rev(e, s), ok, lambda ex: None, self)

    def reload_from_banner(self):
        if self.save.status != "saved" and not C.confirm(self, "未保存の変更があります。再読み込みすると失われます。よろしいですか？", "確認", "再読み込み", danger=True):
            return
        self.load(self.params)

    def ignore_external(self):
        self.rev.ignore_external()
        self.rev_wrap.hide()

    # ------------------------------------------------------------------ CSV
    def export_csv(self):
        name = f"{self.event_id}_{self.sub_id}_{self.active}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "CSV出力", name, "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(T.tab_to_csv(self.cur()))
            self.toast(f"CSVを保存しました: {os.path.basename(path)}", "success")
        except OSError as e:
            self.fail("CSVを保存できませんでした", e)

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "CSV入力", "", "CSV (*.csv);;すべてのファイル (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                parsed = T.parse_csv_to_tab_data(f.read())
        except (OSError, ValueError, UnicodeDecodeError) as e:
            return self.toast(f"CSVの読み込みに失敗しました: {e}", "error")
        self.update_tab_data({**self.tab_data, self.active: parsed})
        self.schedule_save()
        self.toast(f"CSVから {len(parsed['nodes'])} ノード / {len(parsed['edges'])} 接続を読み込みました")
