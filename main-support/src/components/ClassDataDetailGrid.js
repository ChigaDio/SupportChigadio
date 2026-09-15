import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  Autocomplete, Select, MenuItem, FormControl, InputLabel, Checkbox, FormControlLabel,
  Chip, Divider, Tooltip
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import SubdirectoryArrowRightIcon from '@mui/icons-material/SubdirectoryArrowRight';
import AccountTreeIcon from '@mui/icons-material/AccountTree';

const CUSTOM_TYPES = ['bit', 'color', 'bezier', 'dictionary'];
const NUMERIC_TYPES = ['int', 'float', 'double', 'byte', 'short', 'long', 'decimal', 'uint'];

/**
 * 依存関係の「有効になる値」選択 UI
 * - bool: True / False
 * - enum / class_data_id: 検索付きドロップダウン
 * - ＋ボタンで複数条件を OR 追加
 */
function DependencyValuesEditor({
  parentType,
  values,          // string[] 現在の enableValues
  onChange,        // (next: string[]) => void
  enumMemberOptions, // [{ value, label }] 親が enum/class_data_id のとき
}) {
  const isBool = parentType && ['bool', 'boolean'].includes(String(parentType).toLowerCase());
  const [pending, setPending] = React.useState(null); // 追加用の一時選択

  const options = isBool
    ? [
      { value: 'true', label: 'True' },
      { value: 'false', label: 'False' },
    ]
    : (enumMemberOptions || []);

  const selected = (values || []).map(String);

  const addValue = (v) => {
    if (v == null || v === '') return;
    const s = String(v);
    if (selected.includes(s)) return;
    onChange([...selected, s]);
    setPending(null);
  };

  const removeValue = (v) => {
    onChange(selected.filter(x => x !== v));
  };



  return (
    <Box sx={{ mt: 1 }}>
      {/* 選択済みチップ */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1, minHeight: 28 }}>
        {selected.length === 0 && (
          <Typography variant="caption" color="text.disabled">
            まだ条件がありません。下から追加してください
          </Typography>
        )}
        {selected.map((v) => {
          const label = options.find(o => o.value === v || o.label === v)?.label || v;
          return (
            <Chip
              key={v}
              size="small"
              label={label}
              onDelete={() => removeValue(v)}
              variant="outlined"
              color="primary"
              sx={{ borderStyle: 'dashed' }}
            />
          );
        })}
      </Box>

      {/* 追加用ドロップダウン + ＋ボタン */}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Autocomplete
          size="small"
          sx={{ flex: 1, minWidth: 220 }}
          options={options.filter(o => !selected.includes(String(o.value)))}
          getOptionLabel={(o) => (typeof o === 'string' ? o : o.label)}
          value={options.find(o => o.value === pending) || null}
          onChange={(e, v) => setPending(v ? v.value : null)}
          isOptionEqualToValue={(a, b) => a?.value === b?.value}
          renderInput={(params) => (
            <TextField
              {...params}
              label={isBool ? 'True / False を選択' : '値を検索して選択'}
              placeholder={isBool ? 'True または False' : '検索...'}
            />
          )}
        />
        <Button
          variant="outlined"
          size="small"
          startIcon={<AddIcon />}
          disabled={pending == null}
          onClick={() => addValue(pending)}
          sx={{ whiteSpace: 'nowrap', height: 40 }}
        >
          追加
        </Button>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        親がこれらの値のいずれかと一致するとき編集可能（OR）
      </Typography>
    </Box>
  );
}

/** 親になれる型かどうか（bool / enum名 / class_data_id名） */
function isParentCandidateType(type, typeInfo) {
  if (!type) return false;
  const t = String(type).toLowerCase();
  if (t === 'bool' || t === 'boolean') return true;
  if ((typeInfo.enum_list || []).includes(type)) return true;
  if ((typeInfo.class_data_id_list || []).includes(type)) return true;
  return false;
}

/** 依存関係の要約テキスト */
function dependencySummary(dep) {
  if (!dep || !dep.parentFieldName) return null;
  const vals = (dep.enableValues || []).map(String);
  const valLabel = vals.length ? vals.join(' | ') : '(条件なし)';
  return `${dep.parentFieldName} → [${valLabel}]`;
}

