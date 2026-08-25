import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box, Typography, TextField, Button, Accordion, AccordionSummary, AccordionDetails,
  List, ListItem, ListItemText, IconButton, MenuItem, Select, FormControl, InputLabel,
  Chip, Divider, CircularProgress, Dialog, DialogTitle, DialogContent, DialogActions
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DeleteIcon from '@mui/icons-material/Delete';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import EditIcon from '@mui/icons-material/Edit';
import RefreshIcon from '@mui/icons-material/Refresh';
import SaveIcon from '@mui/icons-material/Save';
import CloseIcon from '@mui/icons-material/Close';

function Sound() {
  const [groups, setGroups] = useState({});
  const [newGroupName, setNewGroupName] = useState('');
  const [playing, setPlaying] = useState({});

  useEffect(() => {
    fetchGroups();
  }, []);

  const fetchGroups = async () => {
    try {
      const response = await axios.get('/api/sound');
      setGroups(response.data.groups);
    } catch (error) {
      console.error('Failed to fetch groups:', error);
    }
  };

  const addGroup = async () => {
    if (!newGroupName) return;
    try {
      await axios.post('/api/sound/add_group', { group_name: newGroupName });
      setNewGroupName('');
      fetchGroups();
    } catch (error) {
      console.error('Failed to add group:', error);
    }
  };

  const deleteGroup = async (groupName) => {
    try {
      await axios.post('/api/sound/delete_group', { group_name: groupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete group:', error);
    }
  };

  const addSubgroup = async (groupName, subgroupName) => {
    try {
      await axios.post('/api/sound/add_subgroup', { group_name: groupName, subgroup_name: subgroupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add subgroup:', error);
    }
  };

  const deleteSubgroup = async (groupName, subgroupName) => {
    try {
      await axios.post('/api/sound/delete_subgroup', { group_name: groupName, subgroup_name: subgroupName });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete subgroup:', error);
    }
  };

  const addSound = async (groupName, soundData) => {
    try {
      await axios.post('/api/sound/add_sound', { group_name: groupName, ...soundData });
      fetchGroups();
    } catch (error) {
      console.error('Failed to add sound:', error);
    }
  };

  const deleteSound = async (groupName, index) => {
    try {
      await axios.post('/api/sound/delete_sound', { group_name: groupName, index });
      fetchGroups();
    } catch (error) {
      console.error('Failed to delete sound:', error);
    }
  };

  const editSound = async (groupName, index, fields) => {
    await axios.post('/api/sound/edit_sound', { group_name: groupName, index, ...fields });
    fetchGroups();
  };

  const reloadSound = async (groupName, index) => {
    const response = await axios.post('/api/sound/reload_sound', { group_name: groupName, index });
    fetchGroups();
    return response.data.entry;
  };

  const bulkAddFromFolder = async (groupName, soundType, subgroupName, useFolderNameAsSubgroup) => {
    const response = await axios.post('/api/sound/bulk_add_from_folder', {
      group_name: groupName,
      type: soundType,
      subgroup_name: subgroupName || null,
      use_folder_name_as_subgroup: useFolderNameAsSubgroup,
    });
    fetchGroups();
    return response.data;
  };

  const generateFiles = async () => {
    try {
      await axios.post('/api/sound/generate');
      alert('C# and Binary files generated successfully.');
    } catch (error) {
      console.error('Failed to generate files:', error);
    }
  };

  const togglePlay = (groupName, index, audioRef) => {
    setPlaying(prev => {
      const key = `${groupName}-${index}`;
      const isPlaying = prev[key];
      if (isPlaying) {
        audioRef.current.pause();
      } else {
        audioRef.current.play().catch(error => console.error('Playback failed:', error));
      }
      return { ...prev, [key]: !isPlaying };
    });
  };

  return (
    <Box>
      <Typography variant="h4">Sound Management</Typography>
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
        const sounds = groupValue?.items || [];
        const subgroups = groupValue?.subgroups || [];
        return (
          <Accordion key={groupName}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography>{groupName} ({sounds.length} sounds)</Typography>
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

              <GroupedSoundList
                groupName={groupName}
                sounds={sounds}
                subgroups={subgroups}
                playing={playing}
                onDelete={(index) => deleteSound(groupName, index)}
                onTogglePlay={togglePlay}
                onEdit={(index, fields) => editSound(groupName, index, fields)}
                onReload={(index) => reloadSound(groupName, index)}
              />

              <BulkFolderImportButton
                groupName={groupName}
                onBulkAdd={(soundType, subgroupName, useFolderNameAsSubgroup) =>
                  bulkAddFromFolder(groupName, soundType, subgroupName, useFolderNameAsSubgroup)
                }
              />

              <SoundForm groupName={groupName} subgroups={subgroups} onAddSound={addSound} />
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

function GroupedSoundList({ groupName, sounds, subgroups, playing, onDelete, onTogglePlay, onEdit, onReload }) {
  const buckets = [{ label: null, key: '__root__' }, ...subgroups.map((sg) => ({ label: sg, key: sg }))];

  return (
    <Box sx={{ mb: 2 }}>
      {buckets.map((bucket) => {
        const bucketSounds = sounds
          .map((sound, index) => ({ sound, index }))
          .filter(({ sound }) => (sound.subgroup || null) === (bucket.label || null));

        if (bucketSounds.length === 0) return null;

        return (
          <Box key={bucket.key} sx={{ mb: 1 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 'bold' }}>
              {bucket.label ? `SubGroup: ${bucket.label}` : '(SubGroupなし)'}
            </Typography>
            <List>
              {bucketSounds.map(({ sound, index }) => (
                <SoundRow
                  key={index}
                  groupName={groupName}
                  sound={sound}
                  index={index}
                  subgroups={subgroups}
                  playing={playing}
                  onDelete={() => onDelete(index)}
                  onTogglePlay={onTogglePlay}
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

function SoundRow({ groupName, sound, index, subgroups, playing, onDelete, onTogglePlay, onEdit, onReload }) {
  const audioRef = React.useRef();
  const key = `${groupName}-${index}`;

  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(sound.name);
  const [desc, setDesc] = useState(sound.desc);
  const [volume, setVolume] = useState(sound.volume);
  const [type, setType] = useState(sound.type);
  const [subgroupName, setSubgroupName] = useState(sound.subgroup || '');
  const [isSaving, setIsSaving] = useState(false);
  const [isReloading, setIsReloading] = useState(false);

  const startEdit = () => {
    setName(sound.name);
    setDesc(sound.desc);
    setVolume(sound.volume);
    setType(sound.type);
    setSubgroupName(sound.subgroup || '');
    setIsEditing(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onEdit({ name, desc, volume: parseFloat(volume), type, subgroup_name: subgroupName || null });
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to save sound:', error);
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
      console.error('Failed to reload sound file:', error);
      alert(error.response?.data?.error || 'ファイルの再選択に失敗しました。');
    } finally {
      setIsReloading(false);
    }
  };

  if (!isEditing) {
    return (
      <ListItem secondaryAction={
        <>
          <IconButton onClick={() => onTogglePlay(groupName, index, audioRef)}>
            {playing[key] ? <StopIcon /> : <PlayArrowIcon />}
          </IconButton>
          <IconButton onClick={startEdit} title="編集">
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton onClick={onDelete} title="削除">
            <DeleteIcon fontSize="small" />
          </IconButton>
        </>
      }>
        <ListItemText
          primary={`${sound.name} - ${sound.desc}`}
          secondary={`Path: ${sound.path}, Volume: ${sound.volume}, Type: ${sound.type}`}
        />
        <audio ref={audioRef} src={`/api/sound/serve/${groupName}/${index}`} />
      </ListItem>
    );
  }

  return (
    <ListItem sx={{ display: 'block', bgcolor: 'action.hover', borderRadius: 1, my: 0.5 }}>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap', py: 1 }}>
        <TextField label="Name" size="small" value={name} onChange={(e) => setName(e.target.value)} />
        <TextField label="Description" size="small" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <TextField
          label="Volume"
          type="number"
          size="small"
          step="0.1"
          value={volume}
          onChange={(e) => setVolume(e.target.value)}
          sx={{ width: 100 }}
        />
        <Select size="small" value={type} onChange={(e) => setType(e.target.value)}>
          <MenuItem value="SE">SE</MenuItem>
          <MenuItem value="BGM">BGM</MenuItem>
          <MenuItem value="VOICE">VOICE</MenuItem>
        </Select>
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
        Path: {sound.path}
      </Typography>
    </ListItem>
  );
}

// VOICEのように大量にファイルがあるケースを想定し、フォルダを1つ選択する
// だけで直下の音声ファイルをまとめて登録できるボタン＋ダイアログ。
// SubGroup名はフォルダ名を自動採用（チェックを外せば手動指定も可能）。
function BulkFolderImportButton({ groupName, onBulkAdd }) {
  const [open, setOpen] = useState(false);
  const [soundType, setSoundType] = useState('VOICE');
  const [useFolderNameAsSubgroup, setUseFolderNameAsSubgroup] = useState(true);
  const [subgroupName, setSubgroupName] = useState('');
  const [importing, setImporting] = useState(false);

  const handleImport = async () => {
    setImporting(true);
    try {
      const result = await onBulkAdd(
        soundType,
        useFolderNameAsSubgroup ? '' : subgroupName,
        useFolderNameAsSubgroup
      );
      const lines = [
        `フォルダ: ${result.folder}`,
        `SubGroup: ${result.subgroup || '(なし)'}`,
        `追加: ${result.added.length}件`,
        result.skipped.length > 0 ? `スキップ（同名が既存）: ${result.skipped.length}件` : null,
        result.failed.length > 0 ? `失敗: ${result.failed.length}件` : null,
      ].filter(Boolean);
      alert(lines.join('\n'));
      setOpen(false);
    } catch (error) {
      alert('一括追加に失敗しました: ' + (error.response?.data?.error || error.message));
    } finally {
      setImporting(false);
    }
  };

  return (
    <>
      <Button variant="outlined" size="small" onClick={() => setOpen(true)} sx={{ mb: 2 }}>
        フォルダから一括追加（VOICE等）
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>フォルダから一括追加: {groupName}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            フォルダを1つ選択すると、直下にある音声ファイル（.mp3/.wav/.ogg/.aiff）を
            まとめて登録します。同名のアイテムが既にある場合はスキップされます。
          </Typography>
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel>種別</InputLabel>
            <Select label="種別" value={soundType} onChange={(e) => setSoundType(e.target.value)}>
              <MenuItem value="SE">SE</MenuItem>
              <MenuItem value="BGM">BGM</MenuItem>
              <MenuItem value="VOICE">VOICE</MenuItem>
            </Select>
          </FormControl>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <input
              type="checkbox"
              checked={useFolderNameAsSubgroup}
              onChange={(e) => setUseFolderNameAsSubgroup(e.target.checked)}
            />
            <span>SubGroup名としてフォルダ名を自動的に使う</span>
          </label>
          {!useFolderNameAsSubgroup && (
            <TextField
              label="SubGroup名（手動指定・任意）"
              size="small"
              fullWidth
              value={subgroupName}
              onChange={(e) => setSubgroupName(e.target.value)}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={handleImport} disabled={importing}>
            {importing ? '取り込み中...' : 'フォルダを選択して取り込み'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

function SoundForm({ groupName, subgroups, onAddSound }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [volume, setVolume] = useState(1.0);
  const [type, setType] = useState('SE');
  const [subgroupName, setSubgroupName] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onAddSound(groupName, { name, desc, volume: parseFloat(volume), type, subgroup_name: subgroupName || null });
    setName('');
    setDesc('');
    setVolume(1.0);
    setType('SE');
    setSubgroupName('');
  };

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ mt: 2 }}>
      <Typography variant="h6">Add Sound to {groupName}</Typography>
      <TextField
        label="Sound Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        sx={{ mr: 2, mt: 1 }}
      />
      <TextField
        label="Japanese Description"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
        sx={{ mr: 2, mt: 1 }}
      />
      <TextField
        label="Volume"
        type="number"
        step="0.1"
        min="0"
        max="5"
        value={volume}
        onChange={(e) => setVolume(e.target.value)}
        sx={{ mr: 2, mt: 1 }}
      />
      <Select value={type} onChange={(e) => setType(e.target.value)} sx={{ mt: 1, mr: 2 }}>
        <MenuItem value="SE">SE</MenuItem>
        <MenuItem value="BGM">BGM</MenuItem>
        <MenuItem value="VOICE">VOICE</MenuItem>
      </Select>
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
        Add Sound (Select File)
      </Button>
    </Box>
  );
}

export default Sound;