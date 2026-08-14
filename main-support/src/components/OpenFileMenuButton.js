import React, { useState } from 'react';
import { IconButton, Menu, MenuItem, ListSubheader, CircularProgress, Tooltip, Divider } from '@mui/material';
import CodeIcon from '@mui/icons-material/Code';

// VSCodeはカスタムURLスキーム(vscode://file/絶対パス)を公式サポートしており、
// 既にVSCodeが起動していれば新規ウィンドウではなく「タブ追加」として開かれる。
// これはブラウザ(クライアント側)から直接遷移するだけで済むため、
// サーバー側でsubprocessを起動する方式と違い、ユーザーの手元PCで開ける。
function openInVSCode(absolutePath) {
  const normalized = absolutePath.replace(/\\/g, '/');
  window.location.href = `vscode://file/${normalized}`;
}

// Visual Studioには同等の公式URLスキームが無いため、パスをクリップボードに
// コピーしてユーザー自身に「ファイルを開く」してもらうフォールバック。
async function copyForVisualStudio(absolutePath) {
  try {
    await navigator.clipboard.writeText(absolutePath);
    window.alert(
      'Visual Studioには直接開くための標準リンクが無いため、ファイルパスをコピーしました。\n' +
      'Visual Studioの「ファイルを開く」(Ctrl+O)に貼り付けてください:\n\n' + absolutePath
    );
  } catch (e) {
    window.prompt('コピーに失敗しました。以下のパスを手動でコピーしてください:', absolutePath);
  }
}

// category, name: file_locator.py側のカテゴリ名・対象アイテム名（通常の一覧Grid用）
// fetchUrl: 指定した場合、category/name の代わりにこのURLを直接叩く
//           （例: StateDetailGridのノード単位のようにfile-locator以外のAPIを使う場合）
// resolveCsFiles: fetchUrlのレスポンスが {jsonPath, csFiles} と異なる形式のとき、
//           {jsonPath, csFiles} 形式に変換するための関数
// iconColor: アイコンの色（ダークな背景に置く場合など）
function OpenFileMenuButton({ category, name, fetchUrl, resolveCsFiles, size = 'small', iconColor, tooltipLabel = 'エディタで開く' }) {
  const [anchorEl, setAnchorEl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fileInfo, setFileInfo] = useState(null); // {jsonPath, csFiles}
  const [errorMsg, setErrorMsg] = useState('');

  const handleOpenMenu = async (e) => {
    e.stopPropagation();
    setAnchorEl(e.currentTarget);
    if (fileInfo || loading) return;
    setLoading(true);
    setErrorMsg('');
    try {
      const url = fetchUrl || `/api/file-locator/${category}/${encodeURIComponent(name)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'ファイル情報の取得に失敗しました');
      setFileInfo(resolveCsFiles ? resolveCsFiles(data) : data);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = (e) => {
    if (e) e.stopPropagation();
    setAnchorEl(null);
  };

  const hasAnyFile = fileInfo && (fileInfo.jsonPath || (fileInfo.csFiles && fileInfo.csFiles.length > 0));

  return (
    <>
      <Tooltip title={tooltipLabel}>
        <IconButton size={size} onClick={handleOpenMenu} style={iconColor ? { color: iconColor } : undefined}>
          <CodeIcon fontSize={size} />
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchorEl} open={!!anchorEl} onClose={handleClose} onClick={(e) => e.stopPropagation()}>
        {loading && (
          <MenuItem disabled>
            <CircularProgress size={16} sx={{ mr: 1 }} />読み込み中...
          </MenuItem>
        )}
        {!loading && errorMsg && <MenuItem disabled>{errorMsg}</MenuItem>}
        {!loading && !errorMsg && fileInfo && !hasAnyFile && (
          <MenuItem disabled>対象ファイルが見つかりません</MenuItem>
        )}

        {!loading && !errorMsg && fileInfo && fileInfo.jsonPath && (
          <ListSubheader>JSON</ListSubheader>
        )}
        {!loading && !errorMsg && fileInfo && fileInfo.jsonPath && (
          <MenuItem onClick={() => { openInVSCode(fileInfo.jsonPath); handleClose(); }}>
            VSCodeで開く
          </MenuItem>
        )}
        {!loading && !errorMsg && fileInfo && fileInfo.jsonPath && (
          <MenuItem onClick={() => { copyForVisualStudio(fileInfo.jsonPath); handleClose(); }}>
            Visual Studio用にパスをコピー
          </MenuItem>
        )}

        {!loading && !errorMsg && fileInfo && fileInfo.jsonPath && fileInfo.csFiles?.length > 0 && <Divider />}

        {!loading && !errorMsg && fileInfo && fileInfo.csFiles?.length > 0 && (
          <ListSubheader>C#</ListSubheader>
        )}
        {!loading && !errorMsg && fileInfo && fileInfo.csFiles?.map((f) => (
          <MenuItem key={`${f.path}-vscode`} onClick={() => { openInVSCode(f.path); handleClose(); }}>
            VSCodeで開く: {f.label}
          </MenuItem>
        ))}
        {!loading && !errorMsg && fileInfo && fileInfo.csFiles?.map((f) => (
          <MenuItem key={`${f.path}-vs`} onClick={() => { copyForVisualStudio(f.path); handleClose(); }}>
            Visual Studio用にパスをコピー: {f.label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

export default OpenFileMenuButton;
