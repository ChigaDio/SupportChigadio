import React, { useEffect, useMemo, useState } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Box, Typography, Paper, Button, Chip, TextField, Select, MenuItem,
  FormControl, InputLabel, Grid, CircularProgress, Alert,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';

const SEVERITY_LABEL = {
  error: { label: 'エラー', color: 'error' },
  warning: { label: '警告', color: 'warning' },
};

const TYPE_LABEL = {
  naming: '命名規則違反',
  duplicate_id: 'ID重複',
  duplicate_name: '名前重複',
  missing_field: '必須フィールド未入力',
  orphan_reference: '孤立参照（実在しない型を参照）',
};

// pythonSrc/lint_check.py の /api/lint-check を叩き、プロジェクト全体の
// データ整合性（命名規則違反・ID重複・必須フィールド未入力・孤立参照）を
// 一括スキャンして一覧表示するページ。C#生成前にここで気づけるようにする。
function LintCheckGrid() {
  const [issues, setIssues] = useState([]);
  const [counts, setCounts] = useState({ error: 0, warning: 0 });
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [hasRun, setHasRun] = useState(false);

  const [severityFilter, setSeverityFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [keyword, setKeyword] = useState('');

  const runScan = () => {
    setLoading(true);
    setErrorMsg('');
    fetch('/api/lint-check')
      .then((r) => r.json())
      .then((data) => {
        setIssues(data.issues || []);
        setCounts(data.counts || { error: 0, warning: 0 });
        setHasRun(true);
      })
      .catch((e) => setErrorMsg('スキャンエラー: ' + e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { runScan(); }, []);

  const categoryOptions = useMemo(
    () => Array.from(new Set(issues.map((i) => i.category).filter(Boolean))).sort(),
    [issues]
  );
  const typeOptions = useMemo(
    () => Array.from(new Set(issues.map((i) => i.type).filter(Boolean))).sort(),
    [issues]
  );

  const rows = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return issues
      .filter((i) => !severityFilter || i.severity === severityFilter)
      .filter((i) => !categoryFilter || i.category === categoryFilter)
      .filter((i) => !typeFilter || i.type === typeFilter)
      .filter((i) => !kw || `${i.category} ${i.name} ${i.message}`.toLowerCase().includes(kw))
      .map((i, idx) => ({ id: idx, ...i }));
  }, [issues, severityFilter, categoryFilter, typeFilter, keyword]);

  // MUI X DataGrid v8 では valueGetter のシグネチャが (value, row) に
  // 変更されている（v5以前の (params) => params.row... は動かない）。
  // ここでは type 列は row.type がそのまま value として渡ってくるだけなので、
  // row を経由せず value を直接使えばよい。
  const columns = [
    {
      field: 'severity',
      headerName: '深刻度',
      width: 110,
      renderCell: (params) => {
        const s = SEVERITY_LABEL[params.value] || { label: params.value, color: 'default' };
        return <Chip size="small" label={s.label} color={s.color} />;
      },
    },
    {
      field: 'type',
      headerName: '種別',
      width: 220,
      valueGetter: (value) => TYPE_LABEL[value] || value,
    },
    { field: 'category', headerName: 'カテゴリ', width: 180 },
    { field: 'name', headerName: '対象', width: 220 },
    { field: 'message', headerName: '内容', flex: 1, minWidth: 400 },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Typography variant="h4">データ整合性チェック</Typography>
        <Button
          variant="contained"
          startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <RefreshIcon />}
          onClick={runScan}
          disabled={loading}
        >
          {loading ? 'スキャン中...' : '再スキャン'}
        </Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Enum/ClassData/ClassDataID/CustomClassData/CustomClassDataID/State/Behavior/ScenarioRole
        などのデータ全体を横断スキャンし、命名規則違反・ID重複・必須フィールド未入力・
        孤立参照（実在しない型への参照）を、C#生成前に一括で確認できます。
      </Typography>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      <Paper sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item>
            <Chip label={`エラー: ${counts.error || 0}`} color="error" variant={counts.error ? 'filled' : 'outlined'} />
          </Grid>
          <Grid item>
            <Chip label={`警告: ${counts.warning || 0}`} color="warning" variant={counts.warning ? 'filled' : 'outlined'} />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl size="small" fullWidth>
              <InputLabel>深刻度</InputLabel>
              <Select label="深刻度" value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
                <MenuItem value="">すべて</MenuItem>
                <MenuItem value="error">エラー</MenuItem>
                <MenuItem value="warning">警告</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl size="small" fullWidth>
              <InputLabel>カテゴリ</InputLabel>
              <Select label="カテゴリ" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                <MenuItem value="">すべて</MenuItem>
                {categoryOptions.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <FormControl size="small" fullWidth>
              <InputLabel>種別</InputLabel>
              <Select label="種別" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <MenuItem value="">すべて</MenuItem>
                {typeOptions.map((t) => <MenuItem key={t} value={t}>{TYPE_LABEL[t] || t}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              size="small" fullWidth label="キーワード検索"
              value={keyword} onChange={(e) => setKeyword(e.target.value)}
              placeholder="カテゴリ・対象名・内容で検索"
            />
          </Grid>
        </Grid>
      </Paper>

      <Paper sx={{ p: 2 }}>
        {hasRun && issues.length === 0 ? (
          <Alert severity="success">問題は見つかりませんでした。</Alert>
        ) : (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {rows.length}件表示中（全{issues.length}件）
            </Typography>
            <div style={{ height: 640, width: '100%' }}>
              <DataGrid
                rows={rows}
                columns={columns}
                loading={loading}
                pageSizeOptions={[25, 50, 100]}
                initialState={{ pagination: { paginationModel: { pageSize: 50 } } }}
                disableRowSelectionOnClick
                getRowHeight={() => 'auto'}
              />
            </div>
          </>
        )}
      </Paper>
    </Box>
  );
}

export default LintCheckGrid;