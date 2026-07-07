import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent,
  DialogActions, Select, MenuItem, FormControl, InputLabel
} from '@mui/material';

// 対応する定数型
const CONST_TYPES = ['int', 'uint', 'float', 'vector2', 'vector3', 'string'];

// 型ごとのデフォルト値
function getDefaultValue(type) {
  switch (type) {
    case 'int':
    case 'uint':
      return '0';
    case 'float':
      return '0';
    case 'vector2':
      return ['0', '0'];
    case 'vector3':
      return ['0', '0', '0'];
    case 'string':
    default:
      return '';
  }
}

// 数値のみ許容（int/uint/float用）。あいうえお等の文字列は弾く。
const INT_REGEX = /^-?\d+$/;
const UINT_REGEX = /^\d+$/;
const FLOAT_REGEX = /^-?\d+(\.\d+)?$/;

function isValidNumberForType(type, value) {
  if (value === '' || value === null || value === undefined) return false;
  switch (type) {
    case 'int':
      return INT_REGEX.test(String(value).trim());
    case 'uint':
      return UINT_REGEX.test(String(value).trim());
    case 'float':
      return FLOAT_REGEX.test(String(value).trim());
    default:
      return true;
  }
}

// 定数値全体のバリデーション
function validateValue(type, value) {
  switch (type) {
    case 'int':
    case 'uint':
    case 'float':
      return isValidNumberForType(type, value);
    case 'vector2':
      return Array.isArray(value) && value.length === 2 &&
        value.every(v => isValidNumberForType('float', v));
    case 'vector3':
      return Array.isArray(value) && value.length === 3 &&
        value.every(v => isValidNumberForType('float', v));
    case 'string':
      return typeof value === 'string';
    default:
      return false;
  }
}

// 値の表示用フォーマット
function formatValueForDisplay(type, value) {
  if (type === 'vector2' || type === 'vector3') {
    return `(${(Array.isArray(value) ? value : []).join(', ')})`;
  }
  return String(value);
}

