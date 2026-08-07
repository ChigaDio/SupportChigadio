import React, { useState } from 'react';
import { Box, Checkbox, Collapse, IconButton, TextField, Typography, InputAdornment } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import SearchIcon from '@mui/icons-material/Search';

// node: {
//   id: string,
//   label: string,
//   checked: true | false | 'indeterminate',
//   disabled?: boolean,
//   badge?: ReactNode,
//   onToggle?: (checked: boolean) => void,
//   children?: node[],
// }

function matchesQuery(node, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  if (node.label.toLowerCase().includes(q)) return true;
  if (node.children) return node.children.some((c) => matchesQuery(c, query));
  return false;
}

function TreeNode({ node, depth, query }) {
  const [open, setOpen] = useState(true);
  if (!matchesQuery(node, query)) return null;
  const hasChildren = node.children && node.children.length > 0;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', pl: depth * 2.5, py: 0.2 }}>
        {hasChildren ? (
          <IconButton size="small" onClick={() => setOpen((v) => !v)} sx={{ mr: 0.5 }}>
            {open ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
          </IconButton>
        ) : (
          <Box sx={{ width: 32, flexShrink: 0 }} />
        )}
        <Checkbox
          size="small"
          checked={node.checked === true}
          indeterminate={node.checked === 'indeterminate'}
          disabled={node.disabled}
          onChange={(e) => node.onToggle && node.onToggle(e.target.checked)}
        />
        <Typography
          variant="body2"
          sx={{ flexGrow: 1, fontWeight: hasChildren ? 700 : 400, opacity: node.disabled ? 0.5 : 1 }}
        >
          {node.label}
        </Typography>
        {node.badge}
      </Box>
      {hasChildren && (
        <Collapse in={open}>
          {node.children.map((c) => (
            <TreeNode key={c.id} node={c} depth={depth + 1} query={query} />
          ))}
        </Collapse>
      )}
    </Box>
  );
}

function CheckboxTree({ nodes, searchPlaceholder = '検索...', maxHeight = 420, emptyLabel = '対象がありません' }) {
  const [query, setQuery] = useState('');

  const visibleCount = nodes.filter((n) => matchesQuery(n, query)).length;

  return (
    <Box>
      <TextField
        size="small"
        fullWidth
        placeholder={searchPlaceholder}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>
          ),
        }}
        sx={{ mb: 1 }}
      />
      <Box sx={{
        maxHeight, overflowY: 'auto', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 1, p: 1,
      }}>
        {nodes.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>{emptyLabel}</Typography>
        ) : visibleCount === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>検索結果がありません</Typography>
        ) : (
          nodes.map((n) => <TreeNode key={n.id} node={n} depth={0} query={query} />)
        )}
      </Box>
    </Box>
  );
}

export default CheckboxTree;
