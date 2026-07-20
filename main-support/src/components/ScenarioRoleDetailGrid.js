import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete,
  Select, MenuItem, FormControl, InputLabel, Checkbox, FormControlLabel
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';

// bit の初期オプション
function defaultOptionsForType(type) {
  if (type === 'bit') return { sizeMode: 'manual', sizeSourceName: null, size: 8, mode: 'multiple', allowSelectAll: true, flagNames: Array.from({ length: 8 }, (_, i) => `Flag${i}`) };
  if (type === 'bezier') return { valueType: 'float', min: 0, max: 1 };
  return {};
}

// ============================================================
// オプション編集: bit (CustomClassDataDetailGridの編集UIを流用した簡易版)
// ============================================================
function BitOptionsEditor({ options, onChange, enumNames, classDataIdNames, customClassDataIdNames }) {
  const sizeMode = options.sizeMode || 'manual';
  const sourceNames = sizeMode === 'enum' ? enumNames
    : sizeMode === 'classDataId' ? classDataIdNames
    : sizeMode === 'customClassDataId' ? customClassDataIdNames
    : [];
  const flagNames = options.flagNames || [];
  const size = options.size ?? flagNames.length ?? 8;

  const setFlagName = (index, value) => {
    const next = [...flagNames];
    next[index] = value;
    onChange({ ...options, flagNames: next });
  };

  return (
    <Box sx={{ mt: 1 }}>
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>ビット数の決め方</InputLabel>
          <Select label="ビット数の決め方" value={sizeMode}
            onChange={(e) => onChange({ ...options, sizeMode: e.target.value, sizeSourceName: null })}>
            <MenuItem value="manual">手動指定</MenuItem>
            <MenuItem value="enum">Enumの要素数から</MenuItem>
            <MenuItem value="classDataId">ClassDataIDの要素数から</MenuItem>
            <MenuItem value="customClassDataId">CustomClassDataIDの要素数から</MenuItem>
          </Select>
        </FormControl>

        {sizeMode === 'manual' ? (
          <TextField
            label="ビット数" type="number" size="small" value={size}
            onChange={(e) => {
              const n = Math.max(1, Number(e.target.value) || 1);
              const nextFlags = Array.from({ length: n }, (_, i) => flagNames[i] || `Flag${i}`);
              onChange({ ...options, size: n, flagNames: nextFlags });
            }}
          />
        ) : (
          <Autocomplete
            size="small" sx={{ minWidth: 220 }} options={sourceNames}
            value={options.sizeSourceName || null}
            onChange={(e, v) => onChange({ ...options, sizeSourceName: v })}
            renderInput={(params) => <TextField {...params} label="参照元" />}
          />
        )}

        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>選択モード</InputLabel>
          <Select label="選択モード" value={options.mode || 'multiple'}
            onChange={(e) => onChange({ ...options, mode: e.target.value })}>
            <MenuItem value="multiple">複数選択可</MenuItem>
            <MenuItem value="single">1つだけ選択（排他）</MenuItem>
          </Select>
        </FormControl>

        {options.mode !== 'single' && (
          <FormControlLabel
            control={<Checkbox checked={!!options.allowSelectAll} onChange={(e) => onChange({ ...options, allowSelectAll: e.target.checked })} />}
            label="全選択ボタンを許可"
          />
        )}
      </Box>

      {sizeMode === 'manual' && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">フラグ名（各ビットのラベル）</Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 0.5 }}>
            {flagNames.map((n, i) => (
              <TextField key={i} size="small" label={`bit ${i}`} value={n} onChange={(e) => setFlagName(i, e.target.value)} sx={{ width: 130 }} />
            ))}
          </Box>
        </Box>
      )}
      {sizeMode !== 'manual' && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          ※ 参照元を選択して保存すると、要素数からビット数・フラグ名が自動生成されます
        </Typography>
      )}
    </Box>
  );
}

