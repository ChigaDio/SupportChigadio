import React, { useEffect, useMemo, useState } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Box, Typography, TextField, Button, Paper, Alert, Chip, CircularProgress,
} from '@mui/material';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import SearchIcon from '@mui/icons-material/Search';
import DownloadIcon from '@mui/icons-material/Download';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const STATUS_LABEL = {
  exists: { label: '保存先に既存', color: 'warning' },
  new: { label: '新規', color: 'success' },
};

// pythonSrc/download.py（data/ をローカルへダウンロード）用の専用ページ。
// WorkspaceUploadGrid.js と同じ構成（DataGrid + クイック検索 + チェックボックス選択）
// に揃えており、バックエンドのロジック（/api/workspace/download/preview,
// /api/workspace/download）は既存のものをそのまま利用する。
//
// 基礎クラス(Base~)・Enum・ClassData等のJSON・バイナリ・分割生成を行わない
// カテゴリは常にダウンロードに含まれるため、ここで一覧・選択できるのは
// 「本実装クラス」ファイル（保存先で上書きするかどうかが曖昧なもの）のみ。
//
// 注意: @mui/x-data-grid v8 以降、rowSelectionModel は配列ではなく
// { type: 'include' | 'exclude', ids: Set<GridRowId> } というオブジェクト形式になった。
// そのため selectionModel の初期値・更新・参照はすべてこの形式に合わせている。
const EMPTY_SELECTION = { type: 'include', ids: new Set() };

function DownloadGrid() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [destDir, setDestDir] = useState('');
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null); // {destPath, concreteFiles}
  const [selectionModel, setSelectionModel] = useState(EMPTY_SELECTION);
  const [quickFilter, setQuickFilter] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const [downloading, setDownloading] = useState(false);

  // マイページで保存先のデフォルトを設定していれば、初期値として使う
  useEffect(() => {
    if (user?.download_path && !destDir) {
      setDestDir(user.download_path);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const browseFolder = async () => {
    try {
      const res = await fetch('/api/browse-folder', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setDestDir(data.path);
    } catch (e) {
      if (e.message && e.message !== 'フォルダが選択されませんでした') {
        alert('フォルダ選択エラー: ' + e.message);
      }
    }
  };

  const handleScan = async () => {
    if (!destDir.trim()) {
      alert('保存先フォルダを指定してください');
      return;
    }
    setErrorMsg('');
    setScanning(true);
    setScanResult(null);
    setSelectionModel(EMPTY_SELECTION);
    try {
      const res = await fetch('/api/workspace/download/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: destDir }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setScanResult(data);
      // 保存先にまだ存在しないものはデフォルトでチェック（含める）、
      // 既に存在するものはチェックを外す（上書きしない）
      setSelectionModel({
        type: 'include',
        ids: new Set((data.concreteFiles || []).filter((f) => f.checked).map((f) => f.path)),
      });
    } catch (e) {
      setErrorMsg('スキャンエラー: ' + e.message);
    } finally {
      setScanning(false);
    }
  };

  const rows = useMemo(() => {
    const files = scanResult?.concreteFiles || [];
    const filtered = quickFilter.trim()
      ? files.filter((f) => f.path.toLowerCase().includes(quickFilter.toLowerCase()))
      : files;
    return filtered.map((f) => ({
      id: f.path,
      relativePath: f.path,
      status: f.alreadyExists ? 'exists' : 'new',
    }));
  }, [scanResult, quickFilter]);

  const selectedPaths = useMemo(() => Array.from(selectionModel.ids), [selectionModel]);

  const handleDownload = async () => {
    if (!window.confirm(
      `保存先 ${scanResult.destPath} へダウンロードします。\n` +
      `本実装クラスは選択した${selectedPaths.length}件のみ上書き対象になります。よろしいですか？`
    )) {
      return;
    }
    setDownloading(true);
    try {
      const res = await fetch('/api/workspace/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: destDir, selectedFiles: selectedPaths }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      alert(data.message);
      handleScan();
    } catch (e) {
      alert('ダウンロードエラー: ' + e.message);
    } finally {
      setDownloading(false);
    }
  };

  const columns = [
    { field: 'relativePath', headerName: '相対パス（本実装クラス）', flex: 1, minWidth: 380 },
    {
      field: 'status',
      headerName: '状態',
      width: 160,
      renderCell: (params) => {
        const s = STATUS_LABEL[params.value] || { label: params.value, color: 'default' };
        return <Chip size="small" label={s.label} color={s.color} />;
      },
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Typography variant="h4">データダウンロード</Typography>
        <Button size="small" onClick={() => navigate('/workspace')}>ワークスペースへ戻る</Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        data フォルダの内容を保存先へコピーします。基礎クラス(Base〜)・Enum・ClassData等のJSON・
        バイナリなど、分割生成を行わないカテゴリは常に含まれます。
        本実装クラス({'{Name}'}.cs 等)は保存先にまだ無いものだけ初期状態でチェックされており、
        検索で絞り込みながらチェックボックスで含める/含めないを選べます。
      </Typography>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextField
            label="保存先フォルダ"
            value={destDir}
            onChange={(e) => setDestDir(e.target.value)}
            sx={{ flex: 1, minWidth: 320 }}
            size="small"
            placeholder="例: C:\Downloads\MyGameData"
          />
          <Button variant="outlined" startIcon={<FolderOpenIcon />} onClick={browseFolder}>
            参照
          </Button>
          <Button variant="contained" startIcon={<SearchIcon />} onClick={handleScan} disabled={scanning}>
            {scanning ? 'スキャン中...' : 'スキャン'}
          </Button>
        </Box>
        {!user?.download_path && (
          <Alert severity="info" sx={{ mt: 2 }}>
            マイページでデフォルトの保存先を設定しておくと、次回から自動で入力されます。
          </Alert>
        )}
      </Paper>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      {scanResult && (
        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1, flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="body2" color="text.secondary">
              保存先: {scanResult.destPath} ／ 本実装クラス候補: {scanResult.concreteFiles.length}件 / 選択中: {selectedPaths.length}件
            </Typography>
            <TextField
              size="small"
              placeholder="パスで絞り込み検索"
              value={quickFilter}
              onChange={(e) => setQuickFilter(e.target.value)}
              sx={{ width: 260 }}
            />
          </Box>

          {scanResult.concreteFiles.length === 0 ? (
            <Typography color="text.secondary">
              対象となる本実装クラスファイルはありません（それ以外のファイルはそのままダウンロードされます）。
            </Typography>
          ) : (
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
          )}

          <Box sx={{ mt: 2 }}>
            <Button
              variant="contained"
              color="success"
              startIcon={downloading ? <CircularProgress size={16} color="inherit" /> : <DownloadIcon />}
              onClick={handleDownload}
              disabled={downloading}
            >
              この内容でダウンロード
            </Button>
          </Box>
        </Paper>
      )}
    </Box>
  );
}

export default DownloadGrid;
