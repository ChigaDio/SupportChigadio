"""core/transition_ops.py の検証。

- ScenarioEventTransition.js から切り出した原文(tests/gen_transition_harness.py)との差分テスト:
  色分け / withFieldTypes / 採番 / CSV / 全体編集系 (parse/build/apply/merge)
- GUI 操作系(ノード追加・削除・移動・Undo など)は、JS のコードを読んで期待値を明示したテスト
"""
import copy
import os
import random
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import gen_transition_harness  # noqa: E402
from jscompare import norm, run_js_adapter  # noqa: E402
from scenario_editor.core import dsl, transition_ops as T  # noqa: E402
from test_dsl import CLASS_SCHEMAS, SCHEMAS  # noqa: E402

gen_transition_harness.build()
MOD = '_gen_transition'

SETTING_SCHEMA = {'fields': [
    {'name': 'is_wait_key', 'type': 'bool', 'required': True},
    {'name': 'delay', 'type': 'float', 'required': True},
    {'name': 'mode', 'type': 'SettingMode', 'options': ['SettingMode.A', 'SettingMode.B']},
]}
SETTING_DEFAULTS = [
    {'name': 'is_wait_key', 'type': 'bool', 'value': False},
    {'name': 'delay', 'type': 'float', 'value': 0},
    {'name': 'mode', 'type': 'SettingMode', 'value': 'SettingMode.A'},
]


_UID_RE = re.compile(r'^\w+?_\d{10,}_\d+_[a-z0-9]+$')


def mask(x):
    """新規 Role の uniqueId(時刻+乱数)は毎回変わるので、形だけ比べる。"""
    if isinstance(x, dict):
        return {k: mask(v) for k, v in x.items()}
    if isinstance(x, list):
        return [mask(v) for v in x]
    if isinstance(x, str) and _UID_RE.match(x):
        return 'UID'
    return x


def roles_from(text, existing=None):
    return dsl.compile_document(text, SCHEMAS, existing or [], CLASS_SCHEMAS)['roles']


def node(id_, desc='', roles=None, subgroups=None, setting=None, **kw):
    d = {'label': id_, 'description': desc, 'roles': roles or [], 'subgroups': subgroups or {}}
    if setting is not None:
        d['subGroupSetting'] = setting
    return {'id': id_, 'type': 'customGroup', 'position': {'x': 1, 'y': 2}, 'data': d, 'draggable': True, **kw}


def base_trees():
    say = roles_from('Say text="hello"\nWait time=1.5')
    say2 = roles_from('Say text="inner" speed=2')
    sub_nodes = [node('1', 'in-a', roles_from('Wait time=3')), node('2', '', say2)]
    return {
        '1': {'nodes': [node('1', 'intro', say, {'1': {'nodes': sub_nodes, 'edges': [{'source': '1', 'target': '2', 'id': '1-2'}]}}),
                        node('2', 'second\nline', [])],
              'edges': [{'source': '1', 'target': '2', 'id': '1-2'}]},
        '2': {'nodes': [node('1', 'other', roles_from('Say text="x"'))], 'edges': []},
    }


EDIT_ADAPTER = """(m, a) => {
  const e = m.mkEdit({ ...a.ctx, currentTabData: a.ctx.currentTabData });
  const trees = JSON.parse(JSON.stringify(a.trees));
  const targets = {};
  const lines = [];
  for (const sid of a.sids) {
    if (a.merge) e.mergeLocalRoleDataIntoTree(trees[sid], sid);
    lines.push(...e.buildEditLinesForSub(sid, trees[sid], targets));
  }
  let text = lines.join('\\n');
  for (const [o, n] of a.edits || []) text = text.split(o).length > 1 ? text.replace(o, () => n) : text;
  if (a.rawText !== undefined && a.rawText !== null) text = a.rawText;
  const sections = e.parseEditSections(text);
  const norm = (r) => ({ ...r, touchedSubIds: Array.from(r.touchedSubIds).sort() });
  const dry = norm(e.applyEditSections(sections, { current: trees }, { current: targets }, a.allow, true));
  const treesAfterDry = JSON.parse(JSON.stringify(trees));
  const real = norm(e.applyEditSections(sections, { current: trees }, { current: targets }, a.allow, false));
  return { text, sections, dry, real, trees, treesAfterDry, total: e.summarizeChanges(dry.changes) };
}"""


