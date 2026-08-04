import React, { useEffect, useState } from 'react';
import { Box, Typography, Paper, Button, Divider } from '@mui/material';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import SimpleMarkdown from './SimpleMarkdown';

function AnnouncementDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, serverMode } = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch(`/api/announcements/${id}`).then((r) => r.json()).then(setData).catch(() => {});
  }, [id]);

  if (!data) return <Box sx={{ p: 3 }}><Typography>読み込み中...</Typography></Box>;

  const canEdit = !serverMode || (user && (user.role === 'admin' || (user.role === 'editor' && data.author === user.username)));

  const handleDelete = () => {
    if (!window.confirm('このお知らせを削除しますか？')) return;
    fetch(`/api/announcements/${id}`, { method: 'DELETE' })
      .then((r) => r.json())
      .then((res) => { alert(res.message || res.error); navigate('/announcements'); });
  };

  return (
    <Box sx={{ p: 3 }}>
      <Button onClick={() => navigate('/announcements')} sx={{ mb: 2 }}>&larr; 一覧へ戻る</Button>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h4" gutterBottom>{data.title}</Typography>
        <Typography variant="body2" color="text.secondary">
          {data.created_at} - {data.author}
        </Typography>
        <Divider sx={{ my: 2 }} />
        <SimpleMarkdown source={data.body} />
        {canEdit && (
          <Box sx={{ mt: 3, display: 'flex', gap: 1 }}>
            <Button variant="outlined" onClick={() => navigate(`/announcements/${id}/edit`)}>編集</Button>
            <Button variant="outlined" color="error" onClick={handleDelete}>削除</Button>
          </Box>
        )}
      </Paper>
    </Box>
  );
}

export default AnnouncementDetail;
