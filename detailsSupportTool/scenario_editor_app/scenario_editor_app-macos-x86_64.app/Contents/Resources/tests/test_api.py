"""api/client.py と api/lookups.py を、モックサーバーに対して通しで確認する。"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from mock_server import start_mock  # noqa: E402
from scenario_editor.api.client import ApiClient, ApiError  # noqa: E402
from scenario_editor.api.lookups import LookupCache  # noqa: E402
from scenario_editor.core.presets import PresetManager  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = start_mock()

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def setUp(self):
        self.srv.state.clear()
        from mock_server import initial_state
        self.srv.state.update(initial_state())
        self.api = ApiClient(self.srv.url)

    def test_events(self):
        evs = self.api.list_events()
        self.assertEqual(evs[0]["subEvents"][0]["subId"], 1)
        self.api.create_event({"id": 2, "name": "B", "description": ""})
        sid = self.api.create_sub(2, {"name": "s", "description": ""})["subId"]
        self.api.update_sub(2, sid, {"name": "s2", "description": "d"})
        self.assertEqual(self.srv.state["events"]["2"]["subs"][str(sid)]["name"], "s2")
        self.api.copy_sub(2, sid, {"targetEventId": 1})
        self.api.copy_event(1, {"copySubs": True})
        self.api.delete_sub(2, sid)
        self.api.delete_event(2)
        with self.assertRaises(ApiError) as cm:
            self.api.delete_event(999)
        self.assertEqual(cm.exception.status, 404)
        self.assertIn("not found", str(cm.exception))

    def test_transition_and_roles(self):
        data, rev = self.api.get_transition(1, 1)
        self.assertEqual(rev, "r0")
        r = self.api.add_role_to_node(1, 1, "1", 1, "Say", "General", "u1")
        self.assertTrue(r["rev"])
        self.assertEqual(r["data"][0]["name"], "text")
        r2 = self.api.save_role_data_batch(1, 1, [{"nodePath": "1", "uniqueId": "u1", "formData": [{"name": "text", "value": "hi"}]}])
        self.assertEqual(self.api.get_rev(1, 1)["rev"], r2["rev"])
        data, rev = self.api.get_transition(1, 1)
        self.assertEqual(data["nodes"][0]["data"]["roles"][0]["data"][0]["value"], "hi")
        self.assertEqual(rev, r2["rev"])
        self.api.save_subgroup(1, 1, "1", [{"id": "1", "data": {"roles": []}}], [])
        self.assertEqual(self.api.get_subgroup(1, 1, "1")["nodes"][0]["id"], "1")
        res = self.api.save_transition(1, 1, data["nodes"], [])
        self.assertNotEqual(res["rev"], r2["rev"])
        with self.assertRaises(ApiError):
            self.api.get_transition(9, 9)

    def test_role_definition(self):
        self.assertEqual(self.api.list_roles()[0]["name"], "Say")
        res = self.api.create_role("Wait", "待つ", "General")
        self.assertIn("id", res["data"])
        self.api.save_role_definition("Wait", [{"name": "sec", "type": "float"}], "General")
        self.assertEqual(self.api.get_role("Wait")["data"][0]["name"], "sec")
        self.assertEqual(self.api.role_form_schema("Wait")["fields"][0]["name"], "sec")
        self.api.update_role_tags({"Wait": ["time"]})
        self.assertEqual(self.srv.state["roles"]["Wait"]["tags"], ["time"])
        self.api.delete_role("Wait")
        self.assertNotIn("Wait", self.srv.state["roles"])
        self.assertEqual(self.api.check_references("scenario_role", "Say"), {"references": []})

    def test_setting_and_story(self):
        sc = self.api.subgroup_setting_form_schema()
        self.assertEqual(sc["schema"]["fields"][0]["name"], "is_wait_key")
        self.api.save_subgroup_setting_defaults({"is_wait_key": True})
        self.assertTrue(self.api.subgroup_setting_form_schema()["defaults"][0]["value"])
        self.api.save_subgroup_setting_field_default("is_wait_key", False)
        self.api.clear_subgroup_setting_field_default("is_wait_key")
        self.assertNotIn("default", self.srv.state["setting"]["data"][0])
        self.api.save_story(1, 1, [{"slot": "img"}], 3)
        self.assertEqual(self.api.get_story(1, 1)["voiceSeriesId"], 3)

    def test_masters_and_lookups(self):
        lk = LookupCache(self.api)
        self.assertEqual(lk.enum_members("Chara"), ["Alice", "Bob"])
        self.assertEqual(lk.class_data_id_members("ItemID"), ["Potion", "Sword"])
        types = lk.type_options()
        self.assertIn("voice_ref", types["all"])
        self.assertNotIn("voice_ref", lk.type_options(setting_mode=True)["all"])
        self.assertIn("bezier", types["all"])
        # キャッシュ
        self.srv.state["enums"]["Chara"].append("Eve")
        self.assertEqual(lk.enum_members("Chara"), ["Alice", "Bob"])
        lk.invalidate("enum")
        self.assertEqual(lk.enum_members("Chara"), ["Alice", "Bob", "Eve"])
        # スキーマ
        self.assertEqual(lk.role_form_schema("Say")["role"], "Say")
        with self.assertRaises(ApiError):
            lk.role_form_schema("Nope")

    def test_presets_via_manager(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            pm = PresetManager(self.api.request_json, d)
            pm.save_preset("Say", "greet", [{"name": "text", "value": "hi"}])
            pm.refresh()
            self.assertEqual([p["name"] for p in pm.list_presets("Say")], ["greet"])
            self.assertEqual(self.srv.state["presets"]["Say"][0]["name"], "greet")

    def test_connection_error(self):
        api = ApiClient("http://127.0.0.1:1", timeout=1)
        with self.assertRaises(ApiError) as cm:
            api.list_events()
        self.assertEqual(cm.exception.status, 0)
        self.assertFalse(api.ping())
        self.assertTrue(self.api.ping())


if __name__ == "__main__":
    unittest.main()
