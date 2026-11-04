"""BaseRoleInputForm.js (JSX を含むので Node で直接 import できない) から純粋関数を原文のまま切り出し、
js_ref/src/_gen_roleform.js を生成する。差分テスト用。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'js_ref', 'src')
OUT = os.path.join(SRC, '_gen_roleform.js')


def _cut(t, a, b):
    i = t.index(a)
    return t[i:t.index(b, i + len(a))]


def build():
    t = open(os.path.join(SRC, 'BaseRoleInputForm.js'), encoding='utf-8').read()
    parts = [
        _cut(t, 'const VECTOR_AXIS_LABELS', '// ====='),
        _cut(t, 'const stripSoundIdPrefix', '// /api/sound のレスポンスから'),
        _cut(t, 'const buildSoundLookup', '// セル(1つのシナリオ×言語)から'),
        _cut(t, 'const extractCellList', '// 試聴言語の選択は'),
        _cut(t, 'function toHex', 'const COLOR_DEFAULT'),
        _cut(t, 'const colorKey = ', '\nfunction getRecentColors'),
        _cut(t, 'function parseHexColor', '// カラーピッカーのドラッグ中は'),
        _cut(t, 'function hermite', '// タンジェントハンドルの画面上の長さ'),
        _cut(t, 'function defaultDictScalar', 'function DictionaryValueEditor'),
    ]
    gdv = _cut(t, '  const getDefaultValue = useCallback(', '  }, [enumValues, classDataSchemas, customClassSchemas]);')
    gdv = gdv.replace('const getDefaultValue = useCallback(', 'const getDefaultValue = (', 1) + '  });\n'
    dep = _cut(t, '  const isFieldEnabledByDependency', '  const formBody')
    out = '// 自動生成 (tests/gen_roleform_harness.py)。編集しない。\n' + '\n'.join(parts) + f"""
export {{ VECTOR_AXIS_LABELS, stripSoundIdPrefix, buildSoundLookup, extractCellList, toHex, colorKey, parseHexColor, hermite, defaultDictScalar }};
export const mkForm = (ctx) => {{
  const {{ enumValues, classDataSchemas, customClassSchemas, formData }} = ctx;
{gdv}
{dep}
  return {{ getDefaultValue, isFieldEnabledByDependency }};
}};
"""
    # buildSoundLookup は Map を返す。JSON 化できるよう、テスト側アダプタで Object.fromEntries する
    open(OUT, 'w', encoding='utf-8').write(out)
    return OUT


if __name__ == '__main__':
    print(build())
