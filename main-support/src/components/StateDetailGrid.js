import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Grid, Card, CardContent, IconButton, Autocomplete, List, ListItem, ListItemText } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import CloseIcon from '@mui/icons-material/Close';
import SaveIcon from '@mui/icons-material/Save';
import { styled } from '@mui/material/styles';
import { ReactFlow, Background, Controls, MiniMap, useReactFlow, addEdge, Handle, Position, applyNodeChanges } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const CustomNode = ({ data, id }) => {
  const handleDelete = () => {
    window.dispatchEvent(new CustomEvent('deleteNode', { detail: id }));
  };

  const handleShowCode = () => {
    console.log(`Opening code for node ${id}`);
  };

  return (
    <div className="bg-gray-900 rounded-lg text-white w-72" style={{ minHeight: '80px', position: 'relative' }}>
      <IconButton size="small" onClick={handleDelete} style={{ position: 'absolute', top: 4, right: 4, color: 'red' }}>
        <CloseIcon fontSize="small" />
      </IconButton>
      <Button variant="outlined" size="small" onClick={handleShowCode} style={{ position: 'absolute', top: 32, right: 4, color: 'white', borderColor: 'white' }}>
        Show Code
      </Button>
      <div className="bg-gradient-to-r from-blue-800 to-blue-600 p-2 flex items-center justify-center">
        <Typography variant="subtitle1" className="font-semibold text-center text-white">
          {data.label}
        </Typography>
      </div>
      <div className="p-3 bg-gray-800 flex items-center justify-center">
        <Typography variant="caption" className="text-gray-400">
          ID: {id}
        </Typography>
      </div>
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: '#ffffff', border: '2px solid #1E40AF', width: 12, height: 12, borderRadius: '50%', left: '-0.75rem', top: '25%', position: 'absolute' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: '#ffffff', border: '2px solid #1E40AF', width: 12, height: 12, borderRadius: '50%', right: '-0.75rem', top: '75%', position: 'absolute' }}
      />
    </div>
  );
};

const nodeTypes = { default: CustomNode };

