import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid, useGridApiRef } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent,
  DialogActions, Autocomplete, IconButton, Accordion, AccordionSummary,
  AccordionDetails, Chip, Select, MenuItem, FormControl, InputLabel,
  Switch, FormControlLabel
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Papa from 'papaparse';
import { useMemo } from 'react';

// ============================================================
// ユーティリティ
// ============================================================

/**
 * 型名から配列かどうかを判定し、要素型を返す
 * カラム型の "int[]" 表記対応（カラムレベルの配列型）
 */
function parseType(type) {
  if (typeof type === 'string' && type.endsWith('[]')) {
    return { isArray: true, isDynamic: true, arraySize: -1, baseType: type.slice(0, -2) };
  }
  return { isArray: false, isDynamic: false, arraySize: 0, baseType: type };
}

/**
 * classDataスキーマのフィールドから配列情報を取得
 * arraySize: -1 = 動的配列(List), >0 = 固定配列, 0 = 単一値
 */
function getFieldArrayInfo(field) {
  const arraySize = field.arraySize ?? 0;
  if (arraySize === -1) return { isArray: true, isDynamic: true, arraySize: -1 };
  if (arraySize > 0)   return { isArray: true, isDynamic: false, arraySize };
  return { isArray: false, isDynamic: false, arraySize: 0 };
}

/**
 * 型に応じたデフォルト値を返す（単一値用）
 */
function getDefaultValueForType(type, enumValues, classSchemas) {
  const lower = (type || '').toLowerCase();
  switch (lower) {
    case 'int':    return 0;
    case 'float':  return 0.0;
    case 'bool':   return false;
    case 'string': return '';
    case 'vector2': return [0, 0];
    case 'vector3': return [0, 0, 0];
    default:
      // classData型
      if (classSchemas && classSchemas[type]) {
        const schema = classSchemas[type];
        const obj = {};
        schema.forEach(field => {
          const { isArray, baseType } = parseType(field.type);
          obj[field.name] = isArray ? [] : getDefaultValueForType(baseType, enumValues, classSchemas);
        });
        return obj;
      }
      // enum / classDataID型
      return `${type}ID.None`;
  }
}

