import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Typography, Paper, Button, Grid, Autocomplete, TextField,
  FormControlLabel, Checkbox, Select, MenuItem, FormControl, InputLabel,
  List, ListItem, ListItemText, IconButton, Chip, Divider, Alert, Tabs, Tab,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import SaveIcon from '@mui/icons-material/Save';

// シナリオのサブイベントごとに設定する「物語設定」画面。
// 事前ロードしておきたい素材（Texture画像・SE・BGM・GameObjectエフェクト）
// と、Voice系列（voice_series_id）への参照を、検索付きでスロットに割り当てる。
// pythonSrc/story_setting.py の /api/story-setting/*, /api/scenario-event/.../story を利用。

const KIND_DEFS = {
  img: { prefix: 'img', label: '画像(Texture)' },
  se: { prefix: 'sound_se', label: 'SE' },
  bgm: { prefix: 'sound_bgm', label: 'BGM' },
  effect: { prefix: 'effect', label: 'エフェクト(GameObject)' },
};

function flattenAssetGroups(groups, filterFn) {
  const result = [];
  Object.entries(groups || {}).forEach(([groupName, groupValue]) => {
    (groupValue?.items || []).forEach((item) => {
      if (filterFn && !filterFn(item)) return;
      result.push({ group: groupName, ...item });
    });
  });
  return result;
}

function optionLabel(opt) {
  return `${opt.group} / ${opt.name}`;
}

