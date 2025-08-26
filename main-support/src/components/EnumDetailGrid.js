import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';

function EnumDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [originalData, setOriginalData] = useState([]); // 保存済みデータ
  const [loading, setLoading] = useState(true);
  const [openAddDialog, setOpenAddDialog] = useState(false);
  const [openDefaultDialog, setOpenDefaultDialog] = useState(false);
  const [newProperty, setNewProperty] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [defaultCount, setDefaultCount] = useState('');

  // データ取得
  useEffect(() => {
    fetch(`/api/enum/${name}`)
      .then(response => response.json())
      .then(data => {
        const validData = data
          .filter(item => !isNaN(parseFloat(item.value)) && isFinite(item.value))
          .map((item, index) => ({
            ...item,
            id: item.id || index + 1,
            value: parseInt(item.value, 10),
            description: item.description || ''
          }));
        console.log('Fetched data:', validData);
        setData(validData);
        setOriginalData(validData); // 保存済みデータを保持
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching data:', error);
        setLoading(false);
      });
  }, [name]);

  // 新しい行を追加
  const handleAddRow = () => {
    if (!newProperty.trim()) {
      alert('Propertyを入力してください');
      return;
    }
    const maxId = Math.max(...data.map(item => item.id), 0) + 1;
    const maxValue = data.length > 0 ? Math.max(...data.map(item => item.value), 0) + 1 : 1; // 1スタート
    const newRow = {
      id: maxId,
      property: newProperty,
      value: maxValue,
      description: newDescription || ''
    };
    const updatedData = [...data, newRow];
    console.log('Added new row:', newRow);
    setData(updatedData);
    setOpenAddDialog(false);
    setNewProperty('');
    setNewDescription('');
  };

  // デフォルト行を追加（指定数）
  const handleAddDefault = () => {
    const count = parseInt(defaultCount, 10);
    if (isNaN(count) || count <= 0) {
      alert('正の数を入力してください');
      return;
    }
    const maxId = Math.max(...data.map(item => item.id), 0);
    const maxValue = data.length > 0 ? Math.max(...data.map(item => item.value), 0) + 1 : 1; // 1スタート
    const newRows = Array.from({ length: count }, (_, index) => ({
      id: maxId + index + 1,
      property: `${name}_${index}`,
      value: maxValue + index,
      description: `${name}_${index}（デフォルト）`
    }));
    const updatedData = [...data, ...newRows];
    console.log('Added default rows:', newRows);
    setData(updatedData);
    setOpenDefaultDialog(false);
    setDefaultCount('');
  };

  // 行の入れ替え（ドラッグ＆ドロップ）
  const handleRowOrderChange = (params) => {
    const { oldIndex, targetIndex } = params;
    const newData = [...data];
    const [movedRow] = newData.splice(oldIndex, 1);
    newData.splice(targetIndex, 0, movedRow);
    // valueを連番に更新（1スタート）
    const updatedData = newData.map((item, index) => ({
      ...item,
      value: index + 1 // 1スタート
    }));
    console.log('Reordered data:', updatedData);
    setData(updatedData);
  };

  // セル編集（descriptionのみ）
  const processRowUpdate = (newRow, oldRow) => {
    const updatedData = data.map(row =>
      row.id === newRow.id ? newRow : row
    );
    console.log('Edited row:', newRow, 'Updated data:', updatedData);
    setData(updatedData);
    return newRow; // DataGridに新しい行を返す
  };

  // 保存
  const handleSave = () => {
    const validData = data.filter(item => !isNaN(item.value) && isFinite(item.value));
    console.log('Saving data:', validData);
    fetch(`/api/enum/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(validData),
    })
      .then(response => response.json())
      .then(result => {
        alert(result.message);
        setOriginalData(validData); // 保存後にoriginalDataを更新
      })
      .catch(error => alert('保存エラー: ' + error));
  };

  // 削除
  const handleDelete = () => {
    if (window.confirm(`${name}.json を削除しますか？`)) {
      fetch(`/api/enum/${name}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          navigate('/'); // トップページに戻る
        })
        .catch(error => alert('削除エラー: ' + error));
    }
  };

  // C#ファイル生成
  const handleGenerateCs = () => {
    const validData = data.filter(item => !isNaN(item.value) && isFinite(item.value));
    console.log('Generating C# with data:', validData);
    fetch(`/api/generate-enum/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(validData),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('C#生成エラー: ' + error));
  };

  // 行のスタイル（descriptionの差分を赤くハイライト）
  const getRowClassName = (params) => {
    const originalRow = originalData.find(row => row.id === params.id);
    const isDifferent = originalRow && originalRow.description !== params.row.description;
    console.log(`Row ${params.id}: original=${originalRow?.description}, current=${params.row.description}, isDifferent=${isDifferent}`);
    return isDifferent ? 'row-highlight' : '';
  };

  const columns = [
    { field: 'id', headerName: 'ID', width: 90, editable: false },
    { field: 'property', headerName: 'Property', width: 150, editable: true }, // Propertyを編集可能に
    { field: 'value', headerName: 'Value', width: 100, editable: false },
    {
      field: 'description',
      headerName: 'Description',
      width: 200,
      editable: true // 編集可能
    },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        {name} Details
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button
          variant="contained"
          color="primary"
          startIcon={<AddIcon />}
          onClick={() => setOpenAddDialog(true)}
          sx={{ mr: 1 }}
        >
          新しい行を追加
        </Button>
        <Button
          variant="contained"
          color="primary"
          onClick={() => setOpenDefaultDialog(true)}
          sx={{ mr: 1 }}
        >
          デフォルト作成
        </Button>
        <Button
          variant="contained"
          color="primary"
          onClick={handleSave}
          sx={{ mr: 1 }}
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
        <Button
          variant="contained"
          color="error"
          onClick={handleDelete}
        >
          削除
        </Button>
      </Box>
      {loading ? (
        <Typography>Loading...</Typography>
      ) : (
        <div style={{ height: 400, width: '100%' }}>
          <DataGrid
            rows={data}
            columns={columns}
            pageSizeOptions={[5]}
            getRowId={(row) => row.id}
            rowReordering
            onRowOrderChange={handleRowOrderChange}
            processRowUpdate={processRowUpdate}
            onProcessRowUpdateError={(error) => console.error('Cell edit error:', error)}
            getRowClassName={getRowClassName}
            sx={{
              '& .row-highlight': {
                backgroundColor: '#ffe6e6', // 赤い背景
                '&:hover': {
                  backgroundColor: '#ffd1d1', // ホバー時
                },
              },
            }}
          />
        </div>
      )}
      {/* 新しい行追加ダイアログ */}
      <Dialog open={openAddDialog} onClose={() => setOpenAddDialog(false)}>
        <DialogTitle>新しい行を追加</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Property"
            fullWidth
            variant="standard"
            value={newProperty}
            onChange={(e) => setNewProperty(e.target.value)}
          />
          <TextField
            margin="dense"
            label="Description"
            fullWidth
            variant="standard"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddDialog(false)}>キャンセル</Button>
          <Button onClick={handleAddRow}>追加</Button>
        </DialogActions>
      </Dialog>
      {/* デフォルト作成ダイアログ */}
      <Dialog open={openDefaultDialog} onClose={() => setOpenDefaultDialog(false)}>
        <DialogTitle>デフォルト行を追加</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="作成する行数"
            type="number"
            fullWidth
            variant="standard"
            value={defaultCount}
            onChange={(e) => setDefaultCount(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDefaultDialog(false)}>キャンセル</Button>
          <Button onClick={handleAddDefault}>作成</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default EnumDetailGrid;