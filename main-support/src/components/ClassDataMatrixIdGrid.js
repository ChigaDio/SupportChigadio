import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Autocomplete,
  Select, MenuItem, FormControl, Box, IconButton, Typography, Divider
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { useNavigate } from 'react-router-dom';
import OpenFileMenuButton from './OpenFileMenuButton';

const NO_TAG = '__none__';

function ClassDataMatrixIdGrid() {
  const [matrixData, setMatrixData] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [newName, setNewName] = useState('');
  const [newRowId, setNewRowId] = useState('');
  const [newColId, setNewColId] = useState('');
  const [typeOptions, setTypeOptions] = useState([]);
  const [tags, setTags] = useState([]); // [{id, name}]

  const [openTagDialog, setOpenTagDialog] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [editingTagId, setEditingTagId] = useState(null);
  const [editingTagName, setEditingTagName] = useState('');

  const navigate = useNavigate();

  useEffect(() => {
    fetchMatrixList();
    fetchTags();

    Promise.all([
      fetch('/api/enum-id').then(res => res.json()),
      fetch('/api/class-data-id').then(res => res.json()),
      fetch('/api/custom-class-data-id').then(res => res.ok ? res.json() : [])
    ])
      .then(([enumList, classIdList, customClassIdList]) => {
        setTypeOptions([
          ...enumList.map(item => item.name),
          ...classIdList.map(item => item.name),
          ...(Array.isArray(customClassIdList) ? customClassIdList.map(item => item.name) : []),
        ]);
      })
      .catch(error => console.error('オプション取得エラー:', error));
  }, []);

  const fetchMatrixList = () => {
    fetch('/api/class-data-matrix-id')
      .then(response => response.json())
      .then(data => setMatrixData(Array.isArray(data) ? data : []))
      .catch(error => console.error('データ取得エラー:', error));
  };

  const fetchTags = () => {
    fetch('/api/class-data-matrix-id-tags')
      .then(response => response.json())
      .then(data => setTags(Array.isArray(data) ? data : []))
      .catch(error => {
        console.error('タグ取得エラー:', error);
      });
  };

  const handleCreate = async () => {
    if (!newName || !newRowId || !newColId) {
      alert('名前、Row ID、Col IDは必須です');
      return;
    }
    try {
      // Enum / ClassDataID / CustomClassDataID のいずれであっても対応できるようにキーを解決する
      const resolveKeys = async (idName) => {
        // 1. Enum-ID
        const enumRes = await fetch(`/api/enum/${encodeURIComponent(idName)}`);
        if (enumRes.ok) {
          const enumData = await enumRes.json();
          if (Array.isArray(enumData) && enumData.length > 0) {
            return enumData.map(item => (typeof item === 'string' ? item : item.property));
          }
        }
        // 2. ClassDataID
        const classIdRes = await fetch(`/api/class-data-id/${encodeURIComponent(idName + 'ID')}`);
        if (classIdRes.ok) {
          const classIdData = await classIdRes.json();
          const rows = classIdData && classIdData.rows;
          if (Array.isArray(rows) && rows.length > 0) {
            return rows.map(row => row.enum_property);
          }
        }
        // 3. CustomClassDataID
        const customIdRes = await fetch(`/api/custom-class-data-id/${encodeURIComponent(idName)}`);
        if (customIdRes.ok) {
          const customIdData = await customIdRes.json();
          const rows = customIdData && customIdData.rows;
          if (Array.isArray(rows)) {
            return rows.map(row => row.enum_property);
          }
        }
        return [];
      };

      const [rowKeys, colKeys] = await Promise.all([
        resolveKeys(newRowId),
        resolveKeys(newColId)
      ]);

      // 初期データを作成
      const initialData = {};
      rowKeys.forEach(rk => {
        initialData[rk] = {};
        colKeys.forEach(ck => {
          initialData[rk][ck] = 0; // デフォルト値（int）
        });
      });

      const newMatrix = {
        name: newName,
        rowId: newRowId, // rowIdを追加
        colId: newColId, // colIdを追加
        fields: [{ type: 'int', name: 'value', description: 'Default Value' }],
        data: initialData
      };

      const response = await fetch('/api/class-data-matrix-id', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newMatrix)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '作成に失敗しました');
      setMatrixData([...matrixData, { ...result.data, rowId: newRowId, colId: newColId, tag: null }]);
      setOpenDialog(false);
      setNewName('');
      setNewRowId('');
      setNewColId('');
      alert('ClassDataMatrixIDが正常に作成されました');
    } catch (error) {
      alert('作成エラー: ' + error.message);
    }
  };

  const handleDelete = (name) => {
    if (window.confirm(`${name} を削除しますか？`)) {
      fetch('/api/class-data-matrix-id', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      })
        .then(response => response.json())
        .then(result => {
          setMatrixData(matrixData.filter(item => item.name !== name));
          alert('削除が正常に完了しました');
        })
        .catch(error => {
          alert('削除エラー: ' + error.message);
        });
    }
  };

  // --- タグ割り当て ---
  const handleTagChange = (rowName, tagValue) => {
    const tagToSave = tagValue === NO_TAG ? null : tagValue;
    fetch(`/api/class-data-matrix-id/${encodeURIComponent(rowName)}/tag`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tag: tagToSave }),
    })
      .then(response => {
        if (!response.ok) throw new Error('タグの更新に失敗');
        return response.json();
      })
      .then(() => {
        setMatrixData(matrixData.map(item =>
          item.name === rowName ? { ...item, tag: tagToSave } : item
        ));
      })
      .catch(error => alert('タグ更新エラー: ' + error.message));
  };

  // --- タグ管理（新規追加・編集・削除） ---
  const handleAddTag = () => {
    if (!newTagName.trim()) {
      alert('タグ名は必須です');
      return;
    }
    fetch('/api/class-data-matrix-id-tags', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newTagName }),
    })
      .then(response => {
        if (!response.ok) throw new Error('タグの作成に失敗');
        return response.json();
      })
      .then(result => {
        if (result.error) throw new Error(result.error);
        setTags([...tags, result.data]);
        setNewTagName('');
      })
      .catch(error => alert('タグ作成エラー: ' + error.message));
  };

  const startEditTag = (tag) => {
    setEditingTagId(tag.id);
    setEditingTagName(tag.name);
  };

  const handleRenameTag = (tag) => {
    if (!editingTagName.trim()) {
      alert('タグ名は必須です');
      return;
    }
    fetch(`/api/class-data-matrix-id-tags/${tag.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: editingTagName }),
    })
      .then(response => {
        if (!response.ok) throw new Error('タグの更新に失敗');
        return response.json();
      })
      .then(() => {
        setTags(tags.map(t => (t.id === tag.id ? { ...t, name: editingTagName } : t)));
        setMatrixData(matrixData.map(item =>
          item.tag === tag.name ? { ...item, tag: editingTagName } : item
        ));
        setEditingTagId(null);
        setEditingTagName('');
      })
      .catch(error => alert('タグ更新エラー: ' + error.message));
  };

  const handleDeleteTag = (tag) => {
    if (!window.confirm(`タグ「${tag.name}」を削除しますか？（割り当て済みのClassDataMatrixIDは未設定になります）`)) return;
    fetch('/api/class-data-matrix-id-tags', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: tag.name }),
    })
      .then(response => {
        if (!response.ok) throw new Error('タグの削除に失敗');
        return response.json();
      })
      .then(() => {
        setTags(tags.filter(t => t.id !== tag.id));
        setMatrixData(matrixData.map(item =>
          item.tag === tag.name ? { ...item, tag: null } : item
        ));
      })
      .catch(error => alert('タグ削除エラー: ' + error.message));
  };

  const columns = [
    {
      field: 'name',
      headerName: '名前',
      width: 150,
      renderCell: (params) => (
        <div style={{ cursor: 'pointer', color: '#1976d2' }} onClick={() => navigate(`/class-data-matrix-id/${params.value}`)}>
          {params.value}
        </div>
      )
    },
    { field: 'id', headerName: 'ID', width: 90 },
    { field: 'rowId', headerName: 'Row ID', width: 150 },
    { field: 'colId', headerName: 'Col ID', width: 150 },
    {
      field: 'tag',
      headerName: 'タグ',
      width: 180,
      renderCell: (params) => (
        <FormControl size="small" fullWidth>
          <Select
            value={params.row.tag || NO_TAG}
            onChange={(e) => handleTagChange(params.row.name, e.target.value)}
            displayEmpty
          >
            <MenuItem value={NO_TAG}>未設定</MenuItem>
            {tags.map(t => (
              <MenuItem key={t.id} value={t.name}>{t.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
      ),
    },
    {
      field: 'openInEditor',
      headerName: 'エディタ',
      width: 80,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <OpenFileMenuButton category="class_data_matrix_id" name={params.row.name} />
      ),
    },
    {
      field: 'actions',
      headerName: '操作',
      width: 100,
      renderCell: (params) => (
        <Button variant="contained" color="error" size="small" onClick={() => handleDelete(params.row.name)}>
          削除
        </Button>
      )
    }
  ];

  return (
    <div style={{ height: 500, width: '100%', padding: '20px' }}>
      <Button variant="contained" color="primary" onClick={() => setOpenDialog(true)} sx={{ mb: 2 }}>
        新しいClassDataMatrixIDを作成
      </Button>
      <Button
        variant="outlined"
        onClick={() => setOpenTagDialog(true)}
        sx={{ mb: 2, ml: 2 }}
      >
        タグ管理
      </Button>
      <Button
        variant="contained"
        color="secondary"
        onClick={() =>
          fetch('/api/generate-all-binary-matrix', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message || '全バイナリ生成が正常に完了しました'))
            .catch(error => alert('エラー: ' + error.message))
        }
        sx={{ mb: 2, ml: 2 }}
      >
        全バイナリ生成
      </Button>
      <Button
        variant="contained"
        color="secondary"
        onClick={() =>
          fetch('/api/generate-all-cs-matrix-header', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message || '全C#ヘッダー生成が正常に完了しました'))
            .catch(error => alert('エラー: ' + error.message))
        }
        sx={{ mb: 2, ml: 2 }}
      >
        全C#ヘッダー生成
      </Button>
      <Button
        variant="contained"
        color="secondary"
        onClick={() =>
          fetch('/api/generate-matrix-table-id', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message || 'MatrixTableID生成が正常に完了しました'))
            .catch(error => alert('エラー: ' + error.message))
        }
        sx={{ mb: 2, ml: 2 }}
      >
        MatrixTableID生成
      </Button>
      <DataGrid rows={matrixData} columns={columns} getRowId={(row) => row.id} />
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいClassDataMatrixIDを作成</DialogTitle>
        <DialogContent>
          <TextField label="名前" fullWidth value={newName} onChange={(e) => setNewName(e.target.value)} sx={{ mt: 2 }} />
          <Autocomplete options={typeOptions} value={newRowId} onChange={(e, v) => setNewRowId(v || '')} renderInput={(params) => <TextField {...params} label="Row ID" sx={{ mt: 2 }} />} />
          <Autocomplete options={typeOptions} value={newColId} onChange={(e, v) => setNewColId(v || '')} renderInput={(params) => <TextField {...params} label="Col ID" sx={{ mt: 2 }} />} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>キャンセル</Button>
          <Button onClick={handleCreate}>作成</Button>
        </DialogActions>
      </Dialog>

      {/* タグ管理ダイアログ（新規追加・編集・削除） */}
      <Dialog open={openTagDialog} onClose={() => setOpenTagDialog(false)} fullWidth maxWidth="xs">
        <DialogTitle>タグ管理</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', gap: 1, mb: 2, mt: 1 }}>
            <TextField
              size="small"
              label="新しいタグ名"
              fullWidth
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
            />
            <Button variant="contained" onClick={handleAddTag}>追加</Button>
          </Box>
          <Divider sx={{ mb: 1 }} />
          {tags.length === 0 && (
            <Typography variant="body2" color="text.secondary">タグがまだありません</Typography>
          )}
          {tags.map(tag => (
            <Box key={tag.id} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              {editingTagId === tag.id ? (
                <>
                  <TextField
                    size="small"
                    value={editingTagName}
                    onChange={(e) => setEditingTagName(e.target.value)}
                    fullWidth
                  />
                  <Button size="small" onClick={() => handleRenameTag(tag)}>保存</Button>
                  <Button size="small" onClick={() => setEditingTagId(null)}>キャンセル</Button>
                </>
              ) : (
                <>
                  <Typography sx={{ flex: 1 }}>{tag.name}</Typography>
                  <Button size="small" onClick={() => startEditTag(tag)}>編集</Button>
                  <IconButton size="small" color="error" onClick={() => handleDeleteTag(tag)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </>
              )}
            </Box>
          ))}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenTagDialog(false)}>閉じる</Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}

export default ClassDataMatrixIdGrid;