// scenarioIndexTools.js
//
// text_list_index / voice_ref のような「Matrixの何番目か」を指す整数フィールドを、
// 複数のサブグループにまたがってまとめて調整するための計算(React非依存)。
// 元のMatrixで行が増減すると、参照側の番号がずれるため、「このサブグループ以降を +N する」
// 「このサブグループの値から連番にする」を手作業せずに行えるようにする。
//
//  ・GUI用: ノード配列(roles[].data = [{name, value, ...}])を対象にした計画/適用
//  ・DSL用: テキスト(見出し '# ==== SUB:x NODE:y ====' で区切られたセクション)を対象にした計画/適用
//  どちらも「計画(plan)」を作ってプレビューし、確認後に適用する(plan自体は何も書き換えない)。
//
// 変更の対象:
//  ・既定は型が text_list_index / voice_ref のフィールド。includeInt=true で int 系の型も対象にする。
//  ・負の値(-1 = 未選択)は変更しない(skipNegative 既定 true)。
//  ・配列の値は、数値の要素を1つずつ別の出現として扱う。
//  ・結果が負になる変更は適用せず、warnings に入れる(未選択と区別がつかなくなるため)。

import { tokenizeLine } from './scenarioTransactionDsl';

export const INDEX_TYPES = new Set(['text_list_index', 'voice_ref']);
export const INT_TYPES = new Set(['int', 'uint', 'short', 'long', 'byte']);

const typeOfField = (roleSchemas, roleName, fieldName) => {
  const schema = roleSchemas && roleSchemas[roleName];
  const f = schema && Array.isArray(schema.fields) ? schema.fields.find((x) => x && x.name === fieldName) : null;
  return f && f.type ? String(f.type).toLowerCase() : null;
};

const isTargetType = (type, includeInt) => !!type && (INDEX_TYPES.has(type) || (includeInt && INT_TYPES.has(type)));

const keyOf = (roleName, fieldName) => `${roleName}.${fieldName}`;

/** 対象にするフィールド指定: null/'all' = 対象型のすべて、{roleName, fieldName} = 1つだけ */
const matchesTarget = (target, roleName, fieldName) => (
  !target || target === 'all' || (target.roleName === roleName && target.fieldName === fieldName)
);

// ------------------------------------------------------------------
// GUI(ノード配列)
// ------------------------------------------------------------------

/** ノード配列に含まれる、調整対象になりうるフィールドの一覧: [{ roleName, fieldName, type, count }] */
export function collectIndexFields(nodes, roleSchemas, { includeInt = false } = {}) {
  const map = new Map();
  (nodes || []).forEach((node) => {
    ((node.data && node.data.roles) || []).forEach((role) => {
      (role.data || []).forEach((entry) => {
        if (!entry) return;
        const type = typeOfField(roleSchemas, role.name, entry.name);
        if (!isTargetType(type, includeInt)) return;
        const k = keyOf(role.name, entry.name);
        const cur = map.get(k) || { roleName: role.name, fieldName: entry.name, type, count: 0 };
        cur.count += Array.isArray(entry.value) ? entry.value.filter((v) => typeof v === 'number').length : (typeof entry.value === 'number' ? 1 : 0);
        map.set(k, cur);
      });
    });
  });
  return [...map.values()].filter((f) => f.count > 0).sort((a, b) => a.roleName.localeCompare(b.roleName) || a.fieldName.localeCompare(b.fieldName));
}

/** nodes を順に走り、対象フィールドの「出現」を列挙する。 */
function listOccurrences(nodes, roleSchemas, target, includeInt) {
  const occ = [];
  (nodes || []).forEach((node, nodeIndex) => {
    ((node.data && node.data.roles) || []).forEach((role) => {
      (role.data || []).forEach((entry, entryIndex) => {
        if (!entry || !matchesTarget(target, role.name, entry.name)) return;
        if (!isTargetType(typeOfField(roleSchemas, role.name, entry.name), includeInt)) return;
        const base = { nodeId: String(node.id), nodeIndex, roleUniqueId: role.uniqueId, roleName: role.name, fieldName: entry.name, entryIndex };
        if (typeof entry.value === 'number') occ.push({ ...base, arrayIndex: null, value: entry.value });
        else if (Array.isArray(entry.value)) {
          entry.value.forEach((v, arrayIndex) => { if (typeof v === 'number') occ.push({ ...base, arrayIndex, value: v }); });
        }
      });
    });
  });
  return occ;
}

