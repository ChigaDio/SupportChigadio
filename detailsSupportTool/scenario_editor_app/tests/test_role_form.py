"""core/role_form.py の検証 (BaseRoleInputForm.js から原文切り出しした関数との差分テスト + 明示期待値)。"""
import os
import random
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import gen_roleform_harness  # noqa: E402
from jscompare import norm, run_js_adapter  # noqa: E402
from scenario_editor.core import role_form as R  # noqa: E402

gen_roleform_harness.build()
MOD = '_gen_roleform'

CTX = R.make_type_context(
    {'FadeID': ['A', 'B'], 'Empty': [], 'ItemID': ['Potion']},
    {'Cls': [{'name': 'a', 'type': 'int'}, {'name': 'v', 'type': 'Vector2', 'arraySize': 0}, {'name': 'xs', 'type': 'int', 'arraySize': 2}]},
    {'Cust': [{'name': 'c', 'type': 'color'}, {'name': 'bits', 'type': 'bit', 'options': {'size': 4}},
              {'name': 'inner', 'type': 'Cls'}, {'name': 'curve', 'type': 'bezier', 'options': {'min': -1, 'max': 5}}]})
JS_CTX = {'enumValues': CTX['enumValues'], 'classDataSchemas': CTX['classDataSchemas'], 'customClassSchemas': CTX['customClassSchemas']}


