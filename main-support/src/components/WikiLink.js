import React, { useState } from 'react';
import { Button, CircularProgress } from '@mui/material';
import MenuBookIcon from '@mui/icons-material/MenuBook';

// 旧・自前実装のWikiページ（GitSvnGrid.jsのような一覧+編集画面）は廃止し、
// 別プロセスで動く django-wiki を開くだけのシンプルなランチャーに置き換えた。
// クリックのたびに /api/wiki-bridge/launch から新しいSSOトークン付きURLを
// 取得して新しいタブで開く（トークンは60秒で失効するため、都度取得する）。
function WikiLink() {
  const [loading, setLoading] = useState(false);

  const openWiki = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/wiki-bridge/launch');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      window.open(data.url, '_blank', 'noopener');
    } catch (e) {
      alert('Wikiを開けませんでした: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      variant="contained"
      startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <MenuBookIcon />}
      onClick={openWiki}
      disabled={loading}
    >
      Wikiを開く
    </Button>
  );
}

export default WikiLink;
