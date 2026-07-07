import React from 'react';
import { Drawer, List, ListItem, ListItemText, Collapse } from '@mui/material';
import { ExpandLess, ExpandMore } from '@mui/icons-material';

function Sidebar({ selectedMenu, handleMenuClick }) {
  const [open, setOpen] = React.useState({});

  const handleClick = (menu) => {
    setOpen((prev) => ({ ...prev, [menu]: !prev[menu] }));
  };

  const menuItems = [
    {
      name: 'GenerateTool',
      subItems: [
        { name: 'Enum ID', key: 'enum-id' },
        { name: 'Const Class Data', key: 'const-class-data' },
        { name: 'Class Data', key: 'class-data' },
        { name: 'Class Data ID', key: 'class-data-id' },
        { name: 'Class Data Matrix ID', key: 'class-data-matrix-id' },
        { name: 'State', key: 'state' },
        { name: 'Behavior', key: 'behavior' },
        { name: 'Save Data', key: 'save-data' }
      ],
    },
    {
      name: 'Assets',
      subItems: [
        { name: 'Sound', key: 'sound' },
        { name: 'Texture', key: 'texture' },
        { name: 'GameObject', key: 'gameobject' },
        { name: 'Animator', key: 'animator' },
        { name: 'Scene', key: 'scene' }
      ],
    },
    {
      name: 'Scenario',
      subItems: [
        { name: 'ScenarioRole', key: 'scenario-role' },
        { name: 'ScenarioEvent', key: 'scenario-event' },
        { name: 'ScenarioConditions', key: 'scenario-conditions' },
      ],
    },
    {
      name: 'Debug',
      subItems: [
        { name: 'Log', key: 'log' },
      ],
    },
  ];

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: 240,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: 240,
          boxSizing: 'border-box',
        },
      }}
    >
      <List>
        {menuItems.map((item) => (
          <React.Fragment key={item.name}>
            <ListItem
              button
              onClick={() => {
                handleClick(item.name);
                handleMenuClick(item.name, null);
              }}
              selected={selectedMenu === item.name}
            >
              <ListItemText primary={item.name} />
              {open[item.name] ? <ExpandLess /> : <ExpandMore />}
            </ListItem>
            <Collapse in={open[item.name]} timeout="auto" unmountOnExit>
              <List component="div" disablePadding>
                {item.subItems.map((subItem) => (
                  <ListItem
                    button
                    key={subItem.key}
                    sx={{ pl: 4 }}
                    onClick={() => handleMenuClick(item.name, subItem.key)}
                    selected={selectedMenu === item.name && subItem.key === selectedMenu}
                  >
                    <ListItemText primary={subItem.name} />
                  </ListItem>
                ))}
              </List>
            </Collapse>
          </React.Fragment>
        ))}
      </List>
    </Drawer>
  );
}

export default Sidebar;