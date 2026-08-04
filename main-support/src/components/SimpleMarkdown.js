import React from 'react';
import { Box, Typography } from '@mui/material';

// 外部ライブラリに依存しない最小限のMarkdownレンダラー。
// 見出し(#〜######)、太字、イタリック、インラインコード、コードブロック、
// リンク、箇条書き、番号付きリストに対応。
function renderInline(text, keyPrefix) {
  const parts = [];
  let remaining = text;
  let key = 0;
  const pattern = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\((.+?)\))/;
  while (remaining.length > 0) {
    const match = remaining.match(pattern);
    if (!match) {
      parts.push(remaining);
      break;
    }
    const idx = match.index;
    if (idx > 0) parts.push(remaining.slice(0, idx));
    if (match[2] !== undefined) {
      parts.push(<b key={`${keyPrefix}-${key++}`}>{match[2]}</b>);
    } else if (match[3] !== undefined) {
      parts.push(<i key={`${keyPrefix}-${key++}`}>{match[3]}</i>);
    } else if (match[4] !== undefined) {
      parts.push(<code key={`${keyPrefix}-${key++}`} style={{ background: '#f0f0f0', padding: '0 4px', borderRadius: 4 }}>{match[4]}</code>);
    } else if (match[5] !== undefined) {
      parts.push(<a key={`${keyPrefix}-${key++}`} href={match[6]} target="_blank" rel="noreferrer">{match[5]}</a>);
    }
    remaining = remaining.slice(idx + match[0].length);
  }
  return parts;
}

function SimpleMarkdown({ source }) {
  const lines = (source || '').split('\n');
  const blocks = [];
  let i = 0;
  let listBuffer = [];
  let listType = null;

  const flushList = () => {
    if (listBuffer.length === 0) return;
    const Tag = listType === 'ol' ? 'ol' : 'ul';
    blocks.push(
      <Tag key={`list-${blocks.length}`}>
        {listBuffer.map((item, idx) => <li key={idx}>{renderInline(item, `li-${blocks.length}-${idx}`)}</li>)}
      </Tag>
    );
    listBuffer = [];
    listType = null;
  };

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim().startsWith('```')) {
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      flushList();
      blocks.push(
        <Box component="pre" key={`code-${blocks.length}`}
          sx={{ background: '#272822', color: '#f8f8f2', p: 2, borderRadius: 1, overflowX: 'auto' }}>
          <code>{codeLines.join('\n')}</code>
        </Box>
      );
      i++;
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushList();
      const level = headingMatch[1].length;
      const variant = ['h4', 'h5', 'h6', 'subtitle1', 'subtitle2', 'body1'][level - 1];
      blocks.push(
        <Typography key={`h-${blocks.length}`} variant={variant} sx={{ mt: 2, mb: 1, fontWeight: 'bold' }}>
          {renderInline(headingMatch[2], `h-${blocks.length}`)}
        </Typography>
      );
      i++;
      continue;
    }

    const ulMatch = line.match(/^\s*[-*]\s+(.*)$/);
    const olMatch = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ulMatch) {
      if (listType && listType !== 'ul') flushList();
      listType = 'ul';
      listBuffer.push(ulMatch[1]);
      i++;
      continue;
    }
    if (olMatch) {
      if (listType && listType !== 'ol') flushList();
      listType = 'ol';
      listBuffer.push(olMatch[1]);
      i++;
      continue;
    }

    flushList();
    if (line.trim() === '') {
      i++;
      continue;
    }
    blocks.push(
      <Typography key={`p-${blocks.length}`} variant="body1" sx={{ mb: 1 }}>
        {renderInline(line, `p-${blocks.length}`)}
      </Typography>
    );
    i++;
  }
  flushList();

  return <Box>{blocks}</Box>;
}

export default SimpleMarkdown;
