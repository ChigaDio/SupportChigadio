import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Paper, TextField, Button, Divider, Grid, Select, MenuItem,
  FormControl, InputLabel, Table, TableHead, TableRow,
  TableCell, TableBody, IconButton, Alert, Chip, CircularProgress
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { useAuth } from '../context/AuthContext';
import VersionBadge from './VersionBadge';
import CheckboxTree from './CheckboxTree';

const ROLE_LABEL = { admin: '管理人', editor: '編集者', viewer: '閲覧者' };

// 各カテゴリの「個別に許可するデータ」を、実際のJSON/APIから取得するための設定。
// スペルミスを防ぐため、手入力ではなく実データから選ばせる。
const CATEGORY_ITEM_SOURCES = {
  enum: { endpoint: '/api/enum-id', extract: (d) => d.map((x) => x.name) },
  const_class_data: { endpoint: '/api/const-class-data', extract: (d) => d.map((x) => x.name) },
  class_data: { endpoint: '/api/class-data', extract: (d) => d.map((x) => x.name) },
  class_data_id: { endpoint: '/api/class-data-id', extract: (d) => d.map((x) => x.name) },
  class_data_matrix_id: { endpoint: '/api/class-data-matrix-id', extract: (d) => d.map((x) => x.name) },
  custom_class_data: { endpoint: '/api/custom-class-data', extract: (d) => d.map((x) => x.name) },
  custom_class_data_id: { endpoint: '/api/custom-class-data-id', extract: (d) => d.map((x) => x.name) },
  state: { endpoint: '/api/state-data', extract: (d) => d.map((x) => x.name) },
  behavior: { endpoint: '/api/behavior-data', extract: (d) => d.map((x) => x.name) },
  scenario_role: { endpoint: '/api/scenario-role', extract: (d) => d.map((x) => x.name) },
  assets_sound: { endpoint: '/api/sound', extract: (d) => Object.keys(d.groups || {}) },
  assets_texture: { endpoint: '/api/texture', extract: (d) => Object.keys(d.groups || {}) },
  assets_gameobject: { endpoint: '/api/gameobject', extract: (d) => Object.keys(d.groups || {}) },
  assets_material: { endpoint: '/api/material', extract: (d) => Object.keys(d.groups || {}) },
  assets_scene: { endpoint: '/api/scene/get', extract: (d) => (d.scenes || []).map((s) => s.enum) },
  animator: { endpoint: '/api/animator-data', extract: (d) => d.map((x) => x.name) },
  save_data: { staticItems: ['SystemData', 'PlayerData'] },
};

function useCategoryItems(categories) {
  const [itemsByCategory, setItemsByCategory] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all(
      categories.map(async (cat) => {
        const src = CATEGORY_ITEM_SOURCES[cat];
        if (!src) return [cat, null]; // このカテゴリは個別データ選択に非対応
        if (src.staticItems) return [cat, src.staticItems];
        try {
          const res = await fetch(src.endpoint);
          if (!res.ok) return [cat, []];
          const data = await res.json();
          return [cat, src.extract(data) || []];
        } catch (e) {
          return [cat, []];
        }
      })
    ).then((results) => {
      if (cancelled) return;
      const map = {};
      results.forEach(([cat, items]) => { map[cat] = items; });
      setItemsByCategory(map);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [categories]);

  return { itemsByCategory, loading };
}

function PermissionEditor({ categories, permissions, onChange }) {
  const perms = permissions || {};
  const { itemsByCategory, loading } = useCategoryItems(categories);

  const update = (cat, patch) => {
    onChange({ ...perms, [cat]: { ...(perms[cat] || { all: false, items: [] }), ...patch } });
  };

  const toggleItem = (cat, itemName, checked) => {
    const current = perms[cat]?.items || [];
    const next = checked ? [...new Set([...current, itemName])] : current.filter((n) => n !== itemName);
    update(cat, { items: next });
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 2 }}>
        <CircularProgress size={18} /><Typography variant="body2">データ一覧を読み込み中...</Typography>
      </Box>
    );
  }

  // カテゴリを親ノード、データ名を子ノードとするツリーを構築する。
  const nodes = categories.map((cat) => {
    const p = perms[cat] || { all: false, items: [] };
    const items = itemsByCategory[cat]; // null = 個別選択非対応, [] = データ無し
    const selectedCount = (p.items || []).length;
    const catChecked = p.all ? true : (selectedCount > 0 ? 'indeterminate' : false);

    let children;
    let badge;
    if (items === null) {
      badge = <Chip size="small" label="全体のみ" variant="outlined" sx={{ ml: 1 }} />;
      children = undefined;
    } else if (items.length === 0) {
      badge = <Chip size="small" label="データ無し" variant="outlined" sx={{ ml: 1 }} />;
      children = undefined;
    } else {
      badge = (
        <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
          {p.all ? 'すべて許可' : `${selectedCount}/${items.length}件`}
        </Typography>
      );
      children = items.map((name) => ({
        id: `${cat}/${name}`,
        label: name,
        checked: p.all || (p.items || []).includes(name),
        disabled: p.all,
        onToggle: (checked) => toggleItem(cat, name, checked),
      }));
    }

    return {
      id: cat,
      label: cat,
      checked: catChecked,
      badge,
      onToggle: (checked) => update(cat, { all: checked }),
      children,
    };
  });

  return (
    <CheckboxTree
      nodes={nodes}
      searchPlaceholder="カテゴリ・データ名で検索..."
      maxHeight={480}
    />
  );
}

