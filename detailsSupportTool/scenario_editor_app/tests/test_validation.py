"""core/validation.py と scenarioValidation.js の差分テスト。"""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from jscompare import norm, run_js_adapter  # noqa: E402
from scenario_editor.core import validation  # noqa: E402

MOD = 'scenarioValidation'
ADAPTER = """(m, a) => {
  const ctx = { ...(a.ctx || {}) };
  if (Array.isArray(ctx.roleNames)) ctx.roleNames = new Set(ctx.roleNames);
  return m.validateGraph(a.nodes, a.edges, a.noctx ? undefined : ctx);
}"""

SCHEMAS = {
    'Say': {'fields': [{'name': 'text'}, {'name': 'speed'}]},
    'Move': {'fields': [{'name': f'f{i}'} for i in range(9)]},
    'Bad': {'fields': 'nope'},
}


def role(uid, name='Say', names=None):
    return {'uniqueId': uid, 'name': name, 'data': [{'name': n, 'value': 1} for n in (names or [])]}


def node(id_, roles=None, subgroups=None):
    data = {'roles': roles if roles is not None else []}
    if subgroups is not None:
        data['subgroups'] = subgroups
    return {'id': id_, 'data': data}


class ValidateGraphTest(unittest.TestCase):
    def check(self, cases):
        js = run_js_adapter(MOD, ADAPTER, cases)
        for a, jv in zip(cases, js):
            ctx = dict(a.get('ctx') or {})
            if isinstance(ctx.get('roleNames'), list):
                ctx['roleNames'] = set(ctx['roleNames'])
            pv = validation.validate_graph(a['nodes'], a['edges'], None if a.get('noctx') else ctx)
            with self.subTest(case=repr(a)[:400]):
                self.assertEqual(norm(pv), norm(jv))
                # JS のオブジェクトの列挙順 (整数様のキーが先) まで一致する
                self.assertEqual(list(pv['byNode'].keys()), list(jv['byNode'].keys()))

    def test_each_code(self):
        ok = role('u1', 'Say', ['text', 'speed'])
        cases = [
            {'nodes': [], 'edges': []},
            {'nodes': [], 'edges': None},
            {'nodes': [node('1', [ok])], 'edges': [], 'noctx': True},
            {'nodes': [node('1', [ok])], 'edges': [], 'ctx': {'roleSchemas': SCHEMAS}},
            # dup-node-id / non-numeric-id
            {'nodes': [node('1', [ok]), node('1', [role('u2')])], 'edges': []},
            {'nodes': [node('a', [ok]), node('a', [ok]), node('a', [ok])], 'edges': []},
            {'nodes': [node(5, [ok]), node('5', [role('u2')])], 'edges': []},
            {'nodes': [node('1x', [ok]), node('', [ok]), node('-1', [ok]), node('1.5', [ok]), node('１', [ok]),
                       node('5\n', [ok])], 'edges': []},
            {'nodes': [{'data': {'roles': [ok]}}], 'edges': []},  # id 欠落 (undefined)。null と undefined は Python では区別できない
            # uniqueId
            {'nodes': [node('1', [role(None), role(''), {'name': 'X', 'data': []}, role(0), role(False)])], 'edges': []},
            {'nodes': [node('1', [role('a'), role('a'), role('a'), role('b'), role('b')])], 'edges': []},
            {'nodes': [node('1', [role(1), role('1')])], 'edges': []},
            # role-undefined
            {'nodes': [node('1', [ok, role('u2', 'Gone')])], 'edges': [], 'ctx': {'roleNames': ['Say']}},
            {'nodes': [node('1', [ok, role('u2', 'Gone')])], 'edges': [], 'ctx': {'roleNames': []}},
            {'nodes': [node('1', [ok, role('u2', 'Gone')])], 'edges': [], 'ctx': {'roleNames': None}},
            # role-undefined のときはフィールド検査をしない
            {'nodes': [node('1', [role('u1', 'Say', ['zzz'])])], 'edges': [],
             'ctx': {'roleNames': ['Move'], 'roleSchemas': SCHEMAS}},
            # fields missing / extra
            {'nodes': [node('1', [role('u1', 'Say', ['text'])])], 'edges': [], 'ctx': {'roleSchemas': SCHEMAS}},
            {'nodes': [node('1', [role('u1', 'Say', ['text', 'speed', 'x', 'y'])])], 'edges': [], 'ctx': {'roleSchemas': SCHEMAS}},
            {'nodes': [node('1', [role('u1', 'Move', [])])], 'edges': [], 'ctx': {'roleSchemas': SCHEMAS}},
            {'nodes': [node('1', [role('u1', 'Move', ['f0', 'q0', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6']),
                                  role('u2', 'Move', [f'q{i}' for i in range(5)])])], 'edges': [],
             'ctx': {'roleSchemas': SCHEMAS}},
            {'nodes': [node('1', [role('u1', 'Bad', ['x']), role('u2', 'Unknown', ['x'])])], 'edges': [],
             'ctx': {'roleSchemas': SCHEMAS}},
            {'nodes': [node('1', [{'uniqueId': 'u', 'name': 'Say', 'data': [None, {'value': 1}, {'name': 'text'}, {'name': None}]}])],
             'edges': [], 'ctx': {'roleSchemas': SCHEMAS}},
            {'nodes': [node('1', [{'uniqueId': 'u', 'name': 'Say'}])], 'edges': [], 'ctx': {'roleSchemas': SCHEMAS}},
            {'nodes': [node('1', [{'uniqueId': 'u', 'name': 'Say', 'data': [{'name': 'text'}, {'name': 'text'}]}])],
             'edges': [], 'ctx': {'roleSchemas': {'Say': {'fields': [{'name': 'text'}, {'type': 'int'}, {'name': 'text'}]}}}},
            # empty-node
            {'nodes': [node('1', [])], 'edges': []},
            {'nodes': [node('1', [])], 'edges': [], 'ctx': {'isSub': True}},
            {'nodes': [node('1', [], {'1': {'nodes': [node('1')]}})], 'edges': []},
            {'nodes': [node('1', [], {'1': {'nodes': [node('1')]}})], 'edges': [], 'ctx': {'isSub': True}},
            {'nodes': [node('1', [], {'1': {'nodes': []}, '2': None, '3': {}})], 'edges': []},
            {'nodes': [{'id': '1'}, {'id': '2', 'data': None}, {'id': '3', 'data': {}}], 'edges': []},
            # dangling-edge
            {'nodes': [node('1', [ok]), node('2', [ok])], 'edges': [{'source': '1', 'target': '2'}]},
            {'nodes': [node('1', [ok]), node('2', [ok])], 'edges': [{'source': '1', 'target': '3'}, {'source': 9, 'target': 1},
                                                                    {'source': '1'}, {}]},
            {'nodes': [node(1, [ok]), node('2', [ok])], 'edges': [{'source': 1, 'target': 2}]},
            # byNode の列挙順 (整数様キー)
            {'nodes': [node('10'), node('2'), node('x'), node('1'), node('007')], 'edges': []},
        ]
        self.check(cases)

    def test_random(self):
        rnd = random.Random(7)
        names = ['text', 'speed', 'q', 'f0', 'f1']
        cases = []
        for _ in range(150):
            nodes = []
            for _ in range(rnd.randint(0, 6)):
                roles = []
                for _ in range(rnd.randint(0, 3)):
                    uid = rnd.choice(['a', 'b', 'c', None, '', 'd', 1, 2])
                    rn = rnd.choice(['Say', 'Move', 'Gone'])
                    roles.append(role(uid, rn, rnd.sample(names, rnd.randint(0, 4))))
                sub = {'1': {'nodes': [node('1')] * rnd.randint(0, 1)}} if rnd.random() < 0.3 else None
                nodes.append(node(rnd.choice(['1', '2', '3', 'x', '10', 4, 'y']), roles, sub))
            edges = [{'source': rnd.choice(['1', '2', '9', 3]), 'target': rnd.choice(['1', '2', '3', 'x'])}
                     for _ in range(rnd.randint(0, 3))]
            ctx = {'isSub': rnd.random() < 0.5, 'roleSchemas': SCHEMAS,
                   'roleNames': rnd.choice([None, ['Say', 'Move'], ['Say'], []])}
            cases.append({'nodes': nodes, 'edges': edges, 'ctx': ctx})
        self.check(cases)

    def test_messages(self):
        r = validation.validate_graph([node('a', [role(None, 'Say')])], [{'source': 'a', 'target': 'zz'}])
        msgs = [i['message'] for i in r['byNode']['a']] + [i['message'] for i in r['edgeIssues']]
        self.assertIn('ID "a" は数値ではないため、出力では 0 になります', msgs)
        self.assertIn('Role「Say」に uniqueId がありません（データを保存できません）', msgs)
        self.assertIn('接続 a → zz の端が存在しません', msgs)
        self.assertEqual(r['counts'], {'error': 1, 'warn': 2, 'info': 0})
        self.assertEqual(r['total'], 3)


class WorstLevelTest(unittest.TestCase):
    def test_worst_level(self):
        L = lambda *ls: [{'level': x} for x in ls]  # noqa: E731
        cases = [[None], [[]], [L('info')], [L('info', 'warn')], [L('warn', 'error', 'info')], [L('error')],
                 [L('warn', 'warn')]]
        js = run_js_adapter(MOD, "(m, a) => m.worstLevel(a[0])", cases)
        for a, jv in zip(cases, js):
            with self.subTest(args=a):
                self.assertEqual(validation.worst_level(a[0]), jv)


if __name__ == '__main__':
    unittest.main()
