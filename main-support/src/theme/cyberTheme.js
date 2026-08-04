import { createTheme } from '@mui/material/styles';

// サイバー/ネオン系ダークテーマ。
// シアン(#00eaff)とマゼンタ(#ff2fd0)をアクセントに、
// 背景は深いネイビー、パネルはうっすら発光する枠線を持つ。
const cyberTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#00eaff', contrastText: '#04080f' },
    secondary: { main: '#ff2fd0' },
    background: {
      default: '#070b12',
      paper: '#0e1420',
    },
    success: { main: '#39ff9d' },
    error: { main: '#ff4d6d' },
    warning: { main: '#ffd166' },
    text: {
      primary: '#e6f7ff',
      secondary: '#7f93ab',
    },
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
        paper: {
          backgroundColor: '#0b111c',
          borderRight: '1px solid rgba(0,234,255,0.12)',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid rgba(0,234,255,0.10)',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        containedPrimary: {
          boxShadow: '0 0 12px rgba(0,234,255,0.35)',
          '&:hover': { boxShadow: '0 0 18px rgba(0,234,255,0.55)' },
        },
        outlined: {
          borderColor: 'rgba(0,234,255,0.4)',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        outlined: {
          borderColor: 'rgba(0,234,255,0.5)',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          color: '#00eaff',
          fontWeight: 700,
          borderBottom: '1px solid rgba(0,234,255,0.25)',
        },
        root: {
          borderBottom: '1px solid rgba(255,255,255,0.06)',
        },
      },
    },
  },
});

export default cyberTheme;
