import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box, Typography, TextField, Button, Paper, Divider, Checkbox,
  Accordion, AccordionSummary, AccordionDetails,
  List, ListItem, ListItemText, IconButton, CircularProgress, Chip,
  Select, MenuItem, FormControl, InputLabel, Tabs, Tab
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import RefreshIcon from '@mui/icons-material/Refresh';

function Material() {
  const [tab, setTab] = useState(0);

  return (
    <Box>
      <Typography variant="h4">Material Data 管理</Typography>
      <Tabs value={tab} onChange={(e, v) => setTab(v)} sx={{ my: 2 }}>
        <Tab label="グループ管理（Enum・バイナリに含む）" />
        <Tab label="CS生成だけ（Enum・バイナリに含まない）" />
      </Tabs>
      {tab === 0 && <MaterialGroups />}
      {tab === 1 && <MaterialCsOnly />}
    </Box>
  );
}

// =====================================================================
// グループ管理（通常モード）
// =====================================================================
function MaterialGroups() {
  const [groups, setGroups] = useState({});
  const [newGroupName, setNewGroupName] = useState('');
  const [regeneratingKey, setRegeneratingKey] = useState(null); // `${groupName}::${class_name}`

  useEffect(() => {
    fetchGroups();
  }, []);

  const fetchGroups = async () => {
    try {
      const response = await axios.get('/api/material');
      setGroups(response.data.groups || {});
    } catch (error) {
      console.error('Failed to fetch material groups:', error);
    }
  };

  const addGroup = async () => {
    if (!newGroupName) return;
    try {
      await axios.post('/api/material/add_group', { group_name: newGroupName });
      setNewGroupName('');
      fetchGroups();
    } catch (error) {
      console.error('Failed to add material group:', error);
    }
  };

  const deleteGroup = async (groupName) => {
    try {
      await axios.post('/api/material/delete_group', { group_name: groupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete material group:', error);
    }
  };

  
  const addNest = async (groupName, parentPath, nestName) => {
    try {
      await axios.post('/api/material/add_nest', { group_name: groupName, parent_path: parentPath || [], nest_name: nestName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add nest:', error);
      alert(error.response?.data?.error || 'ネストの追加に失敗しました。');
    }
  };
  const deleteNest = async (groupName, path) => {
    try {
      await axios.post('/api/material/delete_nest', { group_name: groupName, path: path || [] });
      fetchGroups();
    } catch (error) { console.error('Failed to delete nest:', error); }
  };
  const renameNest = async (groupName, path, newName) => {
    try {
      await axios.post('/api/material/rename_nest', { group_name: groupName, path: path || [], new_name: newName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to rename nest:', error);
      alert(error.response?.data?.error || 'リネームに失敗しました。');
    }
  };

  const addSubgroup = async (groupName, subgroupName) => {
    try {
      await axios.post('/api/material/add_subgroup', { group_name: groupName, subgroup_name: subgroupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add subgroup:', error);
    }
  };

  const deleteSubgroup = async (groupName, subgroupName) => {
    try {
      await axios.post('/api/material/delete_subgroup', { group_name: groupName, subgroup_name: subgroupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete subgroup:', error);
    }
  };

  const handleGenerate = async (groupName, className, desc, absolutePath, selectedProperties, subgroupOrNest) => {
    const nest = Array.isArray(subgroupOrNest)
      ? subgroupOrNest
      : (subgroupOrNest ? [subgroupOrNest] : []);
    await axios.post('/api/material/generate', {
      group_name: groupName,
      class_name: className,
      desc,
      absolute_path: absolutePath,
      properties: selectedProperties,
      subgroup_name: nest.length ? nest : null
    });
    fetchGroups();
  };

  const handleRegenerate = async (groupName, entryClassName) => {
    const key = `${groupName}::${entryClassName}`;
    setRegeneratingKey(key);
    try {
      await axios.post('/api/material/regenerate', { group_name: groupName, class_name: entryClassName });
      alert(`${entryClassName}.cs を再生成しました。`);
      fetchGroups();
    } catch (error) {
      console.error('Failed to regenerate material CS:', error);
      alert(error.response?.data?.error || '再生成に失敗しました。');
    } finally {
      setRegeneratingKey(null);
    }
  };

  const handleDeleteEntry = async (groupName, entryClassName) => {
    try {
      await axios.post('/api/material/delete', { group_name: groupName, class_name: entryClassName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete material entry:', error);
    }
  };

  return (
    <Box>
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
        const entries = groupValue?.items || [];
        const subgroups = groupValue?.subgroups || [];
        return (
          <Accordion key={groupName}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography sx={{ flex: 1 }}>{groupName}（{entries.length}件）</Typography>
              <IconButton
                onClick={(e) => { e.stopPropagation(); deleteGroup(groupName); }}
                sx={{ ml: 2 }}
              >
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

              <Typography variant="h6" sx={{ mb: 1 }}>生成済みMaterialデータ</Typography>
              {entries.length === 0 && (
                <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
                  このグループにはまだデータがありません。
                </Typography>
              )}

              <GroupedMaterialEntries
                entries={entries}
                subgroups={subgroups}
                regeneratingKey={regeneratingKey}
                groupName={groupName}
                onRegenerate={handleRegenerate}
                onDelete={handleDeleteEntry}
              />

              <MaterialForm groupName={groupName} subgroups={subgroups} nests={groupValue?.nests || {}} onGenerate={handleGenerate} />
            </AccordionDetails>
          </Accordion>
        );
      })}
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

function GroupedMaterialEntries({ entries, subgroups, regeneratingKey, groupName, onRegenerate, onDelete }) {
  const buckets = [{ label: null, key: '__root__' }, ...subgroups.map((sg) => ({ label: sg, key: sg }))];

  return (
    <Box>
      {buckets.map((bucket) => {
        const bucketEntries = entries.filter((entry) => (entry.subgroup || null) === (bucket.label || null));
        if (bucketEntries.length === 0) return null;

        return (
          <Box key={bucket.key} sx={{ mb: 1 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 'bold' }}>
              {bucket.label ? `SubGroup: ${bucket.label}` : '(SubGroupなし)'}
            </Typography>
            {bucketEntries.map((entry) => {
              const key = `${groupName}::${entry.class_name}`;
              return (
                <Accordion key={entry.class_name} sx={{ mb: 1 }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography sx={{ flex: 1 }}>
                      {entry.class_name}（{entry.properties.length}プロパティ）
                    </Typography>
                    <IconButton
                      onClick={(e) => { e.stopPropagation(); onRegenerate(groupName, entry.class_name); }}
                      size="small"
                      disabled={regeneratingKey === key}
                      title="Unityへ再通信してCS/Enum/Core/バイナリを再生成"
                    >
                      {regeneratingKey === key
                        ? <CircularProgress size={18} />
                        : <RefreshIcon />}
                    </IconButton>
                    <IconButton
                      onClick={(e) => { e.stopPropagation(); onDelete(groupName, entry.class_name); }}
                      size="small"
                    >
                      <DeleteIcon />
                    </IconButton>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography variant="body2" sx={{ mb: 1 }}>{entry.desc}</Typography>
                    <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
                      Path: {entry.absolute_path}
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block', mb: 1, color: 'text.secondary' }}>
                      Addressable: {entry.addressable_path || '(未設定)'}
                    </Typography>
                    <List dense>
                      {entry.properties.map((p) => (
                        <ListItem key={p.name}>
                          <ListItemText primary={p.name} secondary={p.type} />
                        </ListItem>
                      ))}
                    </List>
                  </AccordionDetails>
                </Accordion>
              );
            })}
          </Box>
        );
      })}
    </Box>
  );
}

function MaterialForm({ groupName, subgroups, nests = {}, onGenerate }) {
  const [className, setClassName] = useState('');
  const [desc, setDesc] = useState('');
  const [absolutePath, setAbsolutePath] = useState('');
  const [addressablePath, setAddressablePath] = useState('');
  const [properties, setProperties] = useState([]); // [{name, type}]
  const [checkedMap, setCheckedMap] = useState({});  // { propName: bool }
  const [subgroupName, setSubgroupName] = useState('');
  const [nestPath, setNestPath] = useState([]);

  const [isSelecting, setIsSelecting] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  // エクスプローラーを開いて .shader / .shadergraph / .mat を選択し、プロパティ・Addressableパスを一度に取得
  const handleSelectFile = async () => {
    setIsSelecting(true);
    try {
      const response = await axios.post('/api/material/select_file');
      const { absolute_path, addressable_path, properties: fetchedProps } = response.data;
      setAbsolutePath(absolute_path);
      setAddressablePath(addressable_path || '');
      setProperties(fetchedProps || []);
      const initialChecked = {};
      (fetchedProps || []).forEach((p) => { initialChecked[p.name] = false; });
      setCheckedMap(initialChecked);
    } catch (error) {
      console.error('Failed to select material/shader file:', error);
      alert(error.response?.data?.error || 'ファイルの選択に失敗しました。');
    } finally {
      setIsSelecting(false);
    }
  };

  const toggleProperty = (propName) => {
    setCheckedMap((prev) => ({ ...prev, [propName]: !prev[propName] }));
  };

  const resetForm = () => {
    setClassName('');
    setDesc('');
    setAbsolutePath('');
    setAddressablePath('');
    setProperties([]);
    setCheckedMap({});
    setSubgroupName('');
    setNestPath([]);
  };

  const selectedCount = properties.filter((p) => checkedMap[p.name]).length;

  const handleGenerate = async () => {
    if (!className) {
      alert('クラス名を入力してください。');
      return;
    }
    const selectedProperties = properties.filter((p) => checkedMap[p.name]);
    if (selectedProperties.length === 0) {
      alert('プロパティを1つ以上選択してください。');
      return;
    }
    setIsGenerating(true);
    try {
      await onGenerate(groupName, className, desc, absolutePath, selectedProperties, nestPath.length ? nestPath : (subgroupName ? [subgroupName] : []));
      alert(`${className}.cs を生成しました。`);
      resetForm();
    } catch (error) {
      console.error('Failed to generate material CS:', error);
      alert(error.response?.data?.error || 'C#の生成に失敗しました。');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <Paper sx={{ p: 2, mt: 2 }} variant="outlined">
      <Typography variant="subtitle1" sx={{ mb: 2 }}>{groupName} に新規Materialデータを追加</Typography>

      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          label="クラス名"
          value={className}
          onChange={(e) => setClassName(e.target.value)}
          sx={{ flex: 1 }}
        />
        <TextField
          label="説明"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          sx={{ flex: 2 }}
        />
        <NestPathSelect
          nests={nests || {}}
          value={nestPath}
          onChange={(p) => { setNestPath(p); setSubgroupName(p.length ? p[p.length - 1] : ''); }}
          label="Nest Path"
        />
      </Box>

      <Button
        variant="outlined"
        startIcon={isSelecting ? <CircularProgress size={18} /> : <FolderOpenIcon />}
        onClick={handleSelectFile}
        disabled={isSelecting}
      >
        .shader / .shadergraph / .mat を選択
      </Button>

      {absolutePath && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            選択中: {absolutePath}
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Addressable Path: {addressablePath || '(未設定)'}
          </Typography>
        </Box>
      )}

      {properties.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            プロパティを選択（{selectedCount} / {properties.length}）
          </Typography>
          <Divider sx={{ mb: 1 }} />
          <Box>
            {properties.map((p) => (
              <Box
                key={p.name}
                sx={{
                  display: 'grid',
                  gridTemplateColumns: '40px 1fr 120px',
                  alignItems: 'center',
                  py: 0.5,
                  borderBottom: '1px solid #eee'
                }}
              >
                <Checkbox
                  checked={!!checkedMap[p.name]}
                  onChange={() => toggleProperty(p.name)}
                />
                <Typography sx={{ fontFamily: 'monospace' }}>{p.name}</Typography>
                <Chip label={p.type} size="small" variant="outlined" />
              </Box>
            ))}
          </Box>

          <Button
            variant="contained"
            sx={{ mt: 2 }}
            onClick={handleGenerate}
            disabled={isGenerating}
            startIcon={isGenerating ? <CircularProgress size={18} color="inherit" /> : null}
          >
            CS生成
          </Button>
        </Box>
      )}
    </Paper>
  );
}

// =====================================================================
// CS生成だけモード（Enum・バイナリには一切含まれない、独立したクラス生成のみ）
// =====================================================================
function MaterialCsOnly() {
  const [entries, setEntries] = useState([]);
  const [regeneratingClass, setRegeneratingClass] = useState(null);

  useEffect(() => {
    fetchEntries();
  }, []);

  const fetchEntries = async () => {
    try {
      const response = await axios.get('/api/material/cs_only');
      setEntries(response.data.entries || []);
    } catch (error) {
      console.error('Failed to fetch CS-only material entries:', error);
    }
  };

  const handleGenerate = async (className, desc, absolutePath, selectedProperties) => {
    await axios.post('/api/material/cs_only/generate', {
      class_name: className,
      desc,
      absolute_path: absolutePath,
      properties: selectedProperties
    });
    fetchEntries();
  };

  const handleRegenerate = async (className) => {
    setRegeneratingClass(className);
    try {
      await axios.post('/api/material/cs_only/regenerate', { class_name: className });
      alert(`${className}.cs を再生成しました。`);
      fetchEntries();
    } catch (error) {
      console.error('Failed to regenerate CS-only material:', error);
      alert(error.response?.data?.error || '再生成に失敗しました。');
    } finally {
      setRegeneratingClass(null);
    }
  };

  const handleDelete = async (className) => {
    try {
      await axios.post('/api/material/cs_only/delete', { class_name: className });
      fetchEntries();
    } catch (error) {
      console.error('Failed to delete CS-only material:', error);
    }
  };

  return (
    <Box>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
        ここで生成したクラスは、Group / SubGroup / Enum（MaterialGroup・MaterialID）・バイナリのいずれにも登録されません。
        「とりあえずMaterialPropertyBlock操作用のクラスだけ欲しい」場合に使ってください。
      </Typography>

      <Typography variant="h6" sx={{ mb: 1 }}>生成済み（CS-only）</Typography>
      {entries.length === 0 && (
        <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
          まだデータがありません。
        </Typography>
      )}
      {entries.map((entry) => (
        <Accordion key={entry.class_name} sx={{ mb: 1 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography sx={{ flex: 1 }}>
              {entry.class_name}（{entry.properties.length}プロパティ）
            </Typography>
            <IconButton
              onClick={(e) => { e.stopPropagation(); handleRegenerate(entry.class_name); }}
              size="small"
              disabled={regeneratingClass === entry.class_name}
              title="Unityへ再通信してCSのみ再生成"
            >
              {regeneratingClass === entry.class_name
                ? <CircularProgress size={18} />
                : <RefreshIcon />}
            </IconButton>
            <IconButton
              onClick={(e) => { e.stopPropagation(); handleDelete(entry.class_name); }}
              size="small"
            >
              <DeleteIcon />
            </IconButton>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="body2" sx={{ mb: 1 }}>{entry.desc}</Typography>
            <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
              Path: {entry.absolute_path}
            </Typography>
            <Typography variant="caption" sx={{ display: 'block', mb: 1, color: 'text.secondary' }}>
              Addressable: {entry.addressable_path || '(未設定)'}
            </Typography>
            <List dense>
              {entry.properties.map((p) => (
                <ListItem key={p.name}>
                  <ListItemText primary={p.name} secondary={p.type} />
                </ListItem>
              ))}
            </List>
          </AccordionDetails>
        </Accordion>
      ))}

      <MaterialCsOnlyForm onGenerate={handleGenerate} />
    </Box>
  );
}

function MaterialCsOnlyForm({ onGenerate }) {
  const [className, setClassName] = useState('');
  const [desc, setDesc] = useState('');
  const [absolutePath, setAbsolutePath] = useState('');
  const [addressablePath, setAddressablePath] = useState('');
  const [properties, setProperties] = useState([]);
  const [checkedMap, setCheckedMap] = useState({});

  const [isSelecting, setIsSelecting] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  const handleSelectFile = async () => {
    setIsSelecting(true);
    try {
      const response = await axios.post('/api/material/select_file');
      const { absolute_path, addressable_path, properties: fetchedProps } = response.data;
      setAbsolutePath(absolute_path);
      setAddressablePath(addressable_path || '');
      setProperties(fetchedProps || []);
      const initialChecked = {};
      (fetchedProps || []).forEach((p) => { initialChecked[p.name] = false; });
      setCheckedMap(initialChecked);
    } catch (error) {
      console.error('Failed to select material/shader file:', error);
      alert(error.response?.data?.error || 'ファイルの選択に失敗しました。');
    } finally {
      setIsSelecting(false);
    }
  };

  const toggleProperty = (propName) => {
    setCheckedMap((prev) => ({ ...prev, [propName]: !prev[propName] }));
  };

  const resetForm = () => {
    setClassName('');
    setDesc('');
    setAbsolutePath('');
    setAddressablePath('');
    setProperties([]);
    setCheckedMap({});
  };

  const selectedCount = properties.filter((p) => checkedMap[p.name]).length;

  const handleGenerate = async () => {
    if (!className) {
      alert('クラス名を入力してください。');
      return;
    }
    const selectedProperties = properties.filter((p) => checkedMap[p.name]);
    if (selectedProperties.length === 0) {
      alert('プロパティを1つ以上選択してください。');
      return;
    }
    setIsGenerating(true);
    try {
      await onGenerate(className, desc, absolutePath, selectedProperties);
      alert(`${className}.cs を生成しました（CS-only）。`);
      resetForm();
    } catch (error) {
      console.error('Failed to generate CS-only material:', error);
      alert(error.response?.data?.error || 'C#の生成に失敗しました。');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <Paper sx={{ p: 2, mt: 2 }} variant="outlined">
      <Typography variant="subtitle1" sx={{ mb: 2 }}>新規に CS-only クラスを追加</Typography>

      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          label="クラス名"
          value={className}
          onChange={(e) => setClassName(e.target.value)}
          sx={{ flex: 1 }}
        />
        <TextField
          label="説明"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          sx={{ flex: 2 }}
        />
      </Box>

      <Button
        variant="outlined"
        startIcon={isSelecting ? <CircularProgress size={18} /> : <FolderOpenIcon />}
        onClick={handleSelectFile}
        disabled={isSelecting}
      >
        .shader / .shadergraph / .mat を選択
      </Button>

      {absolutePath && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            選択中: {absolutePath}
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Addressable Path: {addressablePath || '(未設定)'}
          </Typography>
        </Box>
      )}

      {properties.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            プロパティを選択（{selectedCount} / {properties.length}）
          </Typography>
          <Divider sx={{ mb: 1 }} />
          <Box>
            {properties.map((p) => (
              <Box
                key={p.name}
                sx={{
                  display: 'grid',
                  gridTemplateColumns: '40px 1fr 120px',
                  alignItems: 'center',
                  py: 0.5,
                  borderBottom: '1px solid #eee'
                }}
              >
                <Checkbox
                  checked={!!checkedMap[p.name]}
                  onChange={() => toggleProperty(p.name)}
                />
                <Typography sx={{ fontFamily: 'monospace' }}>{p.name}</Typography>
                <Chip label={p.type} size="small" variant="outlined" />
              </Box>
            ))}
          </Box>

          <Button
            variant="contained"
            sx={{ mt: 2 }}
            onClick={handleGenerate}
            disabled={isGenerating}
            startIcon={isGenerating ? <CircularProgress size={18} color="inherit" /> : null}
          >
            CS生成（CS-only）
          </Button>
        </Box>
      )}
    </Paper>
  );
}

export default Material;