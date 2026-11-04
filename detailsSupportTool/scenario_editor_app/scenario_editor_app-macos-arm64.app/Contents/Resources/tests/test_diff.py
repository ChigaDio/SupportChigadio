"""core/diff.py と scenarioDiff.js の差分テスト。"""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from jscompare import norm, run_js_adapter  # noqa: E402
from scenario_editor.core import diff  # noqa: E402

MOD = 'scenarioDiff'


def role(uid, name='Say', data=None):
    return {'uniqueId': uid, 'name': name, 'data': data if data is not None else []}


def f(name, value):
    return {'name': name, 'value': value}


class FormatValueTest(unittest.TestCase):
    VALUES = [
        'abc', '', 'あいう', 'a"b', 0, 1, -1, 1.5, 0.1, 1e21, 1e-7, 123456789012345680000, True, False, None,
        [1, 2, 3], [], {}, {'b': 1, 'a': [1, {'z': None}]}, {'10': 1, '2': 2, 'x': 3},
        'x' * 59, 'x' * 58, 'x' * 60, 'x' * 100, list(range(40)), '😀' * 30, '😀' * 29 + 'ab',
        {'text': 'あ' * 70},
    ]

    def test_format_value(self):
        cases = [[v] for v in self.VALUES] + [[v, m] for v in self.VALUES for m in (5, 10, 1, 2)]
        js = run_js_adapter(MOD, "(m, a) => m.formatValue(...a)", cases)
        for a, jv in zip(cases, js):
            with self.subTest(args=repr(a)[:100]):
                self.assertEqual(diff.format_value(*a), jv)

    def test_undefined(self):
        js = run_js_adapter(MOD, "(m, a) => m.formatValue(undefined)", [0])
        self.assertEqual(diff.format_value(diff.UNDEFINED), js[0])
        self.assertEqual(js[0], '(未設定)')

    def test_stable_is_key_order_independent(self):
        self.assertEqual(diff.stable({'a': 1, 'b': [1, {'y': 1, 'x': 2}]}), diff.stable({'b': [1, {'x': 2, 'y': 1}], 'a': 1}))
        self.assertNotEqual(diff.stable(None), diff.stable(diff.UNDEFINED))


class DiffRolesTest(unittest.TestCase):
    def check(self, cases):
        js = run_js_adapter(MOD, "(m, a) => m.diffRoles(a[0], a[1])", cases)
        for a, jv in zip(cases, js):
            with self.subTest(args=repr(a)[:300]):
                self.assertEqual(norm(diff.diff_roles(a[0], a[1])), norm(jv))

    def test_basic(self):
        a = [role('1', 'Say', [f('text', 'a'), f('n', 1)]), role('2', 'Move', [f('x', 1)]), role('3', 'Wait', [])]
        cases = [
            [a, a],
            [a, []],
            [[], a],
            [None, a], [a, None], [None, None], ['x', {'a': 1}],
            # 追加 / 削除 / 変更
            [a, [a[0], role('9', 'New', [f('k', 1)])]],
            [a, [role('1', 'Say', [f('text', 'b'), f('n', 1)]), a[1], a[2]]],
            # フィールド追加・削除 (undefined)
            [a, [role('1', 'Say', [f('text', 'a')]), a[1], a[2]]],
            [a, [role('1', 'Say', [f('text', 'a'), f('n', 1), f('extra', None)]), a[1], a[2]]],
            # 改名のみ
            [a, [role('1', 'Renamed', a[0]['data']), a[1], a[2]]],
            # 並べ替えのみ
            [a, [a[2], a[0], a[1]]],
            [a, [a[1], a[0]]],
            # uniqueId が数値と文字列
            [[role(1, 'A', [f('x', 1)])], [role('1', 'A', [f('x', 1)])]],
            [[role(1, 'A', [f('x', 1)])], [role(1.0, 'A', [f('x', 2)])]],
            # オブジェクト値(キー順違いは同じ)
            [[role('1', 'A', [f('o', {'a': 1, 'b': 2})])], [role('1', 'A', [f('o', {'b': 2, 'a': 1})])]],
            [[role('1', 'A', [f('o', [1, 2])])], [role('1', 'A', [f('o', [2, 1])])]],
            # null と未設定は別
            [[role('1', 'A', [f('o', None)])], [role('1', 'A', [])]],
            [[role('1', 'A', [{'name': 'o'}])], [role('1', 'A', [f('o', None)])]],
            # 重複 uniqueId / data 欠落 / name 欠落エントリ
            [[role('1', 'A', [f('x', 1)]), role('1', 'B', [f('x', 2)])], [role('1', 'A', [f('x', 1)])]],
            [[{'uniqueId': '1', 'name': 'A'}], [{'uniqueId': '1', 'name': 'A', 'data': None}]],
            [[role('1', 'A', [{'value': 1}, None, 5])], [role('1', 'A', [f('x', 1)])]],
            [[role('1', 'A', [f('x', 1), f('x', 2)])], [role('1', 'A', [f('x', 2)])]],
            # 数値表記
            [[role('1', 'A', [f('x', 1)])], [role('1', 'A', [f('x', 1.0)])]],
            [[role('1', 'A', [f('x', 0.1)])], [role('1', 'A', [f('x', 0.10000000000000001)])]],
            [[role('1', 'A', [f('x', 'あ')])], [role('1', 'A', [f('x', 'い')])]],
            # 追加Roleで data 無し / フィールド値なし
            [[], [{'uniqueId': 'n', 'name': 'N'}]],
            [[], [role('n', 'N', [{'name': 'a'}])]],
            # unique key 順(整数様)
            [[role('1', 'A', [f('o', {'10': 1, '2': 2})])], [role('1', 'A', [f('o', {'2': 2, '10': 1})])]],
        ]
        self.check(cases)

    def test_random(self):
        rnd = random.Random(20240601)
        vals = [None, 0, 1, 2, 'a', 'b', True, False, [1], [1, 2], {'k': 1}, {'k': 2}, 1.5, '']
        names = ['x', 'y', 'z', 'w']

        def rdata():
            return [f(rnd.choice(names), rnd.choice(vals)) for _ in range(rnd.randint(0, 4))]

        cases = []
        for _ in range(150):
            before = [role(str(rnd.randint(1, 6)), rnd.choice(['A', 'B']), rdata()) for _ in range(rnd.randint(0, 5))]
            after = []
            for r in before:
                p = rnd.random()
                if p < 0.15:
                    continue
                r2 = {**r, 'data': [dict(d) for d in r['data']]}
                if p < 0.4:
                    r2['data'] = rdata()
                if p < 0.5:
                    r2['name'] = 'C'
                after.append(r2)
            for _ in range(rnd.randint(0, 2)):
                after.append(role(str(rnd.randint(1, 8)), 'N', rdata()))
            rnd.shuffle(after) if rnd.random() < 0.3 else None
            cases.append([before, after])
        self.check(cases)

    def test_result_shape(self):
        a = [role('1', 'Say', [f('t', 'a')])]
        b = [role('1', 'Say', [f('t', 'b'), f('n', 1)])]
        r = diff.diff_roles(a, b)
        self.assertEqual(r['totalChanges'], 1)
        self.assertEqual(r['changed'][0]['fields'][0], {'name': 't', 'from': 'a', 'to': 'b'})
        self.assertIs(r['changed'][0]['fields'][1]['from'], diff.UNDEFINED)
        self.assertEqual(diff.format_value(r['changed'][0]['fields'][1]['from']), '(未設定)')


if __name__ == '__main__':
    unittest.main()
