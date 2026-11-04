"""Qt 層のスモークテスト (PySide6 スタブ + モックサーバー)。

実機の描画・操作は確認できない。ここで見るのは「画面を作って load して主な操作を呼んだとき、
Python の例外(名前/属性/引数の誤り)が出ないこと」と、操作の結果としての *データ* (保存本文など)。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import qt_stub  # noqa: E402

qt_stub.install()

from mock_server import initial_state, start_mock  # noqa: E402


def import_ui():
    from scenario_editor.ui.app_state import AppState
    return AppState


class SmokeBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = start_mock()
        import tempfile
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def setUp(self):
        self.srv.state.clear()
        self.srv.state.update(initial_state())
        AppState = import_ui()
        self.state = AppState(self.tmp)
        self.state.set_base_url(self.srv.url)
        self.toasts = []
        self.state.toast.connect(lambda m, l: self.toasts.append((l, m)))


class ImportTest(unittest.TestCase):
    def test_import_all_modules(self):
        import importlib
        import pkgutil
        import scenario_editor.ui as ui
        names = ["scenario_editor.ui"]
        for m in pkgutil.walk_packages(ui.__path__, "scenario_editor.ui."):
            names.append(m.name)
        for n in names:
            importlib.import_module(n)


class PagesTest(SmokeBase):
    def test_event_list(self):
        from scenario_editor.ui.pages.event_list import EventListPage
        p = EventListPage(self.state)
        p.load({})
        self.assertEqual([t for t in self.toasts if t[0] == "error"], [])

    def test_role_list_and_detail(self):
        from scenario_editor.ui.pages.role_detail import RoleDetailPage, SubGroupSettingPage
        from scenario_editor.ui.pages.role_list import RoleListPage
        RoleListPage(self.state).load({})
        d = RoleDetailPage(self.state)
        d.load({"name": "Say"})
        s = SubGroupSettingPage(self.state)
        s.load({})
        self.assertEqual([t for t in self.toasts if t[0] == "error"], [])

    def test_story_setting(self):
        from scenario_editor.ui.pages.story_setting import StorySettingPage
        p = StorySettingPage(self.state)
        p.load({"eventId": 1, "subId": 1})
        self.assertEqual([t for t in self.toasts if t[0] == "error"], [])


def _tree():
    def node(i, desc="", sub=False, roles=None):
        return {"id": i, "type": "subGroupNode" if sub else "customGroup", "position": {"x": 0, "y": 0},
                "data": {"label": i, "description": desc, "roles": roles or [], "subgroups": {}, "isSubGroup": sub}}
    n1 = node("1", "最初のグループ")
    n1["data"]["subgroups"]["1"] = {"nodes": [node("1", "子A", True), node("2", "子B", True)], "edges": []}
    return {"nodes": [n1, node("2", "二つ目")], "edges": [{"id": "1-2", "source": "1", "target": "2"}]}


class FakeDlg:
    """C.FormDialog / EditPreviewDialog 等の代わり。exec() は常に承認する。"""
    values_to_return = {}

    def __init__(self, *a, **k):
        self.a, self.k = a, k

    def exec(self):
        return 1

    def values(self):
        return dict(FakeDlg.values_to_return)


class TransitionTest(SmokeBase):
    def setUp(self):
        super().setUp()
        self.srv.state["transitions"]["1/1"] = _tree()
        from scenario_editor.ui.pages import transition as TP
        self.TP = TP
        self.page = TP.TransitionPage(self.state)
        self.page.load({"eventId": 1, "subId": 1})

    def errors(self):
        return [t for t in self.toasts if t[0] == "error"]

    def server_nodes(self):
        return self.srv.state["transitions"]["1/1"]["nodes"]

    def save(self):
        qt_stub.fire_timer(self.page.autosave) if self.page.autosave.active else None
        self.page.save_now()

    def test_load(self):
        p = self.page
        self.assertEqual([n["id"] for n in p.tab_data["main"]["nodes"]], ["1", "2"])
        self.assertIn("main", p.save.loaded)
        self.assertEqual(len(p.canvas.cards), 2)
        self.assertTrue(p.global_roles and "Say" in p.role_schemas)
        self.assertIsNotNone(p.setting_schema)
        self.assertEqual(self.errors(), [])

    def test_add_edit_delete_and_autosave(self):
        p = self.page
        orig = self.TP.C.FormDialog
        self.TP.C.FormDialog = FakeDlg
        try:
            FakeDlg.values_to_return = {"description": "新規\n二行目"}
            p.add_node_dialog()
            self.assertEqual([n["id"] for n in p.cur()["nodes"]], ["1", "2", "3"])
            self.assertEqual(p.save.status, "dirty")
            self.assertTrue(p.autosave.active)
            qt_stub.fire_timer(p.autosave)
            self.assertEqual(p.save.status, "saved")
            self.assertEqual([n["id"] for n in self.server_nodes()], ["1", "2", "3"])
            self.assertEqual(self.server_nodes()[2]["data"]["description"], "新規\n二行目")
            self.assertIn("subGroupSetting", self.server_nodes()[2]["data"])   # 設定のデフォルトが入る
            FakeDlg.values_to_return = {"id": "9", "description": "改名"}
            p.edit_node_dialog("3")
            self.assertEqual([n["id"] for n in p.cur()["nodes"]], ["1", "2", "9"])
            p.delete_nodes(["9"])
            p.save_now()
            self.assertEqual([n["id"] for n in self.server_nodes()], ["1", "2"])
        finally:
            self.TP.C.FormDialog = orig
        self.assertEqual(self.errors(), [])

    def test_undo_redo(self):
        p = self.page
        p.delete_nodes(["2"])
        self.assertEqual(len(p.cur()["nodes"]), 1)
        p.history.at = 0
        p.apply_history("undo")
        self.assertEqual([n["id"] for n in p.cur()["nodes"]], ["1", "2"])
        self.assertEqual(len(p.cur()["edges"]), 1)
        p.apply_history("redo")
        self.assertEqual(len(p.cur()["nodes"]), 1)

    def test_connect_reorder_colors(self):
        p = self.page
        p.connect_nodes("2", "1")
        self.assertEqual(len(p.cur()["edges"]), 2)
        p.connect_nodes("2", "1")
        self.assertEqual(self.toasts[-1][1], "既に接続済み")
        p.connect_nodes("2", "99")
        self.assertEqual(self.toasts[-1][1], "存在しないノードID")
        del self.toasts[:]
        p.remove_edge({"source": "2", "target": "1"})
        self.assertEqual(len(p.cur()["edges"]), 1)
        p.reorder_by_id("2", "1")
        self.assertEqual([n["id"] for n in p.cur()["nodes"]], ["2", "1"])
        p.reorder(0, 1)
        self.assertEqual([n["id"] for n in p.cur()["nodes"]], ["1", "2"])
        p.set_colors(["1"], "blue")
        self.assertEqual(self.state.node_colors.get(1, 1), {"1": "blue"})
        self.assertEqual(self.errors(), [])

    def test_subgroup_tab_roles_and_save(self):
        p = self.page
        p.switch_tab("subgroup-1", "1")
        self.assertEqual(p.active, "subgroup-1")
        self.assertEqual([n["id"] for n in p.cur()["nodes"]], ["1", "2"])
        role = p.global_roles[0]
        got = []
        p.add_role_with_server("1", role, unique_id="u1", on_ok=got.append)
        self.assertEqual(got, ["u1"])
        node = p._find_node("1")
        self.assertEqual([r["uniqueId"] for r in node["data"]["roles"]], ["u1"])
        p.save_roles("1/1", "1", [{"uniqueId": "u1", "formData": [{"name": "text", "value": "こんにちは"}]}])
        saved = self.server_nodes()[0]["data"]["subgroups"]["1"]["nodes"][0]["data"]["roles"][0]
        self.assertEqual(saved["data"][0]["value"], "こんにちは")
        p.save_setting("1", [{"name": "is_wait_key", "type": "bool", "value": True}])
        p.save_now()
        sub = self.server_nodes()[0]["data"]["subgroups"]["1"]["nodes"][0]
        self.assertTrue(sub["data"]["subGroupSetting"][0]["value"])
        self.assertEqual(self.errors(), [])

    def test_move_to_group(self):
        p = self.page
        # グループ 2 にサブグループを作っておく
        self.server_nodes()[1]["data"].setdefault("subgroups", {})["2"] = {"nodes": [], "edges": []}
        p.load({"eventId": 1, "subId": 1})
        p.switch_tab("subgroup-1", "1")
        p.move_to_group("1", "2")
        sg1 = self.server_nodes()[0]["data"]["subgroups"]["1"]["nodes"]
        sg2 = self.server_nodes()[1]["data"]["subgroups"]["2"]["nodes"]
        self.assertEqual([n["id"] for n in sg1], ["2"])
        self.assertEqual([n["id"] for n in sg2], ["1"])
        self.assertEqual(self.errors(), [])

    def test_data_drawer_open_close_and_dsl(self):
        p = self.page
        p.switch_tab("subgroup-1", "1")
        p.add_role_with_server("1", p.global_roles[0], unique_id="u1")
        p.save_now()
        p.canvas.render()
        p.open_role_data("1")
        d = p.data_drawer
        self.assertEqual(list(d.cards), ["u1"])
        self.assertIn("u1", d.forms)
        d.save_one("u1") if d.ready.get("u1") else None
        d.request_close()
        self.assertEqual(p.drafts.draft, {})
        self.assertEqual(self.errors(), [])

    def test_edit_dialogs(self):
        p = self.page
        from scenario_editor.ui.dialogs import edit_dialog as ED
        orig = ED.EditPreviewDialog
        ED.EditPreviewDialog = FakeDlg
        try:
            dlg = ED.DslEditDialog(p, self.state, "sub", 1, 1, p._edit_env, lambda t: None)
            dlg.load()
            text = dlg.editor.text()
            self.assertIn("# ==== SUB:1 NODE:1", text)
            new = text.replace("# ==== SUB:1 NODE:1 (最初のグループ) ====", "# ==== SUB:1 NODE:1 (最初のグループ) ====\nSay text=\"hi\"")
            dlg.editor.set_text(new)
            dlg.request_apply()
            roles = self.server_nodes()[0]["data"]["roles"]
            self.assertEqual([r["name"] for r in roles], ["Say"])
        finally:
            ED.EditPreviewDialog = orig
        self.assertEqual(self.errors(), [])

    def test_csv_roundtrip(self):
        p = self.page
        import tempfile
        fn = os.path.join(tempfile.mkdtemp(), "t.csv")
        QF = self.TP.QFileDialog
        self.TP.QFileDialog = type("QFD", (), {"getSaveFileName": staticmethod(lambda *a, **k: (fn, "")),
                                              "getOpenFileName": staticmethod(lambda *a, **k: (fn, ""))})
        try:
            p.export_csv()
            self.assertTrue(os.path.exists(fn))
            p.delete_nodes(["2"])
            p.import_csv()
            self.assertEqual([n["id"] for n in p.cur()["nodes"]], ["1", "2"])
        finally:
            self.TP.QFileDialog = QF
        self.assertEqual(self.errors(), [])

    def test_rev_check(self):
        p = self.page
        self.srv.state["rev"]["1/1"] = "other"
        p.window = lambda: type("W", (), {"isActiveWindow": lambda s: True})()
        p.isVisible = lambda: True
        p.check_rev()
        self.assertEqual(p.rev.external, "other")
        p.ignore_external()
        self.assertEqual(p.rev.known, "other")

    def test_filters_and_selection(self):
        p = self.page
        c = p.canvas
        c.search.setText("二つ目")
        c._query_changed("二つ目")
        self.assertEqual(c.visible_ids, ["2"])
        c._query_changed("")
        c.toggle_select("1")
        c.bulk_wait(True)
        n1 = p._find_node("1")
        self.assertTrue(n1["data"]["subGroupSetting"][0]["value"])
        c._toggle("only_wait")
        self.assertEqual(c.visible_ids, ["1"])

class DrawerAndEditorTest(TransitionTest):
    def test_role_select_drawer(self):
        p = self.page
        picked = []
        p.role_select.open_for("1", p.global_roles, picked.append)
        p.role_select.set_roles(p.global_roles)
        p.open_role_select("1")
        self.assertEqual(self.errors(), [])

    def test_subgroup_setting_drawer(self):
        p = self.page
        applied = []
        p.setting_drawer.open_for("設定", p.setting_schema, [], p.setting_defaults, applied.append, 1, 1)
        self.assertEqual(self.errors(), [])

    def test_dsl_editor(self):
        from scenario_editor.ui.widgets.dsl_editor import DslEditor
        ed = DslEditor()
        ed.set_text("# ==== SUB:1 NODE:1 (a) ====\nSay text=\"x\"\n")
        # QTextDocument はスタブ非対応のため lint の描画部分(_extra_selections)は実機でのみ確認可能
        self.assertIn("SUB:1", ed.text())
        self.assertEqual(self.errors(), [])


class MainWindowTest(SmokeBase):
    def test_main_window_navigation(self):
        from scenario_editor.ui.main_window import MainWindow
        w = MainWindow(self.state)
        self.assertEqual(w.current, "event_list")
        for pid, prm in (("role_list", {}), ("role_detail", {"name": "Say"}), ("subgroup_setting", {}),
                         ("story_setting", {"eventId": 1, "subId": 1}), ("transition", {"eventId": 1, "subId": 1}),
                         ("event_list", {})):
            w.go(pid, prm)
            self.assertEqual(w.current, pid)
        w.go_back()
        cmds = w._commands()
        self.assertTrue(any(c["label"].startswith("遷移:") for c in cmds))
        self.assertEqual(w.current, "transition")
        w.toggle_theme()
        self.assertEqual(w.current, "transition")
        self.assertEqual([t for t in self.toasts if t[0] == "error"], [])


if __name__ == "__main__":
    unittest.main()
