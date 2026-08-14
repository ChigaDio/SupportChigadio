import React, { useState, useMemo } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Box, Typography, TextField, Button, Paper, Alert, LinearProgress,
  Backdrop, Divider,
} from '@mui/material';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import SearchIcon from '@mui/icons-material/Search';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';

// csprojファイルに未登録の.csファイルを再帰的に探し、選択したものだけを
// <Compile Include="..."> として追記するページ。
// 親フォルダ名が"Editor"のファイルは対象外（バックエンド側で除外済み）。
function CsprojSyncGrid() {
  const [csprojPath, setCsprojPath] = useState('');
  const [searchFolder, setSearchFolder] = useState('');

  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null); // {csprojPath, searchFolder, totalScanned, alreadyRegistered, candidates}
  const [selectionModel, setSelectionModel] = useState([]);
  const [quickFilter, setQuickFilter] = useState('');

  const [errorMsg, setErrorMsg] = useState('');

  // --- 追加処理（ジョブ）の進捗管理 ---
  const [applying, setApplying] = useState(false);
  const [jobProgress, setJobProgress] = useState(null); // {total, done, status, message}

  const browseCsproj = async () => {
    try {
      const res = await fetch('/api/csproj-sync/browse-csproj', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setCsprojPath(data.path);
    } catch (e) {
      // ユーザーがダイアログをキャンセルしただけの場合はアラートを出さない
      if (e.message && e.message !== 'ファイルが選択されませんでした') {
        alert('csproj選択エラー: ' + e.message);
      }
    }
  };

  const browseFolder = async () => {
    try {
      const res = await fetch('/api/browse-folder', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setSearchFolder(data.path);
    } catch (e) {
      if (e.message && e.message !== 'フォルダが選択されませんでした') {
        alert('フォルダ選択エラー: ' + e.message);
      }
    }
  };

  const handleScan = async () => {
    if (!csprojPath.trim() || !searchFolder.trim()) {
      alert('csprojファイルと検索フォルダの両方を指定してください');
      return;
    }
    setErrorMsg('');
    setScanning(true);
    setScanResult(null);
    setSelectionModel([]);
    try {
      const res = await fetch('/api/csproj-sync/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csprojPath, searchFolder }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setScanResult(data);
      // デフォルトは全件チェック
      setSelectionModel((data.candidates || []).map((c) => c.relativePath));
    } catch (e) {
      setErrorMsg('スキャンエラー: ' + e.message);
    } finally {
      setScanning(false);
    }
  };

  const rows = useMemo(() => {
    const candidates = scanResult?.candidates || [];
    const filtered = quickFilter.trim()
      ? candidates.filter((c) => c.relativePath.toLowerCase().includes(quickFilter.toLowerCase()))
      : candidates;
    return filtered.map((c) => ({ id: c.relativePath, relativePath: c.relativePath, absolutePath: c.absolutePath }));
  }, [scanResult, quickFilter]);

  const pollProgress = (jobId) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/csproj-sync/progress/${jobId}`);
        const data = await res.json();
        if (!res.ok) {
          clearInterval(interval);
          setApplying(false);
          alert('進捗取得エラー: ' + (data.error || '不明なエラー'));
          return;
        }
        setJobProgress(data);
        if (data.status === 'done') {
          clearInterval(interval);
          setApplying(false);
          alert(data.message || '追加が完了しました');
          // 完了したファイルは候補一覧から取り除く
          setScanResult((prev) => {
            if (!prev) return prev;
            const addedSet = new Set(data.addedFiles || []);
            return { ...prev, candidates: prev.candidates.filter((c) => !addedSet.has(c.relativePath)) };
          });
          setSelectionModel([]);
        } else if (data.status === 'error') {
          clearInterval(interval);
          setApplying(false);
          alert('追加処理でエラーが発生しました: ' + data.message);
        }
      } catch (e) {
        clearInterval(interval);
        setApplying(false);
        alert('進捗取得エラー: ' + e.message);
      }
    }, 400);
  };

  const handleApply = async () => {
    if (selectionModel.length === 0) {
      alert('追加するファイルを選択してください');
      return;
    }
    if (!window.confirm(`${selectionModel.length}件のファイルを ${scanResult.csprojPath} に追加します。よろしいですか？`)) {
      return;
    }
    setApplying(true);
    setJobProgress({ total: selectionModel.length, done: 0, status: 'running', message: '開始しています...' });
    try {
      const res = await fetch('/api/csproj-sync/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csprojPath: scanResult.csprojPath, relativePaths: selectionModel }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      pollProgress(data.jobId);
    } catch (e) {
      setApplying(false);
      alert('追加開始エラー: ' + e.message);
    }
  };

  const columns = [
    { field: 'relativePath', headerName: 'csprojからの相対パス', flex: 1, minWidth: 420 },
  ];

  const progressPercent = jobProgress && jobProgress.total > 0
    ? Math.round((jobProgress.done / jobProgress.total) * 100)
    : 0;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        CSプロジェクト同期（未登録.csファイルの追加）
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        指定した.csprojに対し、検索フォルダ以下を再帰的に走査して見つかった.csファイルのうち、
        まだ &lt;Compile Include&gt; に登録されていないものを一覧化します。
        親フォルダ名が「Editor」のファイルは対象外です。
      </Typography>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2, flexWrap: 'wrap' }}>
          <TextField
            label=".csprojファイルパス"
            value={csprojPath}
            onChange={(e) => setCsprojPath(e.target.value)}
            sx={{ flex: 1, minWidth: 320 }}
            size="small"
            placeholder="例: C:\Projects\MyGame\MyGame.csproj"
          />
          <Button variant="outlined" startIcon={<FolderOpenIcon />} onClick={browseCsproj}>
            参照
          </Button>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2, flexWrap: 'wrap' }}>
          <TextField
            label="検索フォルダ"
            value={searchFolder}
            onChange={(e) => setSearchFolder(e.target.value)}
            sx={{ flex: 1, minWidth: 320 }}
            size="small"
            placeholder="例: C:\Projects\MyGame\Assets\Scripts"
          />
          <Button variant="outlined" startIcon={<FolderOpenIcon />} onClick={browseFolder}>
            参照
          </Button>
        </Box>
        <Button variant="contained" startIcon={<SearchIcon />} onClick={handleScan} disabled={scanning}>
          {scanning ? 'スキャン中...' : 'スキャン'}
        </Button>
      </Paper>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      {scanResult && (
        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1, flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="body2" color="text.secondary">
              走査した.csファイル: {scanResult.totalScanned}件 / 既に登録済み: {scanResult.alreadyRegistered}件 /
              未登録候補: {scanResult.candidates.length}件
            </Typography>
            <TextField
              size="small"
              placeholder="パスで絞り込み検索"
              value={quickFilter}
              onChange={(e) => setQuickFilter(e.target.value)}
              sx={{ width: 260 }}
            />
          </Box>
          <Divider sx={{ mb: 2 }} />

          {scanResult.candidates.length === 0 ? (
            <Typography color="text.secondary">未登録のファイルは見つかりませんでした。</Typography>
          ) : (
            <>
              <div style={{ height: 480, width: '100%' }}>
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
                  startIcon={<PlaylistAddIcon />}
                  onClick={handleApply}
                  disabled={applying || selectionModel.length === 0}
                >
                  選択した{selectionModel.length}件をcsprojに追加
                </Button>
              </Box>
            </>
          )}
        </Paper>
      )}

      {/* 追加処理中は画面全体をブロックし、進捗を表示する */}
      <Backdrop
        open={applying}
        sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.drawer + 10, flexDirection: 'column', gap: 2, p: 4 }}
      >
        <Typography variant="h6">csprojにファイルを追加しています...</Typography>
        <Box sx={{ width: '100%', maxWidth: 480 }}>
          <LinearProgress
            variant="determinate"
            value={progressPercent}
            sx={{ height: 10, borderRadius: 5 }}
          />
        </Box>
        <Typography variant="body2">
          {jobProgress ? `${jobProgress.done} / ${jobProgress.total} （${progressPercent}%）` : ''}
        </Typography>
        <Typography variant="caption" sx={{ opacity: 0.8, maxWidth: 480, textAlign: 'center' }}>
          {jobProgress?.message}
        </Typography>
      </Backdrop>
    </Box>
  );
}

export default CsprojSyncGrid;
