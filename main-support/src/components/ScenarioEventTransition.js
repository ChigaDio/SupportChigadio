import React, {
  useState, useEffect, useCallback, useMemo, useRef
} from 'react';
import { useParams } from 'react-router-dom';
import {
  Box, Button, Typography, IconButton, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, Tabs, Tab, AppBar,
  Accordion, AccordionSummary, AccordionDetails,
  Backdrop, CircularProgress, Chip, Tooltip, Paper, Divider,
  Alert, Snackbar, InputAdornment, List, ListItem, ListItemButton,
  ListItemText, Drawer, Badge, Menu, MenuItem, Select, FormControl,
  InputLabel, Stack, Checkbox, FormControlLabel
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import CloseIcon from '@mui/icons-material/Close';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ContentPasteIcon from '@mui/icons-material/ContentPaste';
import EditIcon from '@mui/icons-material/Edit';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import SaveIcon from '@mui/icons-material/Save';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import FileUploadIcon from '@mui/icons-material/FileUpload';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import LinkIcon from '@mui/icons-material/Link';
import LinkOffIcon from '@mui/icons-material/LinkOff';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import RefreshIcon from '@mui/icons-material/Refresh';
import EditNoteIcon from '@mui/icons-material/EditNote';
import RoleInputFactory from '../scenario/RoleInputFactory';
import ScenarioTransactionCodeEditor from '../scenario/ScenarioTransactionCodeEditor';
import { compileDocument, decompileRoles } from '../scenario/scenarioTransactionDsl';
import { debounce } from 'lodash';

// ============================================================
// SnackBar hook
// ============================================================
const useSnack = () => {
  const [snack, setSnack] = useState({ open: false, msg: '', severity: 'success' });
  const show = (msg, severity = 'success') => setSnack({ open: true, msg, severity });
  const hide = () => setSnack(s => ({ ...s, open: false }));
  return { snack, show, hide };
};

// ============================================================
// ID採番ユーティリティ
// ============================================================
const getNextNodeId = (nodes) => {
  const ids = nodes.map(n => parseInt(n.id, 10)).filter(n => !isNaN(n));
  return ids.length > 0 ? (Math.max(...ids) + 1).toString() : '1';
};

// ============================================================
// CSV入出力(項目10)
// ノードとエッジをまとめて1つのCSVに書き出す/読み込む。
// 1列目(type)で "node" / "edge" を区別する。
// 説明文などに含まれる改行・カンマ・ダブルクォートは
// RFC4180準拠でクォート/エスケープする。
// ============================================================
const CSV_COLUMNS = ['type', 'id', 'description', 'roleIds', 'x', 'y', 'source', 'target', 'sourceHandle', 'targetHandle'];

const csvEscapeCell = (value) => {
  const str = value === undefined || value === null ? '' : String(value);
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
};

const rowsToCsv = (rows) => {
  const lines = [CSV_COLUMNS.join(',')];
  for (const row of rows) {
    lines.push(CSV_COLUMNS.map(col => csvEscapeCell(row[col])).join(','));
  }
  return lines.join('\r\n');
};

// シンプルなRFC4180 CSVパーサ(クォート内の改行・エスケープ済みダブルクォートに対応)
const parseCsv = (text) => {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else { inQuotes = false; }
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      row.push(field); field = '';
    } else if (ch === '\r') {
      // \r\n の \r は無視、\n側で行確定
    } else if (ch === '\n') {
      row.push(field); field = '';
      rows.push(row); row = [];
    } else {
      field += ch;
    }
  }
  if (field.length > 0 || row.length > 0) { row.push(field); rows.push(row); }
  return rows.filter(r => r.length > 1 || (r.length === 1 && r[0] !== ''));
};