function MyPage() {
  const { user, refresh, isAdmin } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const [downloadPath, setDownloadPath] = useState('');
  const [savingPath, setSavingPath] = useState(false);
  const [browsing, setBrowsing] = useState(false);

  useEffect(() => {
    setDownloadPath(user?.download_path || '');
  }, [user]);

  const handleBrowse = () => {
    setBrowsing(true);
    fetch('/api/browse-folder', { method: 'POST' })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error);
        setDownloadPath(data.path);
      })
      .catch((e) => alert('フォルダ選択エラー: ' + e.message))
      .finally(() => setBrowsing(false));
  };

  const handleSaveDownloadPath = () => {
    setSavingPath(true);
    fetch('/api/me/download-path', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: downloadPath || null }),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error);
        refresh();
      })
      .catch((e) => alert('保存エラー: ' + e.message))
      .finally(() => setSavingPath(false));
  };

  const [categories, setCategories] = useState([]);
  const [users, setUsers] = useState([]);
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'viewer', permissions: {} });
  const [editingUser, setEditingUser] = useState(null); // user being permission-edited

  useEffect(() => {
    fetch('/api/categories').then((r) => r.json()).then(setCategories).catch(() => {});
  }, []);

  const fetchUsers = () => {
    if (!isAdmin) return;
    fetch('/api/users').then((r) => r.json()).then(setUsers).catch(() => {});
  };

  useEffect(() => { fetchUsers(); }, [isAdmin]);

  const handleSaveSelf = () => {
    setMessage(''); setError('');
    const body = {};
    if (username) body.username = username;
    if (password) body.password = password;
    fetch('/api/me', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error);
        setMessage('更新しました');
        setUsername(''); setPassword('');
        refresh();
      })
      .catch((e) => setError(e.message));
  };

  const handleCreateUser = () => {
    fetch('/api/users', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(newUser),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error);
        setNewUser({ username: '', password: '', role: 'viewer', permissions: {} });
        fetchUsers();
      })
      .catch((e) => alert('作成エラー: ' + e.message));
  };

  const handleUpdateUserRole = (u, role) => {
    fetch(`/api/users/${u.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role }),
    }).then(() => fetchUsers());
  };

  const handleSavePermissions = () => {
    if (!editingUser) return;
    fetch(`/api/users/${editingUser.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ permissions: editingUser.permissions }),
    }).then(() => { setEditingUser(null); fetchUsers(); });
  };

  const handleDeleteUser = (u) => {
    if (!window.confirm(`ユーザー ${u.username} を削除しますか？`)) return;
    fetch(`/api/users/${u.id}`, { method: 'DELETE' }).then(() => fetchUsers());
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>マイページ</Typography>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
          <Typography variant="h6">現在のログイン情報</Typography>
          <VersionBadge />
        </Box>
        {user && (
          <Typography sx={{ mb: 1 }}>
            ID: <b>{user.username}</b> ／ 役職: <Chip size="small" label={ROLE_LABEL[user.role] || user.role} />
          </Typography>
        )}
        {message && <Alert severity="success" sx={{ mb: 1 }}>{message}</Alert>}
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        <Grid container spacing={2}>
          <Grid item xs={12} sm={5}>
            <TextField label="新しいID" fullWidth value={username} onChange={(e) => setUsername(e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={5}>
            <TextField label="新しいパスワード" type="password" fullWidth value={password} onChange={(e) => setPassword(e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={2}>
            <Button variant="contained" fullWidth sx={{ height: '100%' }} onClick={handleSaveSelf}>更新</Button>
          </Grid>
        </Grid>
      </Paper>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>ダウンロードオプション（ローカル保存先）</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          ワークスペースの「ダウンロード」実行時に使うデフォルトの保存先フォルダです。
          設定しておくと、毎回フォルダを選ばずにダウンロードできます。
        </Typography>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={7}>
            <TextField
              label="デフォルト保存先パス"
              fullWidth
              value={downloadPath}
              onChange={(e) => setDownloadPath(e.target.value)}
              placeholder="例: C:\\Users\\me\\Downloads"
            />
          </Grid>
          <Grid item xs={6} sm={2.5}>
            <Button variant="outlined" fullWidth onClick={handleBrowse} disabled={browsing}>
              {browsing ? '選択中...' : 'フォルダを選択'}
            </Button>
          </Grid>
          <Grid item xs={6} sm={2.5}>
            <Button variant="contained" fullWidth onClick={handleSaveDownloadPath} disabled={savingPath}>
              保存
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {isAdmin && (
        <>
          <Divider sx={{ my: 3 }} />
          <Typography variant="h5" gutterBottom>ユーザー管理（管理人のみ）</Typography>

          <Paper sx={{ p: 2, mb: 3 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>新規ユーザー追加</Typography>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={3}>
                <TextField label="ID" fullWidth value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} />
              </Grid>
              <Grid item xs={12} sm={3}>
                <TextField label="パスワード" type="password" fullWidth value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} />
              </Grid>
              <Grid item xs={12} sm={3}>
                <FormControl fullWidth>
                  <InputLabel>役職</InputLabel>
                  <Select label="役職" value={newUser.role}
                    onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                    <MenuItem value="viewer">閲覧者</MenuItem>
                    <MenuItem value="editor">編集者</MenuItem>
                    <MenuItem value="admin">管理人</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Button variant="contained" fullWidth onClick={handleCreateUser}>追加</Button>
              </Grid>
            </Grid>
            {newUser.role === 'editor' && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" sx={{ mb: 1 }}>編集を許可するデータ（後からマイページで変更できます）</Typography>
                <PermissionEditor
                  categories={categories}
                  permissions={newUser.permissions}
                  onChange={(p) => setNewUser({ ...newUser, permissions: p })}
                />
              </Box>
            )}
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>ユーザー一覧</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>役職</TableCell>
                  <TableCell>権限</TableCell>
                  <TableCell align="right">操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>{u.username}</TableCell>
                    <TableCell>
                      <Select size="small" value={u.role} onChange={(e) => handleUpdateUserRole(u, e.target.value)}>
                        <MenuItem value="viewer">閲覧者</MenuItem>
                        <MenuItem value="editor">編集者</MenuItem>
                        <MenuItem value="admin">管理人</MenuItem>
                      </Select>
                    </TableCell>
                    <TableCell>
                      {u.role === 'editor' ? (
                        <Button size="small" onClick={() => setEditingUser(u)}>権限を編集</Button>
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          {u.role === 'admin' ? '全データ編集可' : '編集不可'}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell align="right">
                      <IconButton size="small" color="error" onClick={() => handleDeleteUser(u)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          {editingUser && (
            <Paper sx={{ p: 2, mt: 2 }}>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>
                {editingUser.username} の編集権限
              </Typography>
              <PermissionEditor
                categories={categories}
                permissions={editingUser.permissions}
                onChange={(p) => setEditingUser({ ...editingUser, permissions: p })}
              />
              <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
                <Button variant="contained" onClick={handleSavePermissions}>保存</Button>
                <Button onClick={() => setEditingUser(null)}>閉じる</Button>
              </Box>
            </Paper>
          )}
        </>
      )}
    </Box>
  );
}

export default MyPage;