/**
 * 調整の計画を作る(何も書き換えない)。
 * opts:
 *   startNodeId   : 起点のサブグループ(ノード)のID
 *   endNodeId     : 終点(含む)。省略で最後まで
 *   mode          : 'shift'(値に delta を足す) | 'sequence'(連番にする)
 *   delta         : shift の増減量(整数)
 *   includeStart  : 起点のノード自体も変更するか(shift 既定 true / sequence 既定 false)
 *   base          : sequence の開始値。省略時は「起点ノードの最後の出現の値」(includeStart=true のときは最初の出現の値)
 *   step          : sequence の増分(既定 1)
 *   target        : null/'all' | { roleName, fieldName }
 *   includeInt    : int系も対象にするか
 *   skipNegative  : 負の値を変更しない(既定 true)
 * 戻り値: { changes:[{nodeId, roleUniqueId, roleName, fieldName, entryIndex, arrayIndex, from, to}], warnings:[string], error?:string }
 */
export function planIndexAdjust(nodes, roleSchemas, opts) {
  const {
    startNodeId, endNodeId, mode = 'shift', delta = 0, step = 1, target = null,
    includeInt = false, skipNegative = true,
  } = opts || {};
  const includeStart = opts && opts.includeStart !== undefined ? opts.includeStart : mode === 'shift';
  const warnings = [];
  const list = nodes || [];
  const startIdx = list.findIndex((n) => String(n.id) === String(startNodeId));
  if (startIdx < 0) return { changes: [], warnings, error: '起点のサブグループが見つかりません' };
  let endIdx = list.length - 1;
  if (endNodeId !== undefined && endNodeId !== null && endNodeId !== '') {
    const e = list.findIndex((n) => String(n.id) === String(endNodeId));
    if (e < 0) return { changes: [], warnings, error: '終点のサブグループが見つかりません' };
    endIdx = e;
  }
  if (endIdx < startIdx) return { changes: [], warnings, error: '終点が起点より前にあります' };
  if (!Number.isInteger(Number(delta)) || !Number.isInteger(Number(step))) return { changes: [], warnings, error: '増減量・増分は整数で指定してください' };

  const occ = listOccurrences(list, roleSchemas, target, includeInt);
  const changes = [];
  const push = (o, to) => {
    if (to === o.value) return;
    if (to < 0) { warnings.push(`ノード${o.nodeId} ${o.roleName}.${o.fieldName}: ${o.value} → ${to} は負の値になるため変更しません`); return; }
    changes.push({ nodeId: o.nodeId, roleUniqueId: o.roleUniqueId, roleName: o.roleName, fieldName: o.fieldName, entryIndex: o.entryIndex, arrayIndex: o.arrayIndex, from: o.value, to });
  };

  if (mode === 'shift') {
    occ.forEach((o) => {
      if (o.nodeIndex < startIdx || o.nodeIndex > endIdx) return;
      if (o.nodeIndex === startIdx && !includeStart) return;
      if (skipNegative && o.value < 0) return;
      push(o, o.value + Number(delta));
    });
    return { changes, warnings };
  }

  // sequence: (Role名.フィールド名)ごとに独立した連番を作る
  const byKey = new Map();
  occ.forEach((o) => {
    const k = keyOf(o.roleName, o.fieldName);
    if (!byKey.has(k)) byKey.set(k, []);
    byKey.get(k).push(o);
  });
  byKey.forEach((items, k) => {
    const startItems = items.filter((o) => o.nodeIndex === startIdx && !(skipNegative && o.value < 0));
    let next;
    let first;
    if (opts.base !== undefined && opts.base !== null && opts.base !== '') {
      first = Number(opts.base);
      next = includeStart ? first : first + Number(step);
    } else if (startItems.length > 0) {
      first = (includeStart ? startItems[0] : startItems[startItems.length - 1]).value;
      next = includeStart ? first : first + Number(step);
    } else {
      warnings.push(`${k}: 起点のサブグループに値が無いため、開始値を決められません(開始値を指定してください)`);
      return;
    }
    if (!Number.isInteger(next)) { warnings.push(`${k}: 開始値が整数ではありません`); return; }
    items.forEach((o) => {
      if (o.nodeIndex < startIdx || o.nodeIndex > endIdx) return;
      if (o.nodeIndex === startIdx && !includeStart) return;
      if (skipNegative && o.value < 0) return;
      push(o, next);
      next += Number(step);
    });
  });
  return { changes, warnings };
}