function ScenarioStorySettingGrid() {
  const { eventId, subId } = useParams();
  const navigate = useNavigate();

  const [tab, setTab] = useState('img');
  const [slots, setSlots] = useState([]); // [{slot, kind, group, id, spriteName, retain}]
  const [voiceSeriesId, setVoiceSeriesId] = useState(null); // {group, subGroup, retain}
  const [slotDefs, setSlotDefs] = useState([]);

  const [textureOptions, setTextureOptions] = useState([]);
  const [seOptions, setSeOptions] = useState([]);
  const [bgmOptions, setBgmOptions] = useState([]);
  const [effectOptions, setEffectOptions] = useState([]);
  const [voiceSeriesOptions, setVoiceSeriesOptions] = useState([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    setLoading(true);
    setErrorMsg('');
    Promise.all([
      fetch('/api/story-setting/slot-defs').then((r) => r.json()),
      fetch(`/api/scenario-event/${eventId}/sub/${subId}/story`).then((r) => r.json()),
      fetch('/api/texture').then((r) => r.json()),
      fetch('/api/sound').then((r) => r.json()),
      fetch('/api/gameobject').then((r) => r.json()),
    ])
      .then(([defs, story, textureData, soundData, gameObjectData]) => {
        setSlotDefs(defs);
        setSlots(story.slots || []);
        setVoiceSeriesId(story.voiceSeriesId || null);

        setTextureOptions(flattenAssetGroups(textureData.groups));
        setSeOptions(flattenAssetGroups(soundData.groups, (it) => it.type === 'SE'));
        setBgmOptions(flattenAssetGroups(soundData.groups, (it) => it.type === 'BGM'));
        setEffectOptions(flattenAssetGroups(gameObjectData.groups));

        // Voice系列 = (group, subgroup) の組み合わせごとに集約
        const voiceItems = flattenAssetGroups(soundData.groups, (it) => it.type === 'VOICE');
        const seriesMap = new Map();
        voiceItems.forEach((it) => {
          if (!it.subgroup) return;
          const key = `${it.group}::${it.subgroup}`;
          seriesMap.set(key, { group: it.group, subGroup: it.subgroup, count: (seriesMap.get(key)?.count || 0) + 1 });
        });
        setVoiceSeriesOptions(Array.from(seriesMap.values()));
      })
      .catch((e) => setErrorMsg('取得エラー: ' + e.message))
      .finally(() => setLoading(false));
  }, [eventId, subId]);

  const usedSlotNumbers = useCallback((prefix) => {
    return new Set(slots.filter((s) => s.slot.startsWith(`${prefix}_`)).map((s) => s.slot));
  }, [slots]);

  const availableSlotNames = useCallback((kind) => {
    const def = slotDefs.find((d) => d.prefix === KIND_DEFS[kind].prefix);
    if (!def) return [];
    const used = usedSlotNumbers(KIND_DEFS[kind].prefix);
    return def.names.filter((n) => !used.has(n));
  }, [slotDefs, usedSlotNumbers]);

  const handleAddSlot = (kind, slotName, asset, spriteName, retain) => {
    if (!slotName || !asset) return;
    setSlots((prev) => [...prev, {
      slot: slotName,
      kind,
      group: asset.group,
      id: asset.name,
      spriteName: kind === 'img' ? (spriteName || null) : undefined,
      retain: !!retain,
    }]);
  };

  const handleRemoveSlot = (slotName) => {
    setSlots((prev) => prev.filter((s) => s.slot !== slotName));
  };

  const handleToggleRetain = (slotName) => {
    setSlots((prev) => prev.map((s) => (s.slot === slotName ? { ...s, retain: !s.retain } : s)));
  };

  const handleSave = () => {
    setSaving(true);
    fetch(`/api/scenario-event/${eventId}/sub/${subId}/story`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slots, voiceSeriesId }),
    })
      .then((r) => r.json())
      .then((result) => alert(result.message || result.error))
      .catch((e) => alert('保存エラー: ' + e.message))
      .finally(() => setSaving(false));
  };

  const [generating, setGenerating] = useState(false);
  const handleGenerateAll = () => {
    setGenerating(true);
    fetch('/api/story-setting/generate', { method: 'POST' })
      .then((r) => r.json())
      .then((result) => alert(result.message || result.error))
      .catch((e) => alert('生成エラー: ' + e.message))
      .finally(() => setGenerating(false));
  };

  const handleGenerateVoiceRole = () => {
    fetch('/api/story-setting/generate-voice-role', { method: 'POST' })
      .then((r) => r.json())
      .then((result) => alert(result.message || result.error))
      .catch((e) => alert('生成エラー: ' + e.message));
  };

  const slotsForKind = (kind) => slots.filter((s) => s.kind === kind);

  if (loading) return <Box sx={{ p: 3 }}><Typography>読み込み中...</Typography></Box>;

  return (
    <Box sx={{ p: 3 }}>
      <Button variant="text" onClick={() => navigate(-1)} sx={{ mb: 1 }}>&larr; 戻る</Button>
      <Typography variant="h4" gutterBottom>
        物語設定: {eventId} / sub {subId}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        このサブイベント再生前に事前ロードしておく素材を、スロット単位で割り当てます。
        「保持」にチェックした項目は、サブイベントが切り替わってGroup/SubGroupが変わっても
        解放されず、次の物語設定でも再ロードされません。
      </Typography>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存'}
        </Button>
        <Button variant="outlined" onClick={handleGenerateAll} disabled={generating}>
          {generating ? '生成中...' : '全サブイベント分をC#/バイナリ生成'}
        </Button>
        <Button variant="outlined" onClick={handleGenerateVoiceRole}>
          Voice専用Roleを生成
        </Button>
      </Box>

      <Tabs value={tab} onChange={(e, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="img" label={`画像 (${slotsForKind('img').length})`} />
        <Tab value="se" label={`SE (${slotsForKind('se').length})`} />
        <Tab value="bgm" label={`BGM (${slotsForKind('bgm').length})`} />
        <Tab value="effect" label={`エフェクト (${slotsForKind('effect').length})`} />
        <Tab value="voice" label="Voice系列" />
      </Tabs>

      {tab === 'img' && (
        <SlotSection
          kind="img" label="画像(Texture)"
          slots={slotsForKind('img')}
          options={textureOptions}
          availableSlotNames={availableSlotNames('img')}
          hasSprite
          onAdd={handleAddSlot}
          onRemove={handleRemoveSlot}
          onToggleRetain={handleToggleRetain}
        />
      )}
      {tab === 'se' && (
        <SlotSection
          kind="se" label="SE"
          slots={slotsForKind('se')}
          options={seOptions}
          availableSlotNames={availableSlotNames('se')}
          onAdd={handleAddSlot}
          onRemove={handleRemoveSlot}
          onToggleRetain={handleToggleRetain}
        />
      )}
      {tab === 'bgm' && (
        <SlotSection
          kind="bgm" label="BGM"
          slots={slotsForKind('bgm')}
          options={bgmOptions}
          availableSlotNames={availableSlotNames('bgm')}
          onAdd={handleAddSlot}
          onRemove={handleRemoveSlot}
          onToggleRetain={handleToggleRetain}
        />
      )}
      {tab === 'effect' && (
        <SlotSection
          kind="effect" label="エフェクト(GameObject)"
          slots={slotsForKind('effect')}
          options={effectOptions}
          availableSlotNames={availableSlotNames('effect')}
          onAdd={handleAddSlot}
          onRemove={handleRemoveSlot}
          onToggleRetain={handleToggleRetain}
        />
      )}
      {tab === 'voice' && (
        <VoiceSeriesSection
          value={voiceSeriesId}
          options={voiceSeriesOptions}
          onChange={setVoiceSeriesId}
        />
      )}
    </Box>
  );
}

function SlotSection({ kind, label, slots, options, availableSlotNames, hasSprite, onAdd, onRemove, onToggleRetain }) {
  const [slotName, setSlotName] = useState('');
  const [asset, setAsset] = useState(null);
  const [spriteName, setSpriteName] = useState('');
  const [retain, setRetain] = useState(false);

  useEffect(() => {
    setSlotName(availableSlotNames[0] || '');
  }, [availableSlotNames]);

  const spriteOptions = asset?.sprites || [];

  const handleAdd = () => {
    onAdd(kind, slotName, asset, spriteName, retain);
    setAsset(null);
    setSpriteName('');
    setRetain(false);
  };

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1 }}>割り当て済み（{slots.length}件）</Typography>
      {slots.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>まだありません。</Typography>
      ) : (
        <List dense sx={{ mb: 2 }}>
          {slots.map((s) => (
            <ListItem
              key={s.slot}
              secondaryAction={
                <IconButton size="small" onClick={() => onRemove(s.slot)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              }
            >
              <ListItemText
                primary={
                  <>
                    <Chip size="small" label={s.slot} sx={{ mr: 1 }} />
                    {s.group} / {s.id}{s.spriteName ? ` (Sprite: ${s.spriteName})` : ''}
                  </>
                }
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={!!s.retain} onChange={() => onToggleRetain(s.slot)} />}
                label="保持"
                sx={{ mr: 2 }}
              />
            </ListItem>
          ))}
        </List>
      )}

      <Divider sx={{ mb: 2 }} />

      <Typography variant="subtitle2" sx={{ mb: 1 }}>スロットを追加</Typography>
      <Grid container spacing={2} alignItems="center">
        <Grid item xs={12} sm={2}>
          <FormControl size="small" fullWidth>
            <InputLabel>スロット</InputLabel>
            <Select label="スロット" value={slotName} onChange={(e) => setSlotName(e.target.value)}>
              {availableSlotNames.map((n) => <MenuItem key={n} value={n}>{n}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} sm={hasSprite ? 4 : 6}>
          <Autocomplete
            size="small"
            options={options}
            value={asset}
            onChange={(e, v) => { setAsset(v); setSpriteName(''); }}
            getOptionLabel={optionLabel}
            isOptionEqualToValue={(a, b) => a.group === b.group && a.name === b.name}
            renderInput={(params) => <TextField {...params} label={`${label}を検索`} />}
          />
        </Grid>
        {hasSprite && (
          <Grid item xs={12} sm={3}>
            <Autocomplete
              size="small"
              options={spriteOptions}
              value={spriteName || null}
              onChange={(e, v) => setSpriteName(v || '')}
              disabled={spriteOptions.length === 0}
              renderInput={(params) => <TextField {...params} label="Sprite(任意)" />}
            />
          </Grid>
        )}
        <Grid item xs={6} sm={2}>
          <FormControlLabel
            control={<Checkbox checked={retain} onChange={(e) => setRetain(e.target.checked)} />}
            label="保持"
          />
        </Grid>
        <Grid item xs={6} sm={1}>
          <Button variant="contained" startIcon={<AddIcon />} onClick={handleAdd} disabled={!slotName || !asset}>
            追加
          </Button>
        </Grid>
      </Grid>
    </Paper>
  );
}

