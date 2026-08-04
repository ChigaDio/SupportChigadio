import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate } from 'react-router-dom';
import { Box, AppBar, Toolbar, Typography, Button, CircularProgress } from '@mui/material';
import { ThemeProvider, CssBaseline } from '@mui/material';
import cyberTheme from './theme/cyberTheme';
import Sidebar from './components/Sidebar';
import Content from './components/Content';
import EnumIdGrid from './components/EnumIdGrid';
import EnumDetailGrid from './components/EnumDetailGrid';
import ConstClassDataGrid from './components/ConstClassDataGrid';
import ConstClassDataDetailGrid from './components/ConstClassDataDetailGrid';
import ClassDataGrid from './components/ClassDataGrid';
import ClassDataDetailGrid from './components/ClassDataDetailGrid';
import ClassDataIdGrid from './components/ClassDataIdGrid';
import ClassDataIdDetailGrid from './components/ClassDataIdDetailGrid';

import CustomClassDataGrid from './components/CustomClassDataGrid';
import CustomClassDataDetailGrid from './components/CustomClassDataDetailGrid';

import CustomClassDataIdGrid from './components/CustomClassDataIdGrid';
import CustomClassDataIdDetailGrid from './components/CustomClassDataIdDetailGrid';

import ClassDataMatrinxIdGrid from './components/ClassDataMatrixIdGrid';
import ClassDataMatrinxIdDetailGrid from './components/ClassDataMatrixIdDetailGrid';
import StateGrid from './components/StateGrid';
import StateDetailGridGrid from './components/StateDetailGrid';
import ScenarioRoleGrid from './components/ScenarioRoleGrid';
import ScenarioRoleDetailGrid from './components/ScenarioRoleDetailGrid';
import ScenarioEventGrid from './components/ScenarioEventGrid';
import ScenarioEventTransition from './components/ScenarioEventTransition';
import ScenarioConditionsGrid from './components/ScenarioConditionsGrid';
import BehaviorGrid from './components/BehaviorGrid';
import BehaviorDetailGrid from './components/BehaviorDetailGrid';

import AnimatorGrid from './components/AnimatorDataGrid'
import AnimatorDataDetailGrid from './components/AnimatorDataDetailGrid';
import SaveDataGrid from './components/SaveDataGrid';

import Sound from './assets/sound';
import Texture from './assets/texture';
import GameObject from './assets/gameobject';
import Material from './assets/material';
import Scene from './assets/scene';

import DbgLog from './components/DebugLog'

import DbgCommand from './components/DebugCommandConsole'

// --- サーバーモード関連の追加ページ ---
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './components/Login';
import MyPage from './components/MyPage';
import Workspace from './components/Workspace';
import AnnouncementList from './components/AnnouncementList';
import AnnouncementDetail from './components/AnnouncementDetail';
import AnnouncementEditor from './components/AnnouncementEditor';
import VersionBadge from './components/VersionBadge';

function TopBar() {
  const { user, serverMode, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <AppBar position="static" color="default" elevation={1}>
      <Toolbar sx={{ gap: 2 }}>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>Unity Data Tool</Typography>
        <VersionBadge />
        {serverMode && user && (
          <>
            <Typography variant="body2">
              {user.username}（{{ admin: '管理人', editor: '編集者', viewer: '閲覧者' }[user.role] || user.role}）
            </Typography>
            <Button size="small" onClick={() => navigate('/mypage')}>マイページ</Button>
            <Button size="small" onClick={logout}>ログアウト</Button>
          </>
        )}
      </Toolbar>
    </AppBar>
  );
}

