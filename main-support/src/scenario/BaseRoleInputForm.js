import React, { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Checkbox,
  Autocomplete,
  FormControlLabel,
  Typography,
  CircularProgress,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import DragHandleIcon from '@mui/icons-material/DragHandle';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';

const BaseRoleInputForm = ({ schema, initialData, onChange }) => {
  const [formData, setFormData] = useState(initialData || []);
  const [enumValues, setEnumValues] = useState({});
  const [classDataSchemas, setClassDataSchemas] = useState({});
  const [isLoading, setIsLoading] = useState(true);

  // デフォルト値を取得する関数
  const getDefaultValue = (type, arraySize) => {
    const baseDefault = () => {
      switch (type.toLowerCase()) {
        case 'int': return 0;
        case 'float': return 0.0;
        case 'double': return 0.0;
        case 'short': return 0;
        case 'long': return 0;
        case 'decimal': return 0.0;
        case 'byte': return 0;
        case 'char': return '';
        case 'bool': return false;
        case 'string': return '';
        case 'vector2': return [0, 0];
        case 'vector3': return [0, 0, 0];
        case 'vector4': return [0, 0, 0, 0];
        default:
          if (type in enumValues && enumValues[type].length > 0) {
            if (typeof enumValues[type][0] === 'object') {
              return `${type}ID.${enumValues[type][0].property || enumValues[type][0].enum_property || enumValues[type][0]}`;
            }
            return `${type}ID.${enumValues[type][0]}`;
          }
          if (type in classDataSchemas && classDataSchemas[type].length > 0) {
            return classDataSchemas[type].reduce((acc, subField) => {
              acc[subField.name] = getDefaultValue(subField.type, subField.arraySize);
              return acc;
            }, {});
          }
          return '';
      }
    };

    if (arraySize === undefined || arraySize === 0) {
      return baseDefault();
    } else if (arraySize > 0) {
      return Array.from({ length: arraySize }, () => baseDefault());
    } else if (arraySize === -1) {
      return []; // 修正: 動的配列の初期値を空配列に設定
    }
    return baseDefault();
  };

  // 初期データ設定
  useEffect(() => {
    if (!isLoading) {
      const formattedData = schema.fields.map(field => {
        const initialItem = initialData.find(d => d.name === field.name);
        return {
          name: field.name,
          value: initialItem ? initialItem.value : getDefaultValue(field.type, field.arraySize),
          arraySize: field.arraySize !== undefined ? field.arraySize : 0
        };
      });
      setFormData(formattedData);
      onChange(formattedData);
    }
  }, [initialData, schema, onChange, enumValues, classDataSchemas, isLoading]);

  // 必要な enum-id, class-data-id, class-data を取得
  useEffect(() => {
    setIsLoading(true);

    // schema.fields から必要な type を抽出（ネストを含むため、再帰的に集める）
    const collectTypes = (fields) => {
      const types = new Set();
      fields.forEach(field => {
        types.add(field.type);
        if (field.subFields) {
          collectTypes(field.subFields).forEach(t => types.add(t));
        }
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

        if (!enumListRes.ok) {
          console.warn(`enum-id取得に失敗: ${enumListRes.status}`);
        }
        if (!classIdListRes.ok) {
          console.warn(`class-id-data取得に失敗: ${classIdListRes.status}`);
        }
        if (!classDataListRes.ok) {
          console.warn(`class-data取得に失敗: ${classDataListRes.status}`);
        }

        const enumList = enumListRes.ok && enumListRes.headers.get('content-type')?.includes('application/json') ? await enumListRes.json() : [];
        const classIdList = classIdListRes.ok && classIdListRes.headers.get('content-type')?.includes('application/json') ? await classIdListRes.json() : [];
        const classDataList = classDataListRes.ok && classDataListRes.headers.get('content-type')?.includes('application/json') ? await classDataListRes.json() : [];

        const enumPromises = enumList
          .filter(enumItem => types.includes(enumItem.name))
          .map(async enumItem => {
            const res = await fetch(`/api/enum/${encodeURIComponent(enumItem.name)}`);
            if (!res.ok) {
              console.warn(`enum値取得に失敗: ${enumItem.name} (${res.status})`);
              return { [enumItem.name]: [] };
            }
            if (!res.headers.get('content-type')?.includes('application/json')) {
              console.error(`enum ${enumItem.name} のレスポンスがJSONではありません`);
              return { [enumItem.name]: [] };
            }
            const data = await res.json();
            return { [enumItem.name]: data || [] };
          });

        const classIdPromises = classIdList
          .filter(classIdItem => types.includes(classIdItem.name))
          .map(async classIdItem => {
            const res = await fetch(`/api/class-data-id/${encodeURIComponent(classIdItem.name)}`);
            if (!res.ok) {
              console.warn(`classId値取得に失敗: ${classIdItem.name} (${res.status})`);
              return { [classIdItem.name]: [] };
            }
            if (!res.headers.get('content-type')?.includes('application/json')) {
              console.error(`classId ${classIdItem.name} のレスポンスがJSONではありません`);
              return { [classIdItem.name]: [] };
            }
            const data = await res.json();
            return { [classIdItem.name]: data.rows.map(row => row.enum_property) || [] };
          });

        const classDataPromises = classDataList
          .filter(classDataItem => types.includes(classDataItem.name))
          .map(async classDataItem => {
            const res = await fetch(`/api/class-data/${encodeURIComponent(classDataItem.name)}`);
            if (!res.ok) {
              console.warn(`classData値取得に失敗: ${classDataItem.name} (${res.status})`);
              return { [classDataItem.name]: [] };
            }
            if (!res.headers.get('content-type')?.includes('application/json')) {
              console.error(`classData ${classDataItem.name} のレスポンスがJSONではありません`);
              return { [classDataItem.name]: [] };
            }
            const data = await res.json();
            return { [classDataItem.name]: data || [] };
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

        setEnumValues(prev => ({ ...prev, ...enumMap })); // 修正: 既存のデータを保持
        setClassDataSchemas(prev => ({ ...prev, ...classDataMap })); // 修正: 既存のデータを保持
        setIsLoading(false);
      } catch (error) {
        console.error('型オプションまたは値の取得エラー:', error);
        setEnumValues({});
        setClassDataSchemas({});
        setIsLoading(false);
      }
    };

    loadData();
  }, [JSON.stringify(schema.fields)]); // 修正: 依存配列をJSON文字列で比較して無限ループを防止

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

    indexPath.forEach(idx => {
      currentValue = currentValue ? currentValue[idx] : undefined;
    });
    if (currentValue === undefined) {
      currentValue = getDefaultValue(field.type, field.arraySize);
    }

    if (field.warning) {
      return <Box key={key} sx={{ color: 'red' }}>{field.warning}</Box>;
    }

    if (isLoading) {
      return (
        <Box key={key} sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <CircularProgress size={20} sx={{ mr: 1 }} />
          <Typography>Loading options...</Typography>
        </Box>
      );
    }

    const renderSingle = (value, onValueChange) => {
      if (enumValues[field.type] && enumValues[field.type].length > 0) {
        const options = enumValues[field.type].map(v => {
          if (typeof v === 'object') {
            const val = v.property || v.enum_property || v;
            return { value: `${field.type}ID.${val}`, label: val };
          }
          return { value: `${field.type}ID.${v}`, label: v };
        });
        return (
          <Autocomplete
            key={key}
            options={options}
            getOptionLabel={(option) => option.label}
            value={options.find(opt => opt.value === value) || null}
            onChange={(e, newValue) => onValueChange(newValue ? newValue.value : '')}
            renderInput={params => <TextField {...params} label={field.label || field.name} sx={{ mb: 1 }} />}
            fullWidth
            isOptionEqualToValue={(option, val) => option.value === val?.value}
          />
        );
      }

      if (classDataSchemas[field.type] && classDataSchemas[field.type].length > 0) {
        const subSchema = {
          fields: classDataSchemas[field.type].map(sub => ({
            ...sub,
            label: sub.label || sub.name,
            arraySize: sub.arraySize !== undefined ? sub.arraySize : 0, // 修正: arraySizeを明示
          })),
        };
        const subInitialData = Object.entries(value || {}).map(([n, v]) => ({
          name: n,
          value: v,
          arraySize: subSchema.fields.find(f => f.name === n)?.arraySize || 0,
        }));

        // 修正: クラスデータの初期値が空の場合、デフォルト値を生成
        if (!value || Object.keys(value).length === 0) {
          const defaultValue = getDefaultValue(field.type, field.arraySize);
          handleChange(field.name, defaultValue, field.arraySize);
          return (
            <Box key={key} sx={{ border: 1, p: 1, mb: 1 }}>
              <Typography variant="subtitle2">{field.label || field.name} (Class Data)</Typography>
              <BaseRoleInputForm
                schema={subSchema}
                initialData={subSchema.fields.map(f => ({
                  name: f.name,
                  value: defaultValue[f.name],
                  arraySize: f.arraySize,
                }))}
                onChange={(subData) => {
                  const newObj = subData.reduce((acc, { name, value }) => {
                    acc[name] = value;
                    return acc;
                  }, {});
                  onValueChange(newObj);
                }}
              />
            </Box>
          );
        }

        return (
          <Box key={key} sx={{ border: 1, p: 1, mb: 1 }}>
            <Typography variant="subtitle2">{field.label || field.name} (Class Data)</Typography>
            <BaseRoleInputForm
              schema={subSchema}
              initialData={subInitialData}
              onChange={(subData) => {
                const newObj = subData.reduce((acc, { name, value }) => {
                  acc[name] = value;
                  return acc;
                }, {});
                onValueChange(newObj);
              }}
            />
          </Box>
        );
      }

      switch (field.type.toLowerCase()) {
        case 'string':
        case 'char':
          return (
            <TextField
              key={key}
              label={field.label || field.name}
              value={currentValue}
              onChange={e => onValueChange(e.target.value)}
              fullWidth
              sx={{ mb: 1 }}
            />
          );

        case 'int':
        case 'short':
        case 'long':
        case 'byte':
          return (
            <TextField
              key={key}
              type="number"
              label={field.label || field.name}
              value={currentValue}
              onChange={e => onValueChange(parseInt(e.target.value) || 0)}
              fullWidth
              sx={{ mb: 1 }}
            />
          );

        case 'float':
        case 'double':
        case 'decimal':
          return (
            <TextField
              key={key}
              type="number"
              step="0.01"
              label={field.label || field.name}
              value={currentValue}
              onChange={e => onValueChange(parseFloat(e.target.value) || 0.0)}
              fullWidth
              sx={{ mb: 1 }}
            />
          );

        case 'bool':
          return (
            <FormControlLabel
              key={key}
              control={
                <Checkbox
                  checked={currentValue === true || currentValue === 'true'}
                  onChange={e => onValueChange(e.target.checked)}
                />
              }
              label={field.label || field.name}
              sx={{ mb: 1 }}
            />
          );

        case 'vector2':
        case 'vector3':
        case 'vector4':
          const dim = parseInt(field.type.replace('vector', '')) || 2;
          return (
            <Box key={key} sx={{ display: 'flex', gap: 1, mb: 1 }}>
              {Array.from({ length: dim }).map((_, i) => (
                <TextField
                  key={`${key}.${i}`}
                  label={`Dim${i + 1}`}
                  type="number"
                  value={currentValue[i] || 0}
                  onChange={e => {
                    const newVal = [...(currentValue || Array(dim).fill(0))];
                    newVal[i] = parseFloat(e.target.value) || 0;
                    onValueChange(newVal);
                  }}
                  sx={{ flex: 1 }}
                />
              ))}
            </Box>
          );

        default:
          return (
            <TextField
              key={key}
              label={field.label || field.name}
              value={currentValue}
              onChange={e => onValueChange(e.target.value)}
              fullWidth
              sx={{ mb: 1 }}
            />
          );
      }
    };

    const arraySize = field.arraySize !== undefined ? field.arraySize : 0;
    if (arraySize === 0) {
      return (
        <Box key={key} sx={{ mb: 1 }}>
          {renderSingle(currentValue, newValue => handleChange(field.name, newValue, arraySize))}
        </Box>
      );
    } else {
      const isDynamic = arraySize === -1;
      const fixedLength = isDynamic ? undefined : arraySize;
      let arrayValue = Array.isArray(currentValue)
        ? currentValue
        : isDynamic
        ? [] // 修正: 動的配列の初期値を空配列に設定
        : Array.from({ length: fixedLength }, () => getDefaultValue(field.type, 0));

      const handleArrayChange = (newArray) => {
        handleChange(field.name, newArray, arraySize);
      };

      const addItem = () => {
        if (isDynamic) {
          handleArrayChange([...arrayValue, getDefaultValue(field.type, 0)]);
        }
      };

      const removeItem = (index) => {
        if (isDynamic) {
          const newArray = arrayValue.filter((_, i) => i !== index);
          handleArrayChange(newArray);
        }
      };

      const onDragEnd = (result) => {
        if (!result.destination || !isDynamic) return;
        const newArray = [...arrayValue];
        const [removed] = newArray.splice(result.source.index, 1);
        newArray.splice(result.destination.index, 0, removed);
        handleArrayChange(newArray);
      };

      return (
        <Box key={key} sx={{ mb: 2, border: 1, p: 1 }}>
          <Typography variant="subtitle2">{field.label || field.name} (Array, size: {isDynamic ? 'Dynamic' : fixedLength})</Typography>
          {arrayValue.length === 0 && isDynamic ? (
            <Typography>No items yet. Add one below.</Typography> // 修正: 動的配列が空の場合のメッセージ
          ) : (
            <DragDropContext onDragEnd={onDragEnd}>
              <Droppable droppableId={key}>
                {(provided) => (
                  <List {...provided.droppableProps} ref={provided.innerRef}>
                    {arrayValue.map((itemValue, index) => (
                      <Draggable key={`${key}-${index}`} draggableId={`${key}-${index}`} index={index} isDragDisabled={!isDynamic}>
                        {(provided) => (
                          <ListItem
                            ref={provided.innerRef}
                            {...provided.draggableProps}
                            secondaryAction={
                              isDynamic ? (
                                <IconButton onClick={() => removeItem(index)}>
                                  <RemoveIcon />
                                </IconButton>
                              ) : null
                            }
                          >
                            <ListItemIcon {...provided.dragHandleProps}>
                              {isDynamic ? <DragHandleIcon /> : null}
                            </ListItemIcon>
                            <ListItemText
                              primary={
                                <Box>
                                  {renderSingle(itemValue, (newItemValue) => {
                                    const newArray = [...arrayValue];
                                    newArray[index] = newItemValue;
                                    handleArrayChange(newArray);
                                  })}
                                </Box>
                              }
                            />
                          </ListItem>
                        )}
                      </Draggable>
                    ))}
                    {provided.placeholder}
                  </List>
                )}
              </Droppable>
            </DragDropContext>
          )}
          {isDynamic && (
            <IconButton onClick={addItem}>
              <AddIcon />
            </IconButton>
          )}
        </Box>
      );
    }
  };

  return (
    <Box sx={{ p: 2 }}>
      {console.log('schema.fields:', schema.fields)} {/* デバッグ用ログ */}
      {schema.fields.map(field => (
        <Box key={field.name} sx={{ mb: 1 }}>
          {renderField(field)}
        </Box>
      ))}
    </Box>
  );
};

export default BaseRoleInputForm;