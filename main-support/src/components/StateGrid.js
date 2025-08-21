import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { useNavigate } from 'react-router-dom';

function StateGrid() {
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [open, setOpen] = useState(false);
  const [newEnumName, setNewEnumName] = useState('');
  const [loading, setLoading] = useState(true);

  // データ取得
  useEffect(() => {
    fetch('/api/state-data')
      .then(response => response.json())
      .then(data => {
        const validData = data.map((item, index) => ({
          id: index + 1,
          name: item
        }));
        console.log('Fetched state-data data:', validData);
        setData(validData);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching state-data:', error);
        setLoading(false);
      });
  }, []);

  // 新しい状態を追加
  const handleAddStateData = () => {
    if (!newEnumName.trim()) {
      alert('状態名を入力してください');
      return;
    }
    fetch('/api/state-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newEnumName })
    })
      .then(response => response.json())
      .then(result => {
        const newData = [...data, { id: data.length + 1, name: newEnumName }];
        console.log('Added state:', newEnumName, 'New data:', newData);
        setData(newData);
        setOpen(false);
        setNewEnumName('');
        alert(result.message);
      })
      .catch(error => alert('追加エラー: ' + error));
  };

  // 状態を削除
  const handleDelete = (name) => {
    if (window.confirm(`${name}.state.json を削除しますか？`)) {
      fetch(`/api/state-data/${name}`, {
        method: 'DELETE'
      })
        .then(response => response.json())
        .then(result => {
          const updatedData = data.filter(item => item.name !== name);
          console.log('Deleted state:', name, 'Updated data:', updatedData);
          setData(updatedData);
          alert(result.message);
        })
        .catch(error => alert('削除エラー: ' + error));
    }
  };

  const columns = [
    {
      field: 'name',
      headerName: 'State Name',
      width: 200,
      renderCell: (params) => (
        <a
          href={`/state/${params.value}`}
          onClick={(e) => {
            e.preventDefault();
            console.log('Navigating to state:', params.value);
            navigate(`/state/${params.value}`);
          }}
          style={{ color: '#1976d2', textDecoration: 'none', cursor: 'pointer' }}
        >
          {params.value}
        </a>
      )
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 150,
      renderCell: (params) => (
        <Button
          variant="contained"
          color="error"
          size="small"
          onClick={() => handleDelete(params.row.name)}
        >
          削除
        </Button>
      )
    }
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        State
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button
          variant="contained"
          color="primary"
          onClick={() => setOpen(true)}
        >
          新しい状態を追加
        </Button>
      </Box>
      {loading ? (
        <Typography>Loading...</Typography>
      ) : (
        <div style={{ height: 400, width: '100%' }}>
          <DataGrid
            rows={data}
            columns={columns}
            pageSizeOptions={[5]}
            getRowId={(row) => row.id}
          />
        </div>
      )}
      <Dialog open={open} onClose={() => setOpen(false)}>
        <DialogTitle>新しい状態を追加</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="状態名"
            fullWidth
            variant="standard"
            value={newEnumName}
            onChange={(e) => setNewEnumName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>キャンセル</Button>
          <Button onClick={handleAddStateData}>追加</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default StateGrid;