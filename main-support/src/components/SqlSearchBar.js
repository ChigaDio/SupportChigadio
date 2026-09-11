import React, { useMemo, useRef, useState } from 'react';
import {
  Box, TextField, Paper, MenuList, MenuItem, Typography, InputAdornment, Tooltip,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import { getSuggestions } from './sqlLikeSearch';

// SQLのWHERE句に近い構文で検索できる検索バー。
// - fieldNames: 予測変換で出すカラム名/識別子一覧
// - valuesByField: { フィールド名: [候補値, ...] } 値側の予測変換（Enum等）
// - onQueryChange(text): クエリ文字列が変わるたびに呼ばれる（実際のフィルタは呼び出し側で行う）
// - error: 呼び出し側で compileQuery した結果のエラーメッセージ（構文エラー表示用）
// - placeholder: プレースホルダ文言
function SqlSearchBar({ value, onChange, fieldNames = [], valuesByField = {}, error, placeholder, sx }) {
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const inputRef = useRef(null);
  const [cursorPos, setCursorPos] = useState(0);

  const suggestions = useMemo(() => {
    if (!suggestOpen) return [];
    return getSuggestions(value || '', cursorPos, { fieldNames, valuesByField }).slice(0, 20);
  }, [suggestOpen, value, cursorPos, fieldNames, valuesByField]);

  const applySuggestion = (label) => {
    const before = (value || '').slice(0, cursorPos);
    const after = (value || '').slice(cursorPos);
    // 現在入力中の単語（識別子の途中）を候補で置き換える
    const wordMatch = before.match(/[A-Za-z0-9_."']*$/);
    const wordStart = wordMatch ? before.length - wordMatch[0].length : before.length;
    const next = before.slice(0, wordStart) + label + ' ' + after;
    onChange(next);
    const newCursor = (before.slice(0, wordStart) + label + ' ').length;
    requestAnimationFrame(() => {
      if (inputRef.current) {
        inputRef.current.setSelectionRange(newCursor, newCursor);
        inputRef.current.focus();
      }
      setCursorPos(newCursor);
    });
    setHighlightIndex(0);
  };

  const handleChange = (e) => {
    onChange(e.target.value);
    setCursorPos(e.target.selectionStart ?? e.target.value.length);
    setSuggestOpen(true);
  };

  const handleKeyDown = (e) => {
    if (!suggestOpen || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      applySuggestion(suggestions[highlightIndex].label);
    } else if (e.key === 'Escape') {
      setSuggestOpen(false);
    }
  };

  return (
    <Box sx={{ position: 'relative', ...sx }}>
      <TextField
        inputRef={inputRef}
        fullWidth
        size="small"
        value={value || ''}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onClick={(e) => setCursorPos(e.target.selectionStart ?? 0)}
        onFocus={() => setSuggestOpen(true)}
        onBlur={() => setTimeout(() => setSuggestOpen(false), 150)}
        placeholder={placeholder || '例: hp > 100 AND rarity = "SR"'}
        error={!!error}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>
          ),
          endAdornment: error ? (
            <InputAdornment position="end">
              <Tooltip title={error}><ErrorOutlineIcon color="error" fontSize="small" /></Tooltip>
            </InputAdornment>
          ) : undefined,
        }}
      />
      {suggestOpen && suggestions.length > 0 && (
        <Paper
          sx={{
            position: 'absolute', zIndex: 20, mt: 0.5, width: '100%', maxHeight: 260, overflowY: 'auto',
          }}
        >
          <MenuList dense>
            {suggestions.map((s, idx) => (
              <MenuItem
                key={`${s.kind}-${s.label}-${idx}`}
                selected={idx === highlightIndex}
                onMouseDown={(e) => { e.preventDefault(); applySuggestion(s.label); }}
              >
                <Typography variant="body2" sx={{ fontFamily: '"Roboto Mono", monospace', mr: 1 }}>
                  {s.label}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {{ field: 'カラム', operator: '演算子', keyword: 'キーワード', value: '値', paren: '' }[s.kind]}
                </Typography>
              </MenuItem>
            ))}
          </MenuList>
        </Paper>
      )}
    </Box>
  );
}

export default SqlSearchBar;
