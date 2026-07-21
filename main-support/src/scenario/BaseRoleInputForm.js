import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
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
  Divider,
  Slider,
  Button
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import DeleteIcon from '@mui/icons-material/Delete';
import DragHandleIcon from '@mui/icons-material/DragHandle';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';

// Vector のラベル定義
const VECTOR_AXIS_LABELS = {
  vector2: ['X', 'Y'],
  vector3: ['X', 'Y', 'Z'],
  vector4: ['X', 'Y', 'Z', 'W'],
};

// ============================================================
// bit / color / bezier 値エディタ
// (CustomClassDataIdDetailGrid.js の編集UIと同じ挙動・データ形式に揃えてある)
// ============================================================
function BitValueEditor({ value, options, onChange }) {
  const size = options?.size ?? value?.size ?? 8;
  const flagNames = options?.flagNames && options.flagNames.length === size
    ? options.flagNames
    : Array.from({ length: size }, (_, i) => `Flag${i}`);
  const bits = Array.isArray(value?.bits) ? value.bits : [];
  const isSingle = options?.mode === 'single';
  const [search, setSearch] = useState('');

  const toggle = (i) => {
    if (isSingle) { onChange({ size, bits: [i] }); return; }
    const has = bits.includes(i);
    onChange({ size, bits: has ? bits.filter(b => b !== i) : [...bits, i] });
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
      <Box sx={{ width: 160, flexShrink: 0, p: 1.5, bgcolor: '#f7f8fa', borderRight: '1px solid #eee' }}>
        <Typography variant="caption" color="text.secondary">選択中</Typography>
        <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2, color: 'primary.main' }}>
          {bits.length}
          <Typography component="span" variant="caption" color="text.secondary"> / {size}</Typography>
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mt: 1.5 }}>
          {!isSingle && options?.allowSelectAll && (
            <Button size="small" variant="outlined" onClick={() => onChange({ size, bits: Array.from({ length: size }, (_, i) => i) })}>全選択</Button>
          )}
          <Button size="small" variant="outlined" color="secondary" onClick={() => onChange({ size, bits: [] })}>クリア</Button>
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
        <Box sx={{ maxHeight: 220, overflowY: 'auto' }}>
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
                  display: 'flex', alignItems: 'center', gap: 1, pl: 0.5, pr: 1.5, py: 0.25, cursor: 'pointer',
                  borderLeft: '3px solid',
                  borderLeftColor: checked ? 'primary.main' : 'transparent',
                  bgcolor: checked ? 'rgba(25, 118, 210, 0.08)' : (i % 2 === 0 ? '#fff' : '#fafafa'),
                  '&:hover': { bgcolor: checked ? 'rgba(25, 118, 210, 0.14)' : '#f0f0f0' },
                }}
              >
                <Checkbox size="small" checked={checked} onChange={() => toggle(i)} onClick={(e) => e.stopPropagation()} />
                <Typography variant="body2" sx={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={label}>{label}</Typography>
                <Typography variant="caption" color="text.disabled">#{i}</Typography>
              </Box>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}

function toHex(v) {
  return Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0');
}
function ColorValueEditor({ value, onChange }) {
  const v = value && typeof value === 'object' ? value : { r: 1, g: 1, b: 1, a: 1 };
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
        style={{ width: 44, height: 32, border: 'none', background: 'none', cursor: 'pointer' }}
      />
      <Box sx={{ width: 160 }}>
        <Typography variant="caption">アルファ: {(v.a ?? 1).toFixed(2)}</Typography>
        <Slider size="small" min={0} max={1} step={0.01} value={v.a ?? 1} onChange={(e, nv) => onChange({ ...v, a: nv })} />
      </Box>
      <Box sx={{ width: 28, height: 28, borderRadius: 1, border: '1px solid #ccc', background: `rgba(${v.r * 255},${v.g * 255},${v.b * 255},${v.a})` }} />
    </Box>
  );
}