class DefaultsTest(unittest.TestCase):
    TYPES = ['int', 'Int', 'short', 'long', 'byte', 'float', 'double', 'decimal', 'char', 'bool', 'string', 'String',
             'Vector2', 'vector3', 'Vector4', 'bit', 'color', 'bezier', 'dictionary', 'text_list_index', 'voice_ref',
             'Cust', 'FadeID', 'Empty', 'Cls', 'Unknown', 'ItemID', 'Bit', 'GameObject']

    def test_get_default_value(self):
        cases = []
        for t in self.TYPES:
            for sz in (None, 0, 1, 3, -1, -5):
                for opt in (None, {'size': 4}, {'min': -2, 'max': 9}, {}):
                    cases.append({'ctx': JS_CTX, 't': t, 'sz': sz, 'o': opt})
        js = run_js_adapter(MOD, "(m,a)=>m.mkForm({...a.ctx, formData: []}).getDefaultValue(a.t, a.sz, a.o)", cases)
        for c, jv in zip(cases, js):
            self.assertEqual(norm(R.get_default_value(c['t'], c['sz'], c['o'], CTX)), norm(jv), c)

    def test_dependency(self):
        deps = [None, {}, {'parentFieldName': 'p'}, {'parentFieldName': 'p', 'enableValues': []},
                {'parentFieldName': 'p', 'enableValues': [True]}, {'parentFieldName': 'p', 'enableValues': [False]},
                {'parentFieldName': 'p', 'enableValues': ['true']}, {'parentFieldName': 'p', 'enableValues': ['FALSE', 'x']},
                {'parentFieldName': 'p', 'enableValues': ['A']}, {'parentFieldName': 'p', 'enableValues': ['FadeID.A']},
                {'parentFieldName': 'p', 'enableValues': ['B', 'FadeID.A']}, {'parentFieldName': 'p', 'enableValues': [1, 2]},
                {'parentFieldName': 'zz', 'enableValues': ['A']}, {'parentFieldName': 'zz', 'enableValues': []}]
        vals = [True, False, 'FadeID.A', 'FadeID.B', 'A', 'FadeID.None', 'None', '', None, 1, 2, 'x.y.A', 5]
        cases = []
        for d in deps:
            for v in vals:
                fd = [{'name': 'p', 'value': v}] if v is not None else [{'name': 'p'}]
                cases.append({'ctx': {**JS_CTX, 'formData': fd}, 'field': {'name': 'f', 'dependency': d}})
            cases.append({'ctx': {**JS_CTX, 'formData': []}, 'field': {'name': 'f', 'dependency': d}})
        js = run_js_adapter(MOD, "(m,a)=>m.mkForm(a.ctx).isFieldEnabledByDependency(a.field)", cases)
        for c, jv in zip(cases, js):
            self.assertEqual(R.is_field_enabled_by_dependency(c['field'], c['ctx']['formData']), jv, c)

    def test_initial_form_data(self):
        schema = {'fields': [
            {'name': 'a', 'type': 'int'}, {'name': 'b', 'type': 'string', 'default': 'dflt'},
            {'name': 'c', 'type': 'Vector2', 'arraySize': -1}, {'name': 'd', 'type': 'bool', 'default': False},
            {'name': 'e', 'type': 'FadeID'}, {'name': 'f', 'type': 'int', 'arraySize': 2}, {'name': 'g', 'type': 'string', 'default': None}]}
        out = R.build_initial_form_data(schema, [{'name': 'a', 'value': 7}, {'name': 'b', 'value': ''}, {'name': 'zz', 'value': 1}], CTX)
        self.assertEqual(out, [
            {'name': 'a', 'value': 7, 'arraySize': 0}, {'name': 'b', 'value': '', 'arraySize': 0},
            {'name': 'c', 'value': [], 'arraySize': -1}, {'name': 'd', 'value': False, 'arraySize': 0},
            {'name': 'e', 'value': 'FadeIDID.None', 'arraySize': 0}, {'name': 'f', 'value': [0, 0], 'arraySize': 2},
            {'name': 'g', 'value': '', 'arraySize': 0}])
        out = R.build_initial_form_data(schema, None, CTX)
        self.assertEqual(out[1]['value'], 'dflt')

    def test_editor_kind(self):
        k = lambda t: R.field_editor_kind({'type': t}, CTX)  # noqa: E731
        self.assertEqual([k(t) for t in ['voice_ref', 'text_list_index', 'bit', 'color', 'bezier', 'dictionary', 'Cust', 'FadeID',
                                         'Empty', 'Cls', 'string', 'String', 'char', 'int', 'long', 'float', 'decimal', 'bool',
                                         'Vector3', 'Foo']],
                         ['voice_ref', 'text_list_index', 'bit', 'color', 'bezier', 'dictionary', 'custom_class', 'enum',
                          'text', 'class', 'string', 'string', 'char', 'int', 'int', 'float', 'float', 'bool', 'vector', 'text'])

    def test_arrays_and_nested(self):
        f = {'name': 'xs', 'type': 'int', 'arraySize': 3}
        self.assertEqual(R.array_value_of(f, None, CTX), [0, 0, 0])
        self.assertEqual(R.array_value_of({**f, 'arraySize': -1}, 'x', CTX), [])
        self.assertEqual(R.array_value_of(f, [1], CTX), [1])
        self.assertEqual(R.field_array_info({'arraySize': -1})['kind'], 'dynamic')
        self.assertEqual(R.field_array_info({})['kind'], 'single')
        self.assertEqual(R.field_array_info({'arraySize': 4}), {'kind': 'fixed', 'length': 4})
        self.assertEqual(R.move_item([1, 2, 3, 4], 0, 2), [2, 3, 1, 4])
        fd = [{'name': 'a', 'value': 1, 'arraySize': 0}, {'name': 'b', 'value': 2, 'arraySize': 0}]
        self.assertEqual(R.set_field_value(fd, 'b', 9, -1)[1], {'name': 'b', 'value': 9, 'arraySize': -1})
        self.assertEqual(R.set_field_value(fd, 'b', 9)[1]['arraySize'], 0)
        self.assertEqual(R.current_field_value({'name': 'zz', 'type': 'int'}, fd, CTX), 0)
        sub = R.build_sub_schema([{'name': 'a', 'type': 'int'}, {'name': 'x', 'type': 'int', 'arraySize': 2, 'label': 'L'}])
        self.assertEqual([(f['label'], f['arraySize']) for f in sub['fields']], [('a', 0), ('L', 2)])
        nid = R.nested_initial_data({'a': 1, 'x': [1, 2], 'unknown': 5}, sub)
        self.assertEqual(nid, [{'name': 'a', 'value': 1, 'arraySize': 0}, {'name': 'x', 'value': [1, 2], 'arraySize': 2},
                               {'name': 'unknown', 'value': 5, 'arraySize': 0}])
        self.assertEqual(R.nested_to_value(nid), {'a': 1, 'x': [1, 2], 'unknown': 5})


