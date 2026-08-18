import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import OpenFileMenuButton from './OpenFileMenuButton';
import { confirmDeleteWithReferenceCheck } from '../services/api';

function BehaviorGrid() {
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [open, setOpen] = useState(false);
  const [newBehaviorName, setNewBehaviorName] = useState('');
  const [loading, setLoading] = useState(true);

  // データ取得
  useEffect(() => {
    fetch('/api/behavior-data')
      .then(response => response.json())
      .then(fetchedData => {
        console.log('Raw fetched behavior-data:', fetchedData);
        const validData = Array.isArray(fetchedData)
          ? fetchedData.map(item => ({
              id: item.id || Math.random().toString(36).substr(2, 9),
              name: item.name || 'Unknown',
            }))
          : [];
        console.log('Processed behavior-data:', validData);
        setData(validData);
        setLoading(false);
      })
      .catch(error => {
        console.error('ビヘイビアデータの取得エラー:', error);
        setData([]);
        setLoading(false);
      });
  }, []);

  // 新しいビヘイビアを追加
  const handleAddBehaviorData = () => {
    if (!newBehaviorName.trim()) {
      alert('ビヘイビア名を入力してください');
      return;
    }
    fetch('/api/behavior-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newBehaviorName }),
    })
      .then(response => response.json())
      .then(result => {
        if (result.error) {
          alert(result.error);
          return;
        }
        const newData = [...data, { id: result.data.id, name: newBehaviorName }];
        setData(newData);
        setOpen(false);
        setNewBehaviorName('');
        alert(result.message);
      })
      .catch(error => alert('追加エラー: ' + error.message));
  };

  // ビヘイビアを削除
  const handleDelete = async (name) => {
    if (await confirmDeleteWithReferenceCheck('behavior_data', name)) {
      fetch(`/api/behavior-data/${name}`, {
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
      headerName: 'ビヘイビア名',
      width: 200,
      renderCell: (params) => {
        const value = typeof params.value === 'string' ? params.value : '不明';
        return (
          <a
            href={`/behavior/${value}`}
            onClick={(e) => {
              e.preventDefault();
              navigate(`/behavior/${value}`);
            }}
            style={{ color: '#1976d2', textDecoration: 'none', cursor: 'pointer' }}
          >
            {value}
          </a>
        );
      },
    },
    {
      field: 'openInEditor',
      headerName: 'エディタ',
      width: 80,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <OpenFileMenuButton category="behavior_data" name={params.row.name} />
      ),
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
        ビヘイビア一覧
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button
          variant="contained"
          color="primary"
          onClick={() => setOpen(true)}
          sx={{ textTransform: 'none', borderRadius: 2 }}
        >
          新しいビヘイビアを追加
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
            disableRowSelectionOnClick
          />
        </div>
      )}

      {/* 追加ダイアログ */}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>
          新しいビヘイビアを追加
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField
            autoFocus
            margin="dense"
            label="ビヘイビア名"
            fullWidth
            variant="outlined"
            value={newBehaviorName}
            onChange={(e) => setNewBehaviorName(e.target.value)}
            required
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} color="secondary" sx={{ textTransform: 'none' }}>
            キャンセル
          </Button>
          <Button onClick={handleAddBehaviorData} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
            追加
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default BehaviorGrid;