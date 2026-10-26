"""core/node_utils.py と scenarioNodeUtils.js の差分テスト。"""
import copy
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from jscompare import norm, run_js_adapter  # noqa: E402
from scenario_editor.core import node_utils  # noqa: E402

MOD = 'scenarioNodeUtils'
# JS は "変更なしなら同じ参照" を返すので、unchanged フラグも一緒に取り出す
ADAPTER = """(m, a) => {
  const r = m.renumberDuplicateNodes(a.nodes, a.opts === undefined ? undefined : a.opts);
  return { ...r, same: r.nodes === a.nodes };
}"""


def n(id_, subgroups=None, **extra):
    data = {'roles': []}
    if subgroups is not None:
        data['subgroups'] = subgroups
    return {'id': id_, 'data': data, **extra}


class RenumberTest(unittest.TestCase):
    def check(self, cases):
        js = run_js_adapter(MOD, ADAPTER, cases)
        for a, jv in zip(cases, js):
            nodes = copy.deepcopy(a['nodes'])
            snapshot = copy.deepcopy(nodes)
            opts = a.get('opts')
            pv = node_utils.renumber_duplicate_nodes(nodes, **(opts or {}) if opts is not None else {}) \
                if opts is None or 'rekeySubgroups' not in opts \
                else node_utils.renumber_duplicate_nodes(nodes, rekey_subgroups=opts['rekeySubgroups'])
            same = pv['nodes'] is nodes
            with self.subTest(case=repr(a)[:300]):
                self.assertEqual(norm({**pv, 'nodes': pv['nodes']}), norm({k: v for k, v in jv.items() if k != 'same'}))
                self.assertEqual(same, jv['same'])
                self.assertEqual(nodes, snapshot, '入力を変更してはならない')

    def test_basic(self):
        cases = [
            {'nodes': []},
            {'nodes': None},
            {'nodes': [n('1'), n('2'), n('3')]},
            {'nodes': [n('1'), n('1')]},
            {'nodes': [n('5'), n('5'), n('5')]},
            {'nodes': [n('5'), n('6'), n('5')]},
            {'nodes': [n('5'), n('6'), n('7'), n('5'), n('5')]},
            {'nodes': [n(5), n('5')]},
            {'nodes': [n(5), n(5)]},
            {'nodes': [n('a'), n('a'), n('1'), n('1'), n('a')]},
            {'nodes': [n('1x'), n('1x')]},
            {'nodes': [n('007'), n('007'), n('8')]},
            {'nodes': [n('0'), n('0')]},
            {'nodes': [n('99999999999999999999'), n('99999999999999999999')]},
            {'nodes': [n('9007199254740990'), n('9007199254740990'), n('9007199254740991')]},
            {'nodes': [n('１'), n('１')]},
            {'nodes': [n('5\n'), n('5\n')]},
            {'nodes': [{'id': '3'}, {'id': '3'}]},
            {'nodes': [{'id': '3', 'data': None}, {'id': '3', 'data': None}]},
            {'nodes': [n('3', label='a'), n('3', label='b')]},
        ]
        for c in list(cases):
            cases.append({**c, 'opts': {'rekeySubgroups': True}})
            cases.append({**c, 'opts': {'rekeySubgroups': False}})
        self.check(cases)

    def test_rekey(self):
        sg = lambda *k: {x: {'nodes': [n(x)]} for x in k}  # noqa: E731
        cases = [
            {'nodes': [n('1', sg('1')), n('1', sg('1'))], 'opts': {'rekeySubgroups': True}},
            {'nodes': [n('1', sg('1', '2')), n('1', sg('1', '2', '3'))], 'opts': {'rekeySubgroups': True}},
            {'nodes': [n('1', sg('1')), n('1', sg('1', '2'))], 'opts': {'rekeySubgroups': False}},
            {'nodes': [n('2', sg('2')), n('2', sg('5')), n('2', sg('2', '3'))], 'opts': {'rekeySubgroups': True}},
            # 新IDのキーが既に subgroups に居る場合(上書き)
            {'nodes': [n('1', sg('1')), n('1', sg('1', '2'))], 'opts': {'rekeySubgroups': True}},
            {'nodes': [n('9', sg('9', '10', 'x')), n('9', sg('9', '10', 'x'))], 'opts': {'rekeySubgroups': True}},
            {'nodes': [n('1', {}), n('1', {})], 'opts': {'rekeySubgroups': True}},
            {'nodes': [n('1', None), n('1', None)], 'opts': {'rekeySubgroups': True}},
        ]
        self.check(cases)

    def test_random(self):
        rnd = random.Random(3)
        cases = []
        for _ in range(150):
            nodes = []
            for _ in range(rnd.randint(0, 8)):
                id_ = rnd.choice(['1', '2', '3', '4', '5', 'a', 'b', 3, '007', '10'])
                sg = None
                if rnd.random() < 0.6:
                    sg = {str(k): {'nodes': []} for k in rnd.sample(['1', '2', '3', '4', '5', '6', 'a', '10'], rnd.randint(0, 4))}
                nodes.append(n(id_, sg))
            cases.append({'nodes': nodes, 'opts': {'rekeySubgroups': rnd.random() < 0.5}})
        self.check(cases)

    def test_alias(self):
        self.assertIs(node_utils.renumber_duplicate_node, node_utils.renumber_duplicate_nodes)
        r = node_utils.renumber_duplicate_nodes([n('5'), n('5')])
        self.assertEqual(r['renamed'], [{'index': 1, 'from': '5', 'to': '6'}])
        self.assertEqual(r['skipped'], [])


if __name__ == '__main__':
    unittest.main()
