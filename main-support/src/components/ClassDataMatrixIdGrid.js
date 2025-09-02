import React, { useState, useEffect } from 'react';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Autocomplete } from '@mui/material';
import { useNavigate } from 'react-router-dom';

function ClassDataMatrixIdGrid() {
  const [matrixData, setMatrixData] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [newName, setNewName] = useState('');
  const [newRowId, setNewRowId] = useState('');
  const [newColId, setNewColId] = useState('');
  const [typeOptions, setTypeOptions] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetch('/api/class-data-matrix-id')
      .then(response => response.json())
      .then(data => setMatrixData(data))
      .catch(error => console.error('データ取得エラー:', error));

    Promise.all([
      fetch('/api/enum-id').then(res => res.json()),
      fetch('/api/class-data-id').then(res => res.json())
    ])
      .then(([enumList, classIdList]) => {
        setTypeOptions([...enumList.map(item => item.name), ...classIdList.map(item => item.name)]);
      })
      .catch(error => console.error('オプション取得エラー:', error));
  }, []);

  const handleCreate = async () => {
    if (!newName || !newRowId || !newColId) {
      alert('名前、Row ID、Col IDは必須です');
      return;
    }
    try {
      // enum値を取得
      const [rowEnumRes, colEnumRes] = await Promise.all([
        fetch(`/api/enum/${encodeURIComponent(newRowId)}`).then(res => res.json()),
        fetch(`/api/enum/${encodeURIComponent(newColId)}`).then(res => res.json())
      ]);
      const rowKeys = rowEnumRes || [];
      const colKeys = colEnumRes || [];

      // 初期データを作成
      const initialData = {};
      rowKeys.forEach(rk => {
        initialData[rk] = {};
        colKeys.forEach(ck => {
          initialData[rk][ck] = 0; // デフォルト値（int）
        });
      });

      const newMatrix = {
        name: newName,
        rowId: newRowId, // rowIdを追加
        colId: newColId, // colIdを追加
        fields: [{ type: 'int', name: 'value', description: 'Default Value' }],
        data: initialData
      };

      const response = await fetch('/api/class-data-matrix-id', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newMatrix)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '作成に失敗しました');
      setMatrixData([...matrixData, { ...result.data, rowId: newRowId, colId: newColId }]); // レスポンスにrowId, colIdを追加
      setOpenDialog(false);
      setNewName('');
      setNewRowId('');
      setNewColId('');
      alert('ClassDataMatrixIDが正常に作成されました');
    } catch (error) {
      alert('作成エラー: ' + error.message);
    }
  };

  const handleDelete = (name) => {
    if (window.confirm(`${name} を削除しますか？`)) {
      fetch('/api/class-data-matrix-id', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      })
        .then(response => response.json())
        .then(result => {
          setMatrixData(matrixData.filter(item => item.name !== name));
          alert('削除が正常に完了しました');
        })
        .catch(error => {
          alert('削除エラー: ' + error.message);
        });
    }
  };

  const columns = [
    {
      field: 'name',
      headerName: '名前',
      width: 150,
      renderCell: (params) => (
        <div style={{ cursor: 'pointer', color: '#1976d2' }} onClick={() => navigate(`/class-data-matrix-id/${params.value}`)}>
          {params.value}
        </div>
      )
    },
    { field: 'id', headerName: 'ID', width: 90 },
    { field: 'rowId', headerName: 'Row ID', width: 150 }, // RowIDカラム
    { field: 'colId', headerName: 'Col ID', width: 150 }, // ColIDカラム
    {
      field: 'actions',
      headerName: '操作',
      width: 100,
      renderCell: (params) => (
        <Button variant="contained" color="error" size="small" onClick={() => handleDelete(params.row.name)}>
          削除
        </Button>
      )
    }
  ];

  return (
    <div style={{ height: 400, width: '100%', padding: '20px' }}>
      <Button variant="contained" color="primary" onClick={() => setOpenDialog(true)} sx={{ mb: 2 }}>
        新しいClassDataMatrixIDを作成
      </Button>
      <Button
        variant="contained"
        color="secondary"
        onClick={() =>
          fetch('/api/generate-all-binary-matrix', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message || '全バイナリ生成が正常に完了しました'))
            .catch(error => alert('エラー: ' + error.message))
        }
        sx={{ mb: 2, ml: 2 }}
      >
        全バイナリ生成
      </Button>
      <Button
        variant="contained"
        color="secondary"
        onClick={() =>
          fetch('/api/generate-all-cs-matrix-header', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message || '全C#ヘッダー生成が正常に完了しました'))
            .catch(error => alert('エラー: ' + error.message))
        }
        sx={{ mb: 2, ml: 2 }}
      >
        全C#ヘッダー生成
      </Button>
      <Button
        variant="contained"
        color="secondary"
        onClick={() =>
          fetch('/api/generate-matrix-table-id', { method: 'POST' })
            .then(res => res.json())
            .then(result => alert(result.message || 'MatrixTableID生成が正常に完了しました'))
            .catch(error => alert('エラー: ' + error.message))
        }
        sx={{ mb: 2, ml: 2 }}
      >
        MatrixTableID生成
      </Button>
      <DataGrid rows={matrixData} columns={columns} getRowId={(row) => row.id} />
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>新しいClassDataMatrixIDを作成</DialogTitle>
        <DialogContent>
          <TextField label="名前" fullWidth value={newName} onChange={(e) => setNewName(e.target.value)} sx={{ mt: 2 }} />
          <Autocomplete options={typeOptions} value={newRowId} onChange={(e, v) => setNewRowId(v || '')} renderInput={(params) => <TextField {...params} label="Row ID" sx={{ mt: 2 }} />} />
          <Autocomplete options={typeOptions} value={newColId} onChange={(e, v) => setNewColId(v || '')} renderInput={(params) => <TextField {...params} label="Col ID" sx={{ mt: 2 }} />} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>キャンセル</Button>
          <Button onClick={handleCreate}>作成</Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}

export default ClassDataMatrixIdGrid;