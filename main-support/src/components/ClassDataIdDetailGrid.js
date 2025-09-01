import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid, useGridApiRef } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, IconButton } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import Papa from 'papaparse';
import { useMemo } from 'react';
function ClassDataIdDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState({ columns: [], rows: [] });
  const [typeOptions, setTypeOptions] = useState([]);
  const [enumValues, setEnumValues] = useState({});
  const [loading, setLoading] = useState(true);
  const [openAddColumn, setOpenAddColumn] = useState(false);
  const [openDefaultRecords, setOpenDefaultRecords] = useState(false);
  const [openDeleteColumn, setOpenDeleteColumn] = useState(false);
  const [openImportCsv, setOpenImportCsv] = useState(false);
  const [newColType, setNewColType] = useState('');
  const [newColName, setNewColName] = useState('');
  const [recordCount, setRecordCount] = useState(1);
  const [columnToDelete, setColumnToDelete] = useState('');
  const apiRef = useGridApiRef();

const gridRows = useMemo(() => {
  return data.rows.map((row) => {
    const rowData = {
      id: row.id,
      enum_property: row.enum_property,
      description: row.description,
    };
    data.columns.forEach((col) => {
      rowData[col.name] = row.data?.[col.name]?.value ?? getDefaultValue(col.type);
    });
    return rowData;
  });
}, [data.rows, data.columns]);


  useEffect(() => {
    if (!name || name.includes(':')) {
      alert('不正なClassDataID名です');
      navigate('/class-data-id');
      return;
    }

    setLoading(true);

    fetch(`/api/class-data-id/${encodeURIComponent(name)}`)
      .then(response => {
        if (!response.ok) {
          throw new Error(`データ取得に失敗しました: ${name} (${response.status} ${response.statusText})`);
        }
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('サーバーからJSON以外のレスポンスを受信しました');
        }
        return response.json();
      })
      .then(fetchedData => {
        const rows = (fetchedData.rows || []).map((row, index) => ({
          id: row.id || index + 1,
          enum_property: row.enum_property || `Row${index + 1}`,
          description: row.description || '',
          data: row.data || {},
        }));
        const columns = fetchedData.columns || [];
        rows.forEach(row => {
          columns.forEach(col => {
            let cell = row.data[col.name];
            if (!cell || typeof cell !== 'object' || !('value' in cell) || !('type' in cell)) {
              row.data[col.name] = { value: getDefaultValue(col.type), type: col.type };
            }
          });
        });
        setData({ columns, rows });
        setLoading(false);
      })
      .catch(error => {
        console.error('データ取得エラー:', error);
        alert('データ取得エラー: ' + error.message);
        setLoading(false);
        navigate('/class-data-id');
      });

    Promise.all([
      fetch('/api/enum-id').then(res => {
        if (!res.ok) throw new Error(`enum-id取得に失敗: ${res.status}`);
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('enum-idエンドポイントからJSON以外のレスポンスを受信');
        }
        return res.json();
      }),
      fetch('/api/class-data').then(res => {
        if (!res.ok) throw new Error(`class-data取得に失敗: ${res.status}`);
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('class-dataエンドポイントからJSON以外のレスポンスを受信');
        }
        return res.json();
      }),
      fetch('/api/class-data-id').then(res => {
        if (!res.ok) throw new Error(`class-id-data取得に失敗: ${res.status}`);
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('class-id-dataエンドポイントからJSON以外のレスポンスを受信');
        }
        return res.json();
      }),
    ]).then(([enumList, classList, classIdList]) => {
      const basicTypes = ['int', 'float', 'bool', 'string'];
      const unityTypes = ['Vector2', 'Vector3'];
      const enumTypes = enumList.map(item => item.name);
      const classTypes = classList.map(item => item.name);
      const classIdTypes = classIdList.map(item => item.name);
      setTypeOptions([...basicTypes, ...unityTypes, ...enumTypes, ...classTypes, ...classIdTypes]);

      const enumPromises = enumList.map(enumItem =>
        fetch(`/api/enum/${encodeURIComponent(enumItem.name)}`)
          .then(res => {
            if (!res.ok) {
              console.warn(`enum値取得に失敗: ${enumItem.name} (${res.status})`);
              return [];
            }
            const contentType = res.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
              throw new Error(`enum ${enumItem.name} のレスポンスがJSONではありません`);
            }
            return res.json();
          })
          .then(data => ({ [enumItem.name]: data || [] }))
      );

      const classIdPromises = classIdList.map(classIdItem =>
        fetch(`/api/class-data-id/${encodeURIComponent(classIdItem.name)}`)
          .then(res => {
            if (!res.ok) {
              console.warn(`classId値取得に失敗: ${classIdItem.name} (${res.status})`);
              return [];
            }
            const contentType = res.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
              throw new Error(`classId ${classIdItem.name} のレスポンスがJSONではありません`);
            }
            return res.json();
          })
          .then(data => ({ [classIdItem.name]: data.rows.map(row => row.enum_property) || [] }))
      );

      return Promise.all([...enumPromises, ...classIdPromises]);
    }).then(results => {
      const enumValuesMap = Object.assign({}, ...results);
      setEnumValues(enumValuesMap);
    }).catch(error => {
      console.error('型オプションまたはenum値の取得エラー:', error);
      alert('型オプション取得エラー: ' + error.message);
    });
  }, [name, navigate]);

  const getDefaultValue = (type) => {
    switch (type.toLowerCase()) {
      case 'int': return 0;
      case 'float': return 0.0;
      case 'bool': return false;
      case 'string': return '';
      case 'vector2': return [0, 0];
      case 'vector3': return [0, 0, 0];
      default:
        if (type in enumValues && enumValues[type].length > 0) return `${type}ID.${enumValues[type][0]}`;
        return '';
    }
  };

  const handleAddColumn = () => {
    if (!newColType.trim() || !newColName.trim()) {
      alert('型と名前は必須です');
      return;
    }
    if (data.columns.some(col => col.name === newColName)) {
      alert('カラム名がすでに存在します');
      return;
    }
    const newColumn = { type: newColType, name: newColName };
    const defaultValue = getDefaultValue(newColType);
    const updatedColumns = [...data.columns, newColumn];
    const updatedRows = data.rows.map(row => ({
      ...row,
      data: { ...row.data, [newColName]: { value: defaultValue, type: newColType } }
    }));
    if (updatedRows.length === 0) {
      updatedRows.push({
        id: 1,
        enum_property: `${name}_00`,
        description: '',
        data: { [newColName]: { value: defaultValue, type: newColType } }
      });
    }
    setData({ columns: updatedColumns, rows: updatedRows });
    setOpenAddColumn(false);
    setNewColType('');
    setNewColName('');
  };

  const handleDeleteColumn = (columnName) => {
    if (!columnName) {
      alert('削除するカラムを選択してください');
      return;
    }
    if (window.confirm(`カラム ${columnName} を削除しますか？`)) {
      try {
        const updatedColumns = data.columns.filter(col => col.name !== columnName);
        const updatedRows = data.rows.map(row => {
          const newData = { ...row.data };
          delete newData[columnName];
          return { ...row, data: newData };
        });
        setData({ columns: updatedColumns, rows: updatedRows });
        apiRef.current.setColumnVisibility(columnName, false);
      } catch (error) {
        console.error('カラム削除エラー:', error);
        alert('カラム削除エラー: ' + error.message);
      }
    }
    setOpenDeleteColumn(false);
    setColumnToDelete('');
  };

  const handleDeleteRow = (rowId) => {
    if (window.confirm(`レコード ID ${rowId} を削除しますか？`)) {
      const updatedRows = data.rows.filter(row => row.id !== rowId);
      setData({ ...data, rows: updatedRows });
    }
  };

  const handleCreateDefaultRecords = () => {
    if (recordCount <= 0) {
      alert('有効なレコード数を入力してください');
      return;
    }
    const maxId = Math.max(0, ...data.rows.map(r => r.id || 0));
    const newRows = Array.from({ length: recordCount }, (_, index) => {
      const rowData = {};
      data.columns.forEach(col => {
        rowData[col.name] = { value: getDefaultValue(col.type), type: col.type };
      });
      return {
        id: maxId + index + 1,
        enum_property: `${name}_${(index + 1).toString().padStart(2, '0')}`,
        description: '',
        data: rowData
      };
    });
    setData({ ...data, rows: [...data.rows, ...newRows] });
    setOpenDefaultRecords(false);
    setRecordCount(1);
  };

