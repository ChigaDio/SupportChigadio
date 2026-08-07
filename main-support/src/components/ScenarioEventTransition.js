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
  InputLabel, Stack
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
import RoleInputFactory from '../scenario/RoleInputFactory';
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
  roleFormSchemas, eventId, subId, onSave, onDeleteRole
}) => {
  const [roleForms, setRoleForms] = useState({});
  const [formErrors, setFormErrors] = useState({});
  const [loadingForms, setLoadingForms] = useState({});
  const { snack, show: showSnack, hide: hideSnack } = useSnack();
  const loadedRef = useRef({});

  // ロールフォーム読み込み（重複防止）
  useEffect(() => {
    if (!open || !roles.length) return;
    roles.forEach(async (role) => {
      const uid = role.uniqueId;
      if (loadedRef.current[uid]) return;
      loadedRef.current[uid] = true;
      setLoadingForms(prev => ({ ...prev, [uid]: true }));
      try {
        // Drawerを開くたびに必ず最新のスキーマを取得する。
        // roleFormSchemas(キャンバス側のキャッシュ)は初回ロード時のまま更新されないため、
        // Role定義(型・bit/color/bezierのoptionsなど)を編集した直後でも
        // 確実に反映されるよう、ここではキャッシュを使わない。
        const schema = await fetchSchemaOnce(role.name, true);
        const FormComp = await RoleInputFactory.getForm(
          role.name,
          formDataState[uid] || role.data || [],
          (formData) => setFormDataState(prev => ({ ...prev, [uid]: formData })),
          schema
        );
        setRoleForms(prev => ({ ...prev, [uid]: FormComp }));
      } catch (err) {
        setFormErrors(prev => ({ ...prev, [uid]: err.message }));
      } finally {
        setLoadingForms(prev => ({ ...prev, [uid]: false }));
      }
    });
  }, [open, roles, roleFormSchemas]);

  // Drawer閉じたらキャッシュリセット（次回再ロード用）
  const handleClose = () => {
    loadedRef.current = {};
    setRoleForms({});
    setFormErrors({});
    onClose();
  };

  const handleSave = (uniqueId) => {
    onSave(uniqueId, formDataState[uniqueId]);
    showSnack('保存しました');
  };
  const handleBatchSave = () => {
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
            <Button variant="contained" size="small" color="success"
              startIcon={<SaveIcon />} onClick={handleBatchSave}>
              一括保存
            </Button>
            <IconButton onClick={handleClose} sx={{ color: 'white' }}><CloseIcon /></IconButton>
          </Box>
        </Box>

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
  globalRoles, roleDataCache, roleFormSchemas, eventId, subId,
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
  eventId, subId,
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
  const [roleDataCache, setRoleDataCache] = useState({});
  const [roleFormSchemas, setRoleFormSchemas] = useState({});

  const { snack, show: showSnack, hide: hideSnack } = useSnack();

  // ============================================================
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

    fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saveData) })
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); })
      .catch(e => {
        console.error('保存エラー:', e);
        showSnack('保存に失敗しました。再度お試しください', 'error');
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
    performSave(activeTabRef.current);
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
                const fresh = {};
                for (const role of globalRoles) {
                  invalidateRoleSchemaCache(role.name);
                  try {
                    fresh[role.name] = await fetchSchemaOnce(role.name, true);
                  } catch (e) {
                    console.error(`スキーマ再取得エラー (${role.name}):`, e);
                  }
                }
                setRoleFormSchemas(fresh);
                showSnack('Roleスキーマを再取得しました');
              }}
              disabled={isLoading}
              sx={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)', borderColor: 'rgba(255,255,255,0.3)' }}>
              Roleスキーマ再取得
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