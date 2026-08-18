import React, { useEffect, useMemo, useState } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Box, Typography, Paper, Button, Chip, TextField, Alert, CircularProgress,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import RestoreIcon from '@mui/icons-material/RestoreFromTrash';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import { useNavigate } from 'react-router-dom';

// pythonSrc/trash.py の /api/trash を利用したゴミ箱管理画面。
// Enum/ClassData/ClassDataID/CustomClassData/CustomClassDataID/
// ClassDataMatrixID/State/Behavior/ScenarioRole の削除は、即時削除ではなく
// 一定期間（デフォルト30日）ここに退避される。誤って削除した場合は
// このページから復元できる。
function TrashGrid() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [keyword, setKeyword] = useState('');
  const [busyId, setBusyId] = useState(null);

  const fetchTrash = () => {
    setLoading(true);
    setErrorMsg('');
    fetch('/api/trash')
      .then((r) => r.json())
      .then((data) => setItems(Array.isArray(data) ? data : []))
      .catch((e) => setErrorMsg('取得エラー: ' + e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchTrash(); }, []);

  const handleRestore = async (trashId, name) => {
    if (!window.confirm(`「${name}」を元の場所へ復元しますか？`)) return;
    setBusyId(trashId);
    try {
      const res = await fetch(`/api/trash/${trashId}/restore`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      alert(data.message);
      fetchTrash();
    } catch (e) {
      alert('復元エラー: ' + e.message);
    } finally {
      setBusyId(null);
    }
  };

  const handlePurge = async (trashId, name) => {
    if (!window.confirm(`「${name}」を完全に削除します。この操作は取り消せません。よろしいですか？`)) return;
    setBusyId(trashId);
    try {
      const res = await fetch(`/api/trash/${trashId}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      fetchTrash();
    } catch (e) {
      alert('完全削除エラー: ' + e.message);
    } finally {
      setBusyId(null);
    }
  };

  const rows = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return items
      .filter((i) => !kw || `${i.category} ${i.name}`.toLowerCase().includes(kw))
      .map((i) => ({ id: i.trash_id, ...i }));
  }, [items, keyword]);

  const columns = [
    { field: 'category', headerName: 'カテゴリ', width: 200 },
    { field: 'name', headerName: '名前', flex: 1, minWidth: 220 },
    { field: 'deleted_at', headerName: '削除日時', width: 200 },
    {
      field: 'actions',
      headerName: '操作',
      width: 220,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            size="small" variant="outlined" startIcon={<RestoreIcon />}
            disabled={busyId === params.row.trash_id}
            onClick={() => handleRestore(params.row.trash_id, params.row.name)}
          >
            復元
          </Button>
          <Button
            size="small" variant="outlined" color="error" startIcon={<DeleteForeverIcon />}
            disabled={busyId === params.row.trash_id}
            onClick={() => handlePurge(params.row.trash_id, params.row.name)}
          >
            完全削除
          </Button>
        </Box>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Typography variant="h4">ゴミ箱</Typography>
        <Button
          variant="contained"
          startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <RefreshIcon />}
          onClick={fetchTrash}
          disabled={loading}
        >
          更新
        </Button>
        <Button size="small" onClick={() => navigate('/')}>トップへ戻る</Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Enum/ClassData/ClassDataID/CustomClassData/CustomClassDataID/ClassDataMatrixID/
        State/Behavior/ScenarioRoleの削除は即時削除ではなく、ここに30日間保管されます。
        期限が過ぎたものは自動的に完全削除されます。
      </Typography>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      <Paper sx={{ p: 2, mb: 2 }}>
        <TextField
          size="small" fullWidth label="カテゴリ・名前で検索"
          value={keyword} onChange={(e) => setKeyword(e.target.value)}
        />
      </Paper>

      <Paper sx={{ p: 2 }}>
        {!loading && items.length === 0 ? (
          <Alert severity="info">ゴミ箱は空です。</Alert>
        ) : (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {rows.length}件表示中（全{items.length}件）
            </Typography>
            <div style={{ height: 560, width: '100%' }}>
              <DataGrid
                rows={rows}
                columns={columns}
                loading={loading}
                pageSizeOptions={[25, 50, 100]}
                initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
                disableRowSelectionOnClick
              />
            </div>
          </>
        )}
      </Paper>
    </Box>
  );
}

export default TrashGrid;