// ============================================================
// ArrayFieldEditor: 配列型の入力コンポーネント
// ============================================================
function ArrayFieldEditor({ value, baseType, enumValues, classSchemas, onChange, onSizeChange, readOnly, isDynamic, arraySize }) {
  const arr = Array.isArray(value) ? value : [];
  // isDynamic(arraySize=-1): 自由に追加削除可
  // arraySize>0: 固定長（追加削除ボタン非表示、長さ固定）
  const isFixed = !isDynamic && arraySize > 0;

  const handleAdd = () => {
    if (readOnly || isFixed) return;
    const newVal = getDefaultValueForType(baseType, enumValues, classSchemas);
    const next = [...arr, newVal];
    onChange(next);
    if (onSizeChange) onSizeChange();
  };

  const handleRemove = (index) => {
    if (readOnly || isFixed) return;
    const next = arr.filter((_, i) => i !== index);
    onChange(next);
    if (onSizeChange) onSizeChange();
  };

  const handleChange = (index, val) => {
    const next = [...arr];
    next[index] = val;
    onChange(next);
  };

  // 固定長の場合、表示する要素数を arraySize に合わせる
  const displayArr = isFixed
    ? Array.from({ length: arraySize }, (_, i) => arr[i] ?? getDefaultValueForType(baseType, enumValues, classSchemas))
    : arr;

  return (
    <Box sx={{ width: '100%' }}>
      {isFixed && (
        <Typography variant="caption" color="text.disabled" sx={{ mb: 0.5, display: 'block' }}>
          固定配列 [{arraySize}]
        </Typography>
      )}
      {!isFixed && isDynamic && (
        <Typography variant="caption" color="text.disabled" sx={{ mb: 0.5, display: 'block' }}>
          動的配列 (List) [{arr.length}件]
        </Typography>
      )}
      {displayArr.map((item, index) => (
        <Box key={index} sx={{ display: 'flex', alignItems: 'center', mb: 0.5, gap: 1 }}>
          <Typography variant="caption" sx={{ minWidth: 20, color: 'text.secondary' }}>[{index}]</Typography>
          <Box sx={{ flex: 1 }}>
            <SingleValueEditor
              value={item}
              type={baseType}
              enumValues={enumValues}
              classSchemas={classSchemas}
              onChange={(val) => handleChange(index, val)}
              onSizeChange={onSizeChange}
              readOnly={readOnly}
            />
          </Box>
          {!isFixed && (
            <IconButton size="small" color="error" disabled={readOnly} onClick={() => handleRemove(index)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          )}
        </Box>
      ))}
      {!isFixed && (
        <Button size="small" startIcon={<AddIcon />} onClick={handleAdd} disabled={readOnly} sx={{ mt: 0.5 }}>
          追加
        </Button>
      )}
    </Box>
  );
}

// ============================================================
// ClassFieldEditor: classData型のネスト入力コンポーネント（折り畳み対応）
// ============================================================
function ClassFieldEditor({ value, typeName, enumValues, classSchemas, onChange, onSizeChange, readOnly }) {
  const schema = classSchemas[typeName] || [];
  const obj = (value && typeof value === 'object' && !Array.isArray(value)) ? value : {};

  const handleFieldChange = (fieldName, fieldVal) => {
    onChange({ ...obj, [fieldName]: fieldVal });
  };

  return (
    <Accordion
      disableGutters
      sx={{ border: '1px solid', borderColor: 'divider', boxShadow: 'none' }}
      onChange={(_, expanded) => {
        // 開閉時に行高さ再計算を要求
        if (onSizeChange) onSizeChange();
      }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 32, '& .MuiAccordionSummary-content': { my: 0.5 } }}>
        <Typography variant="caption" color="text.secondary">
          {typeName} ▸ {schema.map(f => f.name).join(', ') || '（フィールドなし）'}
        </Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ p: 1 }}>
        {schema.length === 0 ? (
          <Typography variant="caption" color="text.disabled">スキーマが未定義です</Typography>
        ) : (
          schema.map(field => {
            // classDataスキーマは { name, type, arraySize, description }
            // arraySize: -1=動的配列, >0=固定配列, 0=単一値
            const { isDynamic, isArray: fieldIsArray, arraySize: fieldArraySize } = getFieldArrayInfo(field);
            const baseType = field.type; // arraySize管理なので型名はそのまま

            const defaultVal = fieldIsArray
              ? Array.from({ length: Math.max(fieldArraySize, 0) }, () => getDefaultValueForType(baseType, enumValues, classSchemas))
              : getDefaultValueForType(baseType, enumValues, classSchemas);
            const fieldValue = obj[field.name] !== undefined ? obj[field.name] : defaultVal;

            const arraySizeLabel = isDynamic ? 'List' : fieldArraySize > 0 ? `[${fieldArraySize}]` : '';

            return (
              <Box key={field.name} sx={{ mb: 1 }}>
                <Typography variant="caption" fontWeight="bold" display="block" sx={{ mb: 0.5 }}>
                  {field.name}
                  <Chip label={`${field.type}${arraySizeLabel}`} size="small" sx={{ ml: 0.5, height: 16, fontSize: 10 }} />
                </Typography>
                {fieldIsArray ? (
                  <ArrayFieldEditor
                    value={Array.isArray(fieldValue) ? fieldValue : []}
                    baseType={baseType}
                    enumValues={enumValues}
                    classSchemas={classSchemas}
                    isDynamic={isDynamic}
                    arraySize={fieldArraySize}
                    onChange={(val) => { handleFieldChange(field.name, val); if (onSizeChange) onSizeChange(); }}
                    onSizeChange={onSizeChange}
                    readOnly={readOnly}
                  />
                ) : (
                  <SingleValueEditor
                    value={fieldValue}
                    type={baseType}
                    enumValues={enumValues}
                    classSchemas={classSchemas}
                    onChange={(val) => handleFieldChange(field.name, val)}
                    onSizeChange={onSizeChange}
                    readOnly={readOnly}
                  />
                )}
              </Box>
            );
          })
        )}
      </AccordionDetails>
    </Accordion>
  );
}

