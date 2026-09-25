import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import {
  Button, Box, Typography, TextField, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete,
  Select, MenuItem, FormControl, InputLabel, Checkbox, FormControlLabel, IconButton, Tooltip,
  Chip, Divider
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import LockIcon from '@mui/icons-material/Lock';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import SubdirectoryArrowRightIcon from '@mui/icons-material/SubdirectoryArrowRight';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import BaseRoleInputForm from '../scenario/BaseRoleInputForm';

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
function isParentCandidateType(type, enumNames, classDataIdNames) {
  if (!type) return false;
  const t = String(type).toLowerCase();
  if (t === 'bool' || t === 'boolean') return true;
  if ((enumNames || []).includes(type)) return true;
  if ((classDataIdNames || []).includes(type)) return true;
  return false;
}

// options（型ごとの追加設定）を持つ型の一覧。
// ここに載っている型だけ、行の「オプション」列と追加ダイアログに編集UIが出る。
const OPTION_EDITABLE_TYPES = ['bit', 'bezier', 'dictionary', 'text_list_index'];
// voice_ref は options 編集UIこそ出さないが(参照先Matrixは固定のため)、追加した直後から
// options を空 {} のまま保存しないよう、既定値だけは defaultOptionsForType で持たせる。

// text_list_index: ScenarioText Matrix の List<string> の何番目かを指す特殊型。
// 実体は int（-1 = 未選択）で、GUI(BaseRoleInputForm.js)側では
// options で指定した Matrix / フィールド / プレビュー言語をもとに、
// 実際のテキストを並べたプルダウンとして描画される。
const DEFAULT_TEXT_LIST_INDEX_OPTIONS = { matrixName: 'ScenarioText', fieldName: 'texts', previewLanguage: 'Ja' };

// voice_ref: ScenarioVoice Matrix の List<SoundID> の何番目かを指す特殊型(text_list_indexと同じ方式)。
const DEFAULT_VOICE_REF_OPTIONS = { matrixName: 'ScenarioVoice', fieldName: 'voices', previewLanguage: 'Ja' };

// bit の初期オプション
function defaultOptionsForType(type) {
  if (type === 'bit') return { sizeMode: 'manual', sizeSourceName: null, size: 8, mode: 'multiple', allowSelectAll: true, flagNames: Array.from({ length: 8 }, (_, i) => `Flag${i}`) };
  if (type === 'bezier') return { valueType: 'float', min: 0, max: 1 };
  if (type === 'dictionary') return { keyType: 'int', valueType: 'int', valueArraySize: 0, valueOptions: {} };
  if (type === 'text_list_index') return { ...DEFAULT_TEXT_LIST_INDEX_OPTIONS };
  if (type === 'voice_ref') return { ...DEFAULT_VOICE_REF_OPTIONS };
  return {};
}

// ============================================================
// オプション編集: bit (CustomClassDataDetailGridの編集UIを流用した簡易版)
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
          <Select label="ビット数の決め方" value={sizeMode}
            onChange={(e) => onChange({ ...options, sizeMode: e.target.value, sizeSourceName: null })}>
            <MenuItem value="manual">手動指定</MenuItem>
            <MenuItem value="enum">Enumの要素数から</MenuItem>
            <MenuItem value="classDataId">ClassDataIDの要素数から</MenuItem>
            <MenuItem value="customClassDataId">CustomClassDataIDの要素数から</MenuItem>
          </Select>
        </FormControl>

        {sizeMode === 'manual' ? (
          <TextField
            label="ビット数" type="number" size="small" value={size}
            onChange={(e) => {
              const n = Math.max(1, Number(e.target.value) || 1);
              const nextFlags = Array.from({ length: n }, (_, i) => flagNames[i] || `Flag${i}`);
              onChange({ ...options, size: n, flagNames: nextFlags });
            }}
          />
        ) : (
          <Autocomplete
            size="small" sx={{ minWidth: 220 }} options={sourceNames}
            value={options.sizeSourceName || null}
            onChange={(e, v) => onChange({ ...options, sizeSourceName: v })}
            renderInput={(params) => <TextField {...params} label="参照元" />}
          />
        )}

        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>選択モード</InputLabel>
          <Select label="選択モード" value={options.mode || 'multiple'}
            onChange={(e) => onChange({ ...options, mode: e.target.value })}>
            <MenuItem value="multiple">複数選択可</MenuItem>
            <MenuItem value="single">1つだけ選択（排他）</MenuItem>
          </Select>
        </FormControl>

        {options.mode !== 'single' && (
          <FormControlLabel
            control={<Checkbox checked={!!options.allowSelectAll} onChange={(e) => onChange({ ...options, allowSelectAll: e.target.checked })} />}
            label="全選択ボタンを許可"
          />
        )}
      </Box>

      {sizeMode === 'manual' && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">フラグ名（各ビットのラベル）</Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 0.5 }}>
            {flagNames.map((n, i) => (
              <TextField key={i} size="small" label={`bit ${i}`} value={n} onChange={(e) => setFlagName(i, e.target.value)} sx={{ width: 130 }} />
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
        <Select label="値の型" value={options.valueType || 'float'} onChange={(e) => onChange({ ...options, valueType: e.target.value })}>
          <MenuItem value="float">float</MenuItem>
          <MenuItem value="int">int</MenuItem>
        </Select>
      </FormControl>
      <TextField label="グラフの最小値" type="number" size="small" value={options.min ?? 0} onChange={(e) => onChange({ ...options, min: Number(e.target.value) })} />
      <TextField label="グラフの最大値" type="number" size="small" value={options.max ?? 1} onChange={(e) => onChange({ ...options, max: Number(e.target.value) })} />
    </Box>
  );
}

// ============================================================
// オプション編集: text_list_index
// どの Matrix のどのフィールドの List を候補として出すか、
// および候補のプレビューに使う言語（行キー）を指定する。
// ============================================================
function TextListIndexOptionsEditor({ options, onChange }) {
  return (
    <Box sx={{ display: 'flex', gap: 2, mt: 1, flexWrap: 'wrap' }}>
      <TextField
        label="Matrix名" size="small" sx={{ minWidth: 160 }}
        value={options.matrixName ?? DEFAULT_TEXT_LIST_INDEX_OPTIONS.matrixName}
        onChange={(e) => onChange({ ...options, matrixName: e.target.value })}
        helperText="例: ScenarioText"
      />
      <TextField
        label="フィールド名" size="small" sx={{ minWidth: 160 }}
        value={options.fieldName ?? DEFAULT_TEXT_LIST_INDEX_OPTIONS.fieldName}
        onChange={(e) => onChange({ ...options, fieldName: e.target.value })}
        helperText="List<string> のフィールド。例: texts"
      />
      <TextField
        label="プレビュー言語" size="small" sx={{ minWidth: 140 }}
        value={options.previewLanguage ?? DEFAULT_TEXT_LIST_INDEX_OPTIONS.previewLanguage}
        onChange={(e) => onChange({ ...options, previewLanguage: e.target.value })}
        helperText="候補表示に使う行。例: Ja"
      />
    </Box>
  );
}

// ============================================================
// オプション編集: dictionary
// キーは数値のみ（int / Enum / ClassDataID / CustomClassDataID）に限定し、
// 値はすべての型（配列・bit/bezierを含む）に対応する
// ============================================================
function DictionaryOptionsEditor({ options, onChange, keyTypeOptions, valueTypeOptions, enumNames, classDataIdNames, customClassDataIdNames }) {
  const keyType = options.keyType || 'int';
  const valueType = options.valueType || 'int';
  const valueArraySize = options.valueArraySize ?? 0;
  const valueOptions = options.valueOptions || {};
  const setValueOptions = (vo) => onChange({ ...options, valueOptions: vo });

  return (
    <Box sx={{ mt: 1 }}>
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>キーの型</InputLabel>
          <Select label="キーの型" value={keyType} onChange={(e) => onChange({ ...options, keyType: e.target.value })}>
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

      {(valueType === 'bit' || valueType === 'bezier') && (
        <Box sx={{ mt: 1.5, p: 1, border: '1px dashed #ccc', borderRadius: 1 }}>
          <Typography variant="caption" color="text.secondary">値の型オプション</Typography>
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
// サブグループ設定のデフォルト値パネル (settingMode のときだけ表示)
// 各フィールドの右のブックマークで「そのフィールドだけ」、下のボタンで「全項目」を
// 手動デフォルトとして保存できる。新しいサブグループ(GUI/DSLのショートカット)を作ったときに、
// まずこの値が入る(手動デフォルトが無いフィールドは型ごとの自動デフォルト)。
// ============================================================
const SETTING_API = '/api/scenario-subgroup-setting';
const SETTING_NAME = 'ScenarioSubGroupSetting';

function SettingDefaultsPanel({ reloadKey }) {
  const [schema, setSchema] = useState(null);
  const [initial, setInitial] = useState([]);
  const [error, setError] = useState('');
  const draftRef = useRef([]);

  useEffect(() => {
    let cancelled = false;
    setError('');
    fetch(`${SETTING_API}/form-schema`)
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then(({ schema: sc, defaults }) => {
        if (cancelled) return;
        setSchema(sc);
        setInitial(defaults || []);
        draftRef.current = defaults || [];
      })
      .catch(e => { if (!cancelled) setError(String(e.message || e)); });
    return () => { cancelled = true; };
  }, [reloadKey]);

  const handleSaveAll = () => {
    const values = {};
    (draftRef.current || []).forEach(d => { values[d.name] = d.value; });
    fetch(`${SETTING_API}/defaults`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ values }),
    })
      .then(res => res.json())
      .then(result => alert(result.message || result.error))
      .catch(e => alert('デフォルト値の保存エラー: ' + e));
  };

  if (error) return <Typography color="error" sx={{ mt: 2 }}>デフォルト値の読み込みエラー: {error}</Typography>;
  if (!schema) return null;
  return (
    <Box sx={{ mt: 3, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1, maxWidth: 720 }}>
      <Typography variant="h6" gutterBottom>デフォルト値</Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        新しいサブグループに最初に入る値です。各項目右のブックマークで項目ごとに、下のボタンで全項目をまとめて保存できます
        （未保存の項目は型ごとの自動デフォルト）。フィールドを追加・削除した直後は、上の「保存」を先に押してください。
        既にあるサブグループの値は変わりません。
      </Typography>
      <BaseRoleInputForm
        schema={schema}
        initialData={initial}
        onChange={(d) => { draftRef.current = d; }}
        roleName={SETTING_NAME}
        fieldDefaultUrl={`${SETTING_API}/field-default`}
      />
      <Button variant="contained" onClick={handleSaveAll} sx={{ mt: 1 }}>全項目をデフォルトとして保存</Button>
    </Box>
  );
}

// settingMode: 「サブグループ設定」(全イベント共通・組み込みフィールド is_wait_key 付き)の
// フィールド定義編集として動かす。Roleのフィールド定義編集と同じ画面・同じ型(class_data_id /
// class_data / enum / bezier / color / bit / 配列 / dictionary / ネスト等)を使えるようにするため、
// このコンポーネントを流用している(ScenarioSubGroupSettingGrid.js が settingMode で呼ぶ)。
function ScenarioRoleDetailGrid({ settingMode = false }) {
  const params = useParams();
  const name = settingMode ? SETTING_NAME : params.name;
  // フィールド定義の取得・保存先(Roleは /api/scenario-role/<name>、設定は /api/scenario-subgroup-setting)
  const definitionUrl = settingMode ? SETTING_API : `/api/scenario-role/${name}`;
  const [savedVersion, setSavedVersion] = useState(0);
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [typeOptions, setTypeOptions] = useState([]);
  const [branchType, setBranchType] = useState('General');
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [newType, setNewType] = useState('');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newArraySize, setNewArraySize] = useState(0);
  const [newOptions, setNewOptions] = useState({});
  // 鍵マーク(必須フィールド)。既定はtrue(=必須)。falseにすると、DSL(Lua風テキスト)
  // 入力でこのフィールドを省略してもエラーにならず、デフォルト値が使われる。
  const [newRequired, setNewRequired] = useState(true);
  // 新規追加時の依存関係
  const [addDepParent, setAddDepParent] = useState(null);
  const [addDepValues, setAddDepValues] = useState([]);

  // bit の sizeMode="enum"/"classDataId"/"customClassDataId" 参照先候補
  const [enumNames, setEnumNames] = useState([]);
  const [classDataIdNames, setClassDataIdNames] = useState([]);
  const [customClassDataIdNames, setCustomClassDataIdNames] = useState([]);

  // 既存行のoptions編集用
  const [optionsEditRow, setOptionsEditRow] = useState(null); // { id, type, options }
  // 依存関係編集用
  const [depEditRow, setDepEditRow] = useState(null); // { id, name, type, dependency }
  const [editDepParent, setEditDepParent] = useState(null);
  const [editDepValues, setEditDepValues] = useState([]);

  // dictionaryのキー型候補: int(数値) + Enum + ClassDataID + CustomClassDataID のみ
  const keyTypeOptions = React.useMemo(() => Array.from(new Set([
    'int', ...enumNames, ...classDataIdNames, ...customClassDataIdNames,
  ])), [enumNames, classDataIdNames, customClassDataIdNames]);

  // 例: 編集ダイアログ用
  const [editParentMemberOptions, setEditParentMemberOptions] = useState([]);

  useEffect(() => {
    if (!editDepParent) {
      setEditParentMemberOptions([]);
      return;
    }
    const parentField = data.find(f => f.name === editDepParent);
    if (!parentField) return;
    const t = parentField.type;
    if (['bool', 'boolean'].includes(String(t).toLowerCase())) {
      setEditParentMemberOptions([
        { value: 'true', label: 'True' },
        { value: 'false', label: 'False' },
      ]);
      return;
    }
    if (enumNames.includes(t)) {
      fetch(`/api/enum/${encodeURIComponent(t)}`)
        .then(r => r.ok ? r.json() : [])
        .then(list => {
          setEditParentMemberOptions(
            (list || []).map(item => {
              const p = item.property || item.enum_property || item;
              return { value: String(p), label: String(p) };
            })
          );
        })
        .catch(() => setEditParentMemberOptions([]));
      return;
    }
    if (classDataIdNames.includes(t)) {
      fetch(`/api/class-data-id/${encodeURIComponent(t)}`)
        .then(r => r.ok ? r.json() : { rows: [] })
        .then(d => {
          setEditParentMemberOptions(
            (d.rows || []).map(row => ({
              value: String(row.enum_property),
              label: String(row.enum_property),
            }))
          );
        })
        .catch(() => setEditParentMemberOptions([]));
      return;
    }
    setEditParentMemberOptions([]);
  }, [editDepParent, data, enumNames, classDataIdNames]);

  // Fetch data for the role
  useEffect(() => {
    fetch(definitionUrl)
      .then(response => response.json())
      .then(fetchedData => {
        setData(fetchedData.data.map((item, index) => ({ ...item, id: item.id || index + 1, required: item.required !== false })));
        setBranchType(fetchedData.branchType || 'General');
        setLoading(false);
      })
      .catch(error => {
        console.error('シナリオロールデータ取得エラー:', error);
        setLoading(false);
      });
  }, [name, definitionUrl]);

  // Fetch type suggestions
  useEffect(() => {
    const basicTypes = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object'];
    const unityTypes = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject'];

    Promise.all([
      fetch('/api/enum-id').then(res => res.json()),
      fetch('/api/class-data').then(res => res.json()),
      fetch('/api/class-data-id').then(res => res.json()),
      // CustomClassData / CustomClassDataID (bit・color・bezier対応版) もロール変数の型として選択できるようにする
      fetch('/api/custom-class-data-type-options').then(res => res.json())
    ]).then(([enumList, classList, classIdList, customOptions]) => {
      const enumTypes = enumList.map(item => item.name);
      const classTypes = classList.map(item => item.name);
      const classIdTypes = classIdList.map(item => item.name);
      const customClassTypes = customOptions.custom_class_list || [];
      const customClassIdTypes = customOptions.custom_class_id_list || [];
      const customValueTypes = Array.from(new Set([...(customOptions.custom_types || []), 'dictionary'])); // ['bit', 'color', 'bezier', 'dictionary']
      // text_list_index / voice_ref はバックエンド(/api/custom-class-data-type-options)が
      // 返す型ではなく、シナリオRole専用の特殊型なのでここで足す。
      //   text_list_index: ScenarioText Matrix の List<string> の何番目か(int)
      //   voice_ref      : ScenarioVoice Matrix の List<SoundID> の何番目か(int、同じ方式)
      const allTypes = [
        ...basicTypes, ...unityTypes,
        ...enumTypes, ...classTypes, ...classIdTypes,
        ...customClassTypes, ...customClassIdTypes, ...customValueTypes,
        'text_list_index', 'voice_ref'
      ];
      // text_list_index / voice_ref はシナリオイベント(eventId/subId)の文脈が必要な型なので、
      // 全イベント共通のサブグループ設定では選べないようにする。
      setTypeOptions(settingMode ? allTypes.filter(t => t !== 'text_list_index' && t !== 'voice_ref') : allTypes);
      setEnumNames(enumTypes);
      setClassDataIdNames(classIdTypes);
      setCustomClassDataIdNames(customClassIdTypes);
    }).catch(error => console.error('タイプオプション取得エラー:', error));
  }, []);

  // Add new row
  const handleAddRow = () => {
    if (!newType.trim() || !newName.trim()) {
      alert('タイプと名前は必須です');
      return;
    }
    if (settingMode && data.some(item => item.name === newName.trim())) {
      alert(`「${newName.trim()}」は既に存在します`);
      return;
    }
    const maxId = Math.max(...data.map(item => item.id), 0) + 1;
    let dependency;
    if (addDepParent) {
      const parentField = data.find(f => f.name === addDepParent);
      dependency = {
        parentFieldName: addDepParent,
        enableValues: addDepValues.length > 0
          ? addDepValues
          : (parentField && String(parentField.type).toLowerCase() === 'bool' ? [true] : []),
        hideWhenDisabled: true,
      };
    }
    const newRow = {
      id: maxId,
      type: newType,
      name: newName,
      description: newDescription,
      arraySize: parseInt(newArraySize, 10) || 0,
      options: OPTION_EDITABLE_TYPES.includes(newType) ? newOptions : undefined,
      required: newRequired,
      ...(dependency ? { dependency } : {}),
    };
    setData([...data, newRow]);
    setOpen(false);
    setNewType('');
    setNewName('');
    setNewDescription('');
    setNewArraySize(0);
    setNewOptions({});
    setNewRequired(true);
    setAddDepParent(null);
    setAddDepValues([]);
  };

  // 既存行のoptionsを保存(bit/bezier)
  const handleSaveRowOptions = () => {
    setData(data.map(item => (item.id === optionsEditRow.id ? { ...item, options: optionsEditRow.options } : item)));
    setOptionsEditRow(null);
  };

  const openDepEdit = (row) => {
    setDepEditRow(row);
    setEditDepParent(row.dependency?.parentFieldName || null);
    setEditDepValues(Array.isArray(row.dependency?.enableValues) ? row.dependency.enableValues.map(String) : []);
  };

  const handleSaveDependency = () => {
    if (!depEditRow) return;
    let dependency;
    if (editDepParent) {
      const parentField = data.find(f => f.name === editDepParent && f.id !== depEditRow.id);
      dependency = {
        parentFieldName: editDepParent,
        enableValues: editDepValues.length > 0
          ? editDepValues
          : (parentField && String(parentField.type).toLowerCase() === 'bool' ? [true] : []),
        hideWhenDisabled: true,
      };
    }
    setData(data.map(item => {
      if (item.id !== depEditRow.id) return item;
      if (dependency) return { ...item, dependency };
      const { dependency: _removed, ...rest } = item;
      return rest;
    }));
    setDepEditRow(null);
    setEditDepParent(null);
    setEditDepValues([]);
  };

  // Delete row（親を消した場合は子の dependency もクリア）
  const handleDeleteRow = (id) => {
    if (settingMode && data.find(item => item.id === id)?.builtin) return; // 組み込みフィールドは削除不可
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
  // 注: DataGridの rowReordering / onRowOrderChange はMUI X の Pro版限定機能で、
  // Community版(@mui/x-data-grid)ではドラッグしても何も起きない(propsが無視される)。
  // そのため上下ボタン(moveRow)での並び替えを別途用意している。この並び順がそのまま
  // {role_name}.json の data 配列順として保存され、Transaction側のGUI入力フォーム・
  // DSLの補完候補もこの順序に従う。

  const moveRow = (id, direction) => {
    const index = data.findIndex((r) => r.id === id);
    const targetIndex = index + direction;
    if (index === -1 || targetIndex < 0 || targetIndex >= data.length) return;
    // 組み込みフィールド(is_wait_key)は常に先頭のまま。動かすことも、その上へ割り込むこともできない。
    if (settingMode && (data[index]?.builtin || data[targetIndex]?.builtin)) return;
    const newData = [...data];
    const [movedRow] = newData.splice(index, 1);
    newData.splice(targetIndex, 0, movedRow);
    setData(newData);
  };

  // 鍵マーク(必須フィールド)の切り替え。falseにすると、DSL入力時にこのフィールドを
  // 省略してもエラーにならず、デフォルト値(このgridで設定した「デフォルト値」、
  // 無ければ型ごとの初期値)がそのまま使われる。
  const toggleRequired = (id) => {
    setData(data.map((item) => {
      if (item.id !== id) return item;
      const isCurrentlyRequired = item.required !== false; // undefined/true => 必須扱い
      return { ...item, required: !isCurrentlyRequired };
    }));
  };

  // Save data
  const handleSave = () => {
    fetch(definitionUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data, branchType }),
    })
      .then(response => response.json())
      .then(result => {
        // 設定の場合、サーバーが全シナリオの既存サブグループへ追加/削除フィールドを反映し、
        // ScenarioSubGroupSetting.cs も再生成している。その結果を併せて知らせる。
        let msg = result.message || result.error || '';
        if (settingMode && result.sync) msg += `\n（既存シナリオの ${result.sync.nodes_touched} 個のサブグループへ反映）`;
        if (settingMode && result.error_detail) msg += `\n⚠ ${result.error_detail}`;
        alert(msg);
        if (settingMode) setSavedVersion(v => v + 1);
      })
      .catch(error => alert('データ保存エラー: ' + error));
  };

  // Delete role
  const handleDelete = () => {
    if (window.confirm(`ロール ${name} を削除しますか？`)) {
      fetch(`/api/scenario-role/${name}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
          alert(result.message);
          navigate('/scenario-role');
        })
        .catch(error => alert('ロール削除エラー: ' + error));
    }
  };

  // Generate C#
  const handleGenerateCs = () => {
    fetch(settingMode ? `${SETTING_API}/generate` : `/api/generate-scenario-role/${name}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data, branchType }),
    })
      .then(response => response.json())
      .then(result => alert(result.message))
      .catch(error => alert('C#生成エラー: ' + error));
  };

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
    {
      field: 'order',
      headerName: '順序',
      width: 90,
      sortable: false,
      renderCell: (params) => {
        const index = data.findIndex((r) => r.id === params.row.id);
        return (
          <Box sx={{ display: 'flex' }}>
            <IconButton size="small" disabled={index === 0} onClick={() => moveRow(params.row.id, -1)}>
              <ArrowUpwardIcon fontSize="small" />
            </IconButton>
            <IconButton size="small" disabled={index === data.length - 1} onClick={() => moveRow(params.row.id, 1)}>
              <ArrowDownwardIcon fontSize="small" />
            </IconButton>
          </Box>
        );
      }
    },
    {
      field: 'required',
      headerName: '必須',
      width: 70,
      sortable: false,
      renderCell: (params) => (
        <Tooltip title={params.row.required !== false ? '必須（DSLで省略不可）。クリックで任意に切り替え' : '任意（DSLで省略可・省略時はデフォルト値）。クリックで必須に切り替え'}>
          <IconButton size="small" onClick={() => toggleRequired(params.row.id)}>
            {params.row.required !== false ? <LockIcon fontSize="small" color="warning" /> : <LockOpenIcon fontSize="small" color="disabled" />}
          </IconButton>
        </Tooltip>
      )
    },
    {
      field: 'type',
      headerName: 'タイプ',
      width: 160,
      renderCell: (params) => params.value,
      editable: true,
      renderEditCell: (params) => (
        <Autocomplete
          freeSolo
          options={typeOptions}
          value={params.value}
          onChange={(e, newValue) => params.api.setEditCellValue({ id: params.id, field: params.field, value: newValue })}
          renderInput={(params) => <TextField {...params} />}
        />
      )
    },
    { field: 'name', headerName: '名前', width: 120, editable: true },
    { field: 'description', headerName: '説明', width: 160, editable: true },
    { field: 'arraySize', headerName: '配列サイズ', width: 110, editable: true, type: 'number' },
    {
      field: 'options',
      headerName: 'オプション',
      width: 90,
      renderCell: (params) => (
        OPTION_EDITABLE_TYPES.includes(params.row.type) ? (
          <Button
            size="small" startIcon={<EditIcon fontSize="small" />}
            onClick={() => setOptionsEditRow({ id: params.row.id, type: params.row.type, options: params.row.options || defaultOptionsForType(params.row.type) })}
          >
            編集
          </Button>
        ) : null
      )
    },
    {
      field: 'dependency',
      headerName: '依存関係',
      width: 240,
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
                    cursor: 'pointer',
                  }}
                  onClick={() => openDepEdit(row)}
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
              <Button size="small" variant="text" onClick={() => openDepEdit(row)} sx={{ minWidth: 0, p: 0.25 }}>
                <Typography variant="caption" color="text.disabled">設定</Typography>
              </Button>
            )}
          </Box>
        );
      },
    },
    {
      field: 'actions',
      headerName: 'アクション',
      width: 100,
      renderCell: (params) => (
        <Button
          variant="contained" color="error" size="small"
          disabled={settingMode && !!params.row.builtin}
          onClick={() => handleDeleteRow(params.id)}
        >
          {settingMode && params.row.builtin ? '組み込み' : '削除'}
        </Button>
      )
    }
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        {settingMode ? 'サブグループ設定（全イベント共通）' : `シナリオロール詳細: ${name}`}
      </Typography>
      {settingMode && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 800 }}>
          サブグループ（ロールを追加する各グループ）ごとに持たせる設定のフィールド定義です。全イベント・全サブグループで共通です。
          先頭の <b>is_wait_key</b>（入力待ち）は組み込みで、削除・改名はできません（デフォルト値は下で変更できます）。
          フィールドを追加・削除して「保存」すると、既存のすべてのサブグループへ反映され（追加はデフォルト値、削除は除去）、
          C#（ScenarioSubGroupSetting.cs）も再生成されます。
        </Typography>
      )}
      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
        {!settingMode && (
          <Autocomplete
            options={['General', 'Branch']}
            value={branchType}
            onChange={(e, newValue) => setBranchType(newValue || 'General')}
            renderInput={(params) => <TextField {...params} label="ロールタイプ" sx={{ width: 200, mr: 2 }} />}
          />
        )}
        <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setOpen(true)} sx={{ mr: 1 }}>
          新しい変数を追加
        </Button>
        <Button variant="contained" color="primary" onClick={handleSave} sx={{ mr: 1 }}>
          保存
        </Button>
        <Button variant="contained" color="secondary" onClick={handleGenerateCs} sx={{ mr: 1 }}>
          C#を生成
        </Button>
        {!settingMode && (
          <Button variant="contained" color="error" onClick={handleDelete}>
            削除
          </Button>
        )}
      </Box>
      {loading ? (
        <Typography>読み込み中...</Typography>
      ) : (
        <div style={{ height: 400, width: '100%' }}>
          <DataGrid
            rows={data}
            columns={columns}
            pageSizeOptions={[5]}
            getRowId={(row) => row.id}
            isCellEditable={(cell) => !(settingMode && cell.row.builtin)}
          />
        </div>
      )}
      {settingMode && !loading && <SettingDefaultsPanel reloadKey={savedVersion} />}
      <Dialog open={open} onClose={() => setOpen(false)}>
        <DialogTitle>新しい変数を追加</DialogTitle>
        <DialogContent>
          <Autocomplete
            freeSolo
            options={typeOptions}
            renderInput={(params) => <TextField {...params} label="タイプ" margin="dense" fullWidth />}
            value={newType}
            onChange={(e, newValue) => {
              setNewType(newValue);
              setNewOptions(OPTION_EDITABLE_TYPES.includes(newValue) ? defaultOptionsForType(newValue) : {});
            }}
          />
          <TextField label="名前" margin="dense" fullWidth value={newName} onChange={(e) => setNewName(e.target.value)} />
          <TextField label="説明" margin="dense" fullWidth value={newDescription} onChange={(e) => setNewDescription(e.target.value)} />
          <TextField label="配列サイズ" margin="dense" fullWidth type="number" value={newArraySize} onChange={(e) => setNewArraySize(e.target.value)} />
          <FormControlLabel
            control={<Checkbox checked={newRequired} onChange={(e) => setNewRequired(e.target.checked)} />}
            label="必須（鍵マーク・DSLで省略不可にする）"
          />
          {newType === 'bit' && (
            <BitOptionsEditor
              options={newOptions} onChange={setNewOptions}
              enumNames={enumNames} classDataIdNames={classDataIdNames} customClassDataIdNames={customClassDataIdNames}
            />
          )}
          {newType === 'bezier' && (
            <BezierOptionsEditor options={newOptions} onChange={setNewOptions} />
          )}
          {newType === 'dictionary' && (
            <DictionaryOptionsEditor
              options={newOptions} onChange={setNewOptions}
              keyTypeOptions={keyTypeOptions}
              valueTypeOptions={typeOptions.filter(t => t !== 'dictionary')}
              enumNames={enumNames} classDataIdNames={classDataIdNames} customClassDataIdNames={customClassDataIdNames}
            />
          )}
          {newType === 'text_list_index' && (
            <TextListIndexOptionsEditor options={newOptions} onChange={setNewOptions} />
          )}
          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <AccountTreeIcon fontSize="small" color="primary" />
            依存関係（親フィールド）
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            enum / bool / class_data_id を親に指定。条件値は OR（いずれか一致）。
          </Typography>
          <Autocomplete
            size="small"
            options={data.filter(f => isParentCandidateType(f.type, enumNames, classDataIdNames))}
            getOptionLabel={(opt) => `${opt.name} (${opt.type})`}
            value={data.find(f => f.name === addDepParent) || null}
            onChange={(e, v) => {
              setAddDepParent(v ? v.name : null);
              if (v && String(v.type).toLowerCase() === 'bool') setAddDepValues(['true']);
              else if (!v) setAddDepValues([]);
            }}
            renderInput={(params) => (
              <TextField {...params} label="親フィールド" margin="dense" fullWidth placeholder="なし（独立）" />
            )}
            isOptionEqualToValue={(a, b) => a?.name === b?.name}
          />
          {addDepParent && (
            <Autocomplete
              multiple
              freeSolo
              size="small"
              options={
                (() => {
                  const p = data.find(f => f.name === addDepParent);
                  return p && String(p.type).toLowerCase() === 'bool' ? ['true', 'false'] : [];
                })()
              }
              value={addDepValues}
              onChange={(e, v) => setAddDepValues(v.map(String))}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="有効になる値（OR・複数可）"
                  margin="dense"
                  fullWidth
                  placeholder="例: hoge, fuga（Enterで追加）"
                  helperText="親がこれらの値のいずれかと一致するとき編集可能"
                />
              )}
              renderTags={(value, getTagProps) =>
                value.map((option, index) => (
                  <Chip variant="outlined" size="small" label={String(option)} {...getTagProps({ index })} key={`${option}-${index}`} sx={{ borderStyle: 'dashed' }} />
                ))
              }
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>キャンセル</Button>
          <Button onClick={handleAddRow}>追加</Button>
        </DialogActions>
      </Dialog>

      {/* 既存行(bit/bezier/dictionary/text_list_index)のオプション編集 */}
      <Dialog open={!!optionsEditRow} onClose={() => setOptionsEditRow(null)} maxWidth="md" fullWidth>
        <DialogTitle>オプション編集</DialogTitle>
        <DialogContent>
          {optionsEditRow && optionsEditRow.type === 'bit' && (
            <BitOptionsEditor
              options={optionsEditRow.options}
              onChange={(opts) => setOptionsEditRow({ ...optionsEditRow, options: opts })}
              enumNames={enumNames} classDataIdNames={classDataIdNames} customClassDataIdNames={customClassDataIdNames}
            />
          )}
          {optionsEditRow && optionsEditRow.type === 'bezier' && (
            <BezierOptionsEditor
              options={optionsEditRow.options}
              onChange={(opts) => setOptionsEditRow({ ...optionsEditRow, options: opts })}
            />
          )}
          {optionsEditRow && optionsEditRow.type === 'dictionary' && (
            <DictionaryOptionsEditor
              options={optionsEditRow.options}
              onChange={(opts) => setOptionsEditRow({ ...optionsEditRow, options: opts })}
              keyTypeOptions={keyTypeOptions}
              valueTypeOptions={typeOptions.filter(t => t !== 'dictionary')}
              enumNames={enumNames} classDataIdNames={classDataIdNames} customClassDataIdNames={customClassDataIdNames}
            />
          )}
          {optionsEditRow && optionsEditRow.type === 'text_list_index' && (
            <TextListIndexOptionsEditor
              options={optionsEditRow.options}
              onChange={(opts) => setOptionsEditRow({ ...optionsEditRow, options: opts })}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOptionsEditRow(null)}>キャンセル</Button>
          <Button onClick={handleSaveRowOptions}>保存</Button>
        </DialogActions>
      </Dialog>

      {/* 依存関係編集 */}
      <Dialog open={!!depEditRow} onClose={() => setDepEditRow(null)} maxWidth="sm" fullWidth>
        <DialogTitle>
          依存関係の編集
          {depEditRow ? ` — ${depEditRow.name}` : ''}
        </DialogTitle>
        <DialogContent>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            親は enum / bool / class_data_id のみ。子は親を1人だけ持てます。条件値は OR です。
          </Typography>
          <Autocomplete
            size="small"
            options={data.filter(f =>
              depEditRow && f.id !== depEditRow.id && isParentCandidateType(f.type, enumNames, classDataIdNames)
            )}
            getOptionLabel={(opt) => `${opt.name} (${opt.type})`}
            value={data.find(f => f.name === editDepParent) || null}
            onChange={(e, v) => {
              setEditDepParent(v ? v.name : null);
              if (v && String(v.type).toLowerCase() === 'bool') setEditDepValues(['true']);
              else if (!v) setEditDepValues([]);
            }}
            renderInput={(params) => (
              <TextField {...params} label="親フィールド" margin="dense" fullWidth placeholder="なし（独立）" />
            )}
            isOptionEqualToValue={(a, b) => a?.name === b?.name}
          />
          {editDepParent && (
            <DependencyValuesEditor
              parentType={data.find(f => f.name === editDepParent)?.type}
              values={editDepValues}
              onChange={setEditDepValues}
              enumMemberOptions={editParentMemberOptions}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDepEditRow(null)}>キャンセル</Button>
          <Button onClick={handleSaveDependency} variant="contained">保存</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default ScenarioRoleDetailGrid;