// ============================================================
// オプション編集: bezier
// ============================================================
function BezierOptionsEditor({ options, onChange }) {
  return (
    <Box sx={{ display: 'flex', gap: 2, mt: 1, flexWrap: 'wrap' }}>
      <FormControl size="small" sx={{ minWidth: 120 }}>
        <InputLabel>値の型</InputLabel>
        <Select label="値の型" value={options.valueType || 'float'} onChange={(e) => onChange({ ...options, valueType: e.target.value })}>
          <MenuItem value="float">float</MenuItem>
          <MenuItem value="int">int</MenuItem>
        </Select>
      </FormControl>
      <TextField label="グラフの最小値" type="number" size="small" value={options.min ?? 0} onChange={(e) => onChange({ ...options, min: Number(e.target.value) })} />
      <TextField label="グラフの最大値" type="number" size="small" value={options.max ?? 1} onChange={(e) => onChange({ ...options, max: Number(e.target.value) })} />
    </Box>
  );
}

function ScenarioRoleDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [typeOptions, setTypeOptions] = useState([]);
  const [branchType, setBranchType] = useState('General');
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [newType, setNewType] = useState('');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newArraySize, setNewArraySize] = useState(0);
  const [newOptions, setNewOptions] = useState({});

  // bit の sizeMode="enum"/"classDataId"/"customClassDataId" 参照先候補
  const [enumNames, setEnumNames] = useState([]);
  const [classDataIdNames, setClassDataIdNames] = useState([]);
  const [customClassDataIdNames, setCustomClassDataIdNames] = useState([]);

  // 既存行のoptions編集用
  const [optionsEditRow, setOptionsEditRow] = useState(null); // { id, type, options }

  // Fetch data for the role
  useEffect(() => {
    fetch(`/api/scenario-role/${name}`)
      .then(response => response.json())
      .then(fetchedData => {
        setData(fetchedData.data.map((item, index) => ({ ...item, id: item.id || index + 1 })));
        setBranchType(fetchedData.branchType || 'General');
        setLoading(false);
      })
      .catch(error => {
        console.error('シナリオロールデータ取得エラー:', error);
        setLoading(false);
      });
  }, [name]);

  // Fetch type suggestions
  useEffect(() => {
    const basicTypes = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object'];
    const unityTypes = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject'];

    Promise.all([
      fetch('/api/enum-id').then(res => res.json()),
      fetch('/api/class-data').then(res => res.json()),
      fetch('/api/class-data-id').then(res => res.json()),
      // CustomClassData / CustomClassDataID (bit・color・bezier対応版) もロール変数の型として選択できるようにする
      fetch('/api/custom-class-data-type-options').then(res => res.json())
    ]).then(([enumList, classList, classIdList, customOptions]) => {
      const enumTypes = enumList.map(item => item.name);
      const classTypes = classList.map(item => item.name);
      const classIdTypes = classIdList.map(item => item.name);
      const customClassTypes = customOptions.custom_class_list || [];
      const customClassIdTypes = customOptions.custom_class_id_list || [];
      const customValueTypes = customOptions.custom_types || []; // ['bit', 'color', 'bezier']
      setTypeOptions([
        ...basicTypes, ...unityTypes,
        ...enumTypes, ...classTypes, ...classIdTypes,
        ...customClassTypes, ...customClassIdTypes, ...customValueTypes
      ]);
      setEnumNames(enumTypes);
      setClassDataIdNames(classIdTypes);
      setCustomClassDataIdNames(customClassIdTypes);
    }).catch(error => console.error('タイプオプション取得エラー:', error));
  }, []);

  // Add new row
  const handleAddRow = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('タイプと名前は必須です');
      return;
    }
    const maxId = Math.max(...data.map(item => item.id), 0) + 1;
    const newRow = {
      id: maxId,
      type: newType,
      name: newName,
      description: newDescription,
      arraySize: parseInt(newArraySize, 10) || 0,
      options: ['bit', 'bezier'].includes(newType) ? newOptions : undefined,
    };
    setData([...data, newRow]);
    setOpen(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
    setNewArraySize(0);
    setNewOptions({});
  };

  // 既存行のoptionsを保存(bit/bezier)
  const handleSaveRowOptions = () => {
    setData(data.map(item => (item.id === optionsEditRow.id ? { ...item, options: optionsEditRow.options } : item)));
    setOptionsEditRow(null);
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
    fetch(`/api/scenario-role/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data, branchType }),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('データ保存エラー: ' + error));
  };

  // Delete role
  const handleDelete = () => {
    if (window.confirm(`ロール ${name} を削除しますか？`)) {
      fetch(`/api/scenario-role/${name}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          navigate('/scenario-role');
        })
        .catch(error => alert('ロール削除エラー: ' + error));
    }
  };

  // Generate C#
  const handleGenerateCs = () => {
    fetch(`/api/generate-scenario-role/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data, branchType }),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('C#生成エラー: ' + error));
  };

  const columns = [
    {
      field: 'type',
      headerName: 'タイプ',
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
    { field: 'name', headerName: '名前', width: 150, editable: true },
    { field: 'description', headerName: '説明', width: 250, editable: true },
    { field: 'arraySize', headerName: '配列サイズ', width: 150, editable: true, type: 'number' },
    {
      field: 'options',
      headerName: 'オプション',
      width: 110,
      renderCell: (params) => (
        ['bit', 'bezier'].includes(params.row.type) ? (
          <Button
            size="small" startIcon={<EditIcon fontSize="small" />}
            onClick={() => setOptionsEditRow({ id: params.row.id, type: params.row.type, options: params.row.options || defaultOptionsForType(params.row.type) })}
          >
            編集
          </Button>
        ) : null
      )
    },
    {
      field: 'actions',
      headerName: 'アクション',
      width: 150,
      renderCell: (params) => (
        <Button variant="contained" color="error" size="small" onClick={() => handleDeleteRow(params.id)}>
          削除
        </Button>
      )
    }
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        シナリオロール詳細: {name}
      </Typography>
      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
        <Autocomplete
          options={['General', 'Branch']}
          value={branchType}
          onChange={(e, newValue) => setBranchType(newValue || 'General')}
          renderInput={(params) => <TextField {...params} label="ロールタイプ" sx={{ width: 200, mr: 2 }} />}
        />
        <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setOpen(true)} sx={{ mr: 1 }}>
          新しい変数を追加
        </Button>
        <Button variant="contained" color="primary" onClick={handleSave} sx={{ mr: 1 }}>
          保存
        </Button>
        <Button variant="contained" color="secondary" onClick={handleGenerateCs} sx={{ mr: 1 }}>
          C#を生成
        </Button>
        <Button variant="contained" color="error" onClick={handleDelete}>
          削除
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
            renderInput={(params) => <TextField {...params} label="タイプ" margin="dense" fullWidth />}
            value={newType}
            onChange={(e, newValue) => {
              setNewType(newValue);
              setNewOptions(['bit', 'bezier'].includes(newValue) ? defaultOptionsForType(newValue) : {});
            }}
          />
          <TextField label="名前" margin="dense" fullWidth value={newName} onChange={(e) => setNewName(e.target.value)} />
          <TextField label="説明" margin="dense" fullWidth value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
          <TextField label="配列サイズ" margin="dense" fullWidth type="number" value={newArraySize} onChange={(e) => setNewArraySize(e.target.value)} />
          {newType === 'bit' && (
            <BitOptionsEditor
              options={newOptions} onChange={setNewOptions}
              enumNames={enumNames} classDataIdNames={classDataIdNames} customClassDataIdNames={customClassDataIdNames}
            />
          )}
          {newType === 'bezier' && (
            <BezierOptionsEditor options={newOptions} onChange={setNewOptions} />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>キャンセル</Button>
          <Button onClick={handleAddRow}>追加</Button>
        </DialogActions>
      </Dialog>

      {/* 既存行(bit/bezier)のオプション編集 */}
      <Dialog open={!!optionsEditRow} onClose={() => setOptionsEditRow(null)} maxWidth="md" fullWidth>
        <DialogTitle>オプション編集</DialogTitle>
        <DialogContent>
          {optionsEditRow && optionsEditRow.type === 'bit' && (
            <BitOptionsEditor
              options={optionsEditRow.options}
              onChange={(opts) => setOptionsEditRow({ ...optionsEditRow, options: opts })}
              enumNames={enumNames} classDataIdNames={classDataIdNames} customClassDataIdNames={customClassDataIdNames}
            />
          )}
          {optionsEditRow && optionsEditRow.type === 'bezier' && (
            <BezierOptionsEditor
              options={optionsEditRow.options}
              onChange={(opts) => setOptionsEditRow({ ...optionsEditRow, options: opts })}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOptionsEditRow(null)}>キャンセル</Button>
          <Button onClick={handleSaveRowOptions}>保存</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ScenarioRoleDetailGrid;