import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Box, Typography,
  Select, MenuItem, FormControl, IconButton, Divider
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { useNavigate } from 'react-router-dom';
import OpenFileMenuButton from './OpenFileMenuButton';

const NO_TAG = '__none__';

function CustomClassDataIdGrid() {
  const [data, setData] = useState([]);
  const [tags, setTags] = useState([]); // [{id, name}]
  const [openDialog, setOpenDialog] = useState(false);
  const [newName, setNewName] = useState('');
  const [loading, setLoading] = useState(true);

  const [openTagDialog, setOpenTagDialog] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [editingTagId, setEditingTagId] = useState(null);
  const [editingTagName, setEditingTagName] = useState('');

  const navigate = useNavigate();

  useEffect(() => {
    fetchList();
    fetchTags();
  }, []);

  const fetchList = () => {
    fetch('/api/custom-class-data-id')
      .then(response => (response.ok ? response.json() : []))
      .then(fetchedData => {
        const validData = (fetchedData || []).filter(item => item.name && !item.name.includes(':'));
        setData(validData);
        setLoading(false);
      })
      .catch(error => {
        console.error('CustomClassDataID取得エラー:', error);
        alert('データ取得エラー: ' + error.message);
        setLoading(false);
      });
  };

  const fetchTags = () => {
    fetch('/api/custom-class-data-id-tags')
      .then(response => response.json())
      .then(data => setTags(Array.isArray(data) ? data : []))
      .catch(error => {
        console.error('タグ取得エラー:', error);
      });
  };

  const handleCreate = () => {
    if (!newName.trim()) {
      alert('名前は必須です');
      return;
    }
    if (newName.includes(':')) {
      alert('名前に":"を含めることはできません');
      return;
    }
    fetch('/api/custom-class-data-id', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName }),
    })
      .then(response => response.json())
      .then(result => {
        if (result.error) throw new Error(result.error);
        alert(result.message);
        setData([...data, result.data]);
        setOpenDialog(false);
        setNewName('');
      })
      .catch(error => alert('作成エラー: ' + error.message));
  };

  const handleDelete = (name) => {
    if (window.confirm(`${name} を削除しますか？`)) {
      fetch('/api/custom-class-data-id', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          setData(data.filter(item => item.name !== name));
        })
        .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  // --- タグ割り当て ---
  const handleTagChange = (rowName, tagValue) => {
    const tagToSave = tagValue === NO_TAG ? null : tagValue;
    fetch(`/api/custom-class-data-id/${encodeURIComponent(rowName)}/tag`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tag: tagToSave }),
    })
      .then(response => {
        if (!response.ok) throw new Error('タグの更新に失敗');
        return response.json();
      })
      .then(() => {
        setData(data.map(item =>
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
    fetch('/api/custom-class-data-id-tags', {
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
    fetch(`/api/custom-class-data-id-tags/${tag.id}`, {
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
        setData(data.map(item =>
          item.tag === tag.name ? { ...item, tag: editingTagName } : item
        ));
        setEditingTagId(null);
        setEditingTagName('');
      })
      .catch(error => alert('タグ更新エラー: ' + error.message));
  };

  const handleDeleteTag = (tag) => {
    if (!window.confirm(`タグ「${tag.name}」を削除しますか？（割り当て済みのCustomClassDataIDは未設定になります）`)) return;
    fetch('/api/custom-class-data-id-tags', {
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
        setData(data.map(item =>
          item.tag === tag.name ? { ...item, tag: null } : item
        ));
      })
      .catch(error => alert('タグ削除エラー: ' + error.message));
  };

  const columns = [
    {
      field: 'name',
      headerName: '名前',
      width: 220,
      renderCell: (params) => (
        <div
          style={{ cursor: 'pointer', color: '#1976d2' }}
          onClick={() => navigate(`/custom-class-data-id/${encodeURIComponent(params.value)}`)}
        >
          {params.value}
        </div>
      ),
    },
    { field: 'id', headerName: 'ID', width: 90 },
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
        <OpenFileMenuButton category="custom_class_data_id" name={params.row.name} />
      ),
    },
    {
      field: 'actions',
      headerName: '操作',
      width: 120,
      renderCell: (params) => (
        <Button variant="contained" color="error" size="small" onClick={() => handleDelete(params.row.name)}>
          削除
        </Button>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        CustomClassDataID（拡張版IDテーブル）
      </Typography>
      <Button variant="contained" color="primary" onClick={() => setOpenDialog(true)} sx={{ mb: 2 }}>
        新しいCustomClassDataIDを作成
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
                          onClick={() => {
                            fetch('/api/generate-all-custom-binary', { method: 'POST' })
                              .then(res => res.json())
                              .then(result => alert(result.message))
                              .catch(err => alert('エラー: ' + err.message));
                          }}
                          sx={{ mb: 2, ml: 2 }}
                        >Binary生成</Button>
                              <Button
        variant="contained"
        color="secondary"
        onClick={() => {
          fetch('/api/generate-custom-cs-header', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message))
            .catch(err => alert('エラー: ' + err.message));
        }}
        sx={{ mb: 2, ml: 2 }}
      >C#ヘッダー生成</Button>
      {loading ? (
        <Typography>読み込み中...</Typography>
      ) : (
        <div style={{ height: 500, width: '100%' }}>
          <DataGrid rows={data} columns={columns} pageSizeOptions={[5]} getRowId={(row) => row.id} />
        </div>
      )}
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいCustomClassDataIDを作成</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="名前"
            fullWidth
            variant="standard"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
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
    </Box>
  );
}

export default CustomClassDataIdGrid;