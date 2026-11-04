"""シナリオロール一覧 (ScenarioRoleGrid.js + タグ列)。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout

from ..async_ import run_async
from ..widgets import common as C
from .base import Page

COLS = ["ID", "名前", "説明", "タイプ", "タグ", "アクション"]


def normalize_roles(data) -> list:
    out = []
    if not isinstance(data, list):
        return out
    for item in data:
        out.append({"id": item.get("id"), "name": item.get("name") or "不明", "description": item.get("description") or "",
                    "branchType": item.get("branchType") or "General",
                    "tags": [str(t) for t in (item.get("tags") or [])]})
    return out


def parse_tags(text) -> list:
    out = []
    for t in str(text or "").replace("、", ",").split(","):
        t = t.strip()
        if t and t not in out:
            out.append(t)
    return out


class RoleListPage(Page):
    PAGE_ID = "role_list"

    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self.roles = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.count = C.Chip("0 ロール", "accent")
        hdr, _ = self.make_header("シナリオロール", "遷移図に追加できるロールの定義。名前をクリックするとフィールド定義を編集できます。", widgets=[self.count])
        root.addWidget(hdr)
        bar = QFrame()
        bar.setProperty("toolbar", True)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 8, 20, 8)
        bl.setSpacing(8)
        self.search = C.SearchEdit("名前・説明・タグで検索...")
        self.search.setMinimumWidth(260)
        self.search.textChanged.connect(self.render)
        bl.addWidget(self.search)
        bl.addWidget(C.separator(True))
        bl.addWidget(C.button("追加", "primary", "plus", None, self.add_dialog))
        bl.addWidget(C.button("サブグループ設定", None, "tune",
                              "サブグループごとの設定(入力待ち is_wait_key など)の共通フィールド定義ページ。全イベント共通。",
                              lambda: self.state.go("subgroup_setting")))
        bl.addStretch(1)
        bl.addWidget(C.icon_button("refresh", "再読み込み", self.reload))
        root.addWidget(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(False)
        for i, w in enumerate([70, 220, 300, 100, 220, 120]):
            self.table.setColumnWidth(i, w)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._dbl)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(20, 14, 20, 20)
        wrap.addWidget(self.table)
        root.addLayout(wrap, 1)
        self.loading = True

    def page_title(self):
        return "シナリオロール"

    def load(self, params):
        super().load(params)
        self.reload()

    def on_activated(self):
        self.reload()

    def reload(self):
        self.loading = True

        def ok(data):
            self.loading = False
            self.roles = normalize_roles(data)
            self.state.lookups.invalidate("roles")
            self.render()

        def err(e):
            self.loading = False
            self.roles = []
            self.render()
            self.fail("ロール一覧の取得に失敗", e)
        run_async(lambda: self.state.api.list_roles(), ok, err, self)

    def _visible(self):
        q = self.search.text().strip().lower()
        if not q:
            return list(self.roles)
        return [r for r in self.roles if q in r["name"].lower() or q in r["description"].lower()
                or any(q in t.lower() for t in r["tags"])]

    def render(self, *_):
        rows = self._visible()
        self.count.setText(f"{len(self.roles)} ロール")
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setRowHeight(i, 40)
            self.table.setItem(i, 0, QTableWidgetItem(str(r["id"] if r["id"] is not None else "")))
            nb = C.button(r["name"], "ghost", None, "フィールド定義を編集", lambda n=r["name"]: self.state.go("role_detail", name=n))
            nb.setStyleSheet("text-align:left;font-weight:700;")
            self.table.setCellWidget(i, 1, nb)
            self.table.setItem(i, 2, QTableWidgetItem(r["description"]))
            bt = QTableWidgetItem(r["branchType"])
            self.table.setItem(i, 3, bt)
            ti = QTableWidgetItem("  ".join(f"#{t}" for t in r["tags"]) or "—")
            ti.setToolTip("ダブルクリックでタグを編集")
            self.table.setItem(i, 4, ti)
            db = C.button("削除", "danger", None, None, lambda n=r["name"]: self.delete_role(n), small=True)
            self.table.setCellWidget(i, 5, db)
            self.table.item(i, 0).setData(Qt.ItemDataRole.UserRole, r["name"])

    def _dbl(self, row, col):
        if col != 4:
            return
        name = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        role = next((r for r in self.roles if r["name"] == name), None)
        if role:
            self.edit_tags(role)

    def edit_tags(self, role):
        dlg = C.FormDialog(self, f"タグを編集: {role['name']}", [("tags", "タグ（カンマ区切り）", "text", ", ".join(role["tags"]))],
                           info="ドキュメント生成などでロールを分類するためのタグです。", ok_text="保存")
        if not dlg.exec():
            return
        tags = parse_tags(dlg.values()["tags"])

        def ok(_):
            role["tags"] = tags
            self.toast("タグを保存しました", "success")
            self.render()
        run_async(lambda: self.state.api.update_role_tags({role["name"]: tags}), ok, lambda e: self.fail("タグ保存エラー", e), self)

    def add_dialog(self):
        dlg = C.FormDialog(self, "新しいロールの作成", [
            ("name", "ロール名", "text", ""), ("description", "説明", "text", ""),
            ("branchType", "タイプ", "choice", ("General", [("General", "General"), ("Branch", "Branch")]))], ok_text="作成")
        if not dlg.exec():
            return
        v = dlg.values()
        if not v["name"].strip():
            self.toast("ロール名を入力してください", "error")
            return

        def ok(res):
            self.toast((res or {}).get("message") or "作成しました", "success")
            self.reload()
        run_async(lambda: self.state.api.create_role(v["name"], v["description"], v["branchType"] or "General"), ok,
                  lambda e: self.fail("ロール追加エラー", e), self)

    def delete_role(self, name):
        def go():
            def ok(res):
                self.toast((res or {}).get("message") or "削除しました", "success")
                self.roles = [r for r in self.roles if r["name"] != name]
                self.state.lookups.invalidate("roles")
                self.render()
            run_async(lambda: self.state.api.delete_role(name), ok, lambda e: self.fail("ロール削除エラー", e), self)
        C.confirm_delete_with_reference_check(self, self.state, "scenario_role", name, go)
