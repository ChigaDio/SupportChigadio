// scenarioValidation.js
//
// シナリオの遷移グラフ(ノード/エッジ/Role)の整合性チェック(React非依存)。
// サーバー(scenario.py)のバイナリ生成の挙動に合わせて「出力が壊れる/意図とずれる」ものを見つける。
//   - ノードidは数値でなければ 0 として出力される(isdigit判定)        → 'non-numeric-id'
//   - 同じ階層でidが重複すると、同じIDのGroup/SubGroupが複数できる       → 'dup-node-id'
//   - Roleのデータ保存は uniqueId をキーにするため、欠落/重複は保存不能  → 'role-no-uid' / 'dup-role-uid'
//   - 定義が削除されたRoleが残っている                                    → 'role-undefined'
//   - Roleのフィールド定義と保存データのずれ                              → 'role-fields-missing' / 'role-fields-extra'
//   - 存在しないノードを指すエッジ                                        → 'dangling-edge'
// ※ エッジ(接続)はバイナリ生成では使われない(ノード順だけが出力される)ため、到達可能性などは検査しない。
//
// level: 'error'(出力が壊れる/保存できない) / 'warn'(意図とずれる可能性) / 'info'(参考)

const LEVEL_ORDER = { error: 0, warn: 1, info: 2 };

export const worstLevel = (issues) => {
  if (!issues || issues.length === 0) return null;
  return issues.reduce((w, i) => (LEVEL_ORDER[i.level] < LEVEL_ORDER[w] ? i.level : w), 'info');
};

const countInnerNodes = (node) => {
  const sgs = (node && node.data && node.data.subgroups) || {};
  return Object.values(sgs).reduce((n, sg) => n + ((sg && sg.nodes) ? sg.nodes.length : 0), 0);
};

/**
 * @param nodes   ノード配列
 * @param edges   エッジ配列
 * @param ctx     { isSub, roleNames?: Set<string>|null, roleSchemas?: {[roleName]: {fields:[{name}]}} }
 * @returns { byNode: {[nodeId]: Issue[]}, edgeIssues: Issue[], counts: {error,warn,info}, total }
 *          Issue = { level, code, message }
 */
export function validateGraph(nodes, edges, ctx = {}) {
  const { isSub = false, roleNames = null, roleSchemas = {} } = ctx;
  const byNode = {};
  const add = (id, level, code, message) => {
    (byNode[id] = byNode[id] || []).push({ level, code, message });
  };

  const idCount = new Map();
  nodes.forEach((n) => idCount.set(String(n.id), (idCount.get(String(n.id)) || 0) + 1));

  const dupReported = new Set(); // 同じIDの重複は1件として数える(byNode はIDをキーにするため)
  nodes.forEach((n) => {
    const id = String(n.id);
    if (idCount.get(id) > 1 && !dupReported.has(id)) {
      dupReported.add(id);
      add(id, 'error', 'dup-node-id', `ID "${id}" が同じ階層で重複しています`);
    }
    if (!/^\d+$/.test(id)) add(id, 'warn', 'non-numeric-id', `ID "${id}" は数値ではないため、出力では 0 になります`);

    const roles = (n.data && n.data.roles) || [];
    const uidCount = new Map();
    roles.forEach((r) => {
      const uid = r.uniqueId;
      if (uid === undefined || uid === null || uid === '') {
        add(id, 'error', 'role-no-uid', `Role「${r.name}」に uniqueId がありません（データを保存できません）`);
      } else {
        uidCount.set(String(uid), (uidCount.get(String(uid)) || 0) + 1);
      }
    });
    uidCount.forEach((c, uid) => {
      if (c > 1) add(id, 'error', 'dup-role-uid', `uniqueId "${uid}" のRoleが ${c} 件あります（保存時に取り違えます）`);
    });

    roles.forEach((r) => {
      if (roleNames && roleNames.size > 0 && !roleNames.has(r.name)) {
        add(id, 'error', 'role-undefined', `Role「${r.name}」の定義が見つかりません（削除された可能性）`);
        return;
      }
      const schema = roleSchemas[r.name];
      if (!schema || !Array.isArray(schema.fields)) return;
      const have = new Set((r.data || []).map((d) => d && d.name));
      const want = new Set(schema.fields.map((f) => f.name));
      const missing = [...want].filter((x) => !have.has(x));
      const extra = [...have].filter((x) => x !== undefined && !want.has(x));
      if (missing.length > 0) {
        add(id, 'info', 'role-fields-missing', `Role「${r.name}」に未保存のフィールド: ${missing.slice(0, 5).join(', ')}${missing.length > 5 ? ' …' : ''}`);
      }
      if (extra.length > 0) {
        add(id, 'info', 'role-fields-extra', `Role「${r.name}」に定義に無いフィールド: ${extra.slice(0, 5).join(', ')}${extra.length > 5 ? ' …' : ''}`);
      }
    });

    if (roles.length === 0 && (isSub || countInnerNodes(n) === 0)) {
      add(id, 'info', 'empty-node', 'Roleがありません');
    }
  });

  const idSet = new Set(nodes.map((n) => String(n.id)));
  const edgeIssues = [];
  (edges || []).forEach((e) => {
    if (!idSet.has(String(e.source)) || !idSet.has(String(e.target))) {
      edgeIssues.push({ level: 'warn', code: 'dangling-edge', message: `接続 ${e.source} → ${e.target} の端が存在しません` });
    }
  });

  const counts = { error: 0, warn: 0, info: 0 };
  Object.values(byNode).forEach((list) => list.forEach((i) => { counts[i.level] += 1; }));
  edgeIssues.forEach((i) => { counts[i.level] += 1; });
  return { byNode, edgeIssues, counts, total: counts.error + counts.warn + counts.info };
}
