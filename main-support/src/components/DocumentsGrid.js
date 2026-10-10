import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, Typography, Paper, Button, IconButton, TextField, Chip, Stack, Breadcrumbs, Link,
  Table, TableHead, TableRow, TableCell, TableBody, Autocomplete,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert, CircularProgress,
  Tabs, Tab, Tooltip,
} from '@mui/material';
import FolderIcon from '@mui/icons-material/Folder';
import InsertDriveFileIcon from '@mui/icons-material/InsertDriveFile';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import DescriptionIcon from '@mui/icons-material/Description';
import TableChartIcon from '@mui/icons-material/TableChart';
import ImageIcon from '@mui/icons-material/Image';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder';
import DownloadIcon from '@mui/icons-material/Download';
import DeleteIcon from '@mui/icons-material/Delete';
import LabelIcon from '@mui/icons-material/Label';
import LockIcon from '@mui/icons-material/Lock';
import RefreshIcon from '@mui/icons-material/Refresh';
import VisibilityIcon from '@mui/icons-material/Visibility';
import HomeIcon from '@mui/icons-material/Home';
import { useAuth } from '../context/AuthContext';

const PDF_EXTS = ['pdf'];
const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'];
const TEXT_EXTS = ['txt', 'md', 'csv', 'json', 'log', 'yml', 'yaml', 'ini', 'conf', 'cs', 'py', 'js', 'ts', 'html', 'xml'];
const WORD_EXTS = ['docx'];
const EXCEL_EXTS = ['xlsx', 'xls'];

const encodePath = (p) => (p || '').split('/').filter(Boolean).map(encodeURIComponent).join('/');

function fileIcon(ext) {
  if (PDF_EXTS.includes(ext)) return <PictureAsPdfIcon fontSize="small" color="error" />;
  if (WORD_EXTS.includes(ext)) return <DescriptionIcon fontSize="small" color="info" />;
  if (EXCEL_EXTS.includes(ext)) return <TableChartIcon fontSize="small" color="success" />;
  if (IMAGE_EXTS.includes(ext)) return <ImageIcon fontSize="small" color="secondary" />;
  return <InsertDriveFileIcon fontSize="small" color="disabled" />;
}

