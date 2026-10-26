"""core/dsl.py と scenarioTransactionDsl.js の差分テスト。

元の JS を Node で実行し(tests/jsref.py)、同一入力の出力が Python 実装と一致することを確認する。
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from jsref import run_js, run_js_batch  # noqa: E402
from scenario_editor.core import dsl  # noqa: E402

MOD = 'scenarioTransactionDsl'
NEW_UID = re.compile(r'^.+_\d{10,}_\d+_[0-9a-z]{0,6}$')


def N(x):
    """JS(JSON経由)と Python の戻り値を比較しやすい形に揃える。"""
    if isinstance(x, dsl.DslIssue):
        return N(x.to_dict())
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if v is None:
                continue
            if k == 'uniqueId' and isinstance(v, str) and NEW_UID.match(v):
                v = '<new>'
            out[k] = N(v)
        return out
    if isinstance(x, (list, tuple)):
        return [N(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted(N(v) for v in x)
    if isinstance(x, float) and x == int(x) and abs(x) < 1e15:
        return int(x)
    return x


# ------------------------------------------------------------------ 共通データ
FADE_OPTS = ['FadeID.None', 'FadeID.In', 'FadeID.Out']

SCHEMAS = {
    'Say': {'id': 1, 'branchType': 'General', 'fields': [
        {'name': 'text', 'type': 'string', 'required': True},
        {'name': 'speed', 'type': 'float', 'required': False},
        {'name': 'wait', 'type': 'bool'},
        {'name': 'count', 'type': 'int'},
        {'name': 'ch', 'type': 'char'},
        {'name': 'fade', 'type': 'FadeID', 'options': FADE_OPTS},
        {'name': 'text_id', 'type': 'text_list_index'},
        {'name': 'voice', 'type': 'voice_ref'},
    ]},
    'Move': {'id': 2, 'branchType': 'General', 'fields': [
        {'name': 'target', 'type': 'Vector3', 'required': False},
        {'name': 'pos', 'type': 'Vector2', 'required': False},
        {'name': 'quat', 'type': 'Vector4', 'required': False},
        {'name': 'col', 'type': 'color', 'required': False},
        {'name': 'bits', 'type': 'bit', 'required': False},
        {'name': 'curve', 'type': 'bezier', 'required': False},
        {'name': 'ui', 'type': 'CharacterUI', 'required': False, 'subFields': [
            {'name': 'add_position', 'type': 'Vector2'},
            {'name': 'scale', 'type': 'float'},
            {'name': 'nick', 'type': 'string'},
        ]},
        {'name': 'dic', 'type': 'dictionary', 'required': False},
        {'name': 'nums', 'type': 'int[]', 'required': False},
        {'name': 'names', 'type': 'string[]', 'required': False},
        {'name': 'items', 'type': 'Item[]', 'required': False, 'subFields': [
            {'name': 'a', 'type': 'int'},
            {'name': 'n', 'type': 'string'},
            {'name': 'p', 'type': 'Vector2'},
        ]},
        {'name': 'fades', 'type': 'FadeID[]', 'required': False, 'options': FADE_OPTS},
        {'name': 'cd', 'type': 'MyClass', 'required': False},
        {'name': 'cds', 'type': 'MyClass[]', 'required': False},
        {'name': 'ref', 'type': 'GameCharacter', 'required': False,
         'options': ['GameCharacterID.None', 'GameCharacterID.Alice', 'GameCharacterID.Bob', 'GameCharacterID.Carol',
                     'GameCharacterID.Dave', 'GameCharacterID.Eve', 'GameCharacterID.Frank']},
    ]},
    'Bare': {'id': 3, 'branchType': 'General', 'fields': [{'name': 'x', 'type': 'int', 'required': False}]},
    'Wait': {'id': 4, 'fields': [{'name': 'time', 'type': 'float'}]},
}
CLASS_SCHEMAS = {
    'MyClass': [
        {'name': 'a', 'type': 'int'},
        {'name': 'tag', 'type': 'string'},
        {'name': 'inner', 'type': 'Inner'},
        {'name': 'pos', 'type': 'Vector2', 'arraySize': 0},
    ],
    'Inner': [{'name': 'z', 'type': 'float'}, {'name': 'flag', 'type': 'bool'}],
}
SETTING = {'fields': [
    {'name': 'is_wait_key', 'type': 'bool', 'required': True},
    {'name': 'delay', 'type': 'float', 'required': True},
    {'name': 'mode', 'type': 'SettingMode', 'options': ['SettingMode.A', 'SettingMode.B']},
    {'name': 'label', 'type': 'string'},
]}
ROLE_NAMES = list(SCHEMAS.keys())


def js_batch(calls):
    return run_js_batch(MOD, calls)


class DiffCase(unittest.TestCase):
    """複数入力をまとめて JS に投げ、1件ずつ Python と比較する。"""

    def compare(self, fn_js, fn_py, arglists, pyargs=None, post=None):
        pyargs = pyargs or (lambda a: a)
        js = js_batch([(fn_js, a) for a in arglists])
        for a, jv in zip(arglists, js):
            with self.subTest(args=repr(a)[:200]):
                pv = fn_py(*pyargs(a))
                if post:
                    pv = post(pv)
                self.assertEqual(N(pv), N(jv))


# ------------------------------------------------------------------ tokenize / parse
LINES = [
    '', '   ', '# comment', '  # indented comment',
    'PlayBGM', 'PlayBGM sound_id=BGM1 fade_time=0.5',
    'Say text="こんにちは" speed=1.5 wait=true # trailing',
    'Say text="a \\"quoted\\" \\\\ b"',
    'Say text="unterminated', 'Say text=', 'Say =1', 'Say text', 'Say text = "x"',
    'Move target={ x: 1.0, y: 0, z: -2.5 }', 'Move nums=[1, 2, 3]', 'Move items=[{a: 1, n: "x"}, {a: 2, n: "y"}]',
    'Move pos={ x: 1', 'Move pos=( 1 )', 'Move pos={ x: 1 }}', 'Move nums=[1,,2]', '1abc x=2', '"quoted" a=1',
    'Say text="x"y', 'Say a=-1 b=-1.5 c=1.', 'Say a=1.2.3', 'Say\ttext="tab"', 'Say  text="x"   speed=2',
    '#@ is_wait_key=true', '# ==== SUB:1 NODE:1/2 (desc) ====', 'Say a:b', 'Say a=b=c', 'Say a=:',
    'Say 日本語=1', 'Say a="日本語" # コメント', '@@ a=1', 'Say a=[', 'Say a=]',
    'Say text="a#b" # real', 'Say a=1,b=2', 'Say a=(1,2)',
]


class TestTokenizeParse(DiffCase):
    def test_tokenize_line(self):
        self.compare('tokenizeLine', dsl.tokenize_line, [[l] for l in LINES])

    def test_parse_line(self):
        self.compare('parseLine', dsl.parse_line, [[l, i] for i, l in enumerate(LINES)])

    def test_parse_document(self):
        docs = ['\n'.join(LINES), '', 'A\nB\n', 'Say a=1\r\nSay b=2', '\n\n#x\n\nSay q="1"\n']
        self.compare('parseDocument', dsl.parse_document, [[d] for d in docs])

    def test_dsl_issue(self):
        i = dsl.DslIssue('m', 1, 2, 3)
        self.assertEqual((i.message, i.from_, i.to, i.line, i.severity), ('m', 1, 2, 3, 'error'))
        self.assertEqual(i.to_dict(), {'message': 'm', 'from': 1, 'to': 2, 'line': 3, 'severity': 'error'})
        self.assertEqual(dsl.DslIssue('m', 1, 2, 3, 'warning').severity, 'warning')


# ------------------------------------------------------------------ 見出し
HDR_DOCS = [
    '',
    'Say a=1',
    '# ==== SUB:1 NODE:1 (a) ====\nSay a=1\n# ==== SUB:1 NODE:2 (b) ====\nSay b=1',
    '# ==== SUB:1 NODE:1 (a) ====\n# ==== SUB:1 NODE:1/1 (a) ====\n# ==== SUB:1 NODE:1/2 (a) ====\n# ==== SUB:1 NODE:2 ====',
    '# ==== SUB:2 NODE:1 ====\n# ==== SUB:2 NODE:1/1 ====\n# ==== SUB:1 NODE:5 ====\n# ==== SUB:1 NODE:1/9 ====',
    '#====SUB:1 NODE:7====\n#   ====   SUB:3   NODE:a09   x y z   ====   ',
    '# ==== SUB:1 NODE:abc ====\n# ==== SUB:1 NODE:abc/x9 ====',
    '# ==== SUB:1 NODE:1 ====\n# ==== SUB:1 NODE:1 ====\n# ==== SUB:1 NODE:1/1 ====\n# ==== SUB:1 NODE:1/1 ====',
    '# ==== SUB:1 NODE:1 (説明) ====\nSay x=1\n#@ is_wait_key=true\n# ==== SUB:1 NODE:1/1 ====\n',
    '# ==== SUB:1 NODE:1 ==== trailing',
    '# ==== SUB:1 NODE:1/1 ====\n# ==== SUB:1 NODE:1/2 ====\n# ==== SUB:1 NODE:2 ====\n# ==== SUB:1 NODE:2/1 ====',
    '# ==== SUB:1 NODE:3/1 ====\n# ==== SUB:1 NODE:1/1 ====\n# ==== SUB:1 NODE:1 ====\n# ==== SUB:1 NODE:1 ====\n# ==== SUB:1 NODE:1/1 ====\n',
    '# ==== SUB:1 NODE:1 ====\n# ==== SUB:1 NODE:1 ====\n# ==== SUB:1 NODE:1 ====\n# ==== SUB:1 NODE:2 ====',
    '# ==== SUB:1 NODE:1/1 ====\n# ==== SUB:1 NODE:1/1/1 ====\n# ==== SUB:1 NODE:1/1/1 ====\n# ==== SUB:1 NODE:1/1 ====',
]


class TestHeaders(DiffCase):
    def test_find_group_headers(self):
        self.compare('findGroupHeaders', dsl.find_group_headers, [[d] for d in HDR_DOCS])

    def test_next_group(self):
        args = []
        for d in HDR_DOCS:
            n = d.count('\n') + 1
            for c in range(-1, n + 2):
                args.append([d, c])
        self.compare('computeNextGroupHeader', dsl.compute_next_group_header, args)

    def test_next_subgroup(self):
        args = []
        for d in HDR_DOCS:
            n = d.count('\n') + 1
            for c in range(-1, n + 2):
                args.append([d, c])
        self.compare('computeNextSubgroupHeader', dsl.compute_next_subgroup_header, args)

    def test_renumber(self):
        self.compare('renumberDuplicateNodeIds', dsl.renumber_duplicate_node_ids, [[d] for d in HDR_DOCS])


# ------------------------------------------------------------------ coerce
def vt(src):
    """JS の tokenizeLine で値のトークン列を作る(Python 側にもそのまま渡す)。"""
    return run_js(MOD, 'tokenizeLine', src)


COERCE_CASES = [
    # (value text, type, options, subFields)
    ('3', 'int', None, None), ('-3', 'int', None, None), ('3.9', 'int', None, None), ('-3.9', 'int', None, None),
    ('x', 'int', None, None), ('"3"', 'int', None, None), ('1 2', 'int', None, None), ('', 'int', None, None),
    ('2.5', 'float', None, None), ('-0.5', 'double', None, None), ('abc', 'float', None, None), ('7', 'decimal', None, None),
    ('2', 'text_list_index', None, None), ('-1', 'text_list_index', None, None), ('a', 'text_list_index', None, None),
    ('4', 'voice_ref', None, None), ('b', 'voice_ref', None, None), ('5', 'uint', None, None), ('5', 'byte', None, None),
    ('true', 'bool', None, None), ('false', 'bool', None, None), ('yes', 'bool', None, None), ('1', 'bool', None, None),
    ('"true"', 'bool', None, None),
    ('"hi"', 'string', None, None), ('hi', 'string', None, None), ('"a b"', 'string', None, None),
    ('"a\\"b"', 'string', None, None), ('"a\\\\b"', 'string', None, None), ('{ a: 1 }', 'string', None, None),
    ('"x" "y"', 'string', None, None), ('x y', 'string', None, None),
    ('"a"', 'char', None, None), ('a', 'char', None, None), ('"ab"', 'char', None, None), ('', 'char', None, None),
    ('In', 'FadeID', FADE_OPTS, None), ('FadeID.In', 'FadeID', FADE_OPTS, None), ('Nope', 'FadeID', FADE_OPTS, None),
    ('"In"', 'FadeID', FADE_OPTS, None), ('A', 'FadeID', ['FadeID.A', 'B', 'C', 'D', 'E', 'F', 'G'], None),
    ('Foo', 'Thing', None, None), ('Foo.Bar', 'Thing', [], None), ('"x y"', 'Thing', None, None),
    ('{ x: 1, y: 2 }', 'Vector2', None, None), ('{ x: 1 }', 'Vector2', None, None), ('{ y: 2, x: 1 }', 'Vector2', None, None),
    ('{ x: 1, y: 2, z: 3 }', 'Vector2', None, None), ('{ x: 1, y: 2, z: 3 }', 'vector3', None, None),
    ('{ x: 1, y: 2, z: 3, w: 4 }', 'Vector4', None, None), ('(1, 2)', 'Vector2', None, None), ('1', 'Vector2', None, None),
    ('{ x: a, y: 2 }', 'Vector2', None, None), ('{ x: 1, y: 2', 'Vector2', None, None), ('{ x: 1 y: 2 }', 'Vector2', None, None),
    ('{ x: 1, x: 2, y: 3 }', 'Vector2', None, None), ('{ q: 1, x: 1, y: 2 }', 'Vector2', None, None),
    ('{ r: 1, g: 0.5, b: 0, a: 1 }', 'color', None, None), ('{ r: 1 }', 'color', None, None), ('{ r: x }', 'color', None, None),
    ('{ size: 8, bits: [0, 2, 5] }', 'bit', None, None), ('{ size: 8 }', 'bit', None, None), ('{ bits: [a] }', 'bit', None, None),
    ('{ points: [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 1, outTangent: 1 }] }', 'bezier', None, None),
    ('{ points: [] }', 'bezier', None, None), ('{ points: [{ time: 0 }] }', 'bezier', None, None),
    ('{"a":1,"b":[1,2],"c":{"d":null}}', 'dictionary', None, None), ('{a: 1}', 'dictionary', None, None), ('', 'dictionary', None, None),
    ('[1, 2]', 'dictionary', None, None), ('"x"', 'dictionary', None, None),
    ('[1, 2, 3]', 'int[]', None, None), ('[]', 'int[]', None, None), ('[1,,2]', 'int[]', None, None), ('1', 'int[]', None, None),
    ('[1, x]', 'int[]', None, None), ('["a", "b"]', 'string[]', None, None), ('[a]', 'string[]', None, None),
    ('[In, FadeID.Out]', 'FadeID[]', FADE_OPTS, None), ('[In, Bad]', 'FadeID[]', FADE_OPTS, None),
    ('[[1, 2], [3]]', 'int[][]', None, None), ('[{ x: 1, y: 2 }]', 'Vector2[]', None, None), ('[{ x: 1 }]', 'Vector2[]', None, None),
    ('[ ]', 'string[]', None, None), ('[1', 'int[]', None, None),
    ('{ add_position: { x: 0, y: 1 }, scale: 2 }', 'CharacterUI', None, 'UI'),
    ('{ add_position: { x: 0, y: 1 } }', 'CharacterUI', None, 'UI'),
    ('{ scale: 2, add_position: { x: 0, y: 1 }, nick: "n" }', 'CharacterUI', None, 'UI'),
    ('{ scale: x }', 'CharacterUI', None, 'UI'), ('{ unknown: 1 }', 'CharacterUI', None, 'UI'),
    ('{ scale: 1, scale: 2 }', 'CharacterUI', None, 'UI'), ('{ scale 1 }', 'CharacterUI', None, 'UI'),
    ('{ scale: }', 'CharacterUI', None, 'UI'), ('{ : 1 }', 'CharacterUI', None, 'UI'), ('{}', 'CharacterUI', None, 'UI'),
    ('x', 'CharacterUI', None, 'UI'), ('[1]', 'CharacterUI', None, 'UI'),
    ('[{ a: 1, n: "x", p: { x: 1, y: 2 } }, { a: 2 }]', 'Item[]', None, 'ITEM'),
    ('[{ a: 1 }, 3]', 'Item[]', None, 'ITEM'), ('{ a: 1 }', 'Item[]', None, 'ITEM'),
    ('{ a: 1, tag: "t", inner: { z: 1.5, flag: true }, pos: { x: 1, y: 2 } }', 'MyClass', None, None),
    ('{ inner: { z: bad } }', 'MyClass', None, None), ('{ "k": 1 }', 'Unknown', None, None), ('{ k: 1 }', 'Unknown', None, None),
    ('{"k": 1}', 'Unknown', None, None), ('{"k": ', 'Unknown', None, None),
    ('{ a: 1 }', 'Unknown2', None, [{'name': 'a', 'type': 'int'}]),
    (')', 'int', None, None), ('=', 'string', None, None), (',', 'string', None, None),
]
SUBS = {
    'UI': [{'name': 'add_position', 'type': 'Vector2'}, {'name': 'scale', 'type': 'float'}, {'name': 'nick', 'type': 'string'}],
    'ITEM': [{'name': 'a', 'type': 'int'}, {'name': 'n', 'type': 'string'}, {'name': 'p', 'type': 'Vector2'}],
}


class TestCoerce(DiffCase):
    def test_coerce_value_tokens(self):
        calls, pys = [], []
        for src, typ, opts, sub in COERCE_CASES:
            line = 'F ' + 'v=' + src
            toks = run_js(MOD, 'tokenizeLine', line)
            # 値トークン = 'v' '=' の後ろ全部(末尾コメントを除く)
            vtoks = [t for t in toks[3:] if t['type'] != 'COMMENT']
            sf = SUBS.get(sub, sub) if isinstance(sub, str) else sub
            calls.append(('coerceValueTokens', [vtoks, typ, opts, line, sf, CLASS_SCHEMAS]))
            pys.append((vtoks, typ, opts, line, sf, CLASS_SCHEMAS))
        js = js_batch(calls)
        for (src, typ, _, _), p, jv in zip(COERCE_CASES, pys, js):
            with self.subTest(src=src, type=typ):
                self.assertEqual(N(dsl.coerce_value_tokens(*p)), N(jv))

    def test_coerce_without_line_text(self):
        for src, typ in [('{"a":1}', 'dictionary'), ('{"a": 2}', 'Unknown')]:
            toks = [t for t in run_js(MOD, 'tokenizeLine', 'F v=' + src)[3:]]
            jv = run_js(MOD, 'coerceValueTokens', toks, typ, None, None, None, {})
            pv = dsl.coerce_value_tokens(toks, typ, None, None, None, {})
            self.assertEqual(N(pv), N(jv))

    def test_effective_sub_fields(self):
        # JS 非公開関数だが、結果は coerce の挙動を通じて上のテストで検証済み。形だけ確認する。
        self.assertEqual([f['name'] for f in dsl.get_effective_sub_fields('Vector2', None, {})], ['x', 'y'])
        self.assertEqual([f['name'] for f in dsl.get_effective_sub_fields('color[]', None, {})], ['r', 'g', 'b', 'a'])
        self.assertEqual([f['name'] for f in dsl.get_effective_sub_fields('MyClass', None, CLASS_SCHEMAS)], ['a', 'tag', 'inner', 'pos'])
        self.assertIsNone(dsl.get_effective_sub_fields('int', None, {}))


# ------------------------------------------------------------------ compile / decompile / lint
COMPILE_DOCS = [
    '',
    'Say text="hi"',
    'Say text="hi" speed=1.5 wait=true count=3 ch="a" fade=In text_id=4 voice=-1',
    'Say text="hi" fade=FadeID.Out',
    'Say text="hi" fade=Nope',
    'Say',
    'Say speed=1',
    'Say text="a" text="b"',
    'Say text="a" nope=1',
    'Say text=a',
    'Say text="a" count=x',
    'NoSuchRole a=1',
    'Say text="a"\nMove pos={ x: 1, y: 2 }\nSay text="b"\nBare\nBare x=1',
    'Move target={ x: 1, y: 2, z: 3 } pos={ x: 0, y: 0 } quat={ x: 0, y: 0, z: 0, w: 1 }',
    'Move col={ r: 1, g: 0.5, b: 0, a: 1 } bits={ size: 8, bits: [0, 2, 5] }',
    'Move curve={ points: [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 0, outTangent: 0 }] }',
    'Move ui={ add_position: { x: 1, y: 2 }, scale: 2, nick: "n" }',
    'Move dic={"a":1,"b":[1,2]} nums=[1, 2, 3] names=["a", "b"]',
    'Move items=[{ a: 1, n: "x", p: { x: 1, y: 2 } }, { a: 2, n: "y", p: { x: 0, y: 0 } }]',
    'Move fades=[In, Out] cd={ a: 1, tag: "t", inner: { z: 1.5, flag: true }, pos: { x: 1, y: 2 } }',
    'Move cds=[{ a: 1 }, { a: 2, tag: "q" }]',
    'Move ref=Alice', 'Move ref=Zed',
    'Move pos={ x: 1 }', 'Move pos={ x: 1, y: 2', 'Move nums=[1, a]',
    '# comment only\n\n   \nSay text="x" # trailing',
    'Say text="a #b"',
    'Say text="日本語 {name}" speed=0.25',
    'Say text="a" =\nSay text',
    'Say text="" voice=0',
    'Wait time=1\nWait time=2\nWait',
]
EXISTING = [
    {'name': 'Say', 'uniqueId': 'Say_1', 'id': 1, 'branchType': 'General', 'data': [], 'extra': {'keep': True}},
    {'name': 'Move', 'uniqueId': 'Move_1', 'id': 2, 'data': []},
    {'name': 'Say', 'uniqueId': 'Say_2', 'id': 1, 'data': []},
]


class TestCompile(DiffCase):
    def test_compile_document(self):
        self.compare('compileDocument', dsl.compile_document,
                     [[d, SCHEMAS, [], CLASS_SCHEMAS] for d in COMPILE_DOCS])

    def test_compile_with_existing(self):
        self.compare('compileDocument', dsl.compile_document,
                     [[d, SCHEMAS, EXISTING, CLASS_SCHEMAS] for d in COMPILE_DOCS])

    def test_compile_defaults(self):
        for d in ['Say text="x"', 'Move cd={ a: 1 }']:
            jv = run_js(MOD, 'compileDocument', d, SCHEMAS)
            pv = dsl.compile_document(d, SCHEMAS)
            self.assertEqual(N(pv), N(jv))

    def test_new_unique_id_format(self):
        r = dsl.compile_document('Say text="x"\nSay text="y"', SCHEMAS)['roles']
        self.assertEqual(len(r), 2)
        self.assertNotEqual(r[0]['uniqueId'], r[1]['uniqueId'])
        self.assertTrue(r[0]['uniqueId'].startswith('Say_'))
        self.assertEqual(r[0]['id'], 1)
        self.assertEqual(r[0]['branchType'], 'General')

    def test_decompile_roles(self):
        rolesets = []
        for d in COMPILE_DOCS:
            rolesets.append(dsl.compile_document(d, SCHEMAS, [], CLASS_SCHEMAS)['roles'])
        extra = [
            [{'name': 'Say', 'data': [{'name': 'text', 'value': 'a "q" \\ b'}, {'name': 'speed', 'value': None},
                                       {'name': 'count', 'value': None}, {'name': 'voice', 'value': None},
                                       {'name': 'text_id', 'value': None}, {'name': 'wait', 'value': None},
                                       {'name': 'fade', 'value': ''}, {'name': 'ch', 'value': None}]}],
            [{'name': 'Move', 'data': [{'name': 'pos', 'value': [1, 2]}, {'name': 'target', 'value': {'x': 1, 'z': 3}},
                                        {'name': 'quat', 'value': None}, {'name': 'col', 'value': {'r': 1}},
                                        {'name': 'bits', 'value': None}, {'name': 'curve', 'value': None},
                                        {'name': 'ui', 'value': None}, {'name': 'dic', 'value': None},
                                        {'name': 'nums', 'value': None}, {'name': 'items', 'value': [{'a': 1}, None]},
                                        {'name': 'cd', 'value': {'a': 1, 'inner': {'z': 2}}},
                                        {'name': 'ref', 'value': 'A B'}, {'name': 'fades', 'value': ['FadeID.In', 'x y']}]}],
            [{'name': 'Unknown', 'data': [{'name': 'f', 'type': 'int', 'value': 3}, {'name': 'g', 'value': 'zz'},
                                           {'name': 'h', 'type': 'Whatever', 'value': {'k': [1, 2]}}]}],
            [{'name': 'Move', 'data': [{'name': 'zz', 'type': 'dictionary', 'value': None},
                                        {'name': 'yy', 'type': 'Vector3', 'value': 7}]}],
            [{'name': 'Bare', 'data': []}, {'name': 'Bare'}],
            [],
        ]
        sets = rolesets + extra
        js = js_batch([('decompileRoles', [rs, SCHEMAS, CLASS_SCHEMAS]) for rs in sets])
        for rs, jv in zip(sets, js):
            with self.subTest(roles=repr(rs)[:160]):
                self.assertEqual(dsl.decompile_roles(rs, SCHEMAS, CLASS_SCHEMAS), jv)

    def test_decompile_null_and_default_schema(self):
        self.assertEqual(dsl.decompile_roles(None, {}), run_js(MOD, 'decompileRoles', None, {}))

    def test_round_trip(self):
        for d in COMPILE_DOCS:
            first = dsl.compile_document(d, SCHEMAS, [], CLASS_SCHEMAS)
            if any(x.severity == 'error' for x in first['diagnostics']):
                continue  # エラーのある入力は往復しない(値が欠けるため)
            roles = first['roles']
            text = dsl.decompile_roles(roles, SCHEMAS, CLASS_SCHEMAS)
            again = dsl.compile_document(text, SCHEMAS, [], CLASS_SCHEMAS)
            with self.subTest(doc=d[:80]):
                self.assertFalse(any(x.severity == 'error' for x in again['diagnostics']))
                # 不足サブフィールドは decompile で既定値が補われるので、2周目以降が不動点になることを確認する
                self.assertEqual(dsl.decompile_roles(again['roles'], SCHEMAS, CLASS_SCHEMAS), text)

    def test_lint_document(self):
        args = [[d, SCHEMAS, CLASS_SCHEMAS] for d in COMPILE_DOCS]
        self.compare('lintDocument', dsl.lint_document, args)

    def test_lint_with_setting(self):
        docs = COMPILE_DOCS + [
            '# ==== SUB:1 NODE:1 ====\n#@ is_wait_key=true delay=1\nSay text="x"',
            '#@ is_wait_key=maybe\n#@ nope=1',
            '#@ mode=A label="x"\n#@ mode=Z',
            '#@\n#@ ',
            '#@x=1\n#@ delay=',
            '  #@ delay=1',
            '#@ is_wait_key=true is_wait_key=false',
        ]
        self.compare('lintDocument', dsl.lint_document, [[d, SCHEMAS, CLASS_SCHEMAS, SETTING] for d in docs])


# ------------------------------------------------------------------ 設定行
SETTING_LINES = [
    '#@ is_wait_key=true', '#@', '#@ ', '#@\tx', '#@x', '# @ x', ' #@ x', '', None, '#@ a=1',
]


class TestSetting(DiffCase):
    def test_constants(self):
        self.assertEqual(dsl.SUBGROUP_SETTING_LINE_PREFIX, '#@')

    def test_is_setting_line(self):
        calls = [[l] for l in SETTING_LINES]
        js = js_batch([('isSubGroupSettingLine', c) for c in calls])
        for c, jv in zip(calls, js):
            self.assertEqual(dsl.is_sub_group_setting_line(c[0]), jv, c)

    def test_extract(self):
        bodies = [
            ['#@ a=1', 'Say x=1', '#@ b=2  ', '#@', '  #@ no'],
            [], None, ['Say'], ['#@\t a=1 '],
        ]
        self.compare('extractSubGroupSettingLines', dsl.extract_sub_group_setting_lines, [[b] for b in bodies])

    def test_compile_setting(self):
        lines = ['is_wait_key=true', 'is_wait_key=true delay=1.5', 'delay=x', 'mode=A', 'mode=SettingMode.B', 'mode=Q',
                 'label="hi"', 'label=hi', 'nope=1', '', 'is_wait_key=true is_wait_key=false', 'delay=1 delay=2', '=1']
        self.compare('compileSubGroupSetting', dsl.compile_sub_group_setting,
                     [[l, SETTING, CLASS_SCHEMAS] for l in lines])

    def test_normalize_setting(self):
        defaults = [{'name': 'is_wait_key', 'type': 'bool', 'value': True}, {'name': 'delay', 'value': 0.5},
                    {'name': 'mode', 'value': 'SettingMode.A'}, None]
        cur_sets = [
            None, [], [{'name': 'is_wait_key', 'value': False}], [{'name': 'delay', 'value': 0}, None],
            [{'name': 'mode', 'value': None}, {'name': 'label', 'value': 'x'}], 'bad',
            [{'name': 'is_wait_key', 'value': False}, {'name': 'delay', 'value': 2}, {'name': 'extra', 'value': 1}],
        ]
        args = []
        for c in cur_sets:
            for sch in (SETTING, None, {'fields': []}, {}):
                for dd in (defaults, None, []):
                    args.append([c, sch, dd])
        self.compare('normalizeSubGroupSetting', dsl.normalize_sub_group_setting, args)

    def test_decompile_setting(self):
        datas = [
            None, [], 'x',
            [{'name': 'is_wait_key', 'type': 'bool', 'value': True}],
            [{'name': 'is_wait_key', 'type': 'bool', 'value': False}, {'name': 'delay', 'value': 1.5},
             {'name': 'mode', 'value': 'SettingMode.B'}, {'name': 'label', 'value': 'a "b"'}],
            [{'name': 'delay', 'value': None}],
            [{'name': 'unknown', 'type': 'int', 'value': 4}],
        ]
        args = [[d, s, CLASS_SCHEMAS] for d in datas for s in (SETTING, None)]
        self.compare('decompileSubGroupSetting', dsl.decompile_sub_group_setting, args)

    def test_setting_round_trip(self):
        data = [{'name': 'is_wait_key', 'type': 'bool', 'value': True}, {'name': 'delay', 'type': 'float', 'value': 1.5}]
        line = dsl.decompile_sub_group_setting(data, SETTING)
        self.assertTrue(line.startswith('#@ '))
        got = dsl.compile_sub_group_setting(line[2:].strip(), SETTING)
        self.assertEqual([(d['name'], d['value']) for d in got['data']], [('is_wait_key', True), ('delay', 1.5)])


# ------------------------------------------------------------------ 補完
COMPLETION_TEXTS = [
    'Say text="hi" speed=1',
    'Say text="hi" fade=In wait=tr',
    'Move pos={ x: 1, y: 2 } ui={ add_position: { x: 0, y: 0 }, scale: 1 }',
    'Move ui={ add_position: { x: 0 }, sc',
    'Move items=[{ a: 1, n: "x" }, { a: 2 }] fades=[In, ',
    'Move col={ r: 1, g: 2 } bits={ size: 8, bits: [1, 2] } curve={ points: [{ time: 0, value: 1 }] }',
    'Move cd={ a: 1, inner: { z: 1, flag: tr } } cds=[{ tag: "a" }, { ',
    'Move ref=Al ref=',
    'Move dic={"a": 1} nums=[1, 2] names=["a"]',
    'Move target={ x: 1, y: 2, z: 3 } quat={ ',
    'Sa', 'Say ', 'Say t', 'Say text', 'Say text=', 'Say text="', 'Say fade=', 'Say fade=F', 'Say wait=', 'Say ch=',
    'Say text="a" ', 'Say text="a" s', 'Say text="a"  # c', '# comment Say', '', '   ', 'Move pos=', 'Move pos={', 'Move pos={ ',
    'Move pos={ x', 'Move pos={ x:', 'Move pos={ x: ', 'Move pos={ x: 1,', 'Move pos={ x: 1, ', 'Move ui={', 'Move ui={ nick: "a", ',
    'Wait time=', 'Wait t', 'No', 'Bare x=', 'Move fades=[', 'Move fades=[In', 'Move fades=[In,', 'Move items=[', 'Move items=[{',
    'Move items=[{ a: 1 },', 'Move items=[{ a: 1 }, {', 'Move nums=[', 'Move nums=[1,',
    '#@ ', '#@ is', '#@ is_wait_key=', '#@ is_wait_key=true ', '#@ mode=', '#@ mode=A de',
    'Say text="a"\nMove \n#@ de\nWait ',
    'Move ref=', 'Move ref=A', 'Move ref=GameCharacterID.',
]


class TestCompletions(DiffCase):
    def test_completions_every_position(self):
        args = []
        for t in COMPLETION_TEXTS:
            lines = t.split('\n')
            for li, ln in enumerate(lines):
                for ch in range(0, len(ln) + 1):
                    args.append([t, li, ch, ROLE_NAMES, SCHEMAS, CLASS_SCHEMAS, SETTING])
        self.assertGreater(len(args), 500)
        self.compare('getCompletionsAt', dsl.get_completions_at, args)

    def test_completions_without_setting(self):
        args = []
        for t in COMPLETION_TEXTS[:25]:
            lines = t.split('\n')
            for li, ln in enumerate(lines):
                for ch in range(0, len(ln) + 1, 2):
                    args.append([t, li, ch, ROLE_NAMES, SCHEMAS, CLASS_SCHEMAS])
        self.compare('getCompletionsAt', dsl.get_completions_at, args)

    def test_completions_defaults(self):
        for t, li, ch in [('Sa', 0, 2), ('Say text=', 0, 9), ('', 0, 0)]:
            jv = run_js(MOD, 'getCompletionsAt', t, li, ch, ROLE_NAMES, SCHEMAS)
            pv = dsl.get_completions_at(t, li, ch, ROLE_NAMES, SCHEMAS)
            self.assertEqual(N(pv), N(jv))

    def test_completions_out_of_range(self):
        for t, li, ch in [('Say', 5, 0), ('Say', -1, 0), ('Say', 0, 99), ('Say a=1', 0, -3)]:
            try:
                jv = run_js(MOD, 'getCompletionsAt', t, li, ch, ROLE_NAMES, SCHEMAS, CLASS_SCHEMAS, SETTING)
            except Exception:
                with self.assertRaises(Exception):
                    dsl.get_completions_at(t, li, ch, ROLE_NAMES, SCHEMAS, CLASS_SCHEMAS, SETTING)
                continue
            pv = dsl.get_completions_at(t, li, ch, ROLE_NAMES, SCHEMAS, CLASS_SCHEMAS, SETTING)
            self.assertEqual(N(pv), N(jv))


# ------------------------------------------------------------------ JS の非公開ヘルパー(Python 側が公開している分)の独自確認
class TestHelpers(unittest.TestCase):
    def test_increment_trailing_number(self):
        for v, e in [('1', '2'), ('9', '10'), ('009', '010'), ('a09', 'a10'), ('abc', 'abc_2'), ('', '_2'), ('x1y2', 'x1y3')]:
            self.assertEqual(dsl.increment_trailing_number(v), e)

    def test_serialize_value_matches_js_via_decompile(self):
        cases = [
            ('int', 3), ('float', 1.5), ('float', None), ('text_list_index', None), ('voice_ref', None), ('bool', True),
            ('bool', 0), ('string', 'a"b'), ('string', None), ('Thing', 'a b'), ('Thing', ''), ('Thing', 'x'), ('Thing', 'a=b'),
            ('dictionary', None), ('dictionary', {'a': [1, 2]}), ('Thing', {'k': 1}), ('Vector2', [1, 2]), ('Vector2', {'x': 3}),
            ('int[]', [1, 2]), ('string[]', ['a']), ('float', 0.1), ('float', 1e21), ('float', 1e-7), ('float', -0.0),
            ('float', 123456789012345680000), ('int', 1.0),
        ]
        sch = {'R': {'fields': [{'name': 'f', 'type': t} for t, _ in cases]}}
        # 1 フィールドずつ別 Role にして比較
        roles = [{'name': 'R', 'data': [{'name': 'f', 'type': t, 'value': v}]} for t, v in cases]
        schemas = {'R': None}
        js = js_batch([('decompileRoles', [[{'name': 'Q', 'data': [{'name': 'f', 'type': t, 'value': v}]}], {}, {}]) for t, v in cases])
        for (t, v), jv in zip(cases, js):
            pv = dsl.decompile_roles([{'name': 'Q', 'data': [{'name': 'f', 'type': t, 'value': v}]}], {}, {})
            with self.subTest(type=t, value=v):
                self.assertEqual(pv, jv)


if __name__ == '__main__':
    unittest.main()
