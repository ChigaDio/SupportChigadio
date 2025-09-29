import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box, Typography, TextField, Button, Accordion, AccordionSummary, AccordionDetails,
  List, ListItem, ListItemText, IconButton, MenuItem, Select
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DeleteIcon from '@mui/icons-material/Delete';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';

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
      {Object.entries(groups).map(([groupName, sounds]) => (
        <Accordion key={groupName}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>{groupName} ({sounds.length} sounds)</Typography>
            <IconButton onClick={() => deleteGroup(groupName)} sx={{ ml: 2 }}>
              <DeleteIcon />
            </IconButton>
          </AccordionSummary>
          <AccordionDetails>
            <List>
              {sounds.map((sound, index) => {
                const audioRef = React.createRef();
                const key = `${groupName}-${index}`;
                return (
                  <ListItem key={index} secondaryAction={
                    <>
                      <IconButton onClick={() => togglePlay(groupName, index, audioRef)}>
                        {playing[key] ? <StopIcon /> : <PlayArrowIcon />}
                      </IconButton>
                      <IconButton onClick={() => deleteSound(groupName, index)}>
                        <DeleteIcon />
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
              })}
            </List>
            <SoundForm groupName={groupName} onAddSound={addSound} />
          </AccordionDetails>
        </Accordion>
      ))}
      <Box sx={{ mt: 2 }}>
        <Button variant="contained" onClick={generateFiles}>Generate C# and Bin</Button>
      </Box>
    </Box>
  );
}

function SoundForm({ groupName, onAddSound }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [volume, setVolume] = useState(1.0);
  const [type, setType] = useState('SE');

  const handleSubmit = (e) => {
    e.preventDefault();
    onAddSound(groupName, { name, desc, volume: parseFloat(volume), type });
    setName('');
    setDesc('');
    setVolume(1.0);
    setType('SE');
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
      <Select value={type} onChange={(e) => setType(e.target.value)} sx={{ mt: 1 }}>
        <MenuItem value="SE">SE</MenuItem>
        <MenuItem value="BGM">BGM</MenuItem>
      </Select>
      <Button type="submit" variant="contained" sx={{ mt: 1, ml: 2 }}>
        Add Sound (Select File)
      </Button>
    </Box>
  );
}

export default Sound;
