import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box, Typography, TextField, Button, Paper, Divider, Checkbox,
  Accordion, AccordionSummary, AccordionDetails,
  List, ListItem, ListItemText, IconButton, CircularProgress, Chip
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DeleteIcon from '@mui/icons-material/Delete';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import RefreshIcon from '@mui/icons-material/Refresh';

function Material() {
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

  const handleGenerate = async (groupName, className, desc, absolutePath, selectedProperties) => {
    await axios.post('/api/material/generate', {
      group_name: groupName,
      class_name: className,
      desc,
      absolute_path: absolutePath,
      properties: selectedProperties
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
      <Typography variant="h4">Material Data 管理</Typography>

      <Box sx={{ my: 2 }}>
        <TextField
          label="New Group Name"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          sx={{ mr: 2 }}
        />
        <Button variant="contained" onClick={addGroup}>Add Group</Button>
      </Box>

      {Object.entries(groups).map(([groupName, entries]) => (
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
            <Typography variant="h6" sx={{ mb: 1 }}>生成済みMaterialデータ</Typography>
            {entries.length === 0 && (
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
                このグループにはまだデータがありません。
              </Typography>
            )}
            {entries.map((entry) => {
              const key = `${groupName}::${entry.class_name}`;
              return (
                <Accordion key={entry.class_name} sx={{ mb: 1 }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography sx={{ flex: 1 }}>
                      {entry.class_name}（{entry.properties.length}プロパティ）
                    </Typography>
                    <IconButton
                      onClick={(e) => { e.stopPropagation(); handleRegenerate(groupName, entry.class_name); }}
                      size="small"
                      disabled={regeneratingKey === key}
                      title="Unityへ再通信してCS/Enum/Core/バイナリを再生成"
                    >
                      {regeneratingKey === key
                        ? <CircularProgress size={18} />
                        : <RefreshIcon />}
                    </IconButton>
                    <IconButton
                      onClick={(e) => { e.stopPropagation(); handleDeleteEntry(groupName, entry.class_name); }}
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

            <MaterialForm groupName={groupName} onGenerate={handleGenerate} />
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
}

function MaterialForm({ groupName, onGenerate }) {
  const [className, setClassName] = useState('');
  const [desc, setDesc] = useState('');
  const [absolutePath, setAbsolutePath] = useState('');
  const [addressablePath, setAddressablePath] = useState('');
  const [properties, setProperties] = useState([]); // [{name, type}]
  const [checkedMap, setCheckedMap] = useState({});  // { propName: bool }

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
      await onGenerate(groupName, className, desc, absolutePath, selectedProperties);
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

export default Material;