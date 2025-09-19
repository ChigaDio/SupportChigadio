import React from 'react';
import { Box, Typography } from '@mui/material';
import BaseRoleInputForm from './BaseRoleInputForm';

const RoleInputFactory = {
  async getForm(roleName, initialData, onChange) {  // onSave を onChange に変更
    try {
      const response = await fetch(`/api/role-form-schema/${roleName}`);
      if (!response.ok) {
        throw new Error(`Schema fetch failed: ${response.status}`);
      }
      const schema = await response.json();

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