import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  TextField,
  Checkbox,
  Autocomplete,
  FormControlLabel,
  Typography,
  CircularProgress,
  IconButton,
  Paper,
  Chip,
  Tooltip,
  Divider
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import DragHandleIcon from '@mui/icons-material/DragHandle';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';

// Vector のラベル定義
const VECTOR_AXIS_LABELS = {
  vector2: ['X', 'Y'],
  vector3: ['X', 'Y', 'Z'],
  vector4: ['X', 'Y', 'Z', 'W'],
};

// 数値入力コンポーネント（マイナス・小数点対応、文字列で管理）
const NumericInput = ({ label, value, onChange, isFloat = false, sx = {} }) => {
  const [inputStr, setInputStr] = useState(String(value ?? 0));

  useEffect(() => {
    // 外部からの値変化に追従（ただし入力中は上書きしない）
    const parsed = isFloat ? parseFloat(inputStr) : parseInt(inputStr, 10);
    if (!isNaN(parsed) && parsed !== value) {
      setInputStr(String(value ?? 0));
    }
  }, [value]);

  const handleChange = (e) => {
    const raw = e.target.value;
    // 途中入力として許可するパターン: "-", "-.", ".", "-.0", "0.", etc.
    const allowPattern = isFloat ? /^-?(\d*\.?\d*)?$/ : /^-?\d*$/;
    if (!allowPattern.test(raw)) return;
    setInputStr(raw);
    const parsed = isFloat ? parseFloat(raw) : parseInt(raw, 10);
    if (!isNaN(parsed)) {
      onChange(parsed);
    } else if (raw === '' || raw === '-') {
      onChange(0);
    }
  };

  const handleBlur = () => {
    // フォーカスを外れたとき、空や単なる"-"なら0に正規化
    const parsed = isFloat ? parseFloat(inputStr) : parseInt(inputStr, 10);
    if (isNaN(parsed) || inputStr === '-') {
      setInputStr('0');
      onChange(0);
    } else {
      setInputStr(String(parsed));
      onChange(parsed);
    }
  };

  return (
    <TextField
      label={label}
      value={inputStr}
      onChange={handleChange}
      onBlur={handleBlur}
      inputProps={{ inputMode: isFloat ? 'decimal' : 'numeric' }}
      sx={sx}
    />
  );
};

