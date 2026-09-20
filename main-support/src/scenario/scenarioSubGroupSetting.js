// scenarioSubGroupSetting.js
//
// サブグループ設定（ScenarioSubGroupSetting）のスキーマ取得と、値([{name,type,value}])の
// 読み書きヘルパー（React非依存）。
//
// 「サブグループ」= ロールを追加する各グループ。設定のフィールド定義は全イベント共通で、
// 組み込みの is_wait_key（入力待ち）を先頭に持つ。各ノードの値は
// node.data.subGroupSetting = [{ name, type, value }, ...] に保存される（roles[].data と同じ形）。
import { normalizeSubGroupSetting, decompileSubGroupSetting } from './scenarioTransactionDsl';

export const SUBGROUP_SETTING_NODE_KEY = 'subGroupSetting';
export const IS_WAIT_KEY_FIELD = 'is_wait_key';
export const SUBGROUP_SETTING_API = '/api/scenario-subgroup-setting';
export const SUBGROUP_SETTING_ROLE_NAME = 'ScenarioSubGroupSetting';

/**
 * 設定スキーマと、デフォルト値（手動デフォルト→自動デフォルト解決済み）を取得する。
 * 戻り値: { schema: {fields:[...]} | null, defaults: [{name,type,value}] }
 * 取得に失敗した場合は schema=null（呼び出し側は設定UIを出さずに従来どおり動く）。
 */
export async function fetchSubGroupSettingSchema() {
  const res = await fetch(`${SUBGROUP_SETTING_API}/form-schema`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const { schema, defaults } = await res.json();
  return {
    schema: schema && !schema.error && Array.isArray(schema.fields) ? schema : null,
    defaults: Array.isArray(defaults) ? defaults : [],
  };
}

/** ノードの設定値を、現在のスキーマの全フィールドへ揃える（無い項目はデフォルトで埋める）。 */
export function getNodeSetting(node, schema, defaults) {
  return normalizeSubGroupSetting(node?.data?.[SUBGROUP_SETTING_NODE_KEY], schema, defaults);
}

/** 設定値の中から、指定フィールドの値を取り出す。 */
export function getSettingValue(setting, name, fallback = undefined) {
  const found = (setting || []).find((d) => d && d.name === name);
  return found && found.value !== undefined && found.value !== null ? found.value : fallback;
}

/** 設定値の1フィールドだけを差し替えた、新しい設定値を返す（他フィールドは維持・スキーマ順）。 */
export function setSettingValue(setting, name, value, schema, defaults) {
  const base = normalizeSubGroupSetting(setting, schema, defaults);
  if (!base.some((d) => d.name === name)) return [...base, { name, type: undefined, value }];
  return base.map((d) => (d.name === name ? { ...d, value } : d));
}

/** BaseRoleInputForm が返す [{name,value,arraySize}] を、保存形式 [{name,type,value}] へ変換する。 */
export function formDataToSetting(formData, schema) {
  return (schema?.fields || []).map((f) => {
    const found = (formData || []).find((d) => d && d.name === f.name);
    return { name: f.name, type: f.type, value: found ? found.value : null };
  });
}

/** 新しいサブグループ(ノード)の初期設定値（デフォルト値のコピー）。 */
export function buildInitialSetting(defaults) {
  return (defaults || []).map((d) => ({ ...d }));
}

/** DSLで新しい見出しに添える、デフォルト値の設定行（'#@ is_wait_key=false ...'）。 */
export function buildDefaultSettingLine(schema, defaults, classDataSchemas = {}) {
  return decompileSubGroupSetting(defaults, schema, classDataSchemas);
}