/** plan.changes をノード配列に反映した、新しいノード配列を返す(元は変更しない。変更の無いノードは同じ参照)。 */
export function applyIndexChanges(nodes, changes) {
  const byNode = new Map();
  (changes || []).forEach((c) => {
    if (!byNode.has(c.nodeId)) byNode.set(c.nodeId, []);
    byNode.get(c.nodeId).push(c);
  });
  return (nodes || []).map((node) => {
    const list = byNode.get(String(node.id));
    if (!list) return node;
    const roles = ((node.data && node.data.roles) || []).map((role) => {
      const mine = list.filter((c) => String(c.roleUniqueId) === String(role.uniqueId));
      if (mine.length === 0) return role;
      const data = (role.data || []).map((entry, ei) => {
        const cs = mine.filter((c) => c.entryIndex === ei);
        if (cs.length === 0) return entry;
        if (Array.isArray(entry.value)) {
          const arr = entry.value.slice();
          cs.forEach((c) => { arr[c.arrayIndex] = c.to; });
          return { ...entry, value: arr };
        }
        return { ...entry, value: cs[0].to };
      });
      return { ...role, data };
    });
    return { ...node, data: { ...node.data, roles } };
  });
}

// ------------------------------------------------------------------
// DSL(テキスト)
// ------------------------------------------------------------------
const HEADER_RE = /^#\s*====\s*SUB:(\S+)\s+NODE:(\S+).*?====\s*$/;

/** 見出しで区切ったセクション一覧: [{ subId, pathKey, parentKey, headerLine, bodyStart, bodyEnd(含まない) }] */
export function splitSections(text) {
  const lines = String(text).split('\n');
  const heads = [];
  lines.forEach((line, i) => {
    const m = line.match(HEADER_RE);
    if (m) heads.push({ subId: m[1], pathKey: m[2], headerLine: i });
  });
  return heads.map((h, idx) => ({
    ...h,
    parentKey: h.pathKey.includes('/') ? h.pathKey.slice(0, h.pathKey.lastIndexOf('/')) : '',
    bodyStart: h.headerLine + 1,
    bodyEnd: idx + 1 < heads.length ? heads[idx + 1].headerLine : lines.length,
  }));
}

/** カーソル行(0始まり)が属するセクションと、同じ親(同じSUB・同じ親パス)を持つ兄弟セクション(出現順)を返す。 */
export function findSiblingSections(text, cursorLine) {
  const sections = splitSections(text);
  let cur = null;
  for (let i = sections.length - 1; i >= 0; i -= 1) {
    if (sections[i].headerLine <= cursorLine) { cur = sections[i]; break; }
  }
  if (!cur) return { current: null, siblings: [], sections };
  const siblings = sections.filter((s) => s.subId === cur.subId && s.parentKey === cur.parentKey);
  return { current: cur, siblings, sections };
}

/** 1行から、「フィールド=数値」の出現を取り出す。 [{ fieldName, roleName, from, to, value, listIndex }] (from/toは行内の文字位置) */
function scanLine(line) {
  const tokens = tokenizeLine(line);
  if (tokens.length === 0 || tokens[0].type !== 'IDENT') return [];
  const roleName = tokens[0].value;
  const out = [];
  for (let i = 1; i < tokens.length - 2; i += 1) {
    const k = tokens[i]; const eq = tokens[i + 1]; const v = tokens[i + 2];
    if (k.type !== 'IDENT' || eq.type !== 'EQUALS') continue;
    if (v.type === 'NUMBER' && /^-?\d+$/.test(v.value)) {
      out.push({ fieldName: k.value, roleName, from: v.from, to: v.to, value: Number(v.value), listIndex: null });
    } else if (v.type === 'LBRACKET') {
      // [1, 2, 3] のような数値の配列
      let j = i + 3; let li = 0;
      while (j < tokens.length && tokens[j].type !== 'RBRACKET') {
        if (tokens[j].type === 'NUMBER' && /^-?\d+$/.test(tokens[j].value)) {
          out.push({ fieldName: k.value, roleName, from: tokens[j].from, to: tokens[j].to, value: Number(tokens[j].value), listIndex: li });
          li += 1;
        } else if (tokens[j].type !== 'COMMA') { li += 1; }
        j += 1;
      }
    }
  }
  return out;
}

/**
 * DSLテキストに対する調整の計画。
 * cursorLine のセクションを起点とし、同じ親の中の「それ以降の兄弟セクション」が対象。
 * opts は GUI 版と同じ(startNodeId/endNodeId の代わりに cursorLine / endPathKey を使う)。
 * 戻り値: { changes:[{ line, from, to(文字位置), fromValue, toValue, roleName, fieldName, pathKey }], warnings, error? }
 */
