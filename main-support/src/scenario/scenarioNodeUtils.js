// scenarioNodeUtils.js
//
// ノード配列に対する整理系の処理(React非依存)。
//  ・重複ID(同じ階層で同じidのノードが複数)の振り直し

const isNumericId = (id) => /^\d+$/.test(String(id));

/**
 * 同じ配列内でIDが重複しているノードのうち、2番目以降に新しい未使用IDを割り当てる。
 *  ・最初に現れたノードのIDはそのまま。
 *  ・新IDは「重複しているIDより大きい、最小の未使用の整数」(例: 5が重複 → 6、使用中なら7…)。
 *  ・数値でないIDは対象外(どう振るか判断できないため)。
 *  ・rekeySubgroups=true のとき、node.data.subgroups が「自分自身のID」をキーに持っていれば、
 *    新IDのキーへ付け替える(トップレベルのノードは、子ノードを自分のIDをキーにして保持しているため)。
 * 戻り値: { nodes, renamed: [{ index, from, to }], skipped: [id...] }  (変更が無ければ nodes は同じ参照)
 */
export function renumberDuplicateNodes(nodes, { rekeySubgroups = false } = {}) {
  const list = nodes || [];
  const used = new Set(list.map((n) => String(n.id)));
  const seen = new Set();
  const renamed = [];
  const skipped = [];
  const out = list.map((node, index) => {
    const id = String(node.id);
    if (!seen.has(id)) { seen.add(id); return node; }
    if (!isNumericId(id)) { if (!skipped.includes(id)) skipped.push(id); return node; }
    let n = Number(id) + 1;
    while (used.has(String(n))) n += 1;
    const newId = String(n);
    used.add(newId);
    seen.add(newId);
    renamed.push({ index, from: id, to: newId });
    let data = node.data;
    if (rekeySubgroups && data && data.subgroups && Object.prototype.hasOwnProperty.call(data.subgroups, id)) {
      const { [id]: moved, ...rest } = data.subgroups;
      data = { ...data, subgroups: { ...rest, [newId]: moved } };
    }
    return { ...node, id: newId, data };
  });
  return { nodes: renamed.length > 0 ? out : list, renamed, skipped };
}
