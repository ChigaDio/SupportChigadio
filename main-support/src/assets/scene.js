import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
    Box, Typography, TextField, Button, List, ListItem, ListItemText, IconButton, Paper, Select, MenuItem, FormControl, InputLabel
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';

function Scene() {
    const [scenes, setScenes] = useState([]);
    const [newSceneEnum, setNewSceneEnum] = useState('');
    const [newSceneType, setNewSceneType] = useState('Client');

    useEffect(() => {
        fetchScenes();
    }, []);

    const fetchScenes = async () => {
        try {
            const response = await axios.get('/api/scene/get');
            setScenes(response.data.scenes);
        } catch (error) {
            console.error('Failed to fetch scenes:', error);
        }
    };

    const addScene = async () => {
        if (!newSceneEnum) return;
        try {
            // APIを呼び出すとサーバー側でファイル選択ダイアログが開く
            const response = await axios.post('/api/scene/add', {
                enum_name: newSceneEnum,
                scene_type: newSceneType
            });
            if (response.data.success) {
                setNewSceneEnum('');
                setNewSceneType('Client');
                fetchScenes();
            } else {
                alert(response.data.message);
            }
        } catch (error) {
            console.error('Failed to add scene:', error);
        }
    };

    const deleteScene = async (enumName) => {
        try {
            const response = await axios.post('/api/scene/delete', { enum_name: enumName });
            if (response.data.success) {
                fetchScenes();
            } else {
                alert(response.data.message);
            }
        } catch (error) {
            console.error('Failed to delete scene:', error);
        }
    };

    const generateCode = async () => {
        try {
            const response = await axios.post('/api/scene/generate');
            if (response.data.success) {
                alert('All C# files generated successfully.');
            } else {
                alert('Failed to generate code.');
            }
        } catch (error) {
            console.error('Failed to generate code:', error);
        }
    };

    return (
        <Box sx={{ p: 2 }}>
            <Typography variant="h4" gutterBottom>Scene Management</Typography>

            <Paper sx={{ p: 2, mb: 2 }}>
                <Typography variant="h6">Add New Scene</Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                    <TextField
                        label="Enum Name (e.g. Title)"
                        value={newSceneEnum}
                        onChange={(e) => setNewSceneEnum(e.target.value)}
                        sx={{ mr: 2 }}
                    />
                    <FormControl sx={{ minWidth: 120, mr: 2 }}>
                        <InputLabel>Type</InputLabel>
                        <Select
                            value={newSceneType}
                            label="Type"
                            onChange={(e) => setNewSceneType(e.target.value)}
                        >
                            <MenuItem value="Client">Client</MenuItem>
                            <MenuItem value="Server">Server</MenuItem>
                        </Select>
                    </FormControl>
                    <Button variant="contained" onClick={addScene}>
                        Select File & Add
                    </Button>
                </Box>
            </Paper>

            <Paper sx={{ p: 2, mb: 2 }}>
                <Typography variant="h6">Current Scenes</Typography>
                <List>
                    {scenes.map((scene, index) => (
                        <ListItem key={index} secondaryAction={
                            <IconButton edge="end" aria-label="delete" onClick={() => deleteScene(scene.enum)}>
                                <DeleteIcon />
                            </IconButton>
                        }>
                            <ListItemText
                                primary={`${scene.enum} (${scene.sceneName})`}
                                secondary={`Path: ${scene.path} | Type: ${scene.type}`}
                            />
                        </ListItem>
                    ))}
                </List>
            </Paper>

            <Button variant="contained" color="secondary" onClick={generateCode} sx={{ mt: 2 }}>
                Generate All C# Files
            </Button>
        </Box>
    );
}

export default Scene;
