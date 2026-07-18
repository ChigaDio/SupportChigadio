import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { useNavigate } from 'react-router-dom';

function CustomClassDataGrid() {
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [newName, setNewName] = useState('');
  const [openDialog, setOpenDialog] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/custom-class-data')
      .then(response => (response.ok ? response.json() : []))
      .then(fetchedData => {
        setData(Array.isArray(fetchedData) ? fetchedData.map(item => ({ id: item.id, name: item.name })) : []);
        setLoading(false);
      })
      .catch(error => {
        console.error('CustomClassData取得エラー:', error);
        setData([]);
        setLoading(false);
      });
  }, []);

  const handleCreate = () => {
    if (!newName.trim()) {
      alert('名前を入力してください');
      return;
    }
    fetch('/api/custom-class-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName }),
    })
      .then(response => response.json())
      .then(result => {
        if (result.error) throw new Error(result.error);
        alert(result.message);
        setData([...data, { id: result.data.id, name: newName }]);
        setNewName('');
        setOpenDialog(false);
      })
      .catch(error => alert('作成エラー: ' + error.message));
  };

  const handleDelete = (name) => {
    if (window.confirm(`CustomClassData ${name} を削除しますか？`)) {
      fetch('/api/custom-class-data', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          setData(data.filter(item => item.name !== name));
        })
        .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  const columns = [
    { field: 'id', headerName: 'ID', width: 90 },
    {
      field: 'name',
      headerName: '名前',
      width: 220,
      renderCell: (params) => (
        <Button variant="text" onClick={() => navigate(`/custom-class-data/${params.value}`)}>
          {params.value}
        </Button>
      ),
    },
    {
      field: 'actions',
      headerName: '操作',
      width: 120,
      renderCell: (params) => (
        <Button variant="contained" color="error" size="small" onClick={() => handleDelete(params.row.name)}>
          削除
        </Button>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        CustomClassData（オプション付き変数定義）
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button variant="contained" onClick={() => setOpenDialog(true)}>
          追加
        </Button>
      </Box>
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいCustomClassDataを作成</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="名前"
            fullWidth
            variant="standard"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>キャンセル</Button>
          <Button onClick={handleCreate}>作成</Button>
        </DialogActions>
      </Dialog>
      {loading ? (
        <Typography>読み込み中...</Typography>
      ) : (
        <div style={{ height: 450, width: '100%' }}>
          <DataGrid rows={data} columns={columns} pageSizeOptions={[5]} getRowId={(row) => row.id} />
        </div>
      )}
    </Box>
  );
}

export default CustomClassDataGrid;
