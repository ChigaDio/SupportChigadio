import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scenario_editor.core import event_ops as E  # noqa: E402

EVS = [{'id': '1', 'name': 'Alpha', 'subEvents': [{'subId': 1, 'name': 'Intro'}]}, {'id': '10', 'name': 'Beta', 'subEvents': []},
       {'id': 'x', 'name': 'Gamma'}]


class T(unittest.TestCase):
    def test_id(self):
        self.assertEqual(E.next_event_id(EVS), '11')
        self.assertEqual(E.next_event_id([]), '1')
        self.assertEqual(E.next_event_id([{'id': 'a'}]), '1')

    def test_filter(self):
        self.assertEqual(len(E.filter_events(EVS, '')), 3)
        self.assertEqual([e['id'] for e in E.filter_events(EVS, 'ALPHA')], ['1'])
        self.assertEqual([e['id'] for e in E.filter_events(EVS, 'intro')], ['1'])
        self.assertEqual([e['id'] for e in E.filter_events(EVS, '1')], ['1', '10'])

    def test_ops(self):
        e = E.add_event(EVS, {'id': '11', 'name': 'N', 'description': ''})
        self.assertEqual(e[-1]['subEvents'], [])
        e = E.add_sub(e, '10', {'subId': 5, 'name': 'S'})
        e = E.edit_sub(e, '10', 5, 'S2', 'd')
        self.assertEqual(e[1]['subEvents'][0], {'subId': 5, 'name': 'S2', 'description': 'd'})
        e = E.delete_sub(e, '10', 5)
        self.assertEqual(e[1]['subEvents'], [])
        e = E.edit_event(e, '1', 'A2', 'dd')
        self.assertEqual(e[0]['name'], 'A2')
        self.assertEqual(len(E.delete_event(e, '1')), 3)

    def test_migrate(self):
        self.assertEqual(E.migrate_message({'migrated': [1], 'failed': [2]})[1], 'warning')
        self.assertEqual(E.migrate_message({'migrated': [1, 2]})[0], '2件のイベントを新しい形式に更新しました')
        self.assertIn('最新形式', E.migrate_message({})[0])


if __name__ == '__main__':
    unittest.main()
