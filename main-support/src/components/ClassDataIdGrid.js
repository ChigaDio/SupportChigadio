import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Select, MenuItem, FormControl, Box, IconButton, Typography, Divider
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { useNavigate } from 'react-router-dom';
import OpenFileMenuButton from './OpenFileMenuButton';

const NO_TAG = '__none__';

function ClassDataIdGrid() {
  const [classDataIdData, setClassDataIdData] = useState([]);
  const [tags, setTags] = useState([]); // [{id, name}]
  const [openDialog, setOpenDialog] = useState(false);
  const [newName, setNewName] = useState('');

  const [openTagDialog, setOpenTagDialog] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [editingTagId, setEditingTagId] = useState(null);
  const [editingTagName, setEditingTagName] = useState('');

  // サブグループ管理（タグ配下）
  const [expandedTagId, setExpandedTagId] = useState(null);
  const [newSubgroupName, setNewSubgroupName] = useState('');

  const navigate = useNavigate();

  useEffect(() => {
    fetchClassDataIdList();
    fetchTags();
  }, []);

  const fetchClassDataIdList = () => {
    fetch('/api/class-data-id')
      .then(response => {
        if (!response.ok) throw new Error(`class-data-id取得に失敗: ${response.status}`);
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('class-data-idエンドポイントからJSON以外のレスポンスを受信');
        }
        return response.json();
      })
      .then(data => {
        const validData = data.filter(item => item.name && !item.name.includes(':') && typeof item.name === 'string');
        if (validData.length !== data.length) {
          console.warn('不正な名前をフィルタリング:', data.filter(item => !item.name || item.name.includes(':')));
        }
        setClassDataIdData(validData);
      })
      .catch(error => {
        console.error('class-data-id取得エラー:', error);
        alert('データ取得エラー: ' + error.message);
      });
  };

  const fetchTags = () => {
    fetch('/api/class-data-id-tags')
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
    fetch('/api/class-data-id', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName }),
    })
      .then(response => {
        if (!response.ok) throw new Error(`${newName} の作成に失敗`);
        return response.json();
      })
      .then(result => {
        if (result.error) throw new Error(result.error);
        alert(result.message);
        setClassDataIdData([...classDataIdData, result.data]);
        setOpenDialog(false);
        setNewName('');
      })
      .catch(error => alert('作成エラー: ' + error.message));
  };

  const handleDelete = (name) => {
    if (window.confirm(`${name} を削除しますか？`)) {
      fetch('/api/class-data-id', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
        .then(response => {
          if (!response.ok) throw new Error(`${name} の削除に失敗`);
          return response.json();
        })
        .then(result => {
          alert(result.message);
          setClassDataIdData(classDataIdData.filter(item => item.name !== name));
        })
        .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  // --- タグ割り当て ---
  const handleTagChange = (rowName, tagValue) => {
    const tagToSave = tagValue === NO_TAG ? null : tagValue;
    fetch(`/api/class-data-id/${encodeURIComponent(rowName)}/tag`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tag: tagToSave }),
    })
      .then(response => {
        if (!response.ok) throw new Error('タグの更新に失敗');
        return response.json();
      })
      .then(() => {
        setClassDataIdData(classDataIdData.map(item =>
          item.name === rowName ? { ...item, tag: tagToSave, subgroup: null } : item
        ));
      })
      .catch(error => alert('タグ更新エラー: ' + error.message));
  };

  // --- サブグループ割り当て（タグ配下の第2階層） ---
  const handleSubgroupChange = (rowName, subgroupValue) => {
    const subgroupToSave = subgroupValue === NO_TAG ? null : subgroupValue;
    fetch(`/api/class-data-id/${encodeURIComponent(rowName)}/subgroup`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subgroup: subgroupToSave }),
    })
      .then(response => {
        if (!response.ok) return response.json().then(e => { throw new Error(e.error || 'サブグループの更新に失敗'); });
        return response.json();
      })
      .then(() => {
        setClassDataIdData(classDataIdData.map(item =>
          item.name === rowName ? { ...item, subgroup: subgroupToSave } : item
        ));
      })
      .catch(error => alert('サブグループ更新エラー: ' + error.message));
  };

  // --- サブグループ管理（タグ管理ダイアログ内、タグごとに追加・削除） ---
  const handleAddSubgroup = (tag) => {
    if (!newSubgroupName.trim()) {
      alert('サブグループ名は必須です');
      return;
    }
    fetch(`/api/class-data-id-tags/${tag.id}/subgroups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newSubgroupName }),
    })
      .then(response => response.json().then(data => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error || 'サブグループの作成に失敗');
        setTags(tags.map(t => (t.id === tag.id ? { ...t, subgroups: data.data } : t)));
        setNewSubgroupName('');
      })
      .catch(error => alert('サブグループ作成エラー: ' + error.message));
  };

  const handleDeleteSubgroup = (tag, subgroupName) => {
    if (!window.confirm(`サブグループ「${subgroupName}」を削除しますか？（割り当て済みのClassDataIDはタグ直下に戻ります）`)) return;
    fetch(`/api/class-data-id-tags/${tag.id}/subgroups/${encodeURIComponent(subgroupName)}`, {
      method: 'DELETE',
    })
      .then(response => {
        if (!response.ok) throw new Error('サブグループの削除に失敗');
        return response.json();
      })
      .then(() => {
        setTags(tags.map(t => (
          t.id === tag.id ? { ...t, subgroups: (t.subgroups || []).filter(s => s !== subgroupName) } : t
        )));
        setClassDataIdData(classDataIdData.map(item =>
          (item.tag === tag.name && item.subgroup === subgroupName) ? { ...item, subgroup: null } : item
        ));
      })
      .catch(error => alert('サブグループ削除エラー: ' + error.message));
  };

  // --- タグ管理（新規追加・編集・削除） ---
  const handleAddTag = () => {
    if (!newTagName.trim()) {
      alert('タグ名は必須です');
      return;
    }
    fetch('/api/class-data-id-tags', {
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
    fetch(`/api/class-data-id-tags/${tag.id}`, {
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
        // 割り当て済みの行の表示も更新（タグはnameで保持している前提）
        setClassDataIdData(classDataIdData.map(item =>
          item.tag === tag.name ? { ...item, tag: editingTagName } : item
        ));
        setEditingTagId(null);
        setEditingTagName('');
      })
      .catch(error => alert('タグ更新エラー: ' + error.message));
  };

  const handleDeleteTag = (tag) => {
    if (!window.confirm(`タグ「${tag.name}」を削除しますか？（割り当て済みのClassDataIDは未設定になります）`)) return;
    fetch('/api/class-data-id-tags', {
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
        setClassDataIdData(classDataIdData.map(item =>
          item.tag === tag.name ? { ...item, tag: null, subgroup: null } : item
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
        <div
          style={{ cursor: 'pointer', color: '#1976d2' }}
          onClick={() => {
            if (params.value && !params.value.includes(':') && typeof params.value === 'string') {
              navigate(`/class-data-id/${encodeURIComponent(params.value)}`);
            } else {
              alert('不正なClassDataID名です');
            }
          }}
        >
          {params.value}
        </div>
      )
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
      field: 'subgroup',
      headerName: 'サブグループ',
      width: 180,
      renderCell: (params) => {
        const currentTag = tags.find(t => t.name === params.row.tag);
        const subgroups = currentTag?.subgroups || [];
        if (!params.row.tag) {
          return <Typography variant="body2" color="text.disabled">タグ未設定</Typography>;
        }
        return (
          <FormControl size="small" fullWidth>
            <Select
              value={params.row.subgroup || NO_TAG}
              onChange={(e) => handleSubgroupChange(params.row.name, e.target.value)}
              displayEmpty
            >
              <MenuItem value={NO_TAG}>未設定</MenuItem>
              {subgroups.map(sg => (
                <MenuItem key={sg} value={sg}>{sg}</MenuItem>
              ))}
            </Select>
          </FormControl>
        );
      },
    },
    {
      field: 'openInEditor',
      headerName: 'エディタ',
      width: 80,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <OpenFileMenuButton category="class_data_id" name={params.row.name} />
      ),
    },
    {
      field: 'actions',
      headerName: '操作',
      width: 100,
      renderCell: (params) => (
        <Button
          variant="contained"
          color="error"
          size="small"
          onClick={() => handleDelete(params.row.name)}
        >
          削除
        </Button>
      ),
    },
  ];

  return (
    <div style={{ height: 500, width: '100%', padding: '20px' }}>
      <Button
        variant="contained"
        color="primary"
        onClick={() => setOpenDialog(true)}
        sx={{ mb: 2 }}
      >
        新しいClassDataIDを作成
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
          fetch('/api/generate-all-binary', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message))
            .catch(err => alert('エラー: ' + err.message));
        }}
        sx={{ mb: 2, ml: 2 }}
      >
        全バイナリ生成
      </Button>
      <Button
        variant="contained"
        color="secondary"
        onClick={() => {
          fetch('/api/generate-all-cs-header', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message))
            .catch(err => alert('エラー: ' + err.message));
        }}
        sx={{ mb: 2, ml: 2 }}
      >
        全C#ヘッダー生成
      </Button>
      <Button
        variant="contained"
        color="secondary"
        onClick={() => {
          fetch('/api/generate-table-id', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message))
            .catch(err => alert('エラー: ' + err.message));
        }}
        sx={{ mb: 2, ml: 2 }}
      >
        TableID生成
      </Button>
      <DataGrid
        rows={classDataIdData}
        columns={columns}
        pageSizeOptions={[5]}
        getRowId={(row) => row.id}
      />

      {/* 新規ClassDataID作成ダイアログ */}
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいClassDataIDを作成</DialogTitle>
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
            <Box key={tag.id} sx={{ mb: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
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
                    <Button
                      size="small"
                      onClick={() => setExpandedTagId(expandedTagId === tag.id ? null : tag.id)}
                    >
                      サブグループ({(tag.subgroups || []).length})
                    </Button>
                    <Button size="small" onClick={() => startEditTag(tag)}>編集</Button>
                    <IconButton size="small" color="error" onClick={() => handleDeleteTag(tag)}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </>
                )}
              </Box>
              {expandedTagId === tag.id && (
                <Box sx={{ pl: 2, pr: 1, py: 1, ml: 1, borderLeft: '2px solid', borderColor: 'divider' }}>
                  <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
                    <TextField
                      size="small"
                      label="新しいサブグループ名"
                      fullWidth
                      value={newSubgroupName}
                      onChange={(e) => setNewSubgroupName(e.target.value)}
                    />
                    <Button size="small" variant="contained" onClick={() => handleAddSubgroup(tag)}>追加</Button>
                  </Box>
                  {(tag.subgroups || []).length === 0 ? (
                    <Typography variant="body2" color="text.secondary">サブグループがまだありません</Typography>
                  ) : (
                    (tag.subgroups || []).map(sg => (
                      <Box key={sg} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        <Typography variant="body2" sx={{ flex: 1 }}>{sg}</Typography>
                        <IconButton size="small" color="error" onClick={() => handleDeleteSubgroup(tag, sg)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Box>
                    ))
                  )}
                </Box>
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

export default ClassDataIdGrid;