import React, { useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import ReactFlow, { addEdge, Background, Controls, MiniMap } from 'react-flow-renderer';
import { Box, Typography } from '@mui/material';

function Flow() {
  const { name } = useParams();
  const [elements, setElements] = useState(() => {
    const savedData = sessionStorage.getItem(`flowData_${name}`);
    return savedData ? JSON.parse(savedData) : { nodes: [], edges: [] };
  });

  const onConnect = useCallback(
    (params) => setElements((els) => addEdge({ ...params, type: 'smoothstep' }, els)),
    [setElements]
  );

  const onElementsRemove = useCallback(
    (elementsToRemove) =>
      setElements((els) => ({
        nodes: els.nodes.filter((n) => !elementsToRemove.some((el) => el.id === n.id)),
        edges: els.edges.filter((e) => !elementsToRemove.some((el) => el.id === e.id)),
      })),
    [setElements]
  );

  const onLoad = useCallback((reactFlowInstance) => {
    reactFlowInstance.fitView();
  }, []);

  return (
    <Box sx={{ height: '100vh', width: '100vw', bgcolor: 'background.default' }}>
      <Typography variant="h4" sx={{ p: 2, fontWeight: 'bold', color: 'primary.main' }}>
        遷移図: {name || '不明'}
      </Typography>
      <ReactFlow
        elements={[...elements.nodes, ...elements.edges]}
        onConnect={onConnect}
        onElementsRemove={onElementsRemove}
        onLoad={onLoad}
        snapToGrid
        snapGrid={[15, 15]}
        style={{ height: 'calc(100vh - 64px)' }}
      >
        <Background variant="dots" gap={15} size={1} />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </Box>
  );
}

export default Flow;