def py_edit(a):
    ctx_d = a['ctx']
    ctx = T.EditContext(
        role_form_schemas=ctx_d.get('roleFormSchemas'), class_data_schemas=ctx_d.get('classDataSchemas'),
        setting_schema=ctx_d.get('subGroupSettingSchema'), setting_defaults=ctx_d.get('subGroupSettingDefaults'),
        sub_id=ctx_d.get('subId'), current_tab_nodes=(ctx_d.get('currentTabData') or {}).get('nodes'),
        is_sub=ctx_d.get('isSub', False), parent_id=ctx_d.get('parentId'), role_data_cache=ctx_d.get('roleDataCache'))
    trees = copy.deepcopy(a['trees'])
    targets = {}
    lines = []
    for sid in a['sids']:
        if a.get('merge'):
            T.merge_local_role_data_into_tree(trees[sid], sid, ctx)
        lines.extend(T.build_edit_lines_for_sub(sid, trees[sid], targets, ctx))
    text = '\n'.join(lines)
    for o, n in a.get('edits') or []:
        if o in text:
            text = text.replace(o, n, 1)
    if a.get('rawText') is not None:
        text = a['rawText']
    sections = T.parse_edit_sections(text)
    dry = T.apply_edit_sections(sections, trees, targets, a['allow'], ctx, dry_run=True)
    after_dry = copy.deepcopy(trees)
    real = T.apply_edit_sections(sections, trees, targets, a['allow'], ctx, dry_run=False)
    for r in (dry, real):
        r['touchedSubIds'] = sorted(r['touchedSubIds'])
    return {'text': text, 'sections': sections, 'dry': dry, 'real': real, 'trees': trees,
            'treesAfterDry': after_dry, 'total': T.summarize_changes(dry['changes'])}


class PureFnTest(unittest.TestCase):
    def test_hash_and_tint(self):
        strs = ['', '1', '1/2', 'abc', 'あいう', '😀', 'x' * 200, '1/2/3', '99999999999']
        js = run_js_adapter(MOD, "(m,a)=>({h:m.hashHue(a[0]), t:m.getNodeTint(a[0],a[1])})",
                            [[s, k] for s in strs for k in (None, 'none', 'red', 'pink', 'bogus')])
        i = 0
        for s in strs:
            for k in (None, 'none', 'red', 'pink', 'bogus'):
                self.assertEqual(T.hash_hue(s), js[i]['h'], s)
                self.assertEqual(norm(T.get_node_tint(s, k)), norm(js[i]['t']), (s, k))
                i += 1

    def test_presets_same(self):
        js = run_js_adapter(MOD, "(m,a)=>m.NODE_COLOR_PRESETS", [0])[0]
        self.assertEqual(js, T.NODE_COLOR_PRESETS)

    def test_with_field_types(self):
        schema = {'fields': [{'name': 'a', 'type': 'int'}, {'name': 'b', 'type': 'string'}, {'name': '', 'type': 'x'}, {'name': 'c'}]}
        fd = [
            [{'name': 'a', 'value': 1, 'arraySize': 0}, {'name': 'b', 'value': 'x', 'type': 'keep'}, {'name': 'zz', 'value': 1},
             {'name': 'c', 'value': 2}, None, 5, {'value': 3}, {'name': 'a', 'value': None}],
            [], None, 'str', [{'name': 'a'}],
        ]
        cases = [[f, s] for f in fd for s in (schema, None, {}, {'fields': 'x'}, {'fields': []})]
        js = run_js_adapter(MOD, "(m,a)=>m.withFieldTypes(a[0],a[1])", cases)
        for c, jv in zip(cases, js):
            pv = T.with_field_types(copy.deepcopy(c[0]), c[1])
            self.assertEqual(norm(pv), norm(jv), repr(c))
        out = T.with_field_types([{'value': 1, 'name': 'a'}], schema)
        self.assertEqual(list(out[0].keys()), ['value', 'name', 'type'])

    def test_next_node_id(self):
        cases = [[], [{'id': '1'}], [{'id': '3'}, {'id': '10'}], [{'id': 'a'}], [{'id': '5x'}, {'id': 'b'}],
                 [{'id': ' 7'}], [{'id': '-3'}], [{'id': '0'}], [{'id': 4}], [{'id': '2'}, {'id': 'x'}, {'id': '9'}]]
        js = run_js_adapter(MOD, "(m,a)=>m.getNextNodeId(a)", cases)
        for c, jv in zip(cases, js):
            self.assertEqual(T.get_next_node_id(c), jv, c)