function hermite(p0, p1, t) {
  const dt = p1.time - p0.time || 1;
  const s = (t - p0.time) / dt;
  const h00 = 2 * s ** 3 - 3 * s ** 2 + 1;
  const h10 = s ** 3 - 2 * s ** 2 + s;
  const h01 = -2 * s ** 3 + 3 * s ** 2;
  const h11 = s ** 3 - s ** 2;
  return h00 * p0.value + h10 * dt * p0.outTangent + h01 * p1.value + h11 * dt * p1.inTangent;
}
// タンジェントハンドルの画面上の長さ（px固定。角度だけが傾き値を表す）
const TANGENT_HANDLE_LEN = 40;
// ハンドルドラッグ時、傾き計算が発散しないようx方向オフセットの最小値をpxで確保する
const TANGENT_MIN_DX = 10;

function BezierValueEditor({ value, options, onChange }) {
  const points = (value?.points && value.points.length >= 2)
    ? [...value.points].sort((a, b) => a.time - b.time)
    : [{ time: 0, value: options?.min ?? 0, inTangent: 0, outTangent: 0 }, { time: 1, value: options?.max ?? 1, inTangent: 0, outTangent: 0 }];
  const min = options?.min ?? 0;
  const max = options?.max ?? 1;
  const W = 360, H = 180, PAD = 20;
  const svgRef = useRef(null);
  const [dragIndex, setDragIndex] = useState(null);
  // アクティブ（選択中）な点。選択されている間、その点の左右にタンジェントハンドルを表示する
  const [activeIndex, setActiveIndex] = useState(null);
  // タンジェントハンドルのドラッグ状態: { index, side: 'in' | 'out' }
  const [dragHandle, setDragHandle] = useState(null);

  const sx = (W - PAD * 2); // px per unit time (time範囲は0-1)
  const sy = (H - PAD * 2) / ((max - min) || 1); // px per unit value

  const xToPx = (t) => PAD + t * (W - PAD * 2);
  const yToPx = (v) => H - PAD - ((v - min) / ((max - min) || 1)) * (H - PAD * 2);
  const pxToX = (px) => Math.max(0, Math.min(1, (px - PAD) / (W - PAD * 2)));
  const pxToY = (py) => min + (1 - (py - PAD) / (H - PAD * 2)) * (max - min);

  // タンジェント値 -> ハンドルの点からの相対オフセット（画面上の長さは固定）
  const tangentToHandleOffset = (tangent, side) => {
    const dtime = side === 'out' ? 1 : -1;
    const dvalue = side === 'out' ? tangent : -tangent;
    let dx = sx * dtime;
    let dy = -sy * dvalue;
    const len = Math.hypot(dx, dy) || 1;
    return { dx: (dx / len) * TANGENT_HANDLE_LEN, dy: (dy / len) * TANGENT_HANDLE_LEN };
  };

  // ハンドルの相対オフセット -> タンジェント値
  const handleOffsetToTangent = (dx, dy, side) => {
    const minDx = side === 'out' ? TANGENT_MIN_DX : -TANGENT_MIN_DX;
    const clampedDx = side === 'out' ? Math.max(dx, minDx) : Math.min(dx, minDx);
    return -(dy * sx) / (clampedDx * sy);
  };

  const pathD = useMemo(() => {
    let d = '';
    const steps = 24;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i], p1 = points[i + 1];
      for (let s = 0; s <= steps; s++) {
        const t = p0.time + (p1.time - p0.time) * (s / steps);
        const v = hermite(p0, p1, t);
        d += `${(i === 0 && s === 0) ? 'M' : 'L'}${xToPx(t)},${yToPx(v)} `;
      }
    }
    return d;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points]);

  const updatePoint = (index, patch) => onChange({ points: points.map((p, i) => (i === index ? { ...p, ...patch } : p)) });
  const handleMove = (e) => {
    if (!svgRef.current) return;
    if (dragIndex === null && dragHandle === null) return;
    const rect = svgRef.current.getBoundingClientRect();
    const px = (e.clientX - rect.left) * (W / rect.width);
    const py = (e.clientY - rect.top) * (H / rect.height);
    if (dragIndex !== null) {
      updatePoint(dragIndex, { time: pxToX(px), value: pxToY(py) });
      return;
    }
    if (dragHandle !== null) {
      const p = points[dragHandle.index];
      const cx = xToPx(p.time), cy = yToPx(p.value);
      const tangent = handleOffsetToTangent(px - cx, py - cy, dragHandle.side);
      updatePoint(dragHandle.index, { [`${dragHandle.side}Tangent`]: tangent });
    }
  };
  const endDrag = () => { setDragIndex(null); setDragHandle(null); };
  const addPoint = () => onChange({ points: [...points, { time: 0.5, value: (min + max) / 2, inTangent: 0, outTangent: 0 }] });
  const removePoint = (index) => {
    if (points.length <= 2) return;
    if (activeIndex === index) setActiveIndex(null);
    onChange({ points: points.filter((_, i) => i !== index) });
  };

  return (
    <Box>
      <svg
        ref={svgRef} viewBox={`0 0 ${W} ${H}`} width="100%"
        style={{ background: '#fafafa', border: '1px solid #ddd', touchAction: 'none' }}
        onMouseMove={handleMove} onMouseUp={endDrag} onMouseLeave={endDrag}
      >
        <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="#bbb" />
        <line x1={PAD} y1={PAD} x2={PAD} y2={H - PAD} stroke="#bbb" />
        <path d={pathD} fill="none" stroke="#1976d2" strokeWidth={2} />
        {points.map((p, i) => {
          const cx = xToPx(p.time), cy = yToPx(p.value);
          const isActive = activeIndex === i;
          const inOff = tangentToHandleOffset(p.inTangent ?? 0, 'in');
          const outOff = tangentToHandleOffset(p.outTangent ?? 0, 'out');
          const inPos = { x: cx + inOff.dx, y: cy + inOff.dy };
          const outPos = { x: cx + outOff.dx, y: cy + outOff.dy };
          return (
            <g key={i}>
              {isActive && (
                <>
                  <line x1={cx} y1={cy} x2={inPos.x} y2={inPos.y} stroke="#43a047" strokeWidth={1.5} strokeDasharray="3,2" />
                  <line x1={cx} y1={cy} x2={outPos.x} y2={outPos.y} stroke="#fb8c00" strokeWidth={1.5} strokeDasharray="3,2" />
                  <circle
                    cx={inPos.x} cy={inPos.y} r={5}
                    fill={dragHandle?.index === i && dragHandle?.side === 'in' ? '#2e7d32' : '#66bb6a'}
                    stroke="#fff" strokeWidth={1}
                    style={{ cursor: 'grab' }}
                    onMouseDown={(e) => { e.stopPropagation(); setDragHandle({ index: i, side: 'in' }); }}
                  />
                  <circle
                    cx={outPos.x} cy={outPos.y} r={5}
                    fill={dragHandle?.index === i && dragHandle?.side === 'out' ? '#e65100' : '#ffa726'}
                    stroke="#fff" strokeWidth={1}
                    style={{ cursor: 'grab' }}
                    onMouseDown={(e) => { e.stopPropagation(); setDragHandle({ index: i, side: 'out' }); }}
                  />
                </>
              )}
              <circle cx={cx} cy={cy} r={isActive ? 6 : 5}
                fill={dragIndex === i ? '#d32f2f' : (isActive ? '#1565c0' : '#1976d2')}
                stroke={isActive ? '#0d47a1' : 'none'} strokeWidth={isActive ? 2 : 0}
                style={{ cursor: 'grab' }}
                onMouseDown={(e) => { e.stopPropagation(); setActiveIndex(i); setDragIndex(i); }} />
            </g>
          );
        })}
      </svg>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        点をクリックして選択すると、左右にタンジェントハンドル（緑=in / 橙=out）が表示され、ドラッグで傾きを調整できます。
      </Typography>
      <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        {points.map((p, i) => (
          <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Chip
              size="small"
              label={`点${i}`}
              color={activeIndex === i ? 'primary' : 'default'}
              onClick={() => setActiveIndex(i)}
              sx={{ cursor: 'pointer' }}
            />
            <TextField size="small" label="time" type="number" value={p.time} sx={{ width: 90 }}
              onChange={(e) => updatePoint(i, { time: Math.max(0, Math.min(1, parseFloat(e.target.value) || 0)) })} />
            <TextField size="small" label="value" type="number" value={p.value} sx={{ width: 90 }}
              onChange={(e) => updatePoint(i, { value: parseFloat(e.target.value) || 0 })} />
            <TextField size="small" label="inTangent" type="number" value={p.inTangent} sx={{ width: 90 }}
              onChange={(e) => updatePoint(i, { inTangent: parseFloat(e.target.value) || 0 })} />
            <TextField size="small" label="outTangent" type="number" value={p.outTangent} sx={{ width: 90 }}
              onChange={(e) => updatePoint(i, { outTangent: parseFloat(e.target.value) || 0 })} />
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

// ============================================================
// dictionary 値エディタ
// キーは数値のみ（int / Enum / ClassDataID / CustomClassDataID）、値は任意の型
// 値データ形式: { entries: [{ key, value }, ...] }
// ============================================================
function DictionaryScalarEditor({ type, value, options, onChange, enumValues, classDataSchemas, customClassSchemas }) {
  const lower = (type || '').toLowerCase();
  if (lower === 'bit') return <BitValueEditor value={value} options={options} onChange={onChange} />;
  if (lower === 'color') return <ColorValueEditor value={value} onChange={onChange} />;
  if (lower === 'bezier') return <BezierValueEditor value={value} options={options} onChange={onChange} />;
  if (lower === 'bool') {
    return (
      <FormControlLabel
        control={<Checkbox checked={!!value} onChange={(e) => onChange(e.target.checked)} />}
        label={value ? 'true' : 'false'}
      />
    );
  }
  if (['int', 'short', 'long', 'byte'].includes(lower)) {
    return <NumericInput label="" value={value ?? 0} onChange={onChange} isFloat={false} sx={{ width: 100 }} />;
  }
  if (['float', 'double', 'decimal'].includes(lower)) {
    return <NumericInput label="" value={value ?? 0} onChange={onChange} isFloat sx={{ width: 100 }} />;
  }
  if (lower === 'string' || lower === 'char') {
    return <TextField size="small" value={value ?? ''} onChange={(e) => onChange(e.target.value)} sx={{ minWidth: 160 }} />;
  }
  if (VECTOR_AXIS_LABELS[lower]) {
    const labels = VECTOR_AXIS_LABELS[lower];
    const arr = Array.isArray(value) ? value : Array(labels.length).fill(0);
    return (
      <Box sx={{ display: 'flex', gap: 0.5 }}>
        {labels.map((l, i) => (
          <TextField
            key={l} size="small" label={l} type="number" value={arr[i] ?? 0} sx={{ width: 64 }}
            onChange={(e) => { const next = [...arr]; next[i] = parseFloat(e.target.value) || 0; onChange(next); }}
          />
        ))}
      </Box>
    );
  }
  // Enum / ClassDataID / CustomClassDataID
  if (enumValues[type] && enumValues[type].length > 0) {
    const opts = [
      { value: `${type}ID.None`, label: 'None' },
      ...enumValues[type].map(v => {
        const val = typeof v === 'object' ? (v.property || v.enum_property || v) : v;
        return { value: `${type}ID.${val}`, label: val };
      }),
    ];
    return (
      <Autocomplete
        size="small"
        options={opts}
        getOptionLabel={(o) => o.label}
        value={opts.find(o => o.value === value) || null}
        onChange={(e, nv) => onChange(nv ? nv.value : `${type}ID.None`)}
        renderInput={(params) => <TextField {...params} size="small" />}
        isOptionEqualToValue={(o, v) => o.value === v?.value}
        sx={{ minWidth: 180 }}
      />
    );
  }
  // CustomClassData / ClassData (ネストしたオブジェクト)
  const nestedSchema = customClassSchemas[type] || classDataSchemas[type];
  if (nestedSchema && nestedSchema.length > 0) {
    const subSchema = {
      fields: nestedSchema.map(sub => ({
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
      <BaseRoleInputForm
        schema={subSchema}
        initialData={subInitialData}
        onChange={(subData) => {
          const newObj = subData.reduce((acc, { name, value: v }) => { acc[name] = v; return acc; }, {});
          onChange(newObj);
        }}
      />
    );
  }
  return <TextField size="small" value={value ?? ''} onChange={(e) => onChange(e.target.value)} sx={{ minWidth: 160 }} />;
}

function DictionaryKeyEditor({ keyValue, keyType, enumValues, onChange }) {
  if ((keyType || 'int').toLowerCase() === 'int') {
    return <NumericInput label="" value={keyValue ?? 0} onChange={onChange} isFloat={false} sx={{ width: 100 }} />;
  }
  const opts = (enumValues && enumValues[keyType]) || [];
  const options = [
    { value: `${keyType}ID.None`, label: 'None' },
    ...opts.map(v => {
      const val = typeof v === 'object' ? (v.property || v.enum_property || v) : v;
      return { value: `${keyType}ID.${val}`, label: val };
    }),
  ];
  return (
    <Autocomplete
      size="small"
      options={options}
      getOptionLabel={(o) => o.label}
      value={options.find(o => o.value === keyValue) || null}
      onChange={(e, nv) => onChange(nv ? nv.value : `${keyType}ID.None`)}
      renderInput={(params) => <TextField {...params} size="small" />}
      isOptionEqualToValue={(o, v) => o.value === v?.value}
      sx={{ minWidth: 160 }}
    />
  );
}

function defaultDictScalar(t, enumValues, classDataSchemas, customClassSchemas) {
  const lower = (t || '').toLowerCase();
  if (['int', 'short', 'long', 'byte'].includes(lower)) return 0;
  if (['float', 'double', 'decimal'].includes(lower)) return 0.0;
  if (lower === 'bool') return false;
  if (lower === 'string' || lower === 'char') return '';
  if (VECTOR_AXIS_LABELS[lower]) return Array(VECTOR_AXIS_LABELS[lower].length).fill(0);
  if (lower === 'bit') return { size: 8, bits: [] };
  if (lower === 'color') return { r: 1, g: 1, b: 1, a: 1 };
  if (lower === 'bezier') return { points: [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 0, outTangent: 0 }] };
  if (enumValues[t] && enumValues[t].length > 0) return `${t}ID.None`;
  if (customClassSchemas[t] || classDataSchemas[t]) return {};
  return '';
}

function DictionaryValueEditor({ value, options, onChange, enumValues, classDataSchemas, customClassSchemas }) {
  const keyType = options?.keyType || 'int';
  const valueType = options?.valueType || 'int';
  const valueArraySize = options?.valueArraySize ?? 0;
  const valueIsArray = valueArraySize !== 0;
  const valueOptions = options?.valueOptions || {};
  const entries = Array.isArray(value?.entries) ? value.entries : [];

  const updateEntries = (next) => onChange({ entries: next });
  const updateKey = (i, k) => updateEntries(entries.map((e, idx) => (idx === i ? { ...e, key: k } : e)));
  const updateValue = (i, v) => updateEntries(entries.map((e, idx) => (idx === i ? { ...e, value: v } : e)));
  const removeEntry = (i) => updateEntries(entries.filter((_, idx) => idx !== i));

  const addEntry = () => {
    const defaultKey = keyType.toLowerCase() === 'int' ? 0 : `${keyType}ID.None`;
    const defaultVal = valueIsArray ? [] : defaultDictScalar(valueType, enumValues, classDataSchemas, customClassSchemas);
    updateEntries([...entries, { key: defaultKey, value: defaultVal }]);
  };
  const addArrayItem = (entryIdx) => {
    const arr = Array.isArray(entries[entryIdx].value) ? entries[entryIdx].value : [];
    updateValue(entryIdx, [...arr, defaultDictScalar(valueType, enumValues, classDataSchemas, customClassSchemas)]);
  };
  const removeArrayItem = (entryIdx, itemIdx) => {
    const arr = Array.isArray(entries[entryIdx].value) ? entries[entryIdx].value : [];
    updateValue(entryIdx, arr.filter((_, i) => i !== itemIdx));
  };
  const updateArrayItem = (entryIdx, itemIdx, v) => {
    const arr = Array.isArray(entries[entryIdx].value) ? [...entries[entryIdx].value] : [];
    arr[itemIdx] = v;
    updateValue(entryIdx, arr);
  };

  return (
    <Box sx={{ border: '1px solid #e0e0e0', borderRadius: 1, p: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          {entries.length}件 / Dictionary&lt;{keyType}, {valueType}{valueIsArray ? '[]' : ''}&gt;
        </Typography>
        <Button size="small" startIcon={<AddIcon />} onClick={addEntry}>エントリを追加</Button>
      </Box>
      {entries.length === 0 && (
        <Typography variant="caption" color="text.disabled" sx={{ display: 'block', py: 1, textAlign: 'center' }}>
          エントリがありません
        </Typography>
      )}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {entries.map((entry, i) => (
          <Box key={i} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, p: 0.5, border: '1px solid #f0f0f0', borderRadius: 1 }}>
            <Box sx={{ pt: 0.5 }}>
              <DictionaryKeyEditor keyValue={entry.key} keyType={keyType} enumValues={enumValues} onChange={(v) => updateKey(i, v)} />
            </Box>
            <Typography variant="caption" sx={{ pt: 1 }}>:</Typography>
            <Box sx={{ flex: 1 }}>
              {valueIsArray ? (
                <Box>
                  {(Array.isArray(entry.value) ? entry.value : []).map((item, itemIdx) => (
                    <Box key={itemIdx} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Typography variant="caption" sx={{ minWidth: 20, color: 'text.secondary' }}>[{itemIdx}]</Typography>
                      <DictionaryScalarEditor
                        type={valueType} value={item} options={valueOptions}
                        onChange={(v) => updateArrayItem(i, itemIdx, v)}
                        enumValues={enumValues} classDataSchemas={classDataSchemas} customClassSchemas={customClassSchemas}
                      />
                      <IconButton size="small" color="error" onClick={() => removeArrayItem(i, itemIdx)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  ))}
                  <Button size="small" startIcon={<AddIcon />} onClick={() => addArrayItem(i)}>要素を追加</Button>
                </Box>
              ) : (
                <DictionaryScalarEditor
                  type={valueType} value={entry.value} options={valueOptions}
                  onChange={(v) => updateValue(i, v)}
                  enumValues={enumValues} classDataSchemas={classDataSchemas} customClassSchemas={customClassSchemas}
                />
              )}
            </Box>
            <IconButton size="small" color="error" onClick={() => removeEntry(i)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

const BaseRoleInputForm = ({ schema, initialData, onChange }) => {
  const [formData, setFormData] = useState(initialData || []);
  const [enumValues, setEnumValues] = useState({});
  const [classDataSchemas, setClassDataSchemas] = useState({});
  const [customClassSchemas, setCustomClassSchemas] = useState({}); // CustomClassData (ネストしたオブジェクト。bit/color/bezierフィールドを含みうる)
  const [isLoading, setIsLoading] = useState(true);

  const getDefaultValue = useCallback((type, arraySize, options) => {
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
          if (type === 'bit') return { size: options?.size ?? 8, bits: [] };
          if (type === 'color') return { r: 1, g: 1, b: 1, a: 1 };
          if (type === 'bezier') return { points: [{ time: 0, value: options?.min ?? 0, inTangent: 0, outTangent: 0 }, { time: 1, value: options?.max ?? 1, inTangent: 0, outTangent: 0 }] };
          if (type === 'dictionary') return { entries: [] };
          if (type in customClassSchemas) {
            const obj = {};
            (customClassSchemas[type] || []).forEach(f => { obj[f.name] = getDefaultValue(f.type, f.arraySize, f.options); });
            return obj;
          }
          if (type in enumValues && enumValues[type].length > 0) return `${type}ID.None`;
          if (type in classDataSchemas && classDataSchemas[type].length > 0) return `${type}ID.None`;
          return '';
      }
    };
    if (arraySize === undefined || arraySize === 0) return baseDefault();
    if (arraySize > 0) return Array.from({ length: arraySize }, () => baseDefault());
    if (arraySize === -1) return [];
    return baseDefault();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enumValues, classDataSchemas, customClassSchemas]);

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
        const [enumListRes, classIdListRes, classDataListRes, customOptionsRes] = await Promise.all([
          fetch('/api/enum-id'),
          fetch('/api/class-data-id'),
          fetch('/api/class-data'),
          fetch('/api/custom-class-data-type-options'),
        ]);
        const enumList = enumListRes.ok ? await enumListRes.json() : [];
        const classIdList = classIdListRes.ok ? await classIdListRes.json() : [];
        const classDataList = classDataListRes.ok ? await classDataListRes.json() : [];
        const customOptions = customOptionsRes.ok ? await customOptionsRes.json() : {};
        const customClassIdList = customOptions.custom_class_id_list || [];
        // custom_class_schemas はすでにフィールド一覧(bit/color/bezierのoptions込み)が
        // まとまって返ってくるので、CustomClassData型は個別フェッチ不要でそのまま使える。
        setCustomClassSchemas(customOptions.custom_class_schemas || {});

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

        // CustomClassDataID: class_data_id と同じくID参照。値候補(enum_property一覧)を取得する。
        const customClassIdPromises = customClassIdList
          .filter(name => types.includes(name))
          .map(async name => {
            const res = await fetch(`/api/custom-class-data-id/${encodeURIComponent(name)}`);
            const data = res.ok ? await res.json() : { rows: [] };
            return { [name]: (data.rows || []).map(r => r.enum_property) };
          });

        const results = await Promise.all([...enumPromises, ...classIdPromises, ...classDataPromises, ...customClassIdPromises]);
        const valuesMap = results.reduce((acc, curr) => ({ ...acc, ...curr }), {});

        const enumMap = {};
        const classDataMap = {};
        Object.keys(valuesMap).forEach(key => {
          if (classDataList.some(item => item.name === key)) {
            classDataMap[key] = valuesMap[key];
          } else {
            // enum / class_data_id / custom_class_data_id はすべて「候補から選ぶID」なので
            // 同じ enumValues 側にまとめる(CustomClassFieldEditor同様の描画を再利用するため)
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
      // bit / color / bezier (CustomClassDataの拡張型)
      if (field.type === 'bit') {
        return <BitValueEditor key={key} value={value} options={field.options} onChange={onValueChange} />;
      }
      if (field.type === 'color') {
        return <ColorValueEditor key={key} value={value} onChange={onValueChange} />;
      }
      if (field.type === 'bezier') {
        return <BezierValueEditor key={key} value={value} options={field.options} onChange={onValueChange} />;
      }
      if (field.type === 'dictionary') {
        return (
          <DictionaryValueEditor
            key={key}
            value={value}
            options={field.options}
            onChange={onValueChange}
            enumValues={enumValues}
            classDataSchemas={classDataSchemas}
            customClassSchemas={customClassSchemas}
          />
        );
      }

      // CustomClassData (ネストしたオブジェクト。中にbit/color/bezierを含んでもよい)
      if (customClassSchemas[field.type] && customClassSchemas[field.type].length > 0) {
        const subSchema = {
          fields: customClassSchemas[field.type].map(sub => ({
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
          <Paper key={key} variant="outlined" sx={{ p: 1.5, mb: 1, bgcolor: 'secondary.50' }}>
            <Typography variant="caption" fontWeight="bold" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
              {field.label || field.name} <Chip label="CustomClass" size="small" color="secondary" sx={{ ml: 0.5, height: 16, fontSize: '0.6rem' }} />
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

      // Enum / class_data_id / custom_class_data_id (すべてID候補から選ぶ形なので同じ描画)
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