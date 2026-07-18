import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  Autocomplete, Select, MenuItem, FormControl, InputLabel, Checkbox, FormControlLabel,
  Chip, Divider, IconButton
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';

const CUSTOM_TYPES = ['bit', 'color', 'bezier'];
const NUMERIC_TYPES = ['int', 'float', 'double', 'byte', 'short', 'long', 'decimal', 'uint'];

// ============================================================
// オプション編集: 数値型 min/max
// ============================================================
function NumericOptionsEditor({ options, onChange }) {
  return (
    <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
      <TextField
        label="最小値" type="number" size="small"
        value={options.min ?? ''}
        onChange={(e) => onChange({ ...options, min: e.target.value === '' ? null : Number(e.target.value) })}
      />
      <TextField
        label="最大値" type="number" size="small"
        value={options.max ?? ''}
        onChange={(e) => onChange({ ...options, max: e.target.value === '' ? null : Number(e.target.value) })}
      />
    </Box>
  );
}

// ============================================================
// オプション編集: bit (チェックボックス on/off, single/multiple, select-all)
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
          <Select
            label="ビット数の決め方"
            value={sizeMode}
            onChange={(e) => onChange({ ...options, sizeMode: e.target.value, sizeSourceName: null })}
          >
            <MenuItem value="manual">手動指定</MenuItem>
            <MenuItem value="enum">Enumの要素数から</MenuItem>
            <MenuItem value="classDataId">ClassDataIDの要素数から</MenuItem>
            <MenuItem value="customClassDataId">CustomClassDataIDの要素数から</MenuItem>
          </Select>
        </FormControl>

        {sizeMode === 'manual' ? (
          <TextField
            label="ビット数" type="number" size="small"
            value={size}
            onChange={(e) => {
              const n = Math.max(1, Number(e.target.value) || 1);
              const nextFlags = Array.from({ length: n }, (_, i) => flagNames[i] || `Flag${i}`);
              onChange({ ...options, size: n, flagNames: nextFlags });
            }}
          />
        ) : (
          <Autocomplete
            size="small"
            sx={{ minWidth: 220 }}
            options={sourceNames}
            value={options.sizeSourceName || null}
            onChange={(e, v) => onChange({ ...options, sizeSourceName: v })}
            renderInput={(params) => <TextField {...params} label="参照元" />}
          />
        )}

        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>選択モード</InputLabel>
          <Select
            label="選択モード"
            value={options.mode || 'multiple'}
            onChange={(e) => onChange({ ...options, mode: e.target.value })}
          >
            <MenuItem value="multiple">複数選択可</MenuItem>
            <MenuItem value="single">1つだけ選択（排他）</MenuItem>
          </Select>
        </FormControl>

        {options.mode !== 'single' && (
          <FormControlLabel
            control={
              <Checkbox
                checked={!!options.allowSelectAll}
                onChange={(e) => onChange({ ...options, allowSelectAll: e.target.checked })}
              />
            }
            label="全選択ボタンを許可"
          />
        )}
      </Box>

      {sizeMode === 'manual' && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">フラグ名（各ビットのラベル）</Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 0.5 }}>
            {flagNames.map((name, i) => (
              <TextField
                key={i}
                size="small"
                label={`bit ${i}`}
                value={name}
                onChange={(e) => setFlagName(i, e.target.value)}
                sx={{ width: 130 }}
              />
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
        <Select
          label="値の型"
          value={options.valueType || 'float'}
          onChange={(e) => onChange({ ...options, valueType: e.target.value })}
        >
          <MenuItem value="float">float</MenuItem>
          <MenuItem value="int">int</MenuItem>
        </Select>
      </FormControl>
      <TextField
        label="グラフの最小値" type="number" size="small"
        value={options.min ?? 0}
        onChange={(e) => onChange({ ...options, min: Number(e.target.value) })}
      />
      <TextField
        label="グラフの最大値" type="number" size="small"
        value={options.max ?? 1}
        onChange={(e) => onChange({ ...options, max: Number(e.target.value) })}
      />
    </Box>
  );
}

function defaultOptionsForType(type) {
  if (NUMERIC_TYPES.includes(type)) return { min: null, max: null };
  if (type === 'bit') return { sizeMode: 'manual', sizeSourceName: null, size: 8, mode: 'multiple', allowSelectAll: true, flagNames: Array.from({ length: 8 }, (_, i) => `Flag${i}`) };
  if (type === 'color') return {};
  if (type === 'bezier') return { valueType: 'float', min: 0, max: 1 };
  return {};
}

function optionsSummary(field) {
  const t = field.type;
  const o = field.options || {};
  if (NUMERIC_TYPES.includes(t)) {
    if (o.min == null && o.max == null) return '範囲指定なし';
    return `範囲 [${o.min ?? '-∞'} , ${o.max ?? '∞'}]`;
  }
  if (t === 'bit') {
    const modeLabel = o.mode === 'single' ? '排他選択' : '複数選択' + (o.allowSelectAll ? '+全選択' : '');
    return `${o.size ?? '?'}bit / ${modeLabel}`;
  }
  if (t === 'color') return 'RGBA';
  if (t === 'bezier') return `ベジェ(${o.valueType || 'float'}) [${o.min ?? 0}, ${o.max ?? 1}]`;
  return '-';
}

// ============================================================
// メインコンポーネント
// ============================================================
function CustomClassDataDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typeInfo, setTypeInfo] = useState({
    basic_types: [], unity_types: [], custom_types: CUSTOM_TYPES,
    enum_list: [], class_list: [], class_data_id_list: [], custom_class_list: [], custom_class_id_list: [],
  });

  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formType, setFormType] = useState('');
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formArraySize, setFormArraySize] = useState(0);
  const [formOptions, setFormOptions] = useState({});

  useEffect(() => {
    fetch(`/api/custom-class-data/${encodeURIComponent(name)}`)
      .then(response => response.json())
      .then(data => {
        setFields((Array.isArray(data) ? data : []).map((f, i) => ({ ...f, id: f.id || i + 1 })));
        setLoading(false);
      })
      .catch(error => {
        console.error('CustomClassData取得エラー:', error);
        setLoading(false);
      });

    fetch('/api/custom-class-data-type-options')
      .then(res => res.json())
      .then(info => setTypeInfo(info))
      .catch(error => console.error('型情報取得エラー:', error));
  }, [name]);

  const typeOptions = useMemo(() => {
    const list = [
      ...typeInfo.basic_types,
      ...typeInfo.unity_types,
      ...typeInfo.custom_types,
      ...typeInfo.enum_list,
      ...typeInfo.class_list,
      ...typeInfo.class_data_id_list,
      ...typeInfo.custom_class_list.filter(n => n !== name), // 自己参照は除外
    ];
    return Array.from(new Set(list));
  }, [typeInfo, name]);

  const openAddDialog = () => {
    setEditingId(null);
    setFormType('');
    setFormName('');
    setFormDescription('');
    setFormArraySize(0);
    setFormOptions({});
    setOpen(true);
  };

  const openEditDialog = (field) => {
    setEditingId(field.id);
    setFormType(field.type);
    setFormName(field.name);
    setFormDescription(field.description || '');
    setFormArraySize(field.arraySize || 0);
    setFormOptions(field.options || defaultOptionsForType(field.type));
    setOpen(true);
  };

  const handleTypeChange = (newType) => {
    setFormType(newType || '');
    setFormOptions(defaultOptionsForType(newType || ''));
  };

  const handleSaveField = () => {
    if (!formType.trim() || !formName.trim()) {
      alert('型と名前は必須です');
      return;
    }
    if (editingId) {
      setFields(fields.map(f => f.id === editingId
        ? { ...f, type: formType, name: formName, description: formDescription, arraySize: Number(formArraySize) || 0, options: formOptions }
        : f));
    } else {
      const maxId = Math.max(0, ...fields.map(f => f.id));
      setFields([...fields, {
        id: maxId + 1, type: formType, name: formName, description: formDescription,
        arraySize: Number(formArraySize) || 0, options: formOptions,
      }]);
    }
    setOpen(false);
  };

  const handleDeleteField = (id) => {
    setFields(fields.filter(f => f.id !== id));
  };

  const handleSave = () => {
    fetch(`/api/custom-class-data/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    })
      .then(response => response.json())
      .then(result => alert(result.message || result.error))
      .catch(error => alert('保存エラー: ' + error.message));
  };

  const handleDelete = () => {
    if (window.confirm(`CustomClassData ${name} を削除しますか？`)) {
      fetch(`/api/custom-class-data/${encodeURIComponent(name)}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          navigate('/custom-class-data');
        })
        .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  const handleGenerateCs = () => {
    fetch(`/api/generate-custom-class/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    })
      .then(response => response.json())
      .then(result => alert(result.message || result.error))
      .catch(error => alert('C#生成エラー: ' + error.message));
  };

  const columns = [
    { field: 'type', headerName: 'Type', width: 150 },
    { field: 'name', headerName: 'Name', width: 150 },
    { field: 'description', headerName: 'Description', width: 200 },
    { field: 'arraySize', headerName: 'ArraySize', width: 100 },
    {
      field: 'options', headerName: 'オプション', width: 260,
      renderCell: (params) => <Chip size="small" label={optionsSummary(params.row)} />,
    },
    {
      field: 'actions', headerName: 'Actions', width: 160,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" variant="outlined" onClick={() => openEditDialog(params.row)}>編集</Button>
          <Button size="small" variant="contained" color="error" onClick={() => handleDeleteField(params.row.id)}>削除</Button>
        </Box>
      ),
    },
  ];

  const isNumeric = NUMERIC_TYPES.includes(formType);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        CustomClassData詳細: {name}
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={openAddDialog} sx={{ mr: 1 }}>
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
        <Typography>Loading...</Typography>
      ) : (
        <div style={{ height: 460, width: '100%' }}>
          <DataGrid rows={fields} columns={columns} pageSizeOptions={[5]} getRowId={(row) => row.id} />
        </div>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingId ? '変数を編集' : '新しい変数を追加'}</DialogTitle>
        <DialogContent>
          <Autocomplete
            freeSolo
            options={typeOptions}
            value={formType}
            onChange={(e, v) => handleTypeChange(v)}
            onInputChange={(e, v, reason) => { if (reason === 'input') handleTypeChange(v); }}
            renderInput={(params) => <TextField {...params} label="変数の型" margin="dense" fullWidth />}
          />
          <TextField label="変数名" margin="dense" fullWidth value={formName} onChange={(e) => setFormName(e.target.value)} />
          <TextField label="説明" margin="dense" fullWidth value={formDescription} onChange={(e) => setFormDescription(e.target.value)} />
          <TextField
            label="配列サイズ（0=単一, -1=可変長List, N>0=固定長配列）"
            margin="dense" fullWidth type="number"
            value={formArraySize}
            onChange={(e) => setFormArraySize(e.target.value)}
          />

          {(isNumeric || CUSTOM_TYPES.includes(formType)) && (
            <>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2">型オプション</Typography>
              {isNumeric && <NumericOptionsEditor options={formOptions} onChange={setFormOptions} />}
              {formType === 'bit' && (
                <BitOptionsEditor
                  options={formOptions}
                  onChange={setFormOptions}
                  enumNames={typeInfo.enum_list}
                  classDataIdNames={typeInfo.class_data_id_list}
                  customClassDataIdNames={typeInfo.custom_class_id_list}
                />
              )}
              {formType === 'color' && (
                <Typography variant="caption" color="text.secondary">
                  RGBAカラー型です。実際の色の値はCustomClassDataID側の各レコードで設定します。
                </Typography>
              )}
              {formType === 'bezier' && (
                <BezierOptionsEditor options={formOptions} onChange={setFormOptions} />
              )}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>キャンセル</Button>
          <Button onClick={handleSaveField}>{editingId ? '更新' : '追加'}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default CustomClassDataDetailGrid;
