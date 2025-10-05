import React, { useState, useEffect } from 'react';
import {
  Container,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  TextField,
  Button,
  Box,
  Chip,
  Paper,
  Grid,
  Alert,
  AlertTitle,
} from '@mui/material';
import {
  Info as InfoIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  Clear as ClearIcon,
} from '@mui/icons-material';
import { styled } from '@mui/material/styles';

// Custom styled components for a modern look
const StyledContainer = styled(Container)(({ theme }) => ({
  marginTop: theme.spacing(4),
  padding: theme.spacing(3),
  backgroundColor: '#f9fafb',
  borderRadius: '12px',
  boxShadow: '0 4px 20px rgba(0, 0, 0, 0.05)',
}));

const StyledList = styled(List)(({ theme }) => ({
  maxHeight: '60vh',
  overflowY: 'auto',
  backgroundColor: '#ffffff',
  borderRadius: '8px',
  border: `1px solid ${theme.palette.divider}`,
}));

const StyledListItem = styled(ListItem)(({ theme, logType }) => ({
  transition: 'background-color 0.3s ease',
  '&:hover': {
    backgroundColor: theme.palette.action.hover,
  },
  ...(logType === 'error' && {
    backgroundColor: '#fff5f5',
    color: theme.palette.error.main,
  }),
  ...(logType === 'warning' && {
    backgroundColor: '#fffbf0',
    color: theme.palette.warning.main,
  }),
  ...(logType === 'log' && {
    color: theme.palette.info.main,
  }),
}));

const HeaderBox = styled(Box)(({ theme }) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: theme.spacing(2),
}));

const CountChip = styled(Chip)(({ theme, color }) => ({
  marginRight: theme.spacing(1),
  fontWeight: 'bold',
}));

function App() {
  const [logs, setLogs] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [counts, setCounts] = useState({ total: 0, error: 0, warning: 0, log: 0 });

  useEffect(() => {
    // Create WebSocket connection
    const socket = new WebSocket('ws://localhost:8765');

    // Handle incoming messages
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      // Assume type is 'log', 'error', or 'warning' (lowercase)
      setLogs((prevLogs) => {
        const newLogs = [...prevLogs, { id: prevLogs.length, ...message }];
        // Limit to max 1000 logs
        if (newLogs.length > 1000) {
          newLogs.shift(); // Remove oldest log
        }
        return newLogs;
      });
    };

    // Update counts whenever logs change
    const updateCounts = () => {
      const errorCount = logs.filter((log) => log.type === 'error').length;
      const warningCount = logs.filter((log) => log.type === 'warning').length;
      const logCount = logs.filter((log) => log.type === 'log').length;
      setCounts({
        total: logs.length,
        error: errorCount,
        warning: warningCount,
        log: logCount,
      });
    };

    updateCounts();

    // Handle connection open
    socket.onopen = () => {
      console.log('Connected to WebSocket server');
    };

    // Handle connection close
    socket.onclose = () => {
      console.log('Disconnected from WebSocket server');
    };

    // Handle errors
    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    // Cleanup on component unmount
    return () => {
      socket.close();
      updateCounts();
    };
  }, [logs]); // Re-run updateCounts when logs change

  // Clear logs
  const handleClear = () => {
    setLogs([]);
  };

  // Filtered logs based on search
  const filteredLogs = logs.filter(
    (log) =>
      log.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.type.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Get icon and color based on type
  const getIcon = (type) => {
    switch (type) {
      case 'error':
        return <ErrorIcon color="error" />;
      case 'warning':
        return <WarningIcon color="warning" />;
      case 'log':
      default:
        return <InfoIcon color="info" />;
    }
  };

  return (
    <StyledContainer maxWidth="md">
      <Typography variant="h4" component="h1" gutterBottom align="center" color="primary">
        Debug Logs Dashboard
      </Typography>

      <HeaderBox>
        <Box>
          <CountChip label={`Total: ${counts.total}`} color="default" variant="outlined" />
          <CountChip label={`Errors: ${counts.error}`} color="error" variant="outlined" />
          <CountChip label={`Warnings: ${counts.warning}`} color="warning" variant="outlined" />
          <CountChip label={`Logs: ${counts.log}`} color="info" variant="outlined" />
        </Box>
        <Button variant="contained" color="secondary" startIcon={<ClearIcon />} onClick={handleClear}>
          Clear Logs
        </Button>
      </HeaderBox>

      <TextField
        fullWidth
        variant="outlined"
        label="Search Logs"
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        sx={{ marginBottom: 2 }}
      />

      {filteredLogs.length === 0 ? (
        <Alert severity="info">
          <AlertTitle>No Logs Found</AlertTitle>
          No logs match your search or no logs available yet.
        </Alert>
      ) : (
        <Paper elevation={3}>
          <StyledList>
            {filteredLogs.map((log) => (
              <React.Fragment key={log.id}>
                <StyledListItem logType={log.type}>
                  <ListItemIcon>{getIcon(log.type)}</ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                        [{log.type.toUpperCase()}] {log.message}
                      </Typography>
                    }
                    secondary={
                      <Typography variant="caption" color="textSecondary">
                        {log.time}
                      </Typography>
                    }
                  />
                </StyledListItem>
                <Divider />
              </React.Fragment>
            ))}
          </StyledList>
        </Paper>
      )}
    </StyledContainer>
  );
}

export default App;