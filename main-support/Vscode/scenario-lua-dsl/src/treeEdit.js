// treeEdit.js
//
// ScenarioEventTransition.js の「全体編集(全Sub一括)」「Sub編集(現在のSubのみ)」で
// 使っているロジックをそのまま移植したもの。ノードツリー(nodes/edges JSON)の
// 走査・Lua形式テキストの組み立て・見出しでのセクション分割・ツリーへの適用は
// Web版と全く同じ挙動になるようにしてある(見出し記法・案内コメントの扱い・
// 新規グループ作成の可否など)。

const { decompileRoles, compileDocument } = require('./dslCore');

const ALL_EDIT_HEADER_RE = /^#\s*====\s*SUB:(\S+)\s+NODE:(\S+).*?====\s*$/;
// 「# 例: ...」で始まる行は、書き方の案内・記入例であり、実際の見出しや
// Transaction本文としては絶対に解釈しない(Web版と同じ安全策)。
const GUIDE_LINE_RE = /^#\s*例\s*[:：]/;

// node以下を再帰的に辿り、Roleを持ちうる全ノード(トップレベル + 入れ子のsubgroups)を収集する
function collectAllEditTargets(nodes, pathIds, out) {
  (nodes || []).forEach((node) => {
    const path = [...pathIds, String(node.id)];
    out.push({ path, node, label: node.description || '' });
    const subgroups = (node.data && node.data.subgroups) || {};
    Object.keys(subgroups).forEach((sgId) => {
      const innerNodes = (subgroups[sgId] && subgroups[sgId].nodes) || [];
      collectAllEditTargets(innerNodes, path, out);
    });
  });
}

// pathSegments(例: ['3','new1']) が指すノードを返す。存在しない場合は、
// 途中の階層も含めて新しいグループ/サブグループとして作成する。
function ensureAllEditNodePath(tree, pathSegments) {
  let list = tree.nodes;
  if (!Array.isArray(list)) { list = []; tree.nodes = list; }
  let node = null;
  for (let i = 0; i < pathSegments.length; i++) {
    const id = pathSegments[i];
    node = list.find((n) => String(n.id) === id);
    if (!node) {
      node = {
        id,
        description: '',
        position: { x: 120 + (list.length % 5) * 180, y: 120 + Math.floor(list.length / 5) * 140 },
        data: { roles: [] },
      };
      list.push(node);
    }
    if (i < pathSegments.length - 1) {
      node.data = node.data || {};
      node.data.subgroups = node.data.subgroups || {};
      const sgKey = String(node.id);
      node.data.subgroups[sgKey] = node.data.subgroups[sgKey] || { nodes: [], edges: [] };
      if (!Array.isArray(node.data.subgroups[sgKey].nodes)) node.data.subgroups[sgKey].nodes = [];
      list = node.data.subgroups[sgKey].nodes;
    }
  }
  return node;
}

// 指定した1つのSubのツリーから、Lua形式編集用のテキスト行を組み立てる。
// targetsOut には "subId::path" -> ノード の対応表を書き込む。
function buildEditLinesForSub(sid, tree, roleSchemas, targetsOut) {
  const lines = [];
  const targets = [];
  collectAllEditTargets(tree.nodes, [], targets);
  targets.forEach((t) => {
    const pathKey = t.path.join('/');
    targetsOut[`${sid}::${pathKey}`] = t.node;
    const labelSuffix = t.label ? ` (${t.label})` : '';
    lines.push(`# ==== SUB:${sid} NODE:${pathKey}${labelSuffix} ====`);
    const roles = (t.node.data && t.node.data.roles) || [];
    const bodyText = decompileRoles(roles, roleSchemas);
    if (bodyText) lines.push(bodyText);
    lines.push('');
  });
  lines.push(`# 例: 新しいグループを追加したい場合は、設定 scenarioLuaDsl.allowCreateNewGroups を`);
  lines.push(`# 例: 有効にしたうえで、下記のような見出しを書いてください（この案内行自体は無視されます）`);
  lines.push(`# 例: ==== SUB:${sid} NODE:新しいノードID ====`);
  lines.push(`# 例: ==== SUB:${sid} NODE:既存または新規の親ID/新しいサブグループのノードID ====`);
  lines.push('');
  return lines;
}

// Lua形式テキストをヘッダ行で分割し、セクション(見出し+本文)の配列にする。
// 案内・記入例コメント("# 例: ...")は見出しとしても本文としても解釈せず、読み飛ばす。
function parseEditSections(text) {
  const rawLines = text.split('\n');
  const sections = [];
  let current = null;
  rawLines.forEach((line) => {
    if (GUIDE_LINE_RE.test(line)) return;
    const m = line.match(ALL_EDIT_HEADER_RE);
    if (m) {
      if (current) sections.push(current);
      current = { subId: m[1], pathKey: m[2], bodyLines: [] };
    } else if (current) {
      current.bodyLines.push(line);
    }
  });
  if (current) sections.push(current);
  sections.sort((a, b) => a.pathKey.split('/').length - b.pathKey.split('/').length);
  return sections;
}

// セクション列を、対応するツリーへ実際に適用する。
// subTrees: { [subId]: {nodes, edges} } / targets: { "subId::path": node }
// allowNewGroups が false の場合、未知の見出しは作成せず警告に留める。
function applyEditSections(sections, subTrees, targets, roleSchemas, allowNewGroups) {
  const diagnostics = [];
  const touchedSubIds = new Set();

  for (const section of sections) {
    const key = `${section.subId}::${section.pathKey}`;
    let targetNode = targets[key];
    if (!targetNode) {
      const tree = subTrees[section.subId];
      if (!tree) {
        diagnostics.push({ message: `存在しないSubです: SUB:${section.subId}`, subId: section.subId, path: section.pathKey });
        continue;
      }
      if (!allowNewGroups) {
        diagnostics.push({
          message: `未知の見出しです（新しいグループは作成されません）: SUB:${section.subId} NODE:${section.pathKey} ／ 新しいグループを追加したい場合は設定 scenarioLuaDsl.allowCreateNewGroups を有効にしてください`,
          subId: section.subId, path: section.pathKey,
        });
        continue;
      }
      targetNode = ensureAllEditNodePath(tree, section.pathKey.split('/'));
      targets[key] = targetNode;
    }
    const existingRoles = (targetNode.data && targetNode.data.roles) || [];
    const { roles: compiledRoles, diagnostics: sectionDiagnostics } = compileDocument(
      section.bodyLines.join('\n'), roleSchemas, existingRoles
    );
    sectionDiagnostics
      .filter((d) => d.severity === 'error')
      .forEach((d) => diagnostics.push({
        message: `SUB:${section.subId} NODE:${section.pathKey} - ${d.message}`,
        subId: section.subId, path: section.pathKey,
      }));
    if (sectionDiagnostics.some((d) => d.severity === 'error')) continue;

    targetNode.data = targetNode.data || {};
    targetNode.data.roles = compiledRoles;
    touchedSubIds.add(section.subId);
  }

  return { diagnostics, touchedSubIds };
}

module.exports = {
  ALL_EDIT_HEADER_RE,
  GUIDE_LINE_RE,
  collectAllEditTargets,
  ensureAllEditNodePath,
  buildEditLinesForSub,
  parseEditSections,
  applyEditSections,
};
