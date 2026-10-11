import React, { useMemo, useState } from 'react';
import {
  Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControl,
  FormControlLabel, InputLabel, MenuItem, Radio, RadioGroup, Select, TextField, Typography,
} from '@mui/material';

// インデックス一括調整ダイアログ(GUI/DSLで共用)。
// text_list_index / voice_ref のような「Matrixの何番目か」を指す整数を、あるサブグループから
// 後ろ(終点まで)に対して「+N/-N ずらす」「連番にする」。適用前に変更内容をプレビューする。
// 計算そのものは scenarioIndexTools.js (React非依存)。このコンポーネントは入力とプレビューだけを担当する。
//
// props:
//   startOptions : [{ value, label }]  起点/終点に選べるサブグループ
//   initialStart : 起点の初期値(startOptionsのvalue)
//   getFields    : (includeInt) => [{ roleName, fieldName, type, count }]  対象にできるフィールド
//   makePlan     : ({ start, end, mode, delta, step, base, includeStart, includeInt, target }) => { changes, warnings, error? }
//   describeChange: (change) => { where, field }  プレビュー表の表示用
//   onApply      : (plan) => void
const MAX_PREVIEW_ROWS = 300;

export default function ScenarioIndexToolsDialog({
  open, onClose, title = 'インデックス一括調整', startOptions, initialStart, getFields, makePlan, describeChange, onApply,
}) {
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState('');
  const [includeInt, setIncludeInt] = useState(false);
  const [targetKey, setTargetKey] = useState('all');
  const [mode, setMode] = useState('shift');
  const [delta, setDelta] = useState('1');
  const [step, setStep] = useState('1');
  const [base, setBase] = useState('');
  const [includeStart, setIncludeStart] = useState(true);

  const fields = useMemo(() => getFields(includeInt), [getFields, includeInt]);
  const target = useMemo(() => {
    if (targetKey === 'all') return 'all';
    const f = fields.find((x) => `${x.roleName}.${x.fieldName}` === targetKey);
    return f ? { roleName: f.roleName, fieldName: f.fieldName } : 'all';
  }, [targetKey, fields]);

  const plan = useMemo(() => makePlan({
    start, end: end || undefined, mode, delta: Number(delta), step: Number(step),
    base: base === '' ? undefined : Number(base), includeStart, includeInt, target,
  }), [makePlan, start, end, mode, delta, step, base, includeStart, includeInt, target]);

  const changeMode = (m) => {
    setMode(m);
    setIncludeStart(m === 'shift'); // ずらす: 起点も含める / 連番: 起点の値から続けるので既定では含めない
  };

  const canApply = !plan.error && plan.changes.length > 0;
  const startIdx = startOptions.findIndex((o) => o.value === start);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Typography variant="body2" color="text.secondary">
          元のMatrixで行が増減したときなどに、サブグループをまたいで番号をまとめて直します。
          -1（未選択）は変更しません。適用前に変更内容を確認できます。
        </Typography>

        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>起点のサブグループ</InputLabel>
            <Select label="起点のサブグループ" value={start} onChange={(e) => { setStart(e.target.value); setEnd(''); }}>
              {startOptions.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>終点（含む）</InputLabel>
            <Select label="終点（含む）" value={end} onChange={(e) => setEnd(e.target.value)} displayEmpty>
              <MenuItem value="">最後まで</MenuItem>
              {startOptions.slice(Math.max(startIdx, 0)).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 260 }}>
            <InputLabel>対象フィールド</InputLabel>
            <Select label="対象フィールド" value={targetKey} onChange={(e) => setTargetKey(e.target.value)}>
              <MenuItem value="all">すべて（text_list_index / voice_ref{includeInt ? ' / int系' : ''}）</MenuItem>
              {fields.map((f) => (
                <MenuItem key={`${f.roleName}.${f.fieldName}`} value={`${f.roleName}.${f.fieldName}`}>
                  {f.roleName}.{f.fieldName}（{f.type} / {f.count}箇所）
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
        <FormControlLabel
          control={<Checkbox size="small" checked={includeInt} onChange={(e) => setIncludeInt(e.target.checked)} />}
          label="int 型のフィールドも対象に含める" sx={{ mt: -1 }}
        />

        <RadioGroup row value={mode} onChange={(e) => changeMode(e.target.value)}>
          <FormControlLabel value="shift" control={<Radio size="small" />} label="ずらす（+N / −N）" />
          <FormControlLabel value="sequence" control={<Radio size="small" />} label="連番にする" />
        </RadioGroup>

        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
          {mode === 'shift' ? (
            <TextField size="small" type="number" label="増減量" value={delta} onChange={(e) => setDelta(e.target.value)} sx={{ width: 140 }}
              helperText="例: 3 / -2" />
          ) : (
            <>
              <TextField size="small" type="number" label="開始値（空=起点の値から）" value={base} onChange={(e) => setBase(e.target.value)} sx={{ width: 240 }} />
              <TextField size="small" type="number" label="増分" value={step} onChange={(e) => setStep(e.target.value)} sx={{ width: 120 }} />
            </>
          )}
          <FormControlLabel
            control={<Checkbox size="small" checked={includeStart} onChange={(e) => setIncludeStart(e.target.checked)} />}
            label={mode === 'shift' ? '起点のサブグループ自体も変更する' : '起点のサブグループ自体も連番に含める'}
          />
        </Box>

        {plan.error && <Alert severity="error">{plan.error}</Alert>}
        {(plan.warnings || []).slice(0, 5).map((w, i) => <Alert key={i} severity="warning">{w}</Alert>)}
        {(plan.warnings || []).length > 5 && <Typography variant="caption">ほか {plan.warnings.length - 5} 件の警告</Typography>}

        {!plan.error && (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>変更内容のプレビュー（{plan.changes.length}件）</Typography>
            {plan.changes.length === 0 ? (
              <Typography variant="body2" color="text.secondary">変更される値はありません。</Typography>
            ) : (
              <Box sx={{ maxHeight: 280, overflow: 'auto', border: '1px solid', borderColor: 'divider', borderRadius: 1, fontFamily: 'monospace', fontSize: '0.8rem' }}>
                {plan.changes.slice(0, MAX_PREVIEW_ROWS).map((c, i) => {
                  const d = describeChange(c);
                  // GUI版の変更は from/to が「値」、DSL版は from/to が「行内の文字位置」で値は fromValue/toValue。
                  // 値(fromValue/toValue)がある方を優先して表示する。
                  const fromV = c.fromValue !== undefined ? c.fromValue : c.from;
                  const toV = c.toValue !== undefined ? c.toValue : c.to;
                  return (
                    <Box key={i} sx={{ display: 'flex', gap: 1.5, px: 1, py: 0.25, borderBottom: '1px solid', borderColor: 'divider' }}>
                      <Box sx={{ width: 110, flexShrink: 0 }}>{d.where}</Box>
                      <Box sx={{ flex: 1 }}>{d.field}</Box>
                      <Box>{fromV} → <b>{toV}</b></Box>
                    </Box>
                  );
                })}
                {plan.changes.length > MAX_PREVIEW_ROWS && (
                  <Box sx={{ px: 1, py: 0.5, color: 'text.secondary' }}>… ほか {plan.changes.length - MAX_PREVIEW_ROWS} 件</Box>
                )}
              </Box>
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>キャンセル</Button>
        <Button variant="contained" color="success" disabled={!canApply} onClick={() => onApply(plan)}>
          適用（{plan.changes.length}件）
        </Button>
      </DialogActions>
    </Dialog>
  );
}
