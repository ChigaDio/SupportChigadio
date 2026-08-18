import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Paper, Button, Checkbox, FormControlLabel, FormGroup,
  Alert, Backdrop, LinearProgress, List, ListItem, ListItemIcon, ListItemText,
  Divider, Chip,
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import DoneAllIcon from '@mui/icons-material/DoneAll';

// カテゴリごとにバラバラだった「C#生成」「バイナリ生成」「TableID生成」等の
// ボタンを1画面に集約し、選択したカテゴリをまとめて再生成する。
// 進捗表示はCsprojSyncGrid.js（csproj_sync.py）で確立したBackdrop+
// LinearProgressのパターンをそのまま流用している。
// 実行順序・対象はバックエンド(pythonSrc/generate_all.py)のSTEPS定義に従う。
function GenerateAllGrid() {
  const [steps, setSteps] = useState([]); // [{id, label}]
  const [selected, setSelected] = useState({}); // {stepId: bool}
  const [errorMsg, setErrorMsg] = useState('');

  const [running, setRunning] = useState(false);
  const [jobProgress, setJobProgress] = useState(null); // {total, done, status, message, results, errorCount}

  useEffect(() => {
    fetch('/api/generate-all/steps')
      .then((r) => r.json())
      .then((data) => {
        setSteps(data);
        const initial = {};
        data.forEach((s) => { initial[s.id] = true; });
        setSelected(initial);
      })
      .catch((e) => setErrorMsg('ステップ一覧の取得に失敗しました: ' + e.message));
  }, []);

  const toggleStep = (id) => {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const setAll = (value) => {
    const next = {};
    steps.forEach((s) => { next[s.id] = value; });
    setSelected(next);
  };

  const selectedIds = steps.filter((s) => selected[s.id]).map((s) => s.id);

  const pollProgress = (jobId) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/generate-all/progress/${jobId}`);
        const data = await res.json();
        if (!res.ok) {
          clearInterval(interval);
          setRunning(false);
          alert('進捗取得エラー: ' + (data.error || '不明なエラー'));
          return;
        }
        setJobProgress(data);
        if (data.status === 'done') {
          clearInterval(interval);
          setRunning(false);
        }
      } catch (e) {
        clearInterval(interval);
        setRunning(false);
        alert('進捗取得エラー: ' + e.message);
      }
    }, 400);
  };

  const handleRun = async () => {
    if (selectedIds.length === 0) {
      alert('生成対象を1つ以上選択してください');
      return;
    }
    setErrorMsg('');
    setRunning(true);
    setJobProgress({ total: 0, done: 0, status: 'running', message: '準備中...', results: [], errorCount: 0 });
    try {
      const res = await fetch('/api/generate-all/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stepIds: selectedIds }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      pollProgress(data.jobId);
    } catch (e) {
      setRunning(false);
      setErrorMsg('開始エラー: ' + e.message);
    }
  };

  const progressPercent = jobProgress && jobProgress.total > 0
    ? Math.round((jobProgress.done / jobProgress.total) * 100)
    : 0;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>一括生成ダッシュボード</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Enum/ClassData/ClassDataID/CustomClassData/ClassDataMatrixID/State/Behavior/
        ScenarioRole/SaveData/各種Assetsの「C#生成」「バイナリ生成」「TableID生成」を
        まとめて実行できます。実行対象を選んで「実行」を押してください。
      </Typography>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      <Paper sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
          <Button size="small" onClick={() => setAll(true)}>すべて選択</Button>
          <Button size="small" onClick={() => setAll(false)}>すべて解除</Button>
          <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto', alignSelf: 'center' }}>
            {selectedIds.length} / {steps.length} 件選択中
          </Typography>
        </Box>
        <FormGroup>
          {steps.map((s) => (
            <FormControlLabel
              key={s.id}
              control={<Checkbox checked={!!selected[s.id]} onChange={() => toggleStep(s.id)} />}
              label={s.label}
            />
          ))}
        </FormGroup>
        <Button
          variant="contained"
          color="primary"
          startIcon={<PlayArrowIcon />}
          onClick={handleRun}
          disabled={running || selectedIds.length === 0}
          sx={{ mt: 2 }}
        >
          {running ? '実行中...' : `選択した${selectedIds.length}件を実行`}
        </Button>
      </Paper>

      {jobProgress && jobProgress.status === 'done' && (
        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <DoneAllIcon color={jobProgress.errorCount > 0 ? 'warning' : 'success'} />
            <Typography variant="h6">{jobProgress.message}</Typography>
          </Box>
          <Divider sx={{ mb: 1 }} />
          <List dense sx={{ maxHeight: 480, overflowY: 'auto' }}>
            {(jobProgress.results || []).map((r, idx) => (
              <ListItem key={idx}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {r.ok ? <CheckCircleIcon color="success" fontSize="small" /> : <ErrorIcon color="error" fontSize="small" />}
                </ListItemIcon>
                <ListItemText
                  primary={r.label}
                  secondary={r.message}
                  secondaryTypographyProps={{ color: r.ok ? 'text.secondary' : 'error' }}
                />
                {!r.ok && <Chip size="small" color="error" label="失敗" />}
              </ListItem>
            ))}
          </List>
        </Paper>
      )}

      {/* 実行中は画面全体をブロックし、進捗を表示する（CsprojSyncGridと同じパターン） */}
      <Backdrop
        open={running}
        sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.drawer + 10, flexDirection: 'column', gap: 2, p: 4 }}
      >
        <Typography variant="h6">一括生成を実行しています...</Typography>
        <Box sx={{ width: '100%', maxWidth: 480 }}>
          <LinearProgress
            variant={jobProgress?.total ? 'determinate' : 'indeterminate'}
            value={progressPercent}
            sx={{ height: 10, borderRadius: 5 }}
          />
        </Box>
        <Typography variant="body2">
          {jobProgress?.total ? `${jobProgress.done} / ${jobProgress.total} （${progressPercent}%）` : ''}
        </Typography>
        <Typography variant="caption" sx={{ opacity: 0.8, maxWidth: 480, textAlign: 'center' }}>
          {jobProgress?.message}
        </Typography>
      </Backdrop>
    </Box>
  );
}

export default GenerateAllGrid;