function VoiceSeriesSection({ value, options, onChange }) {
  const selected = useMemo(() => {
    if (!value) return null;
    return options.find((o) => o.group === value.group && o.subGroup === value.subGroup) || null;
  }, [value, options]);

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Voice系列は個別のセリフではなく「大本」（Group + SubGroup）単位で1つだけ指定します。
        実際のセリフ選択（Transaction入力時）は、ここで指定したVoice系列に属するIDだけが
        カスケードで絞り込まれます（例: Sound_Scenario_TestScene 配下のみ選択可能になる）。
      </Typography>
      <Grid container spacing={2} alignItems="center">
        <Grid item xs={12} sm={6}>
          <Autocomplete
            size="small"
            options={options}
            value={selected}
            onChange={(e, v) => onChange(v ? { group: v.group, subGroup: v.subGroup, retain: value?.retain || false } : null)}
            getOptionLabel={(o) => `Sound_${o.group}_${o.subGroup}（VOICE ${o.count}件）`}
            isOptionEqualToValue={(a, b) => a.group === b.group && a.subGroup === b.subGroup}
            renderInput={(params) => <TextField {...params} label="Voice系列を検索" />}
          />
        </Grid>
        <Grid item xs={12} sm={3}>
          <FormControlLabel
            control={
              <Checkbox
                checked={!!value?.retain}
                disabled={!value}
                onChange={(e) => onChange(value ? { ...value, retain: e.target.checked } : null)}
              />
            }
            label="保持"
          />
        </Grid>
        <Grid item xs={12} sm={3}>
          <Button variant="outlined" color="error" onClick={() => onChange(null)} disabled={!value}>
            クリア
          </Button>
        </Grid>
      </Grid>
    </Paper>
  );
}

export default ScenarioStorySettingGrid;