// ============================================================
// オプション編集: 数値型 min/max
// (CustomClassDataDetailGrid.js と同じロジックをそのまま使用)
// ============================================================
function NumericOptionsEditor({ options, onChange }) {
  return (
    <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
      <TextField
        label="最小値" type="number" size="small"
        value={options.min ?? ''}
        onChange={(e) => onChange({ ...options, min: e.target.value === '' ? null : Number(e.target.value) })}
      />
      <TextField
        label="最大値" type="number" size="small"
        value={options.max ?? ''}
        onChange={(e) => onChange({ ...options, max: e.target.value === '' ? null : Number(e.target.value) })}
      />
    </Box>
  );
}

// ============================================================
// オプション編集: bit (チェックボックス on/off, single/multiple, select-all)
// ============================================================
function BitOptionsEditor({ options, onChange, enumNames, classDataIdNames, customClassDataIdNames }) {
  const sizeMode = options.sizeMode || 'manual';
  const sourceNames = sizeMode === 'enum' ? enumNames
    : sizeMode === 'classDataId' ? classDataIdNames
      : sizeMode === 'customClassDataId' ? customClassDataIdNames
        : [];

  const flagNames = options.flagNames || [];
  const size = options.size ?? flagNames.length ?? 8;

  const setFlagName = (index, value) => {
    const next = [...flagNames];
    next[index] = value;
    onChange({ ...options, flagNames: next });
  };

  return (
    <Box sx={{ mt: 1 }}>
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>ビット数の決め方</InputLabel>
          <Select
            label="ビット数の決め方"
            value={sizeMode}
            onChange={(e) => onChange({ ...options, sizeMode: e.target.value, sizeSourceName: null })}
          >
            <MenuItem value="manual">手動指定</MenuItem>
            <MenuItem value="enum">Enumの要素数から</MenuItem>
            <MenuItem value="classDataId">ClassDataIDの要素数から</MenuItem>
            <MenuItem value="customClassDataId">CustomClassDataIDの要素数から</MenuItem>
          </Select>
        </FormControl>

        {sizeMode === 'manual' ? (
          <TextField
            label="ビット数" type="number" size="small"
            value={size}
            onChange={(e) => {
              const n = Math.max(1, Number(e.target.value) || 1);
              const nextFlags = Array.from({ length: n }, (_, i) => flagNames[i] || `Flag${i}`);
              onChange({ ...options, size: n, flagNames: nextFlags });
            }}
          />
        ) : (
          <Autocomplete
            size="small"
            sx={{ minWidth: 220 }}
            options={sourceNames}
            value={options.sizeSourceName || null}
            onChange={(e, v) => onChange({ ...options, sizeSourceName: v })}
            renderInput={(params) => <TextField {...params} label="参照元" />}
          />
        )}

        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>選択モード</InputLabel>
          <Select
            label="選択モード"
            value={options.mode || 'multiple'}
            onChange={(e) => onChange({ ...options, mode: e.target.value })}
          >
            <MenuItem value="multiple">複数選択可</MenuItem>
            <MenuItem value="single">1つだけ選択（排他）</MenuItem>
          </Select>
        </FormControl>

        {options.mode !== 'single' && (
          <FormControlLabel
            control={
              <Checkbox
                checked={!!options.allowSelectAll}
                onChange={(e) => onChange({ ...options, allowSelectAll: e.target.checked })}
              />
            }
            label="全選択ボタンを許可"
          />
        )}
      </Box>

      {sizeMode === 'manual' && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">フラグ名（各ビットのラベル）</Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 0.5 }}>
            {flagNames.map((name, i) => (
              <TextField
                key={i}
                size="small"
                label={`bit ${i}`}
                value={name}
                onChange={(e) => setFlagName(i, e.target.value)}
                sx={{ width: 130 }}
              />
            ))}
          </Box>
        </Box>
      )}
      {sizeMode !== 'manual' && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          ※ 参照元を選択して保存すると、要素数からビット数・フラグ名が自動生成されます
        </Typography>
      )}
    </Box>
  );
}

