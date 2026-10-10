// scenarioDiff.js
//
// DSL(テキスト)を適用する前に見せる「変更内容の差分」を作る(React非依存)。
//   before: 現在のRole [{ uniqueId, name, data: [{name, value}, ...] }]
//   after : DSLをコンパイルした結果 [{ uniqueId, name, data }]
// 戻り値: { added, removed, changed, unchangedCount, totalChanges }
//   added   : [{ uniqueId, name, fields: [{ name, value }] }]
//   removed : [{ uniqueId, name }]
//   changed : [{ uniqueId, name, fields: [{ name, from, to }] }]   // 値が変わったフィールドだけ
//   順序の入れ替えだけでも「並び替え」として moved に入れる。

const stable = (v) => {
  if (v === undefined) return 'undefined';
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(stable).join(',')}]`;
  return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${stable(v[k])}`).join(',')}}`;
};

const toMap = (data) => {
  const m = new Map();
  (Array.isArray(data) ? data : []).forEach((d) => { if (d && d.name !== undefined) m.set(d.name, d.value); });
  return m;
};

/** 値を、差分表示用の短い文字列にする。 */
export function formatValue(v, max = 60) {
  if (v === undefined) return '(未設定)';
  let s;
  if (typeof v === 'string') s = `"${v}"`;
  else if (v && typeof v === 'object') s = JSON.stringify(v);
  else s = String(v);
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function diffRoles(before, after) {
  const beforeList = Array.isArray(before) ? before : [];
  const afterList = Array.isArray(after) ? after : [];
  const beforeById = new Map(beforeList.map((r) => [String(r.uniqueId), r]));
  const afterIds = new Set(afterList.map((r) => String(r.uniqueId)));

  const added = [];
  const changed = [];
  let unchangedCount = 0;

  afterList.forEach((r) => {
    const prev = beforeById.get(String(r.uniqueId));
    if (!prev) {
      added.push({
        uniqueId: r.uniqueId, name: r.name,
        fields: (r.data || []).map((d) => ({ name: d.name, value: d.value })),
      });
      return;
    }
    const a = toMap(prev.data);
    const b = toMap(r.data);
    const names = [...new Set([...a.keys(), ...b.keys()])];
    const fields = [];
    names.forEach((n) => {
      if (stable(a.get(n)) !== stable(b.get(n))) fields.push({ name: n, from: a.get(n), to: b.get(n) });
    });
    if (fields.length > 0 || prev.name !== r.name) {
      changed.push({ uniqueId: r.uniqueId, name: r.name, renamedFrom: prev.name !== r.name ? prev.name : undefined, fields });
    } else {
      unchangedCount += 1;
    }
  });

  const removed = beforeList
    .filter((r) => !afterIds.has(String(r.uniqueId)))
    .map((r) => ({ uniqueId: r.uniqueId, name: r.name }));

  // 並び順の変化(残っているRoleだけで比較)
  const keptBefore = beforeList.map((r) => String(r.uniqueId)).filter((id) => afterIds.has(id));
  const keptAfter = afterList.map((r) => String(r.uniqueId)).filter((id) => beforeById.has(id));
  const reordered = keptBefore.join('\u0000') !== keptAfter.join('\u0000');

  return {
    added, removed, changed, unchangedCount, reordered,
    totalChanges: added.length + removed.length + changed.length + (reordered ? 1 : 0),
  };
}
