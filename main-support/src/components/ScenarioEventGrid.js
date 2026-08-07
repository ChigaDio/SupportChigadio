import React, { useState, useEffect } from 'react';
import {
  Box, Typography, TextField, Button, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Paper, Chip, Tooltip, Collapse, Divider, InputAdornment,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Alert, Snackbar
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import SearchIcon from '@mui/icons-material/Search';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import BuildIcon from '@mui/icons-material/Build';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import { useNavigate } from 'react-router-dom';

// スナックバー通知
const useSnackbar = () => {
  const [snack, setSnack] = useState({ open: false, message: '', severity: 'success' });
  const show = (message, severity = 'success') => setSnack({ open: true, message, severity });
  const hide = () => setSnack(s => ({ ...s, open: false }));
  return { snack, show, hide };
};

// サブイベント行(名前・説明の編集に対応)
const SubEventRow = ({ event, sub, onDeleteSub, onEditSub, onCopySub, navigate, expanded }) => {
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState(sub.name);
  const [editDesc, setEditDesc] = useState(sub.description || '');

  const commit = () => {
    onEditSub(event.id, sub.subId, { name: editName, description: editDesc });
    setEditMode(false);
  };

  return (
    <TableRow
      sx={{
        display: expanded ? 'table-row' : 'none',
        bgcolor: 'background.paper',
        '&:hover': { bgcolor: 'grey.50' },
      }}
    >
      <TableCell sx={{ pl: 1 }} />
      <TableCell>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pl: 2 }}>
          <Box sx={{ width: 2, height: 24, bgcolor: 'primary.light', borderRadius: 1 }} />
          <Chip label={`#${sub.subId}`} size="small" sx={{ fontFamily: 'monospace', height: 20 }} />
          {editMode ? (
            <TextField
              size="small"
              value={editName}
              onChange={e => setEditName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditMode(false); }}
              autoFocus
            />
          ) : (
            <Typography
              variant="body2"
              sx={{ cursor: 'pointer', '&:hover': { textDecoration: 'underline', color: 'primary.main' } }}
              onClick={() => navigate(`/scenario-event/${event.id}/sub/${sub.subId}`)}
            >
              {sub.name}
            </Typography>
          )}
        </Box>
      </TableCell>
      <TableCell>
        {editMode ? (
          <TextField
            size="small"
            placeholder="説明"
            value={editDesc}
            onChange={e => setEditDesc(e.target.value)}
            onBlur={commit}
            onKeyDown={e => { if (e.key === 'Enter') commit(); }}
            fullWidth
          />
        ) : (
          <Typography variant="body2" color="text.secondary">{sub.description || '—'}</Typography>
        )}
      </TableCell>
      <TableCell>
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          <Button
            size="small"
            variant="outlined"
            startIcon={<AccountTreeIcon />}
            onClick={() => navigate(`/scenario-event/${event.id}/sub/${sub.subId}/transition`)}
            sx={{ fontSize: '0.7rem', py: 0.25 }}
          >
            遷移図
          </Button>
          <Button
            size="small"
            variant="outlined"
            startIcon={<MenuBookIcon />}
            onClick={() => navigate(`/scenario-event/${event.id}/sub/${sub.subId}/story`)}
            sx={{ fontSize: '0.7rem', py: 0.25 }}
          >
            物語設定
          </Button>
        </Box>
      </TableCell>
      <TableCell align="right">
        <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'flex-end' }}>
          <Tooltip title="編集">
            <IconButton size="small" onClick={() => setEditMode(m => !m)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="コピー">
            <IconButton size="small" onClick={() => onCopySub(event.id, sub.subId)}>
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="削除">
            <IconButton size="small" color="error" onClick={() => onDeleteSub(event.id, sub.subId)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </TableCell>
    </TableRow>
  );
};