const exportTabToCsv = (tabData, tabId) => {
  const rows = [];
  for (const node of tabData.nodes) {
    rows.push({
      type: 'node',
      id: node.id,
      description: node.data?.description || '',
      roleIds: (node.data?.roles || []).map(r => r.roleId ?? r.id ?? '').join(';'),
      x: node.position?.x ?? 0,
      y: node.position?.y ?? 0,
      source: '', target: '', sourceHandle: '', targetHandle: '',
    });
  }
  for (const edge of tabData.edges) {
    rows.push({
      type: 'edge',
      id: edge.id || '',
      description: '', roleIds: '', x: '', y: '',
      source: edge.source, target: edge.target,
      sourceHandle: edge.sourceHandle || '', targetHandle: edge.targetHandle || '',
    });
  }
  const csv = rowsToCsv(rows);
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `scenario_${tabId}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

// CSVの内容から { nodes, edges } を再構築する。
// 既存のノード/ロール構造を壊さないよう、description/position/roleIds のみ
// CSVから復元し、roles配列自体は roleId のみの最小構成で再構築する
// (詳細なroleデータはRoleDataDrawer側で個別に読み直される想定)。
const parseCsvToTabData = (text) => {
  const table = parseCsv(text);
  if (table.length === 0) return { nodes: [], edges: [] };
  const header = table[0];
  const colIndex = {};
  header.forEach((h, i) => { colIndex[h.trim()] = i; });
  const get = (row, col) => (colIndex[col] !== undefined ? (row[colIndex[col]] ?? '') : '');

  const nodes = [];
  const edges = [];
  for (const row of table.slice(1)) {
    const type = get(row, 'type');
    if (type === 'node') {
      const id = get(row, 'id');
      if (!id) continue;
      const roleIds = get(row, 'roleIds');
      nodes.push({
        id,
        type: 'customGroup',
        position: { x: parseFloat(get(row, 'x')) || 0, y: parseFloat(get(row, 'y')) || 0 },
        data: {
          label: id,
          description: get(row, 'description'),
          roles: roleIds ? roleIds.split(';').filter(Boolean).map(roleId => ({ roleId, uniqueId: `${id}_${roleId}` })) : [],
          subgroups: {},
        },
        draggable: true,
      });
    } else if (type === 'edge') {
      const source = get(row, 'source');
      const target = get(row, 'target');
      if (!source || !target) continue;
      edges.push({
        id: get(row, 'id') || `e-${source}-${target}`,
        source, target,
        sourceHandle: get(row, 'sourceHandle') || undefined,
        targetHandle: get(row, 'targetHandle') || undefined,
      });
    }
  }
  // 存在しないノードを参照するエッジは除外(不整合防止)
  const nodeIds = new Set(nodes.map(n => n.id));
  const validEdges = edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
  return { nodes, edges: validEdges };
};

// ============================================================
// スキーマAPIキャッシュ（連続呼び出しバグ修正）
// モジュールレベルのキャッシュで同一リクエストの重複排除
// ============================================================
const schemaCache = {};
const schemaInFlight = {};

const fetchSchemaOnce = async (roleName, forceRefresh = false) => {
  // forceRefresh=true のときはキャッシュを無視して必ずサーバーから取り直す。
  // Role定義(型・options)を編集した直後にこのページを開いたまま戻ってきても、
  // 古いスキーマのままにならないようにするため。
  if (!forceRefresh) {
    if (schemaCache[roleName]) return schemaCache[roleName];
    if (schemaInFlight[roleName]) return schemaInFlight[roleName];
  }
  schemaInFlight[roleName] = fetch(`/api/role-form-schema/${roleName}`)
    .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
    .then(schema => { schemaCache[roleName] = schema; delete schemaInFlight[roleName]; return schema; })
    .catch(err => { delete schemaInFlight[roleName]; throw err; });
  return schemaInFlight[roleName];
};

// Role定義(型・bit/color/bezierのoptionsなど)を編集した後、キャンバス側の
// roleFormSchemas(Reactステート)にも古いスキーマが残ってしまうことがあるため、
// 手動で再取得したい場合にモジュールキャッシュ側を明示的に破棄できるようにする。
const invalidateRoleSchemaCache = (roleName) => {
  delete schemaCache[roleName];
  delete schemaInFlight[roleName];
};

// ============================================================
// 接続線SVGコンポーネント（ブロック間の矢印）
// ============================================================
const ConnectionArrows = ({ nodes, edges }) => {
  if (!nodes.length || !edges.length) return null;
  const nodeMap = {};
  nodes.forEach(n => { nodeMap[n.id] = n; });

  return (
    <Box sx={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }}>
      {edges.map((edge, i) => {
        const src = nodeMap[edge.source];
        const tgt = nodeMap[edge.target];
        if (!src || !tgt) return null;
        return (
          <Box key={i} sx={{
            position: 'absolute',
            top: '50%',
            left: 0,
            display: 'flex',
            alignItems: 'center',
            color: 'cyan',
            fontSize: '0.6rem',
            whiteSpace: 'nowrap',
          }}>
            <ArrowForwardIcon sx={{ fontSize: 14, color: 'cyan' }} />
            <Typography variant="caption" sx={{ color: 'cyan', ml: 0.25 }}>
              {edge.source}→{edge.target}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
};

// ============================================================
// 接続バッジ（ノードの接続先表示）
// ============================================================
const ConnectionBadge = ({ nodeId, edges, onRemove }) => {
  const outgoing = edges.filter(e => e.source === nodeId);
  const incoming = edges.filter(e => e.target === nodeId);
  if (!outgoing.length && !incoming.length) return null;
  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.4, mt: 0.5 }}>
      {incoming.map(e => (
        <Chip key={`in-${e.source}`} size="small"
          label={`←${e.source}`}
          onDelete={() => onRemove(e)}
          sx={{ height: 18, fontSize: '0.6rem', bgcolor: 'purple.100', color: 'purple.800' }} />
      ))}
      {outgoing.map(e => (
        <Chip key={`out-${e.target}`} size="small"
          label={`→${e.target}`}
          onDelete={() => onRemove(e)}
          sx={{ height: 18, fontSize: '0.6rem', bgcolor: 'cyan.100', color: 'cyan.800' }} />
      ))}
    </Box>
  );
};

// ============================================================
// RoleDataDrawer（データ入力専用Drawer）
// ============================================================
const RoleDataDrawer = ({
  open, onClose, nodeId, roles, formDataState, setFormDataState,
  roleFormSchemas, eventId, subId, onSave, onDeleteRole, onAddRole, flushStructureSave
}) => {
  const [roleForms, setRoleForms] = useState({});
  const [formErrors, setFormErrors] = useState({});
  const [loadingForms, setLoadingForms] = useState({});
  const { snack, show: showSnack, hide: hideSnack } = useSnack();
  const loadedRef = useRef({});

  // ── テキスト(DSL)モード ──
  // 「上から順にRoleを追加していく」GUI入力は残しつつ、迅速な入力向けに
  // テキストDSL（1行1Role呼び出し）での編集モードを追加している。
  // scenarioTransactionDsl.js が唯一の文法定義であり、シンタックス
  // ハイライト・リンター・オートコンプリートもそこを共通の情報源として使う。
  const [inputMode, setInputMode] = useState('gui'); // 'gui' | 'text'
  const [dslText, setDslText] = useState('');
  const [dslDiagnostics, setDslDiagnostics] = useState([]);
  const [applying, setApplying] = useState(false);

  const switchToTextMode = () => {
    const rolesForDsl = roles.map((r) => ({
      uniqueId: r.uniqueId,
      name: r.name,
      data: formDataState[r.uniqueId] || r.data || [],
    }));
    setDslText(decompileRoles(rolesForDsl, effectiveSchemas));
    setDslDiagnostics([]);
    setInputMode('text');
  };

  const switchToGuiMode = () => {
    if (dslDiagnostics.some((d) => d.severity !== 'warning')) {
      if (!window.confirm('未適用のエラーがあります。GUIモードへ切り替えると、テキストの変更内容は破棄されます。よろしいですか？')) {
        return;
      }
    }
    setInputMode('gui');
  };

  const handleApplyDsl = async () => {
    const { roles: compiledRoles, diagnostics } = compileDocument(dslText, effectiveSchemas, roles);
    setDslDiagnostics(diagnostics);
    const hasError = diagnostics.some((d) => d.severity === 'error');
    if (hasError) {
      showSnack('エラーがあるため適用できません。赤波線の箇所を確認してください。', 'error');
      return;
    }

    setApplying(true);
    try {
      const existingIds = new Set(roles.map((r) => r.uniqueId));
      const compiledIds = new Set(compiledRoles.map((r) => r.uniqueId));
      const hasNewRole = compiledRoles.some((r) => !existingIds.has(r.uniqueId));

      // 削除された行（既存にあったが、テキストから消えたRole呼び出し）
      roles.forEach((r) => {
        if (!compiledIds.has(r.uniqueId)) onDeleteRole(r.uniqueId);
      });

      // 新規追加された行（既存に無かった新しいRole呼び出し）
      compiledRoles.forEach((r) => {
        if (!existingIds.has(r.uniqueId)) {
          onAddRole({ uniqueId: r.uniqueId, id: r.uniqueId, name: r.name, branchType: 'General', data: [] });
        }
      });

      // ── バグ修正: 新規Role行の値が保存されない問題 ──
      // onAddRoleによるノード構造(roles一覧)への追加は、通常は
      // scheduleSave()経由の「デバウンスされた自動保存」でサーバーへ
      // 反映される(600ms後)。一方、直後に呼んでいたonSave(=
      // /api/save-role-data/...)はサーバー側の該当ノードに「そのuniqueId
      // のRoleが既に存在する」前提で値を書き込むため、自動保存が間に
      // 合っていないタイミングでは新規Roleの値が保存されずに消えていた。
      // → 新規行が1つでもあれば、フィールド値の保存を行う前に構造の
      //   保存を即時実行・完了を待ってから進める。
      if (hasNewRole && flushStructureSave) {
        await flushStructureSave();
      }

      // 各Roleのフィールド値を反映（新規・既存とも）
      const nextFormDataState = { ...formDataState };
      compiledRoles.forEach((r) => {
        nextFormDataState[r.uniqueId] = r.data;
      });
      compiledRoles.forEach((r) => {
        if (!existingIds.has(r.uniqueId)) delete loadedRef.current[r.uniqueId]; // 新規分はフォームを再読み込みさせる
      });
      setFormDataState(nextFormDataState);
      compiledRoles.forEach((r) => onSave(r.uniqueId, r.data));

      showSnack(`テキストの内容を適用しました（${compiledRoles.length}件）`);
      setInputMode('gui');
    } finally {
      setApplying(false);
    }
  };

  // ── Role定義の最新化（テキストDSL用） ──
  // GUIモードの各Roleフォームは、Drawerを開くたびに fetchSchemaOnce(name, true) で
  // 強制的に最新スキーマを取ってきている(下のuseEffect)。だが、そこで取得した
  // 最新スキーマは従来「フォームコンポーネントの生成」にしか使われておらず、
  // テキストDSL側(roleNamesForDsl / switchToTextMode / handleApplyDsl / 予測変換)は
  // 親から渡された roleFormSchemas prop（マウント時にキャッシュされたまま更新されない）
  // をそのまま使っていたため、「Roleに新しい変数を追加した直後にLua記法で書いても
  // その変数が出てこない」「新しく作ったRoleを追加してすぐLua記法を使おうとしても
  // 補完が一切出ない」という不具合が起きていた。
  // → ここで取得した最新スキーマを freshSchemas に貯め、DSL側はこちらを優先して使う。
  const [freshSchemas, setFreshSchemas] = useState({});
  // effectiveSchemas / roleNamesForDsl は、スプレッド演算子やmap()で毎レンダー
  // 新しいオブジェクト/配列を作ってしまうと、ScenarioTransactionCodeEditorの
  // extensions(useMemo)の依存配列が毎回変化してしまい、1文字入力するたびに
  // CodeMirrorの拡張機能(リンター・補完)がまるごと再構築されてキー入力が
  // もたつく原因になる。roleFormSchemas/freshSchemasの中身が変わった時だけ
  // 再生成されるようメモ化する。
  const effectiveSchemas = useMemo(
    () => ({ ...roleFormSchemas, ...freshSchemas }),
    [roleFormSchemas, freshSchemas]
  );

  // ── フォームの初期化完了フラグ ──
  // BaseRoleInputFormは、propsのinitialDataを元に「既存値 → 保存済みデフォルト値 →
  // 型の汎用初期値」の優先順位で最終的な値を組み立ててから、初回に一度onChangeを
  // 呼んで親(このコンポーネント)のformDataStateへ反映する（非同期）。
  // この初期化が完了する前に「保存」ボタンを押すと、formDataStateにはまだ
  // roleDataCache由来の(新規Roleなら空の)値しか入っておらず、その空データで
  // 上書き保存してしまっていた。これが「保存ボタンが1回目は効かない
  // （＝空で保存される）。データを一部変更して初めてformDataStateに実データが
  // 入るので、2回目以降はちゃんと保存される」という不具合の原因だった。
  // → 初期化完了(＝最初のonChange)まではformReady[uid]をfalseにし、保存ボタンを
  // 無効化することで、空データでの保存を防ぐ。
  const [formReady, setFormReady] = useState({});

  const roleNamesForDsl = useMemo(
    () => Object.keys(effectiveSchemas || {}),
    [effectiveSchemas]
  );

  // ロールフォーム読み込み（重複防止）
  useEffect(() => {
    if (!open || !roles.length) return;
    roles.forEach(async (role) => {
      const uid = role.uniqueId;
      if (loadedRef.current[uid]) return;
      loadedRef.current[uid] = true;
      setLoadingForms(prev => ({ ...prev, [uid]: true }));
      setFormReady(prev => ({ ...prev, [uid]: false }));
      try {
        // Drawerを開くたびに必ず最新のスキーマを取得する。
        // roleFormSchemas(キャンバス側のキャッシュ)は初回ロード時のまま更新されないため、
        // Role定義(型・bit/color/bezierのoptionsなど)を編集した直後でも
        // 確実に反映されるよう、ここではキャッシュを使わない。
        const schema = await fetchSchemaOnce(role.name, true);
        setFreshSchemas(prev => ({ ...prev, [role.name]: schema }));
        const FormComp = await RoleInputFactory.getForm(
          role.name,
          formDataState[uid] || role.data || [],
          (formData) => {
            setFormDataState(prev => ({ ...prev, [uid]: formData }));
            setFormReady(prev => ({ ...prev, [uid]: true }));
          },
          schema,
          { eventId, subId }
        );
        setRoleForms(prev => ({ ...prev, [uid]: FormComp }));
      } catch (err) {
        setFormErrors(prev => ({ ...prev, [uid]: err.message }));
      } finally {
        setLoadingForms(prev => ({ ...prev, [uid]: false }));
      }
    });
  }, [open, roles, roleFormSchemas]);

  // Drawer閉じたらキャッシュリセット（次回再ロード用）。
  // 閉じる際、初期化済み(formReady)のRoleについては未保存の変更を自動保存してから閉じる
  // （「モーダルを閉じたら保存されているはず」という期待に応えるため）。
  const handleClose = () => {
    roles.forEach((r) => {
      if (formReady[r.uniqueId] && formDataState[r.uniqueId] !== undefined) {
        onSave(r.uniqueId, formDataState[r.uniqueId]);
      }
    });
    loadedRef.current = {};
    setRoleForms({});
    setFormErrors({});
    setFormReady({});
    onClose();
  };

  const handleSave = (uniqueId) => {
    if (!formReady[uniqueId]) {
      showSnack('フォームの読み込み中です。少し待ってから保存してください', 'warning');
      return;
    }
    onSave(uniqueId, formDataState[uniqueId]);
    showSnack('保存しました');
  };
  const handleBatchSave = () => {
    const notReady = roles.some((r) => !formReady[r.uniqueId]);
    if (notReady) {
      showSnack('フォームの読み込み中のRoleがあります。少し待ってから保存してください', 'warning');
      return;
    }
    roles.forEach(r => onSave(r.uniqueId, formDataState[r.uniqueId]));
    showSnack('一括保存しました');
  };

  return (
    <Drawer anchor="right" open={open} onClose={handleClose}>
      <Box sx={{ width: 660, p: 0, height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* ヘッダー */}
        <Box sx={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          px: 2, py: 1.5, bgcolor: 'primary.dark', color: 'white'
        }}>
          <Box>
            <Typography variant="subtitle1" fontWeight="bold">データ入力</Typography>
            <Typography variant="caption" sx={{ opacity: 0.8 }}>ノード {nodeId} / {roles.length} Role</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            {inputMode === 'gui' ? (
              <Button variant="outlined" size="small" color="inherit"
                onClick={switchToTextMode}>
                テキスト入力へ
              </Button>
            ) : (
              <>
                <Button variant="outlined" size="small" color="inherit" onClick={switchToGuiMode}>
                  GUI入力へ
                </Button>
                <Button variant="contained" size="small" color="success"
                  startIcon={<SaveIcon />} onClick={handleApplyDsl} disabled={applying}>
                  {applying ? '適用中...' : '適用して保存'}
                </Button>
              </>
            )}
            <Button variant="contained" size="small" color="success"
              startIcon={<SaveIcon />} onClick={handleBatchSave} disabled={inputMode === 'text'}>
              一括保存
            </Button>
            <IconButton onClick={handleClose} sx={{ color: 'white' }}><CloseIcon /></IconButton>
          </Box>
        </Box>

        {inputMode === 'text' ? (
          <Box sx={{ flex: 1, overflow: 'auto', p: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Alert severity="info" sx={{ py: 0.5 }}>
              1行1コマンド形式: <code>RoleName field1=値 field2=値</code>。文字列は <code>"..."</code>、
              ベクトルは <code>(x, y, z)</code>、配列は <code>[a, b, c]</code>、行頭 <code>#</code> はコメントです。
              入力中はRole名・フィールド名・値の候補が自動的に表示されます。
            </Alert>
            <ScenarioTransactionCodeEditor
              value={dslText}
              onChange={setDslText}
              roleNames={roleNamesForDsl}
              roleSchemas={effectiveSchemas}
              height="60vh"
            />
            {dslDiagnostics.length > 0 && (
              <Alert severity={dslDiagnostics.some(d => d.severity === 'error') ? 'error' : 'warning'} sx={{ maxHeight: 160, overflow: 'auto' }}>
                {dslDiagnostics.map((d, i) => (
                  <div key={i}>{d.line + 1}行目: {d.message}</div>
                ))}
              </Alert>
            )}
          </Box>
        ) : (
        <Box sx={{ flex: 1, overflow: 'auto', p: 1.5 }}>
          {roles.length === 0 ? (
            <Alert severity="info">Roleがありません</Alert>
          ) : roles.map((role, index) => (
            <Accordion key={role.uniqueId} defaultExpanded={index === 0}
              sx={{ mb: 1, border: '1px solid', borderColor: 'divider', borderRadius: '8px !important', '&:before': { display: 'none' } }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ borderRadius: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%', pr: 1 }}>
                  <Typography fontWeight="bold" variant="body2">{role.name}</Typography>
                  {role.branchType && role.branchType !== 'General' && (
                    <Chip label={role.branchType} size="small" color="secondary" sx={{ height: 18, fontSize: '0.65rem' }} />
                  )}
                  <Box sx={{ ml: 'auto', display: 'flex', gap: 0.5 }}>
                    <Tooltip title="保存">
                      <IconButton size="small" color="primary" onClick={(e) => { e.stopPropagation(); handleSave(role.uniqueId); }}>
                        <SaveIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="削除">
                      <IconButton size="small" color="error" onClick={(e) => { e.stopPropagation(); onDeleteRole(role.uniqueId); }}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </AccordionSummary>
              <AccordionDetails sx={{ pt: 0, px: 1.5 }}>
                {formErrors[role.uniqueId] ? (
                  <Alert severity="error" sx={{ mb: 1 }}>エラー: {formErrors[role.uniqueId]}</Alert>
                ) : loadingForms[role.uniqueId] ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1.5 }}>
                    <CircularProgress size={16} />
                    <Typography variant="caption" color="text.secondary">フォームを読み込み中...</Typography>
                  </Box>
                ) : roleForms[role.uniqueId] ? (
                  (() => { const F = roleForms[role.uniqueId]; return <F />; })()
                ) : (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1.5 }}>
                    <CircularProgress size={16} />
                    <Typography variant="caption">Loading...</Typography>
                  </Box>
                )}
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
        )}

        <Snackbar open={snack.open} autoHideDuration={2000} onClose={hideSnack} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}>
          <Alert onClose={hideSnack} severity={snack.severity} variant="filled">{snack.msg}</Alert>
        </Snackbar>
      </Box>
    </Drawer>
  );
};

// ============================================================
// RoleSelectDrawer（Role選択Drawer）
// ============================================================
const RoleSelectDrawer = ({ open, onClose, roles, nodeId, onAdd }) => (
  <Drawer anchor="right" open={open} onClose={onClose}>
    <Box sx={{ width: 320, p: 0, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', px: 2, py: 1.5, bgcolor: 'secondary.dark', color: 'white' }}>
        <Box>
          <Typography variant="subtitle1" fontWeight="bold">Role 追加</Typography>
          <Typography variant="caption" sx={{ opacity: 0.8 }}>ノード {nodeId}</Typography>
        </Box>
        <IconButton onClick={onClose} sx={{ color: 'white' }}><CloseIcon /></IconButton>
      </Box>
      <Box sx={{ flex: 1, overflow: 'auto', p: 1.5 }}>
        {roles.length === 0 ? (
          <Typography color="text.secondary" variant="body2">Roleが登録されていません</Typography>
        ) : roles.map(role => (
          <Paper key={role.id} variant="outlined" sx={{
            mb: 0.75, p: 1.25, cursor: 'pointer',
            transition: 'all 0.15s',
            '&:hover': { bgcolor: 'secondary.50', borderColor: 'secondary.main', transform: 'translateX(2px)' },
          }} onClick={() => { onAdd(role); onClose(); }}>
            <Typography variant="body2" fontWeight="bold">{role.name}</Typography>
            {role.description && (
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'pre-wrap', display: 'block' }}>{role.description}</Typography>
            )}
          </Paper>
        ))}
      </Box>
    </Box>
  </Drawer>
);

// ============================================================
// BlockCard（スクラッチ/ティラノビルダー風ブロックカード）
// ============================================================
const BlockCard = ({
  node, index, totalNodes, isSub, edges, allNodeIds,
  globalRoles, roleDataCache, roleFormSchemas, eventId, subId, flushStructureSave, onRefreshRoles,
  onMoveUp, onMoveDown, onDelete, onCopy, onEditId, onSubGroupOpen,
  onAddRole, onDeleteRole, onSaveRole, onAddEdge, onRemoveEdge,
  onUpdateFormData, onMoveToGroup,
}) => {
  const [collapsed, setCollapsed] = useState(false);
  const [showRoleSelect, setShowRoleSelect] = useState(false);
  const [showDataInput, setShowDataInput] = useState(false);
  const [formDataState, setFormDataState] = useState({});
  const [showConnectDialog, setShowConnectDialog] = useState(false);
  const [connectTarget, setConnectTarget] = useState('');
  const [showMoveDialog, setShowMoveDialog] = useState(false);
  const [moveTargetId, setMoveTargetId] = useState('');
  const [anchorEl, setAnchorEl] = useState(null);
  const { snack, show: showSnack, hide: hideSnack } = useSnack();

  // Role追加ダイアログ・データ入力ドロワーを開くたびに、Role一覧・全スキーマを
  // 強制的に最新化する(新規作成したばかりのRoleや、追加したばかりのフィールドが
  // 反映されない不具合の対策)。
  useEffect(() => {
    if (showRoleSelect || showDataInput) onRefreshRoles?.();
  }, [showRoleSelect, showDataInput]);

  const roles = node.data.roles || [];
  const isGroup = !isSub;
  const headerBg = isSub ? 'secondary.main' : 'primary.main';

  // roleData初期化
  useEffect(() => {
    const init = {};
    roles.forEach(r => {
      init[r.uniqueId] = roleDataCache?.[node.id]?.[r.uniqueId] || r.data || [];
    });
    setFormDataState(init);
  }, [roles, roleDataCache, node.id]);

  const handleAddRole = (role) => {
    const uniqueId = Date.now().toString();
    fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition/${node.id}/role`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roleId: role.id, name: role.name, branchType: role.branchType || 'General', uniqueId }),
    })
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then(() => {
        onAddRole(node.id, { uniqueId, id: role.id, name: role.name, branchType: role.branchType, data: [] });
        showSnack(`${role.name} を追加`);
      })
      .catch(e => showSnack('追加エラー: ' + e.message, 'error'));
  };

  const handleConnect = () => {
    const target = connectTarget.trim();
    if (!target || target === node.id) { showSnack('接続先が無効', 'warning'); return; }
    if (!allNodeIds.includes(target)) { showSnack('存在しないノードID', 'error'); return; }
    const alreadyExists = edges.some(e => e.source === node.id && e.target === target);
    if (alreadyExists) { showSnack('既に接続済み', 'warning'); return; }
    onAddEdge({ source: node.id, target, id: `${node.id}-${target}` });
    setConnectTarget('');
    setShowConnectDialog(false);
    showSnack(`→${target} 接続`);
  };

  const handleMoveBlock = () => {
    const tid = moveTargetId.trim();
    if (!tid) return;
    onMoveToGroup(node.id, tid);
    setShowMoveDialog(false);
  };

  // ドラッグ&ドロップ（HTMLドラッグAPI使用）
  const handleDragStart = (e) => {
    e.dataTransfer.setData('nodeId', node.id);
    e.dataTransfer.setData('nodeIndex', index);
    e.dataTransfer.effectAllowed = 'move';
  };
  const handleDragOver = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; };
  const handleDrop = (e) => {
    e.preventDefault();
    const draggedId = e.dataTransfer.getData('nodeId');
    const draggedIndex = parseInt(e.dataTransfer.getData('nodeIndex'), 10);
    if (draggedId === node.id) return;
    // インデックス差分で上/下移動を判定
    const delta = index - draggedIndex;
    if (Math.abs(delta) > 0) {
      window.dispatchEvent(new CustomEvent('reorderNode', { detail: { draggedId, targetId: node.id } }));
    }
  };

  return (
    <Paper
      draggable
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      elevation={2}
      sx={{
        mb: 1.5,
        borderRadius: 2,
        border: '2px solid',
        borderColor: isSub ? 'secondary.light' : 'primary.light',
        overflow: 'hidden',
        transition: 'box-shadow 0.2s, border-color 0.2s',
        '&:hover': { boxShadow: 6, borderColor: isSub ? 'secondary.main' : 'primary.main' },
        position: 'relative',
      }}
    >
      {/* ── ヘッダー ── */}
      <Box sx={{
        bgcolor: headerBg, px: 1.5, py: 0.75,
        display: 'flex', alignItems: 'center', gap: 0.5, cursor: 'grab',
        '&:active': { cursor: 'grabbing' },
      }}>
        <DragIndicatorIcon sx={{ color: 'rgba(255,255,255,0.6)', fontSize: 16, flexShrink: 0 }} />

        {/* ID バッジ */}
        <Chip
          label={node.id}
          size="small"
          sx={{
            bgcolor: 'rgba(255,255,255,0.2)', color: 'white',
            height: 20, fontSize: '0.7rem', fontWeight: 'bold', flexShrink: 0,
            cursor: 'pointer',
            '&:hover': { bgcolor: 'rgba(255,255,255,0.35)' }
          }}
          onClick={(e) => { e.stopPropagation(); onEditId(node.id); }}
        />

        {/* ラベル/説明（改行を含む場合はツールチップで全文をプレビュー表示） */}
        <Tooltip
          title={node.data.description ? <Box sx={{ whiteSpace: 'pre-wrap' }}>{node.data.description}</Box> : ''}
          disableHoverListener={!node.data.description || !node.data.description.includes('\n')}
        >
          <Typography variant="caption" color="white" noWrap sx={{ flex: 1, opacity: 0.9 }}>
            {(node.data.description || (isSub ? `SubGroup Node` : `Group Node`)).replace(/\n/g, ' / ')}
          </Typography>
        </Tooltip>

        {/* roles カウント */}
        {roles.length > 0 && (
          <Chip label={`${roles.length} Role`} size="small"
            sx={{ height: 18, fontSize: '0.6rem', bgcolor: 'rgba(255,255,255,0.25)', color: 'white', flexShrink: 0 }} />
        )}

        {/* アクションボタン群 */}
        <Box sx={{ display: 'flex', gap: 0, flexShrink: 0 }} onMouseDown={e => e.stopPropagation()}>
          <Tooltip title="上へ">
            <span>
              <IconButton size="small" disabled={index === 0} onClick={onMoveUp}
                sx={{ p: 0.25, color: 'rgba(255,255,255,0.8)', '&:disabled': { color: 'rgba(255,255,255,0.3)' } }}>
                <ArrowUpwardIcon sx={{ fontSize: 14 }} />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="下へ">
            <span>
              <IconButton size="small" disabled={index === totalNodes - 1} onClick={onMoveDown}
                sx={{ p: 0.25, color: 'rgba(255,255,255,0.8)', '&:disabled': { color: 'rgba(255,255,255,0.3)' } }}>
                <ArrowDownwardIcon sx={{ fontSize: 14 }} />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title={collapsed ? '展開' : '折り畳み'}>
            <IconButton size="small" onClick={() => setCollapsed(!collapsed)}
              sx={{ p: 0.25, color: 'rgba(255,255,255,0.8)' }}>
              {collapsed ? <ExpandMoreIcon sx={{ fontSize: 14 }} /> : <ExpandLessIcon sx={{ fontSize: 14 }} />}
            </IconButton>
          </Tooltip>
          {/* ケバブメニュー */}
          <IconButton size="small" sx={{ p: 0.25, color: 'rgba(255,255,255,0.8)' }}
            onClick={(e) => { e.stopPropagation(); setAnchorEl(e.currentTarget); }}>
            <MoreVertIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Box>
      </Box>

      {/* ── ケバブメニュー ── */}
      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
        <MenuItem onClick={() => { onCopy(node.id); setAnchorEl(null); }}>
          <ContentCopyIcon fontSize="small" sx={{ mr: 1 }} />コピー
        </MenuItem>
        <MenuItem onClick={() => { onEditId(node.id); setAnchorEl(null); }}>
          <EditIcon fontSize="small" sx={{ mr: 1 }} />ID / 説明を編集
        </MenuItem>
        <MenuItem onClick={() => { setShowConnectDialog(true); setAnchorEl(null); }}>
          <LinkIcon fontSize="small" sx={{ mr: 1 }} />接続を追加
        </MenuItem>
        <MenuItem onClick={() => { setShowMoveDialog(true); setAnchorEl(null); }}>
          <ArrowForwardIcon fontSize="small" sx={{ mr: 1 }} />別グループへ移動
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => { onDelete(node.id); setAnchorEl(null); }} sx={{ color: 'error.main' }}>
          <DeleteIcon fontSize="small" sx={{ mr: 1 }} />削除
        </MenuItem>
      </Menu>

      {/* ── ボディ（折り畳み） ── */}
      {!collapsed && (
        <Box sx={{ px: 1.5, py: 1 }} onMouseDown={e => e.stopPropagation()}>

          {/* 接続バッジ */}
          <ConnectionBadge nodeId={node.id} edges={edges} onRemove={onRemoveEdge} />

          {/* Role リスト */}
          {roles.length > 0 && (
            <Box sx={{ mt: 0.75, mb: 0.5 }}>
              {roles.map((role, ri) => (
                <Box key={role.uniqueId} sx={{
                  display: 'flex', alignItems: 'center', px: 1, py: 0.4,
                  mb: 0.4, borderRadius: 1, bgcolor: 'grey.100',
                  border: '1px solid', borderColor: 'grey.300',
                  gap: 0.5,
                  '&:hover': { bgcolor: 'primary.50', borderColor: 'primary.200' },
                }}>
                  <DragIndicatorIcon sx={{ fontSize: 12, color: 'text.disabled', flexShrink: 0 }} />
                  <Typography variant="caption" fontWeight="bold" noWrap sx={{ flex: 1 }}>
                    {role.name}
                  </Typography>
                  {role.branchType && role.branchType !== 'General' && (
                    <Chip label={role.branchType} size="small"
                      sx={{ height: 14, fontSize: '0.55rem', flexShrink: 0 }} />
                  )}
                  <Tooltip title="削除">
                    <IconButton size="small" color="error"
                      onClick={() => onDeleteRole(node.id, role.uniqueId)} sx={{ p: 0.2, flexShrink: 0 }}>
                      <DeleteIcon sx={{ fontSize: 12 }} />
                    </IconButton>
                  </Tooltip>
                </Box>
              ))}
            </Box>
          )}

          {/* アクションボタン */}
          <Box sx={{ display: 'flex', gap: 0.75, mt: 0.75, flexWrap: 'wrap' }}>
            {isGroup && (
              <Button variant="outlined" size="small"
                startIcon={<AccountTreeIcon sx={{ fontSize: 12 }} />}
                onClick={() => onSubGroupOpen(node.id)}
                sx={{ fontSize: '0.68rem', py: 0.3, px: 1, minWidth: 0, flex: 1 }}>
                SubGroup
              </Button>
            )}
            {isSub && (
              <>
                <Button variant="outlined" size="small" color="secondary"
                  startIcon={<AddIcon sx={{ fontSize: 12 }} />}
                  onClick={() => setShowRoleSelect(true)}
                  sx={{ fontSize: '0.68rem', py: 0.3, px: 1, minWidth: 0, flex: 1 }}>
                  Role追加
                </Button>
                {roles.length > 0 && (
                  <Button variant="contained" size="small" color="secondary"
                    onClick={() => setShowDataInput(true)}
                    sx={{ fontSize: '0.68rem', py: 0.3, px: 1, minWidth: 0, flex: 1 }}>
                    データ入力
                  </Button>
                )}
              </>
            )}
            <Button variant="outlined" size="small"
              startIcon={<LinkIcon sx={{ fontSize: 12 }} />}
              onClick={() => setShowConnectDialog(true)}
              sx={{ fontSize: '0.68rem', py: 0.3, px: 1, minWidth: 0 }}>
              接続
            </Button>
          </Box>
        </Box>
      )}

      {/* ── Role選択Drawer ── */}
      <RoleSelectDrawer
        open={showRoleSelect}
        onClose={() => setShowRoleSelect(false)}
        roles={globalRoles}
        nodeId={node.id}
        onAdd={handleAddRole}
      />

      {/* ── データ入力Drawer ── */}
      <RoleDataDrawer
        open={showDataInput}
        onClose={() => setShowDataInput(false)}
        nodeId={node.id}
        roles={roles}
        formDataState={formDataState}
        setFormDataState={(updater) => {
          const newState = typeof updater === 'function' ? updater(formDataState) : updater;
          setFormDataState(newState);
          onUpdateFormData(node.id, newState);
        }}
        roleFormSchemas={roleFormSchemas}
        eventId={eventId}
        subId={subId}
        onSave={(uid, data) => onSaveRole(node.id, uid, data)}
        onDeleteRole={(uid) => onDeleteRole(node.id, uid)}
        onAddRole={(newRole) => onAddRole(node.id, newRole)}
        flushStructureSave={flushStructureSave}
      />

      {/* ── 接続追加ダイアログ ── */}
      <Dialog open={showConnectDialog} onClose={() => setShowConnectDialog(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ pb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <LinkIcon color="primary" />
            接続先を指定（ノード {node.id} から）
          </Box>
        </DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth size="small"
            label="接続先ノードID"
            value={connectTarget}
            onChange={e => setConnectTarget(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleConnect(); }}
            helperText={`利用可能: ${allNodeIds.filter(id => id !== node.id).join(', ') || 'なし'}`}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowConnectDialog(false)} color="inherit">キャンセル</Button>
          <Button onClick={handleConnect} variant="contained" startIcon={<LinkIcon />}>接続</Button>
        </DialogActions>
      </Dialog>

      {/* ── 別グループへ移動ダイアログ ── */}
      <Dialog open={showMoveDialog} onClose={() => setShowMoveDialog(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ pb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ArrowForwardIcon color="primary" />
            別グループへ移動
          </Box>
        </DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth size="small"
            label="移動先 グループID"
            value={moveTargetId}
            onChange={e => setMoveTargetId(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleMoveBlock(); }}
            helperText="移動するとIDが更新されます"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowMoveDialog(false)} color="inherit">キャンセル</Button>
          <Button onClick={handleMoveBlock} variant="contained">移動</Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar */}
      <Snackbar open={snack.open} autoHideDuration={2000} onClose={hideSnack} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}>
        <Alert onClose={hideSnack} severity={snack.severity} variant="filled" sx={{ minWidth: 180 }}>{snack.msg}</Alert>
      </Snackbar>
    </Paper>
  );
};