// ============================================================
// オプション編集: bezier
// ============================================================
function BezierOptionsEditor({ options, onChange }) {
  return (
    <Box sx={{ display: 'flex', gap: 2, mt: 1, flexWrap: 'wrap' }}>
      <FormControl size="small" sx={{ minWidth: 120 }}>
        <InputLabel>値の型</InputLabel>
        <Select
          label="値の型"
          value={options.valueType || 'float'}
          onChange={(e) => onChange({ ...options, valueType: e.target.value })}
        >
          <MenuItem value="float">float</MenuItem>
          <MenuItem value="int">int</MenuItem>
        </Select>
      </FormControl>
      <TextField
        label="グラフの最小値" type="number" size="small"
        value={options.min ?? 0}
        onChange={(e) => onChange({ ...options, min: Number(e.target.value) })}
      />
      <TextField
        label="グラフの最大値" type="number" size="small"
        value={options.max ?? 1}
        onChange={(e) => onChange({ ...options, max: Number(e.target.value) })}
      />
    </Box>
  );
}

// ============================================================
// オプション編集: dictionary
// キーは数値のみ（int / Enum / ClassDataID / CustomClassDataID）に限定し、
// 値はすべての型（配列・bit/color/bezierを含む）に対応する
// ============================================================
function DictionaryOptionsEditor({ options, onChange, keyTypeOptions, valueTypeOptions, enumNames, classDataIdNames, customClassDataIdNames }) {
  const keyType = options.keyType || 'int';
  const valueType = options.valueType || 'int';
  const valueArraySize = options.valueArraySize ?? 0;
  const valueOptions = options.valueOptions || {};
  const valueIsNumeric = NUMERIC_TYPES.includes(valueType);

  const setValueOptions = (vo) => onChange({ ...options, valueOptions: vo });

  return (
    <Box sx={{ mt: 1 }}>
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>キーの型</InputLabel>
          <Select
            label="キーの型"
            value={keyType}
            onChange={(e) => onChange({ ...options, keyType: e.target.value })}
          >
            {keyTypeOptions.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
          </Select>
        </FormControl>

        <Autocomplete
          size="small"
          sx={{ minWidth: 220 }}
          options={valueTypeOptions}
          value={valueType}
          onChange={(e, v) => onChange({ ...options, valueType: v || 'int', valueOptions: {} })}
          renderInput={(params) => <TextField {...params} label="値の型" />}
        />

        <TextField
          label="値の配列サイズ（0=単一, -1=可変長, N>0=固定長）"
          type="number" size="small" sx={{ minWidth: 260 }}
          value={valueArraySize}
          onChange={(e) => onChange({ ...options, valueArraySize: Number(e.target.value) || 0 })}
        />
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        キーは数値のみ（int / Enum / ClassDataID / CustomClassDataID）です。値はどの型でも指定できます。
      </Typography>

      {keyType !== 'int' && (
        <Box sx={{ mt: 1 }}>
          <FormControlLabel
            control={
              <Checkbox
                checked={!!options.prefillKeys}
                onChange={(e) => onChange({ ...options, prefillKeys: e.target.checked })}
              />
            }
            label={`${keyType} の全メンバーをキーとしてデフォルトで事前追加する`}
          />
          {options.prefillKeys && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              有効化するとキーの手動追加・削除はできなくなり、{keyType}の全メンバー分のエントリが常に維持されます。
            </Typography>
          )}
        </Box>
      )}

      {(valueIsNumeric || valueType === 'bit' || valueType === 'bezier') && (
        <Box sx={{ mt: 1.5, p: 1, border: '1px dashed #ccc', borderRadius: 1 }}>
          <Typography variant="caption" color="text.secondary">値の型オプション</Typography>
          {valueIsNumeric && <NumericOptionsEditor options={valueOptions} onChange={setValueOptions} />}
          {valueType === 'bit' && (
            <BitOptionsEditor
              options={valueOptions}
              onChange={setValueOptions}
              enumNames={enumNames}
              classDataIdNames={classDataIdNames}
              customClassDataIdNames={customClassDataIdNames}
            />
          )}
          {valueType === 'bezier' && <BezierOptionsEditor options={valueOptions} onChange={setValueOptions} />}
        </Box>
      )}
    </Box>
  );
}