// イベント行コンポーネント
const EventRow = ({ event, subEvents, onAddSub, onDeleteEvent, onDeleteSub, onEditEvent, onEditSub, onCopyEvent, onCopySub, navigate }) => {
  const [expanded, setExpanded] = useState(true);
  const [editName, setEditName] = useState(event.name);
  const [editDesc, setEditDesc] = useState(event.description || '');
  const [editMode, setEditMode] = useState(false);

  return (
    <>
      {/* 親イベント行 */}
      <TableRow
        sx={{
          bgcolor: 'primary.50',
          '& td': { borderBottom: 'none' },
          '&:hover': { bgcolor: 'primary.100' },
        }}
      >
        <TableCell sx={{ pl: 1, width: 40 }}>
          <IconButton size="small" onClick={() => setExpanded(e => !e)}>
            {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
          </IconButton>
        </TableCell>
        <TableCell>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Chip label={event.id} size="small" color="primary" variant="outlined" sx={{ fontFamily: 'monospace', fontWeight: 'bold' }} />
            {editMode ? (
              <TextField
                size="small"
                value={editName}
                onChange={e => setEditName(e.target.value)}
                onBlur={() => {
                  onEditEvent(event.id, { name: editName, description: editDesc });
                  setEditMode(false);
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    onEditEvent(event.id, { name: editName, description: editDesc });
                    setEditMode(false);
                  }
                  if (e.key === 'Escape') setEditMode(false);
                }}
                autoFocus
                sx={{ minWidth: 200 }}
              />
            ) : (
              <Typography
                variant="body2"
                fontWeight="bold"
                sx={{ cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}
                onClick={() => navigate(`/scenario-event/${event.id}`)}
              >
                {event.name}
              </Typography>
            )}
          </Box>
        </TableCell>
        <TableCell>
          {editMode ? (
            <TextField
              size="small"
              value={editDesc}
              onChange={e => setEditDesc(e.target.value)}
              onBlur={() => {
                onEditEvent(event.id, { name: editName, description: editDesc });
                setEditMode(false);
              }}
              fullWidth
            />
          ) : (
            <Typography variant="body2" color="text.secondary">{event.description || '—'}</Typography>
          )}
        </TableCell>
        <TableCell>
          <Chip label={`サブ ${subEvents.length}件`} size="small" variant="outlined" />
        </TableCell>
        <TableCell align="right">
          <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'flex-end' }}>
            <Tooltip title="編集">
              <IconButton size="small" onClick={() => setEditMode(e => !e)}>
                <EditIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="サブイベント追加">
              <IconButton size="small" color="primary" onClick={() => onAddSub(event.id)}>
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="コピー">
              <IconButton size="small" onClick={() => onCopyEvent(event.id)}>
                <ContentCopyIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="削除">
              <IconButton size="small" color="error" onClick={() => onDeleteEvent(event.id)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </TableCell>
      </TableRow>

      {/* サブイベント行 */}
      {subEvents.map((sub) => (
        <SubEventRow
          key={sub.subId}
          event={event}
          sub={sub}
          expanded={expanded}
          onDeleteSub={onDeleteSub}
          onEditSub={onEditSub}
          onCopySub={onCopySub}
          navigate={navigate}
        />
      ))}
    </>
  );
};

