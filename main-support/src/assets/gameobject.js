import React,{ useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box, Typography, TextField, Button, Accordion, AccordionSummary, AccordionDetails,
  List, ListItem, ListItemText, IconButton, Select, MenuItem, FormControl, InputLabel, Chip, Divider,
  CircularProgress
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import RefreshIcon from '@mui/icons-material/Refresh';
import SaveIcon from '@mui/icons-material/Save';
import CloseIcon from '@mui/icons-material/Close';

function GameObject() {
  const [groups, setGroups] = useState({});
  const [newGroupName, setNewGroupName] = useState('');

  useEffect(() => {
    fetchGroups();
  }, []);

  const fetchGroups = async () => {
    try {
      const response = await axios.get('/api/gameobject');
      setGroups(response.data.groups);
    } catch (error) {
      console.error('Failed to fetch groups:', error);
    }
  };

  const addGroup = async () => {
    if (!newGroupName) return;
    try {
      await axios.post('/api/gameobject/add_group', { group_name: newGroupName });
      setNewGroupName('');
      fetchGroups();
    } catch (error) {
      console.error('Failed to add group:', error);
    }
  };

  const deleteGroup = async (groupName) => {
    try {
      await axios.post('/api/gameobject/delete_group', { group_name: groupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete group:', error);
    }
  };

  
  const addNest = async (groupName, parentPath, nestName) => {
    try {
      await axios.post('/api/gameobject/add_nest', { group_name: groupName, parent_path: parentPath || [], nest_name: nestName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add nest:', error);
      alert(error.response?.data?.error || 'ネストの追加に失敗しました。');
    }
  };
  const deleteNest = async (groupName, path) => {
    try {
      await axios.post('/api/gameobject/delete_nest', { group_name: groupName, path: path || [] });
      fetchGroups();
    } catch (error) { console.error('Failed to delete nest:', error); }
  };
  const renameNest = async (groupName, path, newName) => {
    try {
      await axios.post('/api/gameobject/rename_nest', { group_name: groupName, path: path || [], new_name: newName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to rename nest:', error);
      alert(error.response?.data?.error || 'リネームに失敗しました。');
    }
  };

  const addSubgroup = async (groupName, subgroupName) => {
    try {
      await axios.post('/api/gameobject/add_subgroup', { group_name: groupName, subgroup_name: subgroupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add subgroup:', error);
    }
  };

  const deleteSubgroup = async (groupName, subgroupName) => {
    try {
      await axios.post('/api/gameobject/delete_subgroup', { group_name: groupName, subgroup_name: subgroupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete subgroup:', error);
    }
  };

  const addGameObject = async (groupName, goData) => {
    try {
      await axios.post('/api/gameobject/add_gameobject', { group_name: groupName, ...goData });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add gameobject:', error);
    }
  };

  const deleteGameObject = async (groupName, index) => {
    try {
      await axios.post('/api/gameobject/delete_gameobject', { group_name: groupName, index });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete gameobject:', error);
    }
  };

  const editGameObject = async (groupName, index, fields) => {
    await axios.post('/api/gameobject/edit_gameobject', { group_name: groupName, index, ...fields });
    fetchGroups();
  };

  const reloadGameObject = async (groupName, index) => {
    const response = await axios.post('/api/gameobject/reload_gameobject', { group_name: groupName, index });
    fetchGroups();
    return response.data.entry;
  };

  const generateFiles = async () => {
    try {
      await axios.post('/api/gameobject/generate');
      alert('C# and Binary files generated successfully.');
    } catch (error) {
      console.error('Failed to generate files:', error);
    }
  };

  return (
    <Box>
      <Typography variant="h4">GameObject Management</Typography>
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
        const items = groupValue?.items || [];
        const subgroups = groupValue?.subgroups || [];
        return (
          <Accordion key={groupName}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography>{groupName} ({items.length} gameobjects)</Typography>
              <IconButton onClick={(e) => { e.stopPropagation(); deleteGroup(groupName); }} sx={{ ml: 2 }}>
                <DeleteIcon />
              </IconButton>
            </AccordionSummary>
            <AccordionDetails>
              <NestTree
                groupName={groupName}
                nests={groupValue?.nests || {}}
                path={[]}
                onAdd={(parentPath, name) => addNest(groupName, parentPath, name)}
                onDelete={(path) => deleteNest(groupName, path)}
                onRename={(path, newName) => renameNest(groupName, path, newName)}
              />

              <Divider sx={{ my: 2 }} />

              <GroupedItemList
                groupName={groupName}
                items={items}
                subgroups={subgroups}
                nests={groupValue?.nests || {}}
                onDelete={(index) => deleteGameObject(groupName, index)}
                onEdit={(index, fields) => editGameObject(groupName, index, fields)}
                onReload={(index) => reloadGameObject(groupName, index)}
              />

              <GameObjectForm groupName={groupName} subgroups={subgroups} nests={groupValue?.nests || {}} onAddGameObject={addGameObject} />
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

function NestTree({ groupName, nests, path, onAdd, onDelete, onRename }) {
  const [newName, setNewName] = useState('');
  const [renaming, setRenaming] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [expanded, setExpanded] = useState({});
  const children = nests || {};
  const childNames = Object.keys(children);
  const depth = path.length;
  const label = depth === 0 ? 'Nests（トップレベル）' : `Nest: ${path.join(' / ')}`;
  const handleAdd = () => { if (!newName.trim()) return; onAdd(path, newName.trim()); setNewName(''); };
  return (
    <Box sx={{ ml: depth === 0 ? 0 : 2, borderLeft: depth ? '2px solid #e0e0e0' : 'none', pl: depth ? 1 : 0, mb: 1 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>{label}</Typography>
      {childNames.length === 0 && (
        <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1 }}>ネストはまだありません。下で追加できます。</Typography>
      )}
      {childNames.map((name) => {
        const childPath = [...path, name];
        const isOpen = !!expanded[name];
        return (
          <Box key={name} sx={{ mb: 0.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Button size="small" onClick={() => setExpanded((e) => ({ ...e, [name]: !e[name] }))}>
                {isOpen ? '▼' : '▶'} {name}
              </Button>
              {renaming === name ? (
                <>
                  <TextField size="small" value={renameValue} onChange={(e) => setRenameValue(e.target.value)} sx={{ width: 140 }} />
                  <Button size="small" variant="contained" onClick={() => { onRename(childPath, renameValue.trim()); setRenaming(null); }}>保存</Button>
                  <Button size="small" onClick={() => setRenaming(null)}>キャンセル</Button>
                </>
              ) : (
                <>
                  <IconButton size="small" onClick={() => { setRenaming(name); setRenameValue(name); }}><EditIcon fontSize="small" /></IconButton>
                  <IconButton size="small" onClick={() => onDelete(childPath)}><DeleteIcon fontSize="small" /></IconButton>
                </>
              )}
            </Box>
            {isOpen && (
              <NestTree groupName={groupName} nests={(children[name] && children[name].nests) || {}} path={childPath}
                onAdd={onAdd} onDelete={onDelete} onRename={onRename} />
            )}
          </Box>
        );
      })}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 0.5 }}>
        <TextField label={depth === 0 ? 'New Nest Name' : 'Child Nest Name'} size="small" value={newName} onChange={(e) => setNewName(e.target.value)} />
        <Button variant="outlined" size="small" onClick={handleAdd}>Add Nest</Button>
      </Box>
    </Box>
  );
}
function nestPathLabel(path) {
  if (!path || path.length === 0) return '(グループ直下)';
  return path.join(' / ');
}

function NestPathSelect({ nests, value, onChange, label = "Nest Path" }) {
  // value: string[] path
  const path = Array.isArray(value) ? value : (value ? [value] : []);
  const options = collectNestPaths(nests || {}, []);
  return (
    <FormControl fullWidth size="small" sx={{ mb: 1 }}>
      <InputLabel>{label}</InputLabel>
      <Select
        label={label}
        value={path.join('/') || ''}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === '' ? [] : v.split('/'));
        }}
      >
        {options.map((opt) => (
          <MenuItem key={opt.path.join('/') || '__root'} value={opt.path.join('/')}>
            {opt.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

function collectNestPaths(nests, prefix = []) {
  const result = [{ path: prefix, label: nestPathLabel(prefix) }];
  Object.keys(nests || {}).forEach((name) => {
    result.push(...collectNestPaths((nests[name] && nests[name].nests) || {}, [...prefix, name]));
  });
  return result;
}

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

// SubGroup（無し／各SubGroup）ごとにアイテムをまとめて表示する共通UI
function GroupedItemList({ groupName, items, subgroups, nests = {}, onDelete, onEdit, onReload }) {
  const buckets = [{ label: null, key: '__root__' }, ...subgroups.map((sg) => ({ label: sg, key: sg }))];

  return (
    <Box sx={{ mb: 2 }}>
      {buckets.map((bucket) => {
        const bucketItems = items
          .map((item, index) => ({ item, index }))
          .filter(({ item }) => (item.subgroup || null) === (bucket.label || null));

        if (bucketItems.length === 0) return null;

        return (
          <Box key={bucket.key} sx={{ mb: 1 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 'bold' }}>
              {bucket.label ? `SubGroup: ${bucket.label}` : '(SubGroupなし)'}
            </Typography>
            <List dense>
              {bucketItems.map(({ item, index }) => (
                <GameObjectRow
                  key={index}
                  item={item}
                  subgroups={subgroups}
                  nests={nests}
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

function GameObjectRow({ item, subgroups, nests = {}, onDelete, onEdit, onReload }) {
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(item.name);
  const [desc, setDesc] = useState(item.desc);
  const [subgroupName, setSubgroupName] = useState(item.subgroup || '');
  const [nestPath, setNestPath] = useState(Array.isArray(item.nest_path) ? item.nest_path : (item.subgroup ? [item.subgroup] : []));
  const [isSaving, setIsSaving] = useState(false);
  const [isReloading, setIsReloading] = useState(false);

  const startEdit = () => {
    setName(item.name);
    setDesc(item.desc);
    setSubgroupName(item.subgroup || '');
    setNestPath(Array.isArray(item.nest_path) ? item.nest_path : (item.subgroup ? [item.subgroup] : []));
    setIsEditing(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onEdit({ name, desc, subgroup_name: nestPath && nestPath.length ? nestPath : (subgroupName ? [subgroupName] : []) || null });
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to save gameobject:', error);
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
      console.error('Failed to reload gameobject file:', error);
      alert(error.response?.data?.error || 'ファイルの再選択に失敗しました。');
    } finally {
      setIsReloading(false);
    }
  };

  if (!isEditing) {
    return (
      <ListItem secondaryAction={
        <>
          <IconButton onClick={startEdit} size="small" title="編集">
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton onClick={onDelete} size="small" title="削除">
            <DeleteIcon fontSize="small" />
          </IconButton>
        </>
      }>
        <ListItemText primary={`${item.name} - ${item.desc}`} secondary={`Path: ${item.path}`} />
      </ListItem>
    );
  }

  return (
    <ListItem sx={{ display: 'block', bgcolor: 'action.hover', borderRadius: 1, my: 0.5 }}>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap', py: 1 }}>
        <TextField label="Name" size="small" value={name} onChange={(e) => setName(e.target.value)} />
        <TextField label="Description" size="small" value={desc} onChange={(e) => setDesc(e.target.value)} />
                <NestPathSelect
          nests={nests || {}}
          value={nestPath}
          onChange={(p) => { setNestPath(p); setSubgroupName(p.length ? p[p.length - 1] : ''); }}
          label="Nest Path"
        />


        <Button
          size="small"
          variant="outlined"
          startIcon={isReloading ? <CircularProgress size={14} /> : <RefreshIcon />}
          onClick={handleReload}
          disabled={isReloading}
          title="以前保存していたパスのフォルダから、ファイルを再選択する"
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
        Path: {item.path}
      </Typography>
    </ListItem>
  );
}

function GameObjectForm({ groupName, subgroups, nests = {}, onAddGameObject }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [subgroupName, setSubgroupName] = useState('');
  const [nestPath, setNestPath] = useState([]);

  const handleSubmit = (e) => {
    e.preventDefault();
    onAddGameObject(groupName, { name, desc, subgroup_name: nestPath && nestPath.length ? nestPath : (subgroupName ? [subgroupName] : []) || null });
    setName('');
    setDesc('');
    setSubgroupName('');
    setNestPath([]);
  };

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ mt: 2 }}>
      <Typography variant="h6">Add GameObject to {groupName}</Typography>
      <TextField
        label="GameObject Name"
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
              <NestPathSelect
          nests={nests || {}}
          value={nestPath}
          onChange={(p) => { setNestPath(p); setSubgroupName(p.length ? p[p.length - 1] : ''); }}
          label="Nest Path"
        />

      <Button type="submit" variant="contained" sx={{ mt: 1, ml: 2 }}>
        Add GameObject (Select File)
      </Button>
    </Box>
  );
}

export default GameObject;