function formatSize(bytes) {
  if (bytes === null || bytes === undefined) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function DocumentsGrid() {
  const { isAdmin } = useAuth();

  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const [query, setQuery] = useState('');
  const [tagFilter, setTagFilter] = useState(null);
  const [allTags, setAllTags] = useState([]);
  const searching = !!(query.trim() || tagFilter);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState([]);
  const [uploadTags, setUploadTags] = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  const [uploading, setUploading] = useState(false);

  const [mkdirOpen, setMkdirOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');

  const [tagEditTarget, setTagEditTarget] = useState(null);
  const [editTags, setEditTags] = useState('');
  const [editDescription, setEditDescription] = useState('');

  const [aclOpen, setAclOpen] = useState(false);
  const [aclViewUsers, setAclViewUsers] = useState('');
  const [aclEditUsers, setAclEditUsers] = useState('');
  const [aclRestrictView, setAclRestrictView] = useState(false);
  const [aclRestrictEdit, setAclRestrictEdit] = useState(false);

  const [previewEntry, setPreviewEntry] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewContent, setPreviewContent] = useState(null);
  const [previewError, setPreviewError] = useState('');
  const [sheetTab, setSheetTab] = useState(0);

  const fetchTags = useCallback(() => {
    fetch('/api/documents/tags').then((r) => r.json()).then(setAllTags).catch(() => {});
  }, []);

  const fetchEntries = useCallback(() => {
    setLoading(true);
    setErrorMsg('');
    const url = searching
      ? `/api/documents/search?${new URLSearchParams({ q: query, tag: tagFilter || '' })}`
      : `/api/documents/list?path=${encodeURIComponent(currentPath)}`;
    fetch(url)
      .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.error);
        setEntries(data.entries || []);
      })
      .catch((e) => { setErrorMsg(e.message); setEntries([]); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPath, searching, query, tagFilter]);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);
  useEffect(() => { fetchTags(); }, [fetchTags]);

  const breadcrumbParts = useMemo(() => currentPath.split('/').filter(Boolean), [currentPath]);

  const openFolder = (path) => {
    setQuery(''); setTagFilter(null);
    setCurrentPath(path);
  };

  // --- アップロード ---
  const handleUpload = async () => {
    if (uploadFiles.length === 0) { alert('ファイルを選択してください'); return; }
    setUploading(true);
    try {
      const form = new FormData();
      form.append('path', currentPath);
      form.append('tags', uploadTags);
      form.append('description', uploadDescription);
      uploadFiles.forEach((f) => form.append('files', f));
      const res = await fetch('/api/documents/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      alert(data.message);
      setUploadOpen(false);
      setUploadFiles([]); setUploadTags(''); setUploadDescription('');
      fetchEntries(); fetchTags();
    } catch (e) {
      alert('アップロードエラー: ' + e.message);
    } finally {
      setUploading(false);
    }
  };

  // --- フォルダ作成 ---
  const handleMkdir = async () => {
    if (!newFolderName.trim()) return;
    try {
      const path = currentPath ? `${currentPath}/${newFolderName}` : newFolderName;
      const res = await fetch('/api/documents/mkdir', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setMkdirOpen(false); setNewFolderName('');
      fetchEntries();
    } catch (e) {
      alert('フォルダ作成エラー: ' + e.message);
    }
  };

  // --- タグ・説明の編集 ---
  const openTagEdit = (entry) => {
    setTagEditTarget(entry);
    setEditTags((entry.tags || []).join(', '));
    setEditDescription(entry.description || '');
  };

  const handleSaveTags = async () => {
    try {
      const tags = editTags.split(',').map((t) => t.trim()).filter(Boolean);
      const res = await fetch(`/api/documents/meta?path=${encodeURIComponent(tagEditTarget.path)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags, description: editDescription }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setTagEditTarget(null);
      fetchEntries(); fetchTags();
    } catch (e) {
      alert('タグ更新エラー: ' + e.message);
    }
  };

  // --- 削除 ---
  const handleDelete = async (entry) => {
    if (!window.confirm(`「${entry.name}」をゴミ箱へ移動します。よろしいですか？`)) return;
    try {
      const res = await fetch(`/api/documents/item?path=${encodeURIComponent(entry.path)}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      fetchEntries();
    } catch (e) {
      alert('削除エラー: ' + e.message);
    }
  };

  // --- ダウンロード ---
  const downloadFile = (entry) => {
    window.open(`/api/documents/raw/${encodePath(entry.path)}?download=1`, '_blank');
  };
  const downloadZip = (path) => {
    window.open(`/api/documents/download-zip?path=${encodeURIComponent(path)}`, '_blank');
  };

  // --- フォルダ権限（管理人のみ） ---
  const handleSaveAcl = async () => {
    try {
      const viewUsers = aclRestrictView ? aclViewUsers.split(',').map((u) => u.trim()).filter(Boolean) : null;
      const editUsers = aclRestrictEdit ? aclEditUsers.split(',').map((u) => u.trim()).filter(Boolean) : null;
      const res = await fetch(`/api/documents/acl?path=${encodeURIComponent(currentPath)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ viewUsers, editUsers }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      alert(data.message);
      setAclOpen(false);
      fetchEntries();
    } catch (e) {
      alert('権限更新エラー: ' + e.message);
    }
  };

  // --- プレビュー ---
  const openPreview = async (entry) => {
    setPreviewEntry(entry);
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewContent(null);
    setPreviewError('');
    setSheetTab(0);
    const ext = entry.ext;
    const url = `/api/documents/raw/${encodePath(entry.path)}`;
    try {
      if (PDF_EXTS.includes(ext)) {
        setPreviewContent({ type: 'pdf', url });
      } else if (IMAGE_EXTS.includes(ext)) {
        setPreviewContent({ type: 'image', url });
      } else if (TEXT_EXTS.includes(ext)) {
        const text = await (await fetch(url)).text();
        setPreviewContent({ type: 'text', text });
      } else if (WORD_EXTS.includes(ext)) {
        const buf = await (await fetch(url)).arrayBuffer();
        const mammoth = await import('mammoth');
        const result = await mammoth.convertToHtml({ arrayBuffer: buf });
        setPreviewContent({ type: 'html', html: result.value });
      } else if (EXCEL_EXTS.includes(ext)) {
        const buf = await (await fetch(url)).arrayBuffer();
        const XLSX = await import('xlsx');
        const wb = XLSX.read(buf, { type: 'array' });
        const sheets = wb.SheetNames.map((name) => ({
          name,
          rows: XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, blankrows: false }),
        }));
        setPreviewContent({ type: 'sheet', sheets });
      } else {
        setPreviewContent({ type: 'unsupported' });
      }
    } catch (e) {
      setPreviewError(
        (WORD_EXTS.includes(ext) || EXCEL_EXTS.includes(ext))
          ? `プレビューに失敗しました（"npm install mammoth xlsx" が必要です）: ${e.message}`
          : `プレビューに失敗しました: ${e.message}`
      );
    } finally {
      setPreviewLoading(false);
    }
  };

  const columns = 6;

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Typography variant="h4">仕様書ライブラリ</Typography>
        <Button size="small" startIcon={<RefreshIcon />} onClick={fetchEntries}>更新</Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        PDF / Word / Excel / テキストなどをフォルダ分けしてアップロード・閲覧・ダウンロードできます。
      </Typography>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center">
          <TextField
            size="small" label="ファイル名・タグで検索" value={query}
            onChange={(e) => setQuery(e.target.value)} sx={{ minWidth: 260 }}
          />
          <Autocomplete
            size="small" options={allTags} value={tagFilter} onChange={(e, v) => setTagFilter(v)}
            sx={{ minWidth: 200 }}
            renderInput={(params) => <TextField {...params} label="タグで絞り込み" />}
          />
          <Box sx={{ flexGrow: 1 }} />
          <Button variant="outlined" startIcon={<CreateNewFolderIcon />} onClick={() => setMkdirOpen(true)} disabled={searching}>
            新しいフォルダ
          </Button>
          <Button variant="contained" startIcon={<UploadFileIcon />} onClick={() => setUploadOpen(true)} disabled={searching}>
            アップロード
          </Button>
          <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => downloadZip(currentPath)} disabled={searching}>
            このフォルダをZIP
          </Button>
          {isAdmin && (
            <Button variant="outlined" color="warning" startIcon={<LockIcon />} onClick={() => {
              setAclViewUsers(''); setAclEditUsers(''); setAclRestrictView(false); setAclRestrictEdit(false);
              setAclOpen(true);
            }} disabled={searching}>
              フォルダの権限
            </Button>
          )}
        </Stack>

        {!searching && (
          <Breadcrumbs sx={{ mt: 2 }}>
            <Link component="button" underline="hover" onClick={() => openFolder('')} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <HomeIcon fontSize="small" /> ルート
            </Link>
            {breadcrumbParts.map((part, idx) => {
              const path = breadcrumbParts.slice(0, idx + 1).join('/');
              return (
                <Link key={path} component="button" underline="hover" onClick={() => openFolder(path)}>
                  {part}
                </Link>
              );
            })}
          </Breadcrumbs>
        )}
        {searching && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
            「{query}」{tagFilter ? ` / タグ: ${tagFilter}` : ''} の検索結果（全フォルダを横断）
          </Typography>
        )}
      </Paper>

      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      <Paper sx={{ p: 2 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress /></Box>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>名前</TableCell>
                <TableCell>タグ</TableCell>
                <TableCell>サイズ</TableCell>
                <TableCell>更新日時</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {entries.map((e) => (
                <TableRow key={e.path} hover>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {e.type === 'folder' ? <FolderIcon fontSize="small" color="primary" /> : fileIcon(e.ext)}
                      {e.type === 'folder' ? (
                        <Link component="button" underline="hover" onClick={() => openFolder(e.path)}>{e.name}</Link>
                      ) : (
                        <Link component="button" underline="hover" onClick={() => openPreview(e)}>{e.name}</Link>
                      )}
                      {searching && <Typography variant="caption" color="text.secondary">({e.path})</Typography>}
                    </Box>
                    {e.description && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', ml: 3.5 }}>
                        {e.description}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap">
                      {(e.tags || []).map((t) => (
                        <Chip key={t} size="small" label={t} onClick={() => setTagFilter(t)} />
                      ))}
                    </Stack>
                  </TableCell>
                  <TableCell>{formatSize(e.sizeBytes)}</TableCell>
                  <TableCell>{e.modifiedAt}</TableCell>
                  <TableCell align="right">
                    {e.type === 'file' && (
                      <>
                        <Tooltip title="プレビュー">
                          <IconButton size="small" onClick={() => openPreview(e)}><VisibilityIcon fontSize="small" /></IconButton>
                        </Tooltip>
                        <Tooltip title="ダウンロード">
                          <IconButton size="small" onClick={() => downloadFile(e)}><DownloadIcon fontSize="small" /></IconButton>
                        </Tooltip>
                        <Tooltip title="タグ・説明を編集">
                          <span>
                            <IconButton size="small" onClick={() => openTagEdit(e)} disabled={!e.editable}>
                              <LabelIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </>
                    )}
                    {e.type === 'folder' && (
                      <Tooltip title="フォルダをZIPでダウンロード">
                        <IconButton size="small" onClick={() => downloadZip(e.path)}><DownloadIcon fontSize="small" /></IconButton>
                      </Tooltip>
                    )}
                    <Tooltip title="削除（ゴミ箱へ）">
                      <span>
                        <IconButton size="small" color="error" onClick={() => handleDelete(e)} disabled={!e.editable}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
              {entries.length === 0 && (
                <TableRow><TableCell colSpan={columns}>
                  <Typography color="text.secondary" sx={{ p: 2 }}>
                    {searching ? '該当するファイルが見つかりません。' : 'このフォルダは空です。'}
                  </Typography>
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </Paper>

      {/* --- アップロード --- */}
      <Dialog open={uploadOpen} onClose={() => setUploadOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>ファイルをアップロード{currentPath ? `（${currentPath}）` : ''}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          <Button variant="outlined" component="label" startIcon={<UploadFileIcon />}>
            ファイルを選択（複数可）
            <input type="file" multiple hidden onChange={(e) => setUploadFiles(Array.from(e.target.files || []))} />
          </Button>
          {uploadFiles.length > 0 && (
            <Typography variant="body2" color="text.secondary">
              {uploadFiles.map((f) => f.name).join(', ')}
            </Typography>
          )}
          <TextField label="タグ（カンマ区切り、後からでも編集可）" size="small" value={uploadTags}
            onChange={(e) => setUploadTags(e.target.value)} />
          <TextField label="説明（任意）" size="small" multiline minRows={2} value={uploadDescription}
            onChange={(e) => setUploadDescription(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadOpen(false)}>キャンセル</Button>
          <Button
            variant="contained" onClick={handleUpload} disabled={uploading}
            startIcon={uploading ? <CircularProgress size={16} color="inherit" /> : undefined}
          >
            アップロード
          </Button>
        </DialogActions>
      </Dialog>

      {/* --- フォルダ作成 --- */}
      <Dialog open={mkdirOpen} onClose={() => setMkdirOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>新しいフォルダを作成</DialogTitle>
        <DialogContent>
          <TextField autoFocus fullWidth size="small" label="フォルダ名" sx={{ mt: 1 }}
            value={newFolderName} onChange={(e) => setNewFolderName(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMkdirOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={handleMkdir}>作成</Button>
        </DialogActions>
      </Dialog>

      {/* --- タグ編集 --- */}
      <Dialog open={!!tagEditTarget} onClose={() => setTagEditTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>タグ・説明を編集</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          <TextField label="タグ（カンマ区切り）" size="small" value={editTags} onChange={(e) => setEditTags(e.target.value)} />
          <TextField label="説明" size="small" multiline minRows={2} value={editDescription} onChange={(e) => setEditDescription(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTagEditTarget(null)}>キャンセル</Button>
          <Button variant="contained" onClick={handleSaveTags}>保存</Button>
        </DialogActions>
      </Dialog>

      {/* --- フォルダ権限（管理人のみ） --- */}
      <Dialog open={aclOpen} onClose={() => setAclOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>フォルダの閲覧・編集権限{currentPath ? `（${currentPath}）` : '（ルート）'}</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            サブフォルダは、より近い階層で権限設定されていない限りここを継承します。
            両方チェックを外して保存すると、このフォルダの制限を解除します。
          </Typography>
          <Button
            size="small" variant={aclRestrictView ? 'contained' : 'outlined'}
            onClick={() => setAclRestrictView((v) => !v)}
          >
            閲覧を特定ユーザーに制限{aclRestrictView ? '：ON' : '：OFF（全員閲覧可）'}
          </Button>
          {aclRestrictView && (
            <TextField label="閲覧を許可するユーザー名（カンマ区切り）" size="small" value={aclViewUsers}
              onChange={(e) => setAclViewUsers(e.target.value)} />
          )}
          <Button
            size="small" variant={aclRestrictEdit ? 'contained' : 'outlined'}
            onClick={() => setAclRestrictEdit((v) => !v)}
          >
            編集を特定ユーザーに制限{aclRestrictEdit ? '：ON' : '：OFF（editor/admin既定）'}
          </Button>
          {aclRestrictEdit && (
            <TextField label="編集を許可するユーザー名（カンマ区切り）" size="small" value={aclEditUsers}
              onChange={(e) => setAclEditUsers(e.target.value)} />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAclOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={handleSaveAcl}>保存</Button>
        </DialogActions>
      </Dialog>

      {/* --- プレビュー --- */}
      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {previewEntry && fileIcon(previewEntry.ext)}
          {previewEntry?.name}
        </DialogTitle>
        <DialogContent dividers sx={{ minHeight: 400 }}>
          {previewLoading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}><CircularProgress /></Box>
          )}
          {!previewLoading && previewError && <Alert severity="warning">{previewError}</Alert>}
          {!previewLoading && !previewError && previewContent?.type === 'pdf' && (
            <iframe title="pdf-preview" src={previewContent.url} style={{ width: '100%', height: '70vh', border: 'none' }} />
          )}
          {!previewLoading && !previewError && previewContent?.type === 'image' && (
            <Box sx={{ textAlign: 'center' }}>
              <img src={previewContent.url} alt={previewEntry?.name} style={{ maxWidth: '100%', maxHeight: '70vh' }} />
            </Box>
          )}
          {!previewLoading && !previewError && previewContent?.type === 'text' && (
            <Box component="pre" sx={{
              fontFamily: '"Roboto Mono", monospace', fontSize: 13, whiteSpace: 'pre-wrap',
              bgcolor: 'background.default', p: 2, borderRadius: 1, maxHeight: '70vh', overflowY: 'auto',
            }}>
              {previewContent.text}
            </Box>
          )}
          {!previewLoading && !previewError && previewContent?.type === 'html' && (
            <Box sx={{ maxHeight: '70vh', overflowY: 'auto', p: 1 }}
              dangerouslySetInnerHTML={{ __html: previewContent.html }} />
          )}
          {!previewLoading && !previewError && previewContent?.type === 'sheet' && (
            <Box>
              {previewContent.sheets.length > 1 && (
                <Tabs value={sheetTab} onChange={(e, v) => setSheetTab(v)} sx={{ mb: 1 }}>
                  {previewContent.sheets.map((s) => <Tab key={s.name} label={s.name} />)}
                </Tabs>
              )}
              <Box sx={{ maxHeight: '65vh', overflow: 'auto' }}>
                <Table size="small">
                  <TableBody>
                    {(previewContent.sheets[sheetTab]?.rows || []).map((row, ri) => (
                      <TableRow key={ri}>
                        {row.map((cell, ci) => <TableCell key={ci}>{cell}</TableCell>)}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Box>
          )}
          {!previewLoading && !previewError && previewContent?.type === 'unsupported' && (
            <Alert severity="info">このファイル形式はプレビューに対応していません。ダウンロードしてご確認ください。</Alert>
          )}
        </DialogContent>
        <DialogActions>
          {previewEntry && <Button startIcon={<DownloadIcon />} onClick={() => downloadFile(previewEntry)}>ダウンロード</Button>}
          <Button onClick={() => setPreviewOpen(false)}>閉じる</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default DocumentsGrid;