function ScenarioEventGrid() {
  const navigate = useNavigate();
  const [events, setEvents] = useState([]); // [{ id, name, description, subEvents: [{subId, name}] }]
  const [filterText, setFilterText] = useState('');
  const [loading, setLoading] = useState(true);
  const { snack, show: showSnack, hide: hideSnack } = useSnackbar();

  // 追加ダイアログ
  const [openDialog, setOpenDialog] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');

  // サブ追加ダイアログ
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [openSubDialog, setOpenSubDialog] = useState(false);
  const [newSubName, setNewSubName] = useState('');
  const [newSubDescription, setNewSubDescription] = useState('');

  // イベントコピーダイアログ(項目5: 親イベント。サブイベントもコピーするかチェック、デフォルトON)
  const [copyEventId, setCopyEventId] = useState(null);
  const [openCopyEventDialog, setOpenCopyEventDialog] = useState(false);
  const [copySubsChecked, setCopySubsChecked] = useState(true);

  // サブイベントコピーダイアログ(項目5: 別の親 or 同じ親へコピー)
  const [copySubTarget, setCopySubTarget] = useState(null); // { eventId, subId }
  const [openCopySubDialog, setOpenCopySubDialog] = useState(false);
  const [copySubTargetEventId, setCopySubTargetEventId] = useState('');

  // データ取得
  useEffect(() => {
    fetch('/api/scenario-event')
      .then(r => r.ok ? r.json() : [])
      .then(data => {
        if (Array.isArray(data)) setEvents(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // フィルタ
  const filteredEvents = events.filter(event => {
    if (!filterText.trim()) return true;
    const q = filterText.toLowerCase();
    return (
      event.id.toLowerCase().includes(q) ||
      event.name.toLowerCase().includes(q) ||
      (event.subEvents || []).some(s => s.name.toLowerCase().includes(q))
    );
  });

  // イベント追加（IDは自動採番）
  const handleCreateEvent = () => {
    if (!newName.trim()) { showSnack('イベント名を入力してください', 'error'); return; }
    // 自動ID生成: 既存の数値IDの最大値+1、または既存IDリストから
    const numericIds = events.map(e => parseInt(e.id, 10)).filter(n => !isNaN(n));
    const autoId = numericIds.length > 0 ? (Math.max(...numericIds) + 1).toString() : '1';

    fetch('/api/scenario-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: autoId, name: newName, description: newDescription }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(result => {
        showSnack(result.message || 'イベントを追加しました');
        setEvents(prev => [...prev, { id: autoId, name: newName, description: newDescription, subEvents: [] }]);
        setNewName('');
        setNewDescription('');
        setOpenDialog(false);
      })
      .catch(err => showSnack('イベント追加エラー: ' + err.message, 'error'));
  };

  // イベント編集
  const handleEditEvent = (id, { name, description }) => {
    fetch(`/api/scenario-event/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(() => {
        setEvents(prev => prev.map(e => e.id === id ? { ...e, name, description } : e));
        showSnack('更新しました');
      })
      .catch(() => showSnack('更新エラー', 'error'));
  };

  // イベント削除
  const handleDeleteEvent = (id) => {
    if (!window.confirm(`イベント「${id}」を削除しますか？`)) return;
    fetch(`/api/scenario-event/${id}`, { method: 'DELETE' })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(result => {
        showSnack(result.message || '削除しました');
        setEvents(prev => prev.filter(e => e.id !== id));
      })
      .catch(() => showSnack('削除エラー', 'error'));
  };

  // サブイベント追加（IDは自動採番）
  const handleCreateSubEvent = () => {
    if (!newSubName.trim()) { showSnack('サブイベント名を入力してください', 'error'); return; }
    fetch(`/api/scenario-event/${selectedEventId}/sub`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newSubName, description: newSubDescription }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(result => {
        showSnack(result.message || 'サブイベントを追加しました');
        setEvents(prev => prev.map(e =>
          e.id === selectedEventId
            ? { ...e, subEvents: [...(e.subEvents || []), { subId: result.subId, name: newSubName, description: newSubDescription }] }
            : e
        ));
        setNewSubName('');
        setNewSubDescription('');
        setOpenSubDialog(false);
      })
      .catch(() => showSnack('サブイベント追加エラー', 'error'));
  };

  // サブイベント編集(項目4: 説明文も含む)
  const handleEditSub = (eventId, subId, { name, description }) => {
    fetch(`/api/scenario-event/${eventId}/sub/${subId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(() => {
        setEvents(prev => prev.map(e =>
          e.id === eventId
            ? { ...e, subEvents: e.subEvents.map(s => s.subId === subId ? { ...s, name, description } : s) }
            : e
        ));
        showSnack('更新しました');
      })
      .catch(() => showSnack('更新エラー', 'error'));
  };

  // イベントコピー(項目5)
  const handleCopyEvent = () => {
    fetch(`/api/scenario-event/${copyEventId}/copy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ copySubs: copySubsChecked }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(result => {
        showSnack(result.message || 'コピーしました');
        setOpenCopyEventDialog(false);
        // サーバー側でID採番等を行っているため再取得して整合性を保つ
        return fetch('/api/scenario-event').then(r => r.ok ? r.json() : []);
      })
      .then(data => { if (Array.isArray(data)) setEvents(data); })
      .catch(() => showSnack('コピーエラー', 'error'));
  };

  // サブイベントコピー(項目5: 別の親/同じ親)
  const handleCopySub = () => {
    const { eventId, subId } = copySubTarget;
    fetch(`/api/scenario-event/${eventId}/sub/${subId}/copy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targetEventId: copySubTargetEventId || eventId }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(result => {
        showSnack(result.message || 'コピーしました');
        setOpenCopySubDialog(false);
        return fetch('/api/scenario-event').then(r => r.ok ? r.json() : []);
      })
      .then(data => { if (Array.isArray(data)) setEvents(data); })
      .catch(() => showSnack('コピーエラー', 'error'));
  };

  // サブイベント削除
  const handleDeleteSub = (eventId, subId) => {
    if (!window.confirm(`サブイベント #${subId} を削除しますか？`)) return;
    fetch(`/api/scenario-event/${eventId}/sub/${subId}`, { method: 'DELETE' })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(result => {
        showSnack(result.message || '削除しました');
        setEvents(prev => prev.map(e =>
          e.id === eventId
            ? { ...e, subEvents: (e.subEvents || []).filter(s => s.subId !== subId) }
            : e
        ));
      })
      .catch(() => showSnack('削除エラー', 'error'));
  };

  const handleFixAll = () => {
    if (!window.confirm('全てのイベントの Role データを修正しますか？')) return;
    fetch('/api/fix-all-events', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(result => { showSnack(result.message || '修正完了'); window.location.reload(); })
      .catch(() => showSnack('修正エラー', 'error'));
  };

  const handleGenerateAllBin = () => {
    if (!window.confirm('全てのイベントバイナリを生成しますか？')) return;
    fetch('/api/generate-all-event-bin', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(result => showSnack(result.message || '生成完了'))
      .catch(() => showSnack('生成エラー', 'error'));
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* ヘッダー */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3, gap: 2 }}>
        <MenuBookIcon sx={{ fontSize: 32, color: 'primary.main' }} />
        <Typography variant="h5" fontWeight="bold">シナリオイベント</Typography>
        <Chip label={`${events.length} イベント`} size="small" color="primary" />
      </Box>

      {/* ツールバー */}
      <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <TextField
            placeholder="IDまたは名前で検索..."
            size="small"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            sx={{ minWidth: 240 }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" color="action" />
                </InputAdornment>
              ),
            }}
          />
          <Divider orientation="vertical" flexItem />
          <Tooltip title="新しいイベントを追加（IDは自動採番）">
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              size="small"
              onClick={() => setOpenDialog(true)}
            >
              イベント追加
            </Button>
          </Tooltip>
          <Tooltip title="全Roleデータを修正">
            <Button
              variant="outlined"
              startIcon={<BuildIcon />}
              size="small"
              color="warning"
              onClick={handleFixAll}
            >
              Fix All
            </Button>
          </Tooltip>
          <Tooltip title="全バイナリを生成">
            <Button
              variant="outlined"
              startIcon={<FileDownloadIcon />}
              size="small"
              onClick={handleGenerateAllBin}
            >
              全bin生成
            </Button>
          </Tooltip>
        </Box>
      </Paper>

      {/* テーブル */}
      {loading ? (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <Typography color="text.secondary">読み込み中...</Typography>
        </Box>
      ) : filteredEvents.length === 0 ? (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <Typography color="text.secondary">
            {filterText ? '検索結果がありません' : 'イベントがありません。「イベント追加」から作成してください。'}
          </Typography>
        </Box>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: 'grey.100' }}>
                <TableCell width={40} />
                <TableCell><Typography variant="caption" fontWeight="bold">ID / 名前</Typography></TableCell>
                <TableCell><Typography variant="caption" fontWeight="bold">説明</Typography></TableCell>
                <TableCell><Typography variant="caption" fontWeight="bold">サブイベント / アクション</Typography></TableCell>
                <TableCell align="right"><Typography variant="caption" fontWeight="bold">操作</Typography></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredEvents.map((event) => (
                <EventRow
                  key={event.id}
                  event={event}
                  subEvents={event.subEvents || []}
                  onAddSub={(id) => { setSelectedEventId(id); setOpenSubDialog(true); }}
                  onDeleteEvent={handleDeleteEvent}
                  onDeleteSub={handleDeleteSub}
                  onEditEvent={handleEditEvent}
                  onEditSub={handleEditSub}
                  onCopyEvent={(id) => { setCopyEventId(id); setCopySubsChecked(true); setOpenCopyEventDialog(true); }}
                  onCopySub={(eventId, subId) => {
                    setCopySubTarget({ eventId, subId });
                    setCopySubTargetEventId(eventId);
                    setOpenCopySubDialog(true);
                  }}
                  navigate={navigate}
                />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* イベント追加ダイアログ */}
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AddIcon color="primary" />
            新しいイベントを作成
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            IDは自動で採番されます（現在: {(() => {
              const ids = events.map(e => parseInt(e.id, 10)).filter(n => !isNaN(n));
              return ids.length > 0 ? Math.max(...ids) + 1 : 1;
            })()}）
          </Alert>
          <TextField
            autoFocus
            margin="dense"
            label="イベント名 *"
            fullWidth
            variant="outlined"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreateEvent(); }}
            size="small"
          />
          <TextField
            margin="dense"
            label="説明"
            fullWidth
            variant="outlined"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            size="small"
            sx={{ mt: 1.5 }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpenDialog(false)} color="inherit">キャンセル</Button>
          <Button onClick={handleCreateEvent} variant="contained" disabled={!newName.trim()}>
            作成
          </Button>
        </DialogActions>
      </Dialog>

      {/* サブイベント追加ダイアログ */}
      <Dialog open={openSubDialog} onClose={() => setOpenSubDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AddIcon color="secondary" />
            サブイベントを追加
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            サブイベントIDは自動で採番されます。
          </Alert>
          <TextField
            autoFocus
            margin="dense"
            label="サブイベント名 *"
            fullWidth
            variant="outlined"
            value={newSubName}
            onChange={(e) => setNewSubName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreateSubEvent(); }}
            size="small"
          />
          <TextField
            margin="dense"
            label="説明"
            fullWidth
            variant="outlined"
            value={newSubDescription}
            onChange={(e) => setNewSubDescription(e.target.value)}
            size="small"
            sx={{ mt: 1.5 }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpenSubDialog(false)} color="inherit">キャンセル</Button>
          <Button onClick={handleCreateSubEvent} variant="contained" color="secondary" disabled={!newSubName.trim()}>
            追加
          </Button>
        </DialogActions>
      </Dialog>

      {/* イベントコピーダイアログ(項目5) */}
      <Dialog open={openCopyEventDialog} onClose={() => setOpenCopyEventDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ContentCopyIcon color="primary" />
            イベントをコピー
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            新しいIDで複製します。名前には「のコピー」が付きます。
          </Alert>
          <FormControlLabel
            control={
              <Checkbox
                checked={copySubsChecked}
                onChange={(e) => setCopySubsChecked(e.target.checked)}
              />
            }
            label="サブイベントもコピーする"
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpenCopyEventDialog(false)} color="inherit">キャンセル</Button>
          <Button onClick={handleCopyEvent} variant="contained">コピー</Button>
        </DialogActions>
      </Dialog>

      {/* サブイベントコピーダイアログ(項目5: 別の親/同じ親) */}
      <Dialog open={openCopySubDialog} onClose={() => setOpenCopySubDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ContentCopyIcon color="secondary" />
            サブイベントをコピー
          </Box>
        </DialogTitle>
        <DialogContent>
          <TextField
            select
            margin="dense"
            label="コピー先の親イベント"
            fullWidth
            size="small"
            value={copySubTargetEventId}
            onChange={(e) => setCopySubTargetEventId(e.target.value)}
            helperText="元と同じ親イベントを選ぶと、その親の中に複製されます"
          >
            {events.map(e => (
              <MenuItem key={e.id} value={e.id}>
                {e.name}{copySubTarget && e.id === copySubTarget.eventId ? '（元の親）' : ''}
              </MenuItem>
            ))}
          </TextField>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setOpenCopySubDialog(false)} color="inherit">キャンセル</Button>
          <Button onClick={handleCopySub} variant="contained" color="secondary">コピー</Button>
        </DialogActions>
      </Dialog>

      {/* スナックバー通知 */}
      <Snackbar open={snack.open} autoHideDuration={3000} onClose={hideSnack} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}>
        <Alert onClose={hideSnack} severity={snack.severity} variant="filled" sx={{ minWidth: 240 }}>
          {snack.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}

export default ScenarioEventGrid;