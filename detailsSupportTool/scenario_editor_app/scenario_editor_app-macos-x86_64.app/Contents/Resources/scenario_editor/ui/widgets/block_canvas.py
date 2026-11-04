"""ブロック一覧 (ScenarioEventTransition.js: BlockCanvas)。検索・フィルタ・複数選択・一括操作 + カード一覧。"""
from __future__ import annotations

import json
from types import SimpleNamespace

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QVBoxLayout, QWidget, QWidgetAction)

from ...core import index_tools as IT
from ...core import node_utils as NU
from ...core import subgroup_setting as SGS
from ...core import transition_ops as T
from ...core import validation as V
from .. import icons, theme
from ..dialogs.index_tools_dialog import IndexToolsDialog
from . import common as C
from .block_card import BlockCard, color_palette


class BlockCanvas(QWidget):
    def __init__(self, state, h, parent=None):
        super().__init__(parent)
        self.state, self.h = state, h
        self.nodes, self.edges = [], []
        self.is_sub, self.parent_id = False, None
        self.ctx = SimpleNamespace(role_names=None, role_schemas={}, class_schemas={}, setting_schema=None,
                                   setting_defaults=[], node_colors={})
        self.cards = {}
        self.selected = set()
        self.query = ""
        self.only_wait = self.only_roles = self.only_issues = False
        self.auto_tint = bool(state.settings.get("autoTint", True))
        self.validation = {"byNode": {}, "edgeIssues": [], "counts": {"error": 0, "warn": 0, "info": 0}, "total": 0}
        self.dup_plan = {"renamed": [], "skipped": []}
        self.visible_ids = []
        self._issue_cache = {}
        self._tab_key = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(8)

        # --- フィルタバー
        self.bar = C.Card(flat=True)
        self.bar.body.setContentsMargins(10, 8, 10, 8)
        self.bar.body.setSpacing(6)
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.search = C.SearchEdit("ID・説明・Role名で検索（スペース区切りでAND）")
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(self._query_changed)
        row1.addWidget(self.search, 1)
        self.chip_wait = C.Chip("入力待ちのみ", "true", clickable=True)
        self.chip_roles = C.Chip("Roleありのみ", "true", clickable=True)
        self.chip_issues = C.Chip("問題なし", "ok", clickable=True)
        self.chip_tint = C.Chip("自動色分け", "accent" if self.auto_tint else "true", clickable=True)
        self.chip_wait.clicked.connect(lambda: self._toggle("only_wait"))
        self.chip_roles.clicked.connect(lambda: self._toggle("only_roles"))
        self.chip_issues.clicked.connect(self._issues_clicked)
        self.chip_tint.clicked.connect(self.toggle_tint)
        for w in (self.chip_wait, self.chip_roles, self.chip_issues, self.chip_tint):
            row1.addWidget(w)
        self.bar.body.addLayout(row1)
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.dup_btn = C.button("", "danger", "build", on_click=lambda: self.h.renumber_duplicates(), small=True)
        self.utils_btn = C.button("Utils", "ghost", "build", on_click=self.open_utils, small=True)
        row2.addWidget(self.dup_btn)
        row2.addWidget(self.utils_btn)
        row2.addWidget(C.button("全て折畳", "ghost", on_click=lambda: self.collapse_all(True), small=True))
        row2.addWidget(C.button("全て展開", "ghost", on_click=lambda: self.collapse_all(False), small=True))
        row2.addStretch(1)
        self.count_lb = C.label("", "muted")
        row2.addWidget(self.count_lb)
        self.bar.body.addLayout(row2)
        # --- 選択バー
        self.sel_bar = QFrame()
        self.sel_bar.setProperty("banner", "info")
        sl = QHBoxLayout(self.sel_bar)
        sl.setContentsMargins(10, 4, 10, 4)
        sl.setSpacing(6)
        self.sel_lb = C.label("")
        self.sel_lb.setStyleSheet("font-weight:700;")
        sl.addWidget(self.sel_lb)
        self.bw_on = C.button("入力待ち ON", "warn", on_click=lambda: self.bulk_wait(True), small=True)
        self.bw_off = C.button("入力待ち OFF", on_click=lambda: self.bulk_wait(False), small=True)
        sl.addWidget(self.bw_on)
        sl.addWidget(self.bw_off)
        sl.addWidget(C.button("背景色", on_click=self.bulk_color_menu, small=True))
        sl.addWidget(C.button("削除", "danger", on_click=self.bulk_delete, small=True))
        sl.addStretch(1)
        sl.addWidget(C.button("表示中を全選択", "ghost", on_click=self.select_visible, small=True))
        sl.addWidget(C.button("選択解除", "ghost", on_click=self.clear_selection, small=True))
        self.sel_bar.hide()
        self.bar.body.addWidget(self.sel_bar)
        lay.addWidget(self.bar)

        # --- 一覧
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic = QLabel()
        ic.setPixmap(icons.icon("graph", theme.color("faint"), 56).pixmap(56, 56))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(ic)
        t = C.label("ノードがありません", "h2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t)
        s = C.label("上の「ノード追加」ボタンからノードを追加してください", "muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(s)
        self.no_match = C.label("条件に一致するノードがありません", "muted")
        self.no_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.host = QWidget()
        self.cards_lay = QVBoxLayout(self.host)
        self.cards_lay.setContentsMargins(0, 0, 6, 12)
        self.cards_lay.setSpacing(10)
        self.cards_lay.addWidget(self.no_match)
        self.cards_lay.addStretch(1)
        self.scroll.setWidget(self.host)
        lay.addWidget(self.scroll, 1)
        lay.addWidget(self.empty, 1)

    # ---------------------------------------------------------------- データ
    def set_data(self, nodes, edges, is_sub, parent_id, ctx):
        tab_key = (is_sub, parent_id)
        if tab_key != self._tab_key:
            self._tab_key = tab_key
            self.selected = set()
        self.nodes, self.edges, self.is_sub, self.parent_id, self.ctx = nodes, edges, is_sub, parent_id, ctx
        ids = {n["id"] for n in nodes}
        self.selected &= ids
        self._recompute()
        self.render()

    def node_path(self, node_id):
        return f"{self.parent_id}/{node_id}" if self.is_sub else str(node_id)

    def _is_wait(self, n):
        return T.is_wait_node(n, self.ctx.setting_schema, self.ctx.setting_defaults)

    def _recompute(self):
        c = self.ctx
        v = V.validate_graph(self.nodes, self.edges, {"isSub": self.is_sub, "roleNames": c.role_names, "roleSchemas": c.role_schemas})
        # 内容が同じ問題リストは同じ参照にそろえる(カードの再描画を避ける)
        stable, nxt = {}, {}
        for nid, lst in v["byNode"].items():
            key = json.dumps(lst, ensure_ascii=False, sort_keys=True)
            prev = self._issue_cache.get(nid)
            arr = prev[1] if prev and prev[0] == key else lst
            nxt[nid] = (key, arr)
            stable[nid] = arr
        self._issue_cache = nxt
        v["byNode"] = stable
        self.validation = v
        self.dup_plan = NU.renumber_duplicate_nodes(self.nodes)

    def _visible(self):
        vis = T.filter_visible(self.nodes, self.query, self.only_wait, self.only_roles, self.only_issues,
                               self.validation["byNode"], self._is_wait)
        return vis

    @property
    def filtering(self):
        return bool(self.query.strip()) or self.only_wait or self.only_roles or self.only_issues

    # ---------------------------------------------------------------- 描画
    def render(self):
        nodes = self.nodes
        has_nodes = bool(nodes)
        self.empty.setVisible(not has_nodes)
        self.scroll.setVisible(has_nodes)
        self.bar.setVisible(True)
        setting_on = bool(self.ctx.setting_schema)
        self.chip_wait.setVisible(setting_on)
        self.bw_on.setVisible(setting_on)
        self.bw_off.setVisible(setting_on)
        self._update_chips()
        if not has_nodes:
            for c in self.cards.values():
                c.setParent(None)
                c.deleteLater()
            self.cards = {}
            self.visible_ids = []
            return
        vis = self._visible()
        vis_ids = [n["id"] for n, _ in vis]
        self.visible_ids = vis_ids
        vis_set, index_of = set(vis_ids), {n["id"]: i for i, n in enumerate(nodes)}
        # 消えたノードのカードを捨てる
        ids = set(index_of)
        for nid in [k for k in self.cards if k not in ids]:
            w = self.cards.pop(nid)
            w.setParent(None)
            w.deleteLater()
        # 作成
        for n in nodes:
            if n["id"] not in self.cards:
                self.cards[n["id"]] = BlockCard(self.h, self)
        # 並び順(ノード順)
        want = [self.cards[n["id"]] for n in nodes]
        cur = [self.cards_lay.itemAt(i).widget() for i in range(self.cards_lay.count())]
        cur_cards = [w for w in cur if isinstance(w, BlockCard)]
        if cur_cards != want:
            for i in reversed(range(self.cards_lay.count())):
                it = self.cards_lay.takeAt(i)
                w = it.widget()
                if w is not None and w is not self.no_match:
                    w.setParent(None)
            for w in want:
                self.cards_lay.addWidget(w)
            self.cards_lay.addWidget(self.no_match)
            self.cards_lay.addStretch(1)
        nav = self.nav_ids()
        all_ids = [n["id"] for n in nodes]
        for n in nodes:
            nid = n["id"]
            card = self.cards[nid]
            show = nid in vis_set
            if not show:
                card.setVisible(False)
                card._sig = None
                continue
            path = self.node_path(nid)
            color_key = self.ctx.node_colors.get(path)
            if color_key is None and not self.auto_tint:
                color_key = "none"
            pos = nav.index(nid) if nid in nav else -1
            v = SimpleNamespace(index=index_of[nid], total=len(nodes), is_sub=self.is_sub, edges=self.edges, all_ids=all_ids,
                                path=path, color_key=color_key, selected=nid in self.selected,
                                issues=self.validation["byNode"].get(str(nid)), schema=self.ctx.setting_schema,
                                defaults=self.ctx.setting_defaults, has_prev=pos > 0, has_next=0 <= pos < len(nav) - 1)
            sig = (id(n), id(self.edges), id(v.issues), color_key, v.selected, v.index, v.total, self.is_sub, path,
                   id(v.schema), id(v.defaults), len(all_ids), theme.current_theme())
            if card._sig != sig or card.node is not n:
                card._sig = sig
                card.update_view(n, v)
            else:
                card.v = v
            card.setVisible(True)
        self.no_match.setVisible(not vis)
        self.count_lb.setText(f"{len(vis)} / {len(nodes)} 件" if self.filtering else f"{len(nodes)} 件")
        self._update_selection_bar()

    def _update_chips(self):
        self.chip_wait.set_kind("warn" if self.only_wait else "true")
        self.chip_roles.set_kind("accent" if self.only_roles else "true")
        self.chip_tint.set_kind("accent" if self.auto_tint else "true")
        c = self.validation["counts"]
        n = c["error"] + c["warn"]
        if n > 0:
            self.chip_issues.setText(f"問題 {n}件")
            self.chip_issues.set_kind("err" if c["error"] > 0 else "warn")
            msgs = []
            for nid, lst in self.validation["byNode"].items():
                msgs += [f"ノード{nid}: {i['message']}" for i in lst if i["level"] != "info"]
            msgs += [i["message"] for i in self.validation["edgeIssues"]]
            self.chip_issues.setToolTip("\n".join(msgs[:12]) + "\nクリックで「問題ありのみ」表示")
            self.chip_issues.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.chip_issues.setText("問題なし")
            self.chip_issues.set_kind("ok")
            self.chip_issues.setToolTip("")
        ren = self.dup_plan["renamed"]
        self.dup_btn.setVisible(bool(ren))
        if ren:
            self.dup_btn.setText(f"重複IDを振り直す（{len(ren)}件）")
            self.dup_btn.setToolTip("同じ階層で重複しているIDを、重複した2番目以降だけ未使用のIDへ振り直します（"
                                    + ", ".join(f"{r['from']}→{r['to']}" for r in ren) + "）")

    # ---------------------------------------------------------------- フィルタ操作
    def _query_changed(self, text):
        self.query = text
        self.render()

    def _toggle(self, attr):
        setattr(self, attr, not getattr(self, attr))
        self.render()

    def _issues_clicked(self):
        c = self.validation["counts"]
        if c["error"] + c["warn"] > 0:
            self._toggle("only_issues")

    def toggle_tint(self):
        self.auto_tint = not self.auto_tint
        self.state.settings["autoTint"] = self.auto_tint
        self.state.save_settings()
        for c in self.cards.values():
            c._sig = None
        self.render()

    def collapse_all(self, value):
        for c in self.cards.values():
            c.set_collapsed(value)

    # ---------------------------------------------------------------- 選択 / 一括
    def toggle_select(self, node_id):
        if node_id in self.selected:
            self.selected.discard(node_id)
        else:
            self.selected.add(node_id)
        self.render()

    def select_visible(self):
        self.selected = set(self.visible_ids)
        self.render()

    def clear_selection(self):
        self.selected = set()
        self.render()

    def _update_selection_bar(self):
        n = len(self.selected)
        self.sel_bar.setVisible(n > 0)
        self.sel_lb.setText(f"{n} 件選択中")

    def bulk_wait(self, val):
        schema, defaults = self.ctx.setting_schema, self.ctx.setting_defaults
        if not schema:
            return
        for n in self.nodes:
            if n["id"] in self.selected:
                cur = SGS.get_node_setting(n, schema, defaults)
                self.h.save_setting(n["id"], SGS.set_setting_value(cur, SGS.IS_WAIT_KEY_FIELD, val, schema, defaults))

    def bulk_delete(self):
        if not C.confirm(self, f"選択中の {len(self.selected)} 件のノードを削除します。よろしいですか？", "確認", "削除", danger=True):
            return
        ids = [n["id"] for n in self.nodes if n["id"] in self.selected]
        self.selected = set()
        self.h.delete_many(ids)

    def bulk_color_menu(self):
        m = QMenu(self)
        wa = QWidgetAction(m)
        paths = [self.node_path(i) for i in self.selected]
        wa.setDefaultWidget(color_palette("__none__", lambda key: (m.close(), self.h.set_colors(paths, key)), "選択中のノードの背景色"))
        m.addAction(wa)
        m.exec(self.cursor().pos())

    # ---------------------------------------------------------------- Utils / インデックス調整
    def open_utils(self):
        m = QMenu(self)
        m.addAction(icons.icon("build"), "インデックスを一括調整…", self._utils_index).setToolTip(
            "選択中(なければ先頭)のサブグループ以降の text_list_index / voice_ref をずらす・連番にする")
        n = len(self.dup_plan["renamed"])
        a = m.addAction(f"重複しているIDを振り直す{f'（{n}件）' if n else ''}", lambda: self.h.renumber_duplicates())
        a.setEnabled(n > 0)
        a.setToolTip("同じ階層で重複したIDの2番目以降を、未使用のIDへ")
        m.setToolTipsVisible(True)
        m.exec(self.utils_btn.mapToGlobal(QPoint(0, self.utils_btn.height())))

    def _utils_index(self):
        first = next((n for n in self.nodes if n["id"] in self.selected), None)
        if first is None and self.visible_ids:
            first = next((n for n in self.nodes if n["id"] == self.visible_ids[0]), None)
        if first is not None:
            self.open_index_tools(first["id"])

    def open_index_tools(self, start_id):
        nodes, schemas = self.nodes, self.ctx.role_schemas
        opts = [{"value": str(n["id"]),
                 "label": f"ノード {n['id']}" + (f" — {str((n.get('data') or {}).get('description')).split(chr(10))[0][:24]}"
                                                  if (n.get("data") or {}).get("description") else "")} for n in nodes]

        def make_plan(o):
            return IT.plan_index_adjust(nodes, schemas, {
                "startNodeId": o["start"], "endNodeId": o.get("end") or None, "mode": o["mode"], "delta": o["delta"],
                "step": o["step"], "base": o["base"], "includeStart": o["includeStart"], "includeInt": o["includeInt"],
                "target": o["target"]})

        def describe(c):
            ai = c.get("arrayIndex")
            return {"where": f"ノード {c['nodeId']}", "field": f"{c['roleName']}.{c['fieldName']}" + (f"[{ai}]" if ai is not None else "")}

        dlg = IndexToolsDialog(self, opts, str(start_id), lambda inc: IT.collect_index_fields(nodes, schemas, {"includeInt": inc}),
                               make_plan, describe,
                               title=f"インデックス一括調整（{'このグループ内のサブグループ' if self.is_sub else 'グループ'}）")
        if dlg.exec() and dlg.plan.get("changes"):
            self.h.apply_index_changes(dlg.plan["changes"])

    # ---------------------------------------------------------------- ナビゲーション / スクロール
    def nav_ids(self):
        vis = [(n, i) for n, i in self._visible_cached()]
        return T.nav_list(vis, self.is_sub)

    def _visible_cached(self):
        s = set(self.visible_ids)
        return [(n, i) for i, n in enumerate(self.nodes) if n["id"] in s]

    def nav_target(self, node_id, direction):
        return T.navigate_target(self.nav_ids(), node_id, direction)

    def reveal(self, node_id):
        c = self.cards.get(node_id)
        if c is not None:
            self.scroll.ensureWidgetVisible(c, 0, 80)

    def autoscroll(self, global_pos):
        vp = self.scroll.viewport()
        y = vp.mapFromGlobal(global_pos).y()
        bar = self.scroll.verticalScrollBar()
        if y < 50:
            bar.setValue(bar.value() - 26)
        elif y > vp.height() - 50:
            bar.setValue(bar.value() + 26)