class NumericTest(unittest.TestCase):
    def test_change(self):
        self.assertEqual(R.numeric_input_change('12', False), (True, (True, 12)))
        self.assertEqual(R.numeric_input_change('-', False), (True, (True, 0)))
        self.assertEqual(R.numeric_input_change('', True), (True, (True, 0)))
        self.assertEqual(R.numeric_input_change('1.5', False), (False, (False, None)))
        self.assertEqual(R.numeric_input_change('1.5', True), (True, (True, 1.5)))
        self.assertEqual(R.numeric_input_change('.', True), (True, (False, None)))
        self.assertEqual(R.numeric_input_change('-.', True), (True, (False, None)))
        self.assertEqual(R.numeric_input_change('1.', True), (True, (True, 1)))
        self.assertEqual(R.numeric_input_change('abc', True), (False, (False, None)))
        self.assertEqual(R.numeric_input_change('--1', False), (False, (False, None)))

    def test_blur(self):
        self.assertEqual(R.numeric_input_blur('', False), ('0', 0))
        self.assertEqual(R.numeric_input_blur('-', True), ('0', 0))
        self.assertEqual(R.numeric_input_blur('-.', True), ('0', 0))
        self.assertEqual(R.numeric_input_blur('1.50', True), ('1.5', 1.5))
        self.assertEqual(R.numeric_input_blur('007', False), ('7', 7))
        self.assertEqual(R.numeric_input_blur('-0', False), ('0', 0))


class ColorBezierTest(unittest.TestCase):
    def test_color_funcs(self):
        vals = [0, 1, 0.5, 0.2, 0.123, 1.5, -1, 0.9999, 0.00196, 0.498, 0.3]
        js = run_js_adapter(MOD, "(m,a)=>m.toHex(a)", vals)
        self.assertEqual([R.to_hex(v) for v in vals], js)
        cols = [{'r': 1, 'g': 0.5, 'b': 0, 'a': 1}, {'r': 0.2, 'g': 0.3, 'b': 0.4}, {'r': 0, 'g': 0, 'b': 0, 'a': 0.555},
                {'r': 0.5, 'g': 0.5, 'b': 0.5, 'a': 0.005}]
        js = run_js_adapter(MOD, "(m,a)=>m.colorKey(a)", cols)
        self.assertEqual([R.color_key(c) for c in cols], js)
        texts = ['#fff', 'FFF', '#112233', '112233', '#11223344', 'abcd', '#ggg', '', ' #abc ', '#12345', '#aabbccdd', 'zz']
        js = run_js_adapter(MOD, "(m,a)=>m.parseHexColor(a)", texts)
        for t, jv in zip(texts, js):
            self.assertEqual(norm(R.parse_hex_color(t)), norm(jv), t)

    def test_hex_css(self):
        self.assertEqual(R.color_hex({'r': 1, 'g': 0.5, 'b': 0}), '#ff8000')
        self.assertEqual(R.color_css({'r': 1, 'g': 0, 'b': 0, 'a': 0.5}), 'rgba(255,0,0,0.5)')
        self.assertEqual(R.color_css({'r': 1, 'g': 0, 'b': 0}), 'rgba(255,0,0,1)')

    def test_recent(self):
        with tempfile.TemporaryDirectory() as d:
            rc = R.RecentColors(d)
            self.assertEqual(rc.get(), [])
            for i in range(12):
                rc.push({'r': i / 12, 'g': 0, 'b': 0})
            self.assertEqual(len(rc.get()), 10)
            rc.push({'r': 11 / 12, 'g': 0, 'b': 0, 'a': 1})  # 同じ色は先頭へ移動 (重複しない)
            self.assertEqual(len(R.RecentColors(d).get()), 10)
            self.assertEqual(R.RecentColors(d).get()[0]['r'], 11 / 12)

    def test_hermite(self):
        rnd = random.Random(1)
        cases = []
        for _ in range(60):
            p0 = {'time': rnd.random() * 0.5, 'value': rnd.uniform(-3, 3), 'inTangent': rnd.uniform(-2, 2), 'outTangent': rnd.uniform(-2, 2)}
            p1 = {'time': 0.5 + rnd.random() * 0.5, 'value': rnd.uniform(-3, 3), 'inTangent': rnd.uniform(-2, 2), 'outTangent': rnd.uniform(-2, 2)}
            cases.append({'p0': p0, 'p1': p1, 't': rnd.random()})
        cases.append({'p0': {'time': 1, 'value': 0, 'inTangent': 0, 'outTangent': 0}, 'p1': {'time': 1, 'value': 2, 'inTangent': 0, 'outTangent': 0}, 't': 1})
        js = run_js_adapter(MOD, "(m,a)=>m.hermite(a.p0,a.p1,a.t)", cases)
        for c, jv in zip(cases, js):
            self.assertAlmostEqual(R.hermite(c['p0'], c['p1'], c['t']), jv, places=9)

    def test_bezier_helpers(self):
        pts = R.bezier_points(None, {'min': -1, 'max': 3})
        self.assertEqual([(p['time'], p['value']) for p in pts], [(0, -1), (1, 3)])
        pts = R.bezier_points({'points': [{'time': 1, 'value': 0}, {'time': 0.2, 'value': 1}]}, None)
        self.assertEqual([p['time'] for p in pts], [0.2, 1])
        self.assertEqual(len(R.bezier_points({'points': [{'time': 1, 'value': 0}]}, None)), 2)
        pts = R.bezier_points(None, None)
        self.assertEqual(R.bezier_add_point(pts, None)['points'][-1], {'time': 0.5, 'value': 0.5, 'inTangent': 0, 'outTangent': 0})
        self.assertIsNone(R.bezier_remove_point(pts, 0))
        self.assertEqual(len(R.bezier_remove_point(R.bezier_add_point(pts, None)['points'], 2)['points']), 2)
        self.assertEqual(R.bezier_update_point(pts, 1, {'value': 9})['points'][1]['value'], 9)
        g = R.BezierGeometry({'min': 0, 'max': 2})
        self.assertAlmostEqual(g.px_to_x(g.x_to_px(0.3)), 0.3)
        self.assertAlmostEqual(g.px_to_y(g.y_to_px(1.1)), 1.1)
        dx, dy = g.tangent_to_handle_offset(1.0, 'out')
        self.assertAlmostEqual((dx ** 2 + dy ** 2) ** 0.5, 40)
        self.assertAlmostEqual(g.handle_offset_to_tangent(dx, dy, 'out'), 1.0)
        dx, dy = g.tangent_to_handle_offset(-0.5, 'in')
        self.assertAlmostEqual(g.handle_offset_to_tangent(dx, dy, 'in'), -0.5)
        self.assertEqual(len(g.curve_points(R.bezier_points(None, None))), 25)


