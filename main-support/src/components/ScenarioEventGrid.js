import React, { useState, useEffect } from 'react';
import { DataGrid, useGridApiRef } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, IconButton } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import { useNavigate } from 'react-router-dom';

function ScenarioEventGrid() {
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [filterText, setFilterText] = useState('');
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [openDialog, setOpenDialog] = useState(false);
  const [loading, setLoading] = useState(true);
  const [idError, setIdError] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [newSubName, setNewSubName] = useState('');
  const [openSubDialog, setOpenSubDialog] = useState(false);
  const apiRef = useGridApiRef();

  // Fetch data
  useEffect(() => {
    fetch('/api/scenario-event')
      .then(response => {
        if (!response.ok) {
          console.warn(`HTTP error! status: ${response.status}`);
          return [];
        }
        return response.json();
      })
      .then(fetchedData => {
        console.log('Fetched scenario event data:', fetchedData);
        if (Array.isArray(fetchedData)) {
          const treeData = [];
          fetchedData.forEach(event => {
            treeData.push({
              id: event.id,
              eventId: event.id,
              name: event.name,
              description: event.description,
              path: [event.id],
              isParent: true
            });
            event.subEvents.forEach(sub => {
              treeData.push({
                id: `${event.id}-${sub.subId}`,
                eventId: event.id,
                subEventId: sub.subId,
                name: sub.name,
                path: [event.id, sub.subId.toString()],
                parentId: event.id,
                subId: sub.subId,
                isSub: true
              });
            });
          });
          console.log('Processed tree data:', treeData);
          setData(treeData);
        } else {
          setData([]);
        }
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching scenario events:', error);
        setData([]);
        setLoading(false);
      });
  }, []);

  // Filter data based on search input
  const filteredData = data.filter(row => {
    if (!filterText.trim()) return true;
    const searchLower = filterText.toLowerCase();
    if (row.isParent) {
      return (
        row.eventId.toLowerCase().includes(searchLower) ||
        row.name.toLowerCase().includes(searchLower)
      );
    } else if (row.isSub) {
      // Include sub-event if its parent matches or it matches directly
      const parent = data.find(parent => parent.id === row.parentId);
      return (
        row.subEventId.toString().toLowerCase().includes(searchLower) ||
        row.name.toLowerCase().includes(searchLower) ||
        (parent && (
          parent.eventId.toLowerCase().includes(searchLower) ||
          parent.name.toLowerCase().includes(searchLower)
        ))
      );
    }
    return false;
  });

  // Validate ID
  const validateId = (value) => {
    const regex = /^[a-zA-Z0-9-]{1,25}$/;
    return regex.test(value);
  };

  // Handle ID change
  const handleIdChange = (e) => {
    const value = e.target.value;
    setNewId(value);
    setIdError(!validateId(value));
  };

  // Add new event
  const handleAddEvent = () => {
    setOpenDialog(true);
  };

  const handleCreateEvent = () => {
    if (!newId.trim() || idError) {
      alert('有効なIDを入力してください (英数字とハイフンのみ、1-25文字)');
      return;
    }
    if (!newName.trim()) {
      alert('イベント名を入力してください');
      return;
    }
    fetch('/api/scenario-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: newId, name: newName, description: newDescription }),
    })
      .then(response => {
        if (!response.ok) {
          return response.text().then(text => {
            throw new Error(`HTTP error! status: ${response.status}, body: ${text}`);
          });
        }
        return response.json();
      })
      .then(result => {
        alert(result.message);
        const newEvent = {
          id: newId,
          eventId: newId,
          name: newName,
          description: newDescription,
          path: [newId],
          isParent: true
        };
        setData([...data, newEvent]);
        setNewId('');
        setNewName('');
        setNewDescription('');
        setIdError(false);
        setOpenDialog(false);
      })
      .catch(error => {
        console.error('Error adding event:', error);
        alert('イベント追加エラー: ' + error.message);
      });
  };

  // Delete event
  const handleDeleteEvent = (id) => {
    if (window.confirm(`イベント ${id} を削除しますか？`)) {
      fetch(`/api/scenario-event/${id}`, {
        method: 'DELETE',
      })
        .then(response => {
          if (!response.ok) {
            return response.text().then(text => {
              throw new Error(`HTTP error! status: ${response.status}, body: ${text}`);
            });
          }
          return response.json();
        })
        .then(result => {
          alert(result.message);
          setData(data.filter(item => item.id !== id && !item.id.startsWith(`${id}-`)));
        })
        .catch(error => {
          console.error('Error deleting event:', error);
          alert('イベント削除エラー: ' + error.message);
        });
    }
  };

  // Add sub event
  const handleAddSubEvent = (eventId) => {
    setSelectedEventId(eventId);
    setOpenSubDialog(true);
  };

  const handleCreateSubEvent = () => {
    if (!newSubName.trim()) {
      alert('サブイベント名を入力してください');
      return;
    }
    fetch(`/api/scenario-event/${selectedEventId}/sub`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newSubName }),
    })
      .then(response => {
        if (!response.ok) {
          return response.text().then(text => {
            throw new Error(`HTTP error! status: ${response.status}, body: ${text}`);
          });
        }
        return response.json();
      })
      .then(result => {
        alert(result.message);
        const newSub = {
          id: `${selectedEventId}-${result.subId}`,
          eventId: selectedEventId,
          subEventId: result.subId,
          name: newSubName,
          path: [selectedEventId, result.subId.toString()],
          parentId: selectedEventId,
          subId: result.subId,
          isSub: true
        };
        setData([...data, newSub]);
        setNewSubName('');
        setOpenSubDialog(false);
      })
      .catch(error => {
        console.error('Error adding sub event:', error);
        alert('サブイベント追加エラー: ' + error.message);
      });
  };

  // Delete sub event
  const handleDeleteSubEvent = (eventId, subId) => {
    if (window.confirm(`サブイベント ${subId} を削除しますか？`)) {
      fetch(`/api/scenario-event/${eventId}/sub/${subId}`, {
        method: 'DELETE',
      })
        .then(response => {
          if (!response.ok) {
            return response.text().then(text => {
              throw new Error(`HTTP error! status: ${response.status}, body: ${text}`);
            });
          }
          return response.json();
        })
        .then(result => {
          alert(result.message);
          setData(data.filter(item => item.id !== `${eventId}-${subId}`));
        })
        .catch(error => {
          console.error('Error deleting sub event:', error);
          alert('サブイベント削除エラー: ' + error.message);
        });
    }
  };

  // Handle cell edit
  const handleCellEditStop = (params, event) => {
    const { id, field, value } = params;
    const row = data.find(row => row.id === id);
    if (!row || value === row[field]) return;

    const updatedData = data.map(row =>
      row.id === id ? { ...row, [field]: value } : row
    );
    setData(updatedData);

    if (row.isParent) {
      fetch(`/api/scenario-event/${row.eventId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
      })
        .then(response => {
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          return response.json();
        })
        .then(result => {
          alert(result.message);
        })
        .catch(error => {
          console.error('Error updating event:', error);
          alert('イベント更新エラー: ' + error.message);
          setData(data); // Revert on error
        });
    } else if (row.isSub) {
      fetch(`/api/scenario-event/${row.eventId}/sub/${row.subId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
      })
        .then(response => {
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          return response.json();
        })
        .then(result => {
          alert(result.message);
        })
        .catch(error => {
          console.error('Error updating sub event:', error);
          alert('サブイベント更新エラー: ' + error.message);
          setData(data); // Revert on error
        });
    }
  };

  const columns = [
    { field: 'eventId', headerName: 'イベントID', width: 200 },
    { field: 'subEventId', headerName: 'サブイベントID', width: 150 },
{
  field: 'name',
  headerName: '名前',
  width: 300,
  editable: true,
  renderCell: (params) => {
    // path が [parentId] または [parentId, subId, ...] になっている想定
    const path = Array.isArray(params.row.path) ? params.row.path : [];
    const depth = Math.max(0, path.length - 1);

    // 簡易ツリー線（縦線＋枝）
    const lines = [];
    for (let i = 1; i <= depth; i++) {
      lines.push(
        <div
          key={`v-${i}`}
          style={{
            position: 'absolute',
            left: `${(i - 1) * 20 + 8}px`,
            top: 0,
            bottom: 0,
            width: '1px',
            backgroundColor: '#d0d0d0',
            pointerEvents: 'none',
          }}
        />
      );
    }

    return (
      <div style={{ position: 'relative', paddingLeft: `${depth * 20 + 12}px`, width: '100%', display: 'flex', alignItems: 'center' }}>
        {/* 縦線（すべての先祖レベルで表示） */}
        {lines}
        {/* 横線（現在の深さの枝） */}
        {depth > 0 && (
          <div style={{
            position: 'absolute',
            left: `${depth * 20 - 8}px`,
            top: '50%',
            width: '12px',
            height: '1px',
            backgroundColor: '#d0d0d0',
            transform: 'translateY(-50%)',
            pointerEvents: 'none',
          }} />
        )}

        <Button
          variant="text"
          onClick={() => {
            if (params.row.isParent) {
              navigate(`/scenario-event/${params.row.eventId}`);
            } else {
              navigate(`/scenario-event/${params.row.parentId}/sub/${params.row.subId}`);
            }
          }}
          sx={{ minWidth: 'auto', textTransform: 'none' }}
        >
          {params.value}
        </Button>
      </div>
    );
  }
},

    { field: 'description', headerName: '説明', width: 300, editable: true },
    {
      field: 'actions',
      headerName: 'アクション',
      width: 250,
      renderCell: (params) => {
        if (params.row.isParent) {
          return (
            <>
              <Button
                variant="contained"
                color="primary"
                size="small"
                startIcon={<AddIcon />}
                onClick={() => handleAddSubEvent(params.row.eventId)}
                sx={{ mr: 1 }}
              >
                サブ追加
              </Button>
              <Button
                variant="contained"
                color="error"
                size="small"
                onClick={() => handleDeleteEvent(params.row.eventId)}
              >
                削除
              </Button>
            </>
          );
        } else if (params.row.isSub) {
          return (
            <>
              <Button
                variant="contained"
                color="secondary"
                size="small"
                sx={{ mr: 1 }}
                onClick={() => navigate(`/scenario-event/${params.row.parentId}/sub/${params.row.subId}/transition`)}
              >
                遷移図
              </Button>
              <Button
                variant="contained"
                color="secondary"
                size="small"
                sx={{ mr: 1 }}
                onClick={() => navigate(`/scenario-event/${params.row.parentId}/sub/${params.row.subId}/story`)}
              >
                物語設定
              </Button>
              <IconButton color="error" onClick={() => handleDeleteSubEvent(params.row.parentId, params.row.subId)}>
                <DeleteIcon />
              </IconButton>
            </>
          );
        }
        return null;
      },
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        シナリオイベント
      </Typography>
      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
        <TextField
          label="検索 (IDまたは名前)"
          variant="outlined"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          sx={{ width: 300, mr: 2 }}
        />
        <Button variant="contained" onClick={handleAddEvent}>
          追加
        </Button>
      </Box>
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいイベントの作成</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="ID (英数字とハイフンのみ、1-25文字)"
            fullWidth
            variant="standard"
            value={newId}
            onChange={handleIdChange}
            error={idError}
            helperText={idError ? '無効なIDです' : ''}
          />
          <TextField
            margin="dense"
            label="イベント名"
            fullWidth
            variant="standard"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="説明"
            fullWidth
            variant="standard"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>キャンセル</Button>
          <Button onClick={handleCreateEvent} disabled={idError || !newId.trim()}>作成</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={openSubDialog} onClose={() => setOpenSubDialog(false)}>
        <DialogTitle>新しいサブイベントの作成</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="サブイベント名"
            fullWidth
            variant="standard"
            value={newSubName}
            onChange={(e) => setNewSubName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenSubDialog(false)}>キャンセル</Button>
          <Button onClick={handleCreateSubEvent}>作成</Button>
        </DialogActions>
      </Dialog>
      {loading ? (
        <Typography>読み込み中...</Typography>
      ) : (
        <div style={{ height: 600, width: '100%' }}>
          <DataGrid
            rows={filteredData}
            columns={columns}
            treeData
            getTreeDataPath={(row) => row.path}
            groupingColDef={{
              headerName: '階層',
              hideDescendantCount: true,
              width: 150,
              renderCell: (params) => (
                <div style={{ paddingLeft: `${params.rowNode.depth * 20}px` }}>
                  {params.rowNode.depth > 0 ? '└─ ' : ''}{params.row.eventId || params.row.subEventId}
                </div>
              )
            }}
            pageSizeOptions={[5]}
            getRowId={(row) => row.id}
            onCellEditStop={handleCellEditStop}
            sx={{
              '& .MuiDataGrid-row': {
                '& .MuiDataGrid-cell': {
                  borderLeft: '1px solid rgba(0,0,0,0.1)',
                },
              },
            }}
          />
        </div>
      )}
    </Box>
  );
}

export default ScenarioEventGrid;