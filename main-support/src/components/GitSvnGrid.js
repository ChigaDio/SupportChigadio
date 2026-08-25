import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Box, Typography, Paper, Button, Chip, TextField, Tabs, Tab, Divider, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert, CircularProgress,
  Select, MenuItem, FormControl, InputLabel, Autocomplete, FormControlLabel, Checkbox,
  List, ListItem, ListItemText, Tooltip, Stack,
} from '@mui/material';
import SourceIcon from '@mui/icons-material/Source';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import SyncIcon from '@mui/icons-material/Sync';
import CallMergeIcon from '@mui/icons-material/CallMerge';
import AltRouteIcon from '@mui/icons-material/AltRoute';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import HistoryIcon from '@mui/icons-material/History';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import CloseIcon from '@mui/icons-material/Close';
import TerminalIcon from '@mui/icons-material/Terminal';
import DifferenceIcon from '@mui/icons-material/Difference';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CheckboxTree from './CheckboxTree';
import DiffViewer from './DiffViewer';

const STATUS_COLOR = {
  M: 'warning', A: 'success', D: 'error', R: 'info', C: 'error', U: 'error', '?': 'default', '!': 'default',
};

const LANE_COLORS = [
  '#00c2ff', '#ff6b6b', '#ffd166', '#06d6a0', '#c77dff', '#f4a261', '#4cc9f0', '#f72585',
];

const MONO = '"Roboto Mono", "Share Tech Mono", Consolas, monospace';

// ============================================================
// ファイル一覧 → CheckboxTree用ノードツリーへの変換
// ============================================================
function buildFileTree(files) {
  const root = { children: new Map() };
  files.forEach((f) => {
    const parts = f.path.split('/');
    let node = root;
    parts.forEach((part, idx) => {
      const isLeaf = idx === parts.length - 1;
      if (!node.children) node.children = new Map();
      if (!node.children.has(part)) {
        node.children.set(part, {
          name: part,
          id: parts.slice(0, idx + 1).join('/'),
          children: isLeaf ? null : new Map(),
          file: isLeaf ? f : null,
        });
      }
      node = node.children.get(part);
    });
  });
  return root;
}

function collectLeaves(node) {
  if (node.file) return [node.file];
  let leaves = [];
  if (node.children) {
    for (const child of node.children.values()) leaves = leaves.concat(collectLeaves(child));
  }
  return leaves;
}

function toCheckboxNodes(mapNode, selectedPaths, toggle, onShowDiff) {
  return Array.from(mapNode.children.values()).map((n) => {
    if (n.file) {
      const f = n.file;
      return {
        id: f.path,
        label: n.name,
        checked: selectedPaths.has(f.path),
        disabled: !f.selectable,
        onToggle: (checked) => toggle([f.path], checked),
        badge: (
          <Stack direction="row" spacing={0.5} alignItems="center">
            <Chip size="small" label={f.statusLabel} color={STATUS_COLOR[f.statusCode] || 'default'} sx={{ height: 20, fontSize: 11 }} />
            {f.staged && <Chip size="small" label="staged" variant="outlined" sx={{ height: 20, fontSize: 10 }} />}
            <IconButton size="small" onClick={(e) => { e.stopPropagation(); onShowDiff(f.path); }} title="差分を見る">
              <DifferenceIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Stack>
        ),
      };
    }
    const leaves = collectLeaves(n).filter((f) => f.selectable);
    const leafPaths = leaves.map((f) => f.path);
    const selectedCount = leafPaths.filter((p) => selectedPaths.has(p)).length;
    const checked = leafPaths.length === 0 ? false
      : selectedCount === leafPaths.length ? true
        : selectedCount > 0 ? 'indeterminate' : false;
    return {
      id: n.id,
      label: n.name,
      checked,
      disabled: leafPaths.length === 0,
      onToggle: (c) => toggle(leafPaths, c),
      children: toCheckboxNodes(n, selectedPaths, toggle, onShowDiff),
    };
  });
}