class BitDictTest(unittest.TestCase):
    def test_bit(self):
        self.assertEqual(R.bit_flag_names({'size': 3}, None), ['Flag0', 'Flag1', 'Flag2'])
        self.assertEqual(R.bit_flag_names({'size': 2, 'flagNames': ['a', 'b']}, None), ['a', 'b'])
        self.assertEqual(R.bit_flag_names({'size': 3, 'flagNames': ['a', 'b']}, None), ['Flag0', 'Flag1', 'Flag2'])
        self.assertEqual(R.bit_flag_names(None, {'size': 2}), ['Flag0', 'Flag1'])
        self.assertEqual(R.bit_flag_names(None, None), [f'Flag{i}' for i in range(8)])
        self.assertEqual(R.bit_toggle(None, {'size': 4}, 1), {'size': 4, 'bits': [1]})
        self.assertEqual(R.bit_toggle({'size': 4, 'bits': [1, 2]}, {'size': 4}, 1), {'size': 4, 'bits': [2]})
        self.assertEqual(R.bit_toggle({'size': 4, 'bits': [1, 2]}, {'size': 4, 'mode': 'single'}, 3), {'size': 4, 'bits': [3]})
        self.assertEqual(R.bit_filter(['Foo', 'bar', 'FOOD'], ' foo '), [('Foo', 0), ('FOOD', 2)])
        self.assertEqual(len(R.bit_filter(['a', 'b'], '')), 2)

    def test_dict(self):
        js = run_js_adapter(MOD, "(m,a)=>m.defaultDictScalar(a[0], a[1], a[2], a[3])",
                            [[t, JS_CTX['enumValues'], JS_CTX['classDataSchemas'], JS_CTX['customClassSchemas']] for t in DefaultsTest.TYPES])
        for t, jv in zip(DefaultsTest.TYPES, js):
            self.assertEqual(norm(R.default_dict_scalar(t, CTX)), norm(jv), t)
        opts = {'keyType': 'FadeID', 'valueType': 'int', 'valueArraySize': -1}
        v = R.dictionary_add_entry(None, opts, CTX)
        self.assertEqual(v, {'entries': [{'key': 'FadeIDID.None', 'value': []}]})
        v = R.dictionary_add_entry(v, {'keyType': 'int', 'valueType': 'string'}, CTX)
        self.assertEqual(v['entries'][1], {'key': 0, 'value': ''})
        v = R.dictionary_update(v, 1, key=5, set_key=True)
        v = R.dictionary_update(v, 1, val='x', set_val=True)
        self.assertEqual(v['entries'][1], {'key': 5, 'value': 'x'})
        self.assertEqual(len(R.dictionary_remove(v, 0)['entries']), 1)
        self.assertEqual(R.dictionary_options(None), {'keyType': 'int', 'valueType': 'int', 'valueIsArray': False, 'valueOptions': {}})
        self.assertEqual(R.enum_options('FadeID', ['A'])[:2], [{'value': 'FadeIDID.None', 'label': 'None'}, {'value': 'FadeIDID.A', 'label': 'A'}])
        self.assertEqual(R.enum_options('X', [{'property': 'p'}, {'enum_property': 'q'}])[1:], [
            {'value': 'XID.p', 'label': 'p'}, {'value': 'XID.q', 'label': 'q'}])