class CsvTest(unittest.TestCase):
    TEXTS = [
        '', 'a', 'type,id\r\nnode,1', 'type,id,description,roleIds,x,y,source,target,sourceHandle,targetHandle\r\n'
        'node,1,"line1\nline2, with ""quote""",1;2;,10.5,-3,,,,\r\nnode,2,,,abc,,,,,\r\nedge,,,,,,1,2,h1,\r\nedge,e,,,,,2,9,,\r\n'
        'node,,x,,,,,,,\r\nbogus,1\r\n\r\n',
        'id,type\n1,node\n2,node\n', ' type , id \nnode,A\n', 'type,id\nnode,A,extra,cols\n', '"unterminated,1\n',
        'type,id,x,y\nnode,1,1e3,.5\nnode,2,+7,-0\nnode,3,12abc,Infinity\n',
    ]

    def test_parse_csv(self):
        js = run_js_adapter(MOD, "(m,a)=>m.parseCsv(a)", self.TEXTS)
        for t, jv in zip(self.TEXTS, js):
            self.assertEqual(T.parse_csv(t), jv, repr(t))

    def test_parse_to_tab(self):
        texts = [t for t in self.TEXTS if 'Infinity' not in t]
        js = run_js_adapter(MOD, "(m,a)=>m.parseCsvToTabData(a)", texts)
        for t, jv in zip(texts, js):
            self.assertEqual(norm(T.parse_csv_to_tab_data(t)), norm(jv), repr(t))

    def test_export_roundtrip(self):
        trees = base_trees()['1']
        trees['nodes'][1]['data']['description'] = 'a,b\n"c"'
        trees['nodes'][0]['data']['roles'] = [{'roleId': 5, 'uniqueId': 'u'}, {'id': 7}, {}]
        trees['edges'].append({'source': '2', 'target': '1', 'sourceHandle': 'h'})
        js = run_js_adapter(MOD, "(m,a)=>({rows:m.exportRows(a), csv:m.rowsToCsv(m.exportRows(a))})", [trees])[0]
        self.assertEqual(norm(T.tab_to_csv_rows(trees)), norm(js['rows']))
        self.assertEqual(T.tab_to_csv(trees), js['csv'])
        back = T.parse_csv_to_tab_data(T.tab_to_csv(trees))
        self.assertEqual([n['id'] for n in back['nodes']], ['1', '2'])
        self.assertEqual(back['nodes'][1]['data']['description'], 'a,b\n"c"')
        self.assertEqual(len(back['edges']), 2)

    def test_parse_float(self):
        for s, want in [('12abc', 12), ('', None), ('.5', 0.5), ('1e3', 1000), (' 5', 5), ('-', None), ('+7', 7), ('1.', 1)]:
            self.assertEqual(T.js_parse_float(s), want, s)