// ============================================================
// BlockCanvas（ブロック一覧ビュー）
// ============================================================
const BlockCanvas = ({
  nodes, edges, isSub, globalRoles, roleDataCache, roleFormSchemas,
  eventId, subId, flushStructureSave, onRefreshRoles,
  onReorder, onDelete, onCopy, onEditId, onSubGroupOpen,
  onAddRole, onDeleteRole, onSaveRole, onAddEdge, onRemoveEdge,
  onUpdateFormData, onMoveToGroup,
}) => {
  const allNodeIds = nodes.map(n => n.id);

  if (nodes.length === 0) {
    return (
      <Box sx={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: '60vh', color: 'text.secondary', gap: 2,
      }}>
        <AccountTreeIcon sx={{ fontSize: 64, opacity: 0.3 }} />
        <Typography variant="h6" sx={{ opacity: 0.5 }}>ノードがありません</Typography>
        <Typography variant="body2" sx={{ opacity: 0.4 }}>上の「追加」ボタンからノードを追加してください</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 2 }}>
      {nodes.map((node, index) => (
        <BlockCard
          key={node.id}
          node={node}
          index={index}
          totalNodes={nodes.length}
          isSub={isSub}
          edges={edges}
          allNodeIds={allNodeIds}
          globalRoles={globalRoles}
          roleDataCache={roleDataCache}
          roleFormSchemas={roleFormSchemas}
          eventId={eventId}
          subId={subId}
          flushStructureSave={flushStructureSave}
          onRefreshRoles={onRefreshRoles}
          onMoveUp={() => onReorder(index, index - 1)}
          onMoveDown={() => onReorder(index, index + 1)}
          onDelete={onDelete}
          onCopy={onCopy}
          onEditId={onEditId}
          onSubGroupOpen={onSubGroupOpen}
          onAddRole={onAddRole}
          onDeleteRole={onDeleteRole}
          onSaveRole={onSaveRole}
          onAddEdge={onAddEdge}
          onRemoveEdge={onRemoveEdge}
          onUpdateFormData={onUpdateFormData}
          onMoveToGroup={onMoveToGroup}
        />
      ))}
    </Box>
  );
};

