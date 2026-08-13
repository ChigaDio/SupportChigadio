import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid, useGridApiRef } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent,
  DialogActions, Autocomplete, IconButton, Accordion, AccordionSummary,
  AccordionDetails, Chip, Select, MenuItem, FormControl, InputLabel,
  Switch, FormControlLabel, Tooltip, Checkbox, Slider
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import EditIcon from '@mui/icons-material/Edit';
import Papa from 'papaparse';
import { useMemo } from 'react';

// ============================================================
// ユーティリティ
// ============================================================

/**
 * 数値入力欄の共通コンポーネント。
 * 問題点の修正:
 *  - 先頭の「0」が残り続けて "100" と打っても "0100" になってしまう
 *  - "0" の状態から "-" を打っても符号が反映されない
 * 対応方針:
 *  - 表示用に生の文字列をローカルstateで保持し、フォーカス中は親のonChangeで上書きされないようにする
 *  - 入力中は "-"・"."・空文字などの中間状態を許可する（数値化できる時だけ親へ伝える）
 *  - blur時に正式な数値へ正規化する
 */
function sanitizeNumericText(raw, allowDecimal) {
  let s = raw ?? '';
  // 使用可能な文字だけ残す
  s = allowDecimal ? s.replace(/[^0-9.\-]/g, '') : s.replace(/[^0-9\-]/g, '');
  // 先頭以外の "-" は除去
  s = s.replace(/(?!^)-/g, '');
  if (allowDecimal) {
    // "." は最初の1つだけ有効
    const dot = s.indexOf('.');
    if (dot !== -1) {
      s = s.slice(0, dot + 1) + s.slice(dot + 1).replace(/\./g, '');
    }
  }
  // 先頭の余分な0を除去（"0", "0." , "-0" はそのまま残す）
  s = s.replace(/^(-?)0+(?=\d)/, '$1');
  return s;
}

function parseNumericText(text, allowDecimal) {
  if (text === '' || text === '-' || text === '.' || text === '-.') return null;
  const num = allowDecimal ? parseFloat(text) : parseInt(text, 10);
  return isNaN(num) ? null : num;
}

