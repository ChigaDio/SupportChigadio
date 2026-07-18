import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  Autocomplete, IconButton, Select, MenuItem, FormControl, InputLabel, Checkbox,
  FormControlLabel, Slider, Chip, Tooltip
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';

const NUMERIC_TYPES = ['int', 'float', 'double', 'byte', 'short', 'long', 'decimal', 'uint'];

// ============================================================
// 型ユーティリティ ( "int[]" のような配列表記に対応 )
// ============================================================
function parseType(type) {
  if (typeof type === 'string' && type.endsWith('[]')) {
    return { isArray: true, baseType: type.slice(0, -2) };
  }
  return { isArray: false, baseType: type };
}

function getDefaultValueForType(type, ctx) {
  const { enumValues, classSchemas, customClassSchemas } = ctx;
  const lower = (type || '').toLowerCase();
  if (lower === 'int' || lower === 'float' || lower === 'double') return 0;
  if (lower === 'bool') return false;
  if (lower === 'string') return '';
  if (lower === 'vector2') return [0, 0];
  if (lower === 'vector3') return [0, 0, 0];
  if (type === 'bit') return { size: 8, bits: [] };
  if (type === 'color') return { r: 1, g: 1, b: 1, a: 1 };
  if (type === 'bezier') return { points: [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 0, outTangent: 0 }] };
  if (customClassSchemas && customClassSchemas[type]) {
    const obj = {};
    customClassSchemas[type].forEach(f => { obj[f.name] = getDefaultValueForType(f.type, ctx); });
    return obj;
  }
  if (classSchemas && classSchemas[type]) {
    const obj = {};
    classSchemas[type].forEach(f => { obj[f.name] = getDefaultValueForType(f.type, ctx); });
    return obj;
  }
  if (enumValues && enumValues[type]) return `${type}ID.None`;
  return null;
}

// ============================================================
// 数値/文字列 入力（IME・先頭ゼロ対策の簡易版）
// ============================================================
function NumericField({ value, onChange, allowDecimal = true, min, max, ...props }) {
  const [text, setText] = useState(() => (value ?? 0).toString());
  const focused = useRef(false);
  useEffect(() => { if (!focused.current) setText((value ?? 0).toString()); }, [value]);
  return (
    <TextField
      {...props}
      size="small"
      value={text}
      onFocus={() => { focused.current = true; }}
      onChange={(e) => {
        let s = e.target.value.replace(allowDecimal ? /[^0-9.\-]/g : /[^0-9\-]/g, '');
        setText(s);
        const n = allowDecimal ? parseFloat(s) : parseInt(s, 10);
        if (!isNaN(n)) {
          let clamped = n;
          if (min !== undefined && min !== null) clamped = Math.max(min, clamped);
          if (max !== undefined && max !== null) clamped = Math.min(max, clamped);
          onChange(clamped);
        }
      }}
      onBlur={() => {
        focused.current = false;
        const n = allowDecimal ? parseFloat(text) : parseInt(text, 10);
        const v = isNaN(n) ? 0 : n;
        setText(v.toString());
        onChange(v);
      }}
    />
  );
}

