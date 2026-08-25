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

    // ── バージョン(Base) ──
    // SystemData/PlayerDataそれぞれが持つ「セーブデータのバージョン」。
    // Main.Sub.Details の3つのint値の組み合わせで表す(整数のみ)。
    // 生成されるC#側では各SaveDataクラスにconstとして書き込まれる想定
    // (例: public const int VersionMain = 1; など)。
    // ロード時、実際のプログラム側のバージョン定数とここで書き込んだ値を比較し、
    // 「SaveData側の記録バージョンがプログラムより新しい(=ダウングレードして
    // 読み込もうとしている)」場合だけをエラーとして検知するために使う。
    const [version, setVersion] = useState({ main: 0, sub: 0, details: 0 });

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
            fetch('/api/class-data-id').then(res => res.json()),
            // CustomClassData / CustomClassDataID (bit・color・bezier対応版) も選択できるようにする
            fetch('/api/custom-class-data-type-options').then(res => res.json())
        ]).then(([enumList, classList, classIDList, customOptions]) => {
            const enumTypes = enumList.map(item => item.name);
            const classTypes = classList.map(item => item.name);
            const classIDTypes = classIDList.map(item => item.name);
            const customClassTypes = customOptions.custom_class_list || [];
            const customClassIDTypes = customOptions.custom_class_id_list || [];
            // Save は BinaryFormatter でオブジェクトごとシリアライズするため、
            // UnityEngine.AnimationCurve(bezier) は非対応(BinaryFormatterでは
            // シリアライズできない型のため)。bit/color はどちらもC#側で
            // [Serializable] 付きの型に解決されるので問題なく使える。
            const customValueTypes = (customOptions.custom_types || []).filter(t => t !== 'bezier');
            setTypeOptions([
                ...basicTypes, ...unityTypes,
                ...enumTypes, ...classTypes, ...classIDTypes,
                ...customClassTypes, ...customClassIDTypes, ...customValueTypes
            ]);
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
                // 後方互換: 旧形式(配列そのまま)と新形式({version, fields})の両方を許容する
                const isNewFormat = !Array.isArray(fetchedData) && fetchedData && Array.isArray(fetchedData.fields);
                const fields = isNewFormat ? fetchedData.fields : (Array.isArray(fetchedData) ? fetchedData : []);
                const ver = isNewFormat && fetchedData.version ? fetchedData.version : { main: 0, sub: 0, details: 0 };
                setVersion({
                    main: parseInt(ver.main, 10) || 0,
                    sub: parseInt(ver.sub, 10) || 0,
                    details: parseInt(ver.details, 10) || 0,
                });
                // Ensure data has IDs for DataGrid
                setData(fields.map((item, index) => ({ ...item, id: item.id || index + 1 })));
                setLoading(false);
            })
            .catch(error => {
                console.error(`Error fetching ${name}:`, error);
                setData([]); // Clear data on error or new file
                setVersion({ main: 0, sub: 0, details: 0 });
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

    const handleVersionChange = (field) => (e) => {
        // 整数のみ許可(空文字は一旦許容し、blur時等に0扱いにする)
        const raw = e.target.value;
        if (raw !== '' && !/^-?\d+$/.test(raw)) return;
        setVersion(prev => ({ ...prev, [field]: raw === '' ? '' : parseInt(raw, 10) }));
    };

    const handleSave = () => {
        const normalizedVersion = {
            main: parseInt(version.main, 10) || 0,
            sub: parseInt(version.sub, 10) || 0,
            details: parseInt(version.details, 10) || 0,
        };
        fetch(`/api/save-data/${currentDataName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version: normalizedVersion, fields: data }),
        })
            .then(response => response.json())
            .then(result => alert(result.message))
            .catch(error => alert('Error saving data: ' + error));
    };

    const handleGenerateCs = () => {
        const normalizedVersion = {
            main: parseInt(version.main, 10) || 0,
            sub: parseInt(version.sub, 10) || 0,
            details: parseInt(version.details, 10) || 0,
        };
        fetch(`/api/generate-save-data/${currentDataName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version: normalizedVersion, fields: data }), // Send current data to be safe, though server could read from file
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

            {/* ── Base: バージョン(Main.Sub.Details / int×3) ── */}
            <Box sx={{
                mb: 2, p: 1.5, border: '1px solid rgba(0,0,0,0.12)', borderRadius: 1,
                display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap',
            }}>
                <Typography variant="subtitle2" sx={{ mr: 1 }}>
                    {currentDataName} バージョン (Base / const)
                </Typography>
                <TextField
                    label="Main" size="small" sx={{ width: 90 }}
                    value={version.main}
                    onChange={handleVersionChange('main')}
                    inputProps={{ inputMode: 'numeric', pattern: '-?[0-9]*' }}
                />
                <Typography>.</Typography>
                <TextField
                    label="Sub" size="small" sx={{ width: 90 }}
                    value={version.sub}
                    onChange={handleVersionChange('sub')}
                    inputProps={{ inputMode: 'numeric', pattern: '-?[0-9]*' }}
                />
                <Typography>.</Typography>
                <TextField
                    label="Details" size="small" sx={{ width: 90 }}
                    value={version.details}
                    onChange={handleVersionChange('details')}
                    inputProps={{ inputMode: 'numeric', pattern: '-?[0-9]*' }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ width: '100%' }}>
                    「Save JSON」または「Create/Generate C#」で、{currentDataName}側にconstのバージョン値として書き込まれます。
                    ロード時にプログラム側のバージョンより新しい(セーブデータの方が上)場合は
                    ダウングレード扱いとしてエラーになり、逆にプログラム側の方が新しい場合はセーブ側のバージョンを
                    プログラムのバージョンで上書きします。
                </Typography>
            </Box>

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