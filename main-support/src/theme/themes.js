import { createTheme } from '@mui/material/styles';

// ------------------------------------------------------------------
// ライト（最初のデザインに近い、素のMUIライトテーマ）
// ------------------------------------------------------------------
export const lightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1976d2' },
    secondary: { main: '#9c27b0' },
    background: { default: '#f5f6f8', paper: '#ffffff' },
  },
  typography: {
    fontFamily: ['"Roboto"', '"Noto Sans JP"', 'Helvetica', 'Arial', 'sans-serif'].join(','),
  },
  shape: { borderRadius: 6 },
});

// ------------------------------------------------------------------
// サイバー（ネオン系ダーク）
// ------------------------------------------------------------------
export const cyberTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#00eaff', contrastText: '#04080f' },
    secondary: { main: '#ff2fd0' },
    background: { default: '#070b12', paper: '#0e1420' },
    success: { main: '#39ff9d' },
    error: { main: '#ff4d6d' },
    warning: { main: '#ffd166' },
    text: { primary: '#e6f7ff', secondary: '#7f93ab' },
    divider: 'rgba(0, 234, 255, 0.12)',
  },
  typography: {
    fontFamily: [
      '"Share Tech Mono"', '"Roboto Mono"', 'Consolas',
      '"Noto Sans JP"', 'Roboto', '"Meiryo"', 'sans-serif',
    ].join(','),
    h4: { fontWeight: 700, letterSpacing: 1 },
    h5: { fontWeight: 700, letterSpacing: 0.5 },
    h6: { fontWeight: 700, letterSpacing: 0.5 },
    button: { textTransform: 'none', fontWeight: 700, letterSpacing: 0.5 },
  },
  shape: { borderRadius: 6 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundImage:
            'radial-gradient(circle at 10% 0%, rgba(0,234,255,0.06), transparent 40%),' +
            'radial-gradient(circle at 90% 100%, rgba(255,47,208,0.05), transparent 40%)',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#0b111c',
          borderBottom: '1px solid rgba(0,234,255,0.18)',
          boxShadow: '0 0 18px rgba(0,234,255,0.08)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: { backgroundColor: '#0b111c', borderRight: '1px solid rgba(0,234,255,0.12)' },
      },
    },
    MuiPaper: {
      styleOverrides: { root: { backgroundImage: 'none', border: '1px solid rgba(0,234,255,0.10)' } },
    },
    MuiButton: {
      styleOverrides: {
        containedPrimary: {
          boxShadow: '0 0 12px rgba(0,234,255,0.35)',
          '&:hover': { boxShadow: '0 0 18px rgba(0,234,255,0.55)' },
        },
        outlined: { borderColor: 'rgba(0,234,255,0.4)' },
      },
    },
    MuiChip: { styleOverrides: { outlined: { borderColor: 'rgba(0,234,255,0.5)' } } },
    MuiTableCell: {
      styleOverrides: {
        head: { color: '#00eaff', fontWeight: 700, borderBottom: '1px solid rgba(0,234,255,0.25)' },
        root: { borderBottom: '1px solid rgba(255,255,255,0.06)' },
      },
    },
  },
});

// ------------------------------------------------------------------
// Slack風（紫のサイドバー・明るいコンテンツ領域）
// ------------------------------------------------------------------
export const slackTheme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#611f69' },
    secondary: { main: '#1264a3' },
    background: { default: '#f8f8f8', paper: '#ffffff' },
    success: { main: '#2eb67d' },
    error: { main: '#e01e5a' },
    warning: { main: '#ecb22e' },
  },
  typography: {
    fontFamily: ['"Lato"', '"Helvetica Neue"', 'Arial', '"Noto Sans JP"', 'sans-serif'].join(','),
    h4: { fontWeight: 800 },
    h5: { fontWeight: 800 },
    h6: { fontWeight: 800 },
    button: { textTransform: 'none', fontWeight: 700 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: { backgroundColor: '#350d36', color: '#ffffff', boxShadow: 'none' },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: { backgroundColor: '#3f0e40', color: '#d1c7d1' },
      },
    },
    MuiListItemText: {
      styleOverrides: { primary: { fontWeight: 600 } },
    },
    MuiPaper: {
      styleOverrides: { root: { border: '1px solid #e2e2e2' } },
    },
    MuiButton: {
      styleOverrides: { root: { borderRadius: 6 } },
    },
  },
});

// ------------------------------------------------------------------
// Discord風（ダーク、ブルー系アクセント）
// ------------------------------------------------------------------
export const discordTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#5865F2' },
    secondary: { main: '#57F287' },
    background: { default: '#313338', paper: '#2b2d31' },
    success: { main: '#57F287' },
    error: { main: '#ED4245' },
    warning: { main: '#FEE75C' },
    text: { primary: '#f2f3f5', secondary: '#949ba4' },
  },
  typography: {
    fontFamily: ['"gg sans"', '"Whitney"', '"Helvetica Neue"', 'Roboto', '"Noto Sans JP"', 'sans-serif'].join(','),
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 700 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiAppBar: {
      styleOverrides: { root: { backgroundColor: '#1e1f22', boxShadow: 'none' } },
    },
    MuiDrawer: {
      styleOverrides: { paper: { backgroundColor: '#2b2d31', borderRight: '1px solid #1e1f22' } },
    },
    MuiPaper: {
      styleOverrides: { root: { backgroundImage: 'none', border: '1px solid rgba(255,255,255,0.06)' } },
    },
    MuiButton: {
      styleOverrides: {
        containedPrimary: { boxShadow: 'none', '&:hover': { backgroundColor: '#4752c4' } },
      },
    },
  },
});

export const THEME_OPTIONS = [
  { id: 'light', label: 'ライト', theme: lightTheme },
  { id: 'cyber', label: 'サイバー(ダーク)', theme: cyberTheme },
  { id: 'slack', label: 'Slack風', theme: slackTheme },
  { id: 'discord', label: 'Discord風', theme: discordTheme },
];

export const DEFAULT_THEME_ID = 'cyber';
