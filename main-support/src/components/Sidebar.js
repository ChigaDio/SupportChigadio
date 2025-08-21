import React, { useState } from 'react';
import { Drawer, List, ListItem, ListItemIcon, ListItemText, Toolbar, Collapse } from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import SettingsIcon from '@mui/icons-material/Settings';
import InfoIcon from '@mui/icons-material/Info';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';

function Sidebar({ onMenuSelect }) {
  const [openGenerateTool, setOpenGenerateTool] = useState(false);

  const handleGenerateToolClick = () => {
    setOpenGenerateTool(!openGenerateTool);
  };

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: 240,
        flexShrink: 0,
        '& .MuiDrawer-paper': { width: 240, boxSizing: 'border-box' },
      }}
    >
      <Toolbar />
      <List>
        <ListItem button onClick={() => onMenuSelect('Main')}>
          <ListItemIcon><DashboardIcon /></ListItemIcon>
          <ListItemText primary="Main" />
        </ListItem>
        <ListItem button onClick={handleGenerateToolClick}>
          <ListItemIcon><SettingsIcon /></ListItemIcon>
          <ListItemText primary="GenerateTool" />
          {openGenerateTool ? <ExpandLess /> : <ExpandMore />}
        </ListItem>
        <Collapse in={openGenerateTool} timeout="auto" unmountOnExit>
          <List component="div" disablePadding>
            <ListItem button sx={{ pl: 4 }} onClick={() => onMenuSelect('Enum-ID')}>
              <ListItemText primary="Enum-ID" />
            </ListItem>
            <ListItem button sx={{ pl: 4 }} onClick={() => onMenuSelect('ClassData')}>
              <ListItemText primary="ClassData" />
            </ListItem>
            <ListItem button sx={{ pl: 4 }} onClick={() => onMenuSelect('State')}>
              <ListItemText primary="State" />
            </ListItem>
          </List>
        </Collapse>
        <ListItem button onClick={() => onMenuSelect('About')}>
          <ListItemIcon><InfoIcon /></ListItemIcon>
          <ListItemText primary="About" />
        </ListItem>
      </List>
    </Drawer>
  );
}

export default Sidebar;