import React, { useEffect, useMemo, useState } from 'react';
import {
  Box, Typography, Paper, Grid, Card, CardContent, CircularProgress,
  Alert, Button, LinearProgress,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';

// pythonSrc/project_stats.py の /api/project-stats を利用したプロジェクト
// 統計ダッシュボード。クラスデータ数・シナリオイベント数・State数などを
// カード＋バーチャート（追加npm依存を避けるため、MUIのLinearProgressを
// 応用した簡易バーで表現）で可視化する。
function ProjectStatsGrid() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const fetchStats = () => {
    setLoading(true);
    setErrorMsg('');
    fetch('/api/project-stats')
      .then((r) => r.json())
      .then((data) => setStats(data))
      .catch((e) => setErrorMsg('取得エラー: ' + e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchStats(); }, []);

  const categories = stats?.categories || [];
  const maxCount = useMemo(
    () => categories.reduce((m, c) => Math.max(m, c.count), 0) || 1,
    [categories]
  );

  const topCategories = [...categories]
    .filter((c) => c.count > 0)
    .slice(0, 5);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Typography variant="h4">プロジェクト統計</Typography>
        <Button
          variant="contained"
          startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <RefreshIcon />}
          onClick={fetchStats}
          disabled={loading}
        >
          更新
        </Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        クラスデータ数・シナリオイベント数・State数など、プロジェクト全体の規模感を一目で確認できます。
      </Typography>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      {stats && (
        <>
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary">総アイテム数</Typography>
                  <Typography variant="h3">{stats.totals.totalItems}</Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary">利用中カテゴリ数</Typography>
                  <Typography variant="h3">{stats.totals.categoryCount}</Typography>
                </CardContent>
              </Card>
            </Grid>
            {topCategories.slice(0, 2).map((c) => (
              <Grid item xs={12} sm={6} md={3} key={c.id}>
                <Card>
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">{c.label}</Typography>
                    <Typography variant="h3">{c.count}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>カテゴリ別件数</Typography>
            {categories.map((c) => (
              <Box key={c.id} sx={{ mb: 1.5 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
                  <Typography variant="body2">{c.label}</Typography>
                  <Typography variant="body2" color="text.secondary">{c.count}</Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={(c.count / maxCount) * 100}
                  sx={{ height: 10, borderRadius: 5 }}
                />
              </Box>
            ))}
          </Paper>
        </>
      )}
    </Box>
  );
}

export default ProjectStatsGrid;
