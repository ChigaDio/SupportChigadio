import React,{ useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box, Typography, TextField, Button, Accordion, AccordionSummary, AccordionDetails,
  List, ListItem, ListItemText, IconButton
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DeleteIcon from '@mui/icons-material/Delete';

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
      {Object.entries(groups).map(([groupName, gameobjects]) => (
        <Accordion key={groupName}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>{groupName} ({gameobjects.length} gameobjects)</Typography>
            <IconButton onClick={() => deleteGroup(groupName)} sx={{ ml: 2 }}>
              <DeleteIcon />
            </IconButton>
          </AccordionSummary>
          <AccordionDetails>
            <List>
              {gameobjects.map((go, index) => (
                <ListItem key={index} secondaryAction={
                  <IconButton onClick={() => deleteGameObject(groupName, index)}>
                    <DeleteIcon />
                  </IconButton>
                }>
                  <ListItemText
                    primary={`${go.name} - ${go.desc}`}
                    secondary={`Path: ${go.path}`}
                  />
                </ListItem>
              ))}
            </List>
            <GameObjectForm groupName={groupName} onAddGameObject={addGameObject} />
          </AccordionDetails>
        </Accordion>
      ))}
      <Box sx={{ mt: 2 }}>
        <Button variant="contained" onClick={generateFiles}>Generate C# and Bin</Button>
      </Box>
    </Box>
  );
}

function GameObjectForm({ groupName, onAddGameObject }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onAddGameObject(groupName, { name, desc });
    setName('');
    setDesc('');
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
      <Button type="submit" variant="contained" sx={{ mt: 1, ml: 2 }}>
        Add GameObject (Select File)
      </Button>
    </Box>
  );
}

export default GameObject;