// ============================================================
// ScenarioEventTransition メイン
// ============================================================
function ScenarioEventTransition() {
  const params = useParams();
  const eventId = params.eventId;
  const subId = params.subId;

  const [isLoading, setIsLoading] = useState(true);
  const [tabs, setTabs] = useState([{ id: 'main', label: 'Group遷移', type: 'group' }]);
  const [activeTab, setActiveTab] = useState('main');
  const [tabData, setTabData] = useState({ main: { nodes: [], edges: [] } });

  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editNodeId, setEditNodeId] = useState(null);
  const [newDescription, setNewDescription] = useState('');
  const [editNewId, setEditNewId] = useState('');

  const [copiedNode, setCopiedNode] = useState(null);
  const [globalRoles, setGlobalRoles] = useState([]);
  // globalRoles.map(...) を毎レンダー新しい配列として作ってしまうと、
  // ScenarioTransactionCodeEditorのextensions(useMemo)が毎回作り直されて
  // 入力(1文字打つたび)がもたつく原因になるため、globalRoles自体が
  // 変わった時だけ再生成されるようメモ化する（全体編集/Sub編集ダイアログ共通）。
  const globalRoleNamesForDsl = useMemo(
    () => globalRoles.map((r) => r.name),
    [globalRoles]
  );
  const [roleDataCache, setRoleDataCache] = useState({});
  const [roleFormSchemas, setRoleFormSchemas] = useState({});

  const { snack, show: showSnack, hide: hideSnack } = useSnack();

  // ============================================================
  // 全体編集（イベント内の全Sub・全ノードのTransactionを1つのテキストで一括編集）
  // ------------------------------------------------------------
  // データの持ち方・保存先は既存のまま(各Subの nodes[].data.roles /
  // nodes[].data.subgroups[...].nodes[].data.roles)。あくまで「編集画面」を
  // 追加するだけで、新しいデータ構造や実行タイミングの変更は一切行わない。
  // 既存の /api/scenario-event (一覧) と
  // /api/scenario-event/<eventId>/sub/<subId>/transition (GET/POST) だけを使う。
  //
  // スコープ: 既存ノードのRole呼び出し内容(追加/削除/値変更)の一括編集のみ対応。
  // 新しいノード自体の作成はこの画面では行えない(通常のGUI操作で追加してください)。
  // ============================================================
  const [showAllEditDialog, setShowAllEditDialog] = useState(false);
  const [allEditLoading, setAllEditLoading] = useState(false);
  const [allEditApplying, setAllEditApplying] = useState(false);
  const [allEditText, setAllEditText] = useState('');
  const [allEditDiagnostics, setAllEditDiagnostics] = useState([]); // [{message, subId, path}]
  // 見出しに一致しない(＝未知の)行があった場合に、新しいグループとして
  // 自動作成することを許可するかどうか。デフォルトはOFF。
  // これにより、案内コメントの消し忘れや見出しの書き間違いだけで
  // 意図せずグループが増えてしまう事故を防ぐ(明示的にチェックした場合のみ作成する)。
  const [allEditAllowNewGroups, setAllEditAllowNewGroups] = useState(false);
  // subId -> { nodes, edges }  (取得時点の全ノードツリー。適用時にこれを直接書き換えて送り返す)
  const allEditSubTreesRef = useRef({});
  // "subId::path" -> ノードオブジェクトへの直接参照 (allEditSubTreesRef内のツリーの一部)
  const allEditTargetsRef = useRef({});

  // ------------------------------------------------------------
  // 現在開いているSubだけをLua形式で編集するための状態
  // (「全体編集」と全く同じ仕組み・同じヘルパー関数を、対象Subを1件だけに
  //  限定して使う。データの持ち方・保存先・API呼び出しは既存のまま)
  // ------------------------------------------------------------
  const [showSubEditDialog, setShowSubEditDialog] = useState(false);
  const [subEditLoading, setSubEditLoading] = useState(false);
  const [subEditApplying, setSubEditApplying] = useState(false);
  const [subEditText, setSubEditText] = useState('');
  const [subEditDiagnostics, setSubEditDiagnostics] = useState([]);
  const [subEditAllowNewGroups, setSubEditAllowNewGroups] = useState(false);
  const subEditSubTreesRef = useRef({});
  const subEditTargetsRef = useRef({});

  const ALL_EDIT_HEADER_RE = /^#\s*====\s*SUB:(\S+)\s+NODE:(\S+).*?====\s*$/;
  // 「# 例: ...」で始まる行は、あくまで書き方の案内・記入例であり、
  // 実際の見出しやTransaction本文としては絶対に解釈しない。
  // ユーザーが消し忘れたまま適用しても、見出し扱いにも他ノードの本文への
  // 混入にもならないよう、パースの最初の段階で丸ごと読み飛ばす。
  const GUIDE_LINE_RE = /^#\s*例\s*[:：]/;

  // node以下を再帰的に辿り、Roleを持ちうる全ノード(トップレベル + 入れ子のsubgroups)を収集する
  const collectAllEditTargets = (nodes, pathIds, out) => {
    (nodes || []).forEach((node) => {
      const path = [...pathIds, String(node.id)];
      out.push({ path, node, label: node.description || '' });
      const subgroups = (node.data && node.data.subgroups) || {};
      Object.keys(subgroups).forEach((sgId) => {
        const innerNodes = (subgroups[sgId] && subgroups[sgId].nodes) || [];
        collectAllEditTargets(innerNodes, path, out);
      });
    });
  };

  // pathSegments(例: ['3','new1']) が指すノードを返す。存在しない場合は、
  // 途中の階層も含めて新しいグループ/サブグループとして作成する。
  // (Lua/テキスト側から「新しいグループを追加」「そのグループの中にさらに
  //   サブグループを追加」できるようにするための処理。既存ノードには一切触れない)
  const ensureAllEditNodePath = (tree, pathSegments) => {
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
        // さらに深い階層(サブグループ)へ進む準備。サブグループは自分自身の
        // idをキーとして「自分の中身」を持つ、という既存の規約(handle_subgroup系)に合わせる。
        node.data = node.data || {};
        node.data.subgroups = node.data.subgroups || {};
        const sgKey = String(node.id);
        node.data.subgroups[sgKey] = node.data.subgroups[sgKey] || { nodes: [], edges: [] };
        if (!Array.isArray(node.data.subgroups[sgKey].nodes)) node.data.subgroups[sgKey].nodes = [];
        list = node.data.subgroups[sgKey].nodes;
      }
    }
    return node;
  };

  // 指定した1つのSubのツリーから、Lua形式編集用のテキスト行を組み立てる。
  // 「全体編集(全Sub)」「Sub編集(現在のSubのみ)」の両方から共通で使う。
  // targetsOut には "subId::path" -> ノード の対応表を書き込む。
  const buildEditLinesForSub = (sid, tree, targetsOut) => {
    const lines = [];
    const targets = [];
    collectAllEditTargets(tree.nodes, [], targets);
    targets.forEach((t) => {
      const pathKey = t.path.join('/');
      targetsOut[`${sid}::${pathKey}`] = t.node;
      const labelSuffix = t.label ? ` (${t.label})` : '';
      lines.push(`# ==== SUB:${sid} NODE:${pathKey}${labelSuffix} ====`);
      const roles = (t.node.data && t.node.data.roles) || [];
      const bodyText = decompileRoles(roles, roleFormSchemas);
      if (bodyText) lines.push(bodyText);
      lines.push('');
    });
    // 新しいグループを追加する際の書き方の案内。
    // 「# 例:」で始まる行はGUIDE_LINE_REにより保存時に必ず無視されるため、
    // 消し忘れて適用してもグループが作られたり内容が化けたりすることはない。
    lines.push(`# 例: 新しいグループを追加したい場合は、下の「新しいグループの追加を許可する」に`);
    lines.push(`# 例: チェックを入れたうえで、下記のような見出しを書いてください（この案内行自体は無視されます）`);
    lines.push(`# 例: ==== SUB:${sid} NODE:新しいノードID ====`);
    lines.push(`# 例: ==== SUB:${sid} NODE:既存または新規の親ID/新しいサブグループのノードID ====`);
    lines.push('');
    return lines;
  };

  // Lua形式テキストをヘッダ行で分割し、セクション(見出し+本文)の配列にする。
  // 案内・記入例コメント("# 例: ...")は見出しとしても本文としても解釈せず、
  // その場で読み飛ばす。
  const parseEditSections = (text) => {
    const rawLines = text.split('\n');
    const sections = [];
    let current = null;
    rawLines.forEach((line) => {
      if (GUIDE_LINE_RE.test(line)) return; // 案内コメント行は無視する
      const m = line.match(ALL_EDIT_HEADER_RE);
      if (m) {
        if (current) sections.push(current);
        current = { subId: m[1], pathKey: m[2], bodyLines: [] };
      } else if (current) {
        current.bodyLines.push(line);
      }
    });
    if (current) sections.push(current);

    // パスが短い(=階層が浅い)順に処理する。新規グループの中にさらに新規サブグループを
    // 追加するようなケースで、親を先に作ってから子を作れるようにするため。
    sections.sort((a, b) => a.pathKey.split('/').length - b.pathKey.split('/').length);
    return sections;
  };

  // セクション列を、対応するツリーへ実際に適用する。
  // 「全体編集」「Sub編集」どちらの適用処理からも呼ばれる共通ロジック。
  // allowNewGroups が false の場合、見出しに対応する既存ノードが見つからなくても
  // 新しいグループは作成せず、警告としてdiagnosticsに積むだけに留める
  // (案内コメントの消し忘れや見出しの書き間違いだけで、意図せずグループが
  //  増えてしまう事故を防ぐため)。
  const applyEditSections = (sections, subTreesRef, targetsRef, allowNewGroups) => {
    const diagnostics = [];
    const touchedSubIds = new Set();

    for (const section of sections) {
      const key = `${section.subId}::${section.pathKey}`;
      let targetNode = targetsRef.current[key];
      if (!targetNode) {
        const tree = subTreesRef.current[section.subId];
        if (!tree) {
          diagnostics.push({
            message: `存在しないSubです: SUB:${section.subId}`,
            subId: section.subId, path: section.pathKey,
          });
          continue;
        }
        if (!allowNewGroups) {
          diagnostics.push({
            message: `未知の見出しです（新しいグループは作成されません）: SUB:${section.subId} NODE:${section.pathKey} ／ 新しいグループを追加したい場合は「新しいグループの追加を許可する」にチェックを入れてから適用してください`,
            subId: section.subId, path: section.pathKey,
          });
          continue;
        }
        // 見出しに対応する既存ノードが無く、かつ新規グループ作成が許可されている
        // 場合のみ、新しいグループ(または新しいサブグループ)として作成する。
        targetNode = ensureAllEditNodePath(tree, section.pathKey.split('/'));
        targetsRef.current[key] = targetNode;
      }
      const existingRoles = (targetNode.data && targetNode.data.roles) || [];
      const { roles: compiledRoles, diagnostics: sectionDiagnostics } = compileDocument(
        section.bodyLines.join('\n'), roleFormSchemas, existingRoles
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
  };

  const handleOpenAllEditDialog = async () => {
    if (!eventId) return;
    setShowAllEditDialog(true);
    setAllEditLoading(true);
    setAllEditDiagnostics([]);
    try {
      // このイベントのSub一覧を取得
      const listRes = await fetch('/api/scenario-event');
      const list = listRes.ok ? await listRes.json() : [];
      const eventEntry = (list || []).find((e) => e.id === eventId);
      const subIds = (eventEntry?.subEvents || []).map((s) => String(s.subId));

      allEditSubTreesRef.current = {};
      allEditTargetsRef.current = {};
      const lines = [];

      for (const sid of subIds) {
        const res = await fetch(`/api/scenario-event/${eventId}/sub/${sid}/transition`);
        const tree = res.ok ? await res.json() : { nodes: [], edges: [] };
        allEditSubTreesRef.current[sid] = tree;
        lines.push(...buildEditLinesForSub(sid, tree, allEditTargetsRef.current));
      }

      setAllEditText(lines.join('\n'));
    } catch (e) {
      console.error('全体編集の読み込みエラー:', e);
      showSnack('全体編集データの取得に失敗しました', 'error');
    } finally {
      setAllEditLoading(false);
    }
  };

  const handleApplyAllEdit = async () => {
    setAllEditApplying(true);
    try {
      const sections = parseEditSections(allEditText);
      const { diagnostics, touchedSubIds } = applyEditSections(
        sections, allEditSubTreesRef, allEditTargetsRef, allEditAllowNewGroups
      );

      setAllEditDiagnostics(diagnostics);
      if (diagnostics.length > 0) {
        showSnack('エラーがあるため一部(またはすべて)適用できませんでした。内容を確認してください。', 'error');
        return;
      }

      // 変更のあったSubだけ、既存の /transition エンドポイントへそのまま書き戻す
      // (新規作成したノード/サブグループも、このtreeオブジェクトに直接追加済みなので
      //  そのまま送るだけでよい)
      for (const sid of touchedSubIds) {
        const tree = allEditSubTreesRef.current[sid];
        const res = await fetch(`/api/scenario-event/${eventId}/sub/${sid}/transition`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nodes: tree.nodes, edges: tree.edges }),
        });
        if (!res.ok) throw new Error(`Sub ${sid} の保存に失敗しました (HTTP ${res.status})`);
      }

      showSnack(`全体編集を適用しました（${touchedSubIds.size}件のSubを更新）`);
      setShowAllEditDialog(false);

      // 現在開いているタブが今回更新対象に含まれていた場合、表示中データが古くなるため再読み込みする
      if (touchedSubIds.has(String(subId))) {
        window.location.reload();
      }
    } catch (e) {
      console.error('全体編集の適用エラー:', e);
      showSnack(`全体編集の適用に失敗しました: ${e.message}`, 'error');
    } finally {
      setAllEditApplying(false);
    }
  };

  // ------------------------------------------------------------
  // Sub編集(現在開いているSubのみをLua形式で編集)
  // 「全体編集」と同じ仕組みを、対象Subを現在のsubId 1件だけに限定して使う。
  // ------------------------------------------------------------
  const handleOpenSubEditDialog = async () => {
    if (!eventId || !subId) return;
    setShowSubEditDialog(true);
    setSubEditLoading(true);
    setSubEditDiagnostics([]);
    try {
      subEditSubTreesRef.current = {};
      subEditTargetsRef.current = {};

      const res = await fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition`);
      const tree = res.ok ? await res.json() : { nodes: [], edges: [] };
      subEditSubTreesRef.current[subId] = tree;

      const lines = buildEditLinesForSub(subId, tree, subEditTargetsRef.current);
      setSubEditText(lines.join('\n'));
    } catch (e) {
      console.error('Sub編集の読み込みエラー:', e);
      showSnack('Sub編集データの取得に失敗しました', 'error');
    } finally {
      setSubEditLoading(false);
    }
  };

  const handleApplySubEdit = async () => {
    if (!eventId || !subId) return;
    setSubEditApplying(true);
    try {
      const allSections = parseEditSections(subEditText);
      // このダイアログは現在のSub専用。念のため、他Subの見出しが紛れ込んでいた場合は
      // 適用せずエラーとして扱う(全体編集ダイアログを使うよう案内する)。
      const sections = allSections.filter((s) => String(s.subId) === String(subId));
      const foreignSections = allSections.filter((s) => String(s.subId) !== String(subId));

      const { diagnostics, touchedSubIds } = applyEditSections(
        sections, subEditSubTreesRef, subEditTargetsRef, subEditAllowNewGroups
      );
      foreignSections.forEach((s) => diagnostics.push({
        message: `このSub編集では別Subの見出しは扱えません（SUB:${s.subId} NODE:${s.pathKey}）。複数Subをまたいで編集する場合は「全体編集(全Sub一括)」を使ってください`,
        subId: s.subId, path: s.pathKey,
      }));

      setSubEditDiagnostics(diagnostics);
      if (diagnostics.length > 0) {
        showSnack('エラーがあるため適用できませんでした。内容を確認してください。', 'error');
        return;
      }

      if (touchedSubIds.has(String(subId))) {
        const tree = subEditSubTreesRef.current[subId];
        const res = await fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nodes: tree.nodes, edges: tree.edges }),
        });
        if (!res.ok) throw new Error(`Sub ${subId} の保存に失敗しました (HTTP ${res.status})`);
      }

      showSnack('このSubの編集内容を適用しました');
      setShowSubEditDialog(false);
      window.location.reload();
    } catch (e) {
      console.error('Sub編集の適用エラー:', e);
      showSnack(`Sub編集の適用に失敗しました: ${e.message}`, 'error');
    } finally {
      setSubEditApplying(false);
    }
  };


  // 保存バグ修正用の参照群
  // ------------------------------------------------------------
  // ・tabDataRef: setState は非同期なため、直後に保存処理を呼んでも
  //   古い(更新前の)tabDataを参照してしまうことがあった(＝保存漏れ/
  //   空データでの上書きの原因)。updateTabData内で同期的に書き込み、
  //   常に最新の状態を保存処理から参照できるようにする。
  // ・loadedTabsRef: タブ(main / subgroup-xxx)ごとに「サーバーからの
  //   初回読み込みが完了したか」を保持する。読み込み完了前は保存を
  //   一切行わない(＝空のJSONで上書きしてしまう問題を防ぐ)。
  // ・savingRef / pendingSaveRef: 保存処理の排他制御。保存中に新しい
  //   保存要求が来た場合はリクエストを重複発行せず、完了後に最新の
  //   データで1回だけ保存し直す(取りこぼし防止)。
  // ============================================================
  const tabDataRef = useRef(tabData);
  const activeTabRef = useRef(activeTab);
  const eventIdRef = useRef(eventId);
  const subIdRef = useRef(subId);
  const loadedTabsRef = useRef({});
  const savingRef = useRef(false);
  const pendingSaveRef = useRef(null);

  useEffect(() => { activeTabRef.current = activeTab; }, [activeTab]);
  useEffect(() => { eventIdRef.current = eventId; subIdRef.current = subId; }, [eventId, subId]);

  const currentTabData = tabData[activeTab] || { nodes: [], edges: [] };
  const isSub = activeTab.startsWith('subgroup-');
  const parentId = isSub ? activeTab.replace('subgroup-', '') : null;

  // ── グローバルRole取得 ──
  useEffect(() => {
    fetch('/api/scenario-role')
      .then(res => res.json())
      .then(d => setGlobalRoles(d))
      .catch(err => console.error('Role取得エラー:', err));
  }, []);

  // Role一覧・全Roleスキーマを強制的に再取得する共通関数。
  // 「Roleスキーマ再取得」ボタンに加え、Role追加ダイアログ／データ入力ダイアログを
  // 開くタイミングでも自動的に呼び、新規作成したばかりのRole種別が一覧に出ない、
  // 新しく追加したフィールドがLua記法の補完に出ない、といった不具合を防ぐ。
  const refreshGlobalRolesAndSchemas = useCallback(async () => {
    try {
      const res = await fetch('/api/scenario-role');
      const rolesList = res.ok ? await res.json() : [];
      setGlobalRoles(rolesList);
      const fresh = {};
      for (const role of rolesList) {
        invalidateRoleSchemaCache(role.name);
        try {
          fresh[role.name] = await fetchSchemaOnce(role.name, true);
        } catch (e) {
          console.error(`スキーマ再取得エラー (${role.name}):`, e);
        }
      }
      setRoleFormSchemas(fresh);
    } catch (e) {
      console.error('Role一覧再取得エラー:', e);
    }
  }, []);

  // ── スキーマ一括ロード（重複排除済み） ──
  useEffect(() => {
    if (!globalRoles.length) return;
    globalRoles.forEach(async (role) => {
      if (roleFormSchemas[role.name]) return; // 既にある
      try {
        const schema = await fetchSchemaOnce(role.name);
        setRoleFormSchemas(prev => ({ ...prev, [role.name]: schema }));
      } catch (e) {
        console.error(`スキーマ取得エラー (${role.name}):`, e);
      }
    });
  }, [globalRoles]);

  // ── 初期データロード ──
  useEffect(() => {
    if (!eventId || !subId) { setIsLoading(false); return; }
    const ctrl = new AbortController();
    setIsLoading(true);
    // 新しいeventId/subIdへの遷移時は、読み込み完了フラグを一旦リセットする
    // （読み込みが完了するまでmainタブへの保存を禁止するため）。
    loadedTabsRef.current.main = false;
    fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition`, { signal: ctrl.signal })
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then(result => {
        const nodes = result.nodes || [];
        const edges = (result.edges || []).filter(e =>
          nodes.some(n => n.id === e.source) && nodes.some(n => n.id === e.target)
        );
        const loaded = { main: { nodes, edges } };
        tabDataRef.current = loaded;
        setTabData(loaded);
        // 読み込みが正常に完了した場合のみ保存を許可する
        loadedTabsRef.current.main = true;
      })
      .catch(e => {
        if (e.name !== 'AbortError') {
          console.error('初期ロードエラー:', e);
          showSnack('データの読み込みに失敗しました。保存はできません', 'error');
        }
      })
      .finally(() => setIsLoading(false));
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId, subId]);

  // ── ドラッグ&ドロップ並び替えイベント ──
  useEffect(() => {
    const handler = (e) => {
      const { draggedId, targetId } = e.detail;
      let changed = false;
      updateTabData(prev => {
        const cur = prev[activeTab] || { nodes: [], edges: [] };
        const from = cur.nodes.findIndex(n => n.id === draggedId);
        const to = cur.nodes.findIndex(n => n.id === targetId);
        if (from < 0 || to < 0) return prev;
        const newNodes = [...cur.nodes];
        const [moved] = newNodes.splice(from, 1);
        newNodes.splice(to, 0, moved);
        changed = true;
        return { ...prev, [activeTab]: { ...cur, nodes: newNodes } };
      });
      // updateTabData経由でtabDataRefも同期されるので、ここで自動保存をスケジュールしてよい
      if (changed) scheduleSave();
    };
    window.addEventListener('reorderNode', handler);
    return () => window.removeEventListener('reorderNode', handler);
  }, [activeTab]);

  // ── 保存処理本体 ──
  // 常に tabDataRef.current / eventIdRef.current / subIdRef.current という
  // 「最新値」だけを参照する。呼び出し元から値を引数で受け取らないことで、
  // クロージャの古い状態を保存してしまう問題を構造的に防ぐ。
  const performSave = useCallback((tabId) => {
    const eventIdCur = eventIdRef.current;
    const subIdCur = subIdRef.current;
    if (!tabId || !eventIdCur || !subIdCur) return;

    // 1) 読み込み完了前は保存しない（空JSONでの上書き防止）
    if (!loadedTabsRef.current[tabId]) return;

    const cur = tabDataRef.current[tabId];
    if (!cur) return;

    // 2) 保存処理中に呼ばれた場合は多重発行せず、完了後に最新データで
    //    もう一度だけ保存するようキューする（取りこぼし防止）
    if (savingRef.current) {
      pendingSaveRef.current = tabId;
      return;
    }

    savingRef.current = true;
    setIsLoading(true);

    const pid = tabId.startsWith('subgroup-') ? tabId.replace('subgroup-', '') : null;
    const saveData = {
      nodes: cur.nodes.map(n => ({
        id: n.id, type: n.type || (tabId === 'main' ? 'customGroup' : 'subGroupNode'),
        position: n.position || { x: 0, y: 0 },
        data: { label: n.data.label, description: n.data.description || '', roles: n.data.roles || [], subgroups: n.data.subgroups || {}, isSubGroup: n.data.isSubGroup },
        draggable: true,
      })),
      edges: cur.edges,
    };
    const url = pid
      ? `/api/scenario-event/${eventIdCur}/sub/${subIdCur}/transition/${pid}/subgroup`
      : `/api/scenario-event/${eventIdCur}/sub/${subIdCur}/transition`;

    // 戻り値のPromiseはDSL適用時など「構造(node/role一覧)の保存が
    // サーバー側に反映されたことを保証してから、続けてRoleのフィールド値を
    // 保存したい」呼び出し元(handleApplyDsl)のために公開している。
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saveData) })
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); })
      .catch(e => {
        console.error('保存エラー:', e);
        showSnack('保存に失敗しました。再度お試しください', 'error');
        throw e;
      })
      .finally(() => {
        savingRef.current = false;
        setIsLoading(false);
        // 保存中に来た最新の保存要求があれば、ここで1回だけ実行する
        if (pendingSaveRef.current) {
          const nextTabId = pendingSaveRef.current;
          pendingSaveRef.current = null;
          performSave(nextTabId);
        }
      });
  }, [showSnack]);

  // 連続編集をまとめるためのdebounce（自動保存用）。
  // 実際に呼び出す関数は毎回同じインスタンスを使い回し、常に
  // activeTabRef.current（最新のタブ）で保存する。
  const debouncedAutoSaveRef = useRef();
  if (!debouncedAutoSaveRef.current) {
    debouncedAutoSaveRef.current = debounce(() => {
      performSave(activeTabRef.current);
    }, 600);
  }

  // ノード編集などの操作後に呼ぶ自動保存（デバウンスされる）
  const scheduleSave = useCallback(() => {
    debouncedAutoSaveRef.current();
  }, []);

  // 「保存」ボタン用。デバウンスを待たず、保留中の自動保存があれば
  // それを確定させたうえで即座に保存する。これにより「押しても反応が
  // 無いように見える」状態を無くし、クリックすれば必ず保存が実行される。
  const saveCurrentTab = useCallback(() => {
    debouncedAutoSaveRef.current.cancel();
    return performSave(activeTabRef.current);
  }, [performSave]);

  // ── タブ切り替え ──
  const handleTabSwitch = useCallback((tabId, pid = null) => {
    if (tabId === activeTab) return;
    if (!eventId || !subId) { showSnack('Event/Sub IDが未定義', 'error'); return; }

    // デバウンス待ちの自動保存が残っている場合、activeTabRefが切り替わる前に
    // 「今のタブ」に対して確定させる。そうしないと600ms以内にタブを切り替えた際、
    // 保存が新しいタブに対して発火してしまい、元のタブの編集が失われる。
    debouncedAutoSaveRef.current.flush();

    if (tabId.startsWith('subgroup-')) {
      const pId = pid || tabId.replace('subgroup-', '');
      const existingTab = tabs.find(t => t.id === tabId);
      if (existingTab && tabData[tabId]) {
        setActiveTab(tabId);
        return;
      }
      setIsLoading(true);
      const newTab = { id: tabId, label: `Sub: ${pId}`, type: 'subgroup', parentId: pId };
      setTabs(prev => prev.find(t => t.id === tabId) ? prev : [...prev, newTab]);
      fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition/${pId}/subgroup`)
        .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
        .then(result => {
          const nodes = result.nodes || [];
          const edges = (result.edges || []).filter(e =>
            nodes.some(n => n.id === e.source) && nodes.some(n => n.id === e.target)
          );
          setTabData(prev => ({ ...prev, [tabId]: { nodes, edges } }));
          // 読み込みが正常に完了した場合のみ、このサブグループタブへの保存を許可する
          loadedTabsRef.current[tabId] = true;
          setActiveTab(tabId);
        })
        .catch(e => console.error('SubGroupロードエラー:', e))
        .finally(() => setIsLoading(false));
    } else {
      setActiveTab(tabId);
    }
  }, [eventId, subId, activeTab, tabs, tabData]);

  const handleTabClose = (tabId) => {
    if (tabId === 'main') return;
    setTabs(prev => prev.filter(t => t.id !== tabId));
    setTabData(prev => { const { [tabId]: _, ...rest } = prev; return rest; });
    if (activeTab === tabId) setActiveTab('main');
  };

  // ── ノード操作 ──
  const updateTabData = (updater) => {
    setTabData(prev => {
      const updated = typeof updater === 'function' ? updater(prev) : updater;
      // setState自体は非同期でも、参照(tabDataRef)はここで同期的に
      // 最新化しておく。これにより直後にsaveCurrentTab()を呼んでも
      // 更新前の古いデータで保存してしまうことがなくなる。
      tabDataRef.current = updated;
      return updated;
    });
  };

  const handleReorder = (from, to) => {
    if (to < 0 || to >= currentTabData.nodes.length) return;
    const newNodes = [...currentTabData.nodes];
    const [moved] = newNodes.splice(from, 1);
    newNodes.splice(to, 0, moved);
    updateTabData(prev => ({ ...prev, [activeTab]: { ...prev[activeTab], nodes: newNodes } }));
    scheduleSave();
  };

  const handleAddNode = () => {
    if (!eventId || !subId) { showSnack('Event/Sub IDが未定義', 'error'); return; }
    const currentNodes = currentTabData.nodes;
    const newId = getNextNodeId(currentNodes);
    const newNode = {
      id: newId,
      type: isSub ? 'subGroupNode' : 'customGroup',
      position: { x: 0, y: 0 },
      data: {
        label: isSub ? `Group: ${parentId} / Sub: ${newId}` : newId,
        description: newDescription.trim(),
        roles: [],
        subgroups: {},
        isSubGroup: isSub,
      },
    };
    updateTabData(prev => ({
      ...prev,
      [activeTab]: { ...prev[activeTab], nodes: [...prev[activeTab].nodes, newNode] }
    }));
    setAddDialogOpen(false);
    setNewDescription('');
    scheduleSave();
    showSnack(`ノード ${newId} を追加`);
  };

  const handleDeleteNode = (nodeId) => {
    updateTabData(prev => {
      const cur = prev[activeTab];
      return {
        ...prev,
        [activeTab]: {
          nodes: cur.nodes.filter(n => n.id !== nodeId),
          edges: cur.edges.filter(e => e.source !== nodeId && e.target !== nodeId),
        }
      };
    });
    scheduleSave();
    showSnack(`ノード ${nodeId} を削除`);
  };

  const handleCopyNode = (nodeId) => {
    const node = currentTabData.nodes.find(n => n.id === nodeId);
    if (node) { setCopiedNode(node); showSnack(`ノード ${nodeId} をコピー`); }
  };

  const handlePasteNode = () => {
    if (!copiedNode) { showSnack('コピーなし', 'warning'); return; }
    const newId = getNextNodeId(currentTabData.nodes);
    const newNode = {
      ...copiedNode,
      id: newId,
      type: isSub ? 'subGroupNode' : 'customGroup',
      data: {
        ...copiedNode.data,
        label: isSub ? `Group: ${parentId} / Sub: ${newId}` : newId,
        isSubGroup: isSub,
        subgroups: {},
        roles: copiedNode.data.roles?.map(r => ({ ...r, uniqueId: `${Date.now()}-${r.uniqueId}` })) || [],
      }
    };
    updateTabData(prev => ({
      ...prev,
      [activeTab]: { ...prev[activeTab], nodes: [...prev[activeTab].nodes, newNode] }
    }));
    scheduleSave();
    showSnack(`ノード ${newId} としてペースト`);
  };

  const handleOpenEditDialog = (nodeId) => {
    const node = currentTabData.nodes.find(n => n.id === nodeId);
    if (node) {
      setEditNodeId(nodeId);
      setEditNewId(nodeId);
      setNewDescription(node.data.description || '');
      setEditDialogOpen(true);
    }
  };

  const handleEditNode = () => {
    const newId = editNewId.trim();
    const currentNodes = currentTabData.nodes;

    // ID変更チェック
    if (newId && newId !== editNodeId && currentNodes.some(n => n.id === newId)) {
      showSnack('IDが重複しています', 'error'); return;
    }

    updateTabData(prev => {
      const cur = prev[activeTab];
      const updatedNodes = cur.nodes.map(n => {
        if (n.id !== editNodeId) return n;
        return {
          ...n,
          id: newId || editNodeId,
          data: {
            ...n.data,
            description: newDescription.trim(),
            label: isSub
              ? `Group: ${parentId} / Sub: ${newId || editNodeId}`
              : (newId || editNodeId),
          }
        };
      });
      const updatedEdges = cur.edges.map(e => ({
        ...e,
        source: e.source === editNodeId ? (newId || editNodeId) : e.source,
        target: e.target === editNodeId ? (newId || editNodeId) : e.target,
        id: `${e.source === editNodeId ? (newId || editNodeId) : e.source}-${e.target === editNodeId ? (newId || editNodeId) : e.target}`,
      }));
      return { ...prev, [activeTab]: { nodes: updatedNodes, edges: updatedEdges } };
    });

    setEditDialogOpen(false);
    scheduleSave();
    showSnack('更新しました');
  };

  // ── Role操作 ──
  const handleAddRole = (nodeId, newRole) => {
    updateTabData(prev => ({
      ...prev,
      [activeTab]: {
        ...prev[activeTab],
        nodes: prev[activeTab].nodes.map(n =>
          n.id === nodeId ? { ...n, data: { ...n.data, roles: [...(n.data.roles || []), newRole] } } : n
        )
      }
    }));
    scheduleSave();
  };

  const handleDeleteRole = (nodeId, uniqueId) => {
    updateTabData(prev => ({
      ...prev,
      [activeTab]: {
        ...prev[activeTab],
        nodes: prev[activeTab].nodes.map(n =>
          n.id === nodeId
            ? { ...n, data: { ...n.data, roles: n.data.roles.filter(r => r.uniqueId !== uniqueId) } }
            : n
        )
      }
    }));
    scheduleSave();
  };

  const handleSaveRole = (nodeId, uniqueId, formData) => {
    if (!eventId || !subId) { showSnack('Event/Sub IDが未定義', 'error'); return; }
    fetch(`/api/save-role-data/${eventId}/${subId}/${nodeId}/${uniqueId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ formData }),
    })
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then(() => {
        setRoleDataCache(prev => ({
          ...prev,
          [nodeId]: { ...(prev[nodeId] || {}), [uniqueId]: formData }
        }));
        updateTabData(prev => ({
          ...prev,
          [activeTab]: {
            ...prev[activeTab],
            nodes: prev[activeTab].nodes.map(n =>
              n.id === nodeId
                ? { ...n, data: { ...n.data, roles: n.data.roles.map(r => r.uniqueId === uniqueId ? { ...r, data: formData } : r) } }
                : n
            )
          }
        }));
      })
      .catch(e => showSnack('保存エラー: ' + e.message, 'error'));
  };

  const handleUpdateFormData = (nodeId, newState) => {
    // フォームデータをキャッシュに反映（保存はhandleSaveRoleで行う）
    setRoleDataCache(prev => {
      const nodeCache = prev[nodeId] || {};
      const updated = { ...nodeCache, ...newState };
      return { ...prev, [nodeId]: updated };
    });
  };

  // ── 接続操作 ──
  const handleAddEdge = (edge) => {
    const alreadyExists = currentTabData.edges.some(e => e.source === edge.source && e.target === edge.target);
    if (alreadyExists) { showSnack('既に接続済み', 'warning'); return; }
    updateTabData(prev => ({
      ...prev,
      [activeTab]: { ...prev[activeTab], edges: [...prev[activeTab].edges, edge] }
    }));
    scheduleSave();
  };

  const handleRemoveEdge = (edge) => {
    updateTabData(prev => ({
      ...prev,
      [activeTab]: {
        ...prev[activeTab],
        edges: prev[activeTab].edges.filter(e => !(e.source === edge.source && e.target === edge.target))
      }
    }));
    scheduleSave();
    showSnack(`接続 ${edge.source}→${edge.target} を削除`);
  };

  // ── グループ間移動（IDを更新して移動） ──
  const handleMoveToGroup = (nodeId, targetGroupId) => {
    // 現在のタブから取り除き、別グループのSubGroupタブへ追加
    const node = currentTabData.nodes.find(n => n.id === nodeId);
    if (!node) return;
    const targetTabId = `subgroup-${targetGroupId}`;
    const targetTabData = tabData[targetTabId] || { nodes: [], edges: [] };
    const newId = getNextNodeId(targetTabData.nodes);

    const newNode = {
      ...node,
      id: newId,
      data: {
        ...node.data,
        label: `Group: ${targetGroupId} / Sub: ${newId}`,
        isSubGroup: true,
      }
    };

    updateTabData(prev => {
      const cur = prev[activeTab];
      const targetCur = prev[targetTabId] || { nodes: [], edges: [] };
      return {
        ...prev,
        [activeTab]: {
          nodes: cur.nodes.filter(n => n.id !== nodeId),
          edges: cur.edges.filter(e => e.source !== nodeId && e.target !== nodeId),
        },
        [targetTabId]: {
          nodes: [...targetCur.nodes, newNode],
          edges: targetCur.edges,
        }
      };
    });
    scheduleSave();
    showSnack(`ノード ${nodeId} → グループ ${targetGroupId} に移動 (新ID: ${newId})`);
  };

  // ── 接続一覧表示（サマリー） ──
  const renderConnectionSummary = () => {
    const { edges, nodes } = currentTabData;
    if (!edges.length) return null;
    return (
      <Box sx={{ px: 2, pb: 1 }}>
        <Typography variant="caption" color="text.secondary" fontWeight="bold">接続一覧</Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.4 }}>
          {edges.map((e, i) => (
            <Chip
              key={i}
              label={`${e.source} → ${e.target}`}
              size="small"
              onDelete={() => handleRemoveEdge(e)}
              icon={<ArrowForwardIcon sx={{ fontSize: 12 }} />}
              sx={{ height: 20, fontSize: '0.65rem', bgcolor: 'rgba(0,200,255,0.1)', borderColor: 'cyan.400' }}
              variant="outlined"
            />
          ))}
        </Box>
      </Box>
    );
  };

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', bgcolor: '#0f0f1e' }}>
      {/* ローディング */}
      <Backdrop open={isLoading} sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
        <CircularProgress color="inherit" />
      </Backdrop>

      {/* ── タブバー ── */}
      <AppBar position="static" sx={{ bgcolor: '#1a1a35' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          <Tabs
            value={activeTab}
            onChange={(e, v) => handleTabSwitch(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              flex: 1, minHeight: 38,
              '& .MuiTab-root': { minHeight: 38, py: 0, fontSize: '0.72rem', color: 'rgba(255,255,255,0.6)' },
              '& .Mui-selected': { color: 'white !important' },
              '& .MuiTabs-indicator': { bgcolor: 'cyan' },
            }}
          >
            {tabs.map(tab => (
              <Tab key={tab.id} value={tab.id} label={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  {tab.type === 'subgroup' ? <AccountTreeIcon sx={{ fontSize: 12 }} /> : null}
                  <span>{tab.label}</span>
                  {tab.id !== 'main' && (
                    <IconButton size="small" sx={{ p: 0.1, color: 'inherit', ml: 0.25 }}
                      onClick={(e) => { e.stopPropagation(); handleTabClose(tab.id); }}>
                      <CloseIcon sx={{ fontSize: 11 }} />
                    </IconButton>
                  )}
                </Box>
              } />
            ))}
          </Tabs>
        </Box>

        {/* ── ツールバー ── */}
        <Box sx={{
          px: 1.5, py: 0.75, display: 'flex', gap: 1, alignItems: 'center',
          bgcolor: '#12122a', borderBottom: '1px solid rgba(255,255,255,0.08)'
        }}>
          <Button variant="contained" size="small" color="primary"
            startIcon={<AddIcon />}
            onClick={() => { setAddDialogOpen(true); setNewDescription(''); }}
            disabled={isLoading}
            sx={{ fontSize: '0.72rem', bgcolor: '#2563eb' }}>
            ノード追加
          </Button>

          <Tooltip title={copiedNode ? `ペースト: ノード ${copiedNode.id}` : 'コピーなし'}>
            <span>
              <Button variant="outlined" size="small"
                startIcon={<ContentPasteIcon />}
                onClick={handlePasteNode}
                disabled={isLoading || !copiedNode}
                sx={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.3)' }}>
                ペースト
              </Button>
            </span>
          </Tooltip>

          {copiedNode && (
            <Chip
              label={`コピー中: ${copiedNode.id}`}
              size="small"
              onDelete={() => setCopiedNode(null)}
              sx={{ bgcolor: 'rgba(255,255,255,0.15)', color: 'white', fontSize: '0.65rem', height: 22 }}
            />
          )}

          <Tooltip title="Role定義(型・オプション)を変更した場合、ここを押すと最新のスキーマを取り直します">
            <Button variant="outlined" size="small"
              startIcon={<RefreshIcon />}
              onClick={async () => {
                await refreshGlobalRolesAndSchemas();
                showSnack('Roleスキーマを再取得しました');
              }}
              disabled={isLoading}
              sx={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.3)' }}>
              Roleスキーマ再取得
            </Button>
          </Tooltip>

          <Tooltip title="このイベントに属する全Sub・全ノードのTransactionを1つのテキストでまとめて編集します（既存ノードの内容編集のみ。ノード自体の追加は初期状態では不可）">
            <Button variant="outlined" size="small"
              startIcon={<EditNoteIcon />}
              onClick={handleOpenAllEditDialog}
              disabled={isLoading || !eventId}
              sx={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.3)' }}>
              全体編集(全Sub一括)
            </Button>
          </Tooltip>

          <Tooltip title="現在開いているSubだけを、Lua形式のテキストで編集します（既存ノードの内容編集のみ。ノード自体の追加は初期状態では不可）">
            <Button variant="outlined" size="small"
              startIcon={<EditNoteIcon />}
              onClick={handleOpenSubEditDialog}
              disabled={isLoading || !eventId || !subId}
              sx={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.3)' }}>
              このSubのみ編集
            </Button>
          </Tooltip>

          <Box sx={{ flex: 1 }} />

          {/* ノード数・接続数サマリー */}
          <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.5)' }}>
            {currentTabData.nodes.length} ノード / {currentTabData.edges.length} 接続
          </Typography>

          <Tooltip title="現在のタブのノード・接続をCSVとしてダウンロードします">
            <Button variant="outlined" size="small"
              startIcon={<FileDownloadIcon />}
              onClick={() => exportTabToCsv(currentTabData, activeTab)}
              sx={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.3)' }}>
              CSV出力
            </Button>
          </Tooltip>
          <Tooltip title="CSVを読み込んで現在のタブへ反映します（内容は上書きされます）">
            <Button variant="outlined" size="small" component="label"
              startIcon={<FileUploadIcon />}
              disabled={isLoading}
              sx={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.3)' }}>
              CSV入力
              <input
                type="file"
                accept=".csv,text/csv"
                hidden
                onChange={async (e) => {
                  const file = e.target.files && e.target.files[0];
                  e.target.value = '';
                  if (!file) return;
                  try {
                    const text = await file.text();
                    const parsed = parseCsvToTabData(text);
                    updateTabData(prev => ({ ...prev, [activeTab]: parsed }));
                    scheduleSave();
                    showSnack(`CSVから ${parsed.nodes.length} ノード / ${parsed.edges.length} 接続を読み込みました`);
                  } catch (err) {
                    console.error('CSV読み込みエラー:', err);
                    showSnack('CSVの読み込みに失敗しました: ' + err.message, 'error');
                  }
                }}
              />
            </Button>
          </Tooltip>

          <Button variant="contained" size="small" color="success"
            startIcon={<SaveIcon />}
            onClick={saveCurrentTab}
            disabled={isLoading}
            sx={{ fontSize: '0.72rem' }}>
            保存
          </Button>
        </Box>
      </AppBar>

      {/* ── メインコンテンツ ── */}
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {/* 接続サマリー */}
        {renderConnectionSummary()}

        <BlockCanvas
          nodes={currentTabData.nodes}
          edges={currentTabData.edges}
          isSub={isSub}
          globalRoles={globalRoles}
          roleDataCache={roleDataCache}
          roleFormSchemas={roleFormSchemas}
          eventId={eventId}
          subId={subId}
          flushStructureSave={saveCurrentTab}
          onRefreshRoles={refreshGlobalRolesAndSchemas}
          onReorder={handleReorder}
          onDelete={handleDeleteNode}
          onCopy={handleCopyNode}
          onEditId={handleOpenEditDialog}
          onSubGroupOpen={(nodeId) => handleTabSwitch(`subgroup-${nodeId}`, nodeId)}
          onAddRole={handleAddRole}
          onDeleteRole={handleDeleteRole}
          onSaveRole={handleSaveRole}
          onAddEdge={handleAddEdge}
          onRemoveEdge={handleRemoveEdge}
          onUpdateFormData={handleUpdateFormData}
          onMoveToGroup={handleMoveToGroup}
        />
      </Box>

      {/* ── 全体編集ダイアログ(イベント内の全Sub・全ノードのTransactionを一括編集) ── */}
      <Dialog open={showAllEditDialog} onClose={() => setShowAllEditDialog(false)} maxWidth="lg" fullWidth>
        <DialogTitle>
          全体編集（{eventId} / 全Sub一括）
          <Typography variant="caption" display="block" color="text.secondary">
            既存ノードのRole呼び出し内容(追加・削除・値の変更)をまとめて編集できます。
            「# 例:」で始まる行はあくまで書き方の案内・記入例であり、そのまま残して適用しても無視されるだけで、
            グループが増えたり内容が化けたりすることはありません。
            新しいグループを追加したい場合は、下のチェックを入れたうえで
            新しい見出し（# ==== SUB:番号 NODE:新しいID ====）を書き足してください。
            NODE:親ID/子ID のように "/" で区切ると、親グループの中に新しいサブグループを作成できます。
            ただし新規作成したグループは他のノードと接続されていない状態で追加されるため、必要に応じて
            通常のGUI操作で他のノードと接続してください。既存の見出しコメントは削除・改変しないでください。
          </Typography>
        </DialogTitle>
        <DialogContent sx={{ p: 0 }}>
          {allEditLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <Box sx={{ px: 2, pt: 1 }}>
                <FormControlLabel
                  control={(
                    <Checkbox
                      size="small"
                      checked={allEditAllowNewGroups}
                      onChange={(e) => setAllEditAllowNewGroups(e.target.checked)}
                    />
                  )}
                  label={(
                    <Typography variant="caption">
                      新しいグループの追加を許可する（未知の見出しを新規ノードとして作成します。OFFの場合、未知の見出しは作成されず警告になります）
                    </Typography>
                  )}
                />
              </Box>
              <ScenarioTransactionCodeEditor
                value={allEditText}
                onChange={setAllEditText}
                roleNames={globalRoleNamesForDsl}
                roleSchemas={roleFormSchemas}
                height="60vh"
              />
              {allEditDiagnostics.length > 0 && (
                <Box sx={{ p: 1, maxHeight: 160, overflow: 'auto', bgcolor: 'rgba(255,0,0,0.06)' }}>
                  {allEditDiagnostics.map((d, i) => (
                    <Typography key={i} variant="caption" color="error" display="block">
                      {d.message}
                    </Typography>
                  ))}
                </Box>
              )}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowAllEditDialog(false)} disabled={allEditApplying}>閉じる</Button>
          <Button onClick={handleOpenAllEditDialog} disabled={allEditLoading || allEditApplying}>再取得</Button>
          <Button
            variant="contained"
            onClick={handleApplyAllEdit}
            disabled={allEditLoading || allEditApplying}
          >
            {allEditApplying ? '適用中...' : '適用'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Sub編集ダイアログ(現在開いているSubだけをLua形式でまとめて編集) ── */}
      <Dialog open={showSubEditDialog} onClose={() => setShowSubEditDialog(false)} maxWidth="lg" fullWidth>
        <DialogTitle>
          Sub編集（{eventId} / SUB:{subId} のみ）
          <Typography variant="caption" display="block" color="text.secondary">
            現在開いているSubだけを対象に、既存ノードのRole呼び出し内容(追加・削除・値の変更)を
            まとめて編集できます。「# 例:」で始まる行はあくまで書き方の案内・記入例であり、
            そのまま残して適用しても無視されるだけで、グループが増えたり内容が化けたりすることはありません。
            新しいグループを追加したい場合は、下のチェックを入れたうえで
            新しい見出し（# ==== SUB:{subId} NODE:新しいID ====）を書き足してください。
            他のSubの内容をまとめて編集したい場合は「全体編集(全Sub一括)」を使ってください。
          </Typography>
        </DialogTitle>
        <DialogContent sx={{ p: 0 }}>
          {subEditLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <Box sx={{ px: 2, pt: 1 }}>
                <FormControlLabel
                  control={(
                    <Checkbox
                      size="small"
                      checked={subEditAllowNewGroups}
                      onChange={(e) => setSubEditAllowNewGroups(e.target.checked)}
                    />
                  )}
                  label={(
                    <Typography variant="caption">
                      新しいグループの追加を許可する（未知の見出しを新規ノードとして作成します。OFFの場合、未知の見出しは作成されず警告になります）
                    </Typography>
                  )}
                />
              </Box>
              <ScenarioTransactionCodeEditor
                value={subEditText}
                onChange={setSubEditText}
                roleNames={globalRoleNamesForDsl}
                roleSchemas={roleFormSchemas}
                height="60vh"
              />
              {subEditDiagnostics.length > 0 && (
                <Box sx={{ p: 1, maxHeight: 160, overflow: 'auto', bgcolor: 'rgba(255,0,0,0.06)' }}>
                  {subEditDiagnostics.map((d, i) => (
                    <Typography key={i} variant="caption" color="error" display="block">
                      {d.message}
                    </Typography>
                  ))}
                </Box>
              )}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowSubEditDialog(false)} disabled={subEditApplying}>閉じる</Button>
          <Button onClick={handleOpenSubEditDialog} disabled={subEditLoading || subEditApplying}>再取得</Button>
          <Button
            variant="contained"
            onClick={handleApplySubEdit}
            disabled={subEditLoading || subEditApplying}
          >
            {subEditApplying ? '適用中...' : '適用'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── ノード追加ダイアログ ── */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AddIcon color="primary" />
            ノード追加
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
            次のID: <strong>{getNextNodeId(currentTabData.nodes)}</strong>（自動採番）
          </Alert>
          <TextField
            autoFocus fullWidth size="small"
            label="説明（任意）"
            value={newDescription}
            onChange={e => setNewDescription(e.target.value)}
            multiline
            minRows={2}
            maxRows={6}
            helperText="改行して複数行入力できます"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)} color="inherit">キャンセル</Button>
          <Button onClick={handleAddNode} variant="contained">追加</Button>
        </DialogActions>
      </Dialog>

      {/* ── ノード編集ダイアログ ── */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <EditIcon color="primary" />
            ノード編集
          </Box>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 0.5 }}>
            <TextField
              fullWidth size="small"
              label="ノードID"
              value={editNewId}
              onChange={e => setEditNewId(e.target.value)}
              helperText="変更するとエッジのIDも自動更新されます"
            />
            <TextField
              autoFocus fullWidth size="small"
              label="説明"
              value={newDescription}
              onChange={e => setNewDescription(e.target.value)}
              multiline
              minRows={2}
              maxRows={6}
              helperText="改行して複数行入力できます"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)} color="inherit">キャンセル</Button>
          <Button onClick={handleEditNode} variant="contained">保存</Button>
        </DialogActions>
      </Dialog>

      {/* ── Snackbar ── */}
      <Snackbar open={snack.open} autoHideDuration={3000} onClose={hideSnack} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}>
        <Alert onClose={hideSnack} severity={snack.severity} variant="filled" sx={{ minWidth: 220 }}>
          {snack.msg}
        </Alert>
      </Snackbar>
    </Box>
  );
}

export default ScenarioEventTransition;