export function NumericTextField({ value, onChange, allowDecimal = false, readOnly, ...props }) {
  const [text, setText] = useState(() => (value ?? 0).toString());
  const focusedRef = React.useRef(false);

  useEffect(() => {
    if (!focusedRef.current) {
      setText((value ?? 0).toString());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <TextField
      {...props}
      type="text"
      value={text}
      inputProps={{ inputMode: allowDecimal ? 'decimal' : 'numeric', readOnly, ...(props.inputProps || {}) }}
      onFocus={(e) => { focusedRef.current = true; if (props.onFocus) props.onFocus(e); }}
      onChange={(e) => {
        if (readOnly) return;
        const sanitized = sanitizeNumericText(e.target.value, allowDecimal);
        setText(sanitized);
        const num = parseNumericText(sanitized, allowDecimal);
        if (num !== null) onChange(num);
      }}
      onBlur={(e) => {
        focusedRef.current = false;
        const num = parseNumericText(text, allowDecimal) ?? 0;
        setText(num.toString());
        onChange(num);
        if (props.onBlur) props.onBlur(e);
      }}
    />
  );
}

/**
 * 文字列入力欄の共通コンポーネント。
 * ★ 重要: NumericTextField 同様、表示用の生テキストをローカルstateで
 *   保持する。これがないと、value プロパティ（親から渡される値。
 *   DataGrid経由の場合はデバウンスされて反映が遅れることがある）に
 *   直接紐づいた完全な制御コンポーネントになってしまい、
 *   「親の値が更新される前に別の再レンダーが挟まる」と、
 *   入力途中の文字がその場で古い値に巻き戻される
 *   （＝早いタイピングで文字が消える・詰まる）原因になる。
 *   ローカルstateで即時にエコーし、onChangeで親には非同期に通知する
 *   ことで、親側の反映タイミングに関わらずタイピングの見た目は
 *   常に即座に追従する。
 */
export function StringTextField({ value, onChange, readOnly, multiline = true, ...props }) {
  const [text, setText] = useState(() => value ?? '');
  const focusedRef = React.useRef(false);

  useEffect(() => {
    if (!focusedRef.current) {
      setText(value ?? '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <TextField
      {...props}
      value={text}
      // multiline未指定時はデフォルトでtrueにする。以前はEnterで\nを手動挿入していても
      // 単一行の<input>ではそもそも改行を表示できないバグがあった(仕様書項目4と同種)。
      multiline={multiline}
      minRows={props.minRows ?? 1}
      maxRows={props.maxRows ?? 8}
      inputProps={{ readOnly, ...(props.inputProps || {}) }}
      onFocus={(e) => { focusedRef.current = true; if (props.onFocus) props.onFocus(e); }}
      onChange={(e) => {
        if (readOnly) return;
        const newText = e.target.value;
        setText(newText);
        onChange(newText);
      }}
      onKeyDown={(e) => {
        // Shift+Enter または Enter で改行を挿入（DataGridのEnterによる確定を防ぐ）
        if (e.key === 'Enter') {
          e.stopPropagation(); // DataGridへのEnterキーイベント伝播を止める
          if (!readOnly) {
            const el = e.target;
            const start = el.selectionStart;
            const end = el.selectionEnd;
            // ★ ローカルの text を基に改行を挿入する（親から渡される value は
            //   遅延している可能性があるため、これを基にすると巻き戻りが起きる）
            const newText = text.substring(0, start) + '\n' + text.substring(end);
            setText(newText);
            onChange(newText);
            requestAnimationFrame(() => {
              el.selectionStart = el.selectionEnd = start + 1;
            });
          }
        }
        if (props.onKeyDown) props.onKeyDown(e);
      }}
      onBlur={(e) => {
        focusedRef.current = false;
        if (props.onBlur) props.onBlur(e);
      }}
    />
  );
}

/**
 * 型名から配列かどうかを判定し、要素型を返す
 * カラム型の "int[]" 表記対応（カラムレベルの配列型）
 */
export function parseType(type) {
  if (typeof type === 'string' && type.endsWith('[]')) {
    return { isArray: true, isDynamic: true, arraySize: -1, baseType: type.slice(0, -2) };
  }
  return { isArray: false, isDynamic: false, arraySize: 0, baseType: type };
}

/**
 * classDataスキーマのフィールドから配列情報を取得
 * arraySize: -1 = 動的配列(List), >0 = 固定配列, 0 = 単一値
 */
export function getFieldArrayInfo(field) {
  const arraySize = field.arraySize ?? 0;
  if (arraySize === -1) return { isArray: true, isDynamic: true, arraySize: -1 };
  if (arraySize > 0)   return { isArray: true, isDynamic: false, arraySize };
  return { isArray: false, isDynamic: false, arraySize: 0 };
}

/**
 * 型に応じたデフォルト値を返す（単一値用）
 */
export function getDefaultValueForType(type, enumValues, classSchemas) {
  const lower = (type || '').toLowerCase();
  switch (lower) {
    case 'int':    return 0;
    case 'float':  return 0.0;
    case 'bool':   return false;
    case 'string': return '';
    case 'vector2': return [0, 0];
    case 'vector3': return [0, 0, 0];
    case 'bit': return { size: 8, bits: [] };
    case 'color': return { r: 1, g: 1, b: 1, a: 1 };
    case 'bezier': return { points: [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 0, outTangent: 0 }] };
    case 'dictionary': return { entries: [] };
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

// dictionaryのキー表示（enum/classDataID/customClassDataIDキーは "Type.Value" -> "Value" の形式に整形する）
function formatDictKey(key, keyType) {
  if (typeof key === 'string' && key.includes('.')) {
    const tail = key.split('.').pop();
    return tail === 'None' ? '(未設定)' : tail;
  }
  return String(key);
}

// ============================================================
// 「新しいカラムを追加」ダイアログ用の型オプション編集コンポーネント群
// ClassDataDetailGrid.js / CustomClassDataDetailGrid.js と同じロジック。
// ★ これまでこのダイアログには型オプション編集が無く、bit/bezier/dictionary
//   などの拡張型が常に固定デフォルトのままだった問題を解消するために追加。
// ============================================================
const OPTIONS_NUMERIC_TYPES = ['int', 'float', 'double', 'byte', 'short', 'long', 'decimal', 'uint'];

export function NumericOptionsEditor({ options, onChange }) {
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

export function BitOptionsEditor({ options, onChange, enumNames, classDataIdNames, customClassDataIdNames }) {
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

export function ArrayOptionsEditor({ options, onChange, enumNames, classDataIdNames, customClassDataIdNames }) {
  // 仕様書項目5: List(-1)型カラムに「Enum/ClassDataIDのメンバー数ぶんデフォルトを事前追加する」オプション。
  // 有効化すると要素数はソース側のメンバー数に自動追従し(手動追加削除は不可)、
  // 各要素の編集時にどのIDに対応する要素かをラベル表示する。
  const sourceNames = [...enumNames, ...classDataIdNames, ...customClassDataIdNames];
  const enabled = !!options.prefillSourceName;

  return (
    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
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
          有効化すると要素数は参照元のメンバー数に固定され、手動での追加・削除はできなくなります。
          参照元にメンバーが追加/削除/リネームされた場合、既存レコードのデータも保存時に自動で追従します。
        </Typography>
      )}
    </Box>
  );
}

export function DictionaryOptionsEditor({ options, onChange, keyTypeOptions, valueTypeOptions, enumNames, classDataIdNames, customClassDataIdNames }) {
  const keyType = options.keyType || 'int';
  const valueType = options.valueType || 'int';
  const valueArraySize = options.valueArraySize ?? 0;
  const valueOptions = options.valueOptions || {};
  const valueIsNumeric = OPTIONS_NUMERIC_TYPES.includes(valueType);
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
              {keyType}にメンバーが追加/削除/リネームされた場合、既存レコードのデータも保存時に自動で追従します。
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

function defaultOptionsForNewColumnType(type) {
  if (OPTIONS_NUMERIC_TYPES.includes(type)) return { min: null, max: null };
  if (type === 'bit') return { sizeMode: 'manual', sizeSourceName: null, size: 8, mode: 'multiple', allowSelectAll: true, flagNames: Array.from({ length: 8 }, (_, i) => `Flag${i}`) };
  if (type === 'color') return {};
  if (type === 'bezier') return { valueType: 'float', min: 0, max: 1 };
  if (type === 'dictionary') return { keyType: 'int', valueType: 'int', valueArraySize: 0, valueOptions: {} };
  return {};
}

// ============================================================
// formatPreviewValue: セル表示用の「見やすい」プレビュー文字列を生成
// classData/配列型の中身を JSON.stringify([~~~]) ではなく
// "フィールド名=値" の形式で表示するためのユーティリティ
// ============================================================
function formatScalarPreview(value, baseType, classSchemas, options) {
  if (value === null || value === undefined) return '-';
  const lower = (baseType || '').toLowerCase();

  if (lower === 'bool') return value ? 'true' : 'false';

  if (lower === 'vector2' && Array.isArray(value)) {
    return `(${value[0] ?? 0}, ${value[1] ?? 0})`;
  }
  if (lower === 'vector3' && Array.isArray(value)) {
    return `(${value[0] ?? 0}, ${value[1] ?? 0}, ${value[2] ?? 0})`;
  }

  // dictionary型: "key1: val1, key2: val2" 形式
  if (lower === 'dictionary') {
    const entries = Array.isArray(value?.entries) ? value.entries : [];
    if (entries.length === 0) return '(空のDictionary)';
    const keyType = options?.keyType || 'int';
    const valueType = options?.valueType || 'int';
    const valueIsArray = (options?.valueArraySize ?? 0) !== 0;
    return entries.map(({ key, value: v }) => {
      const kStr = formatDictKey(key, keyType);
      const vStr = valueIsArray
        ? formatArrayPreview(v, valueType, classSchemas, options?.valueOptions)
        : formatScalarPreview(v, valueType, classSchemas, options?.valueOptions);
      return `${kStr}: ${vStr}`;
    }).join(', ');
  }

  // classData型（ネスト）: "field=val, field2=val2" 形式
  if (classSchemas && classSchemas[baseType]) {
    const schema = classSchemas[baseType];
    const obj = (value && typeof value === 'object' && !Array.isArray(value)) ? value : {};
    if (schema.length === 0) return '(フィールドなし)';
    return schema.map(f => {
      const { isArray: fIsArray } = getFieldArrayInfo(f);
      const fv = obj[f.name];
      const preview = fIsArray
        ? formatArrayPreview(fv, f.type, classSchemas, f.options)
        : formatScalarPreview(fv, f.type, classSchemas, f.options);
      return `${f.name}=${preview}`;
    }).join(', ');
  }

  // enum / classDataID型: "TypeID.Value" -> "Value" だけ表示
  if (typeof value === 'string' && value.includes('.')) {
    const tail = value.split('.').pop();
    return tail === 'None' ? '(未設定)' : tail;
  }

  if (typeof value === 'object') {
    // 想定外のオブジェクトは最終手段としてJSON化
    try { return JSON.stringify(value); } catch { return String(value); }
  }

  return String(value);
}

function formatArrayPreview(value, baseType, classSchemas, options) {
  const arr = Array.isArray(value) ? value : [];
  if (arr.length === 0) return '(空)';
  return `[${arr.map(v => formatScalarPreview(v, baseType, classSchemas, options)).join(' / ')}]`;
}

/**
 * カラム型（"int[]" のような配列表記込み）に対する見やすいプレビュー文字列を返す
 */
export function formatPreviewValue(value, type, classSchemas, options) {
  const { isArray, baseType } = parseType(type);
  return isArray
    ? formatArrayPreview(value, baseType, classSchemas, options)
    : formatScalarPreview(value, baseType, classSchemas, options);
}

// ============================================================
// countPreviewLines: renderMiniPreviewTable が実際に描画する「行数」を
// DOMを使わずに計算する。
// ★ パフォーマンス対策: getRowHeight={() => 'auto'} はセルのDOMを
//   ResizeObserverで実測するため、グリッド内部stateが変わるたびに
//   全行分の再計算（レコード数に比例したコスト）が走ってしまう。
//   これがあらゆる型の入力で「打鍵のたびに重くなる」原因になっていた。
//   → セル内容から必要な行数を事前計算し、getRowHeightに「数値」を
//     返させることで、DOM実測（autoモード）を完全に回避する。
// ============================================================
function countPreviewLines(value, type, classSchemas, options) {
  const { isArray, baseType } = parseType(type);
  const isClass = classSchemas && classSchemas[baseType];
  const lower = (baseType || '').toLowerCase();

  if (isArray) {
    const arr = Array.isArray(value) ? value : [];
    // renderMiniPreviewTableは配列の各要素を1行として描画する
    return Math.max(arr.length, 1);
  }
  if (lower === 'dictionary') {
    const entries = Array.isArray(value?.entries) ? value.entries : [];
    // renderMiniPreviewTableはdictionaryの各エントリを1行として描画する
    return Math.max(entries.length, 1);
  }
  if (isClass) {
    const schema = classSchemas[baseType] || [];
    // renderMiniPreviewTableはclassDataの各フィールドを1行として描画する
    return Math.max(schema.length, 1);
  }
  return 1;
}

// ============================================================
// renderMiniPreviewTable: classData/配列型セルの「読みやすい」
// ミニテーブルプレビューを縦に並べて表示する（Matrix版のセル表示を踏襲）
// ============================================================
export function renderMiniPreviewTable(value, type, classSchemas, options) {
  const { isArray, baseType } = parseType(type);
  const isClass = classSchemas && classSchemas[baseType];
  const lower = (baseType || '').toLowerCase();

  const tableSx = {
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
  };

  if (isArray) {
    const arr = Array.isArray(value) ? value : [];
    if (arr.length === 0) {
      return <Typography variant="caption" color="text.disabled">(空)</Typography>;
    }
    return (
      <Box component="table" sx={tableSx}>
        <tbody>
          {arr.map((item, i) => (
            <tr key={i}>
              <td style={{ fontWeight: 600, color: '#666', whiteSpace: 'nowrap', width: 28 }}>[{i}]</td>
              <td style={{ wordBreak: 'break-word' }}>
                {isClass
                  ? (classSchemas[baseType] || [])
                      .map(f => `${f.name}=${formatPreviewValue(item?.[f.name], f.type, classSchemas, f.options)}`)
                      .join(', ')
                  : formatScalarPreview(item, baseType, classSchemas, options)}
              </td>
            </tr>
          ))}
        </tbody>
      </Box>
    );
  }

  if (lower === 'dictionary') {
    const entries = Array.isArray(value?.entries) ? value.entries : [];
    if (entries.length === 0) {
      return <Typography variant="caption" color="text.disabled">(空のDictionary)</Typography>;
    }
    const keyType = options?.keyType || 'int';
    const valueType = options?.valueType || 'int';
    const valueIsArray = (options?.valueArraySize ?? 0) !== 0;
    return (
      <Box component="table" sx={tableSx}>
        <tbody>
          {entries.map(({ key, value: v }, i) => (
            <tr key={i}>
              <td style={{ fontWeight: 600, color: '#666', whiteSpace: 'nowrap' }}>{formatDictKey(key, keyType)}</td>
              <td style={{ wordBreak: 'break-word' }}>
                {valueIsArray
                  ? formatArrayPreview(v, valueType, classSchemas, options?.valueOptions)
                  : formatScalarPreview(v, valueType, classSchemas, options?.valueOptions)}
              </td>
            </tr>
          ))}
        </tbody>
      </Box>
    );
  }

  if (isClass) {
    const schema = classSchemas[baseType] || [];
    const obj = (value && typeof value === 'object' && !Array.isArray(value)) ? value : {};
    if (schema.length === 0) {
      return <Typography variant="caption" color="text.disabled">(フィールドなし)</Typography>;
    }
    return (
      <Box component="table" sx={tableSx}>
        <tbody>
          {schema.map(f => (
            <tr key={f.name}>
              <td style={{ fontWeight: 600, color: '#666', whiteSpace: 'nowrap' }}>
                {f.name}{f.description ? `（${f.description}）` : ''}
              </td>
              <td style={{ wordBreak: 'break-word' }}>
                {formatPreviewValue(obj[f.name], f.type, classSchemas, f.options)}
              </td>
            </tr>
          ))}
        </tbody>
      </Box>
    );
  }

  return <Typography variant="caption">{formatPreviewValue(value, type, classSchemas, options)}</Typography>;
}

// ============================================================
// ArrayFieldEditor: 配列型の入力コンポーネント
// ============================================================
export function ArrayFieldEditor({ value, baseType, enumValues, classSchemas, options, onChange, onSizeChange, readOnly, isDynamic, arraySize }) {
  const arr = Array.isArray(value) ? value : [];

  // 仕様書項目5: prefillSourceNameが設定されている場合、要素数と各要素のラベルを
  // 参照元(Enum/ClassDataID)のメンバーから決定する。ソース側の増減/リネームには
  // useEffectで自動追従する(class_data_idと同様、保存前に常に最新のメンバー構成へ揃える)。
  const prefillSourceName = options?.prefillSourceName || null;
  const prefillMembers = prefillSourceName
    ? (enumValues[prefillSourceName] || []).map(v => v['property'] || v['enum_property'] || v)
    : null;
  const isPrefilled = !!prefillMembers;

  // isDynamic(arraySize=-1)でprefillが無効な場合のみ自由に追加削除可
  const isFixed = isPrefilled || (!isDynamic && arraySize > 0);

  // prefill有効時: 現在の値配列の長さを参照元メンバー数に自動的に揃える(位置対応)。
  // 個数が一致していれば何もしない(既存の入力値を保持する)。個数が変わった時だけ
  // 末尾を切り詰める/デフォルト値で埋める。リネーム時の値の追従(同じメンバーの値を
  // 保持する)はバックエンド側(保存時の同期処理)で安定キーを使って行う。
  useEffect(() => {
    if (!isPrefilled || readOnly) return;
    if (arr.length === prefillMembers.length) return;
    const next = Array.from({ length: prefillMembers.length }, (_, i) => (i < arr.length ? arr[i] : getDefaultValueForType(baseType, enumValues, classSchemas)));
    onChange(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPrefilled, prefillSourceName, prefillMembers ? prefillMembers.length : 0]);

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

  // 固定長(prefillもしくは固定配列)の場合、表示する要素数を合わせる
  const effectiveSize = isPrefilled ? prefillMembers.length : arraySize;
  const displayArr = isFixed
    ? Array.from({ length: effectiveSize }, (_, i) => arr[i] ?? getDefaultValueForType(baseType, enumValues, classSchemas))
    : arr;

  return (
    <Box sx={{ width: '100%' }}>
      {isPrefilled && (
        <Typography variant="caption" color="primary" sx={{ mb: 0.5, display: 'block' }}>
          {prefillSourceName} のメンバーから自動生成 [{effectiveSize}件]（手動追加削除不可）
        </Typography>
      )}
      {!isPrefilled && !isDynamic && arraySize > 0 && (
        <Typography variant="caption" color="text.disabled" sx={{ mb: 0.5, display: 'block' }}>
          固定配列 [{arraySize}]
        </Typography>
      )}
      {!isPrefilled && !isFixed && isDynamic && (
        <Typography variant="caption" color="text.disabled" sx={{ mb: 0.5, display: 'block' }}>
          動的配列 (List) [{arr.length}件]
        </Typography>
      )}
      {displayArr.map((item, index) => (
        <Box key={isPrefilled ? prefillMembers[index] : index} sx={{ display: 'flex', alignItems: 'center', mb: 0.5, gap: 1 }}>
          <Typography variant="caption" sx={{ minWidth: isPrefilled ? 90 : 20, color: 'text.secondary' }}>
            {isPrefilled ? prefillMembers[index] : `[${index}]`}
          </Typography>
          <Box sx={{ flex: 1 }}>
            <SingleValueEditor
              value={item}
              type={baseType}
              enumValues={enumValues}
              classSchemas={classSchemas}
              options={options}
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
export function ClassFieldEditor({ value, typeName, enumValues, classSchemas, onChange, onSizeChange, readOnly, defaultExpanded = false }) {
  const schema = classSchemas[typeName] || [];
  const obj = (value && typeof value === 'object' && !Array.isArray(value)) ? value : {};

  const handleFieldChange = (fieldName, fieldVal) => {
    onChange({ ...obj, [fieldName]: fieldVal });
  };

  return (
    <Accordion
      disableGutters
      defaultExpanded={defaultExpanded}
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
                  {field.name}{field.description ? `（${field.description}）` : ''}
                  <Chip label={`${field.type}${arraySizeLabel}`} size="small" sx={{ ml: 0.5, height: 16, fontSize: 10 }} />
                </Typography>
                {fieldIsArray ? (
                  <ArrayFieldEditor
                    value={Array.isArray(fieldValue) ? fieldValue : []}
                    baseType={baseType}
                    enumValues={enumValues}
                    classSchemas={classSchemas}
                    options={field.options}
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
                    options={field.options}
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
// ============================================================
// bit / color / bezier エディタ
// (CustomClassDataIdDetailGrid.js の実装をそのまま移植したもの)
// ============================================================
function BitFieldEditor({ value, options, onChange, readOnly }) {
  const size = options?.size ?? value?.size ?? 8;
  const flagNames = options?.flagNames && options.flagNames.length === size
    ? options.flagNames
    : Array.from({ length: size }, (_, i) => `Flag${i}`);
  const bits = Array.isArray(value?.bits) ? value.bits : [];
  const isSingle = options?.mode === 'single';
  const [search, setSearch] = useState('');

  const toggle = (i) => {
    if (readOnly) return;
    if (isSingle) {
      onChange({ size, bits: [i] });
      return;
    }
    const has = bits.includes(i);
    const next = has ? bits.filter(b => b !== i) : [...bits, i];
    onChange({ size, bits: next });
  };

  const entries = React.useMemo(() => flagNames.map((label, i) => ({ label, i })), [flagNames]);
  const filtered = React.useMemo(() => {
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
            <Button size="small" variant="outlined" disabled={readOnly}
              onClick={() => onChange({ size, bits: Array.from({ length: size }, (_, i) => i) })}>
              全選択
            </Button>
          )}
          <Button size="small" variant="outlined" color="secondary" disabled={readOnly} onClick={() => onChange({ size, bits: [] })}>
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
                  cursor: readOnly ? 'default' : 'pointer',
                  borderLeft: '3px solid',
                  borderLeftColor: checked ? 'primary.main' : 'transparent',
                  bgcolor: checked ? 'rgba(25, 118, 210, 0.08)' : (i % 2 === 0 ? '#fff' : '#fafafa'),
                  '&:hover': { bgcolor: checked ? 'rgba(25, 118, 210, 0.14)' : '#f0f0f0' },
                }}
              >
                <Checkbox
                  size="small"
                  checked={checked}
                  disabled={readOnly}
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

function _toHex(v) {
  return Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0');
}
function ColorFieldEditor({ value, onChange, readOnly }) {
  const v = value || { r: 1, g: 1, b: 1, a: 1 };
  const hex = `#${_toHex(v.r)}${_toHex(v.g)}${_toHex(v.b)}`;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      <input
        type="color"
        value={hex}
        disabled={readOnly}
        onChange={(e) => {
          const h = e.target.value;
          onChange({
            r: parseInt(h.slice(1, 3), 16) / 255,
            g: parseInt(h.slice(3, 5), 16) / 255,
            b: parseInt(h.slice(5, 7), 16) / 255,
            a: v.a,
          });
        }}
        style={{ width: 48, height: 36, border: 'none', background: 'none', cursor: readOnly ? 'default' : 'pointer' }}
      />
      <Box sx={{ width: 200 }}>
        <Typography variant="caption">アルファ: {v.a.toFixed(2)}</Typography>
        <Slider
          size="small" min={0} max={1} step={0.01}
          value={v.a}
          disabled={readOnly}
          onChange={(e, nv) => onChange({ ...v, a: nv })}
        />
      </Box>
      <Box sx={{ width: 32, height: 32, borderRadius: 1, border: '1px solid #ccc', background: `rgba(${v.r * 255},${v.g * 255},${v.b * 255},${v.a})` }} />
    </Box>
  );
}

function _hermite(p0, p1, t) {
  const dt = p1.time - p0.time || 1;
  const s = (t - p0.time) / dt;
  const h00 = 2 * s ** 3 - 3 * s ** 2 + 1;
  const h10 = s ** 3 - 2 * s ** 2 + s;
  const h01 = -2 * s ** 3 + 3 * s ** 2;
  const h11 = s ** 3 - s ** 2;
  return h00 * p0.value + h10 * dt * p0.outTangent + h01 * p1.value + h11 * dt * p1.inTangent;
}

// タンジェントハンドルの画面上の長さ（px固定。角度だけが傾き値を表す）
const TANGENT_HANDLE_LEN = 46;
// ハンドルドラッグ時、傾き計算が発散しないようx方向オフセットの最小値をpxで確保する
const TANGENT_MIN_DX = 10;

function BezierFieldEditor({ value, options, onChange, readOnly }) {
  const points = (value?.points && value.points.length >= 2)
    ? [...value.points].sort((a, b) => a.time - b.time)
    : [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 0, outTangent: 0 }];
  const min = options?.min ?? 0;
  const max = options?.max ?? 1;
  const W = 420, H = 220, PAD = 24;
  const svgRef = useRef(null);
  const [dragIndex, setDragIndex] = useState(null);
  // アクティブ（選択中）な点。選択されている間、その点の左右にタンジェントハンドルを表示する
  const [activeIndex, setActiveIndex] = useState(null);
  // タンジェントハンドルのドラッグ状態: { index, side: 'in' | 'out' }
  const [dragHandle, setDragHandle] = useState(null);

  const sx = (W - 2 * PAD); // px per unit time (time範囲は0-1)
  const sy = (H - 2 * PAD) / (max - min || 1); // px per unit value

  const xToPx = (t) => PAD + t * (W - 2 * PAD);
  const yToPx = (val) => H - PAD - ((val - min) / (max - min || 1)) * (H - 2 * PAD);
  const pxToX = (px) => Math.max(0, Math.min(1, (px - PAD) / (W - 2 * PAD)));
  const pxToY = (py) => {
    const t = (H - PAD - py) / (H - 2 * PAD);
    return min + t * (max - min);
  };

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

  const pathD = React.useMemo(() => {
    let d = '';
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i], p1 = points[i + 1];
      const steps = 24;
      for (let s = 0; s <= steps; s++) {
        const t = p0.time + (p1.time - p0.time) * (s / steps);
        const val = _hermite(p0, p1, t);
        const cmd = (i === 0 && s === 0) ? 'M' : 'L';
        d += `${cmd}${xToPx(t)},${yToPx(val)} `;
      }
    }
    return d;
  }, [points]);

  const updatePoint = (index, patch) => {
    if (readOnly) return;
    const next = points.map((p, i) => (i === index ? { ...p, ...patch } : p));
    onChange({ points: next });
  };

  const handleMove = (e) => {
    if (readOnly || !svgRef.current) return;
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

  const addPoint = () => {
    if (readOnly) return;
    onChange({ points: [...points, { time: 0.5, value: (min + max) / 2, inTangent: 0, outTangent: 0 }] });
  };
  const removePoint = (index) => {
    if (readOnly || points.length <= 2) return;
    if (activeIndex === index) setActiveIndex(null);
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
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
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
                    style={{ cursor: readOnly ? 'default' : 'grab' }}
                    onMouseDown={(e) => { e.stopPropagation(); if (!readOnly) setDragHandle({ index: i, side: 'in' }); }}
                  />
                  <circle
                    cx={outPos.x} cy={outPos.y} r={5}
                    fill={dragHandle?.index === i && dragHandle?.side === 'out' ? '#e65100' : '#ffa726'}
                    stroke="#fff" strokeWidth={1}
                    style={{ cursor: readOnly ? 'default' : 'grab' }}
                    onMouseDown={(e) => { e.stopPropagation(); if (!readOnly) setDragHandle({ index: i, side: 'out' }); }}
                  />
                </>
              )}
              <circle
                cx={cx} cy={cy} r={isActive ? 7 : 6}
                fill={dragIndex === i ? '#d32f2f' : (isActive ? '#1565c0' : '#1976d2')}
                stroke={isActive ? '#0d47a1' : 'none'} strokeWidth={isActive ? 2 : 0}
                style={{ cursor: readOnly ? 'default' : 'grab' }}
                onMouseDown={(e) => { e.stopPropagation(); setActiveIndex(i); if (!readOnly) setDragIndex(i); }}
              />
            </g>
          );
        })}
      </svg>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        点をクリックして選択すると、左右にタンジェントハンドル（緑=in / 橙=out）が表示され、ドラッグで傾きを調整できます。
      </Typography>
      <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
        {points.map((p, i) => (
          <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Chip
              size="small"
              label={`点${i}`}
              color={activeIndex === i ? 'primary' : 'default'}
              onClick={() => setActiveIndex(i)}
              sx={{ cursor: 'pointer' }}
            />
            <NumericTextField label="time(0-1)" allowDecimal value={p.time} readOnly={readOnly} onChange={(val) => updatePoint(i, { time: Math.max(0, Math.min(1, val)) })} sx={{ width: 100 }} />
            <NumericTextField label="value" allowDecimal value={p.value} readOnly={readOnly} onChange={(val) => updatePoint(i, { value: val })} sx={{ width: 100 }} />
            <NumericTextField label="inTangent" allowDecimal value={p.inTangent} readOnly={readOnly} onChange={(val) => updatePoint(i, { inTangent: val })} sx={{ width: 100 }} />
            <NumericTextField label="outTangent" allowDecimal value={p.outTangent} readOnly={readOnly} onChange={(val) => updatePoint(i, { outTangent: val })} sx={{ width: 100 }} />
            <IconButton size="small" color="error" disabled={readOnly || points.length <= 2} onClick={() => removePoint(i)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Box>
        ))}
        <Button size="small" startIcon={<AddIcon />} onClick={addPoint} disabled={readOnly} sx={{ alignSelf: 'flex-start' }}>点を追加</Button>
      </Box>
    </Box>
  );
}

// ============================================================
// DictionaryFieldEditor: dictionary型の入力コンポーネント
// キーは数値のみ（int / Enum / ClassDataID / CustomClassDataID）、値は任意の型
// 値データ形式: { entries: [{ key, value }, ...] }
// ============================================================
// ============================================================
// SearchableEnumSelect: Enum/ClassDataID等、選択肢が多くなりがちな値の
// ドロップダウンを文字検索付きにするための共通コンポーネント(仕様書項目3)。
// MUIのAutocompleteをベースに、既存のSelect+MenuItemと同じ
// value/onChange(選択されたvalue文字列を渡す)のインターフェースを維持する。
// ============================================================
function SearchableEnumSelect({ value, options, onChange, readOnly, size = 'small', fullWidth, sx, label, minWidth }) {
  const selected = options.find(o => o.value === value) || null;
  return (
    <Autocomplete
      size={size}
      fullWidth={fullWidth}
      sx={{ minWidth, ...sx }}
      options={options}
      disabled={readOnly}
      value={selected}
      onChange={(e, newVal) => {
        if (readOnly) return;
        onChange(newVal ? newVal.value : (options[0]?.value ?? ''));
      }}
      getOptionLabel={(opt) => (opt && opt.label) || ''}
      isOptionEqualToValue={(opt, val) => opt?.value === val?.value}
      renderInput={(params) => <TextField {...params} label={label} size={size} />}
      // 選択肢は数が多くなりがちなので、入力途中の文字列で部分一致フィルタする
      filterOptions={(opts, state) => {
        const input = state.inputValue.trim().toLowerCase();
        if (!input) return opts;
        return opts.filter(o => o.label.toLowerCase().includes(input));
      }}
    />
  );
}

function DictionaryKeyEditor({ keyValue, keyType, enumValues, onChange, readOnly }) {
  if ((keyType || 'int').toLowerCase() === 'int') {
    return (
      <NumericTextField
        size="small"
        allowDecimal={false}
        value={keyValue ?? 0}
        onChange={onChange}
        readOnly={readOnly}
        sx={{ width: 120 }}
      />
    );
  }
  // enum / classDataID / customClassDataID キー: "Type.Value" 形式のセレクト（文字検索対応）
  const opts = (enumValues && enumValues[keyType]) || [];
  const options = [
    { value: `${keyType}ID.None`, label: 'None' },
    ...opts.map(v => {
      const k = v['property'] || v['enum_property'] || v;
      return { value: `${keyType}ID.${k}`, label: k };
    })
  ];
  return (
    <SearchableEnumSelect
      value={keyValue ?? `${keyType}ID.None`}
      options={options}
      onChange={onChange}
      readOnly={readOnly}
      minWidth={160}
    />
  );
}

function DictionaryFieldEditor({ value, options, enumValues, classSchemas, onChange, readOnly }) {
  const keyType = options?.keyType || 'int';
  const valueType = options?.valueType || 'int';
  const valueArraySize = options?.valueArraySize ?? 0;
  const valueIsArray = valueArraySize !== 0;
  const valueIsDynamic = valueArraySize === -1;
  const valueOptions = options?.valueOptions || {};
  const entries = Array.isArray(value?.entries) ? value.entries : [];

  // 仕様書追記項目: キーがEnum/ClassDataIDの場合、全メンバー分のエントリを自動で事前追加するオプション
  const prefillKeys = !!options?.prefillKeys && keyType !== 'int';
  const keyMembers = prefillKeys ? (enumValues[keyType] || []).map(v => v['property'] || v['enum_property'] || v) : null;

  const updateEntries = (next) => { if (!readOnly) onChange({ entries: next }); };
  const updateKey = (index, newKey) => updateEntries(entries.map((e, i) => (i === index ? { ...e, key: newKey } : e)));
  const updateValue = (index, newVal) => updateEntries(entries.map((e, i) => (i === index ? { ...e, value: newVal } : e)));
  const removeEntry = (index) => updateEntries(entries.filter((_, i) => i !== index));
  const addEntry = () => {
    const defaultKey = keyType.toLowerCase() === 'int' ? 0 : `${keyType}ID.None`;
    const defaultVal = valueIsArray ? [] : getDefaultValueForType(valueType, enumValues, classSchemas);
    updateEntries([...entries, { key: defaultKey, value: defaultVal }]);
  };

  // prefillKeys有効時: キーMemberの構成に合わせてエントリ集合を自動的に揃える。
  // 既存エントリはキー文字列("TypeID.Member")で対応付けて値を保持し、
  // 増えたメンバーはデフォルト値で新規追加、消えたメンバーのエントリは除去する。
  useEffect(() => {
    if (!prefillKeys || readOnly) return;
    const wantedKeys = keyMembers.map(m => `${keyType}ID.${m}`);
    const currentByKey = {};
    entries.forEach(e => { currentByKey[e.key] = e; });
    const currentKeySet = new Set(entries.map(e => e.key));
    const wantedKeySet = new Set(wantedKeys);
    const sameSet = currentKeySet.size === wantedKeySet.size && [...wantedKeySet].every(k => currentKeySet.has(k));
    const sameOrder = sameSet && entries.every((e, i) => e.key === wantedKeys[i]);
    if (sameOrder) return;
    const next = wantedKeys.map(k => currentByKey[k] || {
      key: k,
      value: valueIsArray ? [] : getDefaultValueForType(valueType, enumValues, classSchemas),
    });
    updateEntries(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillKeys, keyType, keyMembers ? keyMembers.join(',') : '']);

  return (
    <Box sx={{ border: '1px solid #e0e0e0', borderRadius: 1, p: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
        <Typography variant="caption" color={prefillKeys ? 'primary' : 'text.secondary'}>
          {entries.length}件 / Dictionary&lt;{keyType}, {valueType}{valueIsArray ? '[]' : ''}&gt;
          {prefillKeys && `（${keyType}の全メンバーから自動生成・手動追加削除不可）`}
        </Typography>
        {!prefillKeys && (
          <Button size="small" startIcon={<AddIcon />} onClick={addEntry} disabled={readOnly}>エントリを追加</Button>
        )}
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
              <DictionaryKeyEditor
                keyValue={entry.key}
                keyType={keyType}
                enumValues={enumValues}
                onChange={(v) => updateKey(i, v)}
                readOnly={readOnly || prefillKeys}
              />
            </Box>
            <Typography variant="caption" sx={{ pt: 1 }}>:</Typography>
            <Box sx={{ flex: 1 }}>
              {valueIsArray ? (
                <ArrayFieldEditor
                  value={entry.value}
                  baseType={valueType}
                  enumValues={enumValues}
                  classSchemas={classSchemas}
                  options={valueOptions}
                  onChange={(v) => updateValue(i, v)}
                  readOnly={readOnly}
                  isDynamic={valueIsDynamic}
                  arraySize={valueArraySize}
                />
              ) : (
                <SingleValueEditor
                  value={entry.value}
                  type={valueType}
                  enumValues={enumValues}
                  classSchemas={classSchemas}
                  options={valueOptions}
                  onChange={(v) => updateValue(i, v)}
                  readOnly={readOnly}
                />
              )}
            </Box>
            {!prefillKeys && (
              <IconButton size="small" color="error" disabled={readOnly} onClick={() => removeEntry(i)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            )}
          </Box>
        ))}
      </Box>
    </Box>
  );
}

export function SingleValueEditor({ value, type, enumValues, classSchemas, options, onChange, onSizeChange, readOnly }) {
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
      <NumericTextField
        size="small"
        allowDecimal={false}
        value={value ?? 0}
        onChange={onChange}
        readOnly={readOnly}
        fullWidth
      />
    );
  }

  // float
  if (lower === 'float') {
    return (
      <NumericTextField
        size="small"
        allowDecimal={true}
        value={value ?? 0}
        onChange={onChange}
        readOnly={readOnly}
        fullWidth
      />
    );
  }

  // string
  if (lower === 'string') {
    return (
      <StringTextField
        size="small"
        value={value ?? ''}
        onChange={(newVal) => !readOnly && onChange(newVal)}
        readOnly={readOnly}
        fullWidth
        multiline
        minRows={1}
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
          <NumericTextField
            key={label}
            size="small"
            allowDecimal={true}
            label={label}
            value={arr[i] ?? 0}
            onChange={(val) => {
              if (readOnly) return;
              const next = [...arr];
              next[i] = val;
              onChange(next);
            }}
            readOnly={readOnly}
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
          <NumericTextField
            key={label}
            size="small"
            allowDecimal={true}
            label={label}
            value={arr[i] ?? 0}
            onChange={(val) => {
              if (readOnly) return;
              const next = [...arr];
              next[i] = val;
              onChange(next);
            }}
            readOnly={readOnly}
            sx={{ flex: 1 }}
          />
        ))}
      </Box>
    );
  }

  // bit / color / bezier: CustomClassDataIdDetailGrid.js のエディタをそのまま移植
  if (lower === 'bit') {
    return <BitFieldEditor value={value} options={options} readOnly={readOnly} onChange={onChange} />;
  }
  if (lower === 'color') {
    return <ColorFieldEditor value={value} readOnly={readOnly} onChange={onChange} />;
  }
  if (lower === 'bezier') {
    return <BezierFieldEditor value={value} options={options} readOnly={readOnly} onChange={onChange} />;
  }
  if (lower === 'dictionary') {
    return (
      <DictionaryFieldEditor
        value={value}
        options={options}
        enumValues={enumValues}
        classSchemas={classSchemas}
        onChange={onChange}
        readOnly={readOnly}
      />
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

  // enum / classDataID型（文字検索付きセレクト）
  if (enumValues && enumValues[type]) {
    const options = [
      { value: `${type}ID.None`, label: 'None' },
      ...enumValues[type].map(v => {
        const key = v['property'] || v['enum_property'] || v;
        return { value: `${type}ID.${key}`, label: key };
      })
    ];
    return (
      <SearchableEnumSelect
        value={value ?? `${type}ID.None`}
        options={options}
        onChange={onChange}
        readOnly={readOnly}
        fullWidth
      />
    );
  }

  // フォールバック
  return (
    <StringTextField
      size="small"
      value={value ?? ''}
      onChange={(newVal) => !readOnly && onChange(newVal)}
      readOnly={readOnly}
      fullWidth
    />
  );
}

// ============================================================
// NestedEditorDialogBody: セル編集ダイアログの中身
// ★ パフォーマンス対策: 編集中の値をこのコンポーネント内だけの
//   ローカルstateで持つ。1打鍵ごとに setLocalValue が呼ばれても、
//   親の ClassDataIdDetailGrid（＝DataGridを含む重いツリー）は
//   一切再レンダーされない。「保存」を押した時だけ onSave(localValue)
//   で親へ1回だけ値を渡す。
//   key={`${rowId}:${field}`} を親側で指定してマウントすることで、
//   編集対象セルが変わるたびに自動的に初期値へリセットされる。
// ============================================================
function NestedEditorDialogBody({ cellInfo, enumValues, classSchemas, onSave, onCancel, valueRef }) {
  const [localValue, setLocalValue] = useState(cellInfo.initialValue);
  const { isArray, baseType } = parseType(cellInfo.type);
  const isClass = classSchemas && classSchemas[baseType];
  const fieldOptions = cellInfo.options;

  // ★ 親(ClassDataIdDetailGrid)が「外側クリックで閉じられた時に保存するか確認する」
  //   判断をするために、最新の編集値を ref 経由でも参照できるようにしておく。
  //   ref への書き込みは再レンダーを起こさないので、パフォーマンスへの影響はない。
  useEffect(() => {
    if (valueRef) valueRef.current = localValue;
  }, [localValue, valueRef]);

  return (
    <>
      <DialogContent sx={{ pt: 2, minHeight: 320 }}>
        {isArray ? (
          <ArrayFieldEditor
            value={Array.isArray(localValue) ? localValue : []}
            baseType={baseType}
            enumValues={enumValues}
            classSchemas={classSchemas}
            options={fieldOptions}
            isDynamic={true}
            arraySize={-1}
            onChange={setLocalValue}
          />
        ) : isClass ? (
          <ClassFieldEditor
            value={localValue}
            typeName={baseType}
            enumValues={enumValues}
            classSchemas={classSchemas}
            onChange={setLocalValue}
            defaultExpanded
          />
        ) : (
          <SingleValueEditor
            value={localValue}
            type={cellInfo.type}
            enumValues={enumValues}
            classSchemas={classSchemas}
            options={fieldOptions}
            onChange={setLocalValue}
          />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>キャンセル</Button>
        <Button variant="contained" onClick={() => onSave(localValue)}>保存</Button>
      </DialogActions>
    </>
  );
}

// ============================================================
// メインコンポーネント
//
// ★ classData型・配列型カラムについて:
//   以前はDataGridのセル内(renderEditCell)にAccordionを直接描画して
//   編集していたが、この方式だと編集のたびに resetRowHeights() で
//   行の高さ再計算＝グリッドの再レイアウトが発生し、その最中に
//   Select/Accordionのポップアップが強制的に閉じてしまう上、
//   セル幅・高さの制約で入力しづらいという問題があった。
//   → classData型・配列型は専用の編集ダイアログ（大きく余裕のある
//     画面）で編集する方式に変更し、グリッドのレイアウト変化の
//     影響を受けないようにした。
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
  // ★ 追加: 新規カラムの「型オプション」編集用（bit/bezier/dictionaryの参照元候補）
  const [enumNames, setEnumNames] = useState([]);
  const [classDataIdNames, setClassDataIdNames] = useState([]);
  const [customClassDataIdNames, setCustomClassDataIdNames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openAddColumn, setOpenAddColumn] = useState(false);
  const [openDefaultRecords, setOpenDefaultRecords] = useState(false);
  const [openDeleteColumn, setOpenDeleteColumn] = useState(false);
  const [openImportCsv, setOpenImportCsv] = useState(false);
  const [newColType, setNewColType] = useState('');
  const [newColName, setNewColName] = useState('');
  const [newColDescription, setNewColDescription] = useState('');
  const [newColOptions, setNewColOptions] = useState({});
  const [recordCount, setRecordCount] = useState(1);
  const [columnToDelete, setColumnToDelete] = useState('');
  const apiRef = useGridApiRef();
  // ★ 最新の data を安定した参照(ref)経由でも読めるようにしておく
  //   （コールバックの参照を安定させ、無関係な再レンダーで columns の
  //     useMemo が再生成されるのを防ぐため）
  const dataRef = React.useRef(data);
  dataRef.current = data;

  // ★ classData型・配列型カラム用の編集ダイアログの状態
  // （グリッドの中で直接編集せず、広いダイアログで編集する）
  // ★ パフォーマンス対策: 編集中の値（旧 nestedEditorValue）を親のstateに
  //   持たせていると、ダイアログ内で1打鍵するたびに ClassDataIdDetailGrid
  //   全体が再レンダーされ、DataGrid（レコード数に比例したコストを持つ）まで
  //   巻き込まれて重くなっていた。
  //   → 編集中の値は NestedEditorDialogBody 内のローカルstateだけで持ち、
  //     「保存」時に1回だけ親へ反映する形にする。cell には初期値
  //     （ダイアログを開いた時点の値）だけを持たせる。
  const [nestedEditorOpen, setNestedEditorOpen] = useState(false);
  const [nestedEditorCell, setNestedEditorCell] = useState(null); // { rowId, field, type, initialValue }
  // ★ NestedEditorDialogBody 内で編集中の最新値を、親を再レンダーさせずに読み取るための ref
  //   （外側クリック/Escapeで閉じられた時に「保存しますか？」の確認に使う）
  const nestedEditorValueRef = React.useRef(null);

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
  // ★ パフォーマンス対策: 以前は data.rows が変わるたびに「全行」を
  //   map し直しており、1件だけセルを編集した場合でも
  //   O(レコード数 × カラム数) の再計算が走っていた。
  //   processRowUpdate は編集された行だけを新しいオブジェクトに
  //   差し替え、他の行は同じ参照のまま返す実装になっているため、
  //   行オブジェクトの参照をキーにしたキャッシュを使い、
  //   実際に変更された行だけを再計算するようにする。
  //   （カラム定義・enum・classSchemaが変わった時だけキャッシュを破棄）
  // ============================================================
  const rowDataCacheRef = React.useRef(new Map());
  const gridRowsDepsRef = React.useRef({ columns: null, enumValues: null, classSchemas: null });

  const gridRows = useMemo(() => {
    const prevDeps = gridRowsDepsRef.current;
    if (
      prevDeps.columns !== data.columns ||
      prevDeps.enumValues !== enumValues ||
      prevDeps.classSchemas !== classSchemas
    ) {
      // カラム構成やenum/classSchemaが変わった場合のみキャッシュを作り直す
      rowDataCacheRef.current = new Map();
      gridRowsDepsRef.current = { columns: data.columns, enumValues, classSchemas };
    }
    const cache = rowDataCacheRef.current;
    const nextCache = new Map();
    const rows = data.rows.map((row) => {
      const cached = cache.get(row);
      if (cached) {
        nextCache.set(row, cached);
        return cached;
      }
      const rowData = {
        id: row.id,
        enum_property: row.enum_property,
        description: row.description,
      };
      data.columns.forEach((col) => {
        rowData[col.name] = row.data?.[col.name]?.value ?? getDefaultValueForType(col.type, enumValues, classSchemas);
      });
      nextCache.set(row, rowData);
      return rowData;
    });
    // 削除された行のキャッシュエントリが残り続けないよう、使われた分だけ保持
    rowDataCacheRef.current = nextCache;
    return rows;
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
      fetch('/api/custom-class-data').then(r => r.ok ? r.json() : []),
      fetch('/api/custom-class-data-id').then(r => r.ok ? r.json() : []),
    ]).then(([enumList, classListData, classIdList, customClassList, customClassIdList]) => {
      const basicTypes = ['int', 'float', 'bool', 'string'];
      const unityTypes = ['Vector2', 'Vector3'];
      const customTypes = ['bit', 'color', 'bezier', 'dictionary'];
      const enumTypes = enumList.map(item => item.name);
      const classNames = classListData.map(item => item.name);
      const classIdTypes = classIdList.map(item => item.name);
      const customClassNames = (Array.isArray(customClassList) ? customClassList : []).map(item => item.name);
      const customClassIdTypes = (Array.isArray(customClassIdList) ? customClassIdList : []).map(item => item.name);

      // ★ classListを保存（配列型の判定に使う）
      setClassList(classNames);
      // ★ 新規カラムの「型オプション」編集用に、参照元候補を保存
      setEnumNames(enumTypes);
      setClassDataIdNames(classIdTypes);
      setCustomClassDataIdNames(customClassIdTypes);

      // 配列型のオプションを追加
      const arrayTypes = [
        ...basicTypes,
        ...unityTypes,
        ...customTypes,
        ...enumTypes,
        ...classNames,
        ...classIdTypes,
        ...customClassNames,
        ...customClassIdTypes,
      ].map(t => `${t}[]`);

      setTypeOptions([
        ...basicTypes, ...unityTypes, ...customTypes, ...enumTypes, ...classNames, ...classIdTypes,
        ...customClassNames, ...customClassIdTypes,
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

      // ★ CustomClassDataID値の取得（enum/classDataIDと同じ形でenumValuesへ統合する）
      const customClassIdPromises = customClassIdTypes.map(nm =>
        fetch(`/api/custom-class-data-id/${encodeURIComponent(nm)}`)
          .then(res => res.ok ? res.json() : { rows: [] })
          .then(d => ({ [nm]: (d.rows || []).map(row => row.enum_property) }))
      );

      // ★ classDataスキーマの取得（/api/class-data/{name} → [{name, type}, ...]）
      const classSchemaPromises = classNames.map(className =>
        fetch(`/api/class-data/${encodeURIComponent(className)}`)
          .then(res => res.ok ? res.json() : [])
          .then(d => ({ [className]: Array.isArray(d) ? d : [] }))
          .catch(() => ({ [className]: [] }))
      );

      // ★ CustomClassDataスキーマの取得（ClassDataと同じ形でclassSchemasへ統合する）
      const customClassSchemaPromises = customClassNames.map(className =>
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
      const enumValuesMap = Object.assign({}, ...enumResults, ...classIdResults, ...customClassIdResults);
      setEnumValues(enumValuesMap);

      const schemasMap = Object.assign({}, ...classSchemaResults, ...customClassSchemaResults);
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
    const newColumn = { type: newColType, name: newColName, description: newColDescription, options: newColOptions };
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
    setNewColDescription('');
    setNewColOptions({});
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

  const handleDeleteRow = useCallback((rowId) => {
    if (window.confirm(`レコード ID ${rowId} を削除しますか？`)) {
      setData(prev => ({ ...prev, rows: prev.rows.filter(row => row.id !== rowId) }));
    }
  }, []);

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

  // ★ classData型・配列型カラムのセルをクリックしたときにダイアログを開く
  //   （dataRef 経由で最新の rows を参照することで、この関数自体の参照を
  //     安定させ、columns の useMemo が無関係な再レンダーで作り直されないようにする）
  const openNestedEditor = useCallback((rowId, field, type, options) => {
    const row = dataRef.current.rows.find(r => r.id === rowId);
    const currentValue = row?.data?.[field]?.value ?? getDefaultValue(type);
    nestedEditorValueRef.current = currentValue;
    setNestedEditorCell({ rowId, field, type, options, initialValue: currentValue });
    setNestedEditorOpen(true);
  }, [getDefaultValue]);

  // ★ ダイアログの「保存」ボタン：グリッドを経由せず直接 data.rows を更新する
  // ★ 編集中の値はダイアログ側のローカルstateで持っているため、
  //   ここで受け取るのは「保存」が押された瞬間の最終値だけ（1回だけ呼ばれる）。
  const handleNestedEditorSave = useCallback((localValue) => {
    setNestedEditorCell(prevCell => {
      if (!prevCell) return prevCell;
      const { rowId, field, type } = prevCell;
      setData(prevData => ({
        ...prevData,
        rows: prevData.rows.map(row =>
          row.id === rowId
            ? { ...row, data: { ...row.data, [field]: { value: localValue, type } } }
            : row
        ),
      }));
      return prevCell;
    });
    setNestedEditorOpen(false);
    setNestedEditorCell(null);
  }, []);

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
  // ★ パフォーマンス対策: 以前はレンダーの度に columns 配列を丸ごと
  //   再生成していたため、レコード数・カラム数が増えるとネストダイアログの
  //   入力（nestedEditorValue の更新）のたびに DataGrid 全体の列定義が
  //   作り直され、入力のたびに重くなる原因になっていた。
  //   → 実際に列の内容に影響する値だけを依存配列にした useMemo で包み、
  //     ダイアログ内の入力など無関係な state 更新では再生成されないようにする。
  // ============================================================
  const columns = useMemo(() => [
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
      // ★ 配列型・classData型は元々カスタムエディタ（ダイアログ）が必要だった型
      const needsCustomEditor = isArray || isClass;

      return {
        field: col.name,
        headerName: col.name,
        width: needsCustomEditor ? 260 : 150,
        // ★ 修正: 全カラムをグリッド内編集ではなく、専用ダイアログ編集に統一する。
        //   経緯: DataGridの「セル内編集モード（editable + renderEditCell +
        //   processRowUpdate + getRowHeight）」の組み合わせ自体が、
        //   このグリッドでは打鍵のたびに重く、早いタイピングで入力が
        //   詰まる問題が型を問わず解消しなかった。
        //   classData型・配列型は元々「編集のたびに行高さ再計算が走り、
        //   ドロップダウンが閉じる」問題を避けるためダイアログ編集に
        //   していたが、同じ理屈が通常型（int/float/string/bool/vector/enum）
        //   にも当てはまっていたと考えられる。
        //   → 全カラムをクリックでダイアログを開いて編集する方式に統一し、
        //     タイピング自体をDataGridの再描画サイクルから完全に切り離す。
        editable: false,
        headerAlign: 'right',
        renderHeader: () => (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
            {/* ★ カラム名 + 説明文（あれば括弧書き）で表示 */}
            <Tooltip title={col.description || ''} disableHoverListener={!col.description}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {col.name}{col.description ? `（${col.description}）` : ''}
              </span>
            </Tooltip>
            {/* ★ 型ラベル表示 */}
            <Chip label={col.type} size="small" sx={{ mx: 0.5, height: 16, fontSize: 10, flexShrink: 0 }} />
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

        // ★ 型に応じてDataGridのtype属性を設定（ソート・フィルタ用。
        //   編集自体はダイアログで行うためeditable関連の分岐は不要）
        type: isNumber ? 'number'
          : isBool   ? 'boolean'
          : 'string',

        // ★ 表示用フォーマッタ（classData型・配列型はJSONで表示。
        //   実際の見た目はrenderCellのミニプレビューが優先されるが、
        //   エクスポート等で使われるため残しておく）
        valueFormatter: (value) => {
          if (value === null || value === undefined) return '';
          if (Array.isArray(value)) return `[${value.length}件] ${JSON.stringify(value)}`;
          if (typeof value === 'object') return JSON.stringify(value);
          return value;
        },

        // ★ 全カラム共通: グリッド内は読みやすいプレビュー表示＋編集アイコンのみ。
        //   クリックすると専用ダイアログが開き、そこで実際の編集を行う。
        //   （renderEditCellは使わない＝DataGridの編集モードに一切入らないため、
        //     打鍵のたびにDataGrid側の再計算が走ることがなくなる）
        renderCell: (params) => (
          <Box
            onClick={() => openNestedEditor(params.id, col.name, col.type, col.options)}
            sx={{
              width: '100%',
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              gap: 0.25,
              cursor: 'pointer',
              px: 0.5,
              py: 0.5,
              '&:hover': { bgcolor: 'action.hover' },
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <EditIcon fontSize="small" color="action" sx={{ flexShrink: 0 }} />
              <Typography variant="caption" color="text.disabled">クリックで編集</Typography>
            </Box>
            {renderMiniPreviewTable(params.value, col.type, classSchemas, col.options)}
          </Box>
        ),
      };
    }),
  ], [data.columns, enumValues, classSchemas, classList, getDefaultValue, handleDeleteRow, openNestedEditor]);

  // ============================================================
  // getRowHeightForRow: 行の高さを「数値」で計算して返す
  // ★ classData型・配列型カラムはプレビュー行数に応じて縦に伸びる必要が
  //   あるが、getRowHeight={() => 'auto'} のようなDOM実測方式だと
  //   グリッド内部stateが変わるたび（＝1打鍵ごと）に全行の高さ再計算が
  //   走ってしまう（レコード数に比例して重くなる主因だった）。
  //   → セルの値から必要な行数を事前計算し、数値としての高さを返すことで
  //     DOM実測（autoモード特有の重い経路）を完全に回避する。
  // ============================================================
  const LINE_HEIGHT_PX = 18;
  const ROW_BASE_HEIGHT_PX = 52; // 通常セル（1行）の最低高さ
  const ROW_VERTICAL_PADDING_PX = 24; // 上下パディング分

  const getRowHeightForRow = useCallback((params) => {
    const row = params.model || {};
    let maxLines = 1;
    data.columns.forEach((col) => {
      // ★ 全カラムがクリックで編集方式になったため、
      //   「クリックで編集」ラベル分の1行を全カラムに加算する
      const lines = countPreviewLines(row[col.name], col.type, classSchemas, col.options) + 1;
      if (lines > maxLines) maxLines = lines;
    });
    return Math.max(ROW_BASE_HEIGHT_PX, maxLines * LINE_HEIGHT_PX + ROW_VERTICAL_PADDING_PX);
  }, [data.columns, classSchemas]);

  // ★「新しいカラムを追加」ダイアログの型オプション用
  const isNewColNumeric = OPTIONS_NUMERIC_TYPES.includes(newColType);
  const isNewColArray = newColType.endsWith('[]');
  const newColKeyTypeOptions = ['int', ...enumNames, ...classDataIdNames, ...customClassDataIdNames];
  const newColValueTypeOptions = typeOptions.filter(t => t !== 'dictionary' && !t.endsWith('[]'));
  const handleNewColTypeChange = (t) => {
    setNewColType(t || '');
    setNewColOptions(defaultOptionsForNewColumnType(t || ''));
  };

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
            // ★ 行高さをコンテンツ（プレビュー行数）に応じて計算する。
            //   'auto'（DOM実測）だと入力のたびに全行再計算が走り重くなるため、
            //   事前計算した「数値」を返す方式に変更。
            getRowHeight={getRowHeightForRow}
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
            onChange={(e, newValue) => handleNewColTypeChange(newValue)}
          />
          <TextField
            label="名前"
            margin="dense"
            fullWidth
            value={newColName}
            onChange={(e) => setNewColName(e.target.value)}
          />
          <TextField
            label="説明"
            margin="dense"
            fullWidth
            value={newColDescription}
            onChange={(e) => setNewColDescription(e.target.value)}
          />

          {(isNewColNumeric || isNewColArray || ['bit', 'color', 'bezier', 'dictionary'].includes(newColType)) && (
            <>
              <Box sx={{ borderTop: '1px solid #eee', mt: 2, pt: 1 }}>
                <Typography variant="subtitle2">型オプション</Typography>
                {isNewColNumeric && <NumericOptionsEditor options={newColOptions} onChange={setNewColOptions} />}
                {isNewColArray && (
                  <ArrayOptionsEditor
                    options={newColOptions}
                    onChange={setNewColOptions}
                    enumNames={enumNames}
                    classDataIdNames={classDataIdNames}
                    customClassDataIdNames={customClassDataIdNames}
                  />
                )}
                {newColType === 'bit' && (
                  <BitOptionsEditor
                    options={newColOptions}
                    onChange={setNewColOptions}
                    enumNames={enumNames}
                    classDataIdNames={classDataIdNames}
                    customClassDataIdNames={customClassDataIdNames}
                  />
                )}
                {newColType === 'color' && (
                  <Typography variant="caption" color="text.secondary">
                    RGBAカラー型です。実際の色の値は各レコードで設定します。
                  </Typography>
                )}
                {newColType === 'bezier' && (
                  <BezierOptionsEditor options={newColOptions} onChange={setNewColOptions} />
                )}
                {newColType === 'dictionary' && (
                  <DictionaryOptionsEditor
                    options={newColOptions}
                    onChange={setNewColOptions}
                    keyTypeOptions={newColKeyTypeOptions}
                    valueTypeOptions={newColValueTypeOptions}
                    enumNames={enumNames}
                    classDataIdNames={classDataIdNames}
                    customClassDataIdNames={customClassDataIdNames}
                  />
                )}
              </Box>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setOpenAddColumn(false); setNewColDescription(''); setNewColOptions({}); }}>キャンセル</Button>
          <Button onClick={handleAddColumn}>追加</Button>
        </DialogActions>
      </Dialog>

      {/* レコード追加ダイアログ */}
      <Dialog open={openDefaultRecords} onClose={() => setOpenDefaultRecords(false)}>
        <DialogTitle>新しくレコード追加</DialogTitle>
        <DialogContent>
          <NumericTextField
            label="レコード数"
            allowDecimal={false}
            margin="dense"
            fullWidth
            value={recordCount}
            onChange={(val) => setRecordCount(val || 1)}
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

      {/* classData型・配列型セル編集ダイアログ */}
      {/* ★ グリッドの外にある広いダイアログで編集するため、
             行高さ再計算によるドロップダウンの強制クローズが起きず、
             幅・高さの制約もなく入力しやすい */}
      <Dialog
        open={nestedEditorOpen}
        onClose={(event, reason) => {
          if (reason === 'backdropClick' || reason === 'escapeKeyDown') {
            // ダイアログ外クリック/Escapeでの意図しない破棄を防ぐため、保存するか確認する
            if (window.confirm('変更を保存しますか？\n（キャンセルすると変更は破棄されます）')) {
              handleNestedEditorSave(nestedEditorValueRef.current);
            } else {
              setNestedEditorOpen(false);
              setNestedEditorCell(null);
            }
            return;
          }
          setNestedEditorOpen(false);
        }}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          データ編集
          {nestedEditorCell ? (() => {
            const editingRow = data.rows.find(r => r.id === nestedEditorCell.rowId);
            const recordLabel = editingRow
              ? `${editingRow.enum_property}${editingRow.description ? `（${editingRow.description}）` : ''}`
              : '';
            return ` - ${recordLabel} / ${nestedEditorCell.field} (${nestedEditorCell.type})`;
          })() : ''}
        </DialogTitle>
        {nestedEditorCell && (
          <NestedEditorDialogBody
            key={`${nestedEditorCell.rowId}:${nestedEditorCell.field}`}
            cellInfo={nestedEditorCell}
            enumValues={enumValues}
            classSchemas={classSchemas}
            onSave={handleNestedEditorSave}
            onCancel={() => setNestedEditorOpen(false)}
            valueRef={nestedEditorValueRef}
          />
        )}
      </Dialog>
    </Box>
  );
}

export default ClassDataIdDetailGrid;