import React, { useState, useEffect, useCallback } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Box, Typography, Paper, TextField, Select, MenuItem, FormControl, InputLabel,
  Button, Chip, Grid, Dialog, DialogTitle, DialogContent, DialogActions,
  List, ListItemButton, ListItemText, CircularProgress,
} from '@mui/material';
import DifferenceIcon from '@mui/icons-material/Difference';
import { useNavigate } from 'react-router-dom';
import DiffViewer from './DiffViewer';

// 直近7日分だけでなく、アーカイブ済みの過去ログも含めた「全体ログ」を
// フィルタ（ユーザー・操作種別・カテゴリ・日付範囲）とキーワード検索付きで
// 閲覧するページ。/api/workspace/logs/all を利用する。
function ActivityLogGrid() {
  const navigate = useNavigate();

  const [filterOptions, setFilterOptions] = useState({ users: [], categories: [], methods: [] });

  const [user, setUser] = useState('');
  const [method, setMethod] = useState('');
  const [category, setCategory] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [keyword, setKeyword] = useState('');

  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 50 });

  // --- 変更内容(diff)ダイアログ ---
  const [diffDialogOpen, setDiffDialogOpen] = useState(false);
  const [diffTargets, setDiffTargets] = useState([]); // [{path, snapshot}]
  const [diffSelected, setDiffSelected] = useState(null); // {path, snapshot}
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffData, setDiffData] = useState(null); // {diffText, summary}

  const openDiffDialog = (changedFiles) => {
    setDiffTargets(changedFiles);
    setDiffSelected(changedFiles[0]);
    setDiffDialogOpen(true);
    setDiffData(null);
  };

  const fetchDiff = useCallback((target) => {
    if (!target) return;
    setDiffLoading(true);
    setDiffData(null);
    const params = new URLSearchParams({ path: target.path, snapshot: target.snapshot });
    fetch(`/api/history-diff?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => setDiffData(data))
      .catch((e) => setDiffData({ diffText: null, summary: 'エラー: ' + e.message }))
      .finally(() => setDiffLoading(false));
  }, []);

  useEffect(() => {
    if (diffDialogOpen && diffSelected) {
      fetchDiff(diffSelected);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diffDialogOpen, diffSelected]);

  useEffect(() => {
    fetch('/api/workspace/logs/filters')
      .then((r) => r.json())
      .then(setFilterOptions)
      .catch(() => {});
  }, []);

  const fetchLogs = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (user) params.set('user', user);
    if (method) params.set('method', method);
    if (category) params.set('category', category);
    if (dateFrom) params.set('dateFrom', dateFrom);
    if (dateTo) params.set('dateTo', dateTo);
    if (keyword) params.set('keyword', keyword);
    params.set('offset', String(paginationModel.page * paginationModel.pageSize));
    params.set('limit', String(paginationModel.pageSize));

    fetch(`/api/workspace/logs/all?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => {
        setRows((data.entries || []).map((e, i) => ({ id: `${e.time}-${i}`, ...e })));
        setTotal(data.total || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user, method, category, dateFrom, dateTo, keyword, paginationModel]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  // フィルタ条件を変えたら1ページ目に戻す
  const handleFilterChange = (setter) => (value) => {
    setter(value);
    setPaginationModel((prev) => ({ ...prev, page: 0 }));
  };

  const handleReset = () => {
    setUser('');
    setMethod('');
    setCategory('');
    setDateFrom('');
    setDateTo('');
    setKeyword('');
    setPaginationModel({ page: 0, pageSize: 50 });
  };

  const columns = [
    { field: 'time', headerName: '日時', width: 180 },
    { field: 'user', headerName: 'アカウント名', width: 140 },
    { field: 'role', headerName: '権限', width: 100 },
    { field: 'method', headerName: '操作', width: 100 },
    { field: 'category', headerName: 'カテゴリ', width: 160 },
    { field: 'item', headerName: '対象', flex: 1, minWidth: 200 },
    { field: 'path', headerName: 'パス', flex: 1.2, minWidth: 240 },
    {
      field: 'status',
      headerName: '結果',
      width: 100,
      renderCell: (params) => (
        <Chip size="small" color={params.value < 400 ? 'success' : 'error'} label={params.value} />
      ),
    },
    {
      field: 'diff',
      headerName: '変更内容',
      width: 130,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const changedFiles = params.row.changed_files;
        if (!changedFiles || changedFiles.length === 0) return null;
        return (
          <Button
            size="small"
            startIcon={<DifferenceIcon />}
            onClick={() => openDiffDialog(changedFiles)}
          >
            確認({changedFiles.length})
          </Button>
        );
      },
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
        <Typography variant="h4">全体ログ</Typography>
        <Button size="small" onClick={() => navigate('/workspace')}>ワークスペースへ戻る</Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        直近7日間だけでなく、アーカイブされた過去分も含めた全期間のログを検索できます。
      </Typography>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl size="small" fullWidth>
              <InputLabel>ユーザー</InputLabel>
              <Select label="ユーザー" value={user} onChange={(e) => handleFilterChange(setUser)(e.target.value)}>
                <MenuItem value="">すべて</MenuItem>
                {filterOptions.users.map((u) => <MenuItem key={u} value={u}>{u}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl size="small" fullWidth>
              <InputLabel>操作種別</InputLabel>
              <Select label="操作種別" value={method} onChange={(e) => handleFilterChange(setMethod)(e.target.value)}>
                <MenuItem value="">すべて</MenuItem>
                {filterOptions.methods.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl size="small" fullWidth>
              <InputLabel>カテゴリ</InputLabel>
              <Select label="カテゴリ" value={category} onChange={(e) => handleFilterChange(setCategory)(e.target.value)}>
                <MenuItem value="">すべて</MenuItem>
                {filterOptions.categories.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <TextField
              size="small" fullWidth label="開始日" type="date" InputLabelProps={{ shrink: true }}
              value={dateFrom} onChange={(e) => handleFilterChange(setDateFrom)(e.target.value)}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <TextField
              size="small" fullWidth label="終了日" type="date" InputLabelProps={{ shrink: true }}
              value={dateTo} onChange={(e) => handleFilterChange(setDateTo)(e.target.value)}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Button fullWidth variant="outlined" onClick={handleReset}>条件をクリア</Button>
          </Grid>
          <Grid item xs={12}>
            <TextField
              size="small" fullWidth label="キーワード検索（パス・対象・ユーザー・カテゴリ）"
              value={keyword} onChange={(e) => handleFilterChange(setKeyword)(e.target.value)}
              placeholder="例: HeroRole, class-data, Foo.cs など"
            />
          </Grid>
        </Grid>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {total}件ヒット
        </Typography>
        <div style={{ height: 640, width: '100%' }}>
          <DataGrid
            rows={rows}
            columns={columns}
            loading={loading}
            paginationMode="server"
            rowCount={total}
            paginationModel={paginationModel}
            onPaginationModelChange={setPaginationModel}
            pageSizeOptions={[25, 50, 100]}
            disableRowSelectionOnClick
          />
        </div>
      </Paper>

      <Dialog open={diffDialogOpen} onClose={() => setDiffDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>変更内容の確認</DialogTitle>
        <DialogContent dividers>
          {diffTargets.length > 1 && (
            <List dense sx={{ mb: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
              {diffTargets.map((t) => (
                <ListItemButton
                  key={`${t.path}-${t.snapshot}`}
                  selected={diffSelected?.snapshot === t.snapshot && diffSelected?.path === t.path}
                  onClick={() => setDiffSelected(t)}
                >
                  <ListItemText primary={t.path} />
                </ListItemButton>
              ))}
            </List>
          )}
          {diffTargets.length === 1 && (
            <Typography variant="body2" sx={{ mb: 2, fontFamily: '"Roboto Mono", monospace' }}>
              {diffTargets[0].path}
            </Typography>
          )}
          {diffLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <DiffViewer diffText={diffData?.diffText} summary={diffData?.summary} />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDiffDialogOpen(false)}>閉じる</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ActivityLogGrid;
