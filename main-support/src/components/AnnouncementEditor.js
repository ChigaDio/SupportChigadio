import React, { useEffect, useState } from 'react';
import { Box, Typography, TextField, Button, Grid, Paper, Divider } from '@mui/material';
import { useParams, useNavigate } from 'react-router-dom';
import SimpleMarkdown from './SimpleMarkdown';

function AnnouncementEditor() {
  const { id } = useParams();
  const isNew = !id;
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');

  useEffect(() => {
    if (!isNew) {
      fetch(`/api/announcements/${id}`).then((r) => r.json()).then((d) => {
        setTitle(d.title);
        setBody(d.body);
      });
    }
  }, [id, isNew]);

  const handleSave = () => {
    if (!title.trim()) { alert('タイトルは必須です'); return; }
    const url = isNew ? '/api/announcements' : `/api/announcements/${id}`;
    const method = isNew ? 'POST' : 'PUT';
    fetch(url, {
      method, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, body }),
    })
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error);
        navigate(`/announcements/${isNew ? data.id : id}`);
      })
      .catch((e) => alert('保存エラー: ' + e.message));
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>{isNew ? 'お知らせを作成' : 'お知らせを編集'}</Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <TextField label="タイトル" fullWidth sx={{ mb: 2 }} value={title} onChange={(e) => setTitle(e.target.value)} />
          <TextField
            label="本文（Markdown形式）"
            fullWidth
            multiline
            minRows={16}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            記法例: # 見出し1 / ## 見出し2 / **太字** / *斜体* / `コード` / - 箇条書き / 1. 番号付き（#やーの直後にスペースがなくても認識されます）
          </Typography>
          <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
            <Button variant="contained" onClick={handleSave}>保存</Button>
            <Button onClick={() => navigate(-1)}>キャンセル</Button>
          </Box>
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>プレビュー</Typography>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h5">{title}</Typography>
            <Divider sx={{ my: 1 }} />
            <SimpleMarkdown source={body} />
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}

export default AnnouncementEditor;