function AppContent() {
  const navigate = useNavigate();
  const { serverMode, user, loading } = useAuth();
  const [selectedMenu, setSelectedMenu] = useState('GenerateTool');

  // Menu click handler
  const handleMenuClick = (menu, subMenu) => {
    setSelectedMenu(menu);
    console.log('Menu clicked:', menu, 'SubMenu:', subMenu);
    if (menu === 'GenerateTool' && subMenu) {
      switch (subMenu) {
        case 'enum-id':
          navigate('/enum-id');
          break;
        case 'const-class-data':
          navigate('/const-class-data');
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
        case 'custom-class-data':
          navigate('/custom-class-data');
          break;
        case 'custom-class-data-id':
          navigate('/custom-class-data-id');
          break;
        case 'state':
          navigate('/state');
          break;
        case 'behavior':
          navigate('/behavior');
          break;
        case 'save-data':
          navigate('/save-data');
          break;
        default:
          navigate('/enum-id'); // GenerateTool default
      }
    } else if (menu === 'Scenario' && subMenu) {
      switch (subMenu) {
        case 'scenario-role':
          navigate('/scenario-role');
          break;
        case 'scenario-event':
          navigate('/scenario-event');
          break;
        case 'scenario-conditions':
          navigate('/scenario-conditions');
          break;
        default:
          navigate('/scenario-role'); // Scenario default
      }
    } else if (menu === 'Assets' && subMenu) {
      switch (subMenu) {
        case 'sound':
          navigate('sound');
          break;
        case 'texture':
          navigate('texture');
          break;
        case 'gameobject':
          navigate('gameobject');
          break;
        case 'animator':
          navigate('animator');
          break;
        case 'material':
          navigate('material');
          break;
        case 'scene':
          navigate('scene');
          break;
        default:
          navigate('sound'); // Assets default
      }
    }
    else if (menu === 'Debug' && subMenu) {
      switch (subMenu) {
        case 'log':
          navigate('log');
          break;
        case 'command':
          navigate('command');
            break;
          
      }
    } else if (menu === 'Workspace') {
      navigate('/workspace');
    } else if (menu === 'Announcements') {
      navigate('/announcements');
    }
    else {
      navigate('/');
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  // サーバーモードで未ログインの場合はログイン画面のみ表示する
  if (serverMode && !user) {
    return <Login />;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <TopBar />
      <Box sx={{ display: 'flex', flexGrow: 1 }}>
        <Sidebar selectedMenu={selectedMenu} handleMenuClick={handleMenuClick} />
        <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
          <Routes>
            <Route path="/" element={<Content />} />
            <Route path="/enum-id" element={<EnumIdGrid />} />
            <Route path="/enum/:name" element={<EnumDetailGrid />} />
            <Route path="/const-class-data" element={<ConstClassDataGrid />} />
            <Route path="/const-class-data/:name" element={<ConstClassDataDetailGrid />} />
            <Route path="/class-data" element={<ClassDataGrid />} />
            <Route path="/class/:name" element={<ClassDataDetailGrid />} />
            <Route path="/class-data-id" element={<ClassDataIdGrid />} />
            <Route path="/class-data-id/:name" element={<ClassDataIdDetailGrid />} />
            <Route path="/class-data-matrix-id" element={<ClassDataMatrinxIdGrid />} />
            <Route path="/class-data-matrix-id/:name" element={<ClassDataMatrinxIdDetailGrid />} />
            <Route path="/state" element={<StateGrid />} />
            <Route path="/state/:name" element={<StateDetailGridGrid />} />
            <Route path="/behavior" element={<BehaviorGrid />} />
            <Route path="/behavior/:name" element={<BehaviorDetailGrid />} />
            <Route path="/scenario-role" element={<ScenarioRoleGrid />} />
            <Route path="/scenario-role/:name" element={<ScenarioRoleDetailGrid />} />
            <Route path="/scenario-event" element={<ScenarioEventGrid />} />
            <Route path="/scenario-event/:eventId/sub/:subId/transition" element={<ScenarioEventTransition />} />

            <Route path="/custom-class-data" element={<CustomClassDataGrid />} />
            <Route path="/custom-class-data/:name" element={<CustomClassDataDetailGrid />} />
            <Route path="/custom-class-data-id" element={<CustomClassDataIdGrid />} />
            <Route path="/custom-class-data-id/:name" element={<CustomClassDataIdDetailGrid />} />


            <Route path="/scenario-conditions" element={<ScenarioConditionsGrid />} />
            <Route path="/sound" element={<Sound />} />
            <Route path="/texture" element={<Texture />} />
            <Route path="/gameobject" element={<GameObject />} />
            <Route path='/material' element={<Material />}/>
            <Route path="/animator" element={<AnimatorGrid />} />
            <Route path="/animator/:name" element={<AnimatorDataDetailGrid />} />
            <Route path="/scene" element={<Scene />} />
            <Route path="/save-data" element={<SaveDataGrid />} />
            <Route path="/log" element={<DbgLog />} />
            <Route path="/command" element={<DbgCommand />} />

            {/* --- 追加ページ --- */}
            <Route path="/mypage" element={<MyPage />} />
            <Route path="/workspace" element={<Workspace />} />
            <Route path="/announcements" element={<AnnouncementList />} />
            <Route path="/announcements/new" element={<AnnouncementEditor />} />
            <Route path="/announcements/:id" element={<AnnouncementDetail />} />
            <Route path="/announcements/:id/edit" element={<AnnouncementEditor />} />

          </Routes>
        </Box>
      </Box>
    </Box>
  );
}

function App() {
  return (
    <ThemeProvider theme={cyberTheme}>
      <CssBaseline />
      <Router>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </Router>
    </ThemeProvider>
  );
}

export default App;