SOUND = {'groups': {
    'Scenario': {'items': [
        {'name': 'Line001', 'subgroup': 'Test', 'desc': 'こんにちは', 'type': 'voice'},
        {'name': 'Line002', 'nest_path': ['A', 'B'], 'type': 'voice'},
        {'name': 'Line003', 'subgroup': 'Test', 'nest_path': ['Test']},
        {'name': 'NoSub'}]},
    'Bgm': {'items': [{'name': 'Main', 'subgroup': '', 'desc': None}]}, 'Empty': {}, 'Nul': None}}


class VoiceTextTest(unittest.TestCase):
    def test_sound_lookup(self):
        js = run_js_adapter(MOD, "(m,a)=>Object.fromEntries(m.buildSoundLookup(a))", [SOUND, {}, None])
        for s, jv in zip([SOUND, {}, None], js):
            self.assertEqual(norm(R.build_sound_lookup(s)), norm(jv))
        vals = [None, 'SoundID.Scenario_Test_Line001', 'Scenario_Test_Line001', 3, '', 'a.b.c', '.x']
        js = run_js_adapter(MOD, "(m,a)=>m.stripSoundIdPrefix(a)", vals)
        self.assertEqual([R.strip_sound_id_prefix(v) for v in vals], js)

    def test_extract_cell(self):
        cells = [None, 'str', 5, [1, 2], {'voices': {'value': [1]}}, {'voices': {'value': 'x'}}, {'voices': [3]}, {'voices': 'x'},
                 {'other': 1}, {}, {'voices': None}, {'voices': {'value': None}}]
        js = run_js_adapter(MOD, "(m,a)=>{const r=m.extractCellList(a,'voices'); return r===null?{__null:true}:r;}", cells)
        for c, jv in zip(cells, js):
            pv = R.extract_cell_list(c, 'voices')
            self.assertEqual(jv, {'__null': True} if pv is None else pv, c)

    def test_resolve_key(self):
        evs = [{'id': 1, 'name': 'Ev', 'subEvents': [{'subId': 2, 'name': 'Sub'}]}]
        self.assertEqual(R.resolve_scenario_key(evs, '1', '2'), 'Ev_Sub')
        for args in ((evs, None, '2'), (evs, '1', None), (evs, '9', '2'), (evs, '1', '9'), (None, '1', '2')):
            with self.assertRaises(ValueError):
                R.resolve_scenario_key(*args)

    TABLE = {'data': {
        'LanguageID.Ja': {'Ev_Sub': {'voices': {'value': ['SoundID.Scenario_Test_Line001', 'x']}, 'texts': {'value': ['あ', 'い', None, 5]}}},
        'En': {'ScenarioEventID.Ev_Sub': {'voices': {'value': ['SoundID.Scenario_Test_Line001']}, 'texts': ['a']}},
        'Fr': {'Other': {}}, 'De': {'X.Ev_Sub': {'nothing': 1}}}}

    def test_voice(self):
        langs = R.voice_languages(self.TABLE, 'Ev_Sub', 'voices')
        self.assertEqual([(l['label'], l['colKey'], None if l['list'] is None else len(l['list'])) for l in langs],
                         [('Ja', 'Ev_Sub', 2), ('En', 'ScenarioEventID.Ev_Sub', 1), ('Fr', None, None), ('De', 'X.Ev_Sub', None)])
        self.assertEqual(R.active_language(langs, 'en')['label'], 'En')
        self.assertEqual(R.active_language(langs, 'zz')['label'], 'Ja')
        self.assertIsNone(R.active_language([], 'Ja'))
        self.assertEqual(R.length_mismatch(langs), 'Ja:2件 / En:1件')
        self.assertEqual(R.length_mismatch(langs[:1]), '')
        items = R.voice_items(langs[0], R.build_sound_lookup(SOUND))
        self.assertEqual(items[0]['label'], '0 : Scenario_Test_Line001 — こんにちは')
        self.assertEqual(items[1]['label'], '1 : x')
        self.assertIsNone(items[1]['info'])
        self.assertEqual(R.voice_items(langs[0], None)[0]['label'], '0 : Scenario_Test_Line001')
        self.assertEqual(R.voice_languages(None, 'k', 'voices'), [])

    def test_text(self):
        items = R.text_list_items(self.TABLE, 'Ev_Sub', 'Ja', 'texts')
        self.assertEqual([i['label'] for i in items], ['0 : あ', '1 : い', '2 : ', '3 : 5'])
        self.assertEqual(R.text_list_items(self.TABLE, 'Ev_Sub', 'En', 'texts')[0]['text'], 'a')
        self.assertEqual(R.text_list_items(self.TABLE, 'Ev_Sub', 'en', 'texts')[0]['text'], 'a')  # 小文字比較は行キー全体に対して行う(元JSどおり)
        for lang, key, msg in [('Zz', 'Ev_Sub', '言語 "Zz"'), ('Ja', 'Nope', '列 "Nope"'), ('De', 'Ev_Sub', 'フィールド "texts"')]:
            with self.assertRaises(ValueError) as cm:
                R.text_list_items(self.TABLE, key, lang, 'texts')
            self.assertIn(msg, str(cm.exception))

    def test_index_value(self):
        for v, want in [(3, 3), ('4', 4), (' 5x', 5), ('', -1), ('x', -1), (None, -1), (True, -1), (float('nan'), -1), (2.5, 2.5), ([], -1)]:
            self.assertEqual(R.index_value(v), want, v)