class EditSectionsTest(unittest.TestCase):
    def ctx(self, **kw):
        c = {'roleFormSchemas': SCHEMAS, 'classDataSchemas': CLASS_SCHEMAS, 'subGroupSettingSchema': SETTING_SCHEMA,
             'subGroupSettingDefaults': SETTING_DEFAULTS, 'subId': '1'}
        c.update(kw)
        return c

    def run_cases(self, cases):
        js = run_js_adapter(MOD, EDIT_ADAPTER, cases)
        for a, jv in zip(cases, js):
            pv = py_edit(a)
            with self.subTest(case=repr({k: v for k, v in a.items() if k not in ('trees', 'ctx')})[:200]):
                self.assertEqual(norm(pv['text']), norm(jv['text']))
                self.assertEqual(norm(pv['sections']), norm(jv['sections']))
                for k in ('dry', 'real', 'trees', 'treesAfterDry', 'total'):
                    self.assertEqual(mask(norm(pv[k])), mask(norm(jv[k])), k)

    def case(self, edits=(), allow=False, ctx=None, trees=None, sids=('1', '2'), **kw):
        return {'trees': trees or base_trees(), 'ctx': ctx or self.ctx(), 'sids': list(sids),
                'edits': [list(e) for e in edits], 'allow': allow, **kw}

    def test_basic(self):
        cases = [
            self.case(),
            self.case(edits=[('text="hello"', 'text="bye"')]),
            self.case(edits=[('Wait time=3', 'Wait time=4\nSay text="added"')]),
            self.case(edits=[('Wait time=3', '')]),
            self.case(edits=[('Wait time=3', 'Nope a=1')]),
            self.case(edits=[('Wait time=3', 'Say text=')]),
            self.case(edits=[('text="x"', 'text="y"')], sids=('2',)),
            self.case(edits=[('Say text="inner" speed=2', 'Say text="inner" speed=9')], sids=('1',)),
        ]
        self.run_cases(cases)

    def test_no_setting_schema(self):
        ctx = self.ctx(subGroupSettingSchema=None, subGroupSettingDefaults=[])
        self.run_cases([self.case(ctx=ctx), self.case(ctx=ctx, edits=[('text="hello"', 'text="z"')])])

    def test_setting_lines(self):
        trees = base_trees()
        trees['1']['nodes'][0]['data']['subGroupSetting'] = [{'name': 'is_wait_key', 'type': 'bool', 'value': True},
                                                              {'name': 'delay', 'type': 'float', 'value': 2.5}]
        self.run_cases([
            self.case(trees=trees),
            self.case(trees=trees, edits=[('==== SUB:1 NODE:1 (intro) ====', '==== SUB:1 NODE:1 (intro) ====\n#@ is_wait_key=false delay=1')]),
            self.case(trees=trees, edits=[('==== SUB:1 NODE:2 (second\nline) ====', 'x')]),
            self.case(trees=trees, edits=[('#@ ', '#@ bogus=1 ')]),
            self.case(trees=trees, edits=[('#@ ', '#@ delay="abc" ')]),
        ])

    def test_new_groups(self):
        foot = '# 例: 新しいグループを追加したい場合は'
        new_top = '# ==== SUB:1 NODE:7 (new) ====\n#@ is_wait_key=true\nSay text="n"\n\n'
        new_nested = '# ==== SUB:1 NODE:9/3 ====\nWait time=1\n\n'
        new_deep = '# ==== SUB:1 NODE:1/5/6 ====\nSay text="deep"\n\n'
        unknown_sub = '# ==== SUB:9 NODE:1 ====\nSay text="u"\n\n'
        cases = []
        for allow in (False, True):
            for ins in (new_top, new_nested, new_deep, unknown_sub, new_top + new_nested + new_deep):
                cases.append(self.case(edits=[(foot, ins + foot)], allow=allow))
        cases.append(self.case(edits=[(foot, new_top + 'Bad line here\n' + foot)], allow=True))
        self.run_cases(cases)

    def test_reorder_sections(self):
        a = self.case(trees=base_trees(), sids=('1',))
        text = py_edit(a)['text']
        head, *secs = text.split('# ==== ')
        by_path = {s_.split(' ')[0] + ' ' + s_.split(' ')[1]: s_ for s_ in secs}
        n1 = next(v for k, v in by_path.items() if k.endswith('NODE:1'))
        n2 = next(v for k, v in by_path.items() if k.endswith('NODE:2'))
        rest = [v for v in secs if v is not n1 and v is not n2]
        # ノード 2 のセクションを 1 の前へ移動 (見出し単位の並べ替え)
        reordered = head + ''.join('# ==== ' + v for v in [n2, n1, *rest])
        self.run_cases([dict(a, rawText=reordered, allow=False), dict(a, rawText=reordered, allow=True)])
        r = py_edit(dict(a, rawText=reordered, allow=False))
        # 元の JS も同じ挙動 (差分テストで一致済み): 既存ノードは targets から直接引かれるため並びは変わらない。
        # ensureAllEditNodePath 内の「出現順に積み直す」処理が働くのは、targets に無い見出しのときだけ。
        # (コメントは「並び順がテキストに追従」と主張しているが、実際は追従しない。docs/PORTING_GAPS.md 参照)
        self.assertEqual([n['id'] for n in r['trees']['1']['nodes']], ['1', '2'])

    def test_raw_texts(self):
        crlf = '# ==== SUB:1 NODE:1 (intro) ====\r\nSay text="crlf"\r\n\r\n# ==== SUB:1 NODE:2 ====\r\n'
        raws = [
            '', 'garbage', crlf, '# ==== SUB:1 NODE:1 ====', '#====SUB:1 NODE:1====\nSay text="t"',
            '# ====  SUB:1   NODE:1  extra words ====  \nSay text="t"', '# ==== SUB:1 NODE:1 ==== trailing',
            '# 例: x\n# ==== SUB:1 NODE:1 ====\n# 例：y\nSay text="q"\n',
            '# ==== SUB:1 NODE:1/1 ====\nWait time=8\n# ==== SUB:1 NODE:1 ====\nSay text="parent"\n',
        ]
        self.run_cases([self.case(rawText=r, allow=al) for r in raws for al in (False, True)])

    def test_merge_local(self):
        trees = base_trees()
        # ローカル(画面)側: 同じツリーをベースに、Role の値を変え、ローカルだけの Role を足し、サブグループ設定を持たせる
        local = copy.deepcopy(trees['1']['nodes'])
        r0 = local[0]['data']['roles'][0]
        r0['data'] = [{'name': 'text', 'type': 'string', 'value': 'LOCAL'}]
        local[0]['data']['roles'].append({'uniqueId': 'only-local', 'name': 'Wait', 'data': [{'name': 'time', 'type': 'float', 'value': 9}]})
        local[0]['data']['subGroupSetting'] = [{'name': 'is_wait_key', 'type': 'bool', 'value': True}]
        local[0]['data']['subgroups']['1']['nodes'][1]['data']['roles'][0]['data'] = [{'name': 'text', 'type': 'string', 'value': 'LOCAL-IN'}]
        cache = {'1/1': {js: [{'name': 'time', 'type': 'float', 'value': 77}]
                         for js in [str(trees['1']['nodes'][0]['data']['subgroups']['1']['nodes'][0]['data']['roles'][0]['uniqueId'])]}}
        cache0 = {'1': {str(r0['uniqueId']): [{'name': 'text', 'type': 'string', 'value': 'CACHED'}]}}
        sub_tab_nodes = copy.deepcopy(trees['1']['nodes'][0]['data']['subgroups']['1']['nodes'])
        sub_tab_nodes[0]['data']['roles'][0]['data'] = [{'name': 'time', 'type': 'float', 'value': 123}]
        cases = []
        for ctx in (
            self.ctx(currentTabData={'nodes': local}),
            self.ctx(currentTabData={'nodes': local}, roleDataCache=cache0),
            self.ctx(currentTabData={'nodes': local}, subId='2'),
            self.ctx(currentTabData={'nodes': []}),
            self.ctx(currentTabData=None),
            self.ctx(currentTabData={'nodes': sub_tab_nodes}, isSub=True, parentId='1', roleDataCache=cache),
            self.ctx(currentTabData={'nodes': sub_tab_nodes}, isSub=True, parentId=None),
        ):
            cases.append(self.case(ctx=ctx, merge=True))
        self.run_cases(cases)

    def test_diagnostics_and_helpers(self):
        a = self.case(edits=[('Wait time=3', 'Nope a=1')], allow=False)
        r = py_edit(a)
        self.assertTrue(r['dry']['diagnostics'])
        self.assertEqual(r['total'], 0)
        mine, foreign = T.split_sections_for_sub('# ==== SUB:1 NODE:1 ====\nx\n# ==== SUB:2 NODE:1 ====\ny', 1)
        self.assertEqual(len(mine), 1)
        self.assertIn('別Subの見出し', T.foreign_section_diagnostics(foreign)[0]['message'])


