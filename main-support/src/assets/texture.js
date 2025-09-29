import React,{ useState, useEffect } from 'react';
import axios from 'axios';
import {
  Box, Typography, TextField, Button, Accordion, AccordionSummary, AccordionDetails,
  List, ListItem, ListItemText, IconButton, ListItemSecondaryAction
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import DeleteIcon from '@mui/icons-material/Delete';

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
      {Object.entries(groups).map(([groupName, textures]) => (
        <Accordion key={groupName}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>{groupName} ({textures.length} textures)</Typography>
            <IconButton onClick={() => deleteGroup(groupName)} sx={{ ml: 2 }}>
              <DeleteIcon />
            </IconButton>
          </AccordionSummary>
          <AccordionDetails>
            <List>
              {textures.map((texture, index) => (
                <ListItem key={index} secondaryAction={
                  <IconButton onClick={() => deleteTexture(groupName, index)}>
                    <DeleteIcon />
                  </IconButton>
                }>
                  <ListItemText
                    primary={`${texture.name} - ${texture.desc}`}
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
              ))}
            </List>
            <TextureForm groupName={groupName} onAddTexture={addTexture} />
          </AccordionDetails>
        </Accordion>
      ))}
      <Box sx={{ mt: 2 }}>
        <Button variant="contained" onClick={generateFiles}>Generate C# and Bin</Button>
      </Box>
    </Box>
  );
}

function TextureForm({ groupName, onAddTexture }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onAddTexture(groupName, { name, desc });
    setName('');
    setDesc('');
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
      <Button type="submit" variant="contained" sx={{ mt: 1, ml: 2 }}>
        Add Texture (Select File)
      </Button>
    </Box>
  );
}

export default Texture;