export function planIndexAdjustInDsl(text, roleSchemas, opts) {
  const { cursorLine = 0, endPathKey, mode = 'shift', delta = 0, step = 1, target = null, includeInt = false, skipNegative = true } = opts || {};
  const includeStart = opts && opts.includeStart !== undefined ? opts.includeStart : mode === 'shift';
  const warnings = [];
  const { current, siblings } = findSiblingSections(text, cursorLine);
  if (!current) return { changes: [], warnings, error: 'カーソルがサブグループ(見出し)の中にありません' };
  const startIdx = siblings.findIndex((s) => s.headerLine === current.headerLine);
  let endIdx = siblings.length - 1;
  if (endPathKey) {
    const e = siblings.findIndex((s) => s.pathKey === endPathKey);
    if (e < 0) return { changes: [], warnings, error: '終点のサブグループが見つかりません' };
    endIdx = e;
  }
  if (endIdx < startIdx) return { changes: [], warnings, error: '終点が起点より前にあります' };
  if (!Number.isInteger(Number(delta)) || !Number.isInteger(Number(step))) return { changes: [], warnings, error: '増減量・増分は整数で指定してください' };

  const lines = String(text).split('\n');
  const occ = [];
  siblings.forEach((sec, secIndex) => {
    for (let li = sec.bodyStart; li < sec.bodyEnd; li += 1) {
      scanLine(lines[li]).forEach((o) => {
        if (!matchesTarget(target, o.roleName, o.fieldName)) return;
        if (!isTargetType(typeOfField(roleSchemas, o.roleName, o.fieldName), includeInt)) return;
        occ.push({ ...o, line: li, secIndex, pathKey: sec.pathKey });
      });
    }
  });

  const changes = [];
  const push = (o, to) => {
    if (to === o.value) return;
    if (to < 0) { warnings.push(`${o.pathKey} ${o.roleName}.${o.fieldName}: ${o.value} → ${to} は負の値になるため変更しません`); return; }
    changes.push({ line: o.line, from: o.from, to: o.to, fromValue: o.value, toValue: to, roleName: o.roleName, fieldName: o.fieldName, pathKey: o.pathKey });
  };

  if (mode === 'shift') {
    occ.forEach((o) => {
      if (o.secIndex < startIdx || o.secIndex > endIdx) return;
      if (o.secIndex === startIdx && !includeStart) return;
      if (skipNegative && o.value < 0) return;
      push(o, o.value + Number(delta));
    });
    return { changes, warnings };
  }

  const byKey = new Map();
  occ.forEach((o) => {
    const k = keyOf(o.roleName, o.fieldName);
    if (!byKey.has(k)) byKey.set(k, []);
    byKey.get(k).push(o);
  });
  byKey.forEach((items, k) => {
    const startItems = items.filter((o) => o.secIndex === startIdx && !(skipNegative && o.value < 0));
    let next;
    if (opts.base !== undefined && opts.base !== null && opts.base !== '') {
      const first = Number(opts.base);
      next = includeStart ? first : first + Number(step);
    } else if (startItems.length > 0) {
      const first = (includeStart ? startItems[0] : startItems[startItems.length - 1]).value;
      next = includeStart ? first : first + Number(step);
    } else {
      warnings.push(`${k}: 起点のサブグループに値が無いため、開始値を決められません(開始値を指定してください)`);
      return;
    }
    if (!Number.isInteger(next)) { warnings.push(`${k}: 開始値が整数ではありません`); return; }
    items.forEach((o) => {
      if (o.secIndex < startIdx || o.secIndex > endIdx) return;
      if (o.secIndex === startIdx && !includeStart) return;
      if (skipNegative && o.value < 0) return;
      push(o, next);
      next += Number(step);
    });
  });
  return { changes, warnings };
}

/** plan.changes をテキストへ反映した新しいテキストを返す(後ろの変更から適用するので位置がずれない)。 */
export function applyIndexChangesToDsl(text, changes) {
  const lines = String(text).split('\n');
  const byLine = new Map();
  (changes || []).forEach((c) => {
    if (!byLine.has(c.line)) byLine.set(c.line, []);
    byLine.get(c.line).push(c);
  });
  byLine.forEach((list, li) => {
    let s = lines[li];
    list.sort((a, b) => b.from - a.from).forEach((c) => { s = `${s.slice(0, c.from)}${c.toValue}${s.slice(c.to)}`; });
    lines[li] = s;
  });
  return lines.join('\n');
}

/** DSLテキストに含まれる、調整対象のフィールド一覧(UIの対象選択用): [{ roleName, fieldName, type, count }] */
export function collectIndexFieldsInDsl(text, roleSchemas, { includeInt = false } = {}) {
  const map = new Map();
  String(text).split('\n').forEach((line) => {
    scanLine(line).forEach((o) => {
      const type = typeOfField(roleSchemas, o.roleName, o.fieldName);
      if (!isTargetType(type, includeInt)) return;
      const k = keyOf(o.roleName, o.fieldName);
      const cur = map.get(k) || { roleName: o.roleName, fieldName: o.fieldName, type, count: 0 };
      cur.count += 1;
      map.set(k, cur);
    });
  });
  return [...map.values()].sort((a, b) => a.roleName.localeCompare(b.roleName) || a.fieldName.localeCompare(b.fieldName));
}
