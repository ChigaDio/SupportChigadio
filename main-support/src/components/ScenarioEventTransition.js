import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { ReactFlow, Background, Controls, useNodesState, useEdgesState, addEdge, Position, Handle, applyNodeChanges } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Box, Drawer, List, ListItem, ListItemText, Button, Typography, IconButton, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Tabs, Tab, AppBar, Accordion, AccordionSummary, AccordionDetails, Backdrop, CircularProgress } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import CloseIcon from '@mui/icons-material/Close';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ContentPasteIcon from '@mui/icons-material/ContentPaste';
import EditIcon from '@mui/icons-material/Edit';
import RoleInputFactory from '../scenario/RoleInputFactory';
import { debounce } from 'lodash';

const CustomGroupNode = ({ data, id, saveCurrentTab, roles: globalRoles, roleDataCache, roleFormSchemas }) => {
  const params = useParams();
  const eventId = params.eventId;
  const subId = params.subId;
  const [showMenu, setShowMenu] = useState(false);
  const [showDataMenu, setShowDataMenu] = useState(false);
  const [roles, setRoles] = useState(globalRoles);
  const [roleForms, setRoleForms] = useState({});
  const [formErrors, setFormErrors] = useState({});
  const [formDataState, setFormDataState] = useState({});
  const formRefs = useRef([]);

  useEffect(() => {
    console.log('CustomGroupNode params:', { eventId, subId, nodeId: id });
    if (!eventId || !subId) {
      console.error('CustomGroupNode: eventId or subId is undefined');
    }
  }, [eventId, subId, id]);

  useEffect(() => {
    setRoles(globalRoles || []);
  }, [globalRoles]);

  useEffect(() => {
    console.log('showMenu state for node', id, ':', showMenu);
    console.log('showDataMenu state for node', id, ':', showDataMenu);
  }, [showMenu, showDataMenu, id]);

  useEffect(() => {
    if (data.roles && data.roles.length > 0) {
      data.roles.forEach((role, index) => {
        const cachedData = roleDataCache?.[id]?.[role.uniqueId];
        setFormDataState(prev => ({ ...prev, [role.uniqueId]: cachedData || role.data || [] }));
        formRefs.current[index] = { submit: () => {} };
      });
      const loadRoleData = async () => {
        const updatedRoles = await Promise.all(data.roles.map(async (role) => {
          const uniqueId = role.uniqueId;
          if (roleDataCache?.[id]?.[uniqueId]) {
            console.log(`Cache hit for node ${id}, role ${uniqueId}`);
            return { ...role, data: roleDataCache[id][uniqueId] };
          }
          try {
            const res = await fetch(`/api/save-role-data/${eventId}/${subId}/${id}/${uniqueId}`);
            if (res.ok) {
              const { formData } = await res.json();
              setFormDataState(prev => ({ ...prev, [uniqueId]: formData }));
              window.dispatchEvent(new CustomEvent('updateRoleDataCache', { detail: { nodeId: id, uniqueId, formData } }));
              return { ...role, data: formData };
            }
            return role;
          } catch (error) {
            console.error(`Error loading role data for node ${id}, role ${uniqueId}:`, error);
            return role;
          }
        }));
        if (updatedRoles.some((r, i) => JSON.stringify(r.data) !== JSON.stringify(data.roles[i].data))) {
          window.dispatchEvent(new CustomEvent('updateNodeRoles', { detail: { id, newRoles: updatedRoles } }));
        }
      };
      const debouncedLoad = debounce(loadRoleData, 500);
      debouncedLoad();
      return () => debouncedLoad.cancel();
    }
  }, [data.roles, eventId, subId, id, roleDataCache]);

  const loadForms = useCallback(async () => {
    if (!eventId || !subId) {
      console.error('Cannot load role forms: eventId or subId is undefined');
      return;
    }
    try {
      const formPromises = (data.roles || []).map(async (role) => {
        try {
          // 修正: 親から渡されたスキーマを使用
          const cachedSchema = roleFormSchemas[role.name];
          if (cachedSchema) {
            console.log(`Using cached schema for role ${role.name}`);
            const FormComp = await RoleInputFactory.getForm(
              role.name,
              formDataState[role.uniqueId] || role.data || [],
              (formData) => {
                console.log(`Form data updated for ${role.uniqueId}:`, formData);
                setFormDataState(prev => ({ ...prev, [role.uniqueId]: formData }));
              },
              cachedSchema // スキーマを渡す
            );
            return { uniqueId: role.uniqueId, FormComp };
          }
          const res = await fetch(`/api/role-form-schema/${role.name}`);
          if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
          const schema = await res.json();
          window.dispatchEvent(new CustomEvent('updateRoleFormSchema', { detail: { roleName: role.name, schema } }));
          const FormComp = await RoleInputFactory.getForm(
            role.name,
            formDataState[role.uniqueId] || role.data || [],
            (formData) => {
              console.log(`Form data updated for ${role.uniqueId}:`, formData);
              setFormDataState(prev => ({ ...prev, [role.uniqueId]: formData }));
            },
            schema
          );
          return { uniqueId: role.uniqueId, FormComp };
        } catch (error) {
          console.error(`Error loading form for role ${role.name}:`, error);
          return { uniqueId: role.uniqueId, error: error.message };
        }
      });
      const results = await Promise.all(formPromises);
      const newRoleForms = {};
      const newFormErrors = {};
      results.forEach(({ uniqueId, FormComp, error }) => {
        if (error) {
          newFormErrors[uniqueId] = error;
        } else {
          newRoleForms[uniqueId] = FormComp;
        }
      });
      setRoleForms(newRoleForms);
      setFormErrors(newFormErrors);
    } catch (error) {
      console.error('Error loading role forms:', error);
    }
  }, [data.roles, eventId, subId, roleFormSchemas]); // 修正: formDataStateを依存から除外

  useEffect(() => {
    const debouncedLoad = debounce(loadForms, 500);
    debouncedLoad();
    return () => debouncedLoad.cancel();
  }, [loadForms]);

  const handleAddRole = (role) => {
    if (!eventId || !subId) {
      alert('エラー: Event IDまたはSub IDが未定義です。');
      return;
    }
    const uniqueId = Date.now().toString();
    fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition/${id}/role`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roleId: role.id, name: role.name, branchType: role.branchType || 'General', uniqueId }),
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .then(result => {
        alert(result.message);
        const newRole = { uniqueId, id: role.id, name: role.name, branchType: role.branchType, data: [] };
        const newRoles = [...(data.roles || []), newRole];
        window.dispatchEvent(new CustomEvent('updateNodeRoles', { detail: { id, newRoles } }));
        setShowMenu(false);
        saveCurrentTab();
      })
      .catch(error => {
        console.error('Error adding role:', error);
        alert('Role追加エラー: ' + error.message);
      });
  };

  const handleDeleteRole = (uniqueId) => {
    const newRoles = (data.roles || []).filter(role => role.uniqueId !== uniqueId);
    window.dispatchEvent(new CustomEvent('updateNodeRoles', { detail: { id, newRoles } }));
    saveCurrentTab();
  };

  const handleSaveRole = (uniqueId, formData) => {
    if (!eventId || !subId) {
      alert('エラー: Event IDまたはSub IDが未定義です。');
      return;
    }
    console.log('Saving role data:', { uniqueId, formData });
    fetch(`/api/save-role-data/${eventId}/${subId}/${id}/${uniqueId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ formData }),
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .then(result => {
        console.log('Role save response:', result);
        alert(result.message);
        const newRoles = (data.roles || []).map(role =>
          role.uniqueId === uniqueId ? { ...role, data: formData } : role
        );
        window.dispatchEvent(new CustomEvent('updateNodeRoles', { detail: { id, newRoles } }));
        window.dispatchEvent(new CustomEvent('updateRoleDataCache', { detail: { nodeId: id, uniqueId, formData } }));
        saveCurrentTab();
      })
      .catch(error => {
        console.error('Error saving role data:', error);
        alert('保存エラー: ' + error.message);
      });
  };

  const handleBatchSave = () => {
    data.roles.forEach((role) => {
      const formData = formDataState[role.uniqueId];
      if (formData) {
        handleSaveRole(role.uniqueId, formData);
      }
    });
  };

  const handleDeleteNode = (e) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('deleteNode', { detail: id }));
  };

  const handleCopyNode = (e) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('copyNode', { detail: id }));
  };

  const handleEditNodeId = (e) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('editNodeId', { detail: id }));
  };

  const hasRoleButton = data.isSubGroup;
  const hasSubGroupButton = !data.isSubGroup;

  return (
    <Box
      sx={{ bgcolor: 'white', p: 2, borderRadius: 2, border: '1px solid black', width: 200, textAlign: 'center' }}
      onClick={(e) => {
        if (hasRoleButton) {
          e.stopPropagation();
          setShowDataMenu(true);
        }
      }}
    >
      <IconButton onClick={handleDeleteNode} sx={{ position: 'absolute', top: 0, right: 0 }}>
        <DeleteIcon />
      </IconButton>
      <IconButton onClick={handleCopyNode} sx={{ position: 'absolute', top: 0, left: 0 }}>
        <ContentCopyIcon />
      </IconButton>
      <IconButton onClick={handleEditNodeId} sx={{ position: 'absolute', bottom: 0, left: 0 }}>
        <EditIcon />
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
              <ListItem key={role.uniqueId}>
                <ListItemText primary={role.name} secondary={role.description} />
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
            data.onTabSwitch?.(id);
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
          onClick={(e) => {
            e.stopPropagation();
            setShowMenu(true);
          }}
          sx={{ mt: 1 }}
        >
          Role追加
        </Button>
      )}
      <Drawer
        key={`drawer-role-select-${id}-${showMenu}`}
        anchor="right"
        open={showMenu}
        onClose={(e) => {
          e.stopPropagation();
          setShowMenu(false);
        }}
      >
        <Box sx={{ width: 600, p: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">ScenarioRole 選択</Typography>
            <IconButton
              onClick={(e) => {
                e.stopPropagation();
                console.log('Close Role select button clicked for node:', id);
                setShowMenu(false);
              }}
            >
              <CloseIcon />
            </IconButton>
          </Box>
          <List>
            {roles.map(role => (
              <ListItem button key={role.id} onClick={() => handleAddRole(role)}>
                <ListItemText primary={role.name} secondary={role.description} />
              </ListItem>
            ))}
          </List>
        </Box>
      </Drawer>
      <Drawer
        key={`drawer-data-input-${id}-${showDataMenu}`}
        anchor="right"
        open={showDataMenu}
        onClose={(e) => {
          e.stopPropagation();
          setShowDataMenu(false);
        }}
      >
        <Box sx={{ width: 600, p: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">Role データ入力</Typography>
            <IconButton
              onClick={(e) => {
                e.stopPropagation();
                console.log('Close Data input button clicked for node:', id);
                setShowDataMenu(false);
              }}
            >
              <CloseIcon />
            </IconButton>
          </Box>
          {(data.roles || []).map((role, index) => (
            <Accordion key={role.uniqueId}>
              <AccordionSummary>
                <Typography>{role.name}</Typography>
                <Button onClick={() => handleDeleteRole(role.uniqueId)} sx={{ ml: 'auto' }}>削除</Button>
              </AccordionSummary>
              <AccordionDetails>
                {formErrors[role.uniqueId] ? (
                  <Typography color="error">フォーム読み込みエラー: {formErrors[role.uniqueId]}</Typography>
                ) : roleForms[role.uniqueId] ? (
                  (() => {
                    const RoleForm = roleForms[role.uniqueId];
                    return <RoleForm />;
                  })()
                ) : (
                  <Typography>Loading...</Typography>
                )}
              </AccordionDetails>
            </Accordion>
          ))}
          <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
            <Button variant="contained" color="primary" onClick={handleBatchSave}>
              一括保存
            </Button>
          </Box>
        </Box>
      </Drawer>
      <Handle type="source" position={Position.Right} />
      <Handle type="target" position={Position.Left} />
    </Box>
  );
};

function ScenarioEventTransition() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const params = useParams();
  const eventId = params.eventId;
  const subId = params.subId;
  const [isLoading, setIsLoading] = useState(true);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editNodeId, setEditNodeId] = useState(null);
  const [newId, setNewId] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [tabs, setTabs] = useState([{ id: 'main', label: 'Group遷移図', type: 'group' }]);
  const [activeTab, setActiveTab] = useState('main');
  const [tabData, setTabData] = useState({ main: { nodes: [], edges: [] } });
  const [copiedNode, setCopiedNode] = useState(null);
  const [globalRoles, setGlobalRoles] = useState([]);
  const [roleDataCache, setRoleDataCache] = useState({});
  const [roleFormSchemas, setRoleFormSchemas] = useState({}); // 修正: スキーマキャッシュ

  useEffect(() => {
    fetch('/api/scenario-role')
      .then(res => res.json())
      .then(rolesData => setGlobalRoles(rolesData))
      .catch(error => console.error('Error fetching roles:', error));
  }, []);

  // 修正: ロールスキーマを一括ロード
  useEffect(() => {
    const loadSchemas = async () => {
      try {
        const promises = globalRoles.map(async (role) => {
          const res = await fetch(`/api/role-form-schema/${role.name}`);
          if (res.ok) {
            const schema = await res.json();
            return { roleName: role.name, schema };
          }
          return null;
        });
        const results = await Promise.all(promises);
        const schemas = results.reduce((acc, curr) => {
          if (curr) acc[curr.roleName] = curr.schema;
          return acc;
        }, {});
        setRoleFormSchemas(schemas);
      } catch (error) {
        console.error('Error loading role form schemas:', error);
      }
    };
    if (globalRoles.length > 0) {
      loadSchemas();
    }
  }, [globalRoles]);

  useEffect(() => {
    const handleUpdateRoleDataCache = (event) => {
      const { nodeId, uniqueId, formData } = event.detail;
      setRoleDataCache(prev => ({
        ...prev,
        [nodeId]: {
          ...prev[nodeId],
          [uniqueId]: formData
        }
      }));
    };
    const handleUpdateRoleFormSchema = (event) => {
      const { roleName, schema } = event.detail;
      setRoleFormSchemas(prev => ({ ...prev, [roleName]: schema }));
    };
    window.addEventListener('updateRoleDataCache', handleUpdateRoleDataCache);
    window.addEventListener('updateRoleFormSchema', handleUpdateRoleFormSchema);
    return () => {
      window.removeEventListener('updateRoleDataCache', handleUpdateRoleDataCache);
      window.removeEventListener('updateRoleFormSchema', handleUpdateRoleFormSchema);
    };
  }, []);

  const debouncedSaveCurrentTab = useMemo(() => debounce((tabDataArg, activeTabArg, eventIdArg, subIdArg) => {
    if (!tabDataArg[activeTabArg] || !eventIdArg || !subIdArg) {
      console.error('Cannot save tab: tabData or eventId/subId is undefined');
      return;
    }
    setIsLoading(true);
    const parentId = activeTabArg.startsWith('subgroup-') ? activeTabArg.split('-')[1] : null;
    const saveData = {
      nodes: tabDataArg[activeTabArg].nodes.map(n => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: {
          label: n.data.label,
          description: n.data.description,
          roles: n.data.roles,
          subgroups: n.data.subgroups,
          isSubGroup: n.data.isSubGroup
        },
        draggable: n.draggable
      })),
      edges: tabDataArg[activeTabArg].edges
    };
    const saveUrl = activeTabArg.startsWith('subgroup-')
      ? `/api/scenario-event/${eventIdArg}/sub/${subIdArg}/transition/${parentId}/subgroup`
      : `/api/scenario-event/${eventIdArg}/sub/${subIdArg}/transition`;
    fetch(saveUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(saveData),
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .then(result => {
        console.log('Save response:', result);
        if (activeTabArg.startsWith('subgroup-')) {
          setTabData(prev => ({
            ...prev,
            main: {
              ...prev.main,
              nodes: prev.main.nodes.map(node =>
                node.id === parentId ? {
                  ...node,
                  data: { ...node.data, subgroups: { ...node.data.subgroups, [parentId]: saveData } }
                } : node
              )
            }
          }));
        }
        alert(result.message);
      })
      .catch(error => {
        console.error('Error saving:', error);
        alert('保存エラー: ' + error.message);
      })
      .finally(() => setIsLoading(false));
  }, 500), []);

  const saveCurrentTab = useCallback(() => {
    debouncedSaveCurrentTab(tabData, activeTab, eventId, subId);
  }, [debouncedSaveCurrentTab, tabData, activeTab, eventId, subId]);

  const updateNodeId = useCallback((oldId, newId) => {
    if (oldId === newId) return;
    const currentNodes = tabData[activeTab].nodes;
    if (currentNodes.some(n => n.id === newId)) {
      alert('IDが重複しています');
      return;
    }
    setIsLoading(true);
    const parentId = activeTab.startsWith('subgroup-') ? activeTab.split('-')[1] : null;
    let updatedNodes = currentNodes.map(node =>
      node.id === oldId ? {
        ...node,
        id: newId,
        data: {
          ...node.data,
          label: activeTab.startsWith('subgroup-') ? `Group: ${parentId} / Sub: ${newId}` : newId,
          subgroups: node.data.subgroups || {}
        }
      } : node
    );
    const updatedEdges = tabData[activeTab].edges.map(edge => ({
      ...edge,
      source: edge.source === oldId ? newId : edge.source,
      target: edge.target === oldId ? newId : edge.target
    }));
    let newTabData = { ...tabData, [activeTab]: { nodes: updatedNodes, edges: updatedEdges } };
    if (activeTab.startsWith('subgroup-')) {
      newTabData.main = {
        ...tabData.main,
        nodes: tabData.main.nodes.map(node => {
          if (node.id === parentId) {
            const currentSubData = node.data.subgroups[parentId] || { nodes: [], edges: [] };
            const newSubNodes = currentSubData.nodes.map(n =>
              n.id === oldId ? {
                ...n,
                id: newId,
                data: { ...n.data, label: `Group: ${parentId} / Sub: ${newId}` }
              } : n
            );
            const newSubEdges = currentSubData.edges.map(e => ({
              ...e,
              source: e.source === oldId ? newId : e.source,
              target: e.target === oldId ? newId : e.target
            }));
            return {
              ...node,
              data: {
                ...node.data,
                subgroups: {
                  ...node.data.subgroups,
                  [parentId]: { nodes: newSubNodes, edges: newSubEdges }
                }
              }
            };
          }
          return node;
        })
      };
    }
    setTabData(newTabData);
    setNodes(updatedNodes);
    setEdges(updatedEdges);
    saveCurrentTab();
  }, [tabData, activeTab, setTabData, setNodes, setEdges, saveCurrentTab]);

  const nodeTypes = useMemo(() => ({
    customGroup: (props) => <CustomGroupNode {...props} saveCurrentTab={saveCurrentTab} roles={globalRoles} roleDataCache={roleDataCache} roleFormSchemas={roleFormSchemas} />,
    subGroupNode: (props) => <CustomGroupNode {...props} saveCurrentTab={saveCurrentTab} roles={globalRoles} roleDataCache={roleDataCache} roleFormSchemas={roleFormSchemas} />
  }), [saveCurrentTab, globalRoles, roleDataCache, roleFormSchemas]);

  const memoizedNodes = useMemo(() => nodes.map(node => ({
    ...node,
    data: { ...node.data, saveCurrentTab }
  })), [nodes, saveCurrentTab]);

  const memoizedEdges = useMemo(() => edges.map(edge => ({
    ...edge,
    id: `${edge.source}-${edge.target}`, // 修正: エッジIDを明示
    animated: true,
    style: { strokeDasharray: '5,5', stroke: 'cyan', strokeWidth: 3 }
  })), [edges]);

  const addOnShrinkToNodes = (nodeList, isSub = false) => {
    return nodeList.map(node => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data: {
        label: node.data.label,
        description: node.data.description || '',
        roles: node.data.roles || [],
        subgroups: isSub ? {} : node.data.subgroups || {},
        isSubGroup: isSub || node.type === 'subGroupNode',
        onTabSwitch: node.type === 'customGroup' ? (nodeId) => handleTabSwitch(`subgroup-${nodeId}`, nodeId) : undefined,
        saveCurrentTab,
      },
      draggable: true,
    }));
  };

  useEffect(() => {
    const handleUpdateNodeRoles = (event) => {
      const { id, newRoles } = event.detail;
      console.log('updateNodeRoles event:', { id, newRoles });
      setTabData(prev => {
        const updatedNodes = prev[activeTab].nodes.map(node =>
          node.id === id ? { ...node, data: { ...node.data, roles: newRoles } } : node
        );
        const newTabData = { ...prev, [activeTab]: { ...prev[activeTab], nodes: updatedNodes } };
        if (activeTab.startsWith('subgroup-')) {
          const parentId = activeTab.split('-')[1];
          newTabData.main = {
            ...prev.main,
            nodes: prev.main.nodes.map(node =>
              node.id === parentId ? {
                ...node,
                data: {
                  ...node.data,
                  subgroups: {
                    ...node.data.subgroups,
                    [parentId]: { nodes: updatedNodes, edges: prev[activeTab].edges }
                  }
                }
              } : node
            )
          };
        }
        return newTabData;
      });
      setNodes(prev => prev.map(node =>
        node.id === id ? { ...node, data: { ...node.data, roles: newRoles } } : node
      ));
      saveCurrentTab();
    };

    const handleDeleteNode = (event) => {
      handleDeleteNode(event.detail);
    };

    const handleCopyNode = (event) => {
      handleCopyNode(event.detail);
    };

    const handleEditNodeId = (event) => {
      handleOpenEditDialog(event.detail);
    };

    window.addEventListener('updateNodeRoles', handleUpdateNodeRoles);
    window.addEventListener('deleteNode', handleDeleteNode);
    window.addEventListener('copyNode', handleCopyNode);
    window.addEventListener('editNodeId', handleEditNodeId);

    return () => {
      window.removeEventListener('updateNodeRoles', handleUpdateNodeRoles);
      window.removeEventListener('deleteNode', handleDeleteNode);
      window.removeEventListener('copyNode', handleCopyNode);
      window.removeEventListener('editNodeId', handleEditNodeId);
    };
  }, [activeTab, tabData, saveCurrentTab]);

  useEffect(() => {
    if (!eventId || !subId) {
      console.error('Cannot fetch transition: eventId or subId is undefined');
      alert('エラー: Event IDまたはSub IDが未定義です。');
      setIsLoading(false);
      return;
    }
    const abortController = new AbortController();
    setIsLoading(true);
    fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition`, { signal: abortController.signal })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .then(result => {
        let loadedNodes = result.nodes || [];
        loadedNodes = addOnShrinkToNodes(loadedNodes, false);
        const validEdges = (result.edges || []).filter(edge =>
          loadedNodes.some(n => n.id === edge.source) && loadedNodes.some(n => n.id === edge.target)
        );
        setTabData(prev => ({ ...prev, main: { nodes: loadedNodes, edges: validEdges } }));
        setNodes(loadedNodes);
        setEdges(validEdges);
      })
      .catch(error => {
        if (error.name === 'AbortError') return;
        console.error('Error fetching transition:', error);
        setTabData(prev => ({ ...prev, main: { nodes: [], edges: [] } }));
        setNodes([]);
        setEdges([]);
      })
      .finally(() => setIsLoading(false));
    return () => abortController.abort();
  }, [eventId, subId]);

  const handleTabSwitch = useCallback((tabId, parentId = null) => {
    if (tabId === activeTab) return;
    if (!eventId || !subId) {
      alert('エラー: Event IDまたはSub IDが未定義です。');
      return;
    }
    setIsLoading(true);
    const existingTab = tabs.find(t => t.id === tabId);
    if (tabId.startsWith('subgroup-')) {
      if (existingTab) {
        setActiveTab(tabId);
        const parentNode = tabData.main.nodes.find(n => n.id === parentId);
        const subGroupData = parentNode?.data.subgroups?.[parentId] || { nodes: [], edges: [] };
        const loadedNodes = addOnShrinkToNodes(subGroupData.nodes, true);
        const validEdges = subGroupData.edges.filter(edge =>
          loadedNodes.some(n => n.id === edge.source) && loadedNodes.some(n => n.id === edge.target)
        );
        setNodes(loadedNodes);
        setEdges(validEdges);
        setTabData(prev => ({ ...prev, [tabId]: { nodes: loadedNodes, edges: validEdges } }));
        setTimeout(() => {
          const revalidatedEdges = validEdges.filter(edge =>
            loadedNodes.some(n => n.id === edge.source) && loadedNodes.some(n => n.id === edge.target)
          );
          if (revalidatedEdges.length !== validEdges.length) {
            console.warn('Invalid edges detected in tab switch:', { tabId, invalidEdges: validEdges.length - revalidatedEdges.length });
            setEdges(revalidatedEdges);
            setTabData(prev => ({
              ...prev,
              [tabId]: { ...prev[tabId], edges: revalidatedEdges }
            }));
          }
        }, 0);
        setIsLoading(false);
        return;
      }
      const newTab = { id: tabId, label: `SubGroup: ${parentId}`, type: 'subgroup', parentId };
      setTabs(prev => {
        if (!prev.find(t => t.id === tabId)) return [...prev, newTab];
        return prev;
      });
      fetch(`/api/scenario-event/${eventId}/sub/${subId}/transition/${parentId}/subgroup`)
        .then(res => {
          if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
          return res.json();
        })
        .then(result => {
          let loadedNodes = result.nodes || [];
          loadedNodes = addOnShrinkToNodes(loadedNodes, true);
          const validEdges = (result.edges || []).filter(edge =>
            loadedNodes.some(n => n.id === edge.source) && loadedNodes.some(n => n.id === edge.target)
          );
          setTabData(prev => ({
            ...prev,
            [tabId]: { nodes: loadedNodes, edges: validEdges },
            main: {
              ...prev.main,
              nodes: prev.main.nodes.map(node =>
                node.id === parentId ? {
                  ...node,
                  data: { ...node.data, subgroups: { ...node.data.subgroups, [parentId]: { nodes: loadedNodes, edges: validEdges } } }
                } : node
              )
            }
          }));
          setNodes(loadedNodes);
          setEdges(validEdges);
          setActiveTab(tabId);
        })
        .catch(error => {
          console.error('Error fetching subgroup:', error);
          setTabData(prev => ({ ...prev, [tabId]: { nodes: [], edges: [] } }));
          setNodes([]);
          setEdges([]);
          setActiveTab(tabId);
        })
        .finally(() => setIsLoading(false));
    } else {
      setActiveTab(tabId);
      const currentTabData = tabData[tabId] || { nodes: [], edges: [] };
      const loadedNodes = addOnShrinkToNodes(currentTabData.nodes, false);
      const validEdges = currentTabData.edges.filter(edge =>
        loadedNodes.some(n => n.id === edge.source) && loadedNodes.some(n => n.id === edge.target)
      );
      setNodes(loadedNodes);
      setEdges(validEdges);
      setTabData(prev => ({ ...prev, [tabId]: { nodes: loadedNodes, edges: validEdges } }));
      setTimeout(() => {
        const revalidatedEdges = validEdges.filter(edge =>
          loadedNodes.some(n => n.id === edge.source) && loadedNodes.some(n => n.id === edge.target)
        );
        if (revalidatedEdges.length !== validEdges.length) {
          console.warn('Invalid edges detected in main tab switch:', { tabId, invalidEdges: validEdges.length - revalidatedEdges.length });
          setEdges(revalidatedEdges);
          setTabData(prev => ({
            ...prev,
            [tabId]: { ...prev[tabId], edges: revalidatedEdges }
          }));
        }
      }, 0);
      setIsLoading(false);
    }
  }, [eventId, subId, activeTab, tabData, tabs]);

  const handleTabClose = (tabId) => {
    if (tabId === 'main') return;
    setTabs(prev => prev.filter(t => t.id !== tabId));
    setTabData(prev => {
      const { [tabId]: _, ...rest } = prev;
      return rest;
    });
    if (activeTab === tabId) {
      handleTabSwitch('main');
    }
  };

  const onConnect = (params) => {
    console.log('onConnect called with params:', params);
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
      id: `${params.source}-${params.target}`, // 修正: エッジIDを明示
      animated: true,
      style: { strokeDasharray: '5,5', stroke: 'cyan', strokeWidth: 3 }
    };
    setEdges(eds => {
      const updatedEdges = addEdge(newEdge, eds);
      console.log('New edges after addEdge:', updatedEdges);
      return updatedEdges;
    });
    setTabData(prev => ({
      ...prev,
      [activeTab]: { nodes: prev[activeTab].nodes, edges: [...prev[activeTab].edges, newEdge] }
    }));
    adjustTargetIds(params.source, params.target);
    saveCurrentTab();
  };

  const adjustTargetIds = useCallback((sourceId, targetId, visited = new Set()) => {
    console.log('adjustTargetIds called with:', { sourceId, targetId, visited });
    if (visited.has(targetId)) return;
    visited.add(targetId);

    const currentNodes = tabData[activeTab]?.nodes || [];
    const sourceNode = currentNodes.find(n => n.id === sourceId);
    const targetNode = currentNodes.find(n => n.id === targetId);

    if (!sourceNode || !targetNode) {
      console.warn('Source or target node not found:', { sourceId, targetId });
      return;
    }

    const sourceNum = parseInt(sourceId, 10);
    if (isNaN(sourceNum)) {
      console.warn('Source ID is not a number:', sourceId);
      return;
    }

    let newTargetId = (sourceNum + 1).toString();
    while (currentNodes.some(n => n.id === newTargetId && n.id !== targetId)) {
      newTargetId = (parseInt(newTargetId, 10) + 1).toString();
    }

    if (newTargetId !== targetId) {
      console.log('Updating node ID from', targetId, 'to', newTargetId);
      updateNodeId(targetId, newTargetId);
      const updatedEdges = (tabData[activeTab]?.edges || []).map(edge => ({
        ...edge,
        source: edge.source === targetId ? newTargetId : edge.source,
        target: edge.target === targetId ? newTargetId : edge.target,
        id: `${edge.source === targetId ? newTargetId : edge.source}-${edge.target === targetId ? newTargetId : edge.target}` // 修正: エッジID更新
      }));
      setEdges(updatedEdges);
      setTabData(prev => ({
        ...prev,
        [activeTab]: {
          ...prev[activeTab],
          edges: updatedEdges
        }
      }));
    }

    const nextEdges = (tabData[activeTab]?.edges || []).filter(e => e.source === newTargetId);
    console.log('Next edges to process:', nextEdges);
    nextEdges.forEach(edge => {
      adjustTargetIds(newTargetId, edge.target, visited);
    });
  }, [tabData, activeTab, updateNodeId]);

  const handleOpenAddDialog = () => {
    setAddDialogOpen(true);
    setNewId('');
    setNewDescription('');
  };

  const handleCloseAddDialog = () => {
    setAddDialogOpen(false);
  };

  const handleAddNode = () => {
    if (!eventId || !subId) {
      alert('エラー: Event IDまたはSub IDが未定義です。');
      return;
    }
    if (!newId.trim()) {
      alert('IDを入力してください（数値推奨）');
      return;
    }
    if (tabData[activeTab].nodes.find(node => node.id === newId)) {
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
        subgroups: nodeType === 'customGroup' ? {} : {},
        isSubGroup: activeTab.startsWith('subgroup-'),
        onTabSwitch: nodeType === 'customGroup' ? (nodeId) => handleTabSwitch(`subgroup-${nodeId}`, nodeId) : undefined,
        saveCurrentTab,
      },
      draggable: true,
    };
    let updatedNodes = [...(tabData[activeTab]?.nodes || []), newNode];
    let newTabData = { ...tabData, [activeTab]: { nodes: updatedNodes, edges: tabData[activeTab]?.edges || [] } };
    if (activeTab.startsWith('subgroup-')) {
      newTabData.main = {
        ...tabData.main,
        nodes: tabData.main.nodes.map(node => {
          if (node.id === parentId) {
            const currentSubData = node.data.subgroups[parentId] || { nodes: [], edges: [] };
            const newSubNodes = [...currentSubData.nodes, newNode];
            return {
              ...node,
              data: {
                ...node.data,
                subgroups: {
                  ...node.data.subgroups,
                  [parentId]: { nodes: newSubNodes, edges: currentSubData.edges }
                }
              }
            };
          }
          return node;
        })
      };
    }
    setTabData(newTabData);
    setNodes(updatedNodes);
    saveCurrentTab();
  };

  const handleDeleteNode = (nodeId) => {
    if (!eventId || !subId) {
      alert('エラー: Event IDまたはSub IDが未定義です。');
      return;
    }
    setIsLoading(true);
    const parentId = activeTab.startsWith('subgroup-') ? activeTab.split('-')[1] : null;
    let updatedNodes = tabData[activeTab]?.nodes.filter(node => node.id !== nodeId) || [];
    const currentEdges = tabData[activeTab]?.edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId) || [];
    let newTabData = { ...tabData, [activeTab]: { nodes: updatedNodes, edges: currentEdges } };
    if (activeTab.startsWith('subgroup-')) {
      newTabData.main = {
        ...tabData.main,
        nodes: tabData.main.nodes.map(node => {
          if (node.id === parentId) {
            const currentSubData = node.data.subgroups[parentId] || { nodes: [], edges: [] };
            const newSubNodes = currentSubData.nodes.filter(n => n.id !== nodeId);
            const newSubEdges = currentSubData.edges.filter(e => e.source !== nodeId && e.target !== nodeId);
            return {
              ...node,
              data: {
                ...node.data,
                subgroups: {
                  ...node.data.subgroups,
                  [parentId]: { nodes: newSubNodes, edges: newSubEdges }
                }
              }
            };
          }
          return node;
        })
      };
    }
    setTabData(newTabData);
    setNodes(updatedNodes);
    setEdges(currentEdges);
    saveCurrentTab();
  };

  const handleCopyNode = (nodeId) => {
    const nodeToCopy = (tabData[activeTab]?.nodes || []).find(n => n.id === nodeId);
    if (nodeToCopy) {
      const isSub = activeTab.startsWith('subgroup-');
      setCopiedNode({
        ...nodeToCopy,
        type: isSub ? 'subGroupNode' : 'customGroup',
        data: {
          ...nodeToCopy.data,
          subgroups: isSub ? {} : nodeToCopy.data.subgroups || {}
        }
      });
    } else {
      alert('ノードが見つかりません');
    }
  };

  const handlePasteNode = () => {
    if (!copiedNode) {
      alert('コピーされたノードがありません');
      return;
    }
    if (!eventId || !subId) {
      alert('エラー: Event IDまたはSub IDが未定義です。');
      return;
    }
    setIsLoading(true);
    const currentNodes = tabData[activeTab].nodes;
    const isSub = activeTab.startsWith('subgroup-');
    const expectedType = isSub ? 'subGroupNode' : 'customGroup';
    if (copiedNode.type !== expectedType) {
      alert('このタブでは異なるタイプのノードをペーストできません');
      setIsLoading(false);
      return;
    }
    const ids = currentNodes.map(n => parseInt(n.id, 10)).filter(id => !isNaN(id));
    const maxId = ids.length > 0 ? Math.max(...ids) : 0;
    const newNodeId = (maxId + 1).toString();
    const parentId = isSub ? activeTab.split('-')[1] : null;
    const label = isSub ? `Group: ${parentId} / Sub: ${newNodeId}` : newNodeId;
    const newNode = {
      ...copiedNode,
      id: newNodeId,
      type: isSub ? 'subGroupNode' : 'customGroup',
      position: { x: copiedNode.position.x + 20, y: copiedNode.position.y + 20 },
      data: {
        ...copiedNode.data,
        label: label,
        subgroups: isSub ? {} : copiedNode.data.subgroups || {},
        isSubGroup: isSub,
        onTabSwitch: isSub ? undefined : (nodeId) => handleTabSwitch(`subgroup-${nodeId}`, nodeId),
        saveCurrentTab,
      }
    };
    let updatedNodes = [...currentNodes, newNode];
    let newTabData = { ...tabData, [activeTab]: { nodes: updatedNodes, edges: tabData[activeTab].edges } };
    if (isSub) {
      newTabData.main = {
        ...tabData.main,
        nodes: tabData.main.nodes.map(node => {
          if (node.id === parentId) {
            const currentSubData = node.data.subgroups[parentId] || { nodes: [], edges: [] };
            const newSubNodes = [...currentSubData.nodes, newNode];
            return {
              ...node,
              data: {
                ...node.data,
                subgroups: {
                  ...node.data.subgroups,
                  [parentId]: { nodes: newSubNodes, edges: currentSubData.edges }
                }
              }
            };
          }
          return node;
        })
      };
    }
    setTabData(newTabData);
    setNodes(updatedNodes);
    saveCurrentTab();
  };

  const handleOpenEditDialog = (nodeId) => {
    const node = tabData[activeTab].nodes.find(n => n.id === nodeId);
    if (node) {
      setEditNodeId(nodeId);
      setNewId(node.id);
      setNewDescription(node.data.description || '');
      setEditDialogOpen(true);
    }
  };

  const handleCloseEditDialog = () => {
    setEditDialogOpen(false);
    setEditNodeId(null);
  };

  const handleEditNode = () => {
    if (!newId.trim()) {
      alert('IDを入力してください（数値推奨）');
      return;
    }
    updateNodeId(editNodeId, newId.trim());
    const updatedNodes = tabData[activeTab].nodes.map(node =>
      node.id === newId ? { ...node, data: { ...node.data, description: newDescription.trim() } } : node
    );
    setTabData(prev => ({ ...prev, [activeTab]: { nodes: updatedNodes, edges: prev[activeTab].edges } }));
    setNodes(updatedNodes);
    saveCurrentTab();
    handleCloseEditDialog();
  };

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Backdrop open={isLoading} sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
        <CircularProgress color="inherit" />
      </Backdrop>
      <AppBar position="static">
        <Tabs value={activeTab} onChange={(e, newValue) => handleTabSwitch(newValue)} sx={{ bgcolor: 'primary.main' }}>
          {tabs.map(tab => (
            <Tab
              key={tab.id}
              value={tab.id}
              label={
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Typography>{tab.label}</Typography>
                  {tab.id !== 'main' && (
                    <IconButton size="small" onClick={(e) => { e.stopPropagation(); handleTabClose(tab.id); }}>
                      <CloseIcon />
                    </IconButton>
                  )}
                </Box>
              }
            />
          ))}
        </Tabs>
        <Box sx={{ p: 1, display: 'flex', gap: 1 }}>
          <Button variant="contained" color="secondary" onClick={handleOpenAddDialog} disabled={isLoading}>
            ノード追加
          </Button>
          <Button variant="contained" color="secondary" onClick={handlePasteNode} disabled={isLoading || !copiedNode}>
            ノードペースト
          </Button>
          <Button variant="contained" color="primary" onClick={saveCurrentTab} disabled={isLoading}>
            保存
          </Button>
        </Box>
      </AppBar>
      <Box sx={{ flexGrow: 1, height: 'calc(100vh - 64px)' }}>
        <ReactFlow
          nodes={memoizedNodes}
          edges={memoizedEdges}
          onNodesChange={(changes) => {
            onNodesChange(changes);
            setTabData(prev => {
              const updated = applyNodeChanges(changes, prev[activeTab].nodes);
              const newTabData = { ...prev, [activeTab]: { ...prev[activeTab], nodes: updated } };
              if (activeTab.startsWith('subgroup-')) {
                const parentId = activeTab.split('-')[1];
                newTabData.main = {
                  ...prev.main,
                  nodes: prev.main.nodes.map(node =>
                    node.id === parentId ? {
                      ...node,
                      data: {
                        ...node.data,
                        subgroups: {
                          ...node.data.subgroups,
                          [parentId]: { nodes: updated, edges: prev[activeTab].edges }
                        }
                      }
                    } : node
                  )
                };
              }
              return newTabData;
            });
            if (changes.some(change => change.type === 'add' || change.type === 'remove')) {
              saveCurrentTab();
            }
          }}
          onEdgesChange={(changes) => {
            onEdgesChange(changes);
            saveCurrentTab();
          }}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          style={{ backgroundColor: 'black' }}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={true}
          minZoom={0.5}
          maxZoom={2}
        >
          <Background variant="lines" color="white" gap={20} size={1} />
          <Controls />
        </ReactFlow>
      </Box>
      <Dialog open={addDialogOpen} onClose={handleCloseAddDialog}>
        <DialogTitle>ノード追加</DialogTitle>
        <DialogContent>
          <TextField
            label="ID（数値推奨）"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            fullWidth
            margin="normal"
          />
          <TextField
            label="説明"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            fullWidth
            margin="normal"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseAddDialog}>キャンセル</Button>
          <Button onClick={handleAddNode} variant="contained">追加</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={editDialogOpen} onClose={handleCloseEditDialog}>
        <DialogTitle>ノード編集</DialogTitle>
        <DialogContent>
          <TextField
            label="ID（数値推奨）"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            fullWidth
            margin="normal"
          />
          <TextField
            label="説明"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            fullWidth
            margin="normal"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseEditDialog}>キャンセル</Button>
          <Button onClick={handleEditNode} variant="contained">保存</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ScenarioEventTransition;