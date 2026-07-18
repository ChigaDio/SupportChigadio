import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid, useGridApiRef } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, createTheme, ThemeProvider } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import SaveIcon from '@mui/icons-material/Save';
import DownloadIcon from '@mui/icons-material/Download';
import UploadIcon from '@mui/icons-material/Upload';
import CodeIcon from '@mui/icons-material/Code';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import Chip from '@mui/material/Chip';
import Papa from 'papaparse';
import {
  parseType,
  getDefaultValueForType,
  SingleValueEditor,
  ArrayFieldEditor,
  ClassFieldEditor,
  formatPreviewValue,
} from './ClassDataIdDetailGrid';

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
  // ★ 追加: classDataのスキーマを保持（ネスト入力・配列対応のため）
  const [classSchemas, setClassSchemas] = useState({});
  const [classList, setClassList] = useState([]);
  // ★ 追加: タグ表示用（一覧側で管理、ここでは読み取りのみ）
  const [currentTag, setCurrentTag] = useState(null);
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

  // ★ 配列型("int[]"等)・classData型（ネスト）にも対応した共通のデフォルト値生成
  // (gridRows等より先に定義しておく必要があるため、ここに配置)
  const getDefaultValue = (type) => {
    const { isArray, baseType } = parseType(type);
    if (isArray) return [];
    return getDefaultValueForType(baseType, enumValues, classSchemas);
  };

  const parseImportedValue = (value, type) => {
    const { isArray, baseType } = parseType(type);
    if (isArray) {
      // CSVインポート時、セル全体はJSON化されているため配列はそのまま渡ってくる想定
      return Array.isArray(value) ? value : [];
    }
    if (value === undefined || value === '') return getDefaultValue(type);
    switch (baseType.toLowerCase()) {
      case 'int': return parseInt(value, 10) || 0;
      case 'float': return parseFloat(value) || 0.0;
      case 'bool': return typeof value === 'string' ? (value.toLowerCase() === 'true' || value === '1') : !!value;
      case 'string': return String(value);
      case 'vector2':
        try {
          const parsed = typeof value === 'string' ? JSON.parse(value) : value;
          if (Array.isArray(parsed) && parsed.length === 2) return parsed;
          return [0, 0];
        } catch {
          return [0, 0];
        }
      case 'vector3':
        try {
          const parsed = typeof value === 'string' ? JSON.parse(value) : value;
          if (Array.isArray(parsed) && parsed.length === 3) return parsed;
          return [0, 0, 0];
        } catch {
          return [0, 0, 0];
        }
      default:
        if (classSchemas && classSchemas[baseType]) {
          // classData型: すでにオブジェクトであればそのまま、文字列ならJSONとして解釈
          if (typeof value === 'object' && value !== null) return value;
          try {
            const parsed = JSON.parse(value);
            return (parsed && typeof parsed === 'object') ? parsed : getDefaultValue(type);
          } catch {
            return getDefaultValue(type);
          }
        }
        const enumOpts = enumValues[baseType]?.map(v => `${baseType}ID.${v}`) || [];
        return enumOpts.includes(value) ? value : (enumOpts[0] || `${baseType}ID.None`);
    }
  };

  const gridRows = useMemo(() => {
    return rowKeys.map((rowKey, index) => {
      const rowData = { id: index, rowKey };
      colKeys.forEach(colKey => {
        const cellData = data.data[rowKey]?.[colKey] || {};
        const initializedCell = {};
        data.fields.forEach(field => {
          initializedCell[field.name] = cellData[field.name] ?? getDefaultValue(field.type);
        });
        rowData[colKey] = initializedCell;
      });
      return rowData;
    });
  }, [rowKeys, colKeys, data.data, data.fields]);

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
        console.log('fetchedData:', fetchedData);
        const transformedData = {
          ...fetchedData,
          data: Object.keys(fetchedData.data).reduce((acc, rowKey) => {
            if (typeof rowKey !== 'string') return acc;
            acc[rowKey] = Object.keys(fetchedData.data[rowKey] || {}).reduce((colAcc, colKey) => {
              if (typeof colKey !== 'string') return colAcc;
              const cellData = fetchedData.data[rowKey][colKey] || {};
              const transformedCell = {};
              fetchedData.fields.forEach(field => {
                transformedCell[field.name] = cellData[field.name] ?? cellData.value ?? getDefaultValue(field.type);
              });
              colAcc[colKey] = transformedCell;
              return colAcc;
            }, {});
            return acc;
          }, {}),
        };
        if (Object.keys(transformedData.data).length === 0 && transformedData.rowId && transformedData.colId) {
          const initialData = {};
          const defaultRowKeys = enumValues[transformedData.rowId]?.map(item => typeof item === 'string' ? item : item.property || '').filter(v => v) || ['defaultRow1', 'defaultRow2'];
          const defaultColKeys = enumValues[transformedData.colId]?.map(item => typeof item === 'string' ? item : item.enum_property || '').filter(v => v) || ['defaultCol1', 'defaultCol2'];
          defaultRowKeys.forEach(rk => {
            initialData[rk] = {};
            defaultColKeys.forEach(ck => {
              initialData[rk][ck] = {};
              transformedData.fields.forEach(field => {
                initialData[rk][ck][field.name] = getDefaultValue(field.type);
              });
            });
          });
          transformedData.data = initialData;
        }
        setData(transformedData);
        setLoading(false);
      })
      .catch(error => {
        alert('データ取得エラー: ' + error.message);
        navigate('/class-data-matrix-id');
      });

    // 現在のタグ表示用（一覧のリストから拾う）
    fetch('/api/class-data-matrix-id')
      .then(res => res.json())
      .then(list => {
        const entry = Array.isArray(list) ? list.find(item => item.name === name) : null;
        setCurrentTag(entry?.tag ?? null);
      })
      .catch(() => {});

    Promise.all([
      fetch('/api/enum-id').then(res => res.json()),
      fetch('/api/class-data').then(res => res.json()),
      fetch('/api/class-data-id').then(res => res.json())
    ]).then(([enumList, classListData, classIdList]) => {
      const basicTypes = ['int', 'float', 'bool', 'string'];
      const unityTypes = ['Vector2', 'Vector3'];
      const enumTypes = enumList.map(item => item.name);
      const classTypes = classListData.map(item => item.name);
      const classIdTypes = classIdList.map(item => item.name);

      // ★ classDataの一覧を保持（配列型判定・ネスト編集に使う）
      setClassList(classTypes);

      // ★ 配列型のオプションを追加（"int[]" のような表記で動的配列を選べるように）
      const allBaseTypes = [...basicTypes, ...unityTypes, ...enumTypes, ...classTypes, ...classIdTypes];
      const arrayTypes = allBaseTypes.map(t => `${t}[]`);

      setTypeOptions([...allBaseTypes, ...arrayTypes]);

      const enumPromises = enumList.map(e =>
        fetch(`/api/enum/${encodeURIComponent(e.name)}`)
          .then(res => res.json())
          .catch(() => [])
          .then(d => ({
            [e.name]: Array.isArray(d) ? d.map(item => typeof item === 'string' ? item : item.property || '').filter(v => v) : []
          }))
      );
      const classIdPromises = classIdList.map(c =>
        fetch(`/api/class-data-id/${encodeURIComponent(c.name)}`)
          .then(res => res.json())
          .catch(() => ({ rows: [] }))
          .then(d => ({
            [c.name]: Array.isArray(d.rows) ? d.rows.map(r => r.enum_property || '').filter(v => v) : []
          }))
      );
      // ★ classDataスキーマの取得（ネスト編集・配列デフォルト値生成に使う）
      const classSchemaPromises = classTypes.map(className =>
        fetch(`/api/class-data/${encodeURIComponent(className)}`)
          .then(res => res.ok ? res.json() : [])
          .then(d => ({ [className]: Array.isArray(d) ? d : [] }))
          .catch(() => ({ [className]: [] }))
      );
      return Promise.all([
        Promise.all(enumPromises),
        Promise.all(classIdPromises),
        Promise.all(classSchemaPromises),
      ]);
    }).then(([enumResults, classIdResults, classSchemaResults]) => {
      const newEnumValues = Object.assign({}, ...enumResults, ...classIdResults);
      console.log('enumValues:', newEnumValues);
      setEnumValues(newEnumValues);
      const schemasMap = Object.assign({}, ...classSchemaResults);
      setClassSchemas(schemasMap);
    }).catch(error => {
      alert('型オプション取得エラー: ' + error.message);
    });
  }, [name, navigate]);

  useEffect(() => {
    if (data.rowId && data.colId && enumValues[data.rowId] && enumValues[data.colId]) {
      const rowValues = Array.isArray(enumValues[data.rowId])
        ? enumValues[data.rowId].map(item => typeof item === 'string' ? item : item.property || '').filter(v => v)
        : [];
      const colValues = Array.isArray(enumValues[data.colId])
        ? enumValues[data.colId].map(item => typeof item === 'string' ? item : item.enum_property || '').filter(v => v)
        : [];
      setRowKeys(rowValues.length ? rowValues : ['defaultRow1', 'defaultRow2']);
      setColKeys(colValues.length ? colValues : ['defaultCol1', 'defaultCol2']);

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

  // ※ Vector2/Vector3/enum/bool/配列/classDataの各エディタは
  //    ClassDataIdDetailGrid.js から共有している SingleValueEditor /
  //    ArrayFieldEditor / ClassFieldEditor に統一（数値入力の不具合修正も含む）。

  const columns = useMemo(() => {
    return [
      {
        field: 'rowKey',
        headerName: 'Row Key',
        width: 150,
        // ★ 行ID(Row Key)は背景色を緑にして目立たせる
        cellClassName: 'matrix-row-id-cell',
      },
      ...colKeys.map(ck => ({
        field: ck,
        headerName: ck,
        width: 240,
        editable: !!data.fields.length,
        // ★ 単一行のテキストではなく、フィールド名/値を並べた
        //   見やすいミニテーブルとして表示する
        renderCell: (params) => {
          const value = params.value || {};
          if (data.fields.length === 0) {
            return <Typography variant="caption" color="text.disabled">空</Typography>;
          }
          return (
            <Box
              component="table"
              sx={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '0.75rem',
                lineHeight: 1.4,
                '& td': {
                  padding: '2px 6px',
                  borderBottom: '1px solid',
                  borderColor: 'divider',
                  verticalAlign: 'top',
                },
                '& tr:last-of-type td': { borderBottom: 'none' },
              }}
            >
              <tbody>
                {data.fields.map(f => {
                  const fieldValue = value[f.name] ?? getDefaultValue(f.type);
                  const preview = formatPreviewValue(fieldValue, f.type, classSchemas);
                  return (
                    <tr key={f.name}>
                      <td style={{ fontWeight: 600, color: '#666', whiteSpace: 'nowrap' }}>
                        {f.name}{f.description ? `（${f.description}）` : ''}
                      </td>
                      <td
                        title={preview}
                        style={{
                          wordBreak: 'break-word',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                        }}
                      >
                        {preview}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Box>
          );
        },
      }))
    ];
  }, [colKeys, data.fields, classSchemas]);

  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ p: 3, maxWidth: '1200px', margin: '0 auto' }}>
        <Typography variant="h5" gutterBottom sx={{ fontWeight: 500, color: 'text.primary', display: 'flex', alignItems: 'center', gap: 1 }}>
          {name}
          {currentTag && <Chip label={currentTag} size="small" color="primary" variant="outlined" />}
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
              // ★ ミニテーブルのプレビューが見切れないよう、行の高さをコンテンツに合わせる
              getRowHeight={() => 'auto'}
              sx={{
                '& .MuiDataGrid-main': {
                  borderRadius: '8px',
                  overflow: 'hidden',
                },
                '& .MuiDataGrid-cell': {
                  py: 0.5,
                  alignItems: 'flex-start',
                },
                // ★ 行ID(Row Key)列の背景色を緑にする
                '& .matrix-row-id-cell': {
                  backgroundColor: '#a5d6a7',
                  fontWeight: 600,
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
        <Dialog
          open={openCellEditor}
          onClose={() => setOpenCellEditor(false)}
          maxWidth="md"
          fullWidth
          sx={{ '& .MuiDialog-paper': { transition: 'opacity 0.2s ease' } }}
        >
          <DialogTitle sx={{ bgcolor: 'primary.main', color: 'white', fontWeight: 500 }}>
            セル編集 ({editingCell?.rowKey}, {editingCell?.colKey})
          </DialogTitle>
          <DialogContent sx={{ pt: 2, minHeight: 320 }}>
{data.fields.map(field => {
  // ★ "int[]" のような配列型・classData型（ネスト）にも対応
  const { isArray, baseType } = parseType(field.type);
  const value = cellValues[field.name] ?? getDefaultValue(field.type);

  return (
    <Box key={field.name} sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {field.name}{field.description ? `（${field.description}）` : ''} ({field.type})
      </Typography>
      {isArray ? (
        <ArrayFieldEditor
          value={Array.isArray(value) ? value : []}
          baseType={baseType}
          enumValues={enumValues}
          classSchemas={classSchemas}
          isDynamic={true}
          arraySize={-1}
          onChange={(val) => setCellValues({ ...cellValues, [field.name]: val })}
        />
      ) : (
        <SingleValueEditor
          value={value}
          type={baseType}
          enumValues={enumValues}
          classSchemas={classSchemas}
          onChange={(val) => setCellValues({ ...cellValues, [field.name]: val })}
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