// ============================================================
// SingleValueEditor: 単一値の入力（型に応じて切り替え）
// ============================================================
function SingleValueEditor({ value, type, enumValues, classSchemas, onChange, onSizeChange, readOnly }) {
  const lower = (type || '').toLowerCase();

  // bool
  if (lower === 'bool') {
    return (
      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={!!value}
            disabled={readOnly}
            onChange={(e) => !readOnly && onChange(e.target.checked)}
          />
        }
        label={value ? 'true' : 'false'}
      />
    );
  }

  // int
  if (lower === 'int') {
    return (
      <TextField
        size="small"
        type="number"
        value={value ?? 0}
        onChange={(e) => !readOnly && onChange(parseInt(e.target.value, 10) || 0)}
        inputProps={{ step: 1, readOnly }}
        fullWidth
      />
    );
  }

  // float
  if (lower === 'float') {
    return (
      <TextField
        size="small"
        type="number"
        value={value ?? 0}
        onChange={(e) => !readOnly && onChange(parseFloat(e.target.value) || 0.0)}
        inputProps={{ step: 0.01, readOnly }}
        fullWidth
      />
    );
  }

  // string
  if (lower === 'string') {
    return (
      <TextField
        size="small"
        value={value ?? ''}
        onChange={(e) => !readOnly && onChange(e.target.value)}
        inputProps={{ readOnly }}
        fullWidth
        multiline
        minRows={1}
        onKeyDown={(e) => {
          // Shift+Enter または Enter で改行を挿入（DataGridのEnterによる確定を防ぐ）
          if (e.key === 'Enter') {
            e.stopPropagation(); // DataGridへのEnterキーイベント伝播を止める
            if (!readOnly) {
              const el = e.target;
              const start = el.selectionStart;
              const end = el.selectionEnd;
              const newVal = (value ?? '').substring(0, start) + '\n' + (value ?? '').substring(end);
              onChange(newVal);
              // カーソル位置を改行の後に移動
              requestAnimationFrame(() => {
                el.selectionStart = el.selectionEnd = start + 1;
              });
            }
          }
        }}
        sx={{
          '& .MuiInputBase-root': { alignItems: 'flex-start' },
        }}
      />
    );
  }

  // vector2
  if (lower === 'vector2') {
    const arr = Array.isArray(value) && value.length === 2 ? value : [0, 0];
    return (
      <Box sx={{ display: 'flex', gap: 0.5 }}>
        {['x', 'y'].map((label, i) => (
          <TextField
            key={label}
            size="small"
            type="number"
            label={label}
            value={arr[i] ?? 0}
            onChange={(e) => {
              if (readOnly) return;
              const next = [...arr];
              next[i] = parseFloat(e.target.value) || 0;
              onChange(next);
            }}
            inputProps={{ readOnly }}
            sx={{ flex: 1 }}
          />
        ))}
      </Box>
    );
  }

  // vector3
  if (lower === 'vector3') {
    const arr = Array.isArray(value) && value.length === 3 ? value : [0, 0, 0];
    return (
      <Box sx={{ display: 'flex', gap: 0.5 }}>
        {['x', 'y', 'z'].map((label, i) => (
          <TextField
            key={label}
            size="small"
            type="number"
            label={label}
            value={arr[i] ?? 0}
            onChange={(e) => {
              if (readOnly) return;
              const next = [...arr];
              next[i] = parseFloat(e.target.value) || 0;
              onChange(next);
            }}
            inputProps={{ readOnly }}
            sx={{ flex: 1 }}
          />
        ))}
      </Box>
    );
  }

  // classData型（ネスト）
  if (classSchemas && classSchemas[type]) {
    return (
      <ClassFieldEditor
        value={value}
        typeName={type}
        enumValues={enumValues}
        classSchemas={classSchemas}
        onChange={onChange}
        onSizeChange={onSizeChange}
        readOnly={readOnly}
      />
    );
  }

  // enum / classDataID型（セレクトボックス）
  if (enumValues && enumValues[type]) {
    const options = [
      { value: `${type}ID.None`, label: 'None' },
      ...enumValues[type].map(v => {
        const key = v['property'] || v['enum_property'] || v;
        return { value: `${type}ID.${key}`, label: key };
      })
    ];
    return (
      <FormControl size="small" fullWidth>
        <Select
          value={value ?? `${type}ID.None`}
          onChange={(e) => !readOnly && onChange(e.target.value)}
          inputProps={{ readOnly }}
        >
          {options.map(opt => (
            <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
          ))}
        </Select>
      </FormControl>
    );
  }

  // フォールバック
  return (
    <TextField
      size="small"
      value={value ?? ''}
      onChange={(e) => !readOnly && onChange(e.target.value)}
      inputProps={{ readOnly }}
      fullWidth
    />
  );
}

