import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ReactFlow, Background, Controls, useNodesState, useEdgesState, addEdge, Position, Handle } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Box, Drawer, List, ListItem, ListItemText, Button, Typography, IconButton, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Tabs, Tab, AppBar } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import CloseIcon from '@mui/icons-material/Close';

const CustomGroupNode = ({ data, id }) => {
  const params = useParams();
  const eventId = params.eventId;
  const subId = params.subId;
  const [showMenu, setShowMenu] = useState(false);
  const [roles, setRoles] = useState([]);

  useEffect(() => {
    fetch('/api/scenario-role')
      .then(res => res.json())
      .then(rolesData => setRoles(rolesData))
      .catch(error => console.error('Error fetching roles:', error));
  }, []);

  const handleAddRole = (role) => {
    fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition/${id}/role`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roleId: role.id, name: role.name, actions: role.actions || [] }),
    })
      .then(res => res.json())
      .then(result => {
        alert(result.message);
        const newRole = { id: role.id, name: role.name, actions: role.actions || [] };
        window.dispatchEvent(new CustomEvent('updateNodeRoles', { detail: { id, newRoles: [...data.roles, newRole] } }));
        setShowMenu(false);
      })
      .catch(error => {
        console.error('Error adding role:', error);
        alert('Role追加エラー: ' + error.message);
      });
  };

  const handleDeleteNode = (e) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('deleteNode', { detail: id }));
  };

  const hasRoleButton = data.isSubGroup;
  const hasSubGroupButton = !data.isSubGroup;

  return (
    <Box sx={{ bgcolor: 'white', p: 2, borderRadius: 2, border: '1px solid black', width: 200, textAlign: 'center' }}>
      <IconButton onClick={handleDeleteNode} sx={{ position: 'absolute', top: 0, right: 0 }}>
        <DeleteIcon />
      </IconButton>
      <Typography variant="h6">{data.label}</Typography>
      {data.description && (
        <Typography variant="body2" sx={{ fontStyle: 'italic', mt: 0.5 }}>{data.description}</Typography>
      )}
      {data.roles && data.roles.length > 0 && (
        <Box sx={{ mt: 1, textAlign: 'left' }}>
          <Typography variant="subtitle2">Roles:</Typography>
          <List dense>
            {data.roles.map((role, index) => (
              <ListItem key={index}>
                <ListItemText primary={role.name} secondary={role.actions.join(', ')} />
              </ListItem>
            ))}
          </List>
        </Box>
      )}
      {hasSubGroupButton && (
        <Button
          variant="contained"
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            if (typeof data.onTabSwitch === 'function') {
              data.onTabSwitch(`subgroup-${id}`);
            } else {
              console.error('onTabSwitch is not a function:', data.onTabSwitch);
            }
          }}
          sx={{ mt: 1 }}
        >
          SubGroupへ
        </Button>
      )}
      {hasRoleButton && (
        <Button
          variant="contained"
          size="small"
          onClick={(e) => { e.stopPropagation(); setShowMenu(true); }}
          sx={{ mt: 1 }}
        >
          Role追加
        </Button>
      )}
      <Drawer anchor="right" open={showMenu} onClose={() => setShowMenu(false)}>
        <Box sx={{ width: 250, p: 2 }}>
          <Typography variant="h6">ScenarioRole 選択</Typography>
          <List>
            {roles.map(role => (
              <ListItem button key={role.id} onClick={() => handleAddRole(role)}>
                <ListItemText primary={role.name} secondary={role.description + ' | Actions: ' + (role.actions?.join(', ') || 'None')} />
              </ListItem>
            ))}
          </List>
        </Box>
      </Drawer>
      <Handle type="source" position={Position.Right} />
      <Handle type="target" position={Position.Left} />
    </Box>
  );
};

const nodeTypes = {
  customGroup: CustomGroupNode,
  subGroupNode: CustomGroupNode
};

function ScenarioEventTransition() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const params = useParams();
  const eventId = params.eventId;
  const subId = params.subId;
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [newId, setNewId] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [tabs, setTabs] = useState([{ id: 'main', label: 'Group遷移図', type: 'group' }]);
  const [activeTab, setActiveTab] = useState('main');
  const [tabData, setTabData] = useState({ main: { nodes: [], edges: [] } });

  const addOnShrinkToNodes = (nodeList, isSub = false, parentId = null) => {
    return nodeList.map(node => ({
      ...node,
      data: {
        ...node.data,
        isSubGroup: isSub || node.type === 'subGroupNode',
        onTabSwitch: () => handleTabSwitch(`subgroup-${node.id}`, node.id)
      }
    }));
  };

  // 初期データロード
  useEffect(() => {
    fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition`)
      .then(res => res.json())
      .then(result => {
        let loadedNodes = result.nodes || [];
        loadedNodes = addOnShrinkToNodes(loadedNodes, false, null);
        setTabData(prev => ({ ...prev, main: { nodes: loadedNodes, edges: result.edges || [] } }));
        setNodes(loadedNodes);
        setEdges(result.edges || []);
      })
      .catch(error => {
        console.error('Error fetching transition:', error);
        setTabData(prev => ({ ...prev, main: { nodes: [], edges: [] } }));
        setNodes([]);
        setEdges([]);
      });
  }, [eventId, subId]);

  const onConnect = (params) => {
    const sourceEdges = edges.filter(edge => edge.source === params.source);
    if (sourceEdges.length > 0) {
      alert('1つのノードから複数の接続はできません');
      return;
    }
    const targetEdges = edges.filter(edge => edge.target === params.target);
    if (targetEdges.length > 0) {
      alert('1つのノードに複数の接続はできません');
      return;
    }
    const newEdge = {
      ...params,
      animated: true,
      style: { strokeDasharray: '5,5', stroke: 'cyan', strokeWidth: 3 }
    };
    setEdges(eds => addEdge(newEdge, eds));
    setTabData(prev => ({
      ...prev,
      [activeTab]: { nodes: prev[activeTab].nodes, edges: [...prev[activeTab].edges, newEdge] }
    }));
    saveCurrentTab();
  };

  const handleOpenAddDialog = () => {
    setAddDialogOpen(true);
    setNewId('');
    setNewDescription('');
  };

  const handleCloseAddDialog = () => {
    setAddDialogOpen(false);
  };

  const handleAddNode = () => {
    if (!newId.trim()) {
      alert('IDを入力してください（数値推奨）');
      return;
    }
    if (nodes.find(node => node.id === newId)) {
      alert('IDが重複しています');
      return;
    }
    const newNodeId = newId.trim();
    const nodeType = activeTab.startsWith('subgroup-') ? 'subGroupNode' : 'customGroup';
    const parentId = activeTab.startsWith('subgroup-') ? activeTab.split('-')[1] : null;
    const label = activeTab.startsWith('subgroup-') ? `Group: ${parentId} / Sub: ${newNodeId}` : newNodeId;
    const newNode = {
      id: newNodeId,
      type: nodeType,
      position: { x: Math.random() * 400, y: Math.random() * 400 },
      data: {
        label: label,
        description: newDescription.trim() || '',
        roles: [],
        isSubGroup: activeTab.startsWith('subgroup-'),
        onTabSwitch: nodeType === 'customGroup' ? () => handleTabSwitch(`subgroup-${newNodeId}`, newNodeId) : undefined
      },
      draggable: true,
    };
    const currentNodes = tabData[activeTab]?.nodes || [];
    const currentEdges = tabData[activeTab]?.edges || [];
    const updatedNodes = [...currentNodes, newNode];
    setTabData(prev => ({ ...prev, [activeTab]: { nodes: updatedNodes, edges: currentEdges } }));
    setNodes(updatedNodes);
    const apiUrl = activeTab.startsWith('subgroup-') 
      ? `/api/scenario-event/${eventId}/sub/${subId}/transition/${parentId}/subgroup` 
      : `/api/scenario-event/${eventId}/sub/${subId}/transition`;
    fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes: updatedNodes, edges: currentEdges }),
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .then(result => {
        alert(result.message);
        // 再読み込みで最新データを取得
        fetch(apiUrl)
          .then(res => res.json())
          .then(result => {
            let loadedNodes = result.nodes || [];
            loadedNodes = addOnShrinkToNodes(loadedNodes, activeTab.startsWith('subgroup-'), parentId);
            setTabData(prev => ({ ...prev, [activeTab]: { nodes: loadedNodes, edges: result.edges || [] } }));
            setNodes(loadedNodes);
            setEdges(result.edges || []);
          })
          .catch(error => console.error('Error re-fetching data:', error));
      })
      .catch(error => {
        console.error('Error adding node:', error);
        alert('ノード追加エラー: ' + error.message);
      });
    handleCloseAddDialog();
  };

  const handleDeleteNode = (nodeId) => {
    const currentNodes = tabData[activeTab]?.nodes || [];
    const updatedNodes = currentNodes.filter(node => node.id !== nodeId);
    const currentEdges = tabData[activeTab]?.edges || [];
    const updatedEdges = currentEdges.filter(edge => edge.source !== nodeId && edge.target !== nodeId);
    setTabData(prev => ({ ...prev, [activeTab]: { nodes: updatedNodes, edges: updatedEdges } }));
    setNodes(updatedNodes);
    setEdges(updatedEdges);
    saveCurrentTab();
  };

  const handleTabSwitch = (tabId, parentId = null) => {
    if (tabId === activeTab) return;
    if (tabId.startsWith('subgroup-') && !tabs.find(t => t.id === tabId)) {
      const newTab = { id: tabId, label: `SubGroup: ${parentId}`, type: 'subgroup', parentId };
      setTabs(prev => [...prev, newTab]);
      fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition/${parentId}/subgroup`)
        .then(res => res.json())
        .then(result => {
          let loadedNodes = result.nodes || [];
          loadedNodes = addOnShrinkToNodes(loadedNodes, true, parentId);
          setTabData(prev => ({ ...prev, [tabId]: { nodes: loadedNodes, edges: result.edges || [] } }));
        })
        .catch(error => {
          console.error('Error fetching subgroup:', error);
          setTabData(prev => ({ ...prev, [tabId]: { nodes: [], edges: [] } }));
        });
    }
    setActiveTab(tabId);
    const currentTabData = tabData[tabId] || { nodes: [], edges: [] };
    setNodes(addOnShrinkToNodes(currentTabData.nodes, tabId.startsWith('subgroup-'), parentId));
    setEdges(currentTabData.edges);
  };

  const handleTabClose = (tabId) => {
    if (tabId === 'main') return;
    setTabs(prev => prev.filter(t => t.id !== tabId));
    if (activeTab === tabId) {
      const newActive = 'main';
      handleTabSwitch(newActive);
    }
    setTabData(prev => {
      const { [tabId]: omitted, ...rest } = prev;
      return rest;
    });
  };

  const saveCurrentTab = () => {
    if (!tabData[activeTab]) return;
    const parentId = activeTab.startsWith('subgroup-') ? activeTab.split('-')[1] : null;
    const saveData = { 
      nodes: tabData[activeTab].nodes.map(n => ({ ...n, data: { ...n.data, onTabSwitch: undefined } })), 
      edges: tabData[activeTab].edges 
    };
    const saveUrl = activeTab.startsWith('subgroup-') 
      ? `/api/scenario-event/${eventId}/sub/${subId}/transition/${parentId}/subgroup` 
      : `/api/scenario-event/${eventId}/sub/${subId}/transition`;
    fetch(saveUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(saveData),
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .catch(error => console.error('Error saving:', error));
  };

  useEffect(() => {
    const deleteNodeHandler = (e) => handleDeleteNode(e.detail);
    const updateRolesHandler = (e) => {
      setTabData(prev => {
        const current = prev[activeTab];
        if (!current) return prev;
        const updatedNodes = current.nodes.map(node => 
          node.id === e.detail.id 
            ? { ...node, data: { ...node.data, roles: e.detail.newRoles } }
            : node
        );
        return { ...prev, [activeTab]: { ...current, nodes: updatedNodes } };
      });
      setNodes(prevNodes => prevNodes.map(node => 
        node.id === e.detail.id 
          ? { ...node, data: { ...node.data, roles: e.detail.newRoles } }
          : node
      ));
    };
    window.addEventListener('deleteNode', deleteNodeHandler);
    window.addEventListener('updateNodeRoles', updateRolesHandler);
    return () => {
      window.removeEventListener('deleteNode', deleteNodeHandler);
      window.removeEventListener('updateNodeRoles', updateRolesHandler);
    };
  }, [activeTab]);

  useEffect(() => {
    if (tabData[activeTab]?.nodes?.length || tabData[activeTab]?.edges?.length) {
      saveCurrentTab();
    }
  }, [tabData, activeTab]);

  const currentNodes = tabData[activeTab]?.nodes || [];
  const currentEdges = tabData[activeTab]?.edges || [];

  return (
    <Box sx={{ height: '100vh', width: '100vw', bgcolor: 'black' }}>
      <AppBar position="static" sx={{ bgcolor: 'grey.800' }}>
        <Tabs value={activeTab} onChange={(e, newValue) => handleTabSwitch(newValue)} variant="scrollable" scrollButtons="auto">
          {tabs.map((tab) => (
            <Tab
              key={tab.id}
              label={
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  {tab.label}
                  {tab.type === 'subgroup' && (
                    <IconButton size="small" onClick={(e) => { e.stopPropagation(); handleTabClose(tab.id); }}>
                      <CloseIcon />
                    </IconButton>
                  )}
                </Box>
              }
              value={tab.id}
            />
          ))}
        </Tabs>
      </AppBar>
      <Box sx={{ flexGrow: 1, height: 'calc(100vh - 64px)' }}>
        <ReactFlow
          nodes={currentNodes}
          edges={currentEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          style={{ backgroundColor: 'black' }}
          fitView
          nodesDraggable={true}
          minZoom={1}
          maxZoom={1}
        >
          <Background variant="lines" color="white" gap={20} size={1} />
          <Controls />
        </ReactFlow>
      </Box>
      <Button 
        variant="contained" 
        startIcon={<AddIcon />} 
        onClick={handleOpenAddDialog} 
        sx={{ position: 'absolute', bottom: 10, right: 10 }}
      >
        {activeTab.startsWith('subgroup-') ? 'SubGroupNode追加' : 'Group追加'}
      </Button>
      <Dialog open={addDialogOpen} onClose={handleCloseAddDialog}>
        <DialogTitle>{activeTab.startsWith('subgroup-') ? '新しいSubGroupNode追加' : '新しいGroup追加'}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={activeTab.startsWith('subgroup-') ? 'SubGroup ID (数値推奨)' : 'Group ID (数値推奨)'}
            type="text"
            fullWidth
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            variant="standard"
            helperText="数値のIDを入力（例: 1, 2, 3）"
          />
          <TextField
            margin="dense"
            label="説明 (オプション)"
            type="text"
            fullWidth
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            variant="standard"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseAddDialog}>キャンセル</Button>
          <Button onClick={handleAddNode}>追加</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ScenarioEventTransition;