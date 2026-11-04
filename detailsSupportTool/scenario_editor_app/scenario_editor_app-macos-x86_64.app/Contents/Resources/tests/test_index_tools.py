"""core/index_tools.py と scenarioIndexTools.js の差分テスト。"""
import itertools
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from jscompare import norm, run_js_adapter  # noqa: E402
from scenario_editor.core import index_tools as it  # noqa: E402

MOD = 'scenarioIndexTools'
SCHEMAS = {
    'Say': {'fields': [{'name': 'text_id', 'type': 'text_list_index'}, {'name': 'who', 'type': 'string'}]},
    'Voice': {'fields': [{'name': 'voice_ref', 'type': 'voice_ref'}, {'name': 'n', 'type': 'int'}, {'name': 'ids', 'type': 'int[]'}]},
}


def mk_nodes():
    def role(uid, name, **vals):
        return {'uniqueId': uid, 'name': name, 'data': [{'name': k, 'value': v} for k, v in vals.items()]}
    return [
        {'id': '1', 'data': {'roles': [role('a', 'Say', text_id=3, who='x'), role('b', 'Voice', voice_ref=1, n=5)]}},
        {'id': '2', 'data': {'roles': [role('c', 'Say', text_id=4), role('d', 'Say', text_id=-1)]}},
        {'id': '3', 'data': {'roles': [role('e', 'Voice', voice_ref=7, n=2, ids=[1, 2, 'x', 3])]}},
        {'id': '4', 'data': {'roles': [role('f', 'Say', text_id=9)]}},
        {'id': '5'},
    ]


DOC = '\n'.join([
    '# ==== SUB:1 NODE:1 (a) ====', 'Say text_id=3 who="x"', 'Voice voice_ref=1 n=5',
    '# ==== SUB:1 NODE:2 ====', 'Say text_id=4', 'Say text_id=-1',
    '# ==== SUB:1 NODE:2/1 ====', 'Say text_id=11',
    '# ==== SUB:1 NODE:2/2 ====', 'Say text_id=12', 'Voice voice_ref=3 n=1 ids=[1, x, 2]',
    '# ==== SUB:1 NODE:3 ====', 'Say text_id=9', 'Voice voice_ref=8 n=7 # c',
])

OPT_SETS = [
    {'startNodeId': '1', 'mode': 'shift', 'delta': 2},
    {'startNodeId': '2', 'mode': 'shift', 'delta': -3},
    {'startNodeId': '2', 'mode': 'shift', 'delta': 1, 'includeStart': False},
    {'startNodeId': '2', 'endNodeId': '3', 'mode': 'shift', 'delta': 5, 'includeInt': True},
    {'startNodeId': '1', 'mode': 'shift', 'delta': -10},
    {'startNodeId': '1', 'mode': 'shift', 'delta': -10, 'skipNegative': False},
    {'startNodeId': '1', 'mode': 'shift', 'delta': 1.5},
    {'startNodeId': 'zz', 'mode': 'shift', 'delta': 1},
    {'startNodeId': '3', 'endNodeId': '1', 'mode': 'shift', 'delta': 1},
    {'startNodeId': '1', 'mode': 'sequence'},
    {'startNodeId': '1', 'mode': 'sequence', 'includeStart': True, 'step': 2},
    {'startNodeId': '2', 'mode': 'sequence', 'base': 100},
    {'startNodeId': '4', 'mode': 'sequence', 'includeInt': True},
    {'startNodeId': '5', 'mode': 'sequence'},
    {'startNodeId': '1', 'mode': 'sequence', 'base': 1.5},
    {'startNodeId': '1', 'mode': 'sequence', 'target': {'roleName': 'Say', 'fieldName': 'text_id'}, 'step': -2},
    {'startNodeId': '1', 'mode': 'shift', 'delta': 3, 'target': 'all'},
]


