import React from 'react';
import { Box, Typography } from '@mui/material';
import BaseRoleInputForm from './BaseRoleInputForm';

const RoleInputFactory = {
  async getForm(roleName, initialData, onChange, schemaOverride, context) {  // onSave を onChange に変更
    // context: { eventId, subId } を渡すと、voice_ref型フィールド
    // （VoiceLine専用Role）がそのサブイベントの物語設定から
    // Voice候補を絞り込めるようになる（無くても他の型は通常通り動作する）。
    try {
      // 呼び出し元(RoleDataDrawerなど)がすでに(必要なら強制リフレッシュ済みの)
      // スキーマを渡してきた場合はそれをそのまま使う。渡されなかった場合のみ
      // ここで自前フェッチする(後方互換)。
      let schema = schemaOverride;
      if (!schema) {
        const response = await fetch(`/api/role-form-schema/${roleName}`);
        if (!response.ok) {
          throw new Error(`Schema fetch failed: ${response.status}`);
        }
        schema = await response.json();
      }

      if (schema.error) {
        throw new Error(schema.error);
      }

      if (roleName === 'SpecialRole' || schema.branchType === 'Branch') {
        // import SpecialRoleInputForm from './SpecialRoleInputForm'; // 必要なら
      }

      return () => (
        <BaseRoleInputForm
          schema={schema}
          initialData={initialData}
          onChange={onChange}
          eventId={context?.eventId}
          subId={context?.subId}
          roleName={roleName}
        />
      );  // onSave を onChange に変更
    } catch (error) {
      console.error(error);
      return () => (
        <Box sx={{ p: 2, color: 'red' }}>
          <Typography>Error loading form for {roleName}: {error.message}</Typography>
          <Typography>Check if Role data is saved correctly.</Typography>
        </Box>
      );
    }
  }
};

export default RoleInputFactory;