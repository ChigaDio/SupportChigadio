import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Grid, Card, CardContent, IconButton, Autocomplete, Checkbox, FormControlLabel, Tooltip, Chip, Divider } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import CloseIcon from '@mui/icons-material/Close';
import SaveIcon from '@mui/icons-material/Save';
import CodeIcon from '@mui/icons-material/Code';
import TuneIcon from '@mui/icons-material/Tune';
import BoltIcon from '@mui/icons-material/Bolt';
import SyncIcon from '@mui/icons-material/Sync';
import { styled } from '@mui/material/styles';
import { ReactFlow, Background, Controls, MiniMap, useReactFlow, addEdge, Handle, Position, applyNodeChanges } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

// Enter/Update/Exit それぞれの 同期/非同期 使用設定のデフォルト（同期のみ）。
// StateControlのCombined API（同期・非同期を両方動かすモード）が、
// このノードに対応するStateクラスで実際にどちらを呼ぶかを決めるのに使われる。
const DEFAULT_LIFECYCLE = {
  enter: { sync: true, async: false },
  update: { sync: true, async: false },
  exit: { sync: true, async: false },
};

const LIFECYCLE_STAGES = [
  { key: 'enter', label: 'Enter' },
  { key: 'update', label: 'Update' },
  { key: 'exit', label: 'Exit' },
];

const normalizeLifecycle = (lifecycle) => {
  const result = {};
  LIFECYCLE_STAGES.forEach(({ key }) => {
    const stage = (lifecycle && lifecycle[key]) || {};
    let sync = stage.sync !== undefined ? !!stage.sync : DEFAULT_LIFECYCLE[key].sync;
    let async_ = stage.async !== undefined ? !!stage.async : DEFAULT_LIFECYCLE[key].async;
    if (!sync && !async_) sync = true; // 最低1つは必須
    result[key] = { sync, async: async_ };
  });
  return result;
};

