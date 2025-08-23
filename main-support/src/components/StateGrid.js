import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { useNavigate } from 'react-router-dom';

function StateGrid() {
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [open, setOpen] = useState(false);
  const [newStateName, setNewStateName] = useState('');
  const [loading, setLoading] = useState(true);

  // データ取得
  useEffect(() => {
    fetch('/api/state-data')
      .then(response => response.json())
      .then(fetchedData => {
        console.log('Raw fetched state-data:', fetchedData);
        // API から返されるデータは [{ id, name }] の形式
        const validData = Array.isArray(fetchedData)
          ? fetchedData.map(item => ({
              id: item.id || Math.random().toString(36).substr(2, 9), // 一意の ID を保証
              name: item.name || 'Unknown',
            }))
          : [];
        console.log('Processed state-data:', validData);
        setData(validData);
        setLoading(false);
      })
      .catch(error => {
        console.error('状態データの取得エラー:', error);
        setData([]);
        setLoading(false);
      });
  }, []);

  // 新しい状態を追加
  const handleAddStateData = () => {
    if (!newStateName.trim()) {
      alert('状態名を入力してください');
      return;
    }
    fetch('/api/state-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newStateName }),
    })
      .then(response => response.json())
      .then(result => {
        if (result.error) {
          alert(result.error);
          return;
        }
        const newData = [...data, { id: result.data.id, name: newStateName }];
        setData(newData);
        setOpen(false);
        setNewStateName('');
        alert(result.message);
      })
      .catch(error => alert('追加エラー: ' + error.message));
  };

  // 状態を削除
  const handleDelete = (name) => {
    if (window.confirm(`${name}.state.json を削除しますか？`)) {
      fetch(`/api/state-data/${name}`, {
        method: 'DELETE',
      })
        .then(response => response.json())
        .then(result => {
          if (result.error) {
            alert(result.error);
            return;
          }
          const updatedData = data.filter(item => item.name !== name);
          setData(updatedData);
          alert(result.message);
        })
        .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  const columns = [
    {
      field: 'name',
      headerName: '状態名',
      width: 200,
      renderCell: (params) => {
        const value = typeof params.value === 'string' ? params.value : '不明';
        return (
          <a
            href={`/state/${value}`}
            onClick={(e) => {
              e.preventDefault();
              console.log('遷移先:', value);
              navigate(`/state/${value}`);
            }}
            style={{ color: '#1976d2', textDecoration: 'none', cursor: 'pointer' }}
          >
            {value}
          </a>
        );
      },
    },
    {
      field: 'actions',
      headerName: 'アクション',
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
      ),
    },
  ];

  return (
    <Box sx={{ p: 3, bgcolor: 'background.default' }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
        状態一覧
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button
          variant="contained"
          color="primary"
          onClick={() => setOpen(true)}
          sx={{ textTransform: 'none', borderRadius: 2 }}
        >
          新しい状態を追加
        </Button>
      </Box>
      {loading ? (
        <Typography>読み込み中...</Typography>
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
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white' }}>新しい状態を追加</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField
            autoFocus
            margin="dense"
            label="状態名"
            fullWidth
            variant="outlined"
            value={newStateName}
            onChange={(e) => setNewStateName(e.target.value)}
            required
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} color="secondary" sx={{ textTransform: 'none' }}>
            キャンセル
          </Button>
          <Button onClick={handleAddStateData} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
            追加
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default StateGrid;