// ============================================================
// bit エディタ: チェックボックス（複数選択/排他選択/全選択）
// 右側に縦一列のスクロール可能なリストとして配置し、検索で絞り込める。
// ============================================================
function BitFieldEditor({ value, options, onChange }) {
  const size = options?.size ?? value?.size ?? 8;
  const flagNames = options?.flagNames && options.flagNames.length === size
    ? options.flagNames
    : Array.from({ length: size }, (_, i) => `Flag${i}`);
  const bits = Array.isArray(value?.bits) ? value.bits : [];
  const isSingle = options?.mode === 'single';
  const [search, setSearch] = useState('');

  const toggle = (i) => {
    if (isSingle) {
      onChange({ size, bits: [i] });
      return;
    }
    const has = bits.includes(i);
    const next = has ? bits.filter(b => b !== i) : [...bits, i];
    onChange({ size, bits: next });
  };

  const entries = useMemo(() => flagNames.map((label, i) => ({ label, i })), [flagNames]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(({ label }) => label.toLowerCase().includes(q));
  }, [entries, search]);

  return (
    <Box sx={{ display: 'flex', border: '1px solid #e0e0e0', borderRadius: 2, overflow: 'hidden', bgcolor: '#fff' }}>
      {/* 左: サマリー + 一括操作 */}
      <Box sx={{ width: 168, flexShrink: 0, p: 1.75, bgcolor: '#f7f8fa', borderRight: '1px solid #eee' }}>
        <Typography variant="caption" color="text.secondary">選択中</Typography>
        <Typography variant="h5" sx={{ fontWeight: 700, lineHeight: 1.2, color: 'primary.main' }}>
          {bits.length}
          <Typography component="span" variant="caption" color="text.secondary"> / {size}</Typography>
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mt: 2 }}>
          {!isSingle && options?.allowSelectAll && (
            <Button size="small" variant="outlined"
              onClick={() => onChange({ size, bits: Array.from({ length: size }, (_, i) => i) })}>
              全選択
            </Button>
          )}
          <Button size="small" variant="outlined" color="secondary" onClick={() => onChange({ size, bits: [] })}>
            クリア
          </Button>
        </Box>
        {isSingle && (
          <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 1.5 }}>
            単一選択モード
          </Typography>
        )}
      </Box>

      {/* 右: 検索 + 縦一列のスクロール可能なフラグ一覧 */}
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ p: 1, borderBottom: '1px solid #eee', bgcolor: '#fff' }}>
          <TextField
            size="small"
            fullWidth
            placeholder={`フラグを検索 (${flagNames.length}件)`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </Box>
        <Box sx={{ maxHeight: 320, overflowY: 'auto' }}>
          {filtered.length === 0 && (
            <Typography variant="caption" color="text.disabled" sx={{ display: 'block', p: 2, textAlign: 'center' }}>
              該当するフラグがありません
            </Typography>
          )}
          {filtered.map(({ label, i }) => {
            const checked = bits.includes(i);
            return (
              <Box
                key={i}
                onClick={() => toggle(i)}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  pl: 0.5,
                  pr: 1.5,
                  py: 0.25,
                  cursor: 'pointer',
                  borderLeft: '3px solid',
                  borderLeftColor: checked ? 'primary.main' : 'transparent',
                  bgcolor: checked ? 'rgba(25, 118, 210, 0.08)' : (i % 2 === 0 ? '#fff' : '#fafafa'),
                  '&:hover': { bgcolor: checked ? 'rgba(25, 118, 210, 0.14)' : '#f0f0f0' },
                }}
              >
                <Checkbox
                  size="small"
                  checked={checked}
                  onChange={() => toggle(i)}
                  onClick={(e) => e.stopPropagation()}
                />
                <Typography
                  variant="body2"
                  sx={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  title={label}
                >
                  {label}
                </Typography>
                <Typography variant="caption" color="text.disabled">#{i}</Typography>
              </Box>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}

// ============================================================
// color エディタ: RGBA パレット
// ============================================================
function toHex(v) {
  return Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0');
}
function ColorFieldEditor({ value, onChange }) {
  const v = value || { r: 1, g: 1, b: 1, a: 1 };
  const hex = `#${toHex(v.r)}${toHex(v.g)}${toHex(v.b)}`;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      <input
        type="color"
        value={hex}
        onChange={(e) => {
          const h = e.target.value;
          onChange({
            r: parseInt(h.slice(1, 3), 16) / 255,
            g: parseInt(h.slice(3, 5), 16) / 255,
            b: parseInt(h.slice(5, 7), 16) / 255,
            a: v.a,
          });
        }}
        style={{ width: 48, height: 36, border: 'none', background: 'none', cursor: 'pointer' }}
      />
      <Box sx={{ width: 200 }}>
        <Typography variant="caption">アルファ: {v.a.toFixed(2)}</Typography>
        <Slider
          size="small" min={0} max={1} step={0.01}
          value={v.a}
          onChange={(e, nv) => onChange({ ...v, a: nv })}
        />
      </Box>
      <Box sx={{ width: 32, height: 32, borderRadius: 1, border: '1px solid #ccc', background: `rgba(${v.r * 255},${v.g * 255},${v.b * 255},${v.a})` }} />
    </Box>
  );
}

// ============================================================
// bezier エディタ: 各点をドラッグ可能なグラフ + タンジェント数値入力
// ============================================================
function hermite(p0, p1, t) {
  const dt = p1.time - p0.time || 1;
  const s = (t - p0.time) / dt;
  const h00 = 2 * s ** 3 - 3 * s ** 2 + 1;
  const h10 = s ** 3 - 2 * s ** 2 + s;
  const h01 = -2 * s ** 3 + 3 * s ** 2;
  const h11 = s ** 3 - s ** 2;
  return h00 * p0.value + h10 * dt * p0.outTangent + h01 * p1.value + h11 * dt * p1.inTangent;
}

function BezierFieldEditor({ value, options, onChange }) {
  const points = (value?.points && value.points.length >= 2)
    ? [...value.points].sort((a, b) => a.time - b.time)
    : [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 0, outTangent: 0 }];
  const min = options?.min ?? 0;
  const max = options?.max ?? 1;
  const W = 420, H = 220, PAD = 24;
  const svgRef = useRef(null);
  const [dragIndex, setDragIndex] = useState(null);

  const xToPx = (t) => PAD + t * (W - 2 * PAD);
  const yToPx = (v) => H - PAD - ((v - min) / (max - min || 1)) * (H - 2 * PAD);
  const pxToX = (px) => Math.max(0, Math.min(1, (px - PAD) / (W - 2 * PAD)));
  const pxToY = (py) => {
    const t = (H - PAD - py) / (H - 2 * PAD);
    return min + t * (max - min);
  };

  const pathD = useMemo(() => {
    let d = '';
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i], p1 = points[i + 1];
      const steps = 24;
      for (let s = 0; s <= steps; s++) {
        const t = p0.time + (p1.time - p0.time) * (s / steps);
        const v = hermite(p0, p1, t);
        const cmd = (i === 0 && s === 0) ? 'M' : 'L';
        d += `${cmd}${xToPx(t)},${yToPx(v)} `;
      }
    }
    return d;
  }, [points]);

  const updatePoint = (index, patch) => {
    const next = points.map((p, i) => (i === index ? { ...p, ...patch } : p));
    onChange({ points: next });
  };

  const handleMove = (e) => {
    if (dragIndex === null || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const px = (e.clientX - rect.left) * (W / rect.width);
    const py = (e.clientY - rect.top) * (H / rect.height);
    updatePoint(dragIndex, { time: pxToX(px), value: pxToY(py) });
  };

  const addPoint = () => {
    onChange({ points: [...points, { time: 0.5, value: (min + max) / 2, inTangent: 0, outTangent: 0 }] });
  };
  const removePoint = (index) => {
    if (points.length <= 2) return;
    onChange({ points: points.filter((_, i) => i !== index) });
  };

  return (
    <Box>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ background: '#fafafa', border: '1px solid #ddd', touchAction: 'none' }}
        onMouseMove={handleMove}
        onMouseUp={() => setDragIndex(null)}
        onMouseLeave={() => setDragIndex(null)}
      >
        <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="#bbb" />
        <line x1={PAD} y1={PAD} x2={PAD} y2={H - PAD} stroke="#bbb" />
        <path d={pathD} fill="none" stroke="#1976d2" strokeWidth={2} />
        {points.map((p, i) => (
          <circle
            key={i}
            cx={xToPx(p.time)} cy={yToPx(p.value)} r={6}
            fill={dragIndex === i ? '#d32f2f' : '#1976d2'}
            style={{ cursor: 'grab' }}
            onMouseDown={() => setDragIndex(i)}
          />
        ))}
      </svg>
      <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {points.map((p, i) => (
          <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Chip size="small" label={`点${i}`} />
            <NumericField label="time(0-1)" value={p.time} onChange={(v) => updatePoint(i, { time: Math.max(0, Math.min(1, v)) })} sx={{ width: 100 }} />
            <NumericField label="value" value={p.value} onChange={(v) => updatePoint(i, { value: v })} sx={{ width: 100 }} />
            <NumericField label="inTangent" value={p.inTangent} onChange={(v) => updatePoint(i, { inTangent: v })} sx={{ width: 100 }} />
            <NumericField label="outTangent" value={p.outTangent} onChange={(v) => updatePoint(i, { outTangent: v })} sx={{ width: 100 }} />
            <IconButton size="small" color="error" disabled={points.length <= 2} onClick={() => removePoint(i)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Box>
        ))}
        <Button size="small" startIcon={<AddIcon />} onClick={addPoint} sx={{ alignSelf: 'flex-start' }}>点を追加</Button>
      </Box>
    </Box>
  );
}