// ============================================================
// コミットグラフ（レーン方式のシンプルなSVGグラフ）
// ============================================================
function CommitGraph({ commits }) {
  const [hoverId, setHoverId] = useState(null);
  if (!commits || commits.length === 0) {
    return <Typography color="text.secondary" sx={{ p: 2 }}>コミットがありません。</Typography>;
  }
  const rowHeight = 46;
  const laneWidth = 20;
  const leftPad = 16;
  const maxLane = Math.max(0, ...commits.map((c) => c.lane || 0));
  const gutterWidth = leftPad * 2 + (maxLane + 1) * laneWidth;
  const indexById = {};
  commits.forEach((c, i) => { indexById[c.id] = i; });

  const nodePos = (i) => ({
    x: leftPad + (commits[i].lane || 0) * laneWidth,
    y: i * rowHeight + rowHeight / 2,
  });

  return (
    <Box sx={{ position: 'relative', border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
      <svg
        width={gutterWidth}
        height={commits.length * rowHeight}
        style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
      >
        {commits.map((c, i) => {
          const { x, y } = nodePos(i);
          return (c.parents || []).map((pid) => {
            const pi = indexById[pid];
            if (pi === undefined) return null;
            const { x: px, y: py } = nodePos(pi);
            const color = LANE_COLORS[(c.lane || 0) % LANE_COLORS.length];
            const d = x === px
              ? `M ${x} ${y} L ${px} ${py}`
              : `M ${x} ${y} C ${x} ${y + rowHeight / 2}, ${px} ${py - rowHeight / 2}, ${px} ${py}`;
            return <path key={`${c.id}-${pid}`} d={d} stroke={color} strokeWidth={2} fill="none" opacity={0.75} />;
          });
        })}
        {commits.map((c, i) => {
          const { x, y } = nodePos(i);
          const color = LANE_COLORS[(c.lane || 0) % LANE_COLORS.length];
          return (
            <circle key={c.id} cx={x} cy={y} r={hoverId === c.id ? 6.5 : 5} fill={color}
              stroke="#0e1420" strokeWidth={1.5} />
          );
        })}
      </svg>
      <Box>
        {commits.map((c) => (
          <Box
            key={c.id}
            onMouseEnter={() => setHoverId(c.id)}
            onMouseLeave={() => setHoverId(null)}
            sx={{ display: 'flex', alignItems: 'center', height: rowHeight, cursor: 'default' }}
          >
            <Box sx={{ width: gutterWidth, flexShrink: 0 }} />
            <Box
              sx={{
                flexGrow: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 1.5,
                height: rowHeight - 6, px: 1.5, borderRadius: 1.5,
                bgcolor: hoverId === c.id ? 'action.hover' : 'transparent',
                transition: 'background-color 0.15s ease',
              }}
            >
              <Chip
                size="small"
                label={c.id.slice(0, 7)}
                sx={{ fontFamily: MONO, fontWeight: 700, height: 22 }}
              />
              <Typography variant="body2" noWrap sx={{ flexGrow: 1, minWidth: 0 }}>
                {c.message}
              </Typography>
              {(c.refs || []).map((r) => (
                <Chip key={r} size="small" variant="outlined" color="primary" label={r} sx={{ height: 20, fontSize: 10 }} />
              ))}
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                {c.author}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap', fontFamily: MONO }}>
                {(c.date || '').slice(0, 16).replace('T', ' ')}
              </Typography>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ============================================================
// 実行中ジョブの端末風ログダイアログ
// ============================================================
function JobConsole({ open, onClose, status }) {
  const logRef = useRef(null);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status?.log]);

  const running = status?.status === 'running';
  const isError = status?.status === 'error';

  return (
    <Dialog open={open} onClose={running ? undefined : onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <TerminalIcon fontSize="small" />
        VCS操作の実行状況
      </DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
          {running && <CircularProgress size={18} />}
          {status?.status === 'done' && <CheckCircleIcon color="success" fontSize="small" />}
          {isError && <CloseIcon color="error" fontSize="small" />}
          <Typography variant="body2">{status?.message || '準備中...'}</Typography>
        </Box>
        <Box
          ref={logRef}
          sx={{
            bgcolor: '#0b0f16', color: '#39ff9d', fontFamily: MONO, fontSize: 12.5,
            p: 1.5, borderRadius: 1, height: 260, overflowY: 'auto', whiteSpace: 'pre-wrap',
            border: '1px solid rgba(57,255,157,0.25)',
          }}
        >
          {status?.log || '(出力はまだありません)'}
        </Box>
        {isError && <Alert severity="error" sx={{ mt: 2 }}>{status.message}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={running}>閉じる</Button>
      </DialogActions>
    </Dialog>
  );
}

// ============================================================
// メインコンポーネント
// ============================================================
function GitSvnGrid() {
  const [status, setStatus] = useState(null); // /api/vcs/status のレスポンス
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('changes');

  const [selectedPaths, setSelectedPaths] = useState(new Set());
  const [commitMessage, setCommitMessage] = useState('');
  const [autoPush, setAutoPush] = useState(false);

  const [branches, setBranches] = useState([]);
  const [branchFilter, setBranchFilter] = useState('');

  const [commits, setCommits] = useState([]);
  const [logBranch, setLogBranch] = useState('');
  const [logLoading, setLogLoading] = useState(false);

  const [jobOpen, setJobOpen] = useState(false);
  const [jobStatus, setJobStatus] = useState(null);
  const pollRef = useRef(null);
  const pendingActionRef = useRef(null);

  const [diffOpen, setDiffOpen] = useState(false);
  const [diffTarget, setDiffTarget] = useState('');
  const [diffData, setDiffData] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);

  const [branchDialogOpen, setBranchDialogOpen] = useState(false);
  const [newBranchName, setNewBranchName] = useState('');
  const [newBranchFrom, setNewBranchFrom] = useState('');
  const [newBranchCheckout, setNewBranchCheckout] = useState(true);

  const [mergeDialogOpen, setMergeDialogOpen] = useState(false);
  const [mergeTarget, setMergeTarget] = useState('');

  const [pushDialogOpen, setPushDialogOpen] = useState(false);
  const [pushSetUpstream, setPushSetUpstream] = useState(false);

  const fetchStatus = useCallback(() => {
    setLoading(true);
    fetch('/api/vcs/status')
      .then((r) => r.json())
      .then((data) => {
        setStatus(data);
        setSelectedPaths((prev) => {
          const validPaths = new Set((data.files || []).filter((f) => f.selectable).map((f) => f.path));
          const next = new Set();
          prev.forEach((p) => { if (validPaths.has(p)) next.add(p); });
          return next;
        });
      })
      .catch(() => setStatus({ repo: null, error: '状態取得に失敗しました' }))
      .finally(() => setLoading(false));
  }, []);

  const fetchBranches = useCallback(() => {
    fetch('/api/vcs/branches').then((r) => r.json()).then((data) => setBranches(data.branches || [])).catch(() => {});
  }, []);

  const fetchLog = useCallback((branch) => {
    setLogLoading(true);
    const qs = branch ? `?branch=${encodeURIComponent(branch)}` : '';
    fetch(`/api/vcs/log${qs}`)
      .then((r) => r.json())
      .then((data) => setCommits(data.commits || []))
      .catch(() => setCommits([]))
      .finally(() => setLogLoading(false));
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  useEffect(() => {
    if (status?.repo) {
      fetchBranches();
      fetchLog(logBranch);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.repo?.root]);

  const refreshAll = useCallback(() => {
    fetchStatus();
    fetchBranches();
    fetchLog(logBranch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchStatus, fetchBranches, fetchLog, logBranch]);

  // --- ジョブ実行共通処理 ---
  const pollJob = (jobId, onDone) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/vcs/progress/${jobId}`);
        const data = await res.json();
        if (!res.ok) {
          clearInterval(pollRef.current);
          setJobStatus({ status: 'error', message: data.error, log: '' });
          return;
        }
        setJobStatus(data);
        if (data.status === 'done' || data.status === 'error') {
          clearInterval(pollRef.current);
          refreshAll();
          if (data.status === 'done' && onDone) onDone();
        }
      } catch (e) {
        clearInterval(pollRef.current);
        setJobStatus({ status: 'error', message: e.message, log: '' });
      }
    }, 600);
  };

  const startJob = async (url, body, onDone) => {
    setJobStatus({ status: 'running', message: '開始しています...', log: '' });
    setJobOpen(true);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      pollJob(data.jobId, onDone);
    } catch (e) {
      setJobStatus({ status: 'error', message: e.message, log: '' });
    }
  };

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // --- ファイル選択（フォルダ単位のカスケード込み） ---
  const toggleSelection = (paths, checked) => {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      paths.forEach((p) => (checked ? next.add(p) : next.delete(p)));
      return next;
    });
  };

  const handleShowDiff = (path) => {
    setDiffTarget(path);
    setDiffOpen(true);
    setDiffLoading(true);
    setDiffData(null);
    fetch(`/api/vcs/diff?path=${encodeURIComponent(path)}`)
      .then((r) => r.json())
      .then((data) => setDiffData(data))
      .catch((e) => setDiffData({ diffText: null, summary: 'エラー: ' + e.message }))
      .finally(() => setDiffLoading(false));
  };

  const handleCommit = () => {
    if (!commitMessage.trim()) { alert('コミットメッセージを入力してください'); return; }
    if (selectedPaths.size === 0) { alert('コミットするファイルを選択してください'); return; }
    startJob(
      '/api/vcs/commit',
      { message: commitMessage, paths: Array.from(selectedPaths) },
      () => {
        setCommitMessage('');
        setSelectedPaths(new Set());
        if (autoPush && status?.repo?.type === 'git') {
          setTimeout(() => startJob('/api/vcs/push', {}), 300);
        }
      },
    );
  };

  const handleFetch = () => startJob('/api/vcs/fetch', {});
  const handlePull = () => {
    if (!window.confirm('リモートの変更を取り込みます（pull / update）。よろしいですか？')) return;
    startJob('/api/vcs/pull', {});
  };
  const handlePushConfirm = () => {
    setPushDialogOpen(false);
    startJob('/api/vcs/push', { setUpstream: pushSetUpstream, branch: status?.branch });
  };
  const handleMergeConfirm = () => {
    if (!mergeTarget.trim()) return;
    setMergeDialogOpen(false);
    const isGit = status?.repo?.type === 'git';
    startJob('/api/vcs/merge', isGit ? { branch: mergeTarget } : { url: mergeTarget });
    setMergeTarget('');
  };
  const handleBranchCreateConfirm = () => {
    if (!newBranchName.trim()) return;
    setBranchDialogOpen(false);
    startJob('/api/vcs/branch', { name: newBranchName, from: newBranchFrom || undefined, checkout: newBranchCheckout });
    setNewBranchName('');
    setNewBranchFrom('');
  };
  const handleSwitch = (branch) => {
    const isGit = status?.repo?.type === 'git';
    if (isGit && branch.current) return;
    if (!window.confirm(`ブランチ「${branch.name}」に切り替えますか？`)) return;
    startJob('/api/vcs/checkout', isGit ? { name: branch.name } : { url: branch.url });
  };

  const fileTree = useMemo(() => buildFileTree(status?.files || []), [status?.files]);
  const treeNodes = useMemo(
    () => toCheckboxNodes(fileTree, selectedPaths, toggleSelection, handleShowDiff),
    [fileTree, selectedPaths],
  );

  const visibleBranches = useMemo(() => {
    const kw = branchFilter.trim().toLowerCase();
    return branches.filter((b) => !kw || b.name.toLowerCase().includes(kw));
  }, [branches, branchFilter]);

  const repo = status?.repo;
  const caps = status?.capabilities || {};
  const isGit = repo?.type === 'git';

  return (
    <Box sx={{ p: 3 }}>
      {/* --- ヘッダー: リポジトリの現在地を一目で --- */}
      <Paper
        sx={{
          p: 2.5, mb: 3, borderRadius: 3, color: '#fff',
          background: 'linear-gradient(135deg, #10151f 0%, #1a2233 55%, #0d1420 100%)',
          border: '1px solid rgba(0,194,255,0.18)',
          boxShadow: '0 0 30px rgba(0,194,255,0.08)',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <SourceIcon sx={{ fontSize: 34, color: '#00c2ff' }} />
          <Box sx={{ flexGrow: 1, minWidth: 240 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: 0.5 }}>
              バージョン管理
            </Typography>
            {repo ? (
              <Typography variant="caption" sx={{ fontFamily: MONO, color: 'rgba(255,255,255,0.6)' }}>
                {repo.root}{repo.dataRelPath !== '.' ? `  (data: ${repo.dataRelPath})` : ''}
              </Typography>
            ) : (
              <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.6)' }}>
                リポジトリ未検出
              </Typography>
            )}
          </Box>
          {repo && (
            <Chip
              icon={<AccountTreeIcon sx={{ color: '#0d1420 !important' }} />}
              label={repo.type.toUpperCase()}
              sx={{ bgcolor: '#00c2ff', color: '#0d1420', fontWeight: 700 }}
            />
          )}
          {status?.branch && (
            <Chip
              icon={<AltRouteIcon sx={{ color: '#0d1420 !important' }} />}
              label={status.branch}
              sx={{ bgcolor: '#06d6a0', color: '#0d1420', fontWeight: 700, fontFamily: MONO }}
            />
          )}
          {status?.aheadBehind && (
            <Stack direction="row" spacing={0.5}>
              {status.aheadBehind.ahead > 0 && (
                <Chip size="small" icon={<ArrowUpwardIcon sx={{ fontSize: 14 }} />} label={status.aheadBehind.ahead}
                  sx={{ bgcolor: 'rgba(255,209,102,0.18)', color: '#ffd166' }} />
              )}
              {status.aheadBehind.behind > 0 && (
                <Chip size="small" icon={<ArrowDownwardIcon sx={{ fontSize: 14 }} />} label={status.aheadBehind.behind}
                  sx={{ bgcolor: 'rgba(255,107,107,0.18)', color: '#ff6b6b' }} />
              )}
            </Stack>
          )}
        </Box>

        {repo && (
          <Box sx={{ display: 'flex', gap: 1, mt: 2.5, flexWrap: 'wrap' }}>
            {isGit && (
              <Button size="small" variant="contained" startIcon={<CloudDownloadIcon />}
                onClick={handleFetch} disabled={!caps.canFetch}
                sx={{ bgcolor: 'rgba(255,255,255,0.08)', '&:hover': { bgcolor: 'rgba(255,255,255,0.16)' } }}>
                Fetch
              </Button>
            )}
            <Button size="small" variant="contained" startIcon={<SyncIcon />}
              onClick={handlePull} disabled={!caps.canPull}
              sx={{ bgcolor: 'rgba(255,255,255,0.08)', '&:hover': { bgcolor: 'rgba(255,255,255,0.16)' } }}>
              {isGit ? 'Pull' : 'Update'}
            </Button>
            {isGit && (
              <Button size="small" variant="contained" startIcon={<CloudUploadIcon />}
                onClick={() => { setPushSetUpstream(!status?.aheadBehind); setPushDialogOpen(true); }}
                disabled={!caps.canPush}
                sx={{ bgcolor: 'rgba(255,255,255,0.08)', '&:hover': { bgcolor: 'rgba(255,255,255,0.16)' } }}>
                Push
              </Button>
            )}
            <Button size="small" variant="contained" startIcon={<CallMergeIcon />}
              onClick={() => setMergeDialogOpen(true)} disabled={!caps.canMerge}
              sx={{ bgcolor: 'rgba(255,255,255,0.08)', '&:hover': { bgcolor: 'rgba(255,255,255,0.16)' } }}>
              Merge
            </Button>
            <Button size="small" variant="contained" startIcon={<AddIcon />}
              onClick={() => setBranchDialogOpen(true)} disabled={!caps.canBranch}
              sx={{ bgcolor: 'rgba(255,255,255,0.08)', '&:hover': { bgcolor: 'rgba(255,255,255,0.16)' } }}>
              新しいブランチ
            </Button>
            <Button size="small" startIcon={<RefreshIcon />} onClick={refreshAll}
              sx={{ ml: 'auto', color: 'rgba(255,255,255,0.75)' }}>
              更新
            </Button>
          </Box>
        )}
      </Paper>

      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress /></Box>
      )}

      {!loading && !repo && (
        <Alert severity="info">
          この data フォルダは Git / SVN リポジトリの管理下にありません。
          data フォルダ自身、もしくはその祖先フォルダのいずれかが Git（.git）または
          SVN（.svn）の作業コピーになっている必要があります。
        </Alert>
      )}

      {!loading && repo && !repo.available && (
        <Alert severity="warning">
          {repo.type} コマンドがサーバー環境の PATH に見つかりませんでした。{repo.type} クライアントをインストールしてください。
        </Alert>
      )}

      {!loading && repo && repo.available && (
        <>
          <Tabs value={tab} onChange={(e, v) => setTab(v)} sx={{ mb: 2 }}>
            <Tab value="changes" label={`変更 (${(status?.files || []).length})`} icon={<DifferenceIcon />} iconPosition="start" />
            <Tab value="branches" label="ブランチ" icon={<AltRouteIcon />} iconPosition="start" />
            <Tab value="history" label="履歴" icon={<HistoryIcon />} iconPosition="start" />
          </Tabs>

          {status?.error && <Alert severity="error" sx={{ mb: 2 }}>{status.error}</Alert>}

          {/* --- 変更タブ --- */}
          {tab === 'changes' && (
            <Paper sx={{ p: 2 }}>
              {(status?.files || []).length === 0 ? (
                <Alert severity="success">未コミットの変更はありません。</Alert>
              ) : (
                <>
                  <CheckboxTree
                    nodes={treeNodes}
                    searchPlaceholder="ファイル名・フォルダ名で絞り込み..."
                    maxHeight={420}
                    emptyLabel="選択可能なファイルがありません"
                  />
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    選択中: {selectedPaths.size}件
                  </Typography>
                  <TextField
                    label="コミットメッセージ" fullWidth multiline minRows={2}
                    value={commitMessage} onChange={(e) => setCommitMessage(e.target.value)}
                    sx={{ mb: 1.5 }}
                  />
                  {isGit && (
                    <FormControlLabel
                      control={<Checkbox checked={autoPush} onChange={(e) => setAutoPush(e.target.checked)} />}
                      label="コミット後に自動でPushする"
                      sx={{ display: 'block', mb: 1 }}
                    />
                  )}
                  <Button
                    variant="contained" color="success" startIcon={<CheckCircleIcon />}
                    onClick={handleCommit} disabled={!caps.canCommit || selectedPaths.size === 0}
                  >
                    選択した{selectedPaths.size}件をコミット
                  </Button>
                </>
              )}
            </Paper>
          )}

          {/* --- ブランチタブ --- */}
          {tab === 'branches' && (
            <Paper sx={{ p: 2 }}>
              <TextField
                size="small" fullWidth placeholder="ブランチ名で検索..."
                value={branchFilter} onChange={(e) => setBranchFilter(e.target.value)}
                sx={{ mb: 2, maxWidth: 360 }}
              />
              <List dense sx={{ maxHeight: 520, overflowY: 'auto' }}>
                {visibleBranches.map((b) => (
                  <ListItem
                    key={b.name}
                    secondaryAction={
                      b.current ? (
                        <Chip size="small" color="primary" label="現在のブランチ" />
                      ) : (
                        <Button size="small" onClick={() => handleSwitch(b)} disabled={!caps.canBranch}>
                          切り替え
                        </Button>
                      )
                    }
                  >
                    <ListItemText
                      primary={
                        <span style={{ fontFamily: MONO }}>
                          {b.remote ? '🌐 ' : ''}{b.name}
                        </span>
                      }
                    />
                  </ListItem>
                ))}
                {visibleBranches.length === 0 && (
                  <Typography color="text.secondary" sx={{ p: 2 }}>該当するブランチがありません。</Typography>
                )}
              </List>
            </Paper>
          )}

          {/* --- 履歴タブ（コミットグラフ） --- */}
          {tab === 'history' && (
            <Paper sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', gap: 1, mb: 2, alignItems: 'center' }}>
                <FormControl size="small" sx={{ minWidth: 220 }}>
                  <InputLabel>ブランチ（{isGit ? '全ブランチ' : 'trunk'}）</InputLabel>
                  <Select
                    label="ブランチ（全ブランチ）" value={logBranch}
                    onChange={(e) => { setLogBranch(e.target.value); fetchLog(e.target.value); }}
                  >
                    <MenuItem value="">{isGit ? 'すべて' : 'trunk'}</MenuItem>
                    {branches.map((b) => (
                      <MenuItem key={b.name} value={isGit ? b.name : b.url}>{b.name}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Button size="small" startIcon={<RefreshIcon />} onClick={() => fetchLog(logBranch)}>
                  再読み込み
                </Button>
                {logLoading && <CircularProgress size={18} />}
              </Box>
              <CommitGraph commits={commits} />
            </Paper>
          )}
        </>
      )}

      {/* --- 差分ダイアログ --- */}
      <Dialog open={diffOpen} onClose={() => setDiffOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontFamily: MONO, fontSize: 15 }}>{diffTarget}</DialogTitle>
        <DialogContent dividers>
          {diffLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress /></Box>
          ) : (
            <DiffViewer diffText={diffData?.diffText} summary={diffData?.summary} />
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => setDiffOpen(false)}>閉じる</Button></DialogActions>
      </Dialog>

      {/* --- 新規ブランチ作成 --- */}
      <Dialog open={branchDialogOpen} onClose={() => setBranchDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>新しいブランチを作成</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          <TextField label="ブランチ名" fullWidth size="small" value={newBranchName}
            onChange={(e) => setNewBranchName(e.target.value)} autoFocus />
          {isGit && (
            <Autocomplete
              freeSolo options={branches.map((b) => b.name)} value={newBranchFrom}
              onChange={(e, v) => setNewBranchFrom(v || '')}
              renderInput={(params) => <TextField {...params} label="起点（未指定なら現在のHEAD）" size="small" />}
            />
          )}
          {isGit && (
            <FormControlLabel
              control={<Checkbox checked={newBranchCheckout} onChange={(e) => setNewBranchCheckout(e.target.checked)} />}
              label="作成後にこのブランチへ切り替える"
            />
          )}
          {!isGit && (
            <Typography variant="caption" color="text.secondary">
              trunk から ^/branches/{'{ブランチ名}'} をコピーして作成します。
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBranchDialogOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={handleBranchCreateConfirm}>作成</Button>
        </DialogActions>
      </Dialog>

      {/* --- マージ --- */}
      <Dialog open={mergeDialogOpen} onClose={() => setMergeDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>マージ</DialogTitle>
        <DialogContent sx={{ mt: 1 }}>
          {isGit ? (
            <FormControl fullWidth size="small">
              <InputLabel>マージ元ブランチ</InputLabel>
              <Select label="マージ元ブランチ" value={mergeTarget} onChange={(e) => setMergeTarget(e.target.value)}>
                {branches.filter((b) => !b.current).map((b) => (
                  <MenuItem key={b.name} value={b.name}>{b.name}</MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : (
            <Autocomplete
              freeSolo options={branches.map((b) => b.url)} value={mergeTarget}
              onChange={(e, v) => setMergeTarget(v || '')}
              renderInput={(params) => <TextField {...params} label="マージ元URL" size="small" onChange={(e) => setMergeTarget(e.target.value)} />}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMergeDialogOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={handleMergeConfirm} disabled={!mergeTarget.trim()}>マージ実行</Button>
        </DialogActions>
      </Dialog>

      {/* --- Push確認 --- */}
      <Dialog open={pushDialogOpen} onClose={() => setPushDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Push の確認</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            現在のブランチ「{status?.branch}」をリモートへ反映します。
          </Typography>
          {!status?.aheadBehind && (
            <FormControlLabel
              control={<Checkbox checked={pushSetUpstream} onChange={(e) => setPushSetUpstream(e.target.checked)} />}
              label="アップストリームを設定する（origin へ初回push）"
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPushDialogOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={handlePushConfirm}>Push実行</Button>
        </DialogActions>
      </Dialog>

      <JobConsole open={jobOpen} onClose={() => setJobOpen(false)} status={jobStatus} />
    </Box>
  );
}

export default GitSvnGrid;
