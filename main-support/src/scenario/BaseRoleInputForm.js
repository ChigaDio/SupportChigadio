import React, { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Checkbox,
  Autocomplete,
  FormControlLabel,
  Typography
} from '@mui/material';

const BaseRoleInputForm = ({ schema, initialData, onChange }) => {
  const [formData, setFormData] = useState(initialData || []);

  useEffect(() => {
    // 初期データをスキーマに基づいて変換
    const formattedData = schema.fields.map(field => ({
      name: field.name,
      value: initialData.find(d => d.name === field.name)?.value || ''
    }));
    setFormData(formattedData);
    onChange(formattedData); // 親コンポーネントに初期データを通知
  }, [initialData, schema, onChange]);

  const handleChange = (name, value) => {
    setFormData(prev => {
      const newData = prev.map(item =>
        item.name === name ? { ...item, value } : item
      );
      onChange(newData); // 入力値変更を親に通知
      return newData;
    });
  };

  const renderField = (field) => {
    const key = field.name;
    const currentValue = formData.find(d => d.name === key)?.value || '';

    if (field.warning) {
      return <Box key={key} sx={{ color: 'red' }}>{field.warning}</Box>;
    }

    switch (field.type) {
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
            onChange={e => handleChange(key, field.type === 'int' ? parseInt(e.target.value) : parseFloat(e.target.value))}
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
                checked={currentValue || false}
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
                  const newValue = [...(currentValue || Array(dim).fill(''))];
                  newValue[i] = parseFloat(e.target.value);
                  handleChange(key, newValue);
                }}
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
      {schema.fields.map(field => renderField(field))}
    </Box>
  );
};

export default BaseRoleInputForm;