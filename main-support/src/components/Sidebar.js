import React from 'react';
import { Drawer, List, ListItem, ListItemText, ListItemButton, Collapse } from '@mui/material';
import { ExpandLess, ExpandMore } from '@mui/icons-material';

function Sidebar({ selectedMenu, handleMenuClick }) {
  const [open, setOpen] = React.useState(true); // GenerateToolのサブメニュー展開状態

  const handleGenerateToolClick = () => {
    setOpen(!open);
  };

  const handleSubMenuClick = (subMenu) => {
    handleMenuClick('GenerateTool', subMenu);
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
      <List>
        <ListItemButton
          selected={selectedMenu === 'GenerateTool'}
          onClick={handleGenerateToolClick}
        >
          <ListItemText primary="GenerateTool" />
          {open ? <ExpandLess /> : <ExpandMore />}
        </ListItemButton>
        <Collapse in={open} timeout="auto" unmountOnExit>
          <List component="div" disablePadding>
            <ListItemButton
              sx={{ pl: 4 }}
              onClick={() => handleSubMenuClick('enum-id')}
            >
              <ListItemText primary="Enum ID" />
            </ListItemButton>
            <ListItemButton
              sx={{ pl: 4 }}
              onClick={() => handleSubMenuClick('class-data')}
            >
              <ListItemText primary="Class Data" />
            </ListItemButton>
              <ListItemButton
              sx={{ pl: 4 }}
              onClick={() => handleSubMenuClick('class-data-id')}
            >
              <ListItemText primary="Class Data ID" />
              
            </ListItemButton>
              <ListItemButton
              sx={{ pl: 4 }}
              onClick={() => handleSubMenuClick('class-data-matrix-id')}
            >
              <ListItemText primary="Class Data Matrix ID" />

            </ListItemButton>
            <ListItemButton
              sx={{ pl: 4 }}
              onClick={() => handleSubMenuClick('state')}
            >
              <ListItemText primary="State" />
            </ListItemButton>
          </List>
        </Collapse>
      </List>
    </Drawer>
  );
}

export default Sidebar;