// ============================================================
// オプション編集: 配列(arraySize=-1の可変長List)向けprefill設定(仕様書項目5)
// ============================================================
function ArrayOptionsEditor({ options, onChange, enumNames, classDataIdNames, customClassDataIdNames }) {
  const sourceNames = [...enumNames, ...classDataIdNames, ...customClassDataIdNames];
  const enabled = !!options.prefillSourceName;

  return (
    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap', mt: 1 }}>
      <FormControlLabel
        control={
          <Checkbox
            checked={enabled}
            onChange={(e) => onChange({ ...options, prefillSourceName: e.target.checked ? (options.prefillSourceName || sourceNames[0] || null) : null })}
          />
        }
        label="Enum/ClassDataIDのメンバー数ぶんデフォルトを事前追加する"
      />
      {enabled && (
        <Autocomplete
          size="small"
          sx={{ minWidth: 220 }}
          options={sourceNames}
          value={options.prefillSourceName || null}
          onChange={(e, v) => onChange({ ...options, prefillSourceName: v })}
          renderInput={(params) => <TextField {...params} label="参照元(Enum/ClassDataID)" />}
        />
      )}
      {enabled && (
        <Typography variant="caption" color="text.secondary" sx={{ width: '100%' }}>
          有効化すると要素数は参照元のメンバー数に固定され、参照元の増減/リネームに追従します
          （実データはClassDataID/ClassDataMatrixID/ScenarioRole側の各レコードで保持・同期されます）。
        </Typography>
      )}
    </Box>
  );
}

function defaultOptionsForType(type) {
  if (NUMERIC_TYPES.includes(type)) return { min: null, max: null };
  if (type === 'bit') return { sizeMode: 'manual', sizeSourceName: null, size: 8, mode: 'multiple', allowSelectAll: true, flagNames: Array.from({ length: 8 }, (_, i) => `Flag${i}`) };
  if (type === 'color') return {};
  if (type === 'bezier') return { valueType: 'float', min: 0, max: 1 };
  if (type === 'dictionary') return { keyType: 'int', valueType: 'int', valueArraySize: 0, valueOptions: {} };
  return {};
}

function optionsSummary(field) {
  const t = field.type;
  const o = field.options || {};
  if (NUMERIC_TYPES.includes(t)) {
    if (o.min == null && o.max == null) return '範囲指定なし';
    return `範囲 [${o.min ?? '-∞'} , ${o.max ?? '∞'}]`;
  }
  if (t === 'bit') {
    const modeLabel = o.mode === 'single' ? '排他選択' : '複数選択' + (o.allowSelectAll ? '+全選択' : '');
    return `${o.size ?? '?'}bit / ${modeLabel}`;
  }
  if (t === 'color') return 'RGBA';
  if (t === 'bezier') return `ベジェ(${o.valueType || 'float'}) [${o.min ?? 0}, ${o.max ?? 1}]`;
  if (t === 'dictionary') {
    const valueLabel = `${o.valueType || 'int'}${o.valueArraySize ? '[]' : ''}`;
    const keyLabel = o.prefillKeys ? `${o.keyType || 'int'}(全メンバー事前追加)` : (o.keyType || 'int');
    return `Dictionary<${keyLabel}, ${valueLabel}>`;
  }
  if (field.arraySize === -1 && o.prefillSourceName) {
    return `${o.prefillSourceName}の全メンバーを事前追加`;
  }
  return '-';
}

function ClassDataDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  // /api/custom-class-data-type-options から basic/unity/bit-color-bezier/enum/class/classDataId/
  // customClassData/customClassDataId をまとめて取得する(CustomClassDataDetailGrid.jsと同じ仕組み)
  const [typeInfo, setTypeInfo] = useState({
    basic_types: [], unity_types: [], custom_types: CUSTOM_TYPES,
    enum_list: [], class_list: [], class_data_id_list: [], custom_class_list: [], custom_class_id_list: [],
  });

  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formType, setFormType] = useState('');
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formArraySize, setFormArraySize] = useState(0);
  const [formOptions, setFormOptions] = useState({});
  // 依存関係: 親フィールド名 + 有効になる値（OR）
  const [formDepParent, setFormDepParent] = useState(null);
  const [formDepValues, setFormDepValues] = useState([]);
  const [parentMemberOptions, setParentMemberOptions] = useState([]); // [{value, label}]

  // 親フィールドが変わったらメンバー一覧を取得
  useEffect(() => {
    if (!formDepParent) {
      setParentMemberOptions([]);
      return;
    }
    const parentField = data.find(f => f.name === formDepParent);
    if (!parentField) {
      setParentMemberOptions([]);
      return;
    }
    const t = parentField.type;
    const lower = String(t).toLowerCase();
    if (lower === 'bool' || lower === 'boolean') {
      setParentMemberOptions([
        { value: 'true', label: 'True' },
        { value: 'false', label: 'False' },
      ]);
      return;
    }
    // enum
    if ((typeInfo.enum_list || []).includes(t)) {
      fetch(`/api/enum/${encodeURIComponent(t)}`)
        .then(r => r.ok ? r.json() : [])
        .then(list => {
          const opts = (list || [])
            .map(item => item.property || item.enum_property || item)
            .filter(Boolean)
            .map(p => ({ value: String(p), label: String(p) }));
          setParentMemberOptions(opts);
        })
        .catch(() => setParentMemberOptions([]));
      return;
    }
    // class_data_id
    if ((typeInfo.class_data_id_list || []).includes(t)) {
      fetch(`/api/class-data-id/${encodeURIComponent(t)}`)
        .then(r => r.ok ? r.json() : { rows: [] })
        .then(d => {
          const opts = (d.rows || [])
            .map(row => row.enum_property)
            .filter(Boolean)
            .map(p => ({ value: String(p), label: String(p) }));
          setParentMemberOptions(opts);
        })
        .catch(() => setParentMemberOptions([]));
      return;
    }
    setParentMemberOptions([]);
  }, [formDepParent, data, typeInfo]);

  // Fetch data for the class
  useEffect(() => {
    fetch(`/api/class-data/${name}`)
      .then(response => response.json())
      .then(fetchedData => {
        setData((Array.isArray(fetchedData) ? fetchedData : []).map((item, index) => ({ ...item, id: item.id || index + 1 })));
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching class data:', error);
        setLoading(false);
      });
  }, [name]);

  // 型リスト取得(基本型/Unity型/bit・color・bezier/Enum/ClassData/ClassDataID/
  // CustomClassData/CustomClassDataIDを一括で取得)
  useEffect(() => {
    fetch('/api/custom-class-data-type-options')
      .then(res => res.json())
      .then(info => setTypeInfo({ ...info, custom_types: Array.from(new Set([...(info.custom_types || []), 'dictionary'])) }))
      .catch(error => console.error('型情報取得エラー:', error));
  }, []);

  const typeOptions = useMemo(() => {
    const list = [
      ...typeInfo.basic_types,
      ...typeInfo.unity_types,
      ...typeInfo.custom_types,
      ...typeInfo.enum_list,
      ...typeInfo.class_list,
      ...typeInfo.class_data_id_list,
      ...typeInfo.custom_class_list,
      ...typeInfo.custom_class_id_list,
    ];
    return Array.from(new Set(list));
  }, [typeInfo]);

  // dictionaryのキー型候補: int(数値) + Enum + ClassDataID + CustomClassDataID のみ
  const keyTypeOptions = useMemo(() => {
    return Array.from(new Set([
      'int',
      ...typeInfo.enum_list,
      ...typeInfo.class_data_id_list,
      ...typeInfo.custom_class_id_list,
    ]));
  }, [typeInfo]);

  const openAddDialog = () => {
    setEditingId(null);
    setFormType('');
    setFormName('');
    setFormDescription('');
    setFormArraySize(0);
    setFormOptions({});
    setFormDepParent(null);
    setFormDepValues([]);
    setOpen(true);
  };

  const openEditDialog = (field) => {
    setEditingId(field.id);
    setFormType(field.type);
    setFormName(field.name);
    setFormDescription(field.description || '');
    setFormArraySize(field.arraySize || 0);
    setFormOptions(field.options || defaultOptionsForType(field.type));
    const dep = field.dependency || null;
    setFormDepParent(dep?.parentFieldName || null);
    setFormDepValues(Array.isArray(dep?.enableValues) ? dep.enableValues.map(String) : []);
    setOpen(true);
  };

  const handleTypeChange = (newType) => {
    setFormType(newType || '');
    setFormOptions(defaultOptionsForType(newType || ''));
  };

  // 親候補: 自分以外で、bool / enum / class_data_id 型のフィールド
  const parentCandidates = useMemo(() => {
    return data.filter(f => {
      if (editingId && f.id === editingId) return false;
      if (f.name === formName) return false;
      return isParentCandidateType(f.type, typeInfo);
    });
  }, [data, editingId, formName, typeInfo]);

  const selectedParentField = useMemo(
    () => parentCandidates.find(f => f.name === formDepParent) || null,
    [parentCandidates, formDepParent]
  );

  const buildDependency = () => {
    if (!formDepParent) return undefined;
    // 子は親を1人だけ。親は複数の子を持てる（子側が親を指す）
    return {
      parentFieldName: formDepParent,
      enableValues: formDepValues.length > 0
        ? formDepValues
        : (selectedParentField && String(selectedParentField.type).toLowerCase() === 'bool' ? [true] : []),
      hideWhenDisabled: true,
    };
  };

  // Add / Edit 保存
  const handleSaveField = () => {
    if (!formType.trim() || !formName.trim()) {
      alert('Type and Name are required');
      return;
    }
    // 子は親を1人だけ（既に他の親を持っている場合は上書き）
    if (formDepParent) {
      const parentExists = data.some(f => f.name === formDepParent && (!editingId || f.id !== editingId));
      if (!parentExists) {
        alert(`親フィールド「${formDepParent}」が見つかりません`);
        return;
      }
    }
    const dependency = buildDependency();
    if (editingId) {
      setData(data.map(f => f.id === editingId
        ? {
          ...f,
          type: formType,
          name: formName,
          description: formDescription,
          arraySize: parseInt(formArraySize, 10) || 0,
          options: formOptions,
          dependency: dependency || undefined,
        }
        : f));
    } else {
      const maxId = Math.max(...data.map(item => item.id), 0) + 1;
      setData([...data, {
        id: maxId,
        type: formType,
        name: formName,
        description: formDescription,
        arraySize: parseInt(formArraySize, 10) || 0,
        options: formOptions,
        ...(dependency ? { dependency } : {}),
      }]);
    }
    setOpen(false);
  };

  // Delete row（親を消した場合は子の dependency もクリア）
  const handleDeleteRow = (id) => {
    const deleted = data.find(item => item.id === id);
    const deletedName = deleted?.name;
    setData(
      data
        .filter(item => item.id !== id)
        .map(item => {
          if (deletedName && item.dependency?.parentFieldName === deletedName) {
            const { dependency, ...rest } = item;
            return rest;
          }
          return item;
        })
    );
  };

  // Reorder rows
  const handleRowOrderChange = (params) => {
    const { oldIndex, targetIndex } = params;
    const newData = [...data];
    const [movedRow] = newData.splice(oldIndex, 1);
    newData.splice(targetIndex, 0, movedRow);
    setData(newData);
  };

  // Save data
  const handleSave = () => {
    fetch(`/api/class-data/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('Error saving data: ' + error));
  };

  // Delete class
  const handleDelete = () => {
    if (window.confirm(`Delete ${name}?`)) {
      fetch(`/api/class-data/${name}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          navigate('/class-data');
        })
        .catch(error => alert('Error deleting class: ' + error));
    }
  };

  // Generate C#
  const handleGenerateCs = () => {
    fetch(`/api/generate-class/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('Error generating C#: ' + error));
  };

  // 親→子の逆引き（親が何人の子を持っているか）
  const childrenByParent = useMemo(() => {
    const map = {};
    data.forEach(f => {
      const p = f.dependency?.parentFieldName;
      if (p) {
        if (!map[p]) map[p] = [];
        map[p].push(f.name);
      }
    });
    return map;
  }, [data]);

  const columns = [
    { field: 'type', headerName: 'Type', width: 160 },
    { field: 'name', headerName: 'Name', width: 130 },
    { field: 'description', headerName: 'Description', width: 180 },
    { field: 'arraySize', headerName: 'ArraySize', width: 100 },
    {
      field: 'options', headerName: 'オプション', width: 180,
      renderCell: (params) => <Chip size="small" label={optionsSummary(params.row)} />,
    },
    {
      field: 'dependency',
      headerName: '依存関係',
      width: 260,
      sortable: false,
      renderCell: (params) => {
        const row = params.row;
        const dep = row.dependency;
        const kids = childrenByParent[row.name] || [];
        return (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, py: 0.5, width: '100%' }}>
            {dep?.parentFieldName && (
              <Tooltip title={`親「${dep.parentFieldName}」が [${(dep.enableValues || []).join(' | ')}] のとき編集可能`}>
                <Box
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.5,
                    px: 1,
                    py: 0.25,
                    borderRadius: 1,
                    border: '1.5px dashed',
                    borderColor: 'primary.light',
                    bgcolor: 'primary.50',
                    maxWidth: '100%',
                  }}
                >
                  <SubdirectoryArrowRightIcon sx={{ fontSize: 16, color: 'primary.main', opacity: 0.8 }} />
                  <Typography variant="caption" noWrap sx={{ fontWeight: 600, color: 'primary.dark' }}>
                    {dep.parentFieldName}
                  </Typography>
                  <Typography variant="caption" noWrap color="text.secondary">
                    = {(dep.enableValues || []).map(String).join(' | ') || '…'}
                  </Typography>
                </Box>
              </Tooltip>
            )}
            {kids.length > 0 && (
              <Tooltip title={`子: ${kids.join(', ')}`}>
                <Box
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.5,
                    px: 1,
                    py: 0.25,
                    borderRadius: 1,
                    border: '1.5px dashed',
                    borderColor: 'secondary.light',
                    bgcolor: 'secondary.50',
                    maxWidth: '100%',
                  }}
                >
                  <AccountTreeIcon sx={{ fontSize: 14, color: 'secondary.main' }} />
                  <Typography variant="caption" noWrap color="secondary.dark">
                    → {kids.join(', ')}
                  </Typography>
                </Box>
              </Tooltip>
            )}
            {!dep?.parentFieldName && kids.length === 0 && (
              <Typography variant="caption" color="text.disabled">—</Typography>
            )}
          </Box>
        );
      },
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 170,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" variant="outlined" onClick={() => openEditDialog(params.row)}>編集</Button>
          <Button variant="contained" color="error" size="small" onClick={() => handleDeleteRow(params.id)}>
            Delete
          </Button>
        </Box>
      )
    }
  ];

  const isNumeric = NUMERIC_TYPES.includes(formType);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Class Data Detail: {name}
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={openAddDialog} sx={{ mr: 1 }}>
          新しい変数を追加
        </Button>
        <Button variant="contained" color="primary" onClick={handleSave} sx={{ mr: 1 }}>
          保存
        </Button>
        <Button variant="contained" color="secondary" onClick={handleGenerateCs} sx={{ mr: 1 }}>
          C#を生成
        </Button>
        <Button variant="contained" color="error" onClick={handleDelete}>
          削除
        </Button>
      </Box>
      {loading ? (
        <Typography>Loading...</Typography>
      ) : (
        <div style={{ height: 460, width: '100%' }}>
          <DataGrid
            rows={data}
            columns={columns}
            pageSizeOptions={[5]}
            getRowId={(row) => row.id}
            rowReordering
            onRowOrderChange={handleRowOrderChange}
          />
        </div>
      )}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingId ? '変数を編集' : '新しい変数を追加'}</DialogTitle>
        <DialogContent>
          <Autocomplete
            freeSolo
            options={typeOptions}
            renderInput={(params) => <TextField {...params} label="変数の型" margin="dense" fullWidth />}
            value={formType}
            onChange={(e, v) => handleTypeChange(v)}
            onInputChange={(e, v, reason) => { if (reason === 'input') handleTypeChange(v); }}
          />
          <TextField label="変数名" margin="dense" fullWidth value={formName} onChange={(e) => setFormName(e.target.value)} />
          <TextField label="説明" margin="dense" fullWidth value={formDescription} onChange={(e) => setFormDescription(e.target.value)} />
          <TextField label="配列サイズ" margin="dense" fullWidth type="number" value={formArraySize} onChange={(e) => setFormArraySize(e.target.value)} />

          {(isNumeric || CUSTOM_TYPES.includes(formType) || parseInt(formArraySize, 10) === -1) && (
            <>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2">型オプション</Typography>
              {isNumeric && <NumericOptionsEditor options={formOptions} onChange={setFormOptions} />}
              {parseInt(formArraySize, 10) === -1 && (
                <ArrayOptionsEditor
                  options={formOptions}
                  onChange={setFormOptions}
                  enumNames={typeInfo.enum_list}
                  classDataIdNames={typeInfo.class_data_id_list}
                  customClassDataIdNames={typeInfo.custom_class_id_list}
                />
              )}
              {formType === 'bit' && (
                <BitOptionsEditor
                  options={formOptions}
                  onChange={setFormOptions}
                  enumNames={typeInfo.enum_list}
                  classDataIdNames={typeInfo.class_data_id_list}
                  customClassDataIdNames={typeInfo.custom_class_id_list}
                />
              )}
              {formType === 'color' && (
                <Typography variant="caption" color="text.secondary">
                  RGBAカラー型です。実際の色の値はClassDataID/ClassDataMatrixID側の各レコードで設定します。
                </Typography>
              )}
              {formType === 'bezier' && (
                <BezierOptionsEditor options={formOptions} onChange={setFormOptions} />
              )}
              {formType === 'dictionary' && (
                <DictionaryOptionsEditor
                  options={formOptions}
                  onChange={setFormOptions}
                  keyTypeOptions={keyTypeOptions}
                  valueTypeOptions={typeOptions.filter(t => t !== 'dictionary')}
                  enumNames={typeInfo.enum_list}
                  classDataIdNames={typeInfo.class_data_id_list}
                  customClassDataIdNames={typeInfo.custom_class_id_list}
                />
              )}
            </>
          )}

          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <AccountTreeIcon fontSize="small" color="primary" />
            依存関係（親フィールド）
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            enum / bool / class_data_id を親に指定できます。親は複数の子を持てますが、子は親を1人だけ持てます。
            条件値は OR（いずれか一致）です。
          </Typography>
          <Autocomplete
            size="small"
            options={parentCandidates}
            getOptionLabel={(opt) => `${opt.name} (${opt.type})`}
            value={selectedParentField}
            onChange={(e, v) => {
              setFormDepParent(v ? v.name : null);
              // bool 親のときは True を既定値に
              if (v && String(v.type).toLowerCase() === 'bool') {
                setFormDepValues(['true']);
              } else if (!v) {
                setFormDepValues([]);
              }
            }}
            renderInput={(params) => (
              <TextField {...params} label="親フィールド" margin="dense" fullWidth placeholder="なし（独立）" />
            )}
            isOptionEqualToValue={(a, b) => a?.name === b?.name}
          />
          {formDepParent && (
  <DependencyValuesEditor
    parentType={selectedParentField?.type}
    values={formDepValues}
    onChange={setFormDepValues}
    enumMemberOptions={parentMemberOptions}
  />
)}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleSaveField}>{editingId ? '更新' : 'Add'}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ClassDataDetailGrid;