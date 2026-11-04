import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from scenario_editor.core import role_detail_ops as D  # noqa: E402


def base():
    data, bt = D.normalize_loaded({'data': [
        {'type': 'bool', 'name': 'flag'}, {'type': 'FadeID', 'name': 'fade', 'required': False},
        {'type': 'int', 'name': 'n', 'dependency': {'parentFieldName': 'flag', 'enableValues': [True]}},
        {'type': 'string', 'name': 'is_wait_key', 'builtin': True, 'id': 77}]})
    return data


class RoleDetailTest(unittest.TestCase):
    def test_normalize(self):
        d, bt = D.normalize_loaded({'data': [{'name': 'a'}, {'name': 'b', 'id': 9, 'required': False}]})
        self.assertEqual([(f['id'], f['required']) for f in d], [(1, True), (9, False)])
        self.assertEqual(bt, 'General')
        self.assertEqual(D.normalize_loaded({'branchType': 'Branch'})[1], 'Branch')

    def test_add(self):
        d = base()
        nd, err = D.add_field(d, type_='bit', name='b', options=D.default_options_for_type('bit'), array_size='3x')
        self.assertIsNone(err)
        self.assertEqual(nd[-1]['id'], 78)
        self.assertEqual(nd[-1]['arraySize'], 3)
        self.assertEqual(nd[-1]['options']['size'], 8)
        self.assertNotIn('options', D.add_field(d, type_='int', name='x', options={'a': 1})[0][-1])
        self.assertEqual(D.add_field(d, type_='', name='x')[1], 'タイプと名前は必須です')
        self.assertIn('既に存在', D.add_field(d, type_='int', name='n', setting_mode=True)[1])
        self.assertIsNone(D.add_field(d, type_='int', name='n')[1])
        nd, _ = D.add_field(d, type_='int', name='q', dep_parent='flag', dep_values=[])
        self.assertEqual(nd[-1]['dependency'], {'parentFieldName': 'flag', 'enableValues': [True], 'hideWhenDisabled': True})
        nd, _ = D.add_field(d, type_='int', name='q', dep_parent='fade', dep_values=['A'])
        self.assertEqual(nd[-1]['dependency']['enableValues'], ['A'])

    def test_dependency_edit_delete(self):
        d = base()
        d2 = D.set_dependency(d, 3, None, [])
        self.assertNotIn('dependency', d2[2])
        d3 = D.set_dependency(d, 3, 'fade', ['A', 'B'])
        self.assertEqual(d3[2]['dependency']['enableValues'], ['A', 'B'])
        d4 = D.delete_field(d, 1)
        self.assertNotIn('dependency', d4[1])
        self.assertEqual(len(d4), 3)
        self.assertEqual(D.delete_field(d, 77, setting_mode=True), d)
        self.assertEqual(len(D.delete_field(d, 77)), 3)
        self.assertEqual(D.children_by_parent(d), {'flag': ['n']})
        self.assertEqual(D.dependency_summary(d[2]), 'flag = True')
        self.assertEqual(D.dependency_summary({'dependency': {'parentFieldName': 'p'}}), 'p = …')
        self.assertEqual(D.dependency_summary(d[0]), '')

    def test_move_toggle_edit(self):
        d = base()
        self.assertEqual([f['name'] for f in D.move_field(d, 1, 1)][:2], ['fade', 'flag'])
        self.assertEqual(D.move_field(d, 1, -1), d)
        self.assertEqual(D.move_field(d, 3, 1, setting_mode=True), d)
        self.assertEqual(D.move_field(d, 3, 1, setting_mode=False)[3]['name'], 'n')
        self.assertEqual(D.move_field(d, 2, 1, setting_mode=True)[1]['name'], 'n')
        d2 = D.move_field(d, 3, 1, setting_mode=True)
        self.assertEqual(d2, d)
        self.assertEqual(D.toggle_required(d, 1)[0]['required'], False)
        self.assertEqual(D.toggle_required(d, 2)[1]['required'], True)
        self.assertEqual(D.edit_cell(d, 1, 'arraySize', '5')[0]['arraySize'], 5)
        self.assertEqual(D.edit_cell(d, 77, 'name', 'z', setting_mode=True), d)
        self.assertEqual(D.edit_cell(d, 77, 'name', 'z')[3]['name'], 'z')

    def test_options(self):
        o = D.bit_set_size({'flagNames': ['a', '', 'c'], 'size': 3}, '5')
        self.assertEqual(o['flagNames'], ['a', 'Flag1', 'c', 'Flag3', 'Flag4'])
        self.assertEqual(D.bit_set_size({}, 0)['size'], 1)
        self.assertEqual(D.bit_set_flag_name({'flagNames': ['a']}, 2, 'z')['flagNames'], ['a', '', 'z'])
        self.assertEqual(D.bit_effective_size({'flagNames': ['a', 'b']}), 2)
        self.assertEqual(D.bit_effective_size({}), 8)
        self.assertEqual(D.key_type_options(['E', 'int'], ['C'], ['E']), ['int', 'E', 'C'])
        self.assertEqual(D.default_options_for_type('dictionary')['keyType'], 'int')
        self.assertEqual(D.default_options_for_type('voice_ref')['fieldName'], 'voices')
        self.assertEqual(D.default_options_for_type('int'), {})

    def test_dep_values(self):
        self.assertEqual(D.dependency_value_options('Bool', None)[0], {'value': 'true', 'label': 'True'})
        self.assertEqual(D.dependency_value_options('E', [{'value': 'A', 'label': 'A'}]), [{'value': 'A', 'label': 'A'}])
        self.assertEqual(D.add_dependency_value(['a'], 'b'), ['a', 'b'])
        self.assertEqual(D.add_dependency_value(['a'], 'a'), ['a'])
        self.assertEqual(D.add_dependency_value(['a'], ''), ['a'])
        self.assertEqual(D.remove_dependency_value(['a', 'b'], 'a'), ['b'])
        self.assertEqual(D.default_dep_values_for_parent({'type': 'bool'}), ['true'])
        d = base()
        self.assertEqual([f['name'] for f in D.parent_candidates(d, ['FadeID'], [])], ['flag', 'fade'])
        self.assertEqual([f['name'] for f in D.parent_candidates(d, ['FadeID'], [], exclude_id=1)], ['fade'])

    def test_message(self):
        self.assertEqual(D.format_save_message({'message': 'ok', 'sync': {'nodes_touched': 3}, 'error_detail': 'x'}, True),
                         'ok\n（既存シナリオの 3 個のサブグループへ反映）\n⚠ x')
        self.assertEqual(D.format_save_message({'message': 'ok', 'sync': {'nodes_touched': 3}}, False), 'ok')
        self.assertEqual(D.format_save_message({'error': 'bad'}, False), 'bad')


if __name__ == '__main__':
    unittest.main()
