# -*- coding: utf-8 -*-
"""
ffmpeg を利用したサウンドファイルの拡張子(コーデック)変換。
変換処理は QThread 上で実行し、進捗をシグナルで通知する。
"""
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

from PySide6.QtCore import QThread, Signal

from audio_scanner import AudioFileInfo

# 変換先の選択肢: 表示名 -> (拡張子, ffmpeg追加引数)
TARGET_FORMATS = {
    "ogg":  {"label": "OGG Vorbis (.ogg)", "ext": "ogg",  "args": ["-c:a", "libvorbis", "-q:a", "5"]},
    "mp3":  {"label": "MP3 (.mp3)",        "ext": "mp3",  "args": ["-c:a", "libmp3lame", "-q:a", "2"]},
    "wav":  {"label": "WAV (.wav)",        "ext": "wav",  "args": ["-c:a", "pcm_s16le"]},
    "opus": {"label": "Opus (.opus)",      "ext": "opus", "args": ["-c:a", "libopus", "-b:a", "128k"]},
}


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def build_output_path(src: Path, target_ext: str) -> Path:
    out = src.with_suffix(f".{target_ext}")
    if out == src:
        return out
    # 同名ファイルが既にある場合は連番を付与
    counter = 1
    candidate = out
    while candidate.exists():
        candidate = src.with_name(f"{src.stem}_{counter}.{target_ext}")
        counter += 1
    return candidate


def convert_one(src: Path, target_key: str, delete_original: bool) -> Path:
    fmt = TARGET_FORMATS[target_key]
    out_path = build_output_path(src, fmt["ext"])
    cmd = ["ffmpeg", "-y", "-i", str(src), *fmt["args"], str(out_path)]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore")[-500:]
        raise RuntimeError(err or "ffmpeg変換に失敗しました。")

    if delete_original and out_path != src:
        try:
            src.unlink()
        except OSError:
            pass
    return out_path


class ConversionWorker(QThread):
    """複数ファイルの変換をバックグラウンドで順次実行"""
    progress = Signal(int, int, str)     # 現在番号, 総数, ファイル名
    file_done = Signal(str, bool, str)   # 元パス, 成功可否, エラーメッセージ
    finished_all = Signal(int, int)      # 成功数, 失敗数

    def __init__(self, files: List[AudioFileInfo], target_key: str,
                 delete_original: bool, parent=None):
        super().__init__(parent)
        self.files = files
        self.target_key = target_key
        self.delete_original = delete_original
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.files)
        success = 0
        failed = 0
        for i, info in enumerate(self.files, start=1):
            if self._stop:
                break
            self.progress.emit(i, total, info.name)
            try:
                convert_one(info.path, self.target_key, self.delete_original)
                success += 1
                self.file_done.emit(str(info.path), True, "")
            except Exception as e:  # noqa: BLE001
                failed += 1
                self.file_done.emit(str(info.path), False, str(e))
        self.finished_all.emit(success, failed)
