import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Paper, Table, TableHead, TableRow, TableCell, TableBody,
  Button, Divider, TextField, Select, MenuItem, FormControl, InputLabel, Grid, Chip, Link,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import VersionBadge from './VersionBadge';
import CheckboxTree from './CheckboxTree';

function Workspace() {
  const { isAdmin, user, refresh } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [versions, setVersions] = useState([]);
  const [newVersionName, setNewVersionName] = useState('');
  const [parentVersion, setParentVersion] = useState('');

  // --- ダウンロード関連 ---
  const [downloading, setDownloading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewPath, setPreviewPath] = useState('');
  const [concreteFiles, setConcreteFiles] = useState([]); // [{path, alreadyExists, checked}]
  const [previewLoading, setPreviewLoading] = useState(false);

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

  // ダウンロード先パスを決定する（マイページで設定したデフォルトがあればそれを使用、
  // 無ければサーバー側のフォルダ選択ダイアログを開く）
  const resolveDownloadPath = async () => {
    if (user?.download_path) return user.download_path;
    const res = await fetch('/api/browse-folder', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'フォルダが選択されませんでした');
    return data.path;
  };

  const startDownload = async () => {
    setDownloading(true);
    try {
      const path = await resolveDownloadPath();
      setPreviewLoading(true);
      const res = await fetch('/api/workspace/download/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setPreviewPath(path);
      setConcreteFiles(data.concreteFiles || []);
      setPreviewOpen(true);
    } catch (e) {
      alert('ダウンロード準備エラー: ' + e.message);
    } finally {
      setDownloading(false);
      setPreviewLoading(false);
    }
  };

  const toggleFileByPath = (path, checked) => {
    setConcreteFiles((prev) => prev.map((f) => (f.path === path ? { ...f, checked } : f)));
  };

  const setAllChecked = (checked) => {
    setConcreteFiles((prev) => prev.map((f) => ({ ...f, checked })));
  };

  // concreteFiles(フラットな相対パス一覧)を、フォルダ階層のツリーノードへ変換する。
  // 例: "scenario_data/scenario_role/HeroRole/HeroRoleAction.cs" は
  //     scenario_data > scenario_role > HeroRole > HeroRoleAction.cs という親子構造になる。
  const buildFileTree = (files) => {
    const root = { children: {} };
    files.forEach((f) => {
      const parts = f.path.split('/');
      let cur = root;
      parts.forEach((part, idx) => {
        const isLeaf = idx === parts.length - 1;
        cur.children = cur.children || {};
        if (!cur.children[part]) {
          cur.children[part] = isLeaf ? { isLeaf: true, file: f } : { isLeaf: false, children: {} };
        }
        cur = cur.children[part];
      });
    });

    const collectLeafFiles = (node) => {
      if (node.isLeaf) return [node.file];
      return Object.values(node.children || {}).flatMap(collectLeafFiles);
    };

    const toNodes = (node, pathPrefix) => Object.entries(node.children || {}).map(([name, child]) => {
      const fullPath = pathPrefix ? `${pathPrefix}/${name}` : name;
      if (child.isLeaf) {
        const f = child.file;
        return {
          id: fullPath,
          label: name,
          checked: f.checked,
          onToggle: (checked) => toggleFileByPath(f.path, checked),
          badge: f.alreadyExists
            ? <Chip size="small" label="保存先に既存" color="warning" variant="outlined" sx={{ ml: 1 }} />
            : <Chip size="small" label="新規" color="success" variant="outlined" sx={{ ml: 1 }} />,
        };
      }
      const childNodes = toNodes(child, fullPath);
      const leafFiles = collectLeafFiles(child);
      const allChecked = leafFiles.every((f) => f.checked);
      const noneChecked = leafFiles.every((f) => !f.checked);
      const checked = allChecked ? true : noneChecked ? false : 'indeterminate';
      return {
        id: fullPath,
        label: name,
        checked,
        badge: <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>{leafFiles.length}件</Typography>,
        onToggle: (checkedVal) => {
          const paths = leafFiles.map((f) => f.path);
          setConcreteFiles((prev) => prev.map((f) => (paths.includes(f.path) ? { ...f, checked: checkedVal } : f)));
        },
        children: childNodes,
      };
    });

    return toNodes(root, '');
  };

  const confirmDownload = () => {
    setDownloading(true);
    const selectedFiles = concreteFiles.filter((f) => f.checked).map((f) => f.path);
    fetch('/api/workspace/download', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: previewPath, selectedFiles }),
    })
      .then((r) => r.json())
      .then((res) => { alert(res.message || res.error); setPreviewOpen(false); })
      .catch((e) => alert('ダウンロードエラー: ' + e.message))
      .finally(() => setDownloading(false));
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
              バイナリは常に含まれます。本実装クラス({'{Name}'}.cs等)は、保存先に
              まだ無いものだけ初期状態でチェックされます（次の画面で変更可能）。
            </Typography>
            {user?.download_path ? (
              <Alert severity="info" sx={{ mb: 2 }}>
                デフォルト保存先: <b>{user.download_path}</b>（マイページで変更できます）
              </Alert>
            ) : (
              <Alert severity="warning" sx={{ mb: 2 }}>
                デフォルト保存先が未設定です。ダウンロード時に毎回フォルダを選択します。
                （マイページで固定できます）
              </Alert>
            )}
            <Button variant="contained" onClick={startDownload} disabled={downloading}>
              {downloading ? '準備中...' : 'ダウンロード'}
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

      {/* ダウンロード確認ダイアログ（本実装クラスのチェックリスト） */}
      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>ダウンロード内容の確認</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            保存先: <b>{previewPath}</b>
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            基礎クラス・Enum・JSON・バイナリ等は自動的に含まれます。以下は
            「本実装クラス」ファイルです。保存先に既に存在するものは上書きしないよう
            初期状態でチェックが外れています。含めたい場合はチェックしてください。
          </Typography>
          {concreteFiles.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              対象となる本実装クラスファイルはありません。
            </Typography>
          ) : (
            <>
              <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
                <Button size="small" onClick={() => setAllChecked(true)}>すべて含める</Button>
                <Button size="small" onClick={() => setAllChecked(false)}>すべて除外</Button>
                <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto', alignSelf: 'center' }}>
                  {concreteFiles.filter((f) => f.checked).length} / {concreteFiles.length} 件を含める
                </Typography>
              </Box>
              <CheckboxTree
                nodes={buildFileTree(concreteFiles)}
                searchPlaceholder="ファイル名・パスで検索..."
              />
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={confirmDownload} disabled={downloading}>
            {downloading ? 'ダウンロード中...' : 'この内容でダウンロード'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default Workspace;
