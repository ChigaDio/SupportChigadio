import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Paper, Table, TableHead, TableRow, TableCell, TableBody,
  Button, Divider, TextField, Select, MenuItem, FormControl, InputLabel, Grid, Chip, Link,
  Alert
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import VersionBadge from './VersionBadge';

function Workspace() {
  const { isAdmin, user } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [versions, setVersions] = useState([]);
  const [newVersionName, setNewVersionName] = useState('');
  const [parentVersion, setParentVersion] = useState('');

  const fetchSummary = () => {
    fetch('/api/workspace').then((r) => r.json()).then(setSummary).catch(() => {});
  };
  const fetchVersions = () => {
    fetch('/api/versions').then((r) => r.json()).then(setVersions).catch(() => {});
  };

  useEffect(() => { fetchSummary(); fetchVersions(); }, []);

  const handleCreateVersion = () => {
    if (!newVersionName.trim()) { alert('バージョン名を入力してください'); return; }
    fetch('/api/versions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newVersionName, parent: parentVersion || undefined }),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error);
        setNewVersionName('');
        fetchVersions();
      })
      .catch((e) => alert('作成エラー: ' + e.message));
  };

  const handleActivate = (name) => {
    if (!window.confirm(`バージョン '${name}' をアクティブにしますか？（現在の変更内容は現バージョンとして保存されます）`)) return;
    fetch(`/api/versions/${encodeURIComponent(name)}/activate`, { method: 'POST' })
      .then((r) => r.json())
      .then((res) => { alert(res.message || res.error); fetchSummary(); fetchVersions(); });
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
        <Typography variant="h4">ワークスペース</Typography>
        <VersionBadge />
      </Box>

      <Grid container spacing={2}>
        <Grid item xs={12} md={7}>
          <Paper sx={{ p: 2, mb: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography variant="h6">直近の編集ログ（最新7日間）</Typography>
              <Button size="small" onClick={() => navigate('/activity-log')}>全体ログを見る</Button>
            </Box>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>日時</TableCell>
                  <TableCell>アカウント名</TableCell>
                  <TableCell>操作</TableCell>
                  <TableCell>カテゴリ</TableCell>
                  <TableCell>対象</TableCell>
                  <TableCell>結果</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(summary?.recentLogs || []).map((log, i) => (
                  <TableRow key={i}>
                    <TableCell>{log.time}</TableCell>
                    <TableCell>{log.user}</TableCell>
                    <TableCell>{log.method}</TableCell>
                    <TableCell>{log.category}</TableCell>
                    <TableCell>{log.item}</TableCell>
                    <TableCell>
                      <Chip size="small" color={log.status < 400 ? 'success' : 'error'} label={log.status} />
                    </TableCell>
                  </TableRow>
                ))}
                {(!summary || (summary.recentLogs || []).length === 0) && (
                  <TableRow><TableCell colSpan={6}>まだログがありません</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="h6">お知らせ（最新）</Typography>
              <Button size="small" onClick={() => navigate('/announcements')}>すべて見る</Button>
            </Box>
            {(summary?.announcements || []).map((a) => (
              <Box key={a.id} sx={{ py: 1, borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                <Link component="button" onClick={() => navigate(`/announcements/${a.id}`)}>
                  {a.title}
                </Link>
                <Typography variant="caption" display="block" color="text.secondary">
                  {a.created_at} - {a.author}
                </Typography>
              </Box>
            ))}
          </Paper>
        </Grid>

        <Grid item xs={12} md={5}>
          <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>ダウンロード</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              data フォルダの内容を保存先へコピーします。基礎クラス(Base~)・Enum・JSON・
              バイナリは常に含まれます。本実装クラス({'{Name}'}.cs等)は専用画面で
              検索・チェックボックスで選択して含められます。
            </Typography>
            {user?.download_path ? (
              <Alert severity="info" sx={{ mb: 2 }}>
                デフォルト保存先: <b>{user.download_path}</b>（マイページで変更できます）
              </Alert>
            ) : (
              <Alert severity="warning" sx={{ mb: 2 }}>
                デフォルト保存先が未設定です。ダウンロード画面で毎回フォルダを選択します。
                （マイページで固定できます）
              </Alert>
            )}
            <Button variant="contained" onClick={() => navigate('/workspace/download')}>
              ダウンロード画面を開く
            </Button>
          </Paper>

          <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>アップロード</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              ローカルフォルダの内容をdataフォルダへ反映します。差分をgit diff風に
              確認しながら、チェックボックスで選択したファイルだけをアップロードできます。
            </Typography>
            <Button variant="contained" onClick={() => navigate('/workspace/upload')}>
              アップロード画面を開く
            </Button>
          </Paper>

          {isAdmin && (
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" sx={{ mb: 1 }}>バージョン管理（管理人のみ）</Typography>
              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                <TextField size="small" label="新バージョン名" value={newVersionName}
                  onChange={(e) => setNewVersionName(e.target.value)} />
                <FormControl size="small" sx={{ minWidth: 140 }}>
                  <InputLabel>引き継ぎ元</InputLabel>
                  <Select label="引き継ぎ元" value={parentVersion} onChange={(e) => setParentVersion(e.target.value)}>
                    <MenuItem value="">(現在のバージョン)</MenuItem>
                    {versions.map((v) => (
                      <MenuItem key={v.name} value={v.name}>{v.name}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Button variant="contained" onClick={handleCreateVersion}>作成</Button>
              </Box>
              <Divider sx={{ mb: 1 }} />
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>名前</TableCell>
                    <TableCell>引き継ぎ元</TableCell>
                    <TableCell>作成日時</TableCell>
                    <TableCell align="right">操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {versions.map((v) => (
                    <TableRow key={v.name} selected={summary?.currentVersion?.name === v.name}>
                      <TableCell>{v.name}{v.auto ? ' (自動)' : ''}</TableCell>
                      <TableCell>{v.parent || '-'}</TableCell>
                      <TableCell>{v.created_at}</TableCell>
                      <TableCell align="right">
                        {summary?.currentVersion?.name === v.name ? (
                          <Chip size="small" label="アクティブ" color="primary" />
                        ) : (
                          <Button size="small" onClick={() => handleActivate(v.name)}>アクティブにする</Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          )}
        </Grid>
      </Grid>
    </Box>
  );
}

export default Workspace;