const BaseRoleInputForm = ({ schema, initialData, onChange }) => {
  const [formData, setFormData] = useState(initialData || []);
  const [enumValues, setEnumValues] = useState({});
  const [classDataSchemas, setClassDataSchemas] = useState({});
  const [isLoading, setIsLoading] = useState(true);

  const getDefaultValue = useCallback((type, arraySize) => {
    const baseDefault = () => {
      switch (type.toLowerCase()) {
        case 'int': case 'short': case 'long': case 'byte': return 0;
        case 'float': case 'double': case 'decimal': return 0.0;
        case 'char': return '';
        case 'bool': return false;
        case 'string': return '';
        case 'vector2': return [0, 0];
        case 'vector3': return [0, 0, 0];
        case 'vector4': return [0, 0, 0, 0];
        default:
          if (type in enumValues && enumValues[type].length > 0) return `${type}ID.None`;
          if (type in classDataSchemas && classDataSchemas[type].length > 0) return `${type}ID.None`;
          return '';
      }
    };
    if (arraySize === undefined || arraySize === 0) return baseDefault();
    if (arraySize > 0) return Array.from({ length: arraySize }, () => baseDefault());
    if (arraySize === -1) return [];
    return baseDefault();
  }, [enumValues, classDataSchemas]);

  useEffect(() => {
    if (!isLoading) {
      const formattedData = schema.fields.map(field => {
        const initialItem = (initialData || []).find(d => d.name === field.name);
        return {
          name: field.name,
          value: initialItem ? initialItem.value : getDefaultValue(field.type, field.arraySize),
          arraySize: field.arraySize !== undefined ? field.arraySize : 0
        };
      });
      setFormData(formattedData);
      onChange(formattedData);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialData, schema, isLoading]);

  useEffect(() => {
    setIsLoading(true);
    const collectTypes = (fields) => {
      const types = new Set();
      fields.forEach(field => {
        types.add(field.type);
        if (field.subFields) collectTypes(field.subFields).forEach(t => types.add(t));
      });
      return types;
    };
    const types = [...collectTypes(schema.fields)];

    const loadData = async () => {
      try {
        const [enumListRes, classIdListRes, classDataListRes] = await Promise.all([
          fetch('/api/enum-id'),
          fetch('/api/class-data-id'),
          fetch('/api/class-data')
        ]);
        const enumList = enumListRes.ok ? await enumListRes.json() : [];
        const classIdList = classIdListRes.ok ? await classIdListRes.json() : [];
        const classDataList = classDataListRes.ok ? await classDataListRes.json() : [];

        const enumPromises = enumList
          .filter(e => types.includes(e.name))
          .map(async e => {
            const res = await fetch(`/api/enum/${encodeURIComponent(e.name)}`);
            const data = res.ok ? await res.json() : [];
            return { [e.name]: data || [] };
          });

        const classIdPromises = classIdList
          .filter(c => types.includes(c.name))
          .map(async c => {
            const res = await fetch(`/api/class-data-id/${encodeURIComponent(c.name)}`);
            const data = res.ok ? await res.json() : { rows: [] };
            return { [c.name]: (data.rows || []).map(r => r.enum_property) };
          });

        const classDataPromises = classDataList
          .filter(c => types.includes(c.name))
          .map(async c => {
            const res = await fetch(`/api/class-data/${encodeURIComponent(c.name)}`);
            const data = res.ok ? await res.json() : [];
            return { [c.name]: data || [] };
          });

        const results = await Promise.all([...enumPromises, ...classIdPromises, ...classDataPromises]);
        const valuesMap = results.reduce((acc, curr) => ({ ...acc, ...curr }), {});

        const enumMap = {};
        const classDataMap = {};
        Object.keys(valuesMap).forEach(key => {
          if (classDataList.some(item => item.name === key)) {
            classDataMap[key] = valuesMap[key];
          } else {
            enumMap[key] = valuesMap[key];
          }
        });

        setEnumValues(prev => ({ ...prev, ...enumMap }));
        setClassDataSchemas(prev => ({ ...prev, ...classDataMap }));
      } catch (error) {
        console.error('型オプション取得エラー:', error);
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(schema.fields)]);

  const handleChange = (name, value, arraySize) => {
    setFormData(prev => {
      const newData = prev.map(item =>
        item.name === name ? { ...item, value, arraySize: arraySize !== undefined ? arraySize : item.arraySize } : item
      );
      onChange(newData);
      return newData;
    });
  };

  const renderField = (field, parentPath = '', indexPath = []) => {
    const key = parentPath ? `${parentPath}.${field.name}` : field.name;
    let currentValue = formData.find(d => d.name === (parentPath || field.name))?.value;
    indexPath.forEach(idx => { currentValue = currentValue ? currentValue[idx] : undefined; });
    if (currentValue === undefined) currentValue = getDefaultValue(field.type, field.arraySize);

    if (field.warning) {
      return <Box key={key} sx={{ color: 'error.main', p: 1, bgcolor: 'error.50', borderRadius: 1 }}>{field.warning}</Box>;
    }

    if (isLoading) {
      return (
        <Box key={key} sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 1 }}>
          <CircularProgress size={16} />
          <Typography variant="caption" color="text.secondary">Loading...</Typography>
        </Box>
      );
    }

    const renderSingle = (value, onValueChange) => {
      // Enum
      if (enumValues[field.type] && enumValues[field.type].length > 0) {
        const options = [
          { value: `${field.type}ID.None`, label: 'None' },
          ...enumValues[field.type].map(v => {
            const val = typeof v === 'object' ? (v.property || v.enum_property || v) : v;
            return { value: `${field.type}ID.${val}`, label: val };
          })
        ];
        return (
          <Autocomplete
            key={key}
            options={options}
            getOptionLabel={(option) => option.label}
            value={options.find(opt => opt.value === value) || null}
            onChange={(e, newValue) => onValueChange(newValue ? newValue.value : `${field.type}ID.None`)}
            renderInput={params => (
              <TextField {...params} label={field.label || field.name} size="small" />
            )}
            fullWidth
            isOptionEqualToValue={(option, val) => option.value === val?.value}
          />
        );
      }

      // ClassData (nested)
      if (classDataSchemas[field.type] && classDataSchemas[field.type].length > 0) {
        const subSchema = {
          fields: classDataSchemas[field.type].map(sub => ({
            ...sub,
            label: sub.label || sub.name,
            arraySize: sub.arraySize !== undefined ? sub.arraySize : 0,
          })),
        };
        const subInitialData = Object.entries(value || {}).map(([n, v]) => ({
          name: n, value: v,
          arraySize: subSchema.fields.find(f => f.name === n)?.arraySize || 0,
        }));
        return (
          <Paper key={key} variant="outlined" sx={{ p: 1.5, mb: 1, bgcolor: 'grey.50' }}>
            <Typography variant="caption" fontWeight="bold" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
              {field.label || field.name} <Chip label="Class" size="small" sx={{ ml: 0.5, height: 16, fontSize: '0.6rem' }} />
            </Typography>
            <BaseRoleInputForm
              schema={subSchema}
              initialData={subInitialData}
              onChange={(subData) => {
                const newObj = subData.reduce((acc, { name, value }) => { acc[name] = value; return acc; }, {});
                onValueChange(newObj);
              }}
            />
          </Paper>
        );
      }

      const typeLower = field.type.toLowerCase();

      // String / Char
      if (typeLower === 'string' || typeLower === 'char') {
        return (
          <TextField
            key={key}
            label={field.label || field.name}
            value={value ?? ''}
            onChange={e => onValueChange(e.target.value)}
            fullWidth
            size="small"
          />
        );
      }

      // Integer types
      if (['int', 'short', 'long', 'byte'].includes(typeLower)) {
        return (
          <NumericInput
            key={key}
            label={field.label || field.name}
            value={value ?? 0}
            onChange={onValueChange}
            isFloat={false}
            sx={{ width: '100%' }}
          />
        );
      }

      // Float types
      if (['float', 'double', 'decimal'].includes(typeLower)) {
        return (
          <NumericInput
            key={key}
            label={field.label || field.name}
            value={value ?? 0}
            onChange={onValueChange}
            isFloat={true}
            sx={{ width: '100%' }}
          />
        );
      }

      // Bool
      if (typeLower === 'bool') {
        return (
          <FormControlLabel
            key={key}
            control={
              <Checkbox
                checked={value === true || value === 'true'}
                onChange={e => onValueChange(e.target.checked)}
                size="small"
              />
            }
            label={
              <Typography variant="body2">{field.label || field.name}</Typography>
            }
          />
        );
      }

      // Vector2 / Vector3 / Vector4 → 変数名.X, 変数名.Y, ...
      if (typeLower === 'vector2' || typeLower === 'vector3' || typeLower === 'vector4') {
        const axisLabels = VECTOR_AXIS_LABELS[typeLower];
        const dim = axisLabels.length;
        const varName = field.label || field.name;
        return (
          <Box key={key} sx={{ mb: 1 }}>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
              {varName}
            </Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              {axisLabels.map((axis, i) => (
                <NumericInput
                  key={`${key}.${axis}`}
                  label={`${varName}.${axis}`}
                  value={Array.isArray(value) ? (value[i] ?? 0) : 0}
                  onChange={(newVal) => {
                    const newArr = Array.isArray(value) ? [...value] : Array(dim).fill(0);
                    newArr[i] = newVal;
                    onValueChange(newArr);
                  }}
                  isFloat={true}
                  sx={{ flex: 1 }}
                />
              ))}
            </Box>
          </Box>
        );
      }

      // Default fallback
      return (
        <TextField
          key={key}
          label={field.label || field.name}
          value={value ?? ''}
          onChange={e => onValueChange(e.target.value)}
          fullWidth
          size="small"
        />
      );
    };

    const arraySize = field.arraySize !== undefined ? field.arraySize : 0;

    // Non-array
    if (arraySize === 0) {
      return (
        <Box key={key} sx={{ mb: 1.5 }}>
          {renderSingle(currentValue, newValue => handleChange(field.name, newValue, arraySize))}
        </Box>
      );
    }

    // Array (fixed or dynamic)
    const isDynamic = arraySize === -1;
    const fixedLength = isDynamic ? undefined : arraySize;
    let arrayValue = Array.isArray(currentValue)
      ? currentValue
      : isDynamic
        ? []
        : Array.from({ length: fixedLength }, () => getDefaultValue(field.type, 0));

    const handleArrayChange = (newArray) => handleChange(field.name, newArray, arraySize);
    const addItem = () => { if (isDynamic) handleArrayChange([...arrayValue, getDefaultValue(field.type, 0)]); };
    const removeItem = (index) => { if (isDynamic) handleArrayChange(arrayValue.filter((_, i) => i !== index)); };
    const onDragEnd = (result) => {
      if (!result.destination || !isDynamic) return;
      const newArray = [...arrayValue];
      const [removed] = newArray.splice(result.source.index, 1);
      newArray.splice(result.destination.index, 0, removed);
      handleArrayChange(newArray);
    };

    return (
      <Paper key={key} variant="outlined" sx={{ mb: 2, p: 1.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 1 }}>
          <Typography variant="subtitle2">{field.label || field.name}</Typography>
          <Chip
            label={isDynamic ? `Dynamic Array (${arrayValue.length})` : `Array[${fixedLength}]`}
            size="small"
            color={isDynamic ? 'secondary' : 'default'}
            sx={{ height: 18, fontSize: '0.65rem' }}
          />
        </Box>
        {arrayValue.length === 0 && isDynamic ? (
          <Typography variant="caption" color="text.secondary">
            アイテムがありません。下の＋ボタンで追加してください。
          </Typography>
        ) : (
          <DragDropContext onDragEnd={onDragEnd}>
            <Droppable droppableId={key}>
              {(provided) => (
                <Box {...provided.droppableProps} ref={provided.innerRef}>
                  {arrayValue.map((itemValue, index) => (
                    <Draggable
                      key={`${key}-${index}`}
                      draggableId={`${key}-${index}`}
                      index={index}
                      isDragDisabled={!isDynamic}
                    >
                      {(provided) => (
                        <Box
                          ref={provided.innerRef}
                          {...provided.draggableProps}
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 0.5,
                            mb: 0.5,
                            p: 0.5,
                            bgcolor: 'background.paper',
                            borderRadius: 1,
                            border: '1px solid',
                            borderColor: 'divider',
                          }}
                        >
                          {isDynamic && (
                            <Box {...provided.dragHandleProps} sx={{ color: 'text.disabled', cursor: 'grab', display: 'flex', alignItems: 'center' }}>
                              <DragHandleIcon fontSize="small" />
                            </Box>
                          )}
                          <Box sx={{ flex: 1 }}>
                            {renderSingle(itemValue, (newItemValue) => {
                              const newArray = [...arrayValue];
                              newArray[index] = newItemValue;
                              handleArrayChange(newArray);
                            })}
                          </Box>
                          {isDynamic && (
                            <Tooltip title="削除">
                              <IconButton size="small" color="error" onClick={() => removeItem(index)}>
                                <RemoveIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          )}
                        </Box>
                      )}
                    </Draggable>
                  ))}
                  {provided.placeholder}
                </Box>
              )}
            </Droppable>
          </DragDropContext>
        )}
        {isDynamic && (
          <Box sx={{ mt: 1 }}>
            <Tooltip title="アイテムを追加">
              <IconButton size="small" color="primary" onClick={addItem}>
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        )}
      </Paper>
    );
  };

  return (
    <Box sx={{ p: 1 }}>
      {schema.fields.map((field, index) => (
        <Box key={field.name}>
          {renderField(field)}
          {index < schema.fields.length - 1 && field.arraySize !== 0 && (
            <Divider sx={{ mb: 1 }} />
          )}
        </Box>
      ))}
    </Box>
  );
};

export default BaseRoleInputForm;