class GraphOpsTest(unittest.TestCase):
    def td(self):
        return {'main': {'nodes': [node('1', 'a'), node('2', 'b'), node('5', 'c')],
                         'edges': [{'source': '1', 'target': '2', 'id': '1-2'}, {'source': '2', 'target': '5', 'id': '2-5'}]}}

    def test_add_delete(self):
        td = self.td()
        td2, nid = T.add_node(td, 'main', False, None, '  desc  ', SETTING_SCHEMA, SETTING_DEFAULTS)
        self.assertEqual(nid, '6')
        n = td2['main']['nodes'][-1]
        self.assertEqual(n['data']['description'], 'desc')
        self.assertEqual(n['data']['label'], '6')
        self.assertEqual(n['type'], 'customGroup')
        self.assertEqual(n['data']['subGroupSetting'], SETTING_DEFAULTS)
        self.assertIsNot(n['data']['subGroupSetting'][0], SETTING_DEFAULTS[0])
        self.assertEqual(len(td['main']['nodes']), 3, '元は不変')
        td3, nid = T.add_node({'subgroup-1': {'nodes': [], 'edges': []}}, 'subgroup-1', True, '1')
        self.assertEqual(td3['subgroup-1']['nodes'][0]['data']['label'], 'Group: 1 / Sub: 1')
        self.assertNotIn('subGroupSetting', td3['subgroup-1']['nodes'][0]['data'])
        td4 = T.delete_node(td, 'main', '2')
        self.assertEqual([n['id'] for n in td4['main']['nodes']], ['1', '5'])
        self.assertEqual(td4['main']['edges'], [])

    def test_paste(self):
        td = self.td()
        copied = node('1', 'a', roles_from('Say text="a"'), {'x': {}})
        td2, nid = T.paste_node(td, 'main', copied, False, None, now_ms=1000)
        n = td2['main']['nodes'][-1]
        self.assertEqual((nid, n['id'], n['data']['subgroups']), ('6', '6', {}))
        self.assertEqual(n['data']['roles'][0]['uniqueId'], '1000-' + str(copied['data']['roles'][0]['uniqueId']))
        td3, _ = T.paste_node({'subgroup-9': {'nodes': [], 'edges': []}}, 'subgroup-9', copied, True, '9', 5)
        self.assertEqual(td3['subgroup-9']['nodes'][0]['data']['label'], 'Group: 9 / Sub: 1')
        self.assertTrue(td3['subgroup-9']['nodes'][0]['data']['isSubGroup'])

    def test_edit_node(self):
        td = self.td()
        out, err = T.edit_node(td, 'main', '2', '5', 'x', False, None)
        self.assertEqual(err, 'IDが重複しています')
        self.assertIs(out, td)
        out, err = T.edit_node(td, 'main', '2', ' 9 ', ' new ', False, None)
        self.assertIsNone(err)
        self.assertEqual([n['id'] for n in out['main']['nodes']], ['1', '9', '5'])
        self.assertEqual(out['main']['nodes'][1]['data']['description'], 'new')
        self.assertEqual([(e['source'], e['target'], e['id']) for e in out['main']['edges']], [('1', '9', '1-9'), ('9', '5', '9-5')])
        out, _ = T.edit_node(td, 'main', '1', '', 'd', True, '3')
        self.assertEqual(out['main']['nodes'][0]['id'], '1')
        self.assertEqual(out['main']['nodes'][0]['data']['label'], 'Group: 3 / Sub: 1')

    def test_reorder(self):
        td = self.td()
        self.assertIsNone(T.reorder_nodes(td, 'main', 0, -1))
        self.assertIsNone(T.reorder_nodes(td, 'main', 2, 3))
        self.assertEqual([n['id'] for n in T.reorder_nodes(td, 'main', 0, 1)['main']['nodes']], ['2', '1', '5'])
        self.assertEqual([n['id'] for n in T.reorder_by_id(td, 'main', '1', '5')['main']['nodes']], ['2', '5', '1'])
        self.assertEqual([n['id'] for n in T.reorder_by_id(td, 'main', '5', '1')['main']['nodes']], ['5', '1', '2'])
        self.assertIsNone(T.reorder_by_id(td, 'main', 'x', '1'))

    def test_roles(self):
        td = self.td()
        r = {'uniqueId': 'u1', 'name': 'Say', 'data': []}
        td = T.add_role_to_tab(td, 'main', '1', r)
        td = T.add_role_to_tab(td, 'main', '1', {'uniqueId': 7, 'name': 'Wait', 'data': []})
        td = T.apply_saved_role_data(td, 'main', '1', {'u1': [{'name': 'text', 'value': 'v'}], '7': [{'name': 'time', 'value': 1}]})
        roles = td['main']['nodes'][0]['data']['roles']
        self.assertEqual(roles[0]['data'][0]['value'], 'v')
        self.assertEqual(roles[1]['data'][0]['value'], 1)
        td = T.delete_role_from_tab(td, 'main', '1', 'u1')
        self.assertEqual([r['uniqueId'] for r in td['main']['nodes'][0]['data']['roles']], [7])
        td = T.delete_role_from_tab(td, 'main', '1', '7')   # 厳密比較: 数値 7 は '7' では消えない
        self.assertEqual(len(td['main']['nodes'][0]['data']['roles']), 1)
        items = T.typed_role_items([{'uniqueId': 7, 'formData': [{'name': 'time', 'value': 2}]}], td['main']['nodes'][0], SCHEMAS)
        self.assertEqual(items[0]['formData'][0]['type'], 'float')

    def test_edges_and_move(self):
        td = self.td()
        td2, err = T.add_edge(td, 'main', T.make_edge('1', '2'))
        self.assertEqual(err, '既に接続済み')
        td2, err = T.add_edge(td, 'main', T.make_edge('5', '1'))
        self.assertIsNone(err)
        self.assertEqual(td2['main']['edges'][-1], {'source': '5', 'target': '1', 'id': '5-1'})
        td3 = T.remove_edge(td2, 'main', {'source': '1', 'target': '2'})
        self.assertEqual(len(td3['main']['edges']), 2)
        ids = ['1', '2', '5']
        self.assertEqual(T.validate_connect('1', '1', ids, [])[1], '接続先が無効')
        self.assertEqual(T.validate_connect('1', '9', ids, [])[1:], ('存在しないノードID', 'error'))
        self.assertEqual(T.validate_connect('1', '2', ids, td['main']['edges'])[1], '既に接続済み')
        self.assertEqual(T.validate_connect('1', ' 5 ', ids, td['main']['edges'])[0], '5')
        out, nid = T.move_to_group(td, 'main', '2', '7')
        self.assertEqual(nid, '1')
        self.assertEqual([n['id'] for n in out['main']['nodes']], ['1', '5'])
        self.assertEqual(out['main']['edges'], [])
        moved = out['subgroup-7']['nodes'][0]
        self.assertEqual((moved['id'], moved['data']['label'], moved['data']['isSubGroup']), ('1', 'Group: 7 / Sub: 1', True))
        self.assertEqual(T.move_to_group(td, 'main', 'zz', '7')[1], None)

    def test_save_payload(self):
        td = {'main': {'nodes': [
            {'id': '1', 'data': {'label': '1', 'roles': None}},
            {'id': '2', 'type': 'customGroup', 'position': {'x': 3, 'y': 4},
             'data': {'description': 'd', 'roles': [], 'subgroups': {'2': {}}, 'isSubGroup': False, 'subGroupSetting': [], 'extra': 1}},
        ], 'edges': [{'source': '1', 'target': '2'}]}}
        p = T.build_save_data(td, 'main')
        n0, n1 = p['nodes']
        self.assertEqual(n0, {'id': '1', 'type': 'customGroup', 'position': {'x': 0, 'y': 0},
                              'data': {'label': '1', 'description': '', 'roles': [], 'subgroups': {}}, 'draggable': True})
        self.assertEqual(n1['data'], {'description': 'd', 'roles': [], 'subgroups': {'2': {}}, 'isSubGroup': False, 'subGroupSetting': []})
        self.assertEqual(T.build_save_data(td, 'main')['nodes'][0]['type'], 'customGroup')
        td['subgroup-1'] = td['main']
        self.assertEqual(T.build_save_data(td, 'subgroup-1')['nodes'][0]['type'], 'subGroupNode')

    def test_sync_main_subgroup(self):
        td = {'main': {'nodes': [node('1', 'p'), node('2', 'q')], 'edges': []},
              'subgroup-1': {'nodes': [node('1', 'child', roles_from('Say text="a"')), node('2', '')], 'edges': [{'source': '1', 'target': '2'}]}}
        out = T.sync_main_subgroup(td, '1')
        sg = out['main']['nodes'][0]['data']['subgroups']['1']
        self.assertEqual([n['id'] for n in sg['nodes']], ['1', '2'])
        self.assertEqual(sg['nodes'][0]['type'], 'customGroup')   # n.type があればそのまま
        self.assertEqual(sg['edges'], [{'source': '1', 'target': '2'}])
        self.assertIs(out['main']['nodes'][1], td['main']['nodes'][1])
        self.assertIs(T.sync_main_subgroup({'main': td['main']}, '1')['main'], td['main'])

    def test_normalize_loaded_and_misc(self):
        r = T.normalize_loaded_tab({'nodes': [{'id': '1'}, {'id': '2'}], 'edges': [
            {'source': '1', 'target': '2'}, {'source': '1', 'target': '3'}]})
        self.assertEqual(len(r['edges']), 1)
        self.assertEqual(T.normalize_loaded_tab(None), {'nodes': [], 'edges': []})
        self.assertEqual(T.node_path_of(True, '3', '1'), '3/1')
        self.assertEqual(T.node_path_of(False, None, 4), '4')
        self.assertEqual(T.parent_of_tab('subgroup-12'), '12')
        self.assertIsNone(T.parent_of_tab('main'))

    def test_renumber_and_index(self):
        td = {'main': {'nodes': [node('1', subgroups={'1': {'nodes': []}}), node('1', subgroups={'1': {'nodes': []}})], 'edges': []}}
        r = T.renumber_duplicates_in_tab(td, 'main', ['main', 'subgroup-1'])
        self.assertTrue(r['blocked'])
        r = T.renumber_duplicates_in_tab(td, 'main', ['main'])
        self.assertEqual(r['renamed'], [{'index': 1, 'from': '1', 'to': '2'}])
        self.assertEqual(list(r['tabData']['main']['nodes'][1]['data']['subgroups']), ['2'])
        r2 = T.renumber_duplicates_in_tab(r['tabData'], 'main', ['main'])
        self.assertEqual(r2['renamed'], [])
        self.assertIs(r2['tabData'], r['tabData'])


