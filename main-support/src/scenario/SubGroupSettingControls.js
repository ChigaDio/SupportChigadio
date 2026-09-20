import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box, Typography, Switch, Tooltip, IconButton, Drawer, Button, Divider, Chip,
} from '@mui/material';
import { styled } from '@mui/material/styles';
import KeyboardIcon from '@mui/icons-material/Keyboard';
import TuneIcon from '@mui/icons-material/Tune';
import CloseIcon from '@mui/icons-material/Close';
import SettingsIcon from '@mui/icons-material/Settings';
import BaseRoleInputForm from './BaseRoleInputForm';
import { normalizeSubGroupSetting } from './scenarioTransactionDsl';
import {
  formDataToSetting, IS_WAIT_KEY_FIELD, SUBGROUP_SETTING_API, SUBGROUP_SETTING_ROLE_NAME,
} from './scenarioSubGroupSetting';

// ============================================================
// 「入力待ち」用のおしゃれなトグル（iOS風スイッチ）。ONの間はアクセント色に光る。
// ============================================================
const WaitKeySwitch = styled(Switch)(({ theme }) => ({
  width: 42,
  height: 24,
  padding: 0,
  '& .MuiSwitch-switchBase': {
    padding: 2,
    transitionDuration: '250ms',
    '&.Mui-checked': {
      transform: 'translateX(18px)',
      color: '#fff',
      '& + .MuiSwitch-track': {
        background: `linear-gradient(135deg, ${theme.palette.warning.light}, ${theme.palette.warning.main})`,
        opacity: 1,
        boxShadow: `0 0 8px ${theme.palette.warning.light}`,
      },
    },
    '&.Mui-disabled + .MuiSwitch-track': { opacity: 0.4 },
  },
  '& .MuiSwitch-thumb': {
    boxSizing: 'border-box',
    width: 20,
    height: 20,
    boxShadow: '0 2px 4px rgba(0,0,0,0.3)',
  },
  '& .MuiSwitch-track': {
    borderRadius: 12,
    backgroundColor: theme.palette.grey[400],
    opacity: 1,
    transition: theme.transitions.create(['background-color', 'box-shadow'], { duration: 250 }),
  },
}));

/**
 * サブグループの「入力待ち(is_wait_key)」トグル。
 * value: boolean / onChange: (next:boolean) => void
 */
