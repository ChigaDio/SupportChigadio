import React from 'react';
import { Box, Typography } from '@mui/material';
import BaseRoleInputForm from './BaseRoleInputForm';

const RoleInputFactory = {
  async getForm(roleName, initialData, onChange, schemaOverride) {  // onSave を onChange に変更
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

      return () => <BaseRoleInputForm schema={schema} initialData={initialData} onChange={onChange} />;  // onSave を onChange に変更
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