// ============================================================
// 通常型（int/float/bool/string/Vector2/Vector3/enum/classData/classDataId）
// ============================================================
function SingleValueEditor({ value, type, ctx, fieldOptions, onChange }) {
  const lower = (type || '').toLowerCase();
  const { enumValues, classSchemas, customClassSchemas } = ctx;

  if (type === 'bit') return <BitFieldEditor value={value} options={fieldOptions} onChange={onChange} />;
  if (type === 'color') return <ColorFieldEditor value={value} onChange={onChange} />;
  if (type === 'bezier') return <BezierFieldEditor value={value} options={fieldOptions} onChange={onChange} />;

  if (customClassSchemas && customClassSchemas[type]) {
    return <CustomClassFieldEditor value={value} typeName={type} ctx={ctx} onChange={onChange} />;
  }

  if (lower === 'bool') {
    return (
      <FormControlLabel
        control={<Checkbox checked={!!value} onChange={(e) => onChange(e.target.checked)} />}
        label={value ? 'true' : 'false'}
      />
    );
  }
  if (lower === 'int') {
    return <NumericField allowDecimal={false} value={value ?? 0} onChange={onChange} min={fieldOptions?.min} max={fieldOptions?.max} fullWidth />;
  }
  if (NUMERIC_TYPES.includes(lower)) {
    return <NumericField allowDecimal={true} value={value ?? 0} onChange={onChange} min={fieldOptions?.min} max={fieldOptions?.max} fullWidth />;
  }
  if (lower === 'string') {
    return <TextField size="small" fullWidth value={value ?? ''} onChange={(e) => onChange(e.target.value)} />;
  }
  if (lower === 'vector2' || lower === 'vector3') {
    const n = lower === 'vector2' ? 2 : 3;
    const arr = Array.isArray(value) && value.length === n ? value : Array(n).fill(0);
    const labels = n === 2 ? ['x', 'y'] : ['x', 'y', 'z'];
    return (
      <Box sx={{ display: 'flex', gap: 1 }}>
        {labels.map((l, i) => (
          <NumericField key={l} label={l} value={arr[i]} onChange={(v) => { const next = [...arr]; next[i] = v; onChange(next); }} sx={{ flex: 1 }} />
        ))}
      </Box>
    );
  }
  if (classSchemas && classSchemas[type]) {
    // ClassData型: フィールド一覧を単純表示（値はJSONで保持）
    return <CustomClassFieldEditor value={value} typeName={type} ctx={ctx} onChange={onChange} schemaOverride={classSchemas[type]} />;
  }
  if (enumValues && enumValues[type]) {
    const options = [`${type}ID.None`, ...enumValues[type].map(v => `${type}ID.${v}`)];
    return (
      <FormControl size="small" fullWidth>
        <Select value={value ?? `${type}ID.None`} onChange={(e) => onChange(e.target.value)}>
          {options.map(opt => <MenuItem key={opt} value={opt}>{opt.split('.').pop()}</MenuItem>)}
        </Select>
      </FormControl>
    );
  }
  return <TextField size="small" fullWidth value={value ?? ''} onChange={(e) => onChange(e.target.value)} />;
}

