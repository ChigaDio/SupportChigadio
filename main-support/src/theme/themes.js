import { createTheme } from '@mui/material/styles';

// ------------------------------------------------------------------
// 「マテリアルデザインっぽさ」を消すための共通コンポーネント上書き。
// 影(elevation)・リップル・丸みの強い角丸をやめて、枠線ベースのフラットな
// 見た目に統一する。DataGrid（Grid系画面）やフォーム部品もここで一括して
// テーマの配色に追従させる。新しいテーマを増やすときは、色とradiusだけ
// 渡してこの関数を呼べば同じ非マテリアル基調のテーマになる。
// ------------------------------------------------------------------
function buildFlatComponents({
  bg,
  paper,
  border,
  text,
  accent,
  accentContrast,
  radius,
  headerBg,
  headerText,
  hoverBg,
  selectedBg,
  uppercaseHeader = false,
  fontFamily = null,
}) {
  return {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: bg,
          ...(fontFamily ? { fontFamily } : {}),
        },
      },
    },
    // リップルエフェクトを消す（マテリアル感の大きな要因の一つ）
    MuiButtonBase: { defaultProps: { disableRipple: true } },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: radius,
          boxShadow: 'none',
          textTransform: 'none',
          fontWeight: 600,
          ...(fontFamily ? { fontFamily } : {}),
        },
        containedPrimary: {
          backgroundColor: accent,
          color: accentContrast,
          boxShadow: 'none',
          '&:hover': { backgroundColor: accent, opacity: 0.85, boxShadow: 'none' },
        },
        outlined: {
          borderColor: border,
          color: text,
          '&:hover': { backgroundColor: hoverBg, borderColor: accent },
        },
        text: { '&:hover': { backgroundColor: hoverBg } },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          boxShadow: 'none',
          border: `1px solid ${border}`,
          borderRadius: radius,
          backgroundColor: paper,
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: { backgroundColor: paper, color: text, boxShadow: 'none', borderBottom: `1px solid ${border}` },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: { backgroundColor: paper, borderRight: `1px solid ${border}` },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: radius, border: `1px solid ${border}`, boxShadow: 'none', backgroundImage: 'none' },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: radius === 0 ? 0 : 999 },
        outlined: { borderColor: border },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: { borderRadius: radius },
        notchedOutline: { borderColor: border },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 700,
          borderBottom: `2px solid ${border}`,
          color: text,
          textTransform: uppercaseHeader ? 'uppercase' : 'none',
          letterSpacing: uppercaseHeader ? 0.5 : 0,
        },
        root: { borderBottom: `1px solid ${border}` },
      },
    },
    // DataGrid（各種一覧・データ入力Grid）もテーマ配色に追従させる
    MuiDataGrid: {
      styleOverrides: {
        root: {
          border: `1px solid ${border}`,
          borderRadius: radius,
          backgroundColor: paper,
          ...(fontFamily ? { fontFamily } : {}),
          '--DataGrid-rowBorderColor': border,
          '& .MuiDataGrid-columnHeaders': {
            backgroundColor: headerBg,
            color: headerText,
            textTransform: uppercaseHeader ? 'uppercase' : 'none',
            letterSpacing: uppercaseHeader ? 0.5 : 0,
          },
          '& .MuiDataGrid-columnHeaderTitle': { fontWeight: 700 },
          '& .MuiDataGrid-cell': { borderColor: border },
          '& .MuiDataGrid-cell:focus, & .MuiDataGrid-cell:focus-within': { outline: `1px solid ${accent}` },
          '& .MuiDataGrid-row:hover': { backgroundColor: hoverBg },
          '& .MuiDataGrid-row.Mui-selected': { backgroundColor: selectedBg },
          '& .MuiDataGrid-row.Mui-selected:hover': { backgroundColor: selectedBg },
          '& .MuiDataGrid-footerContainer': { borderTop: `1px solid ${border}` },
          '& .MuiDataGrid-columnSeparator': { color: border },
        },
      },
    },
  };
}

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