// ============================================================
// CellEditor: DataGridのrenderEditCellで使うセル編集コンポーネント
// ============================================================
function CellEditor({ params, type, enumValues, classSchemas, apiRef }) {
  const { isArray, baseType } = parseType(type);
  const value = params.value;

  const handleChange = useCallback((newVal) => {
    apiRef.current.setEditCellValue({ id: params.id, field: params.field, value: newVal });
  }, [params.id, params.field, apiRef]);

  // Accordion開閉やリスト変化時に行高さを再計算させる
  const handleSizeChange = useCallback(() => {
    // unstable_rowSpanningEnabled使用時は不要だが、通常はこれで行高さ更新をトリガー
    if (apiRef.current?.resetRowHeights) {
      apiRef.current.resetRowHeights();
    }
  }, [apiRef]);

  if (isArray) {
    return (
      <Box sx={{ p: 1, width: '100%', bgcolor: 'background.paper' }} onChange={handleSizeChange}>
        <ArrayFieldEditor
          value={Array.isArray(value) ? value : []}
          baseType={baseType}
          isDynamic={true}
          arraySize={-1}
          enumValues={enumValues}
          classSchemas={classSchemas}
          onChange={(val) => { handleChange(val); handleSizeChange(); }}
          onSizeChange={handleSizeChange}
        />
      </Box>
    );
  }

  if (classSchemas && classSchemas[type]) {
    return (
      <Box sx={{ p: 1, width: '100%', bgcolor: 'background.paper' }}>
        <ClassFieldEditor
          value={value}
          typeName={type}
          enumValues={enumValues}
          classSchemas={classSchemas}
          onChange={handleChange}
          onSizeChange={handleSizeChange}
        />
      </Box>
    );
  }

  return null; // 通常型はDataGridのデフォルトを使う
}

