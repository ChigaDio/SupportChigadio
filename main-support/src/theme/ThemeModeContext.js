import React, { createContext, useContext, useState, useEffect } from 'react';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { THEME_OPTIONS, DEFAULT_THEME_ID } from './themes';

const ThemeModeContext = createContext(null);
const STORAGE_KEY = 'unityDataTool.themeId';

function loadInitialThemeId() {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved && THEME_OPTIONS.some((t) => t.id === saved)) return saved;
  } catch (e) {
    // localStorageが使えない環境ではデフォルトにフォールバック
  }
  return DEFAULT_THEME_ID;
}

export function ThemeModeProvider({ children }) {
  const [themeId, setThemeId] = useState(loadInitialThemeId);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, themeId);
    } catch (e) {
      // 保存できなくても致命的ではないため無視
    }
  }, [themeId]);

  const current = THEME_OPTIONS.find((t) => t.id === themeId) || THEME_OPTIONS[0];

  return (
    <ThemeModeContext.Provider value={{ themeId, setThemeId, options: THEME_OPTIONS }}>
      <ThemeProvider theme={current.theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ThemeModeContext.Provider>
  );
}

export function useThemeMode() {
  const ctx = useContext(ThemeModeContext);
  if (!ctx) {
    throw new Error('useThemeMode は ThemeModeProvider の内側で使用してください');
  }
  return ctx;
}