class FilterTest(unittest.TestCase):
    def test_filter(self):
        nodes = [node('1', 'Hello World', roles_from('Say text="a"')), node('2', 'second', []),
                 node('3', 'wait here', roles_from('Wait time=1'), setting=[{'name': 'is_wait_key', 'type': 'bool', 'value': True}])]
        ids = lambda v: [n['id'] for n, _ in v]  # noqa: E731
        self.assertEqual(ids(T.filter_visible(nodes)), ['1', '2', '3'])
        self.assertEqual(ids(T.filter_visible(nodes, '  hello   WORLD ')), ['1'])
        self.assertEqual(ids(T.filter_visible(nodes, 'wait')), ['3'])       # Role名 Wait にも一致
        self.assertEqual(ids(T.filter_visible(nodes, 'say')), ['1'])
        self.assertEqual(ids(T.filter_visible(nodes, '2')), ['2'])
        self.assertEqual(ids(T.filter_visible(nodes, '', only_roles=True)), ['1', '3'])
        iw = lambda n: T.is_wait_node(n, SETTING_SCHEMA, SETTING_DEFAULTS)  # noqa: E731
        self.assertEqual(ids(T.filter_visible(nodes, '', only_wait=True, is_wait_node=iw)), ['3'])
        self.assertEqual(ids(T.filter_visible(nodes, '', only_wait=True)), [])
        issues = {'2': [{'level': 'info'}], '1': [{'level': 'warn'}]}
        self.assertEqual(ids(T.filter_visible(nodes, '', only_issues=True, issues_by_node=issues)), ['1'])
        self.assertEqual([i for _, i in T.filter_visible(nodes, 'second')], [1])

    def test_nav(self):
        nodes = [node('1', roles=roles_from('Say text="a"')), node('2'), node('3', roles=roles_from('Say text="b"'))]
        vis = T.filter_visible(nodes)
        ids = T.nav_list(vis, True)
        self.assertEqual(ids, ['1', '3'])
        self.assertEqual(T.nav_list(vis, False), [])
        self.assertEqual(T.navigate_target(ids, '1', 'next'), '3')
        self.assertIsNone(T.navigate_target(ids, '1', 'prev'))
        self.assertIsNone(T.navigate_target(ids, '2', 'next'))


