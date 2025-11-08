// AnimatorDataDetailGrid.js
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle,
  DialogContent, DialogActions, Autocomplete, Chip
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CodeIcon from '@mui/icons-material/Code';
import SaveIcon from '@mui/icons-material/Save';
import DeleteIcon from '@mui/icons-material/Delete';

function AnimatorDataDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();

  const [animatorData, setAnimatorData] = useState(null);
  const [events, setEvents] = useState([]);
  const [typeOptions, setTypeOptions] = useState([]);
  const [loading, setLoading] = useState(true);

  // 追加ダイアログ
  const [open, setOpen] = useState(false);
  const [newType, setNewType] = useState('');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');

  // ================== 型オプション取得（ClassDataDetailGridと100%同じ）==================
  useEffect(() => {
    const basicTypes = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object'];
    const unityTypes = [
      'GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion',
      'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite',
      'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject'
    ];

    Promise.all([
      fetch('/api/enum-id').then(r => r.json()).catch(() => []),
      fetch('/api/class-data').then(r => r.json()).catch(() => []),
      fetch('/api/class-data-id').then(r => r.json()).catch(() => [])
    ]).then(([enumList, classList, classIDList]) => {
      const enumTypes = enumList.map(item => item.name);
      const classTypes = classList.map(item => item.name);
      const classIDTypes = classIDList.map(item => item.name);

      setTypeOptions([...basicTypes, ...unityTypes, ...enumTypes, ...classTypes, ...classIDTypes]);
    }).catch(() => {
      setTypeOptions([...basicTypes, ...unityTypes]);
    });
  }, []);
  // =================================================================================

  // ================== データ取得（animatorData全体 + eventsだけ表示）==================
  useEffect(() => {
    fetch(`/api/animator-data/${encodeURIComponent(name)}`)
      .then(r => r.json())
      .then(data => {
        setAnimatorData(data);
        const evts = data.events || [];
        setEvents(evts.map((e, i) => ({
          id: i + 1,
          type: e.type,
          name: e.name,
          description: e.description || ''
        })));
        setLoading(false);
      })
      .catch(() => {
        alert('取得失敗');
        setLoading(false);
      });
  }, [name]);

  // ================== 追加 ==================
  const handleAdd = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('型と名前は必須です');
      return;
    }
    if (events.some(e => e.name === newName)) {
      alert('同名は登録できません');
      return;
    }

    const maxId = Math.max(...events.map(e => e.id), 0) + 1;
    setEvents([...events, {
      id: maxId,
      type: newType,
      name: newName,
      description: newDescription
    }]);
    setOpen(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
  };

  // ================== 削除 ==================
  const handleDelete = (id) => {
    setEvents(events.filter(e => e.id !== id));
  };

  // ================== 並べ替え ==================
  const handleRowOrderChange = ({ oldIndex, targetIndex }) => {
    const newData = [...events];
    const [moved] = newData.splice(oldIndex, 1);
    newData.splice(targetIndex, 0, moved);
    setEvents(newData);
  };

  // ================== 保存（eventsだけ上書き）==================
  const handleSave = () => {
    const updated = {
      ...animatorData,
      events: events.map(e => ({
        type: e.type,
        name: e.name,
        description: e.description
      }))
    };

    fetch(`/api/animator-data/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updated),
    })
      .then(() => {
        alert('保存完了');
        window.location.reload();
      })
      .catch(() => alert('保存失敗'));
  };

  // ================== C#生成・削除 ==================
  const handleGenerate = () => {
    fetch(`/api/generate-animator/${encodeURIComponent(name)}`, { method: 'POST' })
      .then(r => r.json())
      .then(res => alert(res.message || '生成完了'))
      .catch(() => alert('生成失敗'));
  };

  const handleDeleteAnimator = () => {
    if (!window.confirm(`${name} を削除しますか？`)) return;
    fetch('/api/animator-data', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
      .then(() => {
        alert('削除完了');
        navigate('/animator-data');
      });
  };

  const columns = [
    {
      field: 'type',
      headerName: 'Type',
      width: 280,
      editable: true,
      renderEditCell: (params) => (
        <Autocomplete
          freeSolo
          options={typeOptions}
          value={params.value || ''}
          onChange={(e, v) => {
            params.api.setEditCellValue({ id: params.id, field: 'type', value: v });
            params.api.stopEditing();
          }}
          renderInput={(p) => <TextField {...p} autoFocus size="small" />}
        />
      ),
    },
    { field: 'name', headerName: 'Name', width: 200, editable: true },
    { field: 'description', headerName: 'Description', width: 350, editable: true },
    {
      field: 'actions',
      headerName: '',
      width: 100,
      renderCell: (params) => (
        <Button variant="contained" color="error" size="small" onClick={() => handleDelete(params.id)}>
          削除
        </Button>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Animator Events: <Chip label={name} color="primary" />
      </Typography>

      <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Button variant="contained" color="success" startIcon={<AddIcon />} onClick={() => setOpen(true)}>
          イベント追加
        </Button>
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave}>
          保存
        </Button>
        <Button variant="contained" color="secondary" startIcon={<CodeIcon />} onClick={handleGenerate}>
          C#生成
        </Button>
        <Button variant="contained" color="error" startIcon={<DeleteIcon />} onClick={handleDeleteAnimator}>
          Animator削除
        </Button>
      </Box>

      {loading ? (
        <Typography>Loading...</Typography>
      ) : (
        <div style={{ height: 600, width: '100%' }}>
          <DataGrid
            rows={events}
            columns={columns}
            getRowId={r => r.id}
            rowReordering
            onRowOrderChange={handleRowOrderChange}
            editMode="cell"
          />
        </div>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>イベント追加</DialogTitle>
        <DialogContent>
          <Autocomplete
            freeSolo
            options={typeOptions}
            value={newType}
            onChange={(e, v) => setNewType(v || '')}
            renderInput={(params) => (
              <TextField {...params} label="型" margin="dense" fullWidth autoFocus />
            )}
          />
          <TextField label="名前" margin="dense" fullWidth value={newName} onChange={e => setNewName(e.target.value)} />
          <TextField label="説明" margin="dense" fullWidth value={newDescription} onChange={e => setNewDescription(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>キャンセル</Button>
          <Button onClick={handleAdd} variant="contained">追加</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default AnimatorDataDetailGrid;