export function SubGroupWaitKeyToggle({ value, onChange, disabled = false, label = '入力待ち' }) {
  const on = !!value;
  return (
    <Tooltip title={on
      ? '入力待ちON：このサブグループの実行中/後にキー入力を待ちます（is_wait_key=true）'
      : '入力待ちOFF（is_wait_key=false）。ONにするとキー入力を待ちます'}
    >
      <Box
        sx={{
          display: 'inline-flex', alignItems: 'center', gap: 0.75,
          pl: 1, pr: 0.5, py: 0.25, borderRadius: 5,
          border: '1px solid', borderColor: on ? 'warning.main' : 'divider',
          bgcolor: on ? 'warning.50' : 'transparent',
          transition: 'all 0.25s',
          opacity: disabled ? 0.5 : 1,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <KeyboardIcon sx={{ fontSize: 16, color: on ? 'warning.main' : 'text.disabled', transition: 'color 0.25s' }} />
        <Typography variant="caption" sx={{ fontWeight: on ? 700 : 500, color: on ? 'warning.dark' : 'text.secondary' }}>
          {label}
        </Typography>
        <WaitKeySwitch
          size="small"
          checked={on}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
      </Box>
    </Tooltip>
  );
}

/**
 * ヘッダー用の小さな「設定」アイコンボタン（クリックで全フィールドの入力Drawerを開く）。
 * 追加フィールドを持つ場合は、その存在が分かるようにアイコンを切り替える。
 */
export function SubGroupSettingIconButton({ onClick, hasExtraFields = false, waitKey = false }) {
  return (
    <Tooltip title="サブグループ設定（入力待ち・追加フィールドを編集）">
      <IconButton
        size="small"
        onClick={(e) => { e.stopPropagation(); onClick(e); }}
        sx={{ p: 0.25, color: waitKey ? '#ffd54f' : 'rgba(255,255,255,0.8)' }}
      >
        {hasExtraFields ? <SettingsIcon sx={{ fontSize: 14 }} /> : <TuneIcon sx={{ fontSize: 14 }} />}
      </IconButton>
    </Tooltip>
  );
}

/** 折り畳み時にも分かるよう、ヘッダーに出す「WAIT」小チップ。 */
export function SubGroupWaitKeyChip({ waitKey }) {
  if (!waitKey) return null;
  return (
    <Chip
      icon={<KeyboardIcon sx={{ fontSize: '12px !important', color: '#fff !important' }} />}
      label="WAIT"
      size="small"
      sx={{
        height: 18, fontSize: '0.6rem', fontWeight: 'bold', flexShrink: 0,
        bgcolor: 'warning.main', color: 'white',
      }}
    />
  );
}

// ============================================================
// サブグループ設定の入力Drawer
// 共通のフィールド定義(is_wait_key + 追加した classdataid / classdata / enum / ベジェ / カラー /
// 配列 / リスト / dictionary / ネスト等)を、Roleのデータ入力と同じフォームで編集する。
// 変更は「閉じたとき」にまとめて反映する（入力中にフォームへ値が戻ってしまうのを避けるため、
// 入力中の値は内部でだけ保持する）。各項目右のブックマークで、その値をデフォルトとして保存できる。
// ============================================================
export function SubGroupSettingDrawer({
  open, onClose, title, schema, setting, defaults, onApply, eventId, subId,
}) {
  const [initialData, setInitialData] = useState([]);
  const draftRef = useRef([]);
  const initialJsonRef = useRef('[]');

  useEffect(() => {
    if (!open) return;
    const init = normalizeSubGroupSetting(setting, schema, defaults);
    initialJsonRef.current = JSON.stringify(init);
    draftRef.current = init;
    setInitialData(init);
    // 開いた時点の値だけを初期値にする(以後の親の再描画では初期化し直さない)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleFormChange = useCallback((formData) => {
    draftRef.current = formDataToSetting(formData, schema);
  }, [schema]);

  const handleClose = () => {
    const next = draftRef.current;
    // 変更が無ければ何も書き換えない(不要な自動保存を起こさない)
    if (JSON.stringify(next) !== initialJsonRef.current) onApply(next);
    onClose();
  };

  return (
    <Drawer anchor="right" open={open} onClose={handleClose} PaperProps={{ sx: { width: { xs: '100%', sm: 480 } } }}>
      <Box sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
        <TuneIcon color="primary" />
        <Typography variant="h6" sx={{ flex: 1 }} noWrap>{title || 'サブグループ設定'}</Typography>
        <IconButton onClick={handleClose}><CloseIcon /></IconButton>
      </Box>
      <Divider />
      <Box sx={{ p: 2, overflowY: 'auto', flex: 1 }}>
        {!schema ? (
          <Typography color="text.secondary">設定のフィールド定義を読み込めませんでした。</Typography>
        ) : (
          <>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              全イベント共通のサブグループ設定です（フィールドの追加は「サブグループ設定」ページから）。
              {IS_WAIT_KEY_FIELD} は入力待ちフラグです。ブックマークで、その値を新規サブグループのデフォルトにできます。
            </Typography>
            {open && (
              <BaseRoleInputForm
                schema={schema}
                initialData={initialData}
                onChange={handleFormChange}
                eventId={eventId}
                subId={subId}
                roleName={SUBGROUP_SETTING_ROLE_NAME}
                fieldDefaultUrl={`${SUBGROUP_SETTING_API}/field-default`}
              />
            )}
          </>
        )}
      </Box>
      <Divider />
      <Box sx={{ p: 1.5, display: 'flex', justifyContent: 'flex-end' }}>
        <Button variant="contained" onClick={handleClose}>閉じる（変更を反映）</Button>
      </Box>
    </Drawer>
  );
}
