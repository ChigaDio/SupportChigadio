"""ScenarioEventTransition.js(React コンポーネント)から純粋ロジックの部分を **原文のまま** 切り出して、
Node から呼べる ES モジュール (js_ref/src/_gen_transition.js) を生成する。差分テスト用。

切り出し範囲はマーカー文字列で決める(行番号に依存しない)。元の JS が変わってマーカーが見つからなければ例外。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'js_ref', 'src')
OUT = os.path.join(SRC, '_gen_transition.js')


def _cut(text, start, end, include_end=False):
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[a:b + (len(end) if include_end else 0)]


def build():
    t = open(os.path.join(SRC, 'ScenarioEventTransition.js'), encoding='utf-8').read()
    top_tint = _cut(t, 'const NODE_COLOR_PRESETS', '// ============================================================\n// フィールドの type 補完')
    with_types = _cut(t, 'const withFieldTypes', '// ============================================================\n// パフォーマンス用ヘルパー')
    next_id = _cut(t, 'const getNextNodeId', '// ============================================================\n// CSV入出力')
    csv = _cut(t, 'const CSV_COLUMNS', 'const exportTabToCsv')
    export_rows = _cut(t, '  const rows = [];\n  for (const node of tabData.nodes)', '  const csv = rowsToCsv(rows);')
    parse_csv_tab = _cut(t, 'const parseCsvToTabData', '// ============================================================\n// スキーマAPIキャッシュ')
    seg_a = _cut(t, '  const ALL_EDIT_HEADER_RE', '  // ローカルの roleDataCache / tabData 上の最新Roleデータを')
    seg_merge = _cut(t, '  const mergeLocalRoleDataIntoTree', '  // 指定した1つのSubのツリーから')
    seg_b = _cut(t, '  // 指定した1つのSubのツリーから', '  const handleOpenAllEditDialog')
    seg_sum = _cut(t, '  const summarizeChanges', '  const requestApplyAllEdit')
    # handleOpenAllEditDialog の直前までに applyEditSections が含まれる(seg_b に内包)
    out = f"""// 自動生成 (tests/gen_transition_harness.py)。編集しない。
import {{
  compileDocument, decompileRoles, decompileSubGroupSetting, compileSubGroupSetting, extractSubGroupSettingLines,
}} from './scenarioTransactionDsl.js';
import {{ getNodeSetting, buildInitialSetting, SUBGROUP_SETTING_NODE_KEY }} from './scenarioSubGroupSetting.js';
import {{ diffRoles }} from './scenarioDiff.js';

{top_tint}
{with_types}
{next_id}
{csv}
export {{ NODE_COLOR_PRESETS, hashHue, getNodeTint, withFieldTypes, getNextNodeId, rowsToCsv, parseCsv, parseCsvToTabData }};
export const exportRows = (tabData) => {{
{export_rows}
  return rows;
}};
{parse_csv_tab}
export const mkEdit = (ctx) => {{
  const {{ subGroupSettingSchema, subGroupSettingDefaults, classDataSchemas, roleFormSchemas,
          subId, isSub, parentId, roleDataCache }} = ctx;
  const currentTabData = ctx.currentTabData;
{seg_a}
{seg_merge}
{seg_b}
{seg_sum}
  return {{ collectAllEditTargets, ensureAllEditNodePath, mergeLocalRoleDataIntoTree, buildEditLinesForSub,
           parseEditSections, applyEditSections, summarizeChanges }};
}};
"""
    # parseCsvToTabData は上で定義済みの const を再 export しているので、二重定義にならないよう parse_csv_tab を除く
    out = out.replace(parse_csv_tab, '', 1) if out.count('const parseCsvToTabData') > 1 else out
    open(OUT, 'w', encoding='utf-8').write(out)
    return OUT


if __name__ == '__main__':
    print(build())