// ============================================================
// 値入力コンポーネント（型に応じて切り替え）
// ============================================================
function ValueInput({ type, value, onChange }) {
  if (type === 'vector2' || type === 'vector3') {
    const arr = Array.isArray(value) ? value : getDefaultValue(type);
    const labels = type === 'vector2' ? ['x', 'y'] : ['x', 'y', 'z'];
    return (
      <Box sx={{ display: 'flex', gap: 1 }}>
        {labels.map((label, idx) => (
          <TextField
            key={label}
            label={label}
            size="small"
            value={arr[idx] ?? '0'}
            error={!isValidNumberForType('float', arr[idx])}
            helperText={!isValidNumberForType('float', arr[idx]) ? '数値のみ' : ''}
            onChange={(e) => {
              const next = [...arr];
              next[idx] = e.target.value;
              onChange(next);
            }}
          />
        ))}
      </Box>
    );
  }

  if (type === 'string') {
    return (
      <TextField
        label="値"
        fullWidth
        size="small"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  // int / uint / float
  const invalid = !isValidNumberForType(type, value);
  return (
    <TextField
      label="値"
      fullWidth
      size="small"
      value={value ?? ''}
      error={invalid}
      helperText={invalid ? '数値のみ入力できます（あいうえお等の文字は不可）' : ''}
      onChange={(e) => {
        const v = e.target.value;
        // 入力段階でも数値以外の文字は弾く（uintは負号・小数点も不可、intは小数点不可、floatは整数/小数のみ）
        let pattern;
        if (type === 'int') pattern = /^-?\d*$/;
        else if (type === 'uint') pattern = /^\d*$/;
        else pattern = /^-?\d*\.?\d*$/; // float
        if (v === '' || pattern.test(v)) {
          onChange(v);
        }
      }}
    />
  );
}

// ============================================================
// メインコンポーネント
// ============================================================
function ConstClassDataDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [constants, setConstants] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formType, setFormType] = useState('int');
  const [formName, setFormName] = useState('');
  const [fromComment, setFromComment] = useState('');
  const [formValue, setFormValue] = useState(getDefaultValue('int'));

  useEffect(() => {
    fetch(`/api/const-class-data/${encodeURIComponent(name)}`)
      .then(res => {
        if (!res.ok) throw new Error(`定数データ取得に失敗: ${res.status}`);
        return res.json();
      })
      .then(data => setConstants(data.constants || []))
      .catch(error => {
        console.error('定数データ取得エラー:', error);
        alert('データ取得エラー: ' + error.message);
      });
  }, [name]);

  const openCreateDialog = () => {
    setEditingId(null);
    setFormType('int');
    setFormName('');
    setFromComment('');
    setFormValue(getDefaultValue('int'));
    setOpenDialog(true);
  };

  const openEditDialog = (row) => {
    setEditingId(row.id);
    setFormType(row.type);
    setFormName(row.name);
    setFromComment(row.comment || '');
    setFormValue(row.value);
    setOpenDialog(true);
  };

  const handleTypeChange = (newType) => {
    setFormType(newType);
    setFormValue(getDefaultValue(newType));
  };

  const handleSaveRow = () => {
    if (!formName.trim()) {
      alert('定数名は必須です');
      return;
    }
    if (/[^A-Za-z0-9_]/.test(formName)) {
      alert('定数名は英数字とアンダースコアのみ使用できます');
      return;
    }
    if (!validateValue(formType, formValue)) {
      alert('値の形式が正しくありません（数値のみ入力してください）');
      return;
    }
    const isDuplicate = constants.some(c => c.name === formName && c.id !== editingId);
    if (isDuplicate) {
      alert(`定数名 ${formName} はすでに存在します`);
      return;
    }
    if(!fromComment.trim()) {
      alert('コメントは必須です');
      return;
    }

    if (editingId != null) {
      setConstants(constants.map(c => c.id === editingId
        ? { ...c, comment: fromComment, type: formType, name: formName, value: formValue }
        : c));
    } else {
      const maxId = Math.max(0, ...constants.map(c => c.id));
      setConstants([...constants, { id: maxId + 1, comment: fromComment, type: formType, name: formName, value: formValue }]);
    }
    setOpenDialog(false);
  };

  const handleDeleteRow = (id) => {
    if (window.confirm('この定数を削除しますか？')) {
      setConstants(constants.filter(c => c.id !== id));
    }
  };

  const handleSave = () => {
    fetch(`/api/const-class-data/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ constants }),
    })
      .then(res => res.json())
      .then(result => alert(result.message))
      .catch(error => alert('保存エラー: ' + error.message));
  };

  const handleGenerate = () => {
    fetch(`/api/generate-const-class/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ constants }),
    })
      .then(res => res.json())
      .then(result => alert(result.message))
      .catch(error => alert('生成エラー: ' + error.message));
  };

  const columns = [
    { field: 'name', headerName: '定数名', width: 200 },
    { field: 'comment', headerName: 'コメント', width: 200 },
    { field: 'type', headerName: '型', width: 100 },
    {
      field: 'value',
      headerName: '値',
      width: 220,
      renderCell: (params) => formatValueForDisplay(params.row.type, params.row.value),
    },
    {
      field: 'actions',
      headerName: '操作',
      width: 160,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" variant="outlined" onClick={() => openEditDialog(params.row)}>
            編集
          </Button>
          <Button size="small" variant="contained" color="error" onClick={() => handleDeleteRow(params.row.id)}>
            削除
          </Button>
        </Box>
      ),
    },
  ];

  return (
    <div style={{ padding: '20px' }}>
      <Typography variant="h5" sx={{ mb: 2 }}>ConstClassData: {name}</Typography>
      <Button variant="text" onClick={() => navigate('/const-class-data')} sx={{ mb: 2 }}>
        &larr; 一覧へ戻る
      </Button>
      <Box sx={{ mb: 2, display: 'flex', gap: 2 }}>
        <Button variant="contained" color="primary" onClick={openCreateDialog}>
          定数を追加
        </Button>
        <Button variant="contained" color="success" onClick={handleSave}>
          保存
        </Button>
        <Button variant="contained" color="secondary" onClick={handleGenerate}>
          C#生成（static class）
        </Button>
      </Box>
      <div style={{ height: 450, width: '100%' }}>
        <DataGrid
          rows={constants}
          columns={columns}
          pageSizeOptions={[10]}
          getRowId={(row) => row.id}
        />
      </div>

      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} fullWidth maxWidth="xs">
        <DialogTitle>{editingId != null ? '定数を編集' : '定数を追加'}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          <FormControl fullWidth size="small">
            <InputLabel>型</InputLabel>
            <Select
              label="型"
              value={formType}
              onChange={(e) => handleTypeChange(e.target.value)}
            >
              {CONST_TYPES.map(t => (
                <MenuItem key={t} value={t}>{t}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label="定数名"
            fullWidth
            size="small"
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
          />
          <TextField
            label="コメント"
            fullWidth
            size="small"
            value={fromComment}
            onChange={(e) => setFromComment(e.target.value)}
          />
          <ValueInput type={formType} value={formValue} onChange={setFormValue} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>キャンセル</Button>
          <Button onClick={handleSaveRow}>{editingId != null ? '更新' : '追加'}</Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}

export default ConstClassDataDetailGrid;