// ============================================================
// CustomClassData型のネスト編集（各フィールドがそれぞれのオプション付きエディタで編集できる）
// ============================================================
function CustomClassFieldEditor({ value, typeName, ctx, onChange, schemaOverride }) {
  const schema = schemaOverride || ctx.customClassSchemas[typeName] || [];
  const obj = (value && typeof value === 'object' && !Array.isArray(value)) ? value : {};

  return (
    <Box sx={{ border: '1px solid #ddd', borderRadius: 1, p: 1.5 }}>
      <Typography variant="caption" color="text.secondary">{typeName}</Typography>
      {schema.length === 0 && <Typography variant="caption" color="text.disabled" sx={{ display: 'block' }}>フィールドなし</Typography>}
      {schema.map(field => (
        <Box key={field.name} sx={{ mt: 1.5 }}>
          <Typography variant="caption" fontWeight="bold" display="block">
            {field.name}{field.description ? `（${field.description}）` : ''}
            <Chip label={field.type} size="small" sx={{ ml: 0.5, height: 16, fontSize: 10 }} />
          </Typography>
          <SingleValueEditor
            value={obj[field.name] !== undefined ? obj[field.name] : getDefaultValueForType(field.type, ctx)}
            type={field.type}
            ctx={ctx}
            fieldOptions={field.options}
            onChange={(v) => onChange({ ...obj, [field.name]: v })}
          />
        </Box>
      ))}
    </Box>
  );
}

