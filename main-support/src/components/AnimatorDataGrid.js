// AnimatorDataGrid.js (ClassDataIdGrid.js と100%同挙動)
import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import OpenFileMenuButton from './OpenFileMenuButton';

function AnimatorDataGrid() {
  const [animData, setAnimData] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [newName, setNewName] = useState('');
  const [newGroup, setNewGroup] = useState('Default'); // グループも入力可能に
  const navigate = useNavigate();

  useEffect(() => {
    fetch('/api/animator-data')
      .then(r => r.json())
      .then(data => setAnimData(data))
      .catch(err => alert('取得エラー: ' + err.message));
  }, []);

  const handleCreate = () => {
    if (!newName.trim()) return alert('名前必須');
    if (newName.includes(':')) return alert(':禁止');

    fetch('/api/animator-create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName, group: newGroup }),
    })
      .then(r => r.json())
      .then(res => {
        alert(res.message);
        window.location.reload();
      })
      .catch(err => alert('作成エラー: ' + err.message));
  };

  const handleDelete = (name) => {
    if (!window.confirm(`${name} 削除？`)) return;

    fetch('/api/animator-data', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
      .then(r => r.json())
      .then(() => window.location.reload());
  };

  const columns = [
    { field: 'name', headerName: '名前', width: 200,
      renderCell: (params) => (
        <div style={{ cursor: 'pointer', color: '#1976d2' }}
             onClick={() => navigate(`/animator/${encodeURIComponent(params.value)}`)}>
          {params.value}
        </div>
      )
    },
    { field: 'id', headerName: 'ID', width: 90 },
    {
      field: 'openInEditor', headerName: 'エディタ', width: 80, sortable: false, filterable: false,
      renderCell: (params) => (
        <OpenFileMenuButton category="animator_data" name={params.row.name} />
      ),
    },
    { field: 'actions', headerName: '操作', width: 120,
      renderCell: (params) => (
        <Button variant="contained" color="error" size="small"
                onClick={() => handleDelete(params.row.name)}>
          削除
        </Button>
      )
    },
  ];

  return (
    <div style={{ height: 600, width: '100%', padding: '20px' }}>
      <Button variant="contained" color="primary" onClick={() => setOpenDialog(true)} sx={{ mb: 2 }}>
        新しいAnimatorを作成
      </Button>
      <Button variant="contained" color="secondary" sx={{ mb: 2, ml: 2 }}
              onClick={() => fetch('/api/generate-all-animator', { method: 'POST' })
                .then(r => r.json()).then(res => alert(res.message))}>
        全Animator自動生成
      </Button>

      <DataGrid rows={animData} columns={columns} getRowId={row => row.id} />

      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいAnimatorを作成</DialogTitle>
        <DialogContent>
          <TextField autoFocus margin="dense" label="グループ" fullWidth value={newGroup}
                     onChange={e => setNewGroup(e.target.value)} />
          <TextField margin="dense" label="名前" fullWidth value={newName}
                     onChange={e => setNewName(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>キャンセル</Button>
          <Button onClick={handleCreate}>作成</Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}

export default AnimatorDataGrid;