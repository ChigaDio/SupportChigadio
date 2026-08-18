import React, { useState } from 'react';
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions, Typography,
  RadioGroup, FormControlLabel, Radio, Alert, CircularProgress, Box,
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import DownloadIcon from '@mui/icons-material/Download';

// Enum/ClassDataID等をExcel(.xlsx)/CSVで下ごしらえ・一括投入するための
// 共通ダイアログ。pythonSrc/spreadsheet_io.py の /api/spreadsheet/* を利用する。
// category は "enum" または "class_data_id"。
function SpreadsheetImportExportDialog({ open, onClose, category, name, onImported }) {
  const [format, setFormat] = useState('xlsx');
  const [mode, setMode] = useState('replace');
  const [importing, setImporting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleExport = () => {
    window.location.href = `/api/spreadsheet/${category}/${encodeURIComponent(name)}/export?format=${format}`;
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (mode === 'replace' && !window.confirm(
      `現在の「${name}」のデータは、アップロードしたファイルの内容で全て置き換えられます。よろしいですか？`
    )) {
      e.target.value = '';
      return;
    }
    setImporting(true);
    setErrorMsg('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`/api/spreadsheet/${category}/${encodeURIComponent(name)}/import?mode=${mode}`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      alert(data.message);
      if (onImported) onImported();
      onClose();
    } catch (err) {
      setErrorMsg('取り込みエラー: ' + err.message);
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Excel/CSV連携: {name}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Excel(.xlsx)またはCSVで下ごしらえして、まとめて取り込めます。
        </Typography>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>エクスポート</Typography>
        <RadioGroup row value={format} onChange={(e) => setFormat(e.target.value)} sx={{ mb: 1 }}>
          <FormControlLabel value="xlsx" control={<Radio size="small" />} label="Excel(.xlsx)" />
          <FormControlLabel value="csv" control={<Radio size="small" />} label="CSV" />
        </RadioGroup>
        <Button variant="outlined" startIcon={<DownloadIcon />} onClick={handleExport} fullWidth sx={{ mb: 3 }}>
          ダウンロード
        </Button>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>インポート</Typography>
        <RadioGroup row value={mode} onChange={(e) => setMode(e.target.value)} sx={{ mb: 1 }}>
          <FormControlLabel value="replace" control={<Radio size="small" />} label="全て置き換え" />
          <FormControlLabel value="append" control={<Radio size="small" />} label="追加のみ" />
        </RadioGroup>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          {category === 'enum'
            ? '列: property, value, description'
            : '列: id, enum_property, （各フィールド名）。ベクトル型は "x,y" 形式、配列は "a|b|c" 形式で入力できます。'}
        </Typography>

        {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

        <Button
          variant="contained"
          component="label"
          startIcon={importing ? <CircularProgress size={16} color="inherit" /> : <UploadFileIcon />}
          fullWidth
          disabled={importing}
        >
          {importing ? '取り込み中...' : 'ファイルを選択して取り込み'}
          <input type="file" hidden accept=".xlsx,.csv" onChange={handleFileChange} />
        </Button>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>閉じる</Button>
      </DialogActions>
    </Dialog>
  );
}

export default SpreadsheetImportExportDialog;