const processRowUpdate = (newRow, oldRow) => {
  if (!newRow?.id) {
    console.error('processRowUpdate: newRowにidがありません', newRow);
    return oldRow;
  }
  const updatedRow = {
    id: newRow.id,
    enum_property: newRow.enum_property,
    description: newRow.description,
    data: {},
  };
  data.columns.forEach(col => {
    updatedRow.data[col.name] = {
      value: newRow[col.name] ?? getDefaultValue(col.type),
      type: col.type,
    };
  });
  const updatedRows = data.rows.map(row =>
    row.id === newRow.id ? updatedRow : row
  );
  setData({ ...data, rows: updatedRows });
  return newRow;
};

const handleSave = () => {
  const saveData = {
    columns: data.columns,
    rows: data.rows.map(row => ({
      id: row.id,
      enum_property: row.enum_property,
      description: row.description,
      data: { ...row.data }
    }))
  };

  fetch(`/api/class-data-id/${encodeURIComponent(name)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(saveData),
  })
    .then(response => {
      if (!response.ok) throw new Error(`データ保存に失敗: ${name} (${response.status})`);
      return response.json();
    })
    .then(result => alert(result.message))
    .catch(error => alert('保存エラー: ' + error.message));
};

  const handleDelete = () => {
    if (window.confirm(`${name} を削除しますか？`)) {
      fetch(`/api/class-data-id/${encodeURIComponent(name)}`, { method: 'DELETE' })
        .then(response => {
          if (!response.ok) throw new Error(`${name} の削除に失敗`);
          return response.json();
        })
        .then(result => {
          alert(result.message);
          navigate('/class-data-id');
        })
        .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  const handleGenerateCs = () => {
    fetch(`/api/generate-class-data-id/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(response => {
        if (!response.ok) throw new Error(`${name} のC#生成に失敗`);
        return response.json();
      })
      .then(result => alert(result.message))
      .catch(error => alert('C#生成エラー: ' + error.message));
  };

  const handleGenerateBinary = () => {
    fetch(`/api/generate-binary/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(response => {
        if (!response.ok) throw new Error(`${name} のバイナリ生成に失敗`);
        return response.json();
      })
      .then(result => alert(result.message))
      .catch(error => alert('バイナリ生成エラー: ' + error.message));
  };

  const handleExportCsv = () => {
    const csvRows = [];
    const headers = ['id', 'enum_property', 'description', ...data.columns.map(col => col.name)];
    csvRows.push(headers.join(','));

    data.rows.forEach(row => {
      const values = [row.id, row.enum_property, row.description];
      data.columns.forEach(col => {
        const cell = row.data[col.name];
        let value = cell ? cell.value : '';
        if (typeof value === 'object' && value !== null) value = JSON.stringify(value);
        values.push(`"${value.replace(/"/g, '""')}"`);
      });
      csvRows.push(values.join(','));
    });

    const csvContent = csvRows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${name}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleImportCsv = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    Papa.parse(file, {
      header: true,
      complete: (results) => {
        const importedData = results.data;
        const newRows = importedData.map((importedRow, index) => {
          const rowData = {};
          data.columns.forEach(col => {
            let importedValue = importedRow[col.name];
            const parsedValue = parseImportedValue(importedValue, col.type);
            rowData[col.name] = { value: parsedValue, type: col.type };
          });
          return {
            id: index + 1,
            enum_property: importedRow.enum_property || `Row${index + 1}`,
            description: importedRow.description || '',
            data: rowData,
          };
        });
        setData({ ...data, rows: newRows });
        setOpenImportCsv(false);
        alert('CSVインポートが完了しました');
      },
      error: (error) => {
        alert('CSVインポートエラー: ' + error.message);
      },
    });
  };

  const parseImportedValue = (value, type) => {
    if (value === undefined || value === '') return getDefaultValue(type);
    switch (type.toLowerCase()) {
      case 'int': return parseInt(value, 10) || 0;
      case 'float': return parseFloat(value) || 0.0;
      case 'bool': return value.toLowerCase() === 'true' || value === '1';
      case 'string': return value;
      case 'vector2': 
        try {
          const parsed = JSON.parse(value);
          if (Array.isArray(parsed) && parsed.length === 2) return parsed;
          return [0, 0];
        } catch {
          return [0, 0];
        }
      case 'vector3': 
        try {
          const parsed = JSON.parse(value);
          if (Array.isArray(parsed) && parsed.length === 3) return parsed;
          return [0, 0, 0];
        } catch {
          return [0, 0, 0];
        }
      default: return value;
    }
  };

