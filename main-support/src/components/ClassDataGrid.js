import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { useNavigate } from 'react-router-dom';

function ClassDataGrid() {
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [newClassName, setNewClassName] = useState('');
  const [openDialog, setOpenDialog] = useState(false);
  const [loading, setLoading] = useState(true);

  // データ取得
  useEffect(() => {
    fetch('/api/class-data')
      .then(response => {
        if (!response.ok) {
          console.warn(`HTTPエラー！ステータス: ${response.status}`);
          return [];
        }
        return response.json();
      })
      .then(fetchedData => {
        console.log('取得したクラスデータ:', fetchedData);
        if (Array.isArray(fetchedData)) {
          setData(fetchedData.map(item => ({
            id: item.id,
            name: item.name || '不明'
          })));
        } else {
          setData([]);
        }
        setLoading(false);
      })
      .catch(error => {
        console.error('クラスデータ取得エラー:', error);
        setData([]);
        setLoading(false);
      });
  }, []);

  // 新しいクラスの追加
  const handleAddClass = () => {
    setOpenDialog(true);
  };

  const handleCreateClass = () => {
    if (!newClassName.trim()) {
      alert('クラス名を入力してください');
      return;
    }
    fetch('/api/class-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newClassName }),
    })
      .then(response => {
        if (!response.ok) {
          return response.text().then(text => {
            throw new Error(`HTTPエラー！ステータス: ${response.status}, 本文: ${text}`);
          });
        }
        return response.json();
      })
      .then(result => {
        alert(result.message);
        setData([...data, { id: result.data.id, name: newClassName }]);
        setNewClassName('');
        setOpenDialog(false);
      })
      .catch(error => {
        console.error('クラス追加エラー:', error);
        alert('クラス追加エラー: ' + error.message);
      });
  };

  // クラス削除
  const handleDeleteClass = (name) => {
    if (window.confirm(`クラス ${name} を削除しますか？`)) {
      fetch('/api/class-data', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
        .then(response => {
          if (!response.ok) {
            return response.text().then(text => {
              throw new Error(`HTTPエラー！ステータス: ${response.status}, 本文: ${text}`);
            });
          }
          return response.json();
        })
        .then(result => {
          alert(result.message);
          setData(data.filter(item => item.name !== name));
        })
        .catch(error => {
          console.error('クラス削除エラー:', error);
          alert('クラス削除エラー: ' + error.message);
        });
    }
  };

  const columns = [
    { field: 'id', headerName: 'ID', width: 100 },
    {
      field: 'name',
      headerName: '名前',
      width: 200,
      renderCell: (params) => (
        <Button
          variant="text"
          onClick={() => navigate(`/class/${params.value}`)}
        >
          {params.value}
        </Button>
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
          onClick={() => handleDeleteClass(params.row.name)}
        >
          削除
        </Button>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        クラスデータ
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button variant="contained" onClick={handleAddClass}>
          追加
        </Button>
      </Box>
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいクラスの作成</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="クラス名"
            fullWidth
            variant="standard"
            value={newClassName}
            onChange={(e) => setNewClassName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>キャンセル</Button>
          <Button onClick={handleCreateClass}>作成</Button>
        </DialogActions>
      </Dialog>
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
    </Box>
  );
}

export default ClassDataGrid;