// ============================================================
// メインコンポーネント
// ============================================================
function CustomClassDataIdDetailGrid() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState({ columns: [], rows: [] });
  const [loading, setLoading] = useState(true);
  const [typeInfo, setTypeInfo] = useState({
    basic_types: [], unity_types: [], enum_list: [], class_list: [], class_data_id_list: [],
    custom_class_list: [], custom_class_id_list: [],
  });
  const [enumValues, setEnumValues] = useState({});
  const [classSchemas, setClassSchemas] = useState({});
  const [customClassSchemas, setCustomClassSchemas] = useState({});

  const [openAddColumn, setOpenAddColumn] = useState(false);
  const [newColType, setNewColType] = useState('');
  const [newColName, setNewColName] = useState('');
  const [newColDescription, setNewColDescription] = useState('');
  const [openDeleteColumn, setOpenDeleteColumn] = useState(false);
  const [columnToDelete, setColumnToDelete] = useState('');
  const [openAddRows, setOpenAddRows] = useState(false);
  const [recordCount, setRecordCount] = useState(1);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorCell, setEditorCell] = useState(null); // { rowId, field, type, options }
  const [editorValue, setEditorValue] = useState(null);

  const ctx = useMemo(() => ({ enumValues, classSchemas, customClassSchemas }), [enumValues, classSchemas, customClassSchemas]);

  useEffect(() => {
    if (!name || name.includes(':')) {
      navigate('/custom-class-data-id');
      return;
    }
    setLoading(true);
    fetch(`/api/custom-class-data-id/${encodeURIComponent(name)}`)
      .then(res => res.json())
      .then(fetched => {
        const columns = fetched.columns || [];
        const rows = (fetched.rows || []).map((row, i) => ({
          id: row.id || i + 1,
          enum_property: row.enum_property || `${name}_${i + 1}`,
          description: row.description || '',
          data: row.data || {},
        }));
        setData({ columns, rows });
        setLoading(false);
      })
      .catch(error => {
        console.error(error);
        alert('データ取得エラー: ' + error.message);
        setLoading(false);
      });

    fetch('/api/custom-class-data-type-options')
      .then(res => res.json())
      .then(info => {
        setTypeInfo(info);
        setCustomClassSchemas(info.custom_class_schemas || {});

        const enumPromises = info.enum_list.map(n =>
          fetch(`/api/enum/${encodeURIComponent(n)}`).then(r => r.ok ? r.json() : [])
            .then(d => ({ [n]: (d || []).map(r => r.property) })));
        const classIdPromises = info.class_data_id_list.map(n =>
          fetch(`/api/class-data-id/${encodeURIComponent(n)}`).then(r => r.ok ? r.json() : { rows: [] })
            .then(d => ({ [n]: (d.rows || []).map(r => r.enum_property) })));
        // 他の CustomClassDataID を参照するカラム用に、そちらの enum_property 一覧も取得する
        const customClassIdPromises = (info.custom_class_id_list || []).map(n =>
          fetch(`/api/custom-class-data-id/${encodeURIComponent(n)}`).then(r => r.ok ? r.json() : { rows: [] })
            .then(d => ({ [n]: (d.rows || []).map(r => r.enum_property) })));
        const classSchemaPromises = info.class_list.map(n =>
          fetch(`/api/class-data/${encodeURIComponent(n)}`).then(r => r.ok ? r.json() : [])
            .then(d => ({ [n]: Array.isArray(d) ? d : [] })));

        Promise.all([Promise.all(enumPromises), Promise.all(classIdPromises), Promise.all(customClassIdPromises), Promise.all(classSchemaPromises)])
          .then(([e, c, ci, s]) => {
            setEnumValues(Object.assign({}, ...e, ...c, ...ci));
            setClassSchemas(Object.assign({}, ...s));
          });
      })
      .catch(error => console.error('型情報取得エラー:', error));
  }, [name, navigate]);

  const typeOptions = useMemo(() => {
    const base = [
      ...typeInfo.basic_types, ...typeInfo.unity_types,
      ...typeInfo.enum_list, ...typeInfo.class_list, ...typeInfo.class_data_id_list,
      ...typeInfo.custom_class_list, ...typeInfo.custom_class_id_list,
    ];
    return Array.from(new Set([...base, ...base.map(t => `${t}[]`)]));
  }, [typeInfo]);

  const getDefault = useCallback((type) => {
    const { isArray, baseType } = parseType(type);
    return isArray ? [] : getDefaultValueForType(baseType, ctx);
  }, [ctx]);

  const gridRows = useMemo(() => data.rows.map(row => {
    const r = { id: row.id, enum_property: row.enum_property, description: row.description };
    data.columns.forEach(col => { r[col.name] = row.data?.[col.name]?.value ?? getDefault(col.type); });
    return r;
  }), [data.rows, data.columns, getDefault]);

  const handleAddColumn = () => {
    if (!newColType.trim() || !newColName.trim()) { alert('型と名前は必須です'); return; }
    if (data.columns.some(c => c.name === newColName)) { alert('カラム名が重複しています'); return; }
    const column = { type: newColType, name: newColName, description: newColDescription };
    const def = getDefault(newColType);
    const rows = data.rows.map(row => ({ ...row, data: { ...row.data, [newColName]: { value: def, type: newColType } } }));
    setData({ columns: [...data.columns, column], rows });
    setOpenAddColumn(false);
    setNewColType(''); setNewColName(''); setNewColDescription('');
  };

  const handleDeleteColumn = (colName) => {
    const columns = data.columns.filter(c => c.name !== colName);
    const rows = data.rows.map(row => { const d = { ...row.data }; delete d[colName]; return { ...row, data: d }; });
    setData({ columns, rows });
    setOpenDeleteColumn(false); setColumnToDelete('');
  };

  const handleDeleteRow = (rowId) => {
    if (window.confirm('このレコードを削除しますか？')) {
      setData(prev => ({ ...prev, rows: prev.rows.filter(r => r.id !== rowId) }));
    }
  };

  const handleAddRows = () => {
    const maxId = Math.max(0, ...data.rows.map(r => r.id || 0));
    const rows = Array.from({ length: Math.max(1, Number(recordCount) || 1) }, (_, i) => {
      const rowData = {};
      data.columns.forEach(col => { rowData[col.name] = { value: getDefault(col.type), type: col.type }; });
      return { id: maxId + i + 1, enum_property: `${name}_${(maxId + i + 1).toString().padStart(2, '0')}`, description: '', data: rowData };
    });
    setData({ ...data, rows: [...data.rows, ...rows] });
    setOpenAddRows(false); setRecordCount(1);
  };

  const openEditor = (rowId, colName, type) => {
    const row = data.rows.find(r => r.id === rowId);
    const col = data.columns.find(c => c.name === colName);
    const currentValue = row?.data?.[colName]?.value ?? getDefault(type);
    setEditorCell({ rowId, field: colName, type, options: col?.options });
    setEditorValue(currentValue);
    setEditorOpen(true);
  };

  const saveEditor = () => {
    if (!editorCell) return;
    const { rowId, field, type } = editorCell;
    const rows = data.rows.map(row => row.id === rowId
      ? { ...row, data: { ...row.data, [field]: { value: editorValue, type } } }
      : row);
    setData({ ...data, rows });
    setEditorOpen(false); setEditorCell(null); setEditorValue(null);
  };

  const processRowUpdate = (newRow) => {
    const rows = data.rows.map(row => row.id === newRow.id
      ? { ...row, enum_property: newRow.enum_property, description: newRow.description }
      : row);
    setData({ ...data, rows });
    return newRow;
  };

  const handleSave = () => {
    const payload = {
      columns: data.columns,
      rows: data.rows.map(row => ({ id: row.id, enum_property: row.enum_property, description: row.description, data: row.data })),
    };
    fetch(`/api/custom-class-data-id/${encodeURIComponent(name)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    }).then(res => res.json()).then(result => alert(result.message || result.error))
      .catch(error => alert('保存エラー: ' + error.message));
  };

  const handleDelete = () => {
    if (window.confirm(`${name} を削除しますか？`)) {
      fetch(`/api/custom-class-data-id/${encodeURIComponent(name)}`, { method: 'DELETE' })
        .then(res => res.json())
        .then(result => { alert(result.message); navigate('/custom-class-data-id'); })
        .catch(error => alert('削除エラー: ' + error.message));
    }
  };

  const handleGenerateCs = () => {
    const payload = { columns: data.columns, rows: data.rows };
    fetch(`/api/generate-custom-class-data-id/${encodeURIComponent(name)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    }).then(res => res.json()).then(result => alert(result.message || result.error))
      .catch(error => alert('C#生成エラー: ' + error.message));
  };

  const columns = useMemo(() => [
    { field: 'enum_property', headerName: 'Enum Property', width: 160, editable: true },
    { field: 'description', headerName: '説明', width: 180, editable: true },
    {
      field: 'actions', headerName: '操作', width: 80,
      renderCell: (params) => (
        <IconButton size="small" color="error" onClick={() => handleDeleteRow(params.row.id)}><DeleteIcon fontSize="small" /></IconButton>
      ),
    },
    ...data.columns.map(col => ({
      field: col.name,
      width: 220,
      editable: false,
      renderHeader: () => (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, width: '100%' }}>
          <Tooltip title={col.description || ''} disableHoverListener={!col.description}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{col.name}</span>
          </Tooltip>
          <Chip label={col.type} size="small" sx={{ height: 16, fontSize: 10 }} />
          <IconButton size="small" color="error" onClick={() => { setColumnToDelete(col.name); setOpenDeleteColumn(true); }}>
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Box>
      ),
      renderCell: (params) => (
        <Box
          onClick={() => openEditor(params.id, col.name, col.type)}
          sx={{ width: '100%', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 0.5, '&:hover': { bgcolor: 'action.hover' } }}
        >
          <EditIcon fontSize="small" color="action" />
          <Typography variant="caption" noWrap>
            {(() => {
              const v = params.value;
              if (v === null || v === undefined) return '(未設定)';
              if (typeof v === 'object') return JSON.stringify(v);
              return String(v);
            })()}
          </Typography>
        </Box>
      ),
    })),
  ], [data.columns]);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>CustomClassDataID詳細: {name}</Typography>
      <Box sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 1 }}>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenAddColumn(true)}>カラム追加</Button>
        <Button variant="contained" onClick={() => setOpenAddRows(true)}>レコード追加</Button>
        <Button variant="contained" onClick={handleSave}>保存</Button>
        <Button variant="contained" color="secondary" onClick={handleGenerateCs}>C#生成</Button>
        <Button variant="contained" color="error" onClick={handleDelete}>削除</Button>
      </Box>

      {loading ? <Typography>読み込み中...</Typography> : (
        <div style={{ width: '100%' }}>
          <DataGrid
            rows={gridRows}
            columns={columns}
            pageSizeOptions={[10]}
            getRowId={(row) => row.id}
            processRowUpdate={processRowUpdate}
            onProcessRowUpdateError={(e) => console.error(e)}
            editMode="cell"
          />
        </div>
      )}

      {/* カラム追加 */}
      <Dialog open={openAddColumn} onClose={() => setOpenAddColumn(false)}>
        <DialogTitle>新しいカラムを追加</DialogTitle>
        <DialogContent>
          <Autocomplete
            options={typeOptions}
            value={newColType}
            onChange={(e, v) => setNewColType(v || '')}
            renderInput={(params) => <TextField {...params} label="型（基本型/Enum/ClassData/ClassDataID/CustomClassData、末尾[]で配列）" margin="dense" fullWidth />}
          />
          <TextField label="名前" margin="dense" fullWidth value={newColName} onChange={(e) => setNewColName(e.target.value)} />
          <TextField label="説明" margin="dense" fullWidth value={newColDescription} onChange={(e) => setNewColDescription(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddColumn(false)}>キャンセル</Button>
          <Button onClick={handleAddColumn}>追加</Button>
        </DialogActions>
      </Dialog>

      {/* カラム削除 */}
      <Dialog open={openDeleteColumn} onClose={() => setOpenDeleteColumn(false)}>
        <DialogTitle>カラム削除</DialogTitle>
        <DialogContent><Typography>カラム {columnToDelete} を削除しますか？</Typography></DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDeleteColumn(false)}>いいえ</Button>
          <Button onClick={() => handleDeleteColumn(columnToDelete)}>はい</Button>
        </DialogActions>
      </Dialog>

      {/* レコード追加 */}
      <Dialog open={openAddRows} onClose={() => setOpenAddRows(false)}>
        <DialogTitle>レコードを追加</DialogTitle>
        <DialogContent>
          <NumericField label="件数" allowDecimal={false} value={recordCount} onChange={setRecordCount} fullWidth />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddRows(false)}>キャンセル</Button>
          <Button onClick={handleAddRows}>作成</Button>
        </DialogActions>
      </Dialog>

      {/* セル編集ダイアログ（型・オプションに応じたエディタを出し分け） */}
      <Dialog
        open={editorOpen}
        onClose={(event, reason) => {
          if (reason === 'backdropClick' || reason === 'escapeKeyDown') {
            // ダイアログ外クリック/Escapeでの意図しない破棄を防ぐため、保存するか確認する
            if (window.confirm('変更を保存しますか？\n（キャンセルすると変更は破棄されます）')) {
              saveEditor();
            } else {
              setEditorOpen(false);
              setEditorCell(null);
              setEditorValue(null);
            }
            return;
          }
          setEditorOpen(false);
        }}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          値を編集 {editorCell ? `- ${editorCell.field} (${editorCell.type})` : ''}
        </DialogTitle>
        <DialogContent sx={{ pt: 2, minHeight: 260 }}>
          {editorCell && (() => {
            const { isArray, baseType } = parseType(editorCell.type);
            if (isArray) {
              const arr = Array.isArray(editorValue) ? editorValue : [];
              return (
                <Box>
                  {arr.map((item, i) => (
                    <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', mb: 1 }}>
                      <Chip label={`[${i}]`} size="small" />
                      <Box sx={{ flex: 1 }}>
                        <SingleValueEditor
                          value={item} type={baseType} ctx={ctx} fieldOptions={editorCell.options}
                          onChange={(v) => { const next = [...arr]; next[i] = v; setEditorValue(next); }}
                        />
                      </Box>
                      <IconButton size="small" color="error" onClick={() => setEditorValue(arr.filter((_, idx) => idx !== i))}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  ))}
                  <Button size="small" startIcon={<AddIcon />} onClick={() => setEditorValue([...arr, getDefaultValueForType(baseType, ctx)])}>
                    要素を追加
                  </Button>
                </Box>
              );
            }
            return (
              <SingleValueEditor
                value={editorValue} type={editorCell.type} ctx={ctx} fieldOptions={editorCell.options}
                onChange={setEditorValue}
              />
            );
          })()}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditorOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={saveEditor}>保存</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default CustomClassDataIdDetailGrid;