// ------------------------------------------------------------------
// モノトーン（白黒グレーのみ・角丸なし・影なしのフラットデザイン）
// Grid/フォームも含めてマテリアル感を排した、輪郭線ベースの見た目。
// ------------------------------------------------------------------
export const monotoneTheme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#111111', contrastText: '#ffffff' },
    secondary: { main: '#555555', contrastText: '#ffffff' },
    background: { default: '#fafafa', paper: '#ffffff' },
    success: { main: '#2e7d32' },
    error: { main: '#c62828' },
    warning: { main: '#a17700' },
    text: { primary: '#111111', secondary: '#666666' },
    divider: 'rgba(0, 0, 0, 0.18)',
  },
  typography: {
    // 装飾のない無機質なタイポグラフィ。Webフォントの追加読み込みなしでも
    // 狙った見た目になるよう、OS標準の等幅フォントを優先したスタック。
    // （"IBM Plex Mono"はインストールされていれば使われる程度の位置づけ）
    fontFamily: [
      '"IBM Plex Mono"', 'Menlo', 'Monaco', 'Consolas', '"Courier New"',
      '"Noto Sans JP"', 'monospace',
    ].join(','),
    h4: { fontWeight: 700, letterSpacing: 1.5, textTransform: 'uppercase' },
    h5: { fontWeight: 700, letterSpacing: 1 },
    h6: { fontWeight: 700, letterSpacing: 0.5 },
    subtitle1: { letterSpacing: 0.3 },
    body1: { letterSpacing: 0.1 },
    button: { fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1 },
    caption: { letterSpacing: 0.3 },
  },
  shape: { borderRadius: 0 },
  components: buildFlatComponents({
    bg: '#fafafa',
    paper: '#ffffff',
    border: 'rgba(0, 0, 0, 0.25)',
    text: '#111111',
    accent: '#111111',
    accentContrast: '#ffffff',
    radius: 0,
    headerBg: '#111111',
    headerText: '#ffffff',
    hoverBg: 'rgba(0, 0, 0, 0.05)',
    selectedBg: 'rgba(0, 0, 0, 0.10)',
    uppercaseHeader: true,
    fontFamily: [
      '"IBM Plex Mono"', 'Menlo', 'Monaco', 'Consolas', '"Courier New"',
      '"Noto Sans JP"', 'monospace',
    ].join(','),
  }),
});

// ------------------------------------------------------------------
// フラット（ミニマル）：淡いオフホワイト＋差し色1色、影なしの軽いデザイン
// ------------------------------------------------------------------
export const flatTheme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#2f6fed', contrastText: '#ffffff' },
    secondary: { main: '#0f9d8c' },
    background: { default: '#f6f7f9', paper: '#ffffff' },
    success: { main: '#2f9e44' },
    error: { main: '#e03131' },
    warning: { main: '#e8890c' },
    text: { primary: '#20242c', secondary: '#6b7280' },
    divider: 'rgba(15, 23, 42, 0.08)',
  },
  typography: {
    fontFamily: ['"Inter"', '"Noto Sans JP"', 'Roboto', 'Arial', 'sans-serif'].join(','),
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 700 },
    button: { fontWeight: 600, textTransform: 'none' },
  },
  shape: { borderRadius: 10 },
  components: buildFlatComponents({
    bg: '#f6f7f9',
    paper: '#ffffff',
    border: 'rgba(15, 23, 42, 0.10)',
    text: '#20242c',
    accent: '#2f6fed',
    accentContrast: '#ffffff',
    radius: 10,
    headerBg: '#f1f3f6',
    headerText: '#20242c',
    hoverBg: 'rgba(47, 111, 237, 0.06)',
    selectedBg: 'rgba(47, 111, 237, 0.12)',
    uppercaseHeader: false,
  }),
});

export const THEME_OPTIONS = [
  { id: 'light', label: 'ライト', theme: lightTheme },
  { id: 'cyber', label: 'サイバー(ダーク)', theme: cyberTheme },
  { id: 'slack', label: 'Slack風', theme: slackTheme },
  { id: 'discord', label: 'Discord風', theme: discordTheme },
  { id: 'monotone', label: 'モノトーン', theme: monotoneTheme },
  { id: 'flat', label: 'フラット(ミニマル)', theme: flatTheme },
];

export const DEFAULT_THEME_ID = 'cyber';
