import React,{ useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box, Typography, TextField, Button, Accordion, AccordionSummary, AccordionDetails,
  List, ListItem, ListItemText, IconButton, FormControlLabel, Select, MenuItem, FormControl, InputLabel,
  Chip, Divider, CircularProgress
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import RefreshIcon from '@mui/icons-material/Refresh';
import SaveIcon from '@mui/icons-material/Save';
import CloseIcon from '@mui/icons-material/Close';
import Checkbox from '@mui/material/Checkbox';

function Texture() {
  const [groups, setGroups] = useState({});
  const [newGroupName, setNewGroupName] = useState('');

  useEffect(() => {
    fetchGroups();
  }, []);

  const fetchGroups = async () => {
    try {
      const response = await axios.get('/api/texture');
      setGroups(response.data.groups);
    } catch (error) {
      console.error('Failed to fetch groups:', error);
    }
  };

  const addGroup = async () => {
    if (!newGroupName) return;
    try {
      await axios.post('/api/texture/add_group', { group_name: newGroupName });
      setNewGroupName('');
      fetchGroups();
    } catch (error) {
      console.error('Failed to add group:', error);
    }
  };

  const deleteGroup = async (groupName) => {
    try {
      await axios.post('/api/texture/delete_group', { group_name: groupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete group:', error);
    }
  };

  const addSubgroup = async (groupName, subgroupName) => {
    try {
      await axios.post('/api/texture/add_subgroup', { group_name: groupName, subgroup_name: subgroupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add subgroup:', error);
    }
  };

  const deleteSubgroup = async (groupName, subgroupName) => {
    try {
      await axios.post('/api/texture/delete_subgroup', { group_name: groupName, subgroup_name: subgroupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete subgroup:', error);
    }
  };

  const addTexture = async (groupName, textureData) => {
    try {
      await axios.post('/api/texture/add_texture', { group_name: groupName, ...textureData });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add texture:', error);
    }
  };

  const deleteTexture = async (groupName, index) => {
    try {
      await axios.post('/api/texture/delete_texture', { group_name: groupName, index });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete texture:', error);
    }
  };

  const editTexture = async (groupName, index, fields) => {
    await axios.post('/api/texture/edit_texture', { group_name: groupName, index, ...fields });
    fetchGroups();
  };

  const reloadTexture = async (groupName, index) => {
    const response = await axios.post('/api/texture/reload_texture', { group_name: groupName, index });
    fetchGroups();
    return response.data.entry;
  };

  const generateFiles = async () => {
    try {
      await axios.post('/api/texture/generate');
      alert('C# and Binary files generated successfully.');
    } catch (error) {
      console.error('Failed to generate files:', error);
    }
  };

  return (
    <Box>
      <Typography variant="h4">Texture Management</Typography>
      <Box sx={{ my: 2 }}>
        <TextField
          label="New Group Name"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          sx={{ mr: 2 }}
        />
        <Button variant="contained" onClick={addGroup}>Add Group</Button>
      </Box>
      {Object.entries(groups).map(([groupName, groupValue]) => {
        const textures = groupValue?.items || [];
        const subgroups = groupValue?.subgroups || [];
        return (
          <Accordion key={groupName}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography>{groupName} ({textures.length} textures)</Typography>
              <IconButton onClick={(e) => { e.stopPropagation(); deleteGroup(groupName); }} sx={{ ml: 2 }}>
                <DeleteIcon />
              </IconButton>
            </AccordionSummary>
            <AccordionDetails>
              <SubgroupManager
                subgroups={subgroups}
                onAdd={(name) => addSubgroup(groupName, name)}
                onDelete={(name) => deleteSubgroup(groupName, name)}
              />

              <Divider sx={{ my: 2 }} />

              <GroupedTextureList
                groupName={groupName}
                textures={textures}
                subgroups={subgroups}
                onDelete={(index) => deleteTexture(groupName, index)}
                onEdit={(index, fields) => editTexture(groupName, index, fields)}
                onReload={(index) => reloadTexture(groupName, index)}
              />

              <TextureForm groupName={groupName} subgroups={subgroups} onAddTexture={addTexture} />
            </AccordionDetails>
          </Accordion>
        );
      })}
      <Box sx={{ mt: 2 }}>
        <Button variant="contained" onClick={generateFiles}>Generate C# and Bin</Button>
      </Box>
    </Box>
  );
}

// SubGroupの追加・削除を行う共通UI
function SubgroupManager({ subgroups, onAdd, onDelete }) {
  const [newSubgroupName, setNewSubgroupName] = useState('');

  const handleAdd = () => {
    if (!newSubgroupName) return;
    onAdd(newSubgroupName);
    setNewSubgroupName('');
  };

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>SubGroups</Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
        {subgroups.length === 0 && (
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>SubGroupはまだありません。</Typography>
        )}
        {subgroups.map((sg) => (
          <Chip key={sg} label={sg} onDelete={() => onDelete(sg)} size="small" />
        ))}
      </Box>
      <TextField
        label="New SubGroup Name"
        size="small"
        value={newSubgroupName}
        onChange={(e) => setNewSubgroupName(e.target.value)}
        sx={{ mr: 2 }}
      />
      <Button variant="outlined" size="small" onClick={handleAdd}>Add SubGroup</Button>
    </Box>
  );
}

function GroupedTextureList({ groupName, textures, subgroups, onDelete, onEdit, onReload }) {
  const buckets = [{ label: null, key: '__root__' }, ...subgroups.map((sg) => ({ label: sg, key: sg }))];

  return (
    <Box sx={{ mb: 2 }}>
      {buckets.map((bucket) => {
        const bucketTextures = textures
          .map((texture, index) => ({ texture, index }))
          .filter(({ texture }) => (texture.subgroup || null) === (bucket.label || null));

        if (bucketTextures.length === 0) return null;

        return (
          <Box key={bucket.key} sx={{ mb: 1 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 'bold' }}>
              {bucket.label ? `SubGroup: ${bucket.label}` : '(SubGroupなし)'}
            </Typography>
            <List>
              {bucketTextures.map(({ texture, index }) => (
                <TextureRow
                  key={index}
                  groupName={groupName}
                  texture={texture}
                  index={index}
                  subgroups={subgroups}
                  onDelete={() => onDelete(index)}
                  onEdit={(fields) => onEdit(index, fields)}
                  onReload={() => onReload(index)}
                />
              ))}
            </List>
          </Box>
        );
      })}
    </Box>
  );
}

function TextureRow({ groupName, texture, index, subgroups, onDelete, onEdit, onReload }) {
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(texture.name);
  const [desc, setDesc] = useState(texture.desc);
  const [isSpriteRender, setIsSpriteRender] = useState(!!texture.isSpriteRender);
  const [subgroupName, setSubgroupName] = useState(texture.subgroup || '');
  const [isSaving, setIsSaving] = useState(false);
  const [isReloading, setIsReloading] = useState(false);

  const startEdit = () => {
    setName(texture.name);
    setDesc(texture.desc);
    setIsSpriteRender(!!texture.isSpriteRender);
    setSubgroupName(texture.subgroup || '');
    setIsEditing(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onEdit({ name, desc, isSpriteRender, subgroup_name: subgroupName || null });
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to save texture:', error);
      alert(error.response?.data?.error || '保存に失敗しました。');
    } finally {
      setIsSaving(false);
    }
  };

  const handleReload = async () => {
    setIsReloading(true);
    try {
      await onReload();
    } catch (error) {
      console.error('Failed to reload texture file:', error);
      alert(error.response?.data?.error || 'ファイルの再選択に失敗しました。');
    } finally {
      setIsReloading(false);
    }
  };

  if (!isEditing) {
    return (
      <ListItem secondaryAction={
        <>
          <IconButton onClick={startEdit} title="編集">
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton onClick={onDelete} title="削除">
            <DeleteIcon fontSize="small" />
          </IconButton>
        </>
      }>
        <ListItemText
          primary={`${texture.name} - ${texture.desc} - isSpriteSheet:${texture.isSpriteRender ? "True" : "False"}`}
          secondary={`Path: ${texture.path}`}
        />
        <img src={`/api/texture/serve/${groupName}/${index}`} alt={texture.name} style={{ maxWidth: '100px', marginLeft: '10px' }} />
        {texture.sprites && texture.sprites.length > 0 && (
          <List dense>
            {texture.sprites.map((sprite, sIndex) => (
              <ListItem key={sIndex}>
                <ListItemText primary={`Sprite: ${sprite}`} />
              </ListItem>
            ))}
          </List>
        )}
      </ListItem>
    );
  }

  return (
    <ListItem sx={{ display: 'block', bgcolor: 'action.hover', borderRadius: 1, my: 0.5 }}>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap', py: 1 }}>
        <TextField label="Name" size="small" value={name} onChange={(e) => setName(e.target.value)} />
        <TextField label="Description" size="small" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <FormControlLabel
          control={<Checkbox checked={isSpriteRender} onChange={(e) => setIsSpriteRender(e.target.checked)} />}
          label="Is Sprite"
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>SubGroup</InputLabel>
          <Select value={subgroupName} label="SubGroup" onChange={(e) => setSubgroupName(e.target.value)}>
            <MenuItem value="">(なし)</MenuItem>
            {subgroups.map((sg) => (
              <MenuItem key={sg} value={sg}>{sg}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Button
          size="small"
          variant="outlined"
          startIcon={isReloading ? <CircularProgress size={14} /> : <RefreshIcon />}
          onClick={handleReload}
          disabled={isReloading}
          title="以前保存していたパスのフォルダから、ファイルを再選択する（スプライト情報も再取得）"
        >
          リロード通信
        </Button>
        <Button
          size="small"
          variant="contained"
          startIcon={isSaving ? <CircularProgress size={14} color="inherit" /> : <SaveIcon />}
          onClick={handleSave}
          disabled={isSaving}
        >
          保存
        </Button>
        <IconButton size="small" onClick={() => setIsEditing(false)} title="キャンセル">
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        Path: {texture.path}
      </Typography>
    </ListItem>
  );
}

function TextureForm({ groupName, subgroups, onAddTexture }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [isSpriteRender, setIsSpriteRender] = useState(false);
  const [subgroupName, setSubgroupName] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onAddTexture(groupName, { name, desc, isSpriteRender, subgroup_name: subgroupName || null });
    setName('');
    setDesc('');
    setIsSpriteRender(false);
    setSubgroupName('');
  };

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ mt: 2 }}>
      <Typography variant="h6">Add Texture to {groupName}</Typography>
      <TextField
        label="Texture Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        sx={{ mr: 2, mt: 1 }}
      />
      <TextField
        label="Description"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
        sx={{ mr: 2, mt: 1 }}
      />
      <FormControlLabel
        control={
          <Checkbox
            checked={isSpriteRender}
            onChange={(e) => setIsSpriteRender(e.target.checked)}
          />
        }
        label="Is Sprite"
        sx={{ mt: 2 }}
      />
      <FormControl sx={{ minWidth: 160, mt: 1, mr: 2 }}>
        <InputLabel>SubGroup (optional)</InputLabel>
        <Select
          value={subgroupName}
          label="SubGroup (optional)"
          onChange={(e) => setSubgroupName(e.target.value)}
        >
          <MenuItem value="">(なし)</MenuItem>
          {subgroups.map((sg) => (
            <MenuItem key={sg} value={sg}>{sg}</MenuItem>
          ))}
        </Select>
      </FormControl>

      <Button type="submit" variant="contained" sx={{ mt: 1, ml: 2 }}>
        Add Texture (Select File)
      </Button>
    </Box>
  );
}

export default Texture;