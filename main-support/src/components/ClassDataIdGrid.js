import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField } from '@mui/material';
import { useNavigate } from 'react-router-dom';

function ClassDataIdGrid() {
  const [classDataIdData, setClassDataIdData] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [newName, setNewName] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetch('/api/class-data-id')
      .then(response => {
        if (!response.ok) throw new Error(`class-data-id取得に失敗: ${response.status}`);
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('class-data-idエンドポイントからJSON以外のレスポンスを受信');
        }
        return response.json();
      })
      .then(data => {
        const validData = data.filter(item => item.name && !item.name.includes(':') && typeof item.name === 'string');
        if (validData.length !== data.length) {
          console.warn('不正な名前をフィルタリング:', data.filter(item => !item.name || item.name.includes(':')));
        }
        setClassDataIdData(validData);
      })
      .catch(error => {
        console.error('class-data-id取得エラー:', error);
        alert('データ取得エラー: ' + error.message);
      });
  }, []);

  const handleCreate = () => {
    if (!newName.trim()) {
      alert('名前は必須です');
      return;
    }
    if (newName.includes(':')) {
      alert('名前に":"を含めることはできません');
      return;
    }
    fetch('/api/class-data-id', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName }),
    })
      .then(response => {
        if (!response.ok) throw new Error(`${newName} の作成に失敗`);
        return response.json();
      })
      .then(result => {
        if (result.error) throw new Error(result.error);
        alert(result.message);
        setClassDataIdData([...classDataIdData, result.data]);
        setOpenDialog(false);
        setNewName('');
      })
      .catch(error => alert('作成エラー: ' + error.message));
  };

  const handleDelete = (name) => {
    if (window.confirm(`${name} を削除しますか？`)) {
      fetch('/api/class-data-id', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      .then(response => {
        if (!response.ok) throw new Error(`${name} の削除に失敗`);
        return response.json();
      })
      .then(result => {
        alert(result.message);
        setClassDataIdData(classDataIdData.filter(item => item.name !== name));
      })
      .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  const columns = [
    { 
      field: 'name', 
      headerName: '名前', 
      width: 150,
      renderCell: (params) => (
        <div 
          style={{ cursor: 'pointer', color: '#1976d2' }} 
          onClick={() => {
            if (params.value && !params.value.includes(':') && typeof params.value === 'string') {
              navigate(`/class-data-id/${encodeURIComponent(params.value)}`);
            } else {
              alert('不正なClassDataID名です');
            }
          }}
        >
          {params.value}
        </div>
      )
    },
    { field: 'id', headerName: 'ID', width: 90 },
    {
      field: 'actions',
      headerName: '操作',
      width: 100,
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
    <div style={{ height: 400, width: '100%', padding: '20px' }}>
      <Button 
        variant="contained" 
        color="primary" 
        onClick={() => setOpenDialog(true)}
        sx={{ mb: 2 }}
      >
        新しいClassDataIDを作成
      </Button>
      <DataGrid
        rows={classDataIdData}
        columns={columns}
        pageSizeOptions={[5]}
        getRowId={(row) => row.id}
      />
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいClassDataIDを作成</DialogTitle>
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
    </div>
  );
}

export default ClassDataIdGrid;