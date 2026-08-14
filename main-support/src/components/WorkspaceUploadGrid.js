import React, { useState, useMemo } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Box, Typography, TextField, Button, Paper, Alert, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress,
} from '@mui/material';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import SearchIcon from '@mui/icons-material/Search';
import UploadIcon from '@mui/icons-material/Upload';
import DifferenceIcon from '@mui/icons-material/Difference';
import { useNavigate } from 'react-router-dom';
import DiffViewer from './DiffViewer';

const STATUS_LABEL = {
  new: { label: '新規', color: 'success' },
  modified: { label: '変更あり', color: 'warning' },
  unchanged: { label: '変更なし', color: 'default' },
};

// pythonSrc/download.py（data/ をローカルへダウンロード）の逆方向。
// ローカルフォルダをスキャンし、data/ 内の対応ファイルとの差分を
// git diff 風に確認しながら、選択したファイルだけをアップロードするページ。
function WorkspaceUploadGrid() {
  const navigate = useNavigate();

  const [sourceDir, setSourceDir] = useState('');
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null); // {sourceDir, files}
  const [selectionModel, setSelectionModel] = useState([]);
  const [quickFilter, setQuickFilter] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const [uploading, setUploading] = useState(false);

  const [diffOpen, setDiffOpen] = useState(false);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffTarget, setDiffTarget] = useState(null); // relativePath
  const [diffData, setDiffData] = useState(null); // {isText, diffText, summary}

  const browseFolder = async () => {
    try {
      const res = await fetch('/api/browse-folder', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setSourceDir(data.path);
    } catch (e) {
      if (e.message && e.message !== 'フォルダが選択されませんでした') {
        alert('フォルダ選択エラー: ' + e.message);
      }
    }
  };

  const handleScan = async () => {
    if (!sourceDir.trim()) {
      alert('アップロード元フォルダを指定してください');
      return;
    }
    setErrorMsg('');
    setScanning(true);
    setScanResult(null);
    setSelectionModel([]);
    try {
      const res = await fetch('/api/workspace/upload/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: sourceDir }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setScanResult(data);
      // new / modified はデフォルトでチェック、unchanged は外す
      setSelectionModel(
        (data.files || []).filter((f) => f.status !== 'unchanged').map((f) => f.relativePath)
      );
    } catch (e) {
      setErrorMsg('スキャンエラー: ' + e.message);
    } finally {
      setScanning(false);
    }
  };

  const rows = useMemo(() => {
    const files = scanResult?.files || [];
    const filtered = quickFilter.trim()
      ? files.filter((f) => f.relativePath.toLowerCase().includes(quickFilter.toLowerCase()))
      : files;
    return filtered.map((f) => ({ id: f.relativePath, ...f }));
  }, [scanResult, quickFilter]);

  const handleShowDiff = async (relativePath) => {
    setDiffTarget(relativePath);
    setDiffOpen(true);
    setDiffLoading(true);
    setDiffData(null);
    try {
      const res = await fetch('/api/workspace/upload/diff', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: scanResult.sourceDir, relativePath }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setDiffData(data);
    } catch (e) {
      setDiffData({ isText: true, diffText: null, summary: 'エラー: ' + e.message });
    } finally {
      setDiffLoading(false);
    }
  };

  const handleUpload = async () => {
    if (selectionModel.length === 0) {
      alert('アップロードするファイルを選択してください');
      return;
    }
    if (!window.confirm(`${selectionModel.length}件のファイルをサーバーのdataフォルダへアップロード（上書き）します。よろしいですか？`)) {
      return;
    }
    setUploading(true);
    try {
      const res = await fetch('/api/workspace/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: scanResult.sourceDir, selectedFiles: selectionModel }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      alert(data.message);
      handleScan();
    } catch (e) {
      alert('アップロードエラー: ' + e.message);
    } finally {
      setUploading(false);
    }
  };

  const columns = [
    { field: 'relativePath', headerName: '相対パス', flex: 1, minWidth: 380 },
    {
      field: 'status',
      headerName: '状態',
      width: 120,
      renderCell: (params) => {
        const s = STATUS_LABEL[params.value] || { label: params.value, color: 'default' };
        return <Chip size="small" label={s.label} color={s.color} />;
      },
    },
    { field: 'sourceSize', headerName: 'サイズ(元)', width: 110 },
    { field: 'destSize', headerName: 'サイズ(現行)', width: 110, valueGetter: (params) => params.row.destSize ?? '-' },
    {
      field: 'diff',
      headerName: '差分',
      width: 100,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        params.row.status === 'unchanged' ? null : (
          <Button size="small" startIcon={<DifferenceIcon />} onClick={() => handleShowDiff(params.row.relativePath)}>
            確認
          </Button>
        )
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Typography variant="h4">データアップロード</Typography>
        <Button size="small" onClick={() => navigate('/workspace')}>ワークスペースへ戻る</Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        ローカルフォルダの内容を、サーバーのdataフォルダへアップロード（反映）します。
        アップロード前に、各ファイルの差分をgit diff風に確認できます。
      </Typography>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextField
            label="アップロード元フォルダ"
            value={sourceDir}
            onChange={(e) => setSourceDir(e.target.value)}
            sx={{ flex: 1, minWidth: 320 }}
            size="small"
            placeholder="例: C:\Downloads\MyGameData\data"
          />
          <Button variant="outlined" startIcon={<FolderOpenIcon />} onClick={browseFolder}>
            参照
          </Button>
          <Button variant="contained" startIcon={<SearchIcon />} onClick={handleScan} disabled={scanning}>
            {scanning ? 'スキャン中...' : 'スキャン'}
          </Button>
        </Box>
      </Paper>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      {scanResult && (
        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1, flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="body2" color="text.secondary">
              走査したファイル: {scanResult.files.length}件 / 選択中: {selectionModel.length}件
            </Typography>
            <TextField
              size="small"
              placeholder="パスで絞り込み検索"
              value={quickFilter}
              onChange={(e) => setQuickFilter(e.target.value)}
              sx={{ width: 260 }}
            />
          </Box>

          <div style={{ height: 520, width: '100%' }}>
            <DataGrid
              rows={rows}
              columns={columns}
              checkboxSelection
              disableRowSelectionOnClick
              rowSelectionModel={selectionModel}
              onRowSelectionModelChange={(model) => setSelectionModel(model)}
              pageSizeOptions={[25, 50, 100]}
              initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
            />
          </div>

          <Box sx={{ mt: 2 }}>
            <Button
              variant="contained"
              color="success"
              startIcon={uploading ? <CircularProgress size={16} color="inherit" /> : <UploadIcon />}
              onClick={handleUpload}
              disabled={uploading || selectionModel.length === 0}
            >
              選択した{selectionModel.length}件をアップロード
            </Button>
          </Box>
        </Paper>
      )}

      <Dialog open={diffOpen} onClose={() => setDiffOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontFamily: '"Roboto Mono", monospace', fontSize: 15 }}>
          {diffTarget}
        </DialogTitle>
        <DialogContent dividers>
          {diffLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <DiffViewer diffText={diffData?.diffText} summary={diffData?.summary} />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDiffOpen(false)}>閉じる</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default WorkspaceUploadGrid;
