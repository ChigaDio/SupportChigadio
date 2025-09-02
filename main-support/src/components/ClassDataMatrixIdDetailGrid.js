import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid, useGridApiRef } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, Tooltip, createTheme, ThemeProvider } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import SaveIcon from '@mui/icons-material/Save';
import DownloadIcon from '@mui/icons-material/Download';
import UploadIcon from '@mui/icons-material/Upload';
import CodeIcon from '@mui/icons-material/Code';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import Papa from 'papaparse';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1976d2' },
    secondary: { main: '#ff4081' },
    background: { default: '#fafafa', paper: '#ffffff' },
    text: { primary: '#333', secondary: '#666' },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
          textTransform: 'none',
          padding: '8px 16px',
          transition: 'background-color 0.2s ease',
          '&:hover': {
            backgroundColor: '#e0e0e0',
          },
        },
        containedPrimary: {
          backgroundColor: '#1976d2',
          color: '#fff',
          '&:hover': {
            backgroundColor: '#1565c0',
          },
        },
        containedSecondary: {
          backgroundColor: '#ff4081',
          color: '#fff',
          '&:hover': {
            backgroundColor: '#f50057',
          },
        },
      },
    },
    MuiDataGrid: {
      styleOverrides: {
        root: {
          border: 'none',
          borderRadius: '8px',
          backgroundColor: '#fff',
        },
        columnHeader: {
          backgroundColor: '#1976d2',
          color: '#fff',
          fontWeight: 500,
          borderBottom: '1px solid #e0e0e0',
        },
        cell: {
          borderBottom: '1px solid #e0e0e0',
          borderRight: '1px solid #e0e0e0',
          padding: '8px',
          transition: 'background-color 0.2s ease',
          '&:hover': {
            backgroundColor: '#f5f7fa',
          },
          '&.MuiDataGrid-cell--editing': {
            backgroundColor: '#e8f0fe',
            border: '1px solid #1976d2',
          },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: '8px',
          backgroundColor: '#fff',
        },
      },
    },
  },
});

function ClassDataMatrixIdDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState({ rowId: '', colId: '', fields: [], data: {} });
  const [typeOptions, setTypeOptions] = useState([]);
  const [enumValues, setEnumValues] = useState({});
  const [rowKeys, setRowKeys] = useState([]);
  const [colKeys, setColKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openAddField, setOpenAddField] = useState(false);
  const [openDeleteField, setOpenDeleteField] = useState(false);
  const [newFieldType, setNewFieldType] = useState('');
  const [newFieldName, setNewFieldName] = useState('');
  const [newFieldDescription, setNewFieldDescription] = useState('');
  const [fieldToDelete, setFieldToDelete] = useState('');
  const [openImportCsv, setOpenImportCsv] = useState(false);
  const [openCellEditor, setOpenCellEditor] = useState(false);
  const [editingCell, setEditingCell] = useState(null);
  const [cellValues, setCellValues] = useState({});
  const apiRef = useGridApiRef();

  const gridRows = useMemo(() => {
    return rowKeys.map((rowKey, index) => {
      const rowData = { id: index, rowKey };
      colKeys.forEach(colKey => {
        rowData[colKey] = data.data[rowKey]?.[colKey] ?? {};
      });
      return rowData;
    });
  }, [rowKeys, colKeys, data.data]);

  useEffect(() => {
    if (!name || name.includes(':')) {
      alert('不正なClassDataMatrixID名です');
      navigate('/class-data-matrix-id');
      return;
    }

    setLoading(true);
    fetch(`/api/class-data-matrix-id/${encodeURIComponent(name)}`)
      .then(response => {
        if (!response.ok) throw new Error(`データ取得に失敗: ${response.status}`);
        return response.json();
      })
      .then(fetchedData => {
        setData(fetchedData);
        setLoading(false);
      })
      .catch(error => {
        alert('データ取得エラー: ' + error.message);
        navigate('/class-data-matrix-id');
      });

    Promise.all([
      fetch('/api/enum-id').then(res => res.json()),
      fetch('/api/class-data').then(res => res.json()),
      fetch('/api/class-data-id').then(res => res.json())
    ]).then(([enumList, classList, classIdList]) => {
      const basicTypes = ['int', 'float', 'bool', 'string'];
      const unityTypes = ['Vector2', 'Vector3'];
      const enumTypes = enumList.map(item => item.name);
      const classTypes = classList.map(item => item.name);
      const classIdTypes = classIdList.map(item => item.name);
      setTypeOptions([...basicTypes, ...unityTypes, ...enumTypes, ...classTypes, ...classIdTypes]);

      const enumPromises = enumList.map(e =>
        fetch(`/api/enum/${encodeURIComponent(e.name)}`)
          .then(res => res.json())
          .then(d => ({ [e.name]: d }))
      );
      const classIdPromises = classIdList.map(c =>
        fetch(`/api/class-data-id/${encodeURIComponent(c.name)}`)
          .then(res => res.json())
          .then(d => ({ [c.name]: d.rows.map(r => r.enum_property) }))
      );
      Promise.all([...enumPromises, ...classIdPromises]).then(results => {
        setEnumValues(Object.assign({}, ...results));
      });
    }).catch(error => {
      alert('型オプション取得エラー: ' + error.message);
    });
  }, [name, navigate]);

  useEffect(() => {
    if (data.rowId && data.colId && enumValues[data.rowId] && enumValues[data.colId]) {
      const rowValues = enumValues[data.rowId] || [];
      const colValues = enumValues[data.colId] || [];
      setRowKeys(rowValues);
      setColKeys(colValues);

      const newData = { ...data.data };
      rowValues.forEach(rk => {
        if (!newData[rk]) newData[rk] = {};
        colValues.forEach(ck => {
          if (!newData[rk][ck]) newData[rk][ck] = {};
          data.fields.forEach(field => {
            if (newData[rk][ck][field.name] === undefined) {
              newData[rk][ck][field.name] = getDefaultValue(field.type);
            }
          });
        });
      });
      Object.keys(newData).filter(k => !rowValues.includes(k)).forEach(k => delete newData[k]);
      Object.keys(newData).forEach(rk => {
        Object.keys(newData[rk]).filter(ck => !colValues.includes(ck)).forEach(ck => delete newData[rk][ck]);
      });
      setData({ ...data, data: newData });
    }
  }, [enumValues, data.rowId, data.colId, data.fields]);

  const getDefaultValue = (type) => {
    switch (type.toLowerCase()) {
      case 'int': return 0;
      case 'float': return 0.0;
      case 'bool': return false;
      case 'string': return '';
      case 'vector2': return [0, 0];
      case 'vector3': return [0, 0, 0];
      default:
        return enumValues[type]?.[0] ? `${type}ID.${enumValues[type][0]}` : '';
    }
  };

  const parseImportedValue = (value, type) => {
    if (value === undefined || value === '') return getDefaultValue(type);
    switch (type.toLowerCase()) {
      case 'int': return parseInt(value, 10) || 0;
      case 'float': return parseFloat(value) || 0.0;
      case 'bool': return value.toLowerCase() === 'true' || value === '1';
      case 'string': return String(value);
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
      default:
        const enumOpts = enumValues[type]?.map(v => `${type}ID.${v}`) || [];
        return enumOpts.includes(value) ? value : (enumOpts[0] || '');
    }
  };

  const handleAddField = () => {
    if (!newFieldType || !newFieldName) return alert('型と名前は必須です');
    if (data.fields.some(f => f.name === newFieldName)) return alert('名前がすでに存在します');
    const newFields = [...data.fields, { type: newFieldType, name: newFieldName, description: newFieldDescription }];
    const newData = { ...data.data };
    rowKeys.forEach(rk => {
      colKeys.forEach(ck => {
        if (!newData[rk][ck]) newData[rk][ck] = {};
        newData[rk][ck][newFieldName] = getDefaultValue(newFieldType);
      });
    });
    setData({ ...data, fields: newFields, data: newData });
    setNewFieldType('');
    setNewFieldName('');
    setNewFieldDescription('');
    setOpenAddField(false);
  };

  const handleDeleteField = () => {
    if (!fieldToDelete) return alert('削除するフィールドを選択してください');
    const newFields = data.fields.filter(f => f.name !== fieldToDelete);
    const newData = { ...data.data };
    rowKeys.forEach(rk => {
      colKeys.forEach(ck => {
        if (newData[rk][ck]) delete newData[rk][ck][fieldToDelete];
      });
    });
    setData({ ...data, fields: newFields, data: newData });
    setFieldToDelete('');
    setOpenDeleteField(false);
  };

  const handleSave = () => {
    fetch(`/api/class-data-matrix-id/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('保存エラー: ' + error.message));
  };

  const handleDelete = () => {
    if (window.confirm(`${name} を削除しますか？`)) {
      fetch(`/api/class-data-matrix-id/${encodeURIComponent(name)}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          navigate('/class-data-matrix-id');
        })
        .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  const handleGenerateCs = () => {
    fetch(`/api/generate-class-data-matrix-id/${encodeURIComponent(name)}`, { method: 'POST' })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('C#生成エラー: ' + error.message));
  };

  const handleGenerateBinary = () => {
    fetch(`/api/generate-binary-matrix/${encodeURIComponent(name)}`, { method: 'POST' })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('バイナリ生成エラー: ' + error.message));
  };

  const handleExportCsv = () => {
    const headers = ['rowKey', ...colKeys];
    const csvRows = [headers.join(',')];
    rowKeys.forEach(rk => {
      const values = [rk, ...colKeys.map(ck => {
        const value = data.data[rk]?.[ck] || {};
        return `"${JSON.stringify(value).replace(/"/g, '""')}"`;
      })];
      csvRows.push(values.join(','));
    });
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
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
        const newData = { ...data.data };
        results.data.forEach(impRow => {
          const rk = impRow.rowKey;
          if (rowKeys.includes(rk)) {
            colKeys.forEach(ck => {
              try {
                const parsed = JSON.parse(impRow[ck] || '{}');
                if (!newData[rk][ck]) newData[rk][ck] = {};
                data.fields.forEach(f => {
                  newData[rk][ck][f.name] = parsed[f.name] !== undefined ? parseImportedValue(parsed[f.name], f.type) : getDefaultValue(f.type);
                });
              } catch {
                newData[rk][ck] = {};
                data.fields.forEach(f => {
                  newData[rk][ck][f.name] = getDefaultValue(f.type);
                });
              }
            });
          }
        });
        setData({ ...data, data: newData });
        setOpenImportCsv(false);
        alert('CSVインポートが完了しました');
      },
      error: (error) => alert('CSVインポートエラー: ' + error.message)
    });
  };

  const handleCellDoubleClick = (params) => {
    if (!data.fields.length) return;
    setEditingCell({ rowKey: params.row.rowKey, colKey: params.field });
    setCellValues(data.data[params.row.rowKey]?.[params.field] || {});
    setOpenCellEditor(true);
  };

  const handleCellEditorSave = () => {
    const newData = { ...data.data };
    if (!newData[editingCell.rowKey]) newData[editingCell.rowKey] = {};
    newData[editingCell.rowKey][editingCell.colKey] = { ...cellValues };
    setData({ ...data, data: newData });
    setOpenCellEditor(false);
    setCellValues({});
    setEditingCell(null);
  };

  const Vector2Editor = ({ field, value, onChange }) => {
    const [x, y] = Array.isArray(value) ? value : [0, 0];
    return (
      <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
        <TextField
          type="number"
          label="X"
          value={x}
          onChange={(e) => onChange([parseFloat(e.target.value) || 0, y])}
          size="small"
          variant="outlined"
          sx={{ width: 100 }}
        />
        <TextField
          type="number"
          label="Y"
          value={y}
          onChange={(e) => onChange([x, parseFloat(e.target.value) || 0])}
          size="small"
          variant="outlined"
          sx={{ width: 100 }}
        />
      </Box>
    );
  };

  const Vector3Editor = ({ field, value, onChange }) => {
    const [x, y, z] = Array.isArray(value) ? value : [0, 0, 0];
    return (
      <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
        <TextField
          type="number"
          label="X"
          value={x}
          onChange={(e) => onChange([parseFloat(e.target.value) || 0, y, z])}
          size="small"
          variant="outlined"
          sx={{ width: 100 }}
        />
        <TextField
          type="number"
          label="Y"
          value={y}
          onChange={(e) => onChange([x, parseFloat(e.target.value) || 0, z])}
          size="small"
          variant="outlined"
          sx={{ width: 100 }}
        />
        <TextField
          type="number"
          label="Z"
          value={z}
          onChange={(e) => onChange([x, y, parseFloat(e.target.value) || 0])}
          size="small"
          variant="outlined"
          sx={{ width: 100 }}
        />
      </Box>
    );
  };

  const columns = useMemo(() => {
    return [
      { field: 'rowKey', headerName: 'Row Key', width: 150 },
      ...colKeys.map(ck => {
        return {
          field: ck,
          headerName: ck,
          width: 200,
          editable: !!data.fields.length,
          renderCell: (params) => {
            const value = params.value || {};
            const display = data.fields.map(f => `${f.name}: ${Array.isArray(value[f.name]) ? JSON.stringify(value[f.name]) : value[f.name]}`).join(', ');
            return (
              <Tooltip title={display || '空'}>
                <Box sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {display || '空'}
                </Box>
              </Tooltip>
            );
          },
        };
      })
    ];
  }, [colKeys, data.fields]);

  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ p: 3, maxWidth: '1200px', margin: '0 auto' }}>
        <Typography variant="h5" gutterBottom sx={{ fontWeight: 500, color: 'text.primary' }}>
          {name}
        </Typography>
        <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>Row: {data.rowId}</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>Col: {data.colId}</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setOpenAddField(true)}>
              追加
            </Button>
            {data.fields.length > 0 && (
              <Button variant="contained" color="error" startIcon={<DeleteIcon />} onClick={() => setOpenDeleteField(true)}>
                削除
              </Button>
            )}
            <Button variant="contained" color="primary" startIcon={<DownloadIcon />} onClick={handleExportCsv}>
              CSV
            </Button>
            <Button variant="contained" color="primary" startIcon={<UploadIcon />} onClick={() => setOpenImportCsv(true)}>
              インポート
            </Button>
            <Button variant="contained" color="primary" startIcon={<SaveIcon />} onClick={handleSave}>
              保存
            </Button>
            <Button variant="contained" color="secondary" startIcon={<CodeIcon />} onClick={handleGenerateCs}>
              C#
            </Button>
            <Button variant="contained" color="secondary" startIcon={<CodeIcon />} onClick={handleGenerateBinary}>
              バイナリ
            </Button>
            <Button variant="contained" color="error" startIcon={<DeleteForeverIcon />} onClick={handleDelete}>
              削除
            </Button>
          </Box>
        </Box>
        {loading ? (
          <Typography sx={{ color: 'text.secondary' }}>読み込み中...</Typography>
        ) : (
          <div style={{ height: 600, width: '100%' }}>
            <DataGrid
              rows={gridRows}
              columns={columns}
              pageSizeOptions={[5, 10, 20]}
              getRowId={(row) => row.id}
              editMode="cell"
              apiRef={apiRef}
              onCellDoubleClick={handleCellDoubleClick}
              sx={{
                '& .MuiDataGrid-main': {
                  borderRadius: '8px',
                  overflow: 'hidden',
                },
              }}
            />
          </div>
        )}
        <Dialog open={openAddField} onClose={() => setOpenAddField(false)} sx={{ '& .MuiDialog-paper': { transition: 'opacity 0.2s ease' } }}>
          <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 500 }}>
            フィールド追加
          </DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <Autocomplete
              options={typeOptions}
              value={newFieldType}
              onChange={(e, newValue) => setNewFieldType(newValue || '')}
              renderInput={(params) => <TextField {...params} label="型" margin="dense" fullWidth variant="outlined" />}
            />
            <TextField
              label="名前"
              margin="dense"
              fullWidth
              value={newFieldName}
              onChange={(e) => setNewFieldName(e.target.value)}
              variant="outlined"
            />
            <TextField
              label="説明"
              margin="dense"
              fullWidth
              value={newFieldDescription}
              onChange={(e) => setNewFieldDescription(e.target.value)}
              variant="outlined"
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpenAddField(false)} color="secondary">キャンセル</Button>
            <Button onClick={handleAddField} color="primary">追加</Button>
          </DialogActions>
        </Dialog>
        <Dialog open={openDeleteField} onClose={() => setOpenDeleteField(false)} sx={{ '& .MuiDialog-paper': { transition: 'opacity 0.2s ease' } }}>
          <DialogTitle sx={{ bgcolor: 'error.main', color: 'white', fontWeight: 500 }}>
            フィールド削除
          </DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <Autocomplete
              options={data.fields.map(f => f.name)}
              value={fieldToDelete}
              onChange={(e, newValue) => setFieldToDelete(newValue || '')}
              renderInput={(params) => <TextField {...params} label="削除するフィールド" margin="dense" fullWidth />}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpenDeleteField(false)} color="secondary">キャンセル</Button>
            <Button onClick={handleDeleteField} color="error">削除</Button>
          </DialogActions>
        </Dialog>
        <Dialog open={openImportCsv} onClose={() => setOpenImportCsv(false)} sx={{ '& .MuiDialog-paper': { transition: 'opacity 0.2s ease' } }}>
          <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 500 }}>
            CSVインポート
          </DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            <input type="file" accept=".csv" onChange={handleImportCsv} style={{ marginTop: '16px' }} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpenImportCsv(false)} color="secondary">キャンセル</Button>
          </DialogActions>
        </Dialog>
        <Dialog open={openCellEditor} onClose={() => setOpenCellEditor(false)} sx={{ '& .MuiDialog-paper': { transition: 'opacity 0.2s ease' } }}>
          <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 500 }}>
            セル編集 ({editingCell?.rowKey}, {editingCell?.colKey})
          </DialogTitle>
          <DialogContent sx={{ pt: 2 }}>
            {data.fields.map(field => {
              const fieldType = field.type.toLowerCase();
              const value = cellValues[field.name] ?? getDefaultValue(fieldType);
              const isEnum = fieldType in enumValues;
              const isVector2 = fieldType === 'vector2';
              const isVector3 = fieldType === 'vector3';
              return (
                <Box key={field.name} sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>{field.name} ({field.type})</Typography>
                  {isVector2 ? (
                    <Vector2Editor field={field.name} value={value} onChange={(val) => setCellValues({ ...cellValues, [field.name]: val })} />
                  ) : isVector3 ? (
                    <Vector3Editor field={field.name} value={value} onChange={(val) => setCellValues({ ...cellValues, [field.name]: val })} />
                  ) : isEnum ? (
                    <Autocomplete
                      options={enumValues[fieldType].map(v => `${fieldType}ID.${v}`)}
                      value={value}
                      onChange={(e, newValue) => setCellValues({ ...cellValues, [field.name]: newValue || getDefaultValue(fieldType) })}
                      renderInput={(params) => <TextField {...params} label={field.name} variant="outlined" />}
                    />
                  ) : fieldType === 'bool' ? (
                    <Autocomplete
                      options={[{ value: true, label: 'True' }, { value: false, label: 'False' }]}
                      value={value}
                      getOptionLabel={(option) => option.label}
                      onChange={(e, newValue) => setCellValues({ ...cellValues, [field.name]: newValue ? newValue.value : getDefaultValue(fieldType) })}
                      renderInput={(params) => <TextField {...params} label={field.name} variant="outlined" />}
                    />
                  ) : (
                    <TextField
                      type={fieldType === 'int' || fieldType === 'float' ? 'number' : 'text'}
                      label={field.name}
                      value={value}
                      onChange={(e) => {
                        let newValue = e.target.value;
                        if (fieldType === 'int') newValue = parseInt(newValue) || 0;
                        if (fieldType === 'float') newValue = parseFloat(newValue) || 0.0;
                        setCellValues({ ...cellValues, [field.name]: newValue });
                      }}
                      fullWidth
                      variant="outlined"
                      InputProps={{ inputProps: { step: fieldType === 'float' ? 'any' : undefined } }}
                    />
                  )}
                </Box>
              );
            })}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpenCellEditor(false)} color="secondary">キャンセル</Button>
            <Button onClick={handleCellEditorSave} color="primary">保存</Button>
          </DialogActions>
        </Dialog>
      </Box>
    </ThemeProvider>
  );
}

export default ClassDataMatrixIdDetailGrid;