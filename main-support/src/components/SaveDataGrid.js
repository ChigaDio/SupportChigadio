import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, Tabs, Tab } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import SaveIcon from '@mui/icons-material/Save';
import CodeIcon from '@mui/icons-material/Code';

function SaveDataGrid() {
    const [activeTab, setActiveTab] = useState(0); // 0: SystemData, 1: PlayerData
    const [data, setData] = useState([]);
    const [typeOptions, setTypeOptions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);

    // New field state
    const [newType, setNewType] = useState('');
    const [newName, setNewName] = useState('');
    const [newDescription, setNewDescription] = useState('');
    const [newArraySize, setNewArraySize] = useState(0);

    const currentDataName = activeTab === 0 ? 'SystemData' : 'PlayerData';

    useEffect(() => {
        fetchTypeOptions();
    }, []);

    useEffect(() => {
        fetchData(currentDataName);
    }, [currentDataName]);

    const fetchTypeOptions = () => {
        const basicTypes = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object'];
        const unityTypes = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject'];

        Promise.all([
            fetch('/api/enum-id').then(res => res.json()),
            fetch('/api/class-data').then(res => res.json()),
            fetch('/api/class-data-id').then(res => res.json())
        ]).then(([enumList, classList, classIDList]) => {
            const enumTypes = enumList.map(item => item.name);
            const classTypes = classList.map(item => item.name);
            const classIDTypes = classIDList.map(item => item.name);
            setTypeOptions([...basicTypes, ...unityTypes, ...enumTypes, ...classTypes, ...classIDTypes]);
        }).catch(error => console.error('Error fetching type options:', error));
    };

    const fetchData = (name) => {
        setLoading(true);
        fetch(`/api/save-data/${name}`)
            .then(response => {
                if (!response.ok) throw new Error(response.statusText);
                return response.json();
            })
            .then(fetchedData => {
                // Ensure data has IDs for DataGrid
                setData(fetchedData.map((item, index) => ({ ...item, id: item.id || index + 1 })));
                setLoading(false);
            })
            .catch(error => {
                console.error(`Error fetching ${name}:`, error);
                setData([]); // Clear data on error or new file
                setLoading(false);
            });
    };

    const handleTabChange = (event, newValue) => {
        setActiveTab(newValue);
    };

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
        // Reset form
        setNewType('');
        setNewName('');
        setNewDescription('');
        setNewArraySize(0);
    };

    const handleDeleteRow = (id) => {
        setData(data.filter(item => item.id !== id));
    };

    const handleRowOrderChange = (params) => {
        const { oldIndex, targetIndex } = params;
        const newData = [...data];
        const [movedRow] = newData.splice(oldIndex, 1);
        newData.splice(targetIndex, 0, movedRow);
        setData(newData);
    };

    const handleSave = () => {
        fetch(`/api/save-data/${currentDataName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        })
            .then(response => response.json())
            .then(result => alert(result.message))
            .catch(error => alert('Error saving data: ' + error));
    };

    const handleGenerateCs = () => {
        fetch(`/api/generate-save-data/${currentDataName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data), // Send current data to be safe, though server could read from file
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
        { field: 'name', headerName: 'Name', width: 200, editable: true },
        { field: 'description', headerName: 'Description', width: 300, editable: true },
        { field: 'arraySize', headerName: 'ArraySize', width: 100, editable: true, type: 'number' },
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
                Save Data Settings
            </Typography>

            <Tabs value={activeTab} onChange={handleTabChange} aria-label="save data tabs" sx={{ mb: 2 }}>
                <Tab label="SystemData" />
                <Tab label="PlayerData" />
            </Tabs>

            <Box sx={{ mb: 2 }}>
                <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setOpen(true)} sx={{ mr: 1 }}>
                    Add Variable
                </Button>
                <Button variant="contained" color="primary" startIcon={<SaveIcon />} onClick={handleSave} sx={{ mr: 1 }}>
                    Save JSON
                </Button>
                <Button variant="contained" color="secondary" startIcon={<CodeIcon />} onClick={handleGenerateCs} sx={{ mr: 1 }}>
                    Create/Generate C#
                </Button>
            </Box>

            {loading ? (
                <Typography>Loading...</Typography>
            ) : (
                <div style={{ height: 600, width: '100%' }}>
                    <DataGrid
                        rows={data}
                        columns={columns}
                        pageSizeOptions={[10, 25]}
                        getRowId={(row) => row.id}
                        rowReordering
                        onRowOrderChange={handleRowOrderChange}
                        autoHeight
                    />
                </div>
            )}

            <Dialog open={open} onClose={() => setOpen(false)}>
                <DialogTitle>Add New Variable to {currentDataName}</DialogTitle>
                <DialogContent>
                    <Autocomplete
                        freeSolo
                        options={typeOptions}
                        renderInput={(params) => <TextField {...params} label="Type" margin="dense" fullWidth />}
                        value={newType}
                        onChange={(e, newValue) => setNewType(newValue)}
                    />
                    <TextField label="Name" margin="dense" fullWidth value={newName} onChange={(e) => setNewName(e.target.value)} />
                    <TextField label="Description" margin="dense" fullWidth value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
                    <TextField label="Array Size (0 for single)" margin="dense" fullWidth type="number" value={newArraySize} onChange={(e) => setNewArraySize(e.target.value)} />
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpen(false)}>Cancel</Button>
                    <Button onClick={handleAddRow}>Add</Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
}

export default SaveDataGrid;
