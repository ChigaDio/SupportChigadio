import React, { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Checkbox,
  Autocomplete,
  FormControlLabel,
  Typography,
  CircularProgress
} from '@mui/material';

const BaseRoleInputForm = ({ schema, initialData, onChange }) => {
  const [formData, setFormData] = useState(initialData || []);
  const [enumValues, setEnumValues] = useState({});
  const [isLoading, setIsLoading] = useState(true);

  // デフォルト値を取得する関数
  const getDefaultValue = (type) => {
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
          // enum-id の場合（オブジェクト配列）
          if (typeof enumValues[type][0] === 'object') {
            return `${type}ID.${enumValues[type][0].property || enumValues[type][0].enum_property || enumValues[type][0]}`;
          }
          // class-data-id の場合（文字列配列）
          return `${type}ID.${enumValues[type][0]}`;
        }
        return '';
    }
  };

  // 初期データ設定
  useEffect(() => {
    if (!isLoading) {
      const formattedData = schema.fields.map(field => ({
        name: field.name,
        value: initialData.find(d => d.name === field.name)?.value || getDefaultValue(field.type)
      }));
      setFormData(formattedData);
      onChange(formattedData);
    }
  }, [initialData, schema, onChange, enumValues, isLoading]);

  // 必要な enum-id と class-data-id のみを取得
  useEffect(() => {
    setIsLoading(true);

    // schema.fields から必要な type を抽出
    const types = [...new Set(schema.fields.map(field => field.type))];

    Promise.all([
      fetch('/api/enum-id').then(res => {
        if (!res.ok) {
          console.warn(`enum-id取得に失敗: ${res.status}`);
          return [];
        }
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          console.error('enum-idエンドポイントからJSON以外のレスポンスを受信');
          return [];
        }
        return res.json();
      }),
      fetch('/api/class-data-id').then(res => {
        if (!res.ok) {
          console.warn(`class-id-data取得に失敗: ${res.status}`);
          return [];
        }
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          console.error('class-id-dataエンドポイントからJSON以外のレスポンスを受信');
          return [];
        }
        return res.json();
      }),
    ]).then(([enumList, classIdList]) => {
      // schema.fields の type に含まれる enum-id のみフェッチ
      const enumPromises = enumList
        .filter(enumItem => types.includes(enumItem.name))
        .map(enumItem =>
          fetch(`/api/enum/${encodeURIComponent(enumItem.name)}`)
            .then(res => {
              if (!res.ok) {
                console.warn(`enum値取得に失敗: ${enumItem.name} (${res.status})`);
                return [];
              }
              const contentType = res.headers.get('content-type');
              if (!contentType || !contentType.includes('application/json')) {
                console.error(`enum ${enumItem.name} のレスポンスがJSONではありません`);
                return [];
              }
              return res.json();
            })
            .then(data => ({ [enumItem.name]: data || [] }))
        );

      // schema.fields の type に含まれる class-data-id のみフェッチ
      const classIdPromises = classIdList
        .filter(classIdItem => types.includes(classIdItem.name))
        .map(classIdItem =>
          fetch(`/api/class-data-id/${encodeURIComponent(classIdItem.name)}`)
            .then(res => {
              if (!res.ok) {
                console.warn(`classId値取得に失敗: ${classIdItem.name} (${res.status})`);
                return [];
              }
              const contentType = res.headers.get('content-type');
              if (!contentType || !contentType.includes('application/json')) {
                console.error(`classId ${classIdItem.name} のレスポンスがJSONではありません`);
                return [];
              }
              return res.json();
            })
            .then(data => ({ [classIdItem.name]: data.rows.map(row => row.enum_property) || [] }))
        );

      return Promise.all([...enumPromises, ...classIdPromises]);
    }).then(results => {
      const enumValuesMap = Object.assign({}, ...results);
      console.log('enumValues:', enumValuesMap); // デバッグ用
      setEnumValues(enumValuesMap);
      setIsLoading(false);
    }).catch(error => {
      console.error('型オプションまたはenum値の取得エラー:', error);
      setEnumValues({});
      setIsLoading(false);
    });
  }, [schema.fields]);

  const handleChange = (name, value) => {
    setFormData(prev => {
      const newData = prev.map(item =>
        item.name === name ? { ...item, value } : item
      );
      onChange(newData);
      return newData;
    });
  };

  const renderField = (field) => {
    console.log('renderField called for:', field); // デバッグ用
    const key = field.name;
    const currentValue = formData.find(d => d.name === key)?.value || '';

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

    // enum-id または class-data-id の場合
    if (enumValues[field.type] && enumValues[field.type].length > 0) {
      const options = enumValues[field.type].map(v => {
        // enum-id の場合（オブジェクト配列）
        if (typeof v === 'object') {
          const value = v.property || v.enum_property || v;
          return {
            value: `${field.type}ID.${value}`,
            label: value
          };
        }
        // class-data-id の場合（文字列配列）
        return {
          value: `${field.type}ID.${v}`,
          label: v
        };
      });
      return (
        <Autocomplete
          key={key}
          options={options}
          getOptionLabel={(option) => option.label}
          value={options.find(opt => opt.value === currentValue) || null}
          onChange={(e, newValue) => handleChange(key, newValue ? newValue.value : '')}
          renderInput={params => <TextField {...params} label={field.label} sx={{ mb: 1 }} />}
          fullWidth
          isOptionEqualToValue={(option, value) => option.value === value?.value}
        />
      );
    }

    // その他の型
    switch (field.type.toLowerCase()) {
      case 'string':
        return (
          <TextField
            key={key}
            label={field.label}
            value={currentValue}
            onChange={e => handleChange(key, e.target.value)}
            fullWidth
            sx={{ mb: 1 }}
          />
        );

      case 'int':
      case 'float':
      case 'double':
      case 'short':
      case 'long':
      case 'decimal':
      case 'byte':
      case 'char':
        return (
          <TextField
            key={key}
            type="number"
            label={field.label}
            value={currentValue}
            onChange={e => handleChange(key, field.type === 'int' ? parseInt(e.target.value) || 0 : parseFloat(e.target.value) || 0.0)}
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
                onChange={e => handleChange(key, e.target.checked)}
              />
            }
            label={field.label}
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
                value={currentValue[i] || ''}
                onChange={e => {
                  const newValue = [...(currentValue || Array(dim).fill(0))];
                  newValue[i] = parseFloat(e.target.value) || 0;
                  handleChange(key, newValue);
                }}
                sx={{ flex: 1 }}
              />
            ))}
          </Box>
        );

      default:
        if (field.options) {
          return (
            <Autocomplete
              key={key}
              options={field.options || []}
              value={currentValue || null}
              onChange={(e, v) => handleChange(key, v)}
              renderInput={params => <TextField {...params} label={field.label} sx={{ mb: 1 }} />}
              fullWidth
            />
          );
        }

        if (field.subFields) {
          return (
            <Box key={key} sx={{ border: 1, p: 1, mb: 1 }}>
              <Typography variant="subtitle2">{field.label} (Nested)</Typography>
              {field.subFields.map(subField => renderField(subField))}
            </Box>
          );
        }

        return (
          <TextField
            key={key}
            label={field.label}
            value={currentValue}
            onChange={e => handleChange(key, e.target.value)}
            fullWidth
            sx={{ mb: 1 }}
          />
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