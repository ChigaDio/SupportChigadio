import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete } from '@mui/material';
import { useNavigate } from 'react-router-dom';

function ScenarioRoleGrid() {
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [newRoleName, setNewRoleName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newBranchType, setNewBranchType] = useState('General');
  const [openDialog, setOpenDialog] = useState(false);
  const [loading, setLoading] = useState(true);

  // Fetch data
  useEffect(() => {
    fetch('/api/scenario-role')
      .then(response => {
        if (!response.ok) {
          console.warn(`HTTPエラー！ステータス: ${response.status}`);
          return [];
        }
        return response.json();
      })
      .then(fetchedData => {
        console.log('取得したシナリオロールデータ:', fetchedData);
        if (Array.isArray(fetchedData)) {
          setData(fetchedData.map(item => ({
            id: item.id,
            name: item.name || '不明',
            description: item.description || '',
            branchType: item.branchType || 'General'
          })));
        } else {
          setData([]);
        }
        setLoading(false);
      })
      .catch(error => {
        console.error('シナリオロールデータ取得エラー:', error);
        setData([]);
        setLoading(false);
      });
  }, []);

  // Add new role
  const handleAddRole = () => {
    setOpenDialog(true);
  };

  const handleCreateRole = () => {
    if (!newRoleName.trim()) {
      alert('ロール名を入力してください');
      return;
    }
    fetch('/api/scenario-role', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newRoleName, description: newDescription, branchType: newBranchType }),
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
        setData([...data, { id: result.data.id, name: newRoleName, description: newDescription, branchType: newBranchType }]);
        setNewRoleName('');
        setNewDescription('');
        setNewBranchType('General');
        setOpenDialog(false);
      })
      .catch(error => {
        console.error('ロール追加エラー:', error);
        alert('ロール追加エラー: ' + error.message);
      });
  };

  // Delete role
  const handleDeleteRole = (name) => {
    if (window.confirm(`ロール ${name} を削除しますか？`)) {
      fetch('/api/scenario-role', {
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
          console.error('ロール削除エラー:', error);
          alert('ロール削除エラー: ' + error.message);
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
          onClick={() => navigate(`/scenario-role/${params.value}`)}
        >
          {params.value}
        </Button>
      ),
    },
    { field: 'description', headerName: '説明', width: 300 },
    { field: 'branchType', headerName: 'タイプ', width: 150 },
    {
      field: 'actions',
      headerName: 'アクション',
      width: 150,
      renderCell: (params) => (
        <Button
          variant="contained"
          color="error"
          size="small"
          onClick={() => handleDeleteRole(params.row.name)}
        >
          削除
        </Button>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        シナリオロール
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button variant="contained" onClick={handleAddRole}>
          追加
        </Button>
      </Box>
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいロールの作成</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="ロール名"
            fullWidth
            variant="standard"
            value={newRoleName}
            onChange={(e) => setNewRoleName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="説明"
            fullWidth
            variant="standard"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
          />
          <Autocomplete
            options={['General', 'Branch']}
            value={newBranchType}
            onChange={(e, newValue) => setNewBranchType(newValue || 'General')}
            renderInput={(params) => <TextField {...params} label="タイプ" margin="dense" fullWidth />}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>キャンセル</Button>
          <Button onClick={handleCreateRole}>作成</Button>
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

export default ScenarioRoleGrid;