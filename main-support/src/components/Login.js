import React, { useState } from 'react';
import { Box, Paper, TextField, Button, Typography, Alert } from '@mui/material';
import { keyframes } from '@mui/system';
import { useAuth } from '../context/AuthContext';
import { useThemeMode } from '../theme/ThemeModeContext';
import ThemeSwitcher from './ThemeSwitcher';

const gridMove = keyframes`
  from { background-position: 0 0; }
  to { background-position: 0 48px; }
`;

const scan = keyframes`
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100%); }
`;

const glow = keyframes`
  0%, 100% { box-shadow: 0 0 24px rgba(0,234,255,0.25), 0 0 60px rgba(255,47,208,0.08); }
  50% { box-shadow: 0 0 36px rgba(0,234,255,0.45), 0 0 90px rgba(255,47,208,0.18); }
`;

function Login() {
  const { login } = useAuth();
  const { themeId } = useThemeMode();
  const isCyber = themeId === 'cyber';
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const form = (
    <Box component="form" onSubmit={handleSubmit}>
      <TextField
        label="ID"
        fullWidth
        margin="dense"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoFocus
        InputProps={isCyber ? { sx: { fontFamily: '"Share Tech Mono", monospace' } } : undefined}
      />
      <TextField
        label="パスワード"
        type="password"
        fullWidth
        margin="dense"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        InputProps={isCyber ? { sx: { fontFamily: '"Share Tech Mono", monospace' } } : undefined}
      />
      <Button
        type="submit"
        variant="contained"
        fullWidth
        sx={{ mt: 3, py: 1.2, fontSize: '0.95rem', letterSpacing: isCyber ? 2 : 0.5 }}
        disabled={submitting || !username || !password}
      >
        {submitting ? (isCyber ? 'CONNECTING...' : 'ログイン中...') : (isCyber ? 'ACCESS' : 'ログイン')}
      </Button>
    </Box>
  );

  return (
    <Box
      sx={{
        height: '100vh',
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        overflow: 'hidden',
        bgcolor: isCyber ? '#050810' : 'background.default',
        ...(isCyber && {
          backgroundImage:
            'linear-gradient(rgba(0,234,255,0.10) 1px, transparent 1px),' +
            'linear-gradient(90deg, rgba(0,234,255,0.10) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          animation: `${gridMove} 6s linear infinite`,
        }),
      }}
    >
      <Box sx={{ position: 'absolute', top: 16, right: 16 }}>
        <ThemeSwitcher />
      </Box>

      {isCyber && (
        <Box sx={{
          position: 'absolute', inset: 0,
          background: 'radial-gradient(circle at 50% 45%, rgba(0,234,255,0.14), transparent 55%)',
          pointerEvents: 'none',
        }} />
      )}

      <Paper
        elevation={isCyber ? 0 : 4}
        sx={{
          position: 'relative',
          p: 4,
          width: 380,
          borderRadius: 2,
          overflow: 'hidden',
          ...(isCyber
            ? {
                bgcolor: 'rgba(8,14,24,0.85)',
                border: '1px solid rgba(0,234,255,0.35)',
                backdropFilter: 'blur(6px)',
                animation: `${glow} 3.2s ease-in-out infinite`,
              }
            : {}),
        }}
      >
        {isCyber && (
          <Box sx={{
            position: 'absolute', left: 0, right: 0, height: '40%',
            background: 'linear-gradient(to bottom, transparent, rgba(0,234,255,0.10), transparent)',
            animation: `${scan} 3.5s linear infinite`,
            pointerEvents: 'none',
          }} />
        )}

        {isCyber ? (
          <>
            <Typography
              variant="h5"
              sx={{
                fontWeight: 800, letterSpacing: 3, color: '#00eaff', textAlign: 'center',
                textShadow: '0 0 12px rgba(0,234,255,0.65)', mb: 0.5,
              }}
            >
              SYSTEM LOGIN
            </Typography>
            <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', color: '#5f7386', mb: 3, letterSpacing: 1 }}>
              UNITY DATA TOOL // SERVER MODE
            </Typography>
          </>
        ) : (
          <>
            <Typography variant="h5" sx={{ fontWeight: 700, textAlign: 'center', mb: 0.5 }}>
              ログイン
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mb: 3 }}>
              Unity Data Tool（サーバーモード）
            </Typography>
          </>
        )}

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {form}
      </Paper>
    </Box>
  );
}

export default Login;
