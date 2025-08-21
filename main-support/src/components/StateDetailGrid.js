import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Grid, Card, CardContent, IconButton, Autocomplete } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import { styled } from '@mui/material/styles';

function StateDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [transitions, setTransitions] = useState([]);
  const [selectedTransition, setSelectedTransition] = useState(null);
  const [transitionVariables, setTransitionVariables] = useState([]);
  const [managerData, setManagerData] = useState([]);
  const [openTransitionDialog, setOpenTransitionDialog] = useState(false);
  const [openVariableDialog, setOpenVariableDialog] = useState(false);
  const [openManagerDialog, setOpenManagerDialog] = useState(false);
  const [newFromState, setNewFromState] = useState('');
  const [newToState, setNewToState] = useState('');
  const [newCondition, setNewCondition] = useState('');
  const [newType, setNewType] = useState('');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newArraySize, setNewArraySize] = useState(0);
  const [typeOptions, setTypeOptions] = useState([]);
  const [loading, setLoading] = useState(true);

  // Styled DataGrid for enhanced visuals
  const StyledDataGrid = styled(DataGrid)(({ theme }) => ({
    '& .MuiDataGrid-row': {
      transition: 'background-color 0.2s',
      '&:hover': {
        backgroundColor: theme.palette.action.hover,
      },
    },
    '& .MuiDataGrid-row.Mui-selected': {
      backgroundColor: theme.palette.primary.light,
      color: theme.palette.primary.contrastText,
      '&:hover': {
        backgroundColor: theme.palette.primary.main,
      },
    },
    '& .MuiDataGrid-cell': {
      padding: theme.spacing(1),
    },
    '& .MuiDataGrid-columnHeaders': {
      backgroundColor: theme.palette.primary.main,
      color: theme.palette.primary.contrastText,
      fontWeight: 'bold',
    },
  }));

  // Fetch data
  useEffect(() => {
    setLoading(true);
    // Fetch state transitions
    fetch(`/api/state-data/${name}/transitions`)
      .then(response => response.json())
      .then(fetchedTransitions => setTransitions(fetchedTransitions.map((item, index) => ({ ...item, id: item.id || index + 1 }))))
      .catch(error => console.error('Error fetching transitions:', error));

    // Fetch manager data
    fetch(`/api/state-data/${name}/manager`)
      .then(response => response.json())
      .then(fetchedManager => setManagerData(fetchedManager.map((item, index) => ({ ...item, id: item.id || index + 1 }))))
      .catch(error => console.error('Error fetching manager data:', error));

    // Fetch type options
    const basicTypes = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object'];
    const unityTypes = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject'];
    Promise.all([
      fetch('/api/enum-id').then(res => res.json()),
      fetch('/api/class-data').then(res => res.json()),
    ])
      .then(([enumList, classList]) => {
        const enumTypes = enumList.map(item => item.name);
        const classTypes = classList.map(item => item.name);
        setTypeOptions([...basicTypes, ...unityTypes, ...enumTypes, ...classTypes]);
      })
      .catch(error => console.error('Error fetching type options:', error))
      .finally(() => setLoading(false));
  }, [name]);

  // Add new transition
  const handleAddTransition = () => {
    if (!newFromState.trim() || !newToState.trim()) {
      alert('From State and To State are required');
      return;
    }
    const maxId = Math.max(...transitions.map(item => item.id), 0) + 1;
    const newTransition = {
      id: maxId,
      fromState: newFromState,
      toState: newToState,
      condition: newCondition,
    };
    const newTransitions = [...transitions, newTransition];
    setTransitions(newTransitions);
    handleSaveTransitions(newTransitions);
    setOpenTransitionDialog(false);
    setNewFromState('');
    setNewToState('');
    setNewCondition('');
  };

  // Save transitions
  const handleSaveTransitions = (updatedTransitions) => {
    fetch(`/api/state-data/${name}/transitions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updatedTransitions || transitions),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('Error saving transitions: ' + error));
  };

  // Delete transition
  const handleDeleteTransition = (id) => {
    const newTransitions = transitions.filter(item => item.id !== id);
    setTransitions(newTransitions);
    handleSaveTransitions(newTransitions);
    if (selectedTransition && selectedTransition.id === id) {
      setSelectedTransition(null);
      setTransitionVariables([]);
    }
  };

  // Select transition and load variables
  const handleSelectTransition = (id) => {
    const transition = transitions.find(item => item.id === id);
    setSelectedTransition(transition);
    fetch(`/api/state-data/${name}/transitions/${id}/variables`)
      .then(response => response.json())
      .then(fetchedVariables => setTransitionVariables(fetchedVariables.map((item, index) => ({ ...item, id: item.id || index + 1 }))))
      .catch(error => console.error('Error fetching variables:', error));
  };

  // Add new variable
  const handleAddVariable = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('Type and Name are required');
      return;
    }
    if (isNaN(newArraySize) || newArraySize < -1) {
      alert('ArraySize must be -1 (List), 0 (single), or positive (array)');
      return;
    }
    const maxId = Math.max(...transitionVariables.map(item => item.id), 0) + 1;
    const newVariable = {
      id: maxId,
      type: newType,
      name: newName,
      description: newDescription,
      arraySize: parseInt(newArraySize, 10),
    };
    const newVariables = [...transitionVariables, newVariable];
    setTransitionVariables(newVariables);
    handleSaveVariables(newVariables);
    setOpenVariableDialog(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
    setNewArraySize(0);
  };

  // Save variables
  const handleSaveVariables = (updatedVariables) => {
    if (!selectedTransition) return;
    fetch(`/api/state-data/${name}/transitions/${selectedTransition.id}/variables`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updatedVariables || transitionVariables),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('Error saving variables: ' + error));
  };

  // Delete variable
  const handleDeleteVariable = (id) => {
    const newVariables = transitionVariables.filter(item => item.id !== id);
    setTransitionVariables(newVariables);
    handleSaveVariables(newVariables);
  };

  // Add new manager data row
  const handleAddManagerRow = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('Type and Name are required');
      return;
    }
    if (isNaN(newArraySize) || newArraySize < -1) {
      alert('ArraySize must be -1 (List), 0 (single), or positive (array)');
      return;
    }
    const maxId = Math.max(...managerData.map(item => item.id), 0) + 1;
    const newRow = {
      id: maxId,
      type: newType,
      name: newName,
      description: newDescription,
      arraySize: parseInt(newArraySize, 10),
    };
    const newManagerData = [...managerData, newRow];
    setManagerData(newManagerData);
    handleSaveManager(newManagerData);
    setOpenManagerDialog(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
    setNewArraySize(0);
  };

  // Save manager data
  const handleSaveManager = (updatedManagerData) => {
    fetch(`/api/state-data/${name}/manager`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updatedManagerData || managerData),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('Error saving manager data: ' + error));
  };

  // Delete manager data row
  const handleDeleteManagerRow = (id) => {
    const newManagerData = managerData.filter(item => item.id !== id);
    setManagerData(newManagerData);
    handleSaveManager(newManagerData);
  };

  // DataGrid columns
  const transitionColumns = [
    { field: 'fromState', headerName: 'From State', width: 150 },
    { field: 'toState', headerName: 'To State', width: 150 },
    { field: 'condition', headerName: 'Condition', width: 200 },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 100,
      renderCell: (params) => (
        <IconButton color="error" onClick={() => handleDeleteTransition(params.row.id)}>
          <DeleteIcon />
        </IconButton>
      ),
    },
  ];

  const variableColumns = [
    {
      field: 'type',
      headerName: 'Type',
      width: 200,
      editable: true,
      renderEditCell: (params) => (
        <Autocomplete
          freeSolo
          options={typeOptions}
          value={params.value}
          onChange={(e, newValue) => params.api.setEditCellValue({ id: params.id, field: params.field, value: newValue || '' })}
          renderInput={(params) => <TextField {...params} />}
        />
      ),
    },
    { field: 'name', headerName: 'Name', width: 150, editable: true },
    { field: 'description', headerName: 'Description', width: 250, editable: true },
    { field: 'arraySize', headerName: 'ArraySize', width: 100, editable: true, type: 'number' },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 100,
      renderCell: (params) => (
        <IconButton color="error" onClick={() => handleDeleteVariable(params.row.id)}>
          <DeleteIcon />
        </IconButton>
      ),
    },
  ];

  const managerColumns = [
    {
      field: 'type',
      headerName: 'Type',
      width: 200,
      editable: true,
      renderEditCell: (params) => (
        <Autocomplete
          freeSolo
          options={typeOptions}
          value={params.value}
          onChange={(e, newValue) => params.api.setEditCellValue({ id: params.id, field: params.field, value: newValue || '' })}
          renderInput={(params) => <TextField {...params} />}
        />
      ),
    },
    { field: 'name', headerName: 'Name', width: 150, editable: true },
    { field: 'description', headerName: 'Description', width: 250, editable: true },
    { field: 'arraySize', headerName: 'ArraySize', width: 100, editable: true, type: 'number' },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 100,
      renderCell: (params) => (
        <IconButton color="error" onClick={() => handleDeleteManagerRow(params.row.id)}>
          <DeleteIcon />
        </IconButton>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main', mb: 4 }}>
        State Detail: {name}
      </Typography>
      
      {/* Block 1: State Transitions and Variables */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card sx={{ boxShadow: 3, borderRadius: 2, bgcolor: 'background.paper' }}>
            <CardContent>
              <Typography variant="h5" gutterBottom sx={{ fontWeight: 'medium', color: 'text.primary' }}>
                State Transitions
              </Typography>
              <Button
                variant="contained"
                color="primary"
                startIcon={<AddIcon />}
                onClick={() => setOpenTransitionDialog(true)}
                sx={{ mb: 2, borderRadius: 2, textTransform: 'none' }}
              >
                Add Transition
              </Button>
              <StyledDataGrid
                rows={transitions}
                columns={transitionColumns}
                pageSizeOptions={[5]}
                getRowId={(row) => row.id}
                onRowClick={(params) => handleSelectTransition(params.row.id)}
                rowSelectionModel={selectedTransition ? [selectedTransition.id] : []}
                loading={loading}
                sx={{ height: 400 }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ boxShadow: 3, borderRadius: 2, bgcolor: 'background.paper' }}>
            <CardContent>
              <Typography variant="h5" gutterBottom sx={{ fontWeight: 'medium', color: 'text.primary' }}>
                Transition Variables {selectedTransition ? `(Transition: ${selectedTransition.fromState} → ${selectedTransition.toState})` : '(Select a Transition)'}
              </Typography>
              <Button
                variant="contained"
                color="primary"
                startIcon={<AddIcon />}
                onClick={() => setOpenVariableDialog(true)}
                sx={{ mb: 2, borderRadius: 2, textTransform: 'none' }}
                disabled={!selectedTransition}
              >
                Add Variable
              </Button>
              <StyledDataGrid
                rows={transitionVariables}
                columns={variableColumns}
                pageSizeOptions={[5]}
                getRowId={(row) => row.id}
                loading={loading}
                sx={{ height: 400 }}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Block 2: Manager Data */}
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Card sx={{ boxShadow: 3, borderRadius: 2, bgcolor: 'background.paper' }}>
            <CardContent>
              <Typography variant="h5" gutterBottom sx={{ fontWeight: 'medium', color: 'text.primary' }}>
                Manager Data
              </Typography>
              <Button
                variant="contained"
                color="primary"
                startIcon={<AddIcon />}
                onClick={() => setOpenManagerDialog(true)}
                sx={{ mb: 2, borderRadius: 2, textTransform: 'none' }}
              >
                Add Manager Data
              </Button>
              <StyledDataGrid
                rows={managerData}
                columns={managerColumns}
                pageSizeOptions={[5]}
                getRowId={(row) => row.id}
                loading={loading}
                sx={{ height: 400 }}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Transition Dialog */}
      <Dialog open={openTransitionDialog} onClose={() => setOpenTransitionDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>Add New Transition</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField
            label="From State"
            fullWidth
            value={newFromState}
            onChange={(e) => setNewFromState(e.target.value)}
            margin="dense"
            variant="outlined"
            required
          />
          <TextField
            label="To State"
            fullWidth
            value={newToState}
            onChange={(e) => setNewToState(e.target.value)}
            margin="dense"
            variant="outlined"
            required
          />
          <TextField
            label="Condition"
            fullWidth
            value={newCondition}
            onChange={(e) => setNewCondition(e.target.value)}
            margin="dense"
            variant="outlined"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenTransitionDialog(false)} color="secondary" sx={{ textTransform: 'none' }}>
            Cancel
          </Button>
          <Button onClick={handleAddTransition} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
            Add
          </Button>
        </DialogActions>
      </Dialog>

      {/* Variable Dialog */}
      <Dialog open={openVariableDialog} onClose={() => setOpenVariableDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>Add New Variable</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Autocomplete
            freeSolo
            options={typeOptions}
            value={newType}
            onChange={(e, newValue) => setNewType(newValue || '')}
            renderInput={(params) => (
              <TextField {...params} label="Type" fullWidth margin="dense" variant="outlined" required />
            )}
          />
          <TextField
            label="Name"
            fullWidth
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            margin="dense"
            variant="outlined"
            required
          />
          <TextField
            label="Description"
            fullWidth
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            margin="dense"
            variant="outlined"
          />
          <TextField
            label="ArraySize"
            fullWidth
            type="number"
            value={newArraySize}
            onChange={(e) => setNewArraySize(e.target.value)}
            margin="dense"
            variant="outlined"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenVariableDialog(false)} color="secondary" sx={{ textTransform: 'none' }}>
            Cancel
          </Button>
          <Button onClick={handleAddVariable} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
            Add
          </Button>
        </DialogActions>
      </Dialog>

      {/* Manager Data Dialog */}
      <Dialog open={openManagerDialog} onClose={() => setOpenManagerDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>Add New Manager Data</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Autocomplete
            freeSolo
            options={typeOptions}
            value={newType}
            onChange={(e, newValue) => setNewType(newValue || '')}
            renderInput={(params) => (
              <TextField {...params} label="Type" fullWidth margin="dense" variant="outlined" required />
            )}
          />
          <TextField
            label="Name"
            fullWidth
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            margin="dense"
            variant="outlined"
            required
          />
          <TextField
            label="Description"
            fullWidth
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            margin="dense"
            variant="outlined"
          />
          <TextField
            label="ArraySize"
            fullWidth
            type="number"
            value={newArraySize}
            onChange={(e) => setNewArraySize(e.target.value)}
            margin="dense"
            variant="outlined"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenManagerDialog(false)} color="secondary" sx={{ textTransform: 'none' }}>
            Cancel
          </Button>
          <Button onClick={handleAddManagerRow} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default StateDetailGrid;