const CustomNode = ({ data, id }) => {
  const handleDelete = (e) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('deleteNode', { detail: id }));
  };

  const handleShowCode = (e) => {
    e.stopPropagation();
    fetch(`/api/open-code/${data.stateName}/${data.label}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    })
      .then(response => response.json())
      .then(result => {
        if (result.error) {
          alert(`エラー: ${result.error}`);
        } else {
          alert(result.message);
        }
      })
      .catch(error => {
        console.error('コードを開く際のエラー:', error);
        alert('コードを開く際にエラーが発生しました');
      });
  };

  const handleAddSubNode = (e) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('addSubNode', { detail: id }));
  };

  const handleDeleteSubNode = (e, subId) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('deleteSubNode', { detail: { parentId: id, subId } }));
  };

  const handleOpenLifecycle = (e) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('openLifecycle', { detail: id }));
  };

  const lifecycle = normalizeLifecycle(data.lifecycle);

  return (
    <div
      className="rounded-xl text-white"
      style={{
        width: 288,
        minHeight: 96,
        position: 'relative',
        background: 'linear-gradient(160deg, #1f2937 0%, #111827 100%)',
        borderRadius: 14,
        boxShadow: '0 6px 18px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.06)',
        overflow: 'hidden',
        cursor: 'pointer',
      }}
      onClick={handleOpenLifecycle}
    >
      <div style={{ position: 'absolute', top: 6, right: 6, display: 'flex', gap: 2, zIndex: 2 }}>
        <Tooltip title="ライフサイクル設定 (同期/非同期)">
          <IconButton size="small" onClick={handleOpenLifecycle} style={{ color: '#93c5fd' }}>
            <TuneIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="コードを開く">
          <IconButton size="small" onClick={handleShowCode} style={{ color: '#e5e7eb' }}>
            <CodeIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="サブノードを追加">
          <IconButton size="small" onClick={handleAddSubNode} style={{ color: '#86efac' }}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="削除">
          <IconButton size="small" onClick={handleDelete} style={{ color: '#fca5a5' }}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </div>

      <div
        style={{
          background: 'linear-gradient(90deg, #1d4ed8 0%, #2563eb 60%, #3b82f6 100%)',
          padding: '10px 12px',
          paddingRight: 132,
        }}
      >
        <Typography variant="subtitle1" style={{ fontWeight: 700, color: 'white', lineHeight: 1.2 }}>
          {data.label}
        </Typography>
      </div>

      <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)' }}>
        <Typography variant="caption" style={{ color: '#9ca3af' }}>
          ID: {id}{data.description ? ` ・ ${data.description}` : ''}
        </Typography>
      </div>

      <div style={{ display: 'flex', gap: 6, padding: '4px 12px 10px 12px', flexWrap: 'wrap' }}>
        {LIFECYCLE_STAGES.map(({ key, label }) => {
          const cfg = lifecycle[key];
          return (
            <div
              key={key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                background: 'rgba(255,255,255,0.06)',
                borderRadius: 8,
                padding: '2px 6px',
              }}
            >
              <Typography variant="caption" style={{ color: '#d1d5db', fontSize: 10 }}>{label}</Typography>
              {cfg.sync && <SyncIcon style={{ fontSize: 12, color: '#60a5fa' }} titleAccess="同期" />}
              {cfg.async && <BoltIcon style={{ fontSize: 12, color: '#facc15' }} titleAccess="非同期" />}
            </div>
          );
        })}
      </div>

      {data.subNodes && data.subNodes.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '0 8px 8px 8px' }}>
          <Typography variant="caption" style={{ color: '#9ca3af', fontSize: 10, marginBottom: 2 }}>
            スタック実行（LIFO）— クリックで各Stateの同期/非同期設定
          </Typography>
          {data.subNodes.map((sub) => (
            <div
              key={sub.id}
              onClick={(e) => {
                e.stopPropagation();
                window.dispatchEvent(new CustomEvent('openLifecycleTransition', { detail: sub.label }));
              }}
              style={{
                background: 'linear-gradient(90deg, #065f46 0%, #059669 100%)',
                padding: '4px 8px',
                borderRadius: 8,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
              }}
            >
              <Typography variant="caption" style={{ fontWeight: 600 }}>{sub.label}</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <TuneIcon style={{ fontSize: 13, color: '#d1fae5' }} />
                <IconButton size="small" onClick={(e) => handleDeleteSubNode(e, sub.id)} style={{ color: '#fecaca', padding: 2 }}>
                  <CloseIcon style={{ fontSize: 14 }} />
                </IconButton>
              </Box>
            </div>
          ))}
        </div>
      )}

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
  const [newDescription, setNewDescription] = useState('');
  const [newType, setNewType] = useState('');
  const [newName, setNewName] = useState('');
  const [newArraySize, setNewArraySize] = useState(0);
  const [typeOptions, setTypeOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [flowElements, setFlowElements] = useState({ nodes: [], edges: [] });
  const [dialogType, setDialogType] = useState('');
  const [filterText, setFilterText] = useState('');
  const [filteredTransitions, setFilteredTransitions] = useState([]);
  const { fitView, screenToFlowPosition } = useReactFlow();
  const reactFlowWrapper = useRef(null);
  const [openSubNodeDialog, setOpenSubNodeDialog] = useState(false);
  const [openLifecycleDialog, setOpenLifecycleDialog] = useState(false);
  const [lifecycleTarget, setLifecycleTarget] = useState(null); // { kind: 'node', id } | { kind: 'transition', label }
  const [lifecycleDraft, setLifecycleDraft] = useState(DEFAULT_LIFECYCLE);
  const [lifecycleOriginal, setLifecycleOriginal] = useState(DEFAULT_LIFECYCLE);
  const [selectedParentId, setSelectedParentId] = useState(null);
  const [newSubLabel, setNewSubLabel] = useState('');

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

    const handleAddSubNode = (e) => {
      const parentId = e.detail;
      setSelectedParentId(parentId);
      setOpenSubNodeDialog(true);
    };

    const handleDeleteSubNode = (e) => {
      const { parentId, subId } = e.detail;
      setFlowElements((els) => ({
        ...els,
        nodes: els.nodes.map((node) => {
          if (node.id === parentId) {
            return {
              ...node,
              data: {
                ...node.data,
                subNodes: node.data.subNodes.filter((sub) => sub.id !== subId),
              },
            };
          }
          return node;
        }),
      }));
    };

    const handleOpenLifecycle = (e) => {
      const nodeId = e.detail;
      setLifecycleTarget({ kind: 'node', id: nodeId });
      setFlowElements((els) => {
        const node = els.nodes.find((n) => n.id === nodeId);
        const normalized = normalizeLifecycle(node?.data?.lifecycle);
        setLifecycleDraft(normalized);
        setLifecycleOriginal(normalized);
        return els;
      });
      setOpenLifecycleDialog(true);
    };

    const handleOpenLifecycleTransition = (e) => {
      const label = e.detail;
      setLifecycleTarget({ kind: 'transition', label });
      setTransitions((prev) => {
        const t = prev.find((item) => item.fromState === label);
        const normalized = normalizeLifecycle(t?.lifecycle);
        setLifecycleDraft(normalized);
        setLifecycleOriginal(normalized);
        return prev;
      });
      setOpenLifecycleDialog(true);
    };

    window.addEventListener('deleteNode', handleDeleteNode);
    window.addEventListener('addSubNode', handleAddSubNode);
    window.addEventListener('deleteSubNode', handleDeleteSubNode);
    window.addEventListener('openLifecycle', handleOpenLifecycle);
    window.addEventListener('openLifecycleTransition', handleOpenLifecycleTransition);
    return () => {
      window.removeEventListener('deleteNode', handleDeleteNode);
      window.removeEventListener('addSubNode', handleAddSubNode);
      window.removeEventListener('deleteSubNode', handleDeleteSubNode);
      window.removeEventListener('openLifecycle', handleOpenLifecycle);
      window.removeEventListener('openLifecycleTransition', handleOpenLifecycleTransition);
    };
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
              description: item.description || '',
              variables: Array.isArray(item.variables) ? item.variables : [],
              lifecycle: normalizeLifecycle(item.lifecycle),
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
              animated: true,
              style: { stroke: '#00FF00', strokeWidth: 3 },
            }))
          : [];
        const validNodes = Array.isArray(validData.nodes)
          ? validData.nodes.map(node => ({
              ...node,
              data: { 
                ...node.data, 
                targets: node.data.targets || [], 
                subNodes: node.data.subNodes || [],
                description: validTransitions.find(t => t.fromState === node.data.label)?.description || '',
                stateName: name,
                lifecycle: normalizeLifecycle(node.data.lifecycle)
              }
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
      description: newDescription,
      variables: [],
      lifecycle: DEFAULT_LIFECYCLE,
    };
    setTransitions([...transitions, newTransition]);
    setOpenTransitionDialog(false);
    setNewFromState('');
    setNewDescription('');
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

  const handleAddSubNodeConfirm = () => {
    if (!newSubLabel.trim()) {
      alert('ラベルは必須です');
      return;
    }
    setFlowElements((els) => {
      const updatedNodes = els.nodes.map((node) => {
        if (node.id === selectedParentId) {
          const subNodes = node.data.subNodes || [];
          const newSubId = Math.max(...subNodes.map(s => s.id || 0), 0) + 1;
          return {
            ...node,
            data: {
              ...node.data,
              subNodes: [...subNodes, { id: newSubId, label: newSubLabel }],
            },
          };
        }
        return node;
      });
      return { ...els, nodes: updatedNodes };
    });
    setOpenSubNodeDialog(false);
    setNewSubLabel('');
    setSelectedParentId(null);
  };

  // Enter/Update/Exit × 同期/非同期 のチェックボックスをトグルする。
  // 各行（ステージ）で最低1つはチェックされていなければならないため、
  // 最後の1つを外そうとした場合は無視する。
  const handleToggleLifecycle = (stage, kind) => {
    setLifecycleDraft((prev) => {
      const current = prev[stage];
      const nextValue = !current[kind];
      const otherKind = kind === 'sync' ? 'async' : 'sync';
      if (!nextValue && !current[otherKind]) {
        // 両方外れてしまうので無視（最低1つは必須）
        return prev;
      }
      return {
        ...prev,
        [stage]: { ...current, [kind]: nextValue },
      };
    });
  };

  const isLifecycleDirty = () => JSON.stringify(lifecycleDraft) !== JSON.stringify(lifecycleOriginal);

  const handleCloseLifecycleDialog = () => {
    if (isLifecycleDirty()) {
      if (!window.confirm('変更が保存されていません。破棄して閉じますか？')) {
        return;
      }
    }
    setOpenLifecycleDialog(false);
    setLifecycleTarget(null);
  };

  const handleSaveLifecycle = () => {
    if (!lifecycleTarget) return;
    if (lifecycleTarget.kind === 'node') {
      setFlowElements((els) => ({
        ...els,
        nodes: els.nodes.map((node) =>
          node.id === lifecycleTarget.id
            ? { ...node, data: { ...node.data, lifecycle: lifecycleDraft } }
            : node
        ),
      }));
    } else if (lifecycleTarget.kind === 'transition') {
      setTransitions((prev) =>
        prev.map((t) =>
          t.fromState === lifecycleTarget.label ? { ...t, lifecycle: lifecycleDraft } : t
        )
      );
    }
    setOpenLifecycleDialog(false);
    setLifecycleTarget(null);
  };

  const lifecycleNodeLabel = (() => {
    if (!lifecycleTarget) return '';
    if (lifecycleTarget.kind === 'node') {
      const node = flowElements.nodes.find((n) => n.id === lifecycleTarget.id);
      return node ? `${node.data.label} (ID: ${node.id})` : '';
    }
    return `${lifecycleTarget.label} (スタック/サブノード共通)`;
  })();

  const onConnect = useCallback((connection) => {
    setFlowElements((els) => {
      const newEdge = { ...connection, id: `e${els.edges.length + 1}`, type: 'custom', animated: true, style: { stroke: '#00FF00', strokeWidth: 3 } };
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

  const onEdgeContextMenu = useCallback((event, edge) => {
    event.preventDefault();
    onEdgesDelete([edge]);
  }, [onEdgesDelete]);

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
      data: { label, targets: [], subNodes: [], description: transitions.find(t => t.fromState === label)?.description || '', stateName: name, lifecycle: DEFAULT_LIFECYCLE },
      draggable: true,
    };

    setFlowElements((els) => ({
      ...els,
      nodes: [...els.nodes, newNode],
    }));
  }, [screenToFlowPosition, flowElements.nodes, transitions, name]);

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
    { field: 'description', headerName: '説明', width: 250, editable: true },
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
            <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium', display: 'flex', alignItems: 'center', gap: 1 }}>
              遷移図: {name || '不明'}
              <Chip
                size="small"
                icon={<SyncIcon style={{ color: '#60a5fa' }} />}
                label="同期"
                sx={{ ml: 2, bgcolor: 'rgba(255,255,255,0.15)', color: 'white' }}
              />
              <Chip
                size="small"
                icon={<BoltIcon style={{ color: '#facc15' }} />}
                label="非同期"
                sx={{ bgcolor: 'rgba(255,255,255,0.15)', color: 'white' }}
              />
              <Typography variant="caption" sx={{ ml: 1, opacity: 0.85 }}>
                （ノード右上の <TuneIcon sx={{ fontSize: 14, verticalAlign: 'middle' }} /> またはノード自体をクリックしてEnter/Update/Exitの同期・非同期を設定）
              </Typography>
            </DialogTitle>
            <DialogContent sx={{ p: 0, height: '80vh', display: 'flex' }}>
              <div
                ref={reactFlowWrapper}
                style={{ flex: 1, height: '100%', background: '#0b1220' }}
                onDrop={onDrop}
                onDragOver={onDragOver}
              >
                <ReactFlow
                  nodes={flowElements.nodes}
                  edges={flowElements.edges}
                  onConnect={onConnect}
                  onNodesDelete={onNodesDelete}
                  onEdgesDelete={onEdgesDelete}
                  onEdgeContextMenu={onEdgeContextMenu}
                  onInit={onInit}
                  onNodeDragStart={onNodeDragStart}
                  snapToGrid
                  snapGrid={[15, 15]}
                  nodeTypes={nodeTypes}
                  onNodesChange={onNodesChange}
                  defaultEdgeOptions={{ type: 'custom', animated: true, style: { stroke: '#38bdf8', strokeWidth: 2.5 } }}
                  proOptions={{ hideAttribution: true }}
                >
                  <Background variant="dots" gap={16} size={1} color="#1f2a3d" />
                  <Controls
                    style={{ borderRadius: 10, overflow: 'hidden', boxShadow: '0 2px 10px rgba(0,0,0,0.4)' }}
                  />
                  <MiniMap
                    nodeStrokeColor="#3b82f6"
                    nodeColor="#1d4ed8"
                    maskColor="rgba(11,18,32,0.75)"
                    style={{ background: '#0f172a', borderRadius: 10, border: '1px solid #1f2a3d' }}
                  />
                </ReactFlow>
              </div>
              <Box sx={{ width: 300, bgcolor: 'background.paper', p: 2, borderLeft: 1, borderColor: 'divider', overflowY: 'auto' }}>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 700 }}>
                  遷移リスト
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  カードをキャンバスへドラッグしてノードを追加
                </Typography>
                <TextField
                  label="遷移を検索"
                  fullWidth
                  value={filterText}
                  onChange={(e) => setFilterText(e.target.value)}
                  margin="dense"
                  variant="outlined"
                  placeholder="状態名でフィルタリング"
                  size="small"
                  sx={{ mt: 1, mb: 1 }}
                />
                {filteredTransitions.length > 0 ? (
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {filteredTransitions.map((transition) => (
                      <Box
                        key={transition.id}
                        draggable
                        onDragStart={(e) => onDragStart(e, transition.id, transition.fromState)}
                        sx={{
                          p: 1,
                          borderRadius: 2,
                          cursor: 'grab',
                          bgcolor: 'action.hover',
                          border: '1px solid',
                          borderColor: 'divider',
                          transition: 'all 0.15s',
                          '&:hover': { bgcolor: 'primary.light', borderColor: 'primary.main' },
                        }}
                      >
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{transition.fromState}</Typography>
                        {transition.description && (
                          <Typography variant="caption" color="text.secondary">{transition.description}</Typography>
                        )}
                      </Box>
                    ))}
                  </Box>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    該当する遷移がありません
                  </Typography>
                )}
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
              <TextField
                label="説明"
                fullWidth
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                margin="dense"
                variant="outlined"
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

          <Dialog open={openSubNodeDialog} onClose={() => setOpenSubNodeDialog(false)} maxWidth="sm" fullWidth>
            <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>新しいサブノードを追加</DialogTitle>
            <DialogContent sx={{ pt: 2 }}>
              <Autocomplete
                freeSolo
                options={transitions.map(t => t.fromState)}
                value={newSubLabel}
                onChange={(e, newValue) => setNewSubLabel(newValue || '')}
                renderInput={(params) => <TextField {...params} label="ラベル (遷移から選択)" fullWidth margin="dense" variant="outlined" required />}
              />
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setOpenSubNodeDialog(false)} color="secondary" sx={{ textTransform: 'none' }}>
                キャンセル
              </Button>
              <Button onClick={handleAddSubNodeConfirm} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
                追加
              </Button>
            </DialogActions>
          </Dialog>

          <Dialog open={openLifecycleDialog} onClose={handleCloseLifecycleDialog} maxWidth="sm" fullWidth>
            <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 'medium' }}>
              ライフサイクル設定{lifecycleNodeLabel ? `: ${lifecycleNodeLabel}` : ''}
            </DialogTitle>
            <DialogContent sx={{ pt: 2 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Combinedモード（同期・非同期を同時に動かすAPI）で、このStateのEnter/Update/Exitそれぞれについて
                同期・非同期のどちらを呼び出すかを設定します。各行、最低ひとつはチェックが必要です。
              </Typography>
              {LIFECYCLE_STAGES.map(({ key, label }) => (
                <Box
                  key={key}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    py: 1,
                    px: 1.5,
                    mb: 1,
                    borderRadius: 2,
                    bgcolor: 'action.hover',
                  }}
                >
                  <Typography variant="subtitle2" sx={{ minWidth: 90 }}>{label}</Typography>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <FormControlLabel
                      control={
                        <Checkbox
                          icon={<SyncIcon fontSize="small" />}
                          checkedIcon={<SyncIcon fontSize="small" color="primary" />}
                          checked={lifecycleDraft[key].sync}
                          onChange={() => handleToggleLifecycle(key, 'sync')}
                        />
                      }
                      label="同期"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          icon={<BoltIcon fontSize="small" />}
                          checkedIcon={<BoltIcon fontSize="small" sx={{ color: '#f59e0b' }} />}
                          checked={lifecycleDraft[key].async}
                          onChange={() => handleToggleLifecycle(key, 'async')}
                        />
                      }
                      label="非同期"
                    />
                  </Box>
                </Box>
              ))}
              <Divider sx={{ my: 1 }} />
              <Typography variant="caption" color="text.secondary">
                例: Updateで「非同期」のみチェックすると、Combinedモードでは UpdateAsync だけが呼ばれ、
                同期側は自動的に完了扱いになります（IsActive/IsActiveAsyncの管理は生成コードが自動で行います）。
              </Typography>
            </DialogContent>
            <DialogActions>
              <Button onClick={handleCloseLifecycleDialog} color="secondary" sx={{ textTransform: 'none' }}>
                キャンセル
              </Button>
              <Button onClick={handleSaveLifecycle} color="primary" variant="contained" sx={{ textTransform: 'none' }}>
                適用
              </Button>
            </DialogActions>
          </Dialog>
        </>
      )}
    </Box>
  );
}

export default StateDetailGrid;