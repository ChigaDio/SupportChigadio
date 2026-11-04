"""core/subgroup_setting.py(JS差分) と core/presets.py(動作) のテスト。"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from jscompare import norm, run_js_adapter  # noqa: E402
from scenario_editor.core import presets as P  # noqa: E402
from scenario_editor.core import subgroup_setting as S  # noqa: E402

SCHEMA = {'fields': [
    {'name': 'is_wait_key', 'type': 'bool', 'default': False},
    {'name': 'delay', 'type': 'float'},
    {'name': 'mode', 'type': 'Mode', 'options': ['Mode.A', 'Mode.B']},
]}
DEFAULTS = [{'name': 'is_wait_key', 'type': 'bool', 'value': False}, {'name': 'delay', 'type': 'float', 'value': 0},
            {'name': 'mode', 'type': 'Mode', 'value': 'Mode.A'}]


class SubGroupSettingTest(unittest.TestCase):
    def test_against_js(self):
        nodes = [None, {}, {'data': {}}, {'data': {'subGroupSetting': [{'name': 'delay', 'type': 'float', 'value': 2}]}},
                 {'data': {'subGroupSetting': [{'name': 'is_wait_key', 'type': 'bool', 'value': True}, {'name': 'zz', 'value': 1}]}}]
        cases = [{'node': n, 'schema': SCHEMA, 'defaults': DEFAULTS} for n in nodes]
        js = run_js_adapter('scenarioSubGroupSetting', """(m, a) => {
          const s = m.getNodeSetting(a.node, a.schema, a.defaults);
          return { s, wait: m.getSettingValue(s, 'is_wait_key', 'fb'), none: m.getSettingValue(s, 'nope', 'fb'),
                   set1: m.setSettingValue(s, 'delay', 9, a.schema, a.defaults), set2: m.setSettingValue(s, 'extra', 1, a.schema, a.defaults),
                   form: m.formDataToSetting([{ name: 'delay', value: 4 }], a.schema), init: m.buildInitialSetting(a.defaults),
                   line: m.buildDefaultSettingLine(a.schema, a.defaults, {}) };
        }""", cases)
        for c, j in zip(cases, js):
            s = S.get_node_setting(c['node'], SCHEMA, DEFAULTS)
            self.assertEqual(norm(s), norm(j['s']))
            self.assertEqual(S.get_setting_value(s, 'is_wait_key', 'fb'), j['wait'])
            self.assertEqual(S.get_setting_value(s, 'nope', 'fb'), j['none'])
            self.assertEqual(norm(S.set_setting_value(s, 'delay', 9, SCHEMA, DEFAULTS)), norm(j['set1']))
            self.assertEqual(norm(S.set_setting_value(s, 'extra', 1, SCHEMA, DEFAULTS)), norm(j['set2']))
            self.assertEqual(norm(S.form_data_to_setting([{'name': 'delay', 'value': 4}], SCHEMA)), norm(j['form']))
            self.assertEqual(norm(S.build_initial_setting(DEFAULTS)), norm(j['init']))
            self.assertEqual(S.build_default_setting_line(SCHEMA, DEFAULTS), j['line'])

    def test_parse_response(self):
        self.assertEqual(S.parse_subgroup_setting_response({'schema': SCHEMA, 'defaults': DEFAULTS}), {'schema': SCHEMA, 'defaults': DEFAULTS})
        self.assertIsNone(S.parse_subgroup_setting_response({'schema': {'error': 'x', 'fields': []}})['schema'])
        self.assertEqual(S.parse_subgroup_setting_response(None), {'schema': None, 'defaults': []})


class FakeServer:
    def __init__(self):
        self.presets = {}
        self.up = True

    def __call__(self, url, method='GET', body=None):
        if not self.up:
            raise ConnectionError('down')
        if url == P.PRESET_API and method == 'GET':
            return True, 200, {'presets': self.presets}
        if url == P.PRESET_API and method == 'POST':
            lst = [p for p in self.presets.get(body['roleName'], []) if p['name'] != body['name']]
            self.presets[body['roleName']] = [{'name': body['name'], 'data': body['data'], 'savedAt': 1}, *lst]
            return True, 200, {'presets': self.presets[body['roleName']]}
        if url.startswith(P.PRESET_API + '?') and method == 'DELETE':
            return True, 200, {}
        if url == P.PRESET_API + '/import':
            n = 0
            for role, items in body['presets'].items():
                for it in items:
                    self.presets.setdefault(role, []).append(it)
                    n += 1
            return True, 200, {'presets': self.presets, 'imported': n, 'skipped': 0}
        return False, 404, None


class PresetTest(unittest.TestCase):
    def test_flow(self):
        with tempfile.TemporaryDirectory() as d:
            srv = FakeServer()
            pm = P.PresetManager(srv, d)
            seen = []
            pm.subscribe(lambda: seen.append(1))
            self.assertTrue(pm.refresh())
            self.assertEqual(pm.save_preset('Say', 'p1', [{'name': 'a', 'value': 1}]), {'ok': True, 'shared': True})
            self.assertEqual([p['name'] for p in pm.list_presets('Say')], ['p1'])
            # 未接続 → ローカル退避
            srv.up = False
            self.assertEqual(pm.save_preset('Say', 'p2', [{'name': 'a', 'value': 2}]), {'ok': True, 'shared': False})
            self.assertEqual([(p['name'], p.get('local')) for p in pm.list_presets('Say')], [('p1', None), ('p2', True)])
            self.assertEqual(pm.get_local_only_count(), 1)
            # 再起動してもローカルが残る
            pm2 = P.PresetManager(srv, d)
            self.assertEqual(pm2.get_local_only_count(), 1)
            # 復旧後に移行
            srv.up = True
            pm.refresh()
            self.assertEqual(pm.migrate_local_presets(), {'ok': True, 'imported': 1, 'skipped': 0})
            self.assertEqual(pm.get_local_only_count(), 0)
            self.assertEqual(pm.get_preset_data('Say', 'p2'), [{'name': 'a', 'value': 2}])
            self.assertTrue(pm.delete_preset('Say', 'p1'))
            self.assertNotIn('p1', [p['name'] for p in pm.list_presets('Say')])
            self.assertFalse(pm.save_preset('', 'x', [])['ok'])
            self.assertGreater(len(seen), 2)

    def test_clipboard_and_ids(self):
        with tempfile.TemporaryDirectory() as d:
            c = P.RoleClipboard(d)
            self.assertEqual(c.get(), [])
            self.assertEqual(c.set([{'id': 1, 'name': 'Say', 'uniqueId': 'zzz', 'data': [{'name': 'a', 'value': 1}]}]), 1)
            self.assertEqual(P.RoleClipboard(d).get(), [{'id': 1, 'name': 'Say', 'branchType': 'General', 'data': [{'name': 'a', 'value': 1}]}])
        ids = P.make_unique_ids(3, ['99999999999999'])
        self.assertEqual(ids, ['100000000000000', '100000000000001', '100000000000002'])
        self.assertEqual(len(set(P.make_unique_ids(5, []))), 5)


if __name__ == '__main__':
    unittest.main()