const columns = [
  { field: 'enum_property', headerName: 'Enum Property', width: 150, editable: true },
  { field: 'description', headerName: '説明', width: 200, editable: true },
  {
    field: 'actions',
    headerName: '操作',
    width: 100,
    renderCell: (params) => (
      <IconButton
        color="error"
        size="small"
        onClick={() => handleDeleteRow(params.row.id)}
      >
        <DeleteIcon />
      </IconButton>
    ),
  },
  ...data.columns.map(col => {
    const isBool = col.type.toLowerCase() === 'bool';
    const isEnum = col.type in enumValues;
    const isNumber = col.type.toLowerCase() === 'int' || col.type.toLowerCase() === 'float';
    const isVector = col.type.toLowerCase() === 'vector2' || col.type.toLowerCase() === 'vector3';
    const isString = col.type.toLowerCase() === 'string'; // string 型を明示的にチェック
    return {
      field: col.name,
      headerName: col.name,
      width: 150,
      editable: true,
      headerAlign: 'right',
      renderHeader: () => (
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
          <span>{col.name}</span>
          <IconButton
            color="error"
            size="small"
            onClick={() => {
              setColumnToDelete(col.name);
              setOpenDeleteColumn(true);
            }}
          >
            <DeleteIcon />
          </IconButton>
        </Box>
      ),
      type: isNumber ? 'number' : isBool ? 'boolean' : isString ? 'string' : isVector ? 'string' : 'singleSelect',
      valueOptions: isBool ? [
        { value: true, label: 'true' },
        { value: false, label: 'false' }
      ] : (isEnum ? enumValues[col.type].map(v => ({
        value: `${col.type}ID.${v}`,
        label: `${col.type}ID.${v}`
      })) : undefined),

      valueFormatter: ({ value }) => {
        if (Array.isArray(value)) {
          return JSON.stringify(value);
        }
        return value;
      },
valueParser: (value) => {
  let parsedValue = value;
  try {
    switch (col.type.toLowerCase()) {
      case 'int':
        parsedValue = isNaN(parseInt(value)) ? getDefaultValue(col.type) : parseInt(value);
        break;
      case 'float':
        parsedValue = isNaN(parseFloat(value)) ? getDefaultValue(col.type) : parseFloat(value);
        break;
      case 'bool':
        parsedValue = value === 'true' || value === true || value === '1';
        break;
      case 'string':
        parsedValue = value != null ? String(value) : getDefaultValue(col.type);
        break;
      case 'vector2':
        parsedValue = value ? JSON.parse(value) : getDefaultValue(col.type);
        if (!Array.isArray(parsedValue) || parsedValue.length !== 2) throw new Error('不正なVector2形式');
        break;
      case 'vector3':
        parsedValue = value ? JSON.parse(value) : getDefaultValue(col.type);
        if (!Array.isArray(parsedValue) || parsedValue.length !== 3) throw new Error('不正なVector3形式');
        break;
      default:
        if (isEnum) {
          const enumOpts = enumValues[col.type].map(v => `${col.type}ID.${v}`);
          parsedValue = enumOpts.includes(value) ? value : (enumOpts.length > 0 ? enumOpts[0] : '');
        } else {
          parsedValue = value ?? '';
        }
    }
  } catch (e) {
    console.error(`valueParser error for ${col.name}:`, e);
    parsedValue = getDefaultValue(col.type);
  }
  return parsedValue;
},

    };
  }),
];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        ClassDataID詳細: {name}
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setOpenAddColumn(true)} sx={{ mr: 1 }}>
          カラム追加
        </Button>
        <Button variant="contained" color="primary" onClick={() => setOpenDefaultRecords(true)} sx={{ mr: 1 }}>
          新しくレコード追加
        </Button>
        <Button variant="contained" color="primary" onClick={handleExportCsv} sx={{ mr: 1 }}>
          CSVエクスポート
        </Button>
        <Button variant="contained" color="primary" onClick={() => setOpenImportCsv(true)} sx={{ mr: 1 }}>
          CSVインポート
        </Button>
        <Button variant="contained" color="primary" onClick={handleSave} sx={{ mr: 1 }}>
          保存
        </Button>
        <Button variant="contained" color="secondary" onClick={handleGenerateCs} sx={{ mr: 1 }}>
          C#生成
        </Button>
        <Button variant="contained" color="secondary" onClick={handleGenerateBinary} sx={{ mr: 1 }}>
          バイナリ生成
        </Button>
        <Button variant="contained" color="error" onClick={handleDelete}>
          削除
        </Button>
      </Box>
      {loading || !data.rows ? (
        <Typography>読み込み中...</Typography>
      ) : (
        <div style={{ height: 400, width: '100%' }}>
<DataGrid
            rows={gridRows} // フラットな gridRows を使用
            columns={columns}
            pageSizeOptions={[5]}
            getRowId={(row) => row.id}
            processRowUpdate={processRowUpdate}
            onProcessRowUpdateError={(error) => {
              console.error('編集エラー:', error);
              alert('編集エラー: ' + error.message);
            }}
            editMode="cell"
            apiRef={apiRef}
            onCellClick={(params, event) => {
              if (!params.isEditable || event.defaultMuiPrevented) return;
              try {
                const cellMode = apiRef.current.getCellMode(params.id, params.field);
                if (cellMode !== 'edit') {
                  apiRef.current.startCellEditMode({ id: params.id, field: params.field });
                }
              } catch (error) {
                console.error('セル編集開始エラー:', error);
              }
            }}
            onCellEditStart={(params) => {
              console.log(`セル編集開始: row=${params.id}, field=${params.field}`);
            }}
            onCellEditStop={(params, event) => {
              console.log(`セル編集終了: row=${params.id}, field=${params.field}, reason=${params.reason}`);
              if (params.reason === 'cellFocusOut' || params.reason === 'enterKeyDown') {
                try {
                  apiRef.current.stopCellEditMode({
                    id: params.id,
                    field: params.field,
                    ignoreModifications: false,
                  });
                } catch (error) {
                  console.error('セル編集終了エラー:', error);
                }
              }
            }}
          />
        </div>
      )}
      <Dialog open={openAddColumn} onClose={() => setOpenAddColumn(false)}>
        <DialogTitle>新しいカラムを追加</DialogTitle>
        <DialogContent>
          <Autocomplete
            options={typeOptions}
            renderInput={(params) => <TextField {...params} label="型" margin="dense" fullWidth />}
            value={newColType}
            onChange={(e, newValue) => setNewColType(newValue || '')}
          />
          <TextField
            label="名前"
            margin="dense"
            fullWidth
            value={newColName}
            onChange={(e) => setNewColName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddColumn(false)}>キャンセル</Button>
          <Button onClick={handleAddColumn}>追加</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={openDefaultRecords} onClose={() => setOpenDefaultRecords(false)}>
        <DialogTitle>新しくレコード追加</DialogTitle>
        <DialogContent>
          <TextField
            label="レコード数"
            type="number"
            margin="dense"
            fullWidth
            value={recordCount}
            onChange={(e) => setRecordCount(parseInt(e.target.value) || 1)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDefaultRecords(false)}>キャンセル</Button>
          <Button onClick={handleCreateDefaultRecords}>作成</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={openDeleteColumn} onClose={() => setOpenDeleteColumn(false)}>
        <DialogTitle>カラム削除</DialogTitle>
        <DialogContent>
          <Typography>カラム {columnToDelete} を削除しますか？</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDeleteColumn(false)}>いいえ</Button>
          <Button onClick={() => handleDeleteColumn(columnToDelete)}>はい</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={openImportCsv} onClose={() => setOpenImportCsv(false)}>
        <DialogTitle>CSVインポート</DialogTitle>
        <DialogContent>
          <input type="file" accept=".csv" onChange={handleImportCsv} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenImportCsv(false)}>キャンセル</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ClassDataIdDetailGrid;