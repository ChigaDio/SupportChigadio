import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AppBar, Toolbar, Typography, CssBaseline, Box } from '@mui/material';
import Sidebar from './components/Sidebar';
import Content from './components/Content';
import EnumDetailGrid from './components/EnumDetailGrid';

function App() {
  const [selectedMenu, setSelectedMenu] = useState('Main');

  return (
    <Router>
      <Box sx={{ display: 'flex' }}>
        <CssBaseline />
        <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
          <Toolbar>
            <Typography variant="h6" noWrap component="div">
              My Dashboard
            </Typography>
          </Toolbar>
        </AppBar>
        <Sidebar onMenuSelect={setSelectedMenu} />
        <Routes>
          <Route path="/" element={<Content selectedMenu={selectedMenu} />} />
          <Route path="/enum/:name" element={<EnumDetailGrid />} />
        </Routes>
      </Box>
    </Router>
  );
}

export default App;