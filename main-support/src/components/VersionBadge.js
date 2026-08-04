import React, { useEffect, useState } from 'react';
import { Chip, Tooltip } from '@mui/material';

function VersionBadge() {
  const [version, setVersion] = useState(null);

  useEffect(() => {
    let mounted = true;
    fetch('/api/current-version')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (mounted) setVersion(data);
      })
      .catch(() => {});
    return () => { mounted = false; };
  }, []);

  if (!version || !version.name) return null;

  return (
    <Tooltip title={`作成: ${version.created_at || '-'} / 作成者: ${version.created_by || '-'}`}>
      <Chip
        label={`バージョン: ${version.name}`}
        color="primary"
        variant="outlined"
        size="small"
        sx={{ fontWeight: 'bold' }}
      />
    </Tooltip>
  );
}

export default VersionBadge;
