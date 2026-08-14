import React from 'react';
import { Box, Typography } from '@mui/material';

// difflib.unified_diff() が生成した unified diff 文字列を、
// git diff のような配色（追加=緑背景、削除=赤背景、ハンク見出し=青文字）で
// 表示するだけのシンプルなビューア。
function DiffViewer({ diffText, summary }) {
  if (!diffText) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
        {summary || '差分はありません。'}
      </Typography>
    );
  }

  const lines = diffText.replace(/\n$/, '').split('\n');

  const styleFor = (line) => {
    if (line.startsWith('+++') || line.startsWith('---')) {
      return { color: '#8b8b8b', fontWeight: 700 };
    }
    if (line.startsWith('@@')) {
      return { color: '#0969da', backgroundColor: 'rgba(9,105,218,0.08)' };
    }
    if (line.startsWith('+')) {
      return { color: '#1a7f37', backgroundColor: 'rgba(26,127,55,0.12)' };
    }
    if (line.startsWith('-')) {
      return { color: '#cf222e', backgroundColor: 'rgba(207,34,46,0.12)' };
    }
    return { color: 'inherit' };
  };

  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 1.5,
        fontFamily: '"Roboto Mono", "Courier New", monospace',
        fontSize: 13,
        lineHeight: 1.6,
        overflowX: 'auto',
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
      }}
    >
      {lines.map((line, idx) => (
        <Box key={idx} component="div" sx={{ whiteSpace: 'pre', ...styleFor(line) }}>
          {line.length === 0 ? ' ' : line}
        </Box>
      ))}
    </Box>
  );
}

export default DiffViewer;
