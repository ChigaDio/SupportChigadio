import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid, useGridApiRef } from '@mui/x-data-grid';
import { Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, createTheme, ThemeProvider, InputAdornment, IconButton, Tooltip } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import SaveIcon from '@mui/icons-material/Save';
import DownloadIcon from '@mui/icons-material/Download';
import UploadIcon from '@mui/icons-material/Upload';
import CodeIcon from '@mui/icons-material/Code';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import SearchIcon from '@mui/icons-material/Search';
import ClearIcon from '@mui/icons-material/Clear';
import EditIcon from '@mui/icons-material/Edit';
import Chip from '@mui/material/Chip';
import Papa from 'papaparse';
import {
  parseType,
  getDefaultValueForType,
  SingleValueEditor,
  ArrayFieldEditor,
  ClassFieldEditor,
  formatPreviewValue,
  NumericOptionsEditor,
  BitOptionsEditor,
  ArrayOptionsEditor,
  DictionaryOptionsEditor,
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
  const [enumNames, setEnumNames] = useState([]);
  const [classDataIdNames, setClassDataIdNames] = useState([]);
  const [customClassDataIdNames, setCustomClassDataIdNames] = useState([]);
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
  const [newFieldOptions, setNewFieldOptions] = useState({});
  const [fieldToDelete, setFieldToDelete] = useState('');
  const [openImportCsv, setOpenImportCsv] = useState(false);
  const [openCellEditor, setOpenCellEditor] = useState(false);
  const [editingCell, setEditingCell] = useState(null);
  const [cellValues, setCellValues] = useState({});
  const apiRef = useGridApiRef();
  // ★ 追加: 行ID・列IDが多いと分かりにくいため、検索で絞り込めるようにする
  const [rowSearch, setRowSearch] = useState('');
  const [colSearch, setColSearch] = useState('');

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

  // ★ 追加: 行ID・列IDの検索絞り込み（Matrixは行×列の組み合わせが多くなりがちで
  //   見つけたいセルを探しづらいため、部分一致で絞り込めるようにする）
  const filteredRowKeys = useMemo(() => {
    const q = rowSearch.trim().toLowerCase();
    if (!q) return rowKeys;
    return rowKeys.filter(rk => rk.toLowerCase().includes(q));
  }, [rowKeys, rowSearch]);

  const filteredColKeys = useMemo(() => {
    const q = colSearch.trim().toLowerCase();
    if (!q) return colKeys;
    return colKeys.filter(ck => ck.toLowerCase().includes(q));
  }, [colKeys, colSearch]);

  // ★ 検索結果に応じて実際にグリッドへ渡す行を絞り込む（列は columns 側で絞り込む）
  const displayedRows = useMemo(() => {
    if (filteredRowKeys.length === rowKeys.length) return gridRows;
    const filteredSet = new Set(filteredRowKeys);
    return gridRows.filter(row => filteredSet.has(row.rowKey));
  }, [gridRows, filteredRowKeys, rowKeys.length]);

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
      fetch('/api/class-data-id').then(res => res.json()),
      fetch('/api/custom-class-data').then(res => res.ok ? res.json() : []),
      fetch('/api/custom-class-data-id').then(res => res.ok ? res.json() : [])
    ]).then(([enumList, classListData, classIdList, customClassList, customClassIdList]) => {
      const basicTypes = ['int', 'float', 'bool', 'string'];
      const unityTypes = ['Vector2', 'Vector3'];
      const customTypes = ['bit', 'color', 'bezier', 'dictionary'];
      const enumTypes = enumList.map(item => item.name);
      const classTypes = classListData.map(item => item.name);
      const classIdTypes = classIdList.map(item => item.name);
      const customClassTypes = (Array.isArray(customClassList) ? customClassList : []).map(item => item.name);
      const customClassIdTypes = (Array.isArray(customClassIdList) ? customClassIdList : []).map(item => item.name);

      // ★ classDataの一覧を保持（配列型判定・ネスト編集に使う）
      setClassList(classTypes);
      // ★ prefillオプション等のソース選択用に名前一覧を保持
      setEnumNames(enumTypes);
      setClassDataIdNames(classIdTypes);
      setCustomClassDataIdNames(customClassIdTypes);

      // ★ 配列型のオプションを追加（"int[]" のような表記で動的配列を選べるように）
      const allBaseTypes = [...basicTypes, ...unityTypes, ...customTypes, ...enumTypes, ...classTypes, ...classIdTypes, ...customClassTypes, ...customClassIdTypes];
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
      // ★ CustomClassDataID の行データ（キー一覧・bit参照元などに使う）
      const customClassIdPromises = customClassIdTypes.map(nm =>
        fetch(`/api/custom-class-data-id/${encodeURIComponent(nm)}`)
          .then(res => res.ok ? res.json() : { rows: [] })
          .catch(() => ({ rows: [] }))
          .then(d => ({
            [nm]: Array.isArray(d.rows) ? d.rows.map(r => r.enum_property || '').filter(v => v) : []
          }))
      );
      // ★ classDataスキーマの取得（ネスト編集・配列デフォルト値生成に使う）
      const classSchemaPromises = classTypes.map(className =>
        fetch(`/api/class-data/${encodeURIComponent(className)}`)
          .then(res => res.ok ? res.json() : [])
          .then(d => ({ [className]: Array.isArray(d) ? d : [] }))
          .catch(() => ({ [className]: [] }))
      );
      // ★ CustomClassDataのスキーマ（ネスト編集に使う。ClassDataと同じ形で classSchemas に統合する）
      const customClassSchemaPromises = customClassTypes.map(className =>
        fetch(`/api/custom-class-data/${encodeURIComponent(className)}`)
          .then(res => res.ok ? res.json() : [])
          .then(d => ({ [className]: Array.isArray(d) ? d : [] }))
          .catch(() => ({ [className]: [] }))
      );
      return Promise.all([
        Promise.all(enumPromises),
        Promise.all(classIdPromises),
        Promise.all(customClassIdPromises),
        Promise.all(classSchemaPromises),
        Promise.all(customClassSchemaPromises),
      ]);
    }).then(([enumResults, classIdResults, customClassIdResults, classSchemaResults, customClassSchemaResults]) => {
      const newEnumValues = Object.assign({}, ...enumResults, ...classIdResults, ...customClassIdResults);
      console.log('enumValues:', newEnumValues);
      setEnumValues(newEnumValues);
      const schemasMap = Object.assign({}, ...classSchemaResults, ...customClassSchemaResults);
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
    const newFields = [...data.fields, { type: newFieldType, name: newFieldName, description: newFieldDescription, options: newFieldOptions }];
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
    setNewFieldOptions({});
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

  // ★ 修正: ダブルクリック＋DataGridの「セル内編集モード（editable）」の併用が
  //   打鍵のたびに重くなり入力が詰まる原因だったため、editableは全廃止し、
  //   クリックでダイアログを開く方式に統一（ClassDataIdDetailGridと同じ考え方）。
  //   DataGridの編集モードには一切入らないので、キー入力はダイアログ内の
  //   入力欄だけが受け取るようになる。
  const handleCellClick = (rowKey, colKey) => {
    if (!data.fields.length) return;
    setEditingCell({ rowKey, colKey });
    setCellValues(data.data[rowKey]?.[colKey] || {});
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

  // ★ 修正: 全カラムをグリッド内編集(editable)ではなく専用ダイアログ編集に統一。
  //   （ClassDataIdDetailGridの修正と同じ理由。editable+セル内編集モードの併用が
  //     打鍵のたびに重くなり入力が詰まる原因だった）
  const columns = useMemo(() => {
    return [
      {
        field: 'rowKey',
        headerName: 'Row Key',
        width: 150,
        // ★ 行ID(Row Key)は背景色を緑にして目立たせる
        cellClassName: 'matrix-row-id-cell',
      },
      // ★ 検索ボックスで絞り込んだ列だけを表示する（列IDが多いときの見やすさ対策）
      ...filteredColKeys.map(ck => ({
        field: ck,
        headerName: ck,
        width: 240,
        editable: false,
        // ★ 単一行のテキストではなく、フィールド名/値を並べた
        //   見やすいミニテーブルとして表示する。クリックで編集ダイアログを開く。
        renderCell: (params) => {
          const value = params.value || {};
          if (data.fields.length === 0) {
            return <Typography variant="caption" color="text.disabled">空</Typography>;
          }
          return (
            <Box
              onClick={() => handleCellClick(params.row.rowKey, ck)}
              sx={{
                width: '100%',
                height: '100%',
                cursor: 'pointer',
                px: 0.5,
                py: 0.5,
                '&:hover': { bgcolor: 'action.hover' },
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.25 }}>
                <EditIcon fontSize="inherit" color="action" sx={{ fontSize: 12, flexShrink: 0 }} />
                <Typography variant="caption" color="text.disabled" sx={{ fontSize: 10 }}>クリックで編集</Typography>
              </Box>
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
                    const preview = formatPreviewValue(fieldValue, f.type, classSchemas, f.options);
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
            </Box>
          );
        },
      }))
    ];
  }, [filteredColKeys, data.fields, classSchemas]);

  // ============================================================
  // ★ 追加: 行の高さを「数値」で事前計算する。
  //   以前は getRowHeight={() => 'auto'} でDOM実測（autoモード）していたが、
  //   これはダイアログ内で1文字打つたびにDataGrid側の再計算コストが乗る
  //   原因のひとつだった（ClassDataIdDetailGridと同じ問題）。
  //   Matrixの各セルは「常に data.fields と同じ行数」のミニテーブルなので、
  //   フィールド数から高さは一意に決まる（内容量では変化しない：各項目は
  //   WebkitLineClamp:2で最大2行に固定しているため）。
  // ============================================================
  const MATRIX_FIELD_ROW_PX = 38; // フィールド1件あたりの高さ（2行クランプ＋余白＋罫線）
  const MATRIX_ROW_BASE_PX = 52;  // 最低の行高さ
  const MATRIX_ROW_EXTRA_PX = 34; // 「クリックで編集」ラベル分＋セルpadding

  const matrixRowHeight = useMemo(() => {
    const fieldCount = data.fields.length || 1;
    return Math.max(MATRIX_ROW_BASE_PX, fieldCount * MATRIX_FIELD_ROW_PX + MATRIX_ROW_EXTRA_PX);
  }, [data.fields.length]);

  const getMatrixRowHeight = useCallback(() => matrixRowHeight, [matrixRowHeight]);

  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ p: 3, maxWidth: '1600px', margin: '0 auto' }}>
        <Typography variant="h5" gutterBottom sx={{ fontWeight: 500, color: 'text.primary', display: 'flex', alignItems: 'center', gap: 1 }}>
          {name}
          {currentTag && <Chip label={currentTag} size="small" color="primary" variant="outlined" />}
        </Typography>
        <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>Row: {data.rowId}</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>Col: {data.colId}</Typography>
            {/* ★ 追加: 行ID・列IDが多いと目的のセルを探しづらいため検索ボックスを設置 */}
            <TextField
              size="small"
              placeholder="行IDを検索"
              value={rowSearch}
              onChange={(e) => setRowSearch(e.target.value)}
              sx={{ width: 160 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
                endAdornment: rowSearch && (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setRowSearch('')}>
                      <ClearIcon fontSize="small" />
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <TextField
              size="small"
              placeholder="列IDを検索"
              value={colSearch}
              onChange={(e) => setColSearch(e.target.value)}
              sx={{ width: 160 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
                endAdornment: colSearch && (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setColSearch('')}>
                      <ClearIcon fontSize="small" />
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <Tooltip title="検索に一致した行数 / 全行数">
              <Chip
                size="small"
                variant="outlined"
                label={`行 ${filteredRowKeys.length} / ${rowKeys.length}`}
              />
            </Tooltip>
            <Tooltip title="検索に一致した列数 / 全列数">
              <Chip
                size="small"
                variant="outlined"
                label={`列 ${filteredColKeys.length} / ${colKeys.length}`}
              />
            </Tooltip>
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
              rows={displayedRows}
              columns={columns}
              pageSizeOptions={[5, 10, 20]}
              getRowId={(row) => row.id}
              apiRef={apiRef}
              // ★ 修正: editable(セル内編集モード)は使わず、renderCell側のonClickで
              //   ダイアログを開く方式に統一したため editMode="cell" / onCellDoubleClick は不要。
              //   （editable + セル内編集モードの併用が打鍵のたびに重くなる原因だった）
              // ★ 修正: 'auto'（DOM実測）ではなく、フィールド数から事前計算した数値の
              //   行高さを返す。ダイアログ入力のたびに全行の高さ再計算が走らなくなる。
              getRowHeight={getMatrixRowHeight}
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
              onChange={(e, newValue) => { setNewFieldType(newValue || ''); setNewFieldOptions({}); }}
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
            {(() => {
              const isNumeric = ['int', 'uint', 'float', 'double'].includes(newFieldType);
              const isArray = newFieldType.endsWith('[]');
              if (!(isNumeric || isArray || newFieldType === 'bit' || newFieldType === 'dictionary')) return null;
              return (
                <Box sx={{ borderTop: '1px solid #eee', mt: 2, pt: 1 }}>
                  <Typography variant="subtitle2">型オプション</Typography>
                  {isNumeric && <NumericOptionsEditor options={newFieldOptions} onChange={setNewFieldOptions} />}
                  {isArray && (
                    <ArrayOptionsEditor
                      options={newFieldOptions}
                      onChange={setNewFieldOptions}
                      enumNames={enumNames}
                      classDataIdNames={classDataIdNames}
                      customClassDataIdNames={customClassDataIdNames}
                    />
                  )}
                  {newFieldType === 'bit' && (
                    <BitOptionsEditor
                      options={newFieldOptions}
                      onChange={setNewFieldOptions}
                      enumNames={enumNames}
                      classDataIdNames={classDataIdNames}
                      customClassDataIdNames={customClassDataIdNames}
                    />
                  )}
                  {newFieldType === 'dictionary' && (
                    <DictionaryOptionsEditor
                      options={newFieldOptions}
                      onChange={setNewFieldOptions}
                      keyTypeOptions={['int', ...enumNames, ...classDataIdNames, ...customClassDataIdNames]}
                      valueTypeOptions={typeOptions}
                      enumNames={enumNames}
                      classDataIdNames={classDataIdNames}
                      customClassDataIdNames={customClassDataIdNames}
                    />
                  )}
                </Box>
              );
            })()}
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
          options={field.options}
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
          options={field.options}
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