function StateDetailGrid() {
  const { name } = useParams();
  const [transitions, setTransitions] = useState([]);
  const [selectedTransition, setSelectedTransition] = useState(null);
  const [transitionVariables, setTransitionVariables] = useState([]);
  const [managerData, setManagerData] = useState([]);
  const [baseData, setBaseData] = useState([]);
  const [openTransitionDialog, setOpenTransitionDialog] = useState(false);
  const [openVariableDialog, setOpenVariableDialog] = useState(false);
  const [openManagerDialog, setOpenManagerDialog] = useState(false);
  const [openFlow, setOpenFlow] = useState(false);
  const [newFromState, setNewFromState] = useState('');
  const [newType, setNewType] = useState('');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newArraySize, setNewArraySize] = useState(0);
  const [typeOptions, setTypeOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [flowElements, setFlowElements] = useState({ nodes: [], edges: [] });
  const [dialogType, setDialogType] = useState('');
  const [filterText, setFilterText] = useState('');
  const [filteredTransitions, setFilteredTransitions] = useState([]);
  const { fitView, screenToFlowPosition } = useReactFlow();
  const reactFlowWrapper = useRef(null);

  useEffect(() => {
    const handleDeleteNode = (e) => {
      const nodeId = e.detail;
      setFlowElements((els) => {
        const deletedNodeIndex = els.nodes.findIndex((n) => n.id === nodeId);
        if (deletedNodeIndex === -1) return els;

        const updatedNodes = els.nodes.filter((n) => n.id !== nodeId);
        const updatedEdges = els.edges.filter((e) => e.source !== nodeId && e.target !== nodeId);

        // Update targets in other nodes
        const updatedNodesWithoutTargets = updatedNodes.map(node => ({
          ...node,
          data: {
            ...node.data,
            targets: node.data.targets ? node.data.targets.filter(t => t !== nodeId) : []
          }
        }));

        // Reassign IDs sequentially
        const sortedNodes = updatedNodesWithoutTargets
          .sort((a, b) => parseInt(a.id) - parseInt(b.id));
        const reassignedNodes = sortedNodes.map((node, index) => ({
          ...node,
          id: (index + 1).toString()
        }));

        // Update edges with new IDs
        const idMap = {};
        sortedNodes.forEach((node, index) => {
          idMap[node.id] = (index + 1).toString();
        });
        const reassignedEdges = updatedEdges.map(edge => ({
          ...edge,
          source: idMap[edge.source] || edge.source,
          target: idMap[edge.target] || edge.target
        }));

        // Update targets with new IDs
        const reassignedNodesWithTargets = reassignedNodes.map(node => ({
          ...node,
          data: {
            ...node.data,
            targets: node.data.targets.map(t => idMap[t] || t)
          }
        }));

        return { nodes: reassignedNodesWithTargets, edges: reassignedEdges };
      });
    };

    window.addEventListener('deleteNode', handleDeleteNode);
    return () => window.removeEventListener('deleteNode', handleDeleteNode);
  }, []);

  useEffect(() => {
    setLoading(true);
    const fetchData = async () => {
      try {
        const response = await fetch(`/api/state-data/${name}`);
        const data = await response.json();
        let validData = typeof data === 'object' && !Array.isArray(data) ? data : { transitions: [], manager: [], base: [], edges: [], nodes: [] };

        if (Array.isArray(data) && data.length === 0) {
          validData = { transitions: [], manager: [], base: [], edges: [], nodes: [] };
          const reResponse = await fetch(`/api/state-data/${name}`);
          validData = await reResponse.json();
        }

        const validTransitions = Array.isArray(validData.transitions)
          ? validData.transitions.map((item, index) => ({
              id: item.id || index + 1,
              fromState: item.fromState || '',
              variables: Array.isArray(item.variables) ? item.variables : [],
            }))
          : [];
        const validManagerData = Array.isArray(validData.manager)
          ? validData.manager.map((item, index) => ({
              id: item.id || index + 1,
              type: item.type || '',
              name: item.name || '',
              description: item.description || '',
              arraySize: item.arraySize || 0,
            }))
          : [];
        const validBaseData = Array.isArray(validData.base)
          ? validData.base.map((item, index) => ({
              id: item.id || index + 1,
              type: item.type || '',
              name: item.name || '',
              description: item.description || '',
              arraySize: item.arraySize || 0,
            }))
          : [];
        const validEdges = Array.isArray(validData.edges)
          ? validData.edges.map((edge, index) => ({
              id: edge.id || `e${index}`,
              source: edge.source,
              target: edge.target,
              type: 'custom',
              style: { stroke: '#FFFF00', strokeWidth: 6 },
            }))
          : [];
        const validNodes = Array.isArray(validData.nodes)
          ? validData.nodes.map(node => ({
              ...node,
              data: { ...node.data, targets: node.data.targets || [] }
            }))
          : [];

        setTransitions(validTransitions);
        setManagerData(validManagerData);
        setBaseData(validBaseData);
        setSelectedTransition(null);
        setTransitionVariables([]);
        setFlowElements({
          nodes: validNodes,
          edges: validEdges,
        });
      } catch (error) {
        console.error('状態データの取得エラー:', error);
        const defaultData = { transitions: [], manager: [], base: [], edges: [], nodes: [] };
        setTransitions([]);
        setManagerData([]);
        setBaseData([]);
        setSelectedTransition(null);
        setTransitionVariables([]);
        setFlowElements({ nodes: [], edges: [] });
      } finally {
        setLoading(false);
      }

      const basicTypes = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object'];
      const unityTypes = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject'];
      try {
        const [enumResponse, classResponse] = await Promise.all([
          fetch('/api/enum-id').then(res => res.json()).catch(() => []),
          fetch('/api/class-data').then(res => res.json()).catch(() => []),
        ]);
        const enumTypes = Array.isArray(enumResponse) ? enumResponse.map(item => item.name || '') : [];
        const classTypes = Array.isArray(classResponse) ? classResponse.map(item => item.name || '') : [];
        setTypeOptions([...basicTypes, ...unityTypes, ...enumTypes, ...classTypes].filter(Boolean));
      } catch (error) {
        console.error('型オプションの取得エラー:', error);
        setTypeOptions([...basicTypes, ...unityTypes]);
      }
    };

    fetchData();
  }, [name]);

  const handleSaveStateData = async () => {
    try {
      const data = {
        transitions,
        manager: managerData,
        base: baseData,
        nodes: flowElements.nodes,
        edges: flowElements.edges,
      };
      const response = await fetch(`/api/state-data/${name}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const result = await response.json();
      alert(result.message || 'データを保存しました');
    } catch (error) {
      console.error('データの保存エラー:', error);
      alert('データの保存エラー: ' + error.message);
    }
  };

const handleGenerateCs = async () => {
  const data = {
    transitions,
    manager: managerData,
    base: baseData,
    nodes: flowElements.nodes,
    edges: flowElements.edges,
  };

  // ここを必ず data にする
  fetch(`/api/generate-state/${name}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
    .then(response => response.json())
    .then(result => alert(result.message))
    .catch(error => alert('C#生成エラー: ' + error));
};


  const handleAddTransition = () => {
    if (!newFromState.trim()) {
      alert('状態名は必須です');
      return;
    }
    const newId = Math.max(...transitions.map(item => item.id), 0) + 1;
    const newTransition = {
      id: newId,
      fromState: newFromState,
      variables: [],
    };
    setTransitions([...transitions, newTransition]);
    setOpenTransitionDialog(false);
    setNewFromState('');
  };

  const handleDeleteTransition = (id) => {
    const transitionToDelete = transitions.find(item => item.id === id);
    if (!transitionToDelete) return;

    const newTransitions = transitions.filter(item => item.id !== id);
    setTransitions(newTransitions);

    setFlowElements((els) => {
      // Find node with matching label
      const nodeToDelete = els.nodes.find(n => n.data.label === transitionToDelete.fromState);
      if (!nodeToDelete) return els;

      const nodeId = nodeToDelete.id;

      const updatedNodes = els.nodes.filter(n => n.id !== nodeId);
      const updatedEdges = els.edges.filter(e => e.source !== nodeId && e.target !== nodeId);

      // Update targets in other nodes
      const updatedNodesWithoutTargets = updatedNodes.map(node => ({
        ...node,
        data: {
          ...node.data,
          targets: node.data.targets ? node.data.targets.filter(t => t !== nodeId) : []
        }
      }));

      // Reassign IDs sequentially
      const sortedNodes = updatedNodesWithoutTargets.sort((a, b) => parseInt(a.id) - parseInt(b.id));
      const reassignedNodes = sortedNodes.map((node, index) => ({
        ...node,
        id: (index + 1).toString()
      }));

      // Update edges with new IDs
      const idMap = {};
      sortedNodes.forEach((node, index) => {
        idMap[node.id] = (index + 1).toString();
      });
      const reassignedEdges = updatedEdges.map(edge => ({
        ...edge,
        source: idMap[edge.source] || edge.source,
        target: idMap[edge.target] || edge.target
      }));

      // Update targets with new IDs
      const reassignedNodesWithTargets = reassignedNodes.map(node => ({
        ...node,
        data: {
          ...node.data,
          targets: node.data.targets.map(t => idMap[t] || t)
        }
      }));

      return { nodes: reassignedNodesWithTargets, edges: reassignedEdges };
    });

    if (selectedTransition?.id === id) {
      setSelectedTransition(null);
      setTransitionVariables([]);
    }
  };

  const handleSelectTransition = (id) => {
    const transition = transitions.find(item => item.id === id);
    setSelectedTransition(transition);
    const validVariables = Array.isArray(transition?.variables)
      ? transition.variables.map((item, index) => ({
          id: item.id || index + 1,
          type: item.type || '',
          name: item.name || '',
          description: item.description || '',
          arraySize: item.arraySize || 0,
        }))
      : [];
    setTransitionVariables(validVariables);
  };

  const handleAddVariable = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('型と名前は必須です');
      return;
    }
    if (isNaN(newArraySize) || newArraySize < -1) {
      alert('配列サイズは-1（リスト）、0（単一）、または正の数でなければなりません');
      return;
    }
    const newId = Math.max(...transitionVariables.map(item => item.id), 0) + 1;
    const newVariable = {
      id: newId,
      type: newType,
      name: newName,
      description: newDescription,
      arraySize: parseInt(newArraySize, 10),
    };
    const newVariables = [...transitionVariables, newVariable];
    setTransitionVariables(newVariables);
    setTransitions(transitions.map(t =>
      t.id === selectedTransition?.id ? { ...t, variables: newVariables } : t
    ));
    setOpenVariableDialog(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
    setNewArraySize(0);
  };

  const handleDeleteVariable = (id) => {
    const newVariables = transitionVariables.filter(item => item.id !== id);
    setTransitionVariables(newVariables);
    setTransitions(transitions.map(t =>
      t.id === selectedTransition?.id ? { ...t, variables: newVariables } : t
    ));
  };

  const handleAddManagerRow = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('型と名前は必須です');
      return;
    }
    if (isNaN(newArraySize) || newArraySize < -1) {
      alert('配列サイズは-1（リスト）、0（単一）、または正の数でなければなりません');
      return;
    }
    const newId = Math.max(...managerData.map(item => item.id), 0) + 1;
    const newRow = {
      id: newId,
      type: newType,
      name: newName,
      description: newDescription,
      arraySize: parseInt(newArraySize, 10),
    };
    setManagerData([...managerData, newRow]);
    setOpenManagerDialog(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
    setNewArraySize(0);
  };

  const handleDeleteManagerRow = (id) => {
    setManagerData(managerData.filter(item => item.id !== id));
  };

  const handleAddBaseRow = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('型と名前は必須です');
      return;
    }
    if (isNaN(newArraySize) || newArraySize < -1) {
      alert('配列サイズは-1（リスト）、0（単一）、または正の数でなければなりません');
      return;
    }
    const newId = Math.max(...baseData.map(item => item.id), 0) + 1;
    const newRow = {
      id: newId,
      type: newType,
      name: newName,
      description: newDescription,
      arraySize: parseInt(newArraySize, 10),
    };
    setBaseData([...baseData, newRow]);
    setOpenManagerDialog(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
    setNewArraySize(0);
  };

  const handleDeleteBaseRow = (id) => {
    setBaseData(baseData.filter(item => item.id !== id));
  };

  const onConnect = useCallback((connection) => {
    setFlowElements((els) => {
      const newEdge = { ...connection, id: `e${els.edges.length + 1}`, type: 'custom', style: { stroke: '#FFFF00', strokeWidth: 6 } };
      const updatedEdges = addEdge(newEdge, els.edges);

      const updatedNodes = els.nodes.map((node) => {
        if (node.id === connection.source) {
          const targets = node.data.targets || [];
          return {
            ...node,
            data: { ...node.data, targets: [...new Set([...targets, connection.target])] },
          };
        }
        return node;
      });

      return { nodes: updatedNodes, edges: updatedEdges };
    });
  }, []);

  const onNodesDelete = useCallback((nodesToDelete) => {
    if (!nodesToDelete || nodesToDelete.length === 0) return;
    setFlowElements((els) => {
      const updatedNodes = els.nodes.filter(n => !nodesToDelete.some(del => del.id === n.id));
      const updatedEdges = els.edges.filter(e => !nodesToDelete.some(del => del.id === e.source || del.id === e.target));
      return { nodes: updatedNodes, edges: updatedEdges };
    });
  }, []);

  const onEdgesDelete = useCallback((edgesToDelete) => {
    if (!edgesToDelete || edgesToDelete.length === 0) return;
    setFlowElements((els) => {
      const updatedEdges = els.edges.filter(e => !edgesToDelete.some(del => del.id === e.id));
      // Update targets in nodes if necessary
      const updatedNodes = els.nodes.map(node => {
        if (node.data.targets) {
          const newTargets = node.data.targets.filter(target => 
            !edgesToDelete.some(del => del.source === node.id && del.target === target)
          );
          return { ...node, data: { ...node.data, targets: newTargets } };
        }
        return node;
      });
      return { nodes: updatedNodes, edges: updatedEdges };
    });
  }, []);

  const onNodesChange = useCallback((changes) => {
    setFlowElements((els) => ({
      ...els,
      nodes: applyNodeChanges(changes, els.nodes),
    }));
  }, []);

  const onInit = useCallback(() => {
    fitView({ duration: 400 });
  }, [fitView]);

  const onNodeDragStart = useCallback((event, node) => {
    setFlowElements((els) => ({
      ...els,
      nodes: els.nodes.map(n => ({ ...n, selected: n.id === node.id })),
    }));
  }, []);

  const onDragStart = (event, transitionId, label) => {
    event.dataTransfer.setData('application/reactflow', JSON.stringify({ transitionId, label }));
    event.dataTransfer.effectAllowed = 'move';
  };

  const onDrop = useCallback((event) => {
    event.preventDefault();
    if (!reactFlowWrapper.current) return;

    const data = event.dataTransfer.getData('application/reactflow');
    if (!data) return;

    const { label } = JSON.parse(data);
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });

    const currentMaxId = flowElements.nodes.reduce((max, n) => Math.max(max, parseInt(n.id) || 0), 0);
    const newNodeId = (currentMaxId + 1).toString();

    const newNode = {
      id: newNodeId,
      type: 'default',
      position,
      data: { label, targets: [] },
      draggable: true,
    };

    setFlowElements((els) => ({
      ...els,
      nodes: [...els.nodes, newNode],
    }));
  }, [screenToFlowPosition, flowElements.nodes]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const StyledDataGrid = styled(DataGrid)(({ theme }) => ({
    '& .MuiDataGrid-row': {
      transition: 'background-color 0.2s',
      '&:hover': { backgroundColor: theme.palette.action.hover },
    },
    '& .MuiDataGrid-row.Mui-selected': {
      backgroundColor: theme.palette.primary.light,
      color: theme.palette.primary.contrastText,
      '&:hover': { backgroundColor: theme.palette.primary.main },
    },
    '& .MuiDataGrid-cell': { padding: theme.spacing(1), color: theme.palette.text.primary },
    '& .MuiDataGrid-columnHeaders': { backgroundColor: theme.palette.primary.main, color: '#000000', fontWeight: 'bold' },
  }));

  useEffect(() => {
    setFilteredTransitions(
      transitions.filter(t => t.fromState.toLowerCase().includes(filterText.toLowerCase()))
    );
  }, [filterText, transitions]);

  const transitionColumns = [
    { field: 'id', headerName: 'ID', width: 100 },
    { field: 'fromState', headerName: '状態名', width: 150 },
    {
      field: 'actions',
      headerName: 'アクション',
      width: 100,
      renderCell: (params) => (
        <IconButton color="error" onClick={() => handleDeleteTransition(params.row.id)}>
          <DeleteIcon />
        </IconButton>
      ),
    },
  ];

  const variableColumns = [
    { field: 'id', headerName: 'ID', width: 100 },
    {
      field: 'type',
      headerName: '型',
      width: 200,
      editable: true,
      renderEditCell: (params) => (
        <Autocomplete
          freeSolo
          options={typeOptions}
          value={params.value || ''}
          onChange={(e, newValue) => params.api.setEditCellValue({ id: params.id, field: params.field, value: newValue || '' })}
          renderInput={(params) => <TextField {...params} />}
        />
      ),
    },
    { field: 'name', headerName: '名前', width: 150, editable: true },
    { field: 'description', headerName: '説明', width: 250, editable: true },
    { field: 'arraySize', headerName: '配列サイズ', width: 100, editable: true, type: 'number' },
    {
      field: 'actions',
      headerName: 'アクション',
      width: 100,
      renderCell: (params) => (
        <IconButton color="error" onClick={() => handleDeleteVariable(params.row.id)}>
          <DeleteIcon />
        </IconButton>
      ),
    },
  ];

  const managerColumns = [
    { field: 'id', headerName: 'ID', width: 100 },
    {
      field: 'type',
      headerName: '型',
      width: 200,
      editable: true,
      renderEditCell: (params) => (
        <Autocomplete
          freeSolo
          options={typeOptions}
          value={params.value || ''}
          onChange={(e, newValue) => params.api.setEditCellValue({ id: params.id, field: params.field, value: newValue || '' })}
          renderInput={(params) => <TextField {...params} />}
        />
      ),
    },
    { field: 'name', headerName: '名前', width: 150, editable: true },
    { field: 'description', headerName: '説明', width: 250, editable: true },
    { field: 'arraySize', headerName: '配列サイズ', width: 100, editable: true, type: 'number' },
    {
      field: 'actions',
      headerName: 'アクション',
      width: 100,
      renderCell: (params) => (
        <IconButton color="error" onClick={() => dialogType === 'base' ? handleDeleteBaseRow(params.row.id) : handleDeleteManagerRow(params.row.id)}>
          <DeleteIcon />
        </IconButton>
      ),
    },
  ];

  return (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main', mb: 4 }}>
        状態詳細: {name || '不明'}
      </Typography>

      <Box sx={{ mb: 2 }}>
        <Button
          variant="contained"
          color="primary"
          startIcon={<SaveIcon />}
          onClick={handleSaveStateData}
          sx={{ mr: 2, textTransform: 'none' }}
        >
          保存
        </Button>
        <Button
          variant="contained"
          color="secondary"
          onClick={handleGenerateCs}
          sx={{ mr: 1 }}
        >
          C#生成
        </Button>
      </Box>

      {loading ? (
        <Typography>読み込み中...</Typography>
      ) : (
        <>
          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid item xs={12} md={6}>
              <Card sx={{ boxShadow: 3, borderRadius: 2, bgcolor: 'background.paper' }}>
                <CardContent>
                  <Typography variant="h5" gutterBottom sx={{ fontWeight: 'medium', color: 'text.primary' }}>
                    状態遷移
                  </Typography>
                  <Button
                    variant="contained"
                    color="primary"
                    startIcon={<AddIcon />}
                    onClick={() => setOpenTransitionDialog(true)}
                    sx={{ mb: 2, borderRadius: 2, textTransform: 'none', mr: 2 }}
                  >
                    遷移を追加
                  </Button>
                  <Button
                    variant="contained"
                    color="secondary"
                    onClick={() => setOpenFlow(true)}
                    sx={{ mb: 2, borderRadius: 2, textTransform: 'none' }}
                  >
                    遷移図を表示
                  </Button>
                  <StyledDataGrid
                    rows={transitions}
                    columns={transitionColumns}
                    pageSizeOptions={[5]}
                    getRowId={(row) => row.id}
                    onRowClick={(params) => handleSelectTransition(params.row.id)}
                    selectionModel={selectedTransition ? [selectedTransition.id] : []}
                    onSelectionModelChange={(newModel) => {
                      const id = newModel[0];
                      if (id) handleSelectTransition(id);
                      else {
                        setSelectedTransition(null);
                        setTransitionVariables([]);
                      }
                    }}
                    disableMultipleSelection
                    hideFooter={transitions.length === 0}
                    loading={loading}
                    sx={{ height: 400 }}
                  />
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card sx={{ boxShadow: 3, borderRadius: 2, bgcolor: 'background.paper' }}>
                <CardContent>
                  <Typography variant="h5" gutterBottom sx={{ fontWeight: 'medium', color: 'text.primary' }}>
                    遷移変数 {selectedTransition ? `(${selectedTransition.fromState})` : '(遷移を選択してください)'}
                  </Typography>
                  <Button
                    variant="contained"
                    color="primary"
                    startIcon={<AddIcon />}
                    onClick={() => setOpenVariableDialog(true)}
                    sx={{ mb: 2, borderRadius: 2, textTransform: 'none' }}
                    disabled={!selectedTransition}
                  >
                    変数を追加
                  </Button>
                  <StyledDataGrid
                    rows={transitionVariables}
                    columns={variableColumns}
                    pageSizeOptions={[5]}
                    getRowId={(row) => row.id}
                    hideFooter={transitionVariables.length === 0}
                    loading={loading}
                    sx={{ height: 400 }}
                  />
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid item xs={12}>
              <Card sx={{ boxShadow: 3, borderRadius: 2, bgcolor: 'background.paper' }}>
                <CardContent>
                  <Typography variant="h5" gutterBottom sx={{ fontWeight: 'medium', color: 'text.primary' }}>
                    マネージャーデータ
                  </Typography>
                  <Button
                    variant="contained"
                    color="primary"
                    startIcon={<AddIcon />}
                    onClick={() => {
                      setDialogType('manager');
                      setOpenManagerDialog(true);
                    }}
                    sx={{ mb: 2, borderRadius: 2, textTransform: 'none' }}
                  >
                    データを追加
                  </Button>
                  <StyledDataGrid
                    rows={managerData}
                    columns={managerColumns}
                    pageSizeOptions={[5]}
                    getRowId={(row) => row.id}
                    hideFooter={managerData.length === 0}
                    loading={loading}
                    sx={{ height: 400 }}
                  />
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Grid container spacing={3}>
            <Grid item xs={12}>
              <Card sx={{ boxShadow: 3, borderRadius: 2, bgcolor: 'background.paper' }}>
                <CardContent>
                  <Typography variant="h5" gutterBottom sx={{ fontWeight: 'medium', color: 'text.primary' }}>
                    ベースデータ
                  </Typography>
                  <Button
                    variant="contained"
                    color="primary"
                    startIcon={<AddIcon />}
                    onClick={() => {
                      setDialogType('base');
                      setOpenManagerDialog(true);
                    }}
                    sx={{ mb: 2, borderRadius: 2, textTransform: 'none' }}
                  >
                    データを追加
                  </Button>
                  <StyledDataGrid
                    rows={baseData}
                    columns={managerColumns}
                    pageSizeOptions={[5]}
                    getRowId={(row) => row.id}
                    hideFooter={baseData.length === 0}
                    loading={loading}
                    sx={{ height: 400 }}
                  />
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Dialog open={openFlow} onClose={() => setOpenFlow(false)} maxWidth="xl" fullWidth>
            <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>
              遷移図: {name || '不明'}
            </DialogTitle>
            <DialogContent sx={{ p: 0, height: '80vh', display: 'flex' }}>
              <div
                ref={reactFlowWrapper}
                style={{ flex: 1, height: '100%' }}
                onDrop={onDrop}
                onDragOver={onDragOver}
              >
                <ReactFlow
                  nodes={flowElements.nodes}
                  edges={flowElements.edges}
                  onConnect={onConnect}
                  onNodesDelete={onNodesDelete}
                  onEdgesDelete={onEdgesDelete}
                  onInit={onInit}
                  onNodeDragStart={onNodeDragStart}
                  snapToGrid
                  snapGrid={[15, 15]}
                  nodeTypes={nodeTypes}
                  onNodesChange={onNodesChange}
                  defaultEdgeOptions={{ type: 'custom', style: { stroke: '#FFFF00', strokeWidth: 6 } }}
                >
                  <Background variant="dots" gap={15} size={1} />
                  <Controls />
                  <MiniMap nodeStrokeColor="#1E40AF" nodeColor="#90CAF9" nodeBorderRadius={2} />
                </ReactFlow>
              </div>
              <Box sx={{ width: 300, bgcolor: 'background.paper', p: 2, borderLeft: 1, borderColor: 'divider', overflowY: 'auto' }}>
                <Typography variant="h6" gutterBottom>
                  遷移リスト (ドラッグして追加)
                </Typography>
                <TextField
                  label="遷移を検索"
                  fullWidth
                  value={filterText}
                  onChange={(e) => setFilterText(e.target.value)}
                  margin="dense"
                  variant="outlined"
                  placeholder="状態名でフィルタリング"
                />
                <List>
                  {filteredTransitions.length > 0 ? (
                    filteredTransitions.map((transition) => (
                      <ListItem
                        key={transition.id}
                        draggable
                        onDragStart={(e) => onDragStart(e, transition.id, transition.fromState)}
                      >
                        <ListItemText primary={transition.fromState} />
                      </ListItem>
                    ))
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      該当する遷移がありません
                    </Typography>
                  )}
                </List>
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenFlow(false)} color="secondary" sx={{ textTransform: 'none' }}>
                閉じる
              </Button>
              <Button
                variant="contained"
                color="primary"
                startIcon={<SaveIcon />}
                onClick={handleSaveStateData}
                sx={{ textTransform: 'none' }}
              >
                保存
              </Button>
            </DialogActions>
          </Dialog>

          <Dialog open={openTransitionDialog} onClose={() => setOpenTransitionDialog(false)} maxWidth="sm" fullWidth>
            <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>新しい遷移を追加</DialogTitle>
            <DialogContent sx={{ pt: 2 }}>
              <TextField
                label="状態名"
                fullWidth
                value={newFromState}
                onChange={(e) => setNewFromState(e.target.value)}
                margin="dense"
                variant="outlined"
                required
              />
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenTransitionDialog(false)} color="secondary" sx={{ textTransform: 'none' }}>
                キャンセル
              </Button>
              <Button onClick={handleAddTransition} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
                追加
              </Button>
            </DialogActions>
          </Dialog>

          <Dialog open={openVariableDialog} onClose={() => setOpenVariableDialog(false)} maxWidth="sm" fullWidth>
            <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>新しい変数を追加</DialogTitle>
            <DialogContent sx={{ pt: 2 }}>
              <Autocomplete
                freeSolo
                options={typeOptions}
                value={newType}
                onChange={(e, newValue) => setNewType(newValue || '')}
                renderInput={(params) => <TextField {...params} label="型" fullWidth margin="dense" variant="outlined" required />}
              />
              <TextField
                label="名前"
                fullWidth
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                margin="dense"
                variant="outlined"
                required
              />
              <TextField
                label="説明"
                fullWidth
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                margin="dense"
                variant="outlined"
              />
              <TextField
                label="配列サイズ"
                fullWidth
                type="number"
                value={newArraySize}
                onChange={(e) => setNewArraySize(e.target.value)}
                margin="dense"
                variant="outlined"
              />
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenVariableDialog(false)} color="secondary" sx={{ textTransform: 'none' }}>
                キャンセル
              </Button>
              <Button onClick={handleAddVariable} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
                追加
              </Button>
            </DialogActions>
          </Dialog>

          <Dialog open={openManagerDialog} onClose={() => setOpenManagerDialog(false)} maxWidth="sm" fullWidth>
            <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>
              新しい{dialogType === 'manager' ? 'マネージャーデータ' : 'ベースデータ'}を追加
            </DialogTitle>
            <DialogContent sx={{ pt: 2 }}>
              <Autocomplete
                freeSolo
                options={typeOptions}
                value={newType}
                onChange={(e, newValue) => setNewType(newValue || '')}
                renderInput={(params) => <TextField {...params} label="型" fullWidth margin="dense" variant="outlined" required />}
              />
              <TextField
                label="名前"
                fullWidth
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                margin="dense"
                variant="outlined"
                required
              />
              <TextField
                label="説明"
                fullWidth
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                margin="dense"
                variant="outlined"
              />
              <TextField
                label="配列サイズ"
                fullWidth
                type="number"
                value={newArraySize}
                onChange={(e) => setNewArraySize(e.target.value)}
                margin="dense"
                variant="outlined"
              />
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenManagerDialog(false)} color="secondary" sx={{ textTransform: 'none' }}>
                キャンセル
              </Button>
              <Button
                onClick={dialogType === 'manager' ? handleAddManagerRow : handleAddBaseRow}
                color="primary"
                variant="contained"
                sx={{ textTransform: 'none' }}
              >
                追加
              </Button>
            </DialogActions>
          </Dialog>
        </>
      )}
    </Box>
  );
}

export default StateDetailGrid;