class GuiTest(unittest.TestCase):
    def test_collect(self):
        nodes = mk_nodes()
        cases = [{'nodes': nodes, 'schemas': SCHEMAS, 'o': {}}, {'nodes': nodes, 'schemas': SCHEMAS, 'o': {'includeInt': True}},
                 {'nodes': None, 'schemas': None, 'o': {}}]
        js = run_js_adapter(MOD, "(m, a) => m.collectIndexFields(a.nodes, a.schemas, a.o)", cases)
        for c, j in zip(cases, js):
            self.assertEqual(norm(it.collect_index_fields(c['nodes'], c['schemas'], c['o'])), norm(j))

    def test_plan_and_apply(self):
        nodes = mk_nodes()
        cases = [{'nodes': nodes, 'schemas': SCHEMAS, 'o': o} for o in OPT_SETS]
        js = run_js_adapter(MOD, "(m, a) => { const p = m.planIndexAdjust(a.nodes, a.schemas, a.o); return { p, applied: m.applyIndexChanges(a.nodes, p.changes) }; }", cases)
        for c, j in zip(cases, js):
            with self.subTest(o=c['o']):
                p = it.plan_index_adjust(c['nodes'], c['schemas'], c['o'])
                self.assertEqual(norm(p), norm(j['p']))
                self.assertEqual(norm(it.apply_index_changes(c['nodes'], p['changes'])), norm(j['applied']))


class DslTest(unittest.TestCase):
    def test_sections(self):
        cases = [DOC, '', 'no header', '# ==== SUB:1 NODE:1 ====\nx']
        js = run_js_adapter(MOD, "(m, a) => m.splitSections(a)", cases)
        for c, j in zip(cases, js):
            self.assertEqual(norm(it.split_sections(c)), norm(j))
        cur = [{'text': DOC, 'line': n} for n in range(0, 15)]
        js = run_js_adapter(MOD, "(m, a) => m.findSiblingSections(a.text, a.line)", cur)
        for c, j in zip(cur, js):
            self.assertEqual(norm(it.find_sibling_sections(c['text'], c['line'])), norm(j))

    def test_plan_apply(self):
        dsl_opts = []
        for line, o in itertools.product([0, 3, 6, 8, 11, 99], [
            {'mode': 'shift', 'delta': 2}, {'mode': 'shift', 'delta': -5}, {'mode': 'shift', 'delta': 1, 'includeStart': False},
            {'mode': 'sequence'}, {'mode': 'sequence', 'includeStart': True, 'step': 3}, {'mode': 'sequence', 'base': 50},
            {'mode': 'shift', 'delta': 1, 'includeInt': True}, {'mode': 'shift', 'delta': 1, 'endPathKey': '2'},
            {'mode': 'shift', 'delta': 1, 'endPathKey': 'nope'}, {'mode': 'shift', 'delta': 0.5},
            {'mode': 'sequence', 'target': {'roleName': 'Say', 'fieldName': 'text_id'}},
        ]):
            dsl_opts.append({'text': DOC, 'schemas': SCHEMAS, 'o': {**o, 'cursorLine': line}})
        js = run_js_adapter(MOD, "(m, a) => { const p = m.planIndexAdjustInDsl(a.text, a.schemas, a.o); return { p, text: m.applyIndexChangesToDsl(a.text, p.changes) }; }", dsl_opts)
        for c, j in zip(dsl_opts, js):
            with self.subTest(o=c['o']):
                p = it.plan_index_adjust_in_dsl(c['text'], c['schemas'], c['o'])
                self.assertEqual(norm(p), norm(j['p']))
                self.assertEqual(it.apply_index_changes_to_dsl(c['text'], p['changes']), j['text'])

    def test_collect_dsl(self):
        cases = [{'t': DOC, 'o': {}}, {'t': DOC, 'o': {'includeInt': True}}, {'t': '', 'o': {}}]
        js = run_js_adapter(MOD, "(m, a) => m.collectIndexFieldsInDsl(a.t, " + "%s" % "{}" + ", a.o)", cases)
        # schemas は JS 側へ渡す必要がある
        cases2 = [{'t': c['t'], 's': SCHEMAS, 'o': c['o']} for c in cases]
        js = run_js_adapter(MOD, "(m, a) => m.collectIndexFieldsInDsl(a.t, a.s, a.o)", cases2)
        for c, j in zip(cases2, js):
            self.assertEqual(norm(it.collect_index_fields_in_dsl(c['t'], c['s'], c['o'])), norm(j))


if __name__ == '__main__':
    unittest.main()