// ============================================================
// メインコンポーネント
// ============================================================
function ClassDataIdDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState({ columns: [], rows: [] });
  const [typeOptions, setTypeOptions] = useState([]);
  const [enumValues, setEnumValues] = useState({});
  // ★ 追加: classDataのスキーマを保持
  const [classSchemas, setClassSchemas] = useState({});
  // ★ 追加: classData型の名前リスト（配列型対応のため別管理）
  const [classList, setClassList] = useState([]);
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

  // ============================================================
  // getDefaultValue: stateを参照するのでコンポーネント内に定義
  // ============================================================
  const getDefaultValue = useCallback((type) => {
    const { isArray, baseType } = parseType(type);
    if (isArray) return [];
    return getDefaultValueForType(baseType, enumValues, classSchemas);
  }, [enumValues, classSchemas]);

  // ============================================================
  // gridRows: DataGrid用フラット化
  // ============================================================
  const gridRows = useMemo(() => {
    return data.rows.map((row) => {
      const rowData = {
        id: row.id,
        enum_property: row.enum_property,
        description: row.description,
      };
      data.columns.forEach((col) => {
        rowData[col.name] = row.data?.[col.name]?.value ?? getDefaultValueForType(col.type, enumValues, classSchemas);
      });
      return rowData;
    });
  }, [data.rows, data.columns, enumValues, classSchemas]);

  // ============================================================
  // useEffect: データ取得
  // ============================================================
  useEffect(() => {
    if (!name || name.includes(':')) {
      alert('不正なClassDataID名です');
      navigate('/class-data-id');
      return;
    }

    setLoading(true);

    // メインデータ取得
    fetch(`/api/class-data-id/${encodeURIComponent(name)}`)
      .then(response => {
        if (!response.ok) throw new Error(`データ取得に失敗しました: ${name} (${response.status} ${response.statusText})`);
        const ct = response.headers.get('content-type');
        if (!ct || !ct.includes('application/json')) throw new Error('サーバーからJSON以外のレスポンスを受信しました');
        return response.json();
      })
      .then(fetchedData => {
        const columns = fetchedData.columns || [];
        const rows = (fetchedData.rows || []).map((row, index) => ({
          id: row.id || index + 1,
          enum_property: row.enum_property || `Row${index + 1}`,
          description: row.description || '',
          data: row.data || {},
        }));
        // 各セルのdefault補完はclassSchemas取得後に行うため、ここでは保存だけ
        setData({ columns, rows });
        setLoading(false);
      })
      .catch(error => {
        console.error('データ取得エラー:', error);
        alert('データ取得エラー: ' + error.message);
        setLoading(false);
        navigate('/class-data-id');
      });

    // 型リスト・enum・classSchema取得
    Promise.all([
      fetch('/api/enum-id').then(r => r.json()),
      fetch('/api/class-data').then(r => r.json()),
      fetch('/api/class-data-id').then(r => r.json()),
    ]).then(([enumList, classListData, classIdList]) => {
      const basicTypes = ['int', 'float', 'bool', 'string'];
      const unityTypes = ['Vector2', 'Vector3'];
      const enumTypes = enumList.map(item => item.name);
      const classNames = classListData.map(item => item.name);
      const classIdTypes = classIdList.map(item => item.name);

      // ★ classListを保存（配列型の判定に使う）
      setClassList(classNames);

      // 配列型のオプションを追加
      const arrayTypes = [
        ...basicTypes,
        ...unityTypes,
        ...enumTypes,
        ...classNames,
        ...classIdTypes,
      ].map(t => `${t}[]`);

      setTypeOptions([
        ...basicTypes, ...unityTypes, ...enumTypes, ...classNames, ...classIdTypes,
        ...arrayTypes,
      ]);

      // enum値の取得
      const enumPromises = enumList.map(enumItem =>
        fetch(`/api/enum/${encodeURIComponent(enumItem.name)}`)
          .then(res => res.ok ? res.json() : [])
          .then(d => ({ [enumItem.name]: d || [] }))
      );

      // classDataID値の取得
      const classIdPromises = classIdList.map(classIdItem =>
        fetch(`/api/class-data-id/${encodeURIComponent(classIdItem.name)}`)
          .then(res => res.ok ? res.json() : { rows: [] })
          .then(d => ({ [classIdItem.name]: (d.rows || []).map(row => row.enum_property) }))
      );

      // ★ classDataスキーマの取得（/api/class-data/{name} → [{name, type}, ...]）
      const classSchemaPromises = classNames.map(className =>
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
      const enumValuesMap = Object.assign({}, ...enumResults, ...classIdResults);
      setEnumValues(enumValuesMap);

      const schemasMap = Object.assign({}, ...classSchemaResults);
      setClassSchemas(schemasMap);
    }).catch(error => {
      console.error('型オプションまたはenum値の取得エラー:', error);
      alert('型オプション取得エラー: ' + error.message);
    });
  }, [name, navigate]);

  // ============================================================
  // ハンドラ
  // ============================================================
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
        values.push(`"${String(value).replace(/"/g, '""')}"`);
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

  const parseImportedValue = (value, type) => {
    const { isArray, baseType } = parseType(type);
    if (value === undefined || value === '') return getDefaultValue(type);
    if (isArray) {
      try { const p = JSON.parse(value); return Array.isArray(p) ? p : []; }
      catch { return []; }
    }
    const lower = baseType.toLowerCase();
    switch (lower) {
      case 'int':    return parseInt(value, 10) || 0;
      case 'float':  return parseFloat(value) || 0.0;
      case 'bool':   return value.toLowerCase() === 'true' || value === '1';
      case 'string': return value;
      case 'vector2':
        try { const p = JSON.parse(value); return Array.isArray(p) && p.length === 2 ? p : [0, 0]; }
        catch { return [0, 0]; }
      case 'vector3':
        try { const p = JSON.parse(value); return Array.isArray(p) && p.length === 3 ? p : [0, 0, 0]; }
        catch { return [0, 0, 0]; }
      default:
        if (classSchemas[baseType]) {
          try { return JSON.parse(value); }
          catch { return getDefaultValue(type); }
        }
        return value;
    }
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
            const parsedValue = parseImportedValue(importedRow[col.name], col.type);
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
      error: (error) => alert('CSVインポートエラー: ' + error.message),
    });
  };

  // ============================================================
  // columns定義
  // ============================================================
  const columns = [
    { field: 'enum_property', headerName: 'Enum Property', width: 150, editable: true },
    { field: 'description', headerName: '説明', width: 200, editable: true },
    {
      field: 'actions',
      headerName: '操作',
      width: 100,
      renderCell: (params) => (
        <IconButton color="error" size="small" onClick={() => handleDeleteRow(params.row.id)}>
          <DeleteIcon />
        </IconButton>
      ),
    },
    ...data.columns.map(col => {
      const { isArray, baseType } = parseType(col.type);
      const isBool    = !isArray && baseType.toLowerCase() === 'bool';
      const isEnum    = !isArray && baseType in enumValues;
      const isNumber  = !isArray && (baseType.toLowerCase() === 'int' || baseType.toLowerCase() === 'float');
      const isVector  = !isArray && (baseType.toLowerCase() === 'vector2' || baseType.toLowerCase() === 'vector3');
      const isString  = !isArray && baseType.toLowerCase() === 'string';
      // ★ classData型かどうか
      const isClass   = !isArray && classList.includes(baseType);
      // ★ 配列型・classData型はカスタムエディタが必要
      const needsCustomEditor = isArray || isClass;

      return {
        field: col.name,
        headerName: col.name,
        // ★ classData型・配列型はwidthを広めに
        width: needsCustomEditor ? 280 : 150,
        editable: true,
        headerAlign: 'right',
        renderHeader: () => (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
            <span>{col.name}</span>
            {/* ★ 型ラベル表示 */}
            <Chip label={col.type} size="small" sx={{ mx: 0.5, height: 16, fontSize: 10 }} />
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

        // ★ 型に応じてDataGridのtype属性を設定
        type: needsCustomEditor
          ? 'string' // カスタムエディタを使う場合はstringとして扱う（valueFormatterで表示）
          : isNumber ? 'number'
          : isBool   ? 'boolean'
          : isString ? 'string'
          : isVector ? 'string'
          : 'singleSelect',

        // ★ singleSelectの選択肢（enum/classDataID型）
        ...(isEnum && !needsCustomEditor ? {
          valueOptions: [
            { value: `${col.type}ID.None`, label: 'None' },
            ...enumValues[col.type].map(v => {
              const key = v['property'] || v['enum_property'] || v;
              return { value: `${col.type}ID.${key}`, label: key };
            })
          ]
        } : isBool ? {
          valueOptions: [
            { value: true, label: 'true' },
            { value: false, label: 'false' }
          ]
        } : {}),

        // ★ 表示用フォーマッタ（classData型・配列型はJSONで表示）
        // MUI DataGrid v7以降は引数がオブジェクトではなく value 直接渡し
        valueFormatter: (value) => {
          if (value === null || value === undefined) return '';
          if (Array.isArray(value)) return `[${value.length}件] ${JSON.stringify(value)}`;
          if (typeof value === 'object') return JSON.stringify(value);
          return value;
        },

        // ★ valueParser（通常型のみ、カスタムエディタはprocessRowUpdateで処理）
        ...(!needsCustomEditor ? {
          valueParser: (value) => {
            try {
              const lower = baseType.toLowerCase();
              switch (lower) {
                case 'int':
                  return isNaN(parseInt(value)) ? 0 : parseInt(value);
                case 'float':
                  return isNaN(parseFloat(value)) ? 0.0 : parseFloat(value);
                case 'bool':
                  return value === 'true' || value === true || value === '1';
                case 'string':
                  return value != null ? String(value) : '';
                case 'vector2': {
                  const p = value ? [value[0], value[1]] : [0, 0];
                  if (!Array.isArray(p) || p.length !== 2) throw new Error('不正なVector2形式');
                  return p;
                }
                case 'vector3': {
                  const p = value ? [value[0], value[1], value[2]] : [0, 0, 0];
                  if (!Array.isArray(p) || p.length !== 3) throw new Error('不正なVector3形式');
                  return p;
                }
                default:
                  if (isEnum) {
                    const validValues = [
                      `${col.type}ID.None`,
                      ...enumValues[col.type].map(v => {
                        const key = v['property'] || v['enum_property'] || v;
                        return `${col.type}ID.${key}`;
                      })
                    ];
                    return validValues.includes(value) ? value : `${col.type}ID.None`;
                  }
                  return value ?? '';
              }
            } catch (e) {
              console.error(`valueParser error for ${col.name}:`, e);
              return getDefaultValue(col.type);
            }
          }
        } : {}),

        // ★ 全型共通: viewモードは表示専用（onChangeなし＝再レンダリングを起こさない）
        renderCell: (params) => (
          <Box sx={{ width: '100%', py: 0.5, px: 0.5 }}>
            <SingleValueEditor
              value={params.value}
              type={col.type}
              enumValues={enumValues}
              classSchemas={classSchemas}
              readOnly
              onChange={() => {}}
            />
          </Box>
        ),

        // ★ 全型共通: 編集モードは readOnly なし（実際に編集できる）
        renderEditCell: (params) => {
          if (needsCustomEditor) {
            // classData型・配列型はCellEditorを使う（readOnlyなし）
            return (
              <CellEditor
                params={params}
                type={col.type}
                enumValues={enumValues}
                classSchemas={classSchemas}
                apiRef={apiRef}
              />
            );
          }
          // それ以外（int/float/string/bool/enum等）は SingleValueEditor で編集、選択即確定
          return (
            <Box sx={{ width: '100%', py: 0.5, px: 0.5, bgcolor: 'background.paper' }}>
              <SingleValueEditor
                value={params.value}
                type={col.type}
                enumValues={enumValues}
                classSchemas={classSchemas}
                onChange={(newVal) => {
                  apiRef.current.setEditCellValue({ id: params.id, field: params.field, value: newVal });
                  // string型は文字入力中なので即確定しない
                  // enum/bool/number は選択・変更後に確定する
                  if (!isString) {
                    setTimeout(() => {
                      try {
                        apiRef.current.stopCellEditMode({ id: params.id, field: params.field, ignoreModifications: false });
                      } catch (e) {}
                    }, 0);
                  }
                }}
              />
            </Box>
          );
        },
      };
    }),
  ];

  // ============================================================
  // レンダリング
  // ============================================================
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
        <div style={{ width: '100%' }}>
          <DataGrid
            rows={gridRows}
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
            // ★ 行高さをコンテンツに合わせて自動調整
            getRowHeight={() => 'auto'}
            // ★ autoの場合の最低高さ確保
            rowHeight={52}
            sx={{
              // auto行高さ時にセル内のpaddingを確保
              '& .MuiDataGrid-cell': { py: 1, alignItems: 'flex-start' },
            }}
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
              // string型のセルはEnterキーで改行するため、enterKeyDownでは確定しない
              const col = data.columns.find(c => c.name === params.field);
              const isStringField = col && col.type.toLowerCase() === 'string';
              // enum_property / description も string扱い
              const isBuiltinStringField = params.field === 'enum_property' || params.field === 'description';
              if (params.reason === 'enterKeyDown' && (isStringField || isBuiltinStringField)) {
                if (event) event.defaultMuiPrevented = true;
                return; // Enterキーでは確定しない（セル内改行に使うため）
              }
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

      {/* カラム追加ダイアログ */}
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

      {/* レコード追加ダイアログ */}
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

      {/* カラム削除ダイアログ */}
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

      {/* CSVインポートダイアログ */}
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