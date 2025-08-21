import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';

function ClassDataDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [typeOptions, setTypeOptions] = useState([]); // Type suggestions
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [newType, setNewType] = useState('');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newArraySize, setNewArraySize] = useState(0);

  // Fetch data for the class
  useEffect(() => {
    fetch(`/api/class-data/${name}`)
      .then(response => response.json())
      .then(fetchedData => {
        setData(fetchedData.map((item, index) => ({ ...item, id: item.id || index + 1 })));
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching class data:', error);
        setLoading(false);
      });
  }, [name]);

  // Fetch type suggestions (basic, Unity, Enum-id, ClassData)
  useEffect(() => {
    const basicTypes = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object'];
    const unityTypes = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject'];

    Promise.all([
      fetch('/api/enum-id').then(res => res.json()),
      fetch('/api/class-data').then(res => res.json())
    ]).then(([enumList, classList]) => {
      const enumTypes = enumList.map(item => item.name);
      const classTypes = classList.map(item => item.name);
      setTypeOptions([...basicTypes, ...unityTypes, ...enumTypes, ...classTypes]);
    }).catch(error => console.error('Error fetching type options:', error));
  }, []);

  // Add new row
  const handleAddRow = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('Type and Name are required');
      return;
    }
    const maxId = Math.max(...data.map(item => item.id), 0) + 1;
    const newRow = {
      id: maxId,
      type: newType,
      name: newName,
      description: newDescription,
      arraySize: parseInt(newArraySize, 10) || 0
    };
    setData([...data, newRow]);
    setOpen(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
    setNewArraySize(0);
  };

  // Delete row
  const handleDeleteRow = (id) => {
    setData(data.filter(item => item.id !== id));
  };

  // Reorder rows
  const handleRowOrderChange = (params) => {
    const { oldIndex, targetIndex } = params;
    const newData = [...data];
    const [movedRow] = newData.splice(oldIndex, 1);
    newData.splice(targetIndex, 0, movedRow);
    setData(newData);
  };

  // Save data
  const handleSave = () => {
    fetch(`/api/class-data/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('Error saving data: ' + error));
  };

  // Delete class
  const handleDelete = () => {
    if (window.confirm(`Delete ${name}?`)) {
      fetch(`/api/class-data/${name}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          navigate('/class-data');
        })
        .catch(error => alert('Error deleting class: ' + error));
    }
  };

  // Generate C#
  const handleGenerateCs = () => {
    fetch(`/api/generate-class/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('Error generating C#: ' + error));
  };

  const columns = [
    {
      field: 'type',
      headerName: 'Type',
      width: 200,
      renderCell: (params) => params.value,
      editable: true,
      renderEditCell: (params) => (
        <Autocomplete
          freeSolo
          options={typeOptions}
          value={params.value}
          onChange={(e, newValue) => params.api.setEditCellValue({ id: params.id, field: params.field, value: newValue })}
          renderInput={(params) => <TextField {...params} />}
        />
      )
    },
    { field: 'name', headerName: 'Name', width: 150, editable: true },
    { field: 'description', headerName: 'Description', width: 250, editable: true },
    { field: 'arraySize', headerName: 'ArraySize', width: 150, editable: true, type: 'number' },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 150,
      renderCell: (params) => (
        <Button variant="contained" color="error" size="small" onClick={() => handleDeleteRow(params.id)}>
          Delete
        </Button>
      )
    }
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Class Data Detail: {name}
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setOpen(true)} sx={{ mr: 1 }}>
          新しい変数を追加
        </Button>
        <Button variant="contained" color="primary" onClick={handleSave} sx={{ mr: 1 }}>
          保存d
        </Button>
        <Button variant="contained" color="secondary" onClick={handleGenerateCs} sx={{ mr: 1 }}>
          C#を生成
        </Button>
        <Button variant="contained" color="error" onClick={handleDelete}>
          削除
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
            rowReordering
            onRowOrderChange={handleRowOrderChange}
          />
        </div>
      )}
      <Dialog open={open} onClose={() => setOpen(false)}>
        <DialogTitle>新しい変数を追加</DialogTitle>
        <DialogContent>
          <Autocomplete
            freeSolo
            options={typeOptions}
            renderInput={(params) => <TextField {...params} label="変数の型" margin="dense" fullWidth />}
            value={newType}
            onChange={(e, newValue) => setNewType(newValue)}
          />
          <TextField label="変数名" margin="dense" fullWidth value={newName} onChange={(e) => setNewName(e.target.value)} />
          <TextField label="説明" margin="dense" fullWidth value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
          <TextField label="配列サイズ" margin="dense" fullWidth type="number" value={newArraySize} onChange={(e) => setNewArraySize(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleAddRow}>Add</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ClassDataDetailGrid;