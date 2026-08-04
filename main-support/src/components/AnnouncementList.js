import React, { useEffect, useState } from 'react';
import { Box, Typography, TextField, List, ListItemButton, ListItemText, Button, Paper } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function AnnouncementList() {
  const { user, serverMode } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState('');

  const canCreate = !serverMode || (user && (user.role === 'admin' || user.role === 'editor'));

  const fetchList = (q) => {
    const url = q ? `/api/announcements?q=${encodeURIComponent(q)}` : '/api/announcements';
    fetch(url).then((r) => r.json()).then(setItems).catch(() => {});
  };

  useEffect(() => { fetchList(''); }, []);

  const handleSearch = (e) => {
    const q = e.target.value;
    setQuery(q);
    fetchList(q);
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h4">お知らせ</Typography>
        {canCreate && (
          <Button variant="contained" onClick={() => navigate('/announcements/new')}>新規作成</Button>
        )}
      </Box>
      <TextField
        fullWidth
        label="検索"
        value={query}
        onChange={handleSearch}
        sx={{ mb: 2 }}
      />
      <Paper>
        <List>
          {items.map((a) => (
            <ListItemButton key={a.id} onClick={() => navigate(`/announcements/${a.id}`)}>
              <ListItemText
                primary={a.title}
                secondary={`${a.created_at} - ${a.author}${a.excerpt ? ' ／ ' + a.excerpt : ''}`}
              />
            </ListItemButton>
          ))}
          {items.length === 0 && (
            <Box sx={{ p: 2 }}>
              <Typography color="text.secondary">お知らせはまだありません</Typography>
            </Box>
          )}
        </List>
      </Paper>
    </Box>
  );
}

export default AnnouncementList;