class StateMachinesTest(unittest.TestCase):
    def test_history(self):
        now = [1000]
        h = T.History(clock=lambda: now[0])
        s1, s2, s3 = {'a': 1}, {'a': 2}, {'a': 3}
        h.push('main', s1)
        now[0] += 1000
        h.push('main', s2)
        now[0] += 100
        h.push('main', s3)      # 400ms 以内: 無視(最初の状態だけを残す)
        self.assertEqual(h.counts('main'), (2, 0))
        cur = {'a': 4}
        self.assertIs(h.apply('main', 'undo', cur), s2)
        self.assertEqual(h.counts('main'), (1, 1))
        self.assertIs(h.apply('main', 'redo', s2), cur)
        self.assertEqual(h.counts('main'), (2, 0))
        self.assertIsNone(h.apply('main', 'redo', cur))
        self.assertIsNone(h.apply('other', 'undo', cur))
        now[0] += 1000
        h.push('main', s2)      # 新しい変更で redo は消える
        self.assertEqual(h.counts('main')[1], 0)
        h2 = T.History(clock=lambda: now[0])
        for i in range(60):
            now[0] += 1000
            h2.push('t', {'i': i})
        self.assertEqual(h2.counts('t')[0], 50)
        same = {'x': 1}
        h3 = T.History(clock=lambda: now[0])
        h3.push('t', same)
        now[0] += 1000
        h3.push('t', same)
        self.assertEqual(h3.counts('t')[0], 1)

    def test_save_coordinator(self):
        sc = T.SaveCoordinator()
        self.assertFalse(sc.begin('main'), '読み込み前は保存しない')
        sc.mark_loaded('main')
        sc.mark_dirty()
        self.assertEqual(sc.status, 'dirty')
        self.assertTrue(sc.begin('main'))
        self.assertEqual(sc.status, 'saving')
        sc.mark_dirty()
        self.assertEqual(sc.status, 'saving')
        self.assertFalse(sc.begin('main'))      # 保存中: 保留
        self.assertEqual(sc.finish(True), 'main')
        self.assertEqual(sc.status, 'dirty')    # 保存中に編集があった
        self.assertTrue(sc.begin('main'))
        self.assertIsNone(sc.finish(False))
        self.assertEqual(sc.status, 'error')
        self.assertTrue(sc.should_confirm_leave())
        self.assertTrue(sc.begin('main'))
        sc.finish(True)
        self.assertEqual(sc.status, 'saved')
        self.assertFalse(sc.should_confirm_leave())

    def test_rev_tracker(self):
        r = T.RevTracker()
        self.assertFalse(r.should_check())
        r.note('a')
        self.assertTrue(r.should_check())
        self.assertFalse(r.should_check(hidden=True))
        self.assertFalse(r.observe('a'))
        self.assertFalse(r.observe('b', saving=True))
        self.assertTrue(r.observe('b'))
        self.assertEqual(r.external, 'b')
        r.ignore_external()
        self.assertEqual((r.known, r.external), ('b', None))
        self.assertFalse(r.observe('b'))

    def test_drafts(self):
        d = T.RoleDataDrafts()
        d.update('1', {'u1': [1]})
        d.update('1', {'u2': [2]})
        self.assertEqual(d.draft['1'], {'u1': [1], 'u2': [2]})
        d.flush('1')
        self.assertEqual(d.cache['1'], {'u1': [1], 'u2': [2]})
        self.assertNotIn('1', d.draft)
        d.update('1', {'u1': [5], 'u2': [2]})
        d.after_save('1', {'u2': [2]}, [{'uniqueId': 'u2', 'formData': [2]}])
        self.assertEqual(d.draft['1'], {'u1': [5]})
        init = d.initial_for_drawer([{'uniqueId': 'u1', 'data': [9]}, {'uniqueId': 'u3', 'data': [3]}, {'uniqueId': 'u4'}], '1')
        self.assertEqual(init, {'u1': [1], 'u3': [3], 'u4': []})
        d.reset()
        self.assertEqual((d.draft, d.cache), ({}, {}))

    def test_color_store(self):
        import tempfile
        with tempfile.TemporaryDirectory() as dname:
            cs = T.NodeColorStore(dname)
            self.assertEqual(cs.get(1, 2), {})
            self.assertEqual(cs.set_paths(1, 2, ['1', '1/2'], 'red'), {'1': 'red', '1/2': 'red'})
            self.assertEqual(T.NodeColorStore(dname).get(1, 2), {'1': 'red', '1/2': 'red'})
            self.assertEqual(cs.set_paths(1, 2, ['1'], None), {'1/2': 'red'})
            self.assertEqual(cs.get(1, 3), {})
        self.assertEqual(T.NodeColorStore(None).set_paths(1, 2, ['a'], 'none'), {'a': 'none'})


if __name__ == '__main__':
    unittest.main()
