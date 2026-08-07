import React from 'react';
import { Select, MenuItem, FormControl } from '@mui/material';
import PaletteIcon from '@mui/icons-material/Palette';
import { useThemeMode } from '../theme/ThemeModeContext';

function ThemeSwitcher({ size = 'small' }) {
  const { themeId, setThemeId, options } = useThemeMode();

  return (
    <FormControl size={size} sx={{ minWidth: 150 }}>
      <Select
        value={themeId}
        onChange={(e) => setThemeId(e.target.value)}
        displayEmpty
        renderValue={(value) => {
          const opt = options.find((o) => o.id === value);
          return (
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <PaletteIcon fontSize="small" />
              {opt ? opt.label : value}
            </span>
          );
        }}
      >
        {options.map((opt) => (
          <MenuItem key={opt.id} value={opt.id}>{opt.label}</MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

export default ThemeSwitcher;