class TypeContextTest(unittest.TestCase):
    def test_load(self):
        from mock_server import start_mock
        from scenario_editor.api.client import ApiClient
        from scenario_editor.api.lookups import LookupCache
        srv = start_mock()
        try:
            lk = LookupCache(ApiClient(srv.url))
            fields = [{'name': 'a', 'type': 'Chara'}, {'name': 'b', 'type': 'ItemID', 'subFields': [{'name': 'c', 'type': 'Pos'}]},
                      {'name': 'd', 'type': 'int'}]
            ctx = R.load_type_context(lk, fields)
            self.assertEqual(ctx['enumValues']['Chara'], ['Alice', 'Bob'])
            self.assertEqual(ctx['enumValues']['ItemID'], ['Potion', 'Sword'])
            self.assertEqual([f['name'] for f in ctx['classDataSchemas']['Pos']], ['x', 'y'])
            self.assertNotIn('Bar', ctx['enumValues'])
            self.assertEqual(ctx['customClassSchemas'], {})
        finally:
            srv.stop()
        self.assertEqual(R.collect_types([{'type': 'a', 'subFields': [{'type': 'b', 'subFields': [{'type': 'c'}]}]}]), {'a', 'b', 'c'})


if __name__ == '__main__':
    unittest.main()


class NormalizeTest(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(R.js_normalize_numbers({'a': 1.0, 'b': [2.0, 2.5, True, None, 'x'], 'c': {'d': 0.0}}),
                         {'a': 1, 'b': [2, 2.5, True, None, 'x'], 'c': {'d': 0}})
        self.assertIsInstance(R.js_normalize_numbers(3.0), int)
        self.assertEqual(R.js_normalize_numbers(float('inf')), float('inf'))
