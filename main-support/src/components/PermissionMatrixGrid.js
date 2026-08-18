import React, { useEffect, useMemo, useState } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Box, Typography, Paper, Chip, Alert, CircularProgress, Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';

// pythonSrc/auth.py の /api/users, /api/categories をそのまま利用した、
// 「admin/editor/viewerごとに何ができるか」の一覧表示（読み取り専用）。
// MyPage.js には1ユーザーずつ編集するダイアログがあるが、全ユーザー×
// 全カテゴリを一度に見渡せる画面が無かったため、それを補うページ。
// バックエンドは既存のAPIをそのまま使うため変更していない。
function accessLevel(user, category) {
  if (user.role === 'admin') return { label: '全権限', color: 'success' };
  if (user.role === 'viewer') return { label: '閲覧のみ', color: 'default' };
  const perm = (user.permissions || {})[category];
  if (!perm) return { label: 'なし', color: 'default' };
  if (perm.all) return { label: '全て', color: 'info' };
  if ((perm.items || []).length > 0) return { label: `個別(${perm.items.length})`, color: 'warning' };
  return { label: 'なし', color: 'default' };
}

function PermissionMatrixGrid() {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const fetchData = () => {
    setLoading(true);
    setErrorMsg('');
    Promise.all([
      fetch('/api/users').then((r) => {
        if (!r.ok) throw new Error(r.status === 403 ? '管理人のみ閲覧できます' : `取得エラー(${r.status})`);
        return r.json();
      }),
      fetch('/api/categories').then((r) => r.json()),
    ])
      .then(([userList, categoryList]) => {
        setUsers(userList);
        setCategories(categoryList);
      })
      .catch((e) => setErrorMsg(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, []);

  const columns = useMemo(() => {
    const cols = [
      { field: 'category', headerName: 'カテゴリ', width: 180, pinnable: true },
    ];
    users.forEach((u) => {
      cols.push({
        field: `user_${u.id}`,
        headerName: `${u.username}（${{ admin: '管理人', editor: '編集者', viewer: '閲覧者' }[u.role] || u.role}）`,
        width: 170,
        sortable: false,
        filterable: false,
        renderCell: (params) => {
          const level = params.value;
          return <Chip size="small" label={level.label} color={level.color} variant={level.color === 'default' ? 'outlined' : 'filled'} />;
        },
      });
    });
    return cols;
  }, [users]);

  const rows = useMemo(() => {
    return categories.map((cat, idx) => {
      const row = { id: idx, category: cat };
      users.forEach((u) => {
        row[`user_${u.id}`] = accessLevel(u, cat);
      });
      return row;
    });
  }, [categories, users]);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Typography variant="h4">権限マトリクス</Typography>
        <Button
          variant="contained"
          onClick={fetchData}
          disabled={loading}
          startIcon={loading ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          更新
        </Button>
        <Button size="small" onClick={() => navigate('/mypage')}>マイページへ（個別編集）</Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        全ユーザー×全カテゴリの編集権限を一覧表示します（読み取り専用）。
        個別ユーザーの権限を変更する場合はマイページから行ってください。
      </Typography>

      {errorMsg && <Alert severity="warning" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      {!errorMsg && (
        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <Chip size="small" label="全権限" color="success" />
            <Chip size="small" label="全て" color="info" />
            <Chip size="small" label="個別(N)" color="warning" />
            <Chip size="small" label="なし / 閲覧のみ" variant="outlined" />
          </Box>
          <div style={{ height: 640, width: '100%' }}>
            <DataGrid
              rows={rows}
              columns={columns}
              loading={loading}
              disableRowSelectionOnClick
              hideFooter={rows.length <= 100}
              pageSizeOptions={[25, 50, 100]}
              initialState={{ pagination: { paginationModel: { pageSize: 50 } } }}
            />
          </div>
        </Paper>
      )}
    </Box>
  );
}

export default PermissionMatrixGrid;
