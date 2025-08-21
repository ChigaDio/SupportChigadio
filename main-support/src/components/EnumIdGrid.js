import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { fetchEnumIdData } from '../services/api';

function EnumIdGrid() {
  const [enumIdData, setEnumIdData] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [newEnumName, setNewEnumName] = useState('');
  const navigate = useNavigate();

  // データ取得
  useEffect(() => {
    fetchEnumIdData()
      .then(data => setEnumIdData(data))
      .catch(error => console.error('Error fetching data:', error));
  }, []);

  // 新しいEnum作成
  const handleCreateEnum = () => {
    if (!newEnumName.trim()) {
      alert('Enum name cannot be empty');
      return;
    }
    fetch('/api/enum-id', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newEnumName }),
    })
      .then(response => response.json())
      .then(result => {
        if (result.error) throw new Error(result.error);
        alert(result.message);
        setEnumIdData([...enumIdData, result.data]); // リスト更新
        setOpenDialog(false);
        setNewEnumName('');
      })
      .catch(error => alert('Error creating enum: ' + error));
  };

  // Enum削除
  const handleDeleteEnum = (name) => {
    if (window.confirm(`Delete ${name}?`)) {
      fetch(`/api/enum/${name}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
          if (result.error) throw new Error(result.error);
          alert(result.message);
          setEnumIdData(enumIdData.filter(item => item.name !== name)); // リスト更新
        })
        .catch(error => alert('Error deleting enum: ' + error));
    }
  };

  const columns = [
    { 
      field: 'name', 
      headerName: 'Name', 
      width: 150,
      renderCell: (params) => (
        <div 
          style={{ cursor: 'pointer', color: '#1976d2' }} 
          onClick={() => navigate(`/enum/${params.value}`)}
        >
          {params.value}
        </div>
      )
    },
    { field: 'id', headerName: 'ID', width: 90 },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 100,
      renderCell: (params) => (
        <Button
          variant="contained"
          color="error"
          size="small"
          onClick={() => handleDeleteEnum(params.row.name)}
        >
          Delete
        </Button>
      ),
    },
  ];

  return (
    <div style={{ height: 400, width: '100%' }}>
      <Button 
        variant="contained" 
        color="primary" 
        onClick={() => setOpenDialog(true)}
        sx={{ mb: 2 }}
      >
        Create New Enum
      </Button>
      <DataGrid
        rows={enumIdData}
        columns={columns}
        pageSize={5}
        rowsPerPageOptions={[5]}
      />
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>Create New Enum</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Enum Name"
            fullWidth
            variant="standard"
            value={newEnumName}
            onChange={(e) => setNewEnumName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>Cancel</Button>
          <Button onClick={handleCreateEnum}>Create</Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}

export default EnumIdGrid;