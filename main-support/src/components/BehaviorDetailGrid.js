import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Autocomplete, Card, CardContent, Grid, MenuItem, Select, FormControl, InputLabel,
  Paper
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import SaveIcon from '@mui/icons-material/Save';
import CodeIcon from '@mui/icons-material/Code';
import { DataGrid } from '@mui/x-data-grid';
import {
  ReactFlow, Background, Controls, MiniMap, Handle, Position
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { createPortal } from 'react-dom';

// ノードの色
const nodeColors = {
  sequence: '#1976d2',
  selector: '#2e7d32',
  parallel: '#7b1fa2',
  race: '#d81b60',
  randomsequence: '#388e3c',
  randomselector: '#f57c00',
  priorityselector: '#0288d1',
  inverter: '#c2185b',
  succeeder: '#43a047',
  failer: '#e53935',
  repeater: '#5e35b1',
  repeatuntilfail: '#fb8c00',
  repeatuntilsuccess: '#00897b',
  limiter: '#7b1fa2',
  delay: '#3949ab',
  timeout: '#d32f2f',
  cooldown: '#6d4c41',
  blackboardcondition: '#00695c',
  custom: '#7b1fa2'
};

// ノード定義
const nodeDefinitions = {
  sequence: { label: 'Sequence', type: 'sequence', children: true, config: {} },
  selector: { label: 'Selector', type: 'selector', children: true, config: {} },
  parallel: { label: 'Parallel', type: 'parallel', children: true, config: { success: 'all', failure: 'any' } },
  race: { label: 'Race', type: 'race', children: true, config: {} },
  randomsequence: { label: 'RandomSequence', type: 'randomsequence', children: true, config: {} },
  randomselector: { label: 'RandomSelector', type: 'randomselector', children: true, config: {} },
  priorityselector: { label: 'PrioritySelector', type: 'priorityselector', children: true, config: {} },

  inverter: { label: 'Inverter', type: 'inverter', children: false, config: {} },
  succeeder: { label: 'Succeeder', type: 'succeeder', children: false, config: {} },
  failer: { label: 'Failer', type: 'failer', children: false, config: {} },
  repeater: { label: 'Repeater', type: 'repeater', children: false, config: { count: 3 } },
  repeatuntilfail: { label: 'RepeatUntilFail', type: 'repeatuntilfail', children: false, config: {} },
  repeatuntilsuccess: { label: 'RepeatUntilSuccess', type: 'repeatuntilsuccess', children: false, config: {} },
  limiter: { label: 'Limiter', type: 'limiter', children: false, config: { max: 3 } },
  delay: { label: 'Delay', type: 'delay', children: false, config: { seconds: 1.0 } },
  timeout: { label: 'Timeout', type: 'timeout', children: false, config: { seconds: 5.0 } },
  cooldown: { label: 'Cooldown', type: 'cooldown', children: false, config: { seconds: 3.0 } },
  blackboardcondition: { label: 'BlackboardCondition', type: 'blackboardcondition', children: false, config: { key: '', op: '==', value: '' } },

  waittime: { label: 'WaitTime', type: 'action', children: false, config: { seconds: 1.0 } }
};

// CustomNode の外（ファイル上部 or コンポーネント外）に追加
const resetTypeOptions = [
  { value: 'None', label: 'None', color: '#666' },
  { value: 'THIS_RESET', label: 'THIS_RESET', color: '#d32f2f' },
  { value: 'THIS_CHILD_RESET_ALL', label: 'CHILD_RESET_ALL', color: '#f57c00' },
  { value: 'CHILD_FIRST_RESET', label: 'CHILD_FIRST_RESET', color: '#388e3c' },
];

const getResetTypeColor = (type, hover = false) => {
  const opt = resetTypeOptions.find(o => o.value === type);
  const base = opt?.color || '#666';
  return hover ? `${base}dd` : base;
};

// カスタムノード（props の config を表示）
const CustomNode = ({ data, id, selected }) => {
  const { onAddChild, onDelete, customNodeOptions = [] } = data;
  const [openAddDialog, setOpenAddDialog] = useState(false);
  const [newNodeType, setNewNodeType] = useState('sequence');
  const [newNodeLabel, setNewNodeLabel] = useState('');
  const [newCustomSelect, setNewCustomSelect] = useState('');
  const isRoot = id === 'root';
  const def = nodeDefinitions[data.type] || { label: data.type };
  const config = data.config || {};
  const color = nodeColors[data.type] || '#666';

  const handleAdd = () => {
    if (newNodeType === 'custom') {
      if (!newCustomSelect) return;
      onAddChild(id, 'custom', newCustomSelect);
    } else {
      if (!newNodeLabel.trim()) return;
      onAddChild(id, newNodeType, newNodeLabel);
    }
    setOpenAddDialog(false);
    setNewNodeLabel('');
    setNewNodeType('sequence');
    setNewCustomSelect('');
  };

  return (
    <>
      {/* メインのノード本体 */}
      <div
        style={{
          background: color,
          color: 'white',
          padding: '14px 18px',
          borderRadius: 12,
          minWidth: 200,
          textAlign: 'center',
          position: 'relative',
          boxShadow: selected ? '0 0 0 3px #1976d2' : '0 4px 12px rgba(0,0,0,0.15)',
          fontFamily: 'Roboto, sans-serif',
          userSelect: 'none',
          cursor: 'move',
          border: selected ? '3px solid #1976d2' : 'none',
        }}
      >
        {/* ラベル部分：クリック無効 */}
        <div style={{ pointerEvents: 'none' }}>
          <Handle
            type="target"
            position={Position.Top}
            style={{ background: '#fff', border: '2px solid #000', width: 14, height: 14 }}
          />
          <div>
            <strong style={{ fontSize: 15 }}>{data.label || def.label}</strong>
            {data.description && (
              <div style={{ fontSize: 11, marginTop: 6, opacity: 0.9 }}>
                {data.description}
              </div>
            )}
            {Object.keys(config).length > 0 && (
              <div style={{ fontSize: 10, marginTop: 4, opacity: 0.8 }}>
                {Object.entries(config).map(([k, v]) => `${k}: ${v}`).join(' | ')}
              </div>
            )}
          </div>
          <Handle
            type="source"
            position={Position.Bottom}
            style={{ background: '#fff', border: '2px solid #000', width: 14, height: 14 }}
          />
        </div>

        {/* リセットタイプ選択ドロップダウン：クリック有効 */}
<div
  style={{
    position: 'absolute',
    bottom: -25,           // 枠の下に30px飛び出す
    left: -35,              // 左端から10px
    zIndex: 20,
    width: 140,            // 
  }}
>
  <select
    value={data.resetType || 'None'}
    onChange={(e) => {
      e.stopPropagation();
      data.onResetTypeChange?.(id, e.target.value);
    }}
    onMouseDown={(e) => e.stopPropagation()}
    style={{
      padding: '2px 6px',
      fontSize: '0.7rem',
      fontWeight: 600,
      background: getResetTypeColor(data.resetType || 'None'),
      color: 'white',
      border: 'none',
      borderRadius: 6,
      boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
      outline: 'none',
      cursor: 'pointer',
      appearance: 'none',
      WebkitAppearance: 'none',
      MozAppearance: 'none',
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.background = getResetTypeColor(data.resetType || 'None', true);
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.background = getResetTypeColor(data.resetType || 'None');
    }}
  >
    {resetTypeOptions.map((opt) => (
      <option
        key={opt.value}
        value={opt.value}
        style={{
          background: opt.color,
          color: 'white',
        }}
      >
        {opt.label}
      </option>
    ))}
  </select>

  {/* 矢印アイコン（カスタム） */}
  <div
    style={{
      position: 'absolute',
      right: 15,
      top: '50%',
      transform: 'translateY(-50%)',
      pointerEvents: 'none',
      fontSize: '0.6rem',
      color: 'white',
    }}
  >
    ▼
  </div>
</div>

        {/* 追加・削除ボタン：クリック有効 */}
        <div
          style={{
            position: 'absolute',
            top: -40,
            right: -10,
            display: 'flex',
            gap: 6,
            zIndex: 10,
            pointerEvents: 'auto',
          }}
        >
          {def.children !== false && (
            <Button
              size="small"
              startIcon={<AddIcon />}
              onClick={(e) => {
                e.stopPropagation();
                setOpenAddDialog(true);
              }}
              sx={{
                background: 'rgba(0,0,0,0.7)',
                color: 'white',
                fontSize: '0.7rem',
                minWidth: 'auto',
                px: 1,
                py: 0.5,
                '&:hover': { background: 'rgba(0,0,0,0.9)' },
              }}
            >
              追加
            </Button>
          )}
          {!isRoot && (
            <Button
              size="small"
              startIcon={<DeleteIcon />}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(id);
              }}
              sx={{
                background: 'rgba(200,0,0,0.8)',
                color: 'white',
                fontSize: '0.7rem',
                minWidth: 'auto',
                px: 1,
                py: 0.5,
                '&:hover': { background: 'rgba(220,0,0,1)' },
              }}
            >
              削除
            </Button>
          )}
        </div>
      </div>

      {/* 子ノード追加ダイアログ */}
      {openAddDialog &&
        createPortal(
          <Dialog
            open={openAddDialog}
            onClose={() => setOpenAddDialog(false)}
            maxWidth="xs"
            fullWidth
          >
            <DialogTitle>子ノード追加</DialogTitle>
            <DialogContent>
              <FormControl fullWidth margin="dense">
                <InputLabel>タイプ</InputLabel>
                <Select
                  value={newNodeType}
                  label="タイプ"
                  onChange={(e) => setNewNodeType(e.target.value)}
                >
                  {Object.entries(nodeDefinitions).map(([key, def]) => (
                    <MenuItem key={key} value={key}>
                      {def.label}
                    </MenuItem>
                  ))}
                  <MenuItem value="custom">Custom</MenuItem>
                </Select>
              </FormControl>
              {newNodeType === 'custom' ? (
                <FormControl fullWidth margin="dense">
                  <InputLabel>カスタムノード</InputLabel>
                  <Select
                    value={newCustomSelect}
                    onChange={(e) => setNewCustomSelect(e.target.value)}
                  >
                    {customNodeOptions.map((cn) => (
                      <MenuItem key={cn.name} value={cn.name}>
                        {cn.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              ) : (
                <TextField
                  label="ラベル"
                  fullWidth
                  margin="dense"
                  value={newNodeLabel}
                  onChange={(e) => setNewNodeLabel(e.target.value)}
                />
              )}
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenAddDialog(false)}>キャンセル</Button>
              <Button
                onClick={handleAdd}
                variant="contained"
                disabled={
                  newNodeType !== 'custom'
                    ? !newNodeLabel.trim()
                    : !newCustomSelect
                }
              >
                追加
              </Button>
            </DialogActions>
          </Dialog>,
          document.body
        )}
    </>
  );
};

const nodeTypes = { custom: CustomNode };

function BehaviorDetailGrid() {
  const { name } = useParams();
  const [treeData, setTreeData] = useState({ root: 'root', nodes: {} });
  const [reactFlowNodes, setReactFlowNodes] = useState([]);
  const [reactFlowEdges, setReactFlowEdges] = useState([]);
  const [blackboard, setBlackboard] = useState([]);
  const [customNodes, setCustomNodes] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null); // 右メニュー用
  const [openFlow, setOpenFlow] = useState(false);
  const [openNodeDialog, setOpenNodeDialog] = useState(false);
  const [openBlackboardDialog, setOpenBlackboardDialog] = useState(false);
  const [newNodeLabel, setNewNodeLabel] = useState('');
  const [newNodeDesc, setNewNodeDesc] = useState('');
  const [newNodeType, setNewNodeType] = useState('action');
  const [newVarName, setNewVarName] = useState('');
  const [newVarType, setNewVarType] = useState('int');
  const [newVarDesc, setNewVarDesc] = useState('');
  const [loading, setLoading] = useState(true);
  const reactFlowWrapper = useRef(null);

  // 右メニューの一時状態
  const [tempConfig, setTempConfig] = useState({});

  const calculatePosition = useCallback((nodeId, depthMap = new Map()) => {
    const node = treeData.nodes[nodeId];
    if (!node) return { x: 0, y: 0 };
    const depth = depthMap.get(nodeId) ?? 0;
    const parent = node.parent ? treeData.nodes[node.parent] : null;
    const siblings = parent ? (parent.children || []).map(id => treeData.nodes[id]).filter(Boolean) : [];
    siblings.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    const index = siblings.findIndex(n => n.id === nodeId);
    const xOffset = siblings.length > 1 ? -(siblings.length - 1) * 150 : 0;
    return { x: index * 300 + xOffset, y: depth * 250 };
  }, [treeData]);

  const addChildNode = useCallback((parentId, type, label) => {
    const newId = `node_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    const parentNode = treeData.nodes[parentId] || { order: 0 };
    const parentOrder = parentNode.order ?? 0;

    setTreeData(prev => {
      const prevNodes = { ...(prev.nodes || {}) };
      const parent = prevNodes[parentId] || { id: parentId, children: [] };
      const childrenArr = Array.isArray(parent.children) ? parent.children.slice() : [];
      const def = type === 'custom' ? customNodes.find(c => c.name === label) : nodeDefinitions[type] || {};
      const order = parentOrder + 1;
      const newNode = {
        id: newId,
        type,
        label: type === 'custom' ? label : (label || def.label),
        parent: parentId,
        order,
        children: [],
        position: { x: 0, y: 0 },
        config: { ...def.config },
        resetType: 'None'  // ← ここでトップレベルに追加
      };
      prevNodes[newId] = newNode;
      prevNodes[parentId] = { ...parent, children: [...childrenArr, newId] };
      return { ...prev, nodes: prevNodes };
    });
  }, [treeData.nodes, customNodes]);

  const deleteNodeImmediateSafe = useCallback((id) => {
    if (id === 'root') return;
    setTreeData(prev => {
      const node = prev.nodes[id];
      if (!node || !node.parent) return prev;
      const updatedNodes = { ...prev.nodes };
      const parent = updatedNodes[node.parent];
      if (!parent) return prev;
      const updatedChildren = (parent.children || []).filter(cid => cid !== id);
      const removeRecursively = (nid) => {
        const n = updatedNodes[nid];
        if (!n) return;
        if (Array.isArray(n.children)) n.children.forEach(c => removeRecursively(c));
        delete updatedNodes[nid];
      };
      removeRecursively(id);
      const parentOrder = parent.order ?? 0;
      updatedChildren.forEach((cid, i) => {
        if (updatedNodes[cid]) updatedNodes[cid].order = parentOrder + 1;
      });
      updatedNodes[parent.id] = { ...parent, children: updatedChildren };
      return { ...prev, nodes: updatedNodes };
    });
    setReactFlowNodes(prev => prev.filter(n => n.id !== id));
    setReactFlowEdges(prev => prev.filter(e => !(e.source === id || e.target === id)));
  }, []);

  const onNodesChange = useCallback((changes) => {
    setReactFlowNodes(prev => {
      const newNodes = prev.map(node => {
        const change = changes.find(c => c.id === node.id);
        if (change?.type === 'position' && change.position) {
          return { ...node, position: change.position };
        }
        return node;
      });
      return newNodes;
    });
    changes.forEach(change => {
      if (change.type === 'position' && change.position) {
        setTreeData(prev => ({
          ...prev,
          nodes: {
            ...prev.nodes,
            [change.id]: { ...prev.nodes[change.id], position: change.position }
          }
        }));
      }
    });
  }, []);

  const onNodeDragStop = useCallback((_, node) => {
    setTreeData(prevTree => {
      const updatedNodes = { ...prevTree.nodes };
      const target = updatedNodes[node.id];
      if (!target) return prevTree;
      updatedNodes[node.id] = { ...target, position: node.position };
      if (target.parent) {
        const parent = updatedNodes[target.parent];
        if (parent && Array.isArray(parent.children)) {
          const siblingsInfo = parent.children
            .map(cid => {
              const rfNode = reactFlowNodes.find(n => n.id === cid) || updatedNodes[cid];
              const posX = rfNode.position?.x ?? updatedNodes[cid]?.position?.x ?? 0;
              return { id: cid, x: posX };
            })
            .sort((a, b) => a.x - b.x);
          const parentOrder = parent.order ?? 0;
          siblingsInfo.forEach((s, i) => {
            if (updatedNodes[s.id]) updatedNodes[s.id].order = parentOrder + 1;
          });
          updatedNodes[parent.id] = { ...parent, children: siblingsInfo.map(s => s.id) };
        }
      }
      return { ...prevTree, nodes: updatedNodes };
    });
  }, [reactFlowNodes]);

  // ノード選択時に一時 config をセット
  const handleNodeClick = useCallback((_, node) => {
    setSelectedNode(node);
    setTempConfig({ ...node.data.config });
  }, []);

  // 一時 config を更新（入力中は即時反映）
  const handleTempConfigChange = (key, value) => {
    setTempConfig(prev => ({ ...prev, [key]: value }));
  };

  // 保存ボタンで treeData に反映
  const handleSaveNodeConfig = () => {
    if (!selectedNode) return;
    const nodeId = selectedNode.id;
    setTreeData(prev => ({
      ...prev,
      nodes: {
        ...prev.nodes,
        [nodeId]: {
          ...prev.nodes[nodeId],
          config: { ...tempConfig }
        }
      }
    }));
    // ReactFlow も更新
    setReactFlowNodes(prev => prev.map(n => 
      n.id === nodeId ? { ...n, data: { ...n.data, config: { ...tempConfig } } } : n
    ));
    alert('ノード設定を保存しました');
  };

  const syncToReactFlow = useCallback(() => {
    const depthMap = new Map();
    const setDepth = (id, depth) => {
      if (!depthMap.has(id)) depthMap.set(id, depth);
      const node = treeData.nodes[id];
      if (node && Array.isArray(node.children)) node.children.forEach(child => setDepth(child, depth + 1));
    };
    if (treeData.nodes[treeData.root]) setDepth(treeData.root, 0);

    const nodes = [];
    const edges = [];

    Object.keys(treeData.nodes).forEach(id => {
      const node = treeData.nodes[id];
      if (!node) return;
      const savedPos = node.position && typeof node.position.x === 'number' ? node.position : calculatePosition(id, depthMap);
      const def = node.type === 'custom' ? customNodes.find(c => c.name === node.label) : nodeDefinitions[node.type] || {};

      nodes.push({
        id,
        type: 'custom',
        position: savedPos,
        draggable: true,
        data: {
          label: node.label,
          description: node.description,
          type: node.type,
          onAddChild: addChildNode,
          onDelete: deleteNodeImmediateSafe,
          parent: node.parent,
          customNodeOptions: customNodes,
          config: { ...node.config },
          resetType: node.resetType || 'None',  // ← 保存された値を使う
              onResetTypeChange: (nodeId, value) => {
                setTreeData(prev => ({
                  ...prev,
                  nodes: {
                    ...prev.nodes,
                    [nodeId]: {
                      ...prev.nodes[nodeId],
                      resetType: value  // ← ここで正しく更新
                    }
                  }
                }));
                setReactFlowNodes(prev => prev.map(n =>
                  n.id === nodeId
                    ? { ...n, data: { ...n.data, resetType: value } }
                    : n
                ));
    
        }
        }
      });

      if (Array.isArray(node.children)) {
        node.children.forEach(childId => {
          if (treeData.nodes[childId]) {
            edges.push({
              id: `${id}-${childId}`,
              source: id,
              target: childId,
              animated: true,
              style: { stroke: '#555', strokeWidth: 2 }
            });
          }
        });
      }
    });

    setReactFlowNodes(nodes);
    setReactFlowEdges(edges);
  }, [treeData, addChildNode, calculatePosition, customNodes, deleteNodeImmediateSafe]);

  useEffect(() => {
    syncToReactFlow();
  }, [treeData, syncToReactFlow]);

  const handleAddCustomNode = () => {
    if (!newNodeLabel.trim()) return alert('名前を入力');
    setCustomNodes(prev => [...prev, { name: newNodeLabel, type: newNodeType, description: newNodeDesc }]);
    setOpenNodeDialog(false);
    setNewNodeLabel(''); setNewNodeDesc(''); setNewNodeType('action');
  };

  const handleAddBlackboard = () => {
    if (!newVarName.trim()) return alert('名前を入力');
    setBlackboard(prev => [...prev, { name: newVarName, type: newVarType, description: newVarDesc }]);
    setOpenBlackboardDialog(false);
    setNewVarName(''); setNewVarType('int'); setNewVarDesc('');
  };

  useEffect(() => {
    fetch(`/api/behavior-data/${name}`)
      .then(r => r.json())
      .then(data => {
        const nodes = data.nodes || {};
        Object.keys(nodes).forEach(id => {
          if (!Array.isArray(nodes[id].children)) nodes[id].children = [];
          if (!nodes[id].order) nodes[id].order = 0;
          if (!nodes[id].config) nodes[id].config = {};
          if (!nodes[id].resetType) nodes[id].resetType = 'None';  
        });
        if (!nodes[data.root || 'root']) {
          nodes[data.root || 'root'] = { id: data.root || 'root', type: 'sequence', label: 'Root', order: 0, children: [], config: {} };
        }
        setTreeData({ root: data.root || 'root', nodes });
        setBlackboard(Array.isArray(data.blackboard) ? data.blackboard : []);
        setCustomNodes(Array.isArray(data.customNodes) ? data.customNodes : []);
        setLoading(false);
      })
      .catch(() => {
        setTreeData({
          root: 'root',
          nodes: { root: { id: 'root', type: 'sequence', label: 'Root', order: 0, children: [], config: {} } }
        });
        setBlackboard([]);
        setCustomNodes([]);
        setLoading(false);
      });
  }, [name]);

  const handleSave = () => {
    const data = { ...treeData, blackboard, customNodes };
    Object.keys(data.nodes).forEach(id => {
    if (!data.nodes[id].resetType) data.nodes[id].resetType = 'None';
  });
    fetch(`/api/behavior-data/${name}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
      .then(() => alert('保存しました'))
      .catch(() => alert('保存失敗'));
  };

  const handleGenerateCode = () => {
    fetch(`/api/behavior-generate/${name}`, { method: 'POST' })
      .then(r => r.json())
      .then(res => alert(res.message || '生成完了'))
      .catch(() => alert('生成失敗'));
  };

  if (loading) return <Typography>読み込み中...</Typography>;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>{name} - ビヘイビア詳細</Typography>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenNodeDialog(true)}>
            カスタムノード
          </Button>
        </Grid>
        <Grid item>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenBlackboardDialog(true)}>
            Blackboard
          </Button>
        </Grid>
        <Grid item>
          <Button variant="contained" color="success" startIcon={<SaveIcon />} onClick={handleSave}>
            保存
          </Button>
        </Grid>
        <Grid item>
          <Button variant="contained" color="secondary" startIcon={<CodeIcon />} onClick={handleGenerateCode}>
            コード生成
          </Button>
        </Grid>
        <Grid item>
          <Button variant="outlined" onClick={() => setOpenFlow(true)}>
            ツリー図
          </Button>
        </Grid>
      </Grid>

      {/* Blackboard */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Blackboard</Typography>
          <DataGrid
            rows={blackboard.map((v, i) => ({ id: i, ...v }))}
            columns={[
              { field: 'name', headerName: '変数名', flex: 1 },
              { field: 'type', headerName: '型', width: 100 },
              { field: 'description', headerName: '説明', flex: 1 },
              {
  field: 'actions',
  headerName: '',
  width: 100,
  renderCell: (params) => (
    <Button
      size="small"
      color="error"
      onClick={() => {
        setBlackboard(prev => prev.filter((_, i) => i !== params.id));
      }}
    >
      <DeleteIcon fontSize="small" />
    </Button>
  )
}
            ]}
            autoHeight
            disableSelectionOnClick
          />
        </CardContent>
      </Card>

      {/* カスタムノード */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>カスタムノード</Typography>
          <DataGrid
            rows={customNodes.map((n, i) => ({ id: i, ...n }))}
            columns={[
              { field: 'name', headerName: '名前', flex: 1 },
              { field: 'type', headerName: '継承元', width: 120 },
              { field: 'description', headerName: '説明', flex: 1 },
              {
                field: 'actions',
                headerName: '',
                width: 180,
                renderCell: (p) => (
                  <Box sx={{ display: 'flex', gap: 0.5 }}>
                    <Button
                      size="small"
                      color="error"
                      onClick={() => {
                        setCustomNodes(prev => prev.filter((_, i) => i !== p.id));
                      }}
                    >
                      <DeleteIcon fontSize="small" />
                    </Button>
                  </Box>
                )
              }
            ]}
            autoHeight
            disableSelectionOnClick
          />
        </CardContent>
      </Card>

      {/* クイック追加 */}
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
        {Object.entries(nodeDefinitions).map(([key, def]) => (
          <Button key={key} variant="outlined" size="small" onClick={() => addChildNode('root', key, def.label)}>
            + {def.label}
          </Button>
        ))}
      </Box>

      {/* カスタムノード作成ダイアログ */}
      <Dialog open={openNodeDialog} onClose={() => setOpenNodeDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>カスタムノード作成</DialogTitle>
        <DialogContent>
          <TextField label="名前" fullWidth margin="dense" value={newNodeLabel} onChange={e => setNewNodeLabel(e.target.value)} />
          <Autocomplete
            options={['action', 'condition']}
            value={newNodeType}
            onChange={(e, v) => v && setNewNodeType(v)}
            renderInput={p => <TextField {...p} label="継承元" margin="dense" />}
          />
          <TextField label="説明" fullWidth margin="dense" value={newNodeDesc} onChange={e => setNewNodeDesc(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenNodeDialog(false)}>キャンセル</Button>
          <Button onClick={handleAddCustomNode} variant="contained">作成</Button>
        </DialogActions>
      </Dialog>

      {/* Blackboard 変数追加ダイアログ */}
      <Dialog open={openBlackboardDialog} onClose={() => setOpenBlackboardDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Blackboard 変数追加</DialogTitle>
        <DialogContent>
          <TextField label="変数名" fullWidth margin="dense" value={newVarName} onChange={e => setNewVarName(e.target.value)} />
          <Autocomplete
            options={['int', 'float', 'bool', 'string', 'Vector3']}
            value={newVarType}
            onChange={(e, v) => v && setNewVarType(v)}
            renderInput={p => <TextField {...p} label="型" margin="dense" />}
          />
          <TextField label="説明" fullWidth margin="dense" value={newVarDesc} onChange={e => setNewVarDesc(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenBlackboardDialog(false)}>キャンセル</Button>
          <Button onClick={handleAddBlackboard} variant="contained">追加</Button>
        </DialogActions>
      </Dialog>

      {/* ツリー図モーダル */}
      <Dialog open={openFlow} onClose={() => { setOpenFlow(false); setSelectedNode(null); setTempConfig({}); }} maxWidth="lg" fullWidth fullScreen>
        <DialogTitle>ビヘイビアツリー図</DialogTitle>
        <DialogContent dividers sx={{ p: 0, display: 'flex', height: 'calc(100vh - 64px)' }}>
          <Box sx={{ flex: 1, position: 'relative' }}>
            <div ref={reactFlowWrapper} style={{ width: '100%', height: '100%' }}>
              <ReactFlow
                nodes={reactFlowNodes}
                edges={reactFlowEdges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onNodeDragStop={onNodeDragStop}
                onNodeClick={handleNodeClick}
                fitView
                panOnDrag={true}
                panOnScroll={true}
                nodesDraggable={true}
              >
                <Background />
                <Controls />
                <MiniMap />
              </ReactFlow>
            </div>
          </Box>

          {selectedNode && (
            <Paper sx={{ width: 320, p: 2, borderLeft: '1px solid #ddd', overflowY: 'auto' }}>
              <Typography variant="h6" gutterBottom>設定</Typography>
              <Typography variant="subtitle2" color="text.secondary">{selectedNode.data.label}</Typography>

              {/* 保存ボタン */}
              <Button variant="contained" color="primary" size="small" fullWidth sx={{ mt: 1, mb: 2 }} onClick={handleSaveNodeConfig}>
                このノードを保存
              </Button>

              {selectedNode.data.type === 'waittime' && (
                <TextField
                  label="待機時間 (秒)"
                  type="number"
                  fullWidth
                  margin="dense"
                  value={tempConfig.seconds ?? 1.0}
                  onChange={e => handleTempConfigChange('seconds', parseFloat(e.target.value))}
                />
              )}

              {selectedNode.data.type === 'blackboardcondition' && (
                <>
                  <FormControl fullWidth margin="dense">
                    <InputLabel>変数</InputLabel>
                    <Select
                      value={tempConfig.key || ''}
                      onChange={e => handleTempConfigChange('key', e.target.value)}
                    >
                      {blackboard.map(v => (
                        <MenuItem key={v.name} value={v.name}>{v.name} ({v.type})</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth margin="dense">
                    <InputLabel>比較</InputLabel>
                    <Select
                      value={tempConfig.op || '=='}
                      onChange={e => handleTempConfigChange('op', e.target.value)}
                    >
                      <MenuItem value="==">==</MenuItem>
                      <MenuItem value="!=">!=</MenuItem>
                      <MenuItem value=">">&gt;</MenuItem>
                      <MenuItem value="<">&lt;</MenuItem>
                      <MenuItem value=">=">&ge;</MenuItem>
                      <MenuItem value="<=">&le;</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField
                    label="値"
                    fullWidth
                    margin="dense"
                    value={tempConfig.value || ''}
                    onChange={e => handleTempConfigChange('value', e.target.value)}
                  />
                </>
              )}

              {['delay', 'timeout', 'cooldown'].includes(selectedNode.data.type) && (
                <TextField
                  label="時間 (秒)"
                  type="number"
                  fullWidth
                  margin="dense"
                  value={tempConfig.seconds ?? 1.0}
                  onChange={e => handleTempConfigChange('seconds', parseFloat(e.target.value))}
                />
              )}

              {['repeater', 'limiter'].includes(selectedNode.data.type) && (
                <TextField
                  label="回数"
                  type="number"
                  fullWidth
                  margin="dense"
                  value={tempConfig.count ?? tempConfig.max ?? 1}
                  onChange={e => handleTempConfigChange(selectedNode.data.type === 'repeater' ? 'count' : 'max', parseInt(e.target.value))}
                />
              )}
            </Paper>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setOpenFlow(false); setSelectedNode(null); setTempConfig({}); }}>閉じる</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default BehaviorDetailGrid;