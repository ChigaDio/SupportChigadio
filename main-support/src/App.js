import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate } from 'react-router-dom';
import { Box } from '@mui/material';
import Sidebar from './components/Sidebar';
import Content from './components/Content';
import EnumIdGrid from './components/EnumIdGrid';
import EnumDetailGrid from './components/EnumDetailGrid';
import ClassDataGrid from './components/ClassDataGrid';
import ClassDataDetailGrid from './components/ClassDataDetailGrid';

import StateGrid from './components/StateGrid';
import StateDetailGridGrid from './components/StateDetailGrid';
import ClassDataIdGrid from './components/ClassDataIdGrid';
import ClassDataIdDetailGrid from './components/ClassDataIdDetailGrid';

import ClassDataMatrinxIdGrid from './components/ClassDataMatrixIdGrid';
import ClassDataMatrinxIdDetailGrid from './components/ClassDataMatrixIdDetailGrid';

function AppContent() {
  const navigate = useNavigate();
  const [selectedMenu, setSelectedMenu] = useState('GenerateTool');

  // メニュークリックハンドラ
  const handleMenuClick = (menu, subMenu) => {
    setSelectedMenu(menu);
    console.log('Menu clicked:', menu, 'SubMenu:', subMenu);
    if (menu === 'GenerateTool' && subMenu) {
      switch (subMenu) {
        case 'enum-id':
          navigate('/enum-id');
          break;
        case 'class-data':
          navigate('/class-data');
          break;
        case 'class-data-id':
          navigate('/class-data-id');
          break;
          case 'class-data-matrix-id':
          navigate('/class-data-matrix-id');
          break;
        case 'state':
          navigate('/state');
          break;
        default:
          navigate('/enum-id'); // GenerateToolのデフォルト
      }
    } else {
      navigate('/');
    }
  };

  return (
    <Box sx={{ display: 'flex' }}>
      <Sidebar selectedMenu={selectedMenu} handleMenuClick={handleMenuClick} />
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Routes>
          <Route path="/" element={<Content />} />
          <Route path="/enum-id" element={<EnumIdGrid />} />
          <Route path="/enum/:name" element={<EnumDetailGrid />} />
          <Route path="/class-data" element={<ClassDataGrid />} />
          <Route path="/class/:name" element={<ClassDataDetailGrid />} />
          <Route path="/class-data-id" element={<ClassDataIdGrid />} />
          <Route path="/class-data-id/:name" element={<ClassDataIdDetailGrid />} />
          <Route path="/class-data-matrix-id" element={<ClassDataMatrinxIdGrid />} />
          <Route path="/class-data-matrix-id/:name" element={<ClassDataMatrinxIdDetailGrid />} />
          <Route path="/state" element={<StateGrid />} />
          <Route path="/state/:name" element={<StateDetailGridGrid />} />
        </Routes>
      </Box>
    </Box>
  );
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;