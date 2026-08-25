# -*- coding: utf-8 -*-
"""
指定フォルダ配下を再帰的に検索し、サウンドファイル一覧を収集する。
UIを固まらせないよう QThread 上で実行する。
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List

from PySide6.QtCore import QThread, Signal

SUPPORTED_EXTS = {
    ".mp3", ".wav", ".ogg", ".oga", ".opus",
    ".flac", ".m4a", ".aac", ".wma", ".aiff", ".aif",
}


@dataclass
class AudioFileInfo:
    path: Path
    rel_dir: str   # ルートからの相対サブフォルダ ("" はルート直下)
    name: str
    size: int
    ext: str        # 拡張子(ドット無し・小文字)

    @property
    def size_str(self) -> str:
        size = self.size
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024.0:
                return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"


class ScanWorker(QThread):
    """再帰検索を別スレッドで実行し、完了時に一覧を返す"""
    progress = Signal(int)          # 現在までに見つかった件数
    finished_scan = Signal(list)    # List[AudioFileInfo]
    failed = Signal(str)

    def __init__(self, root_dir: str, parent=None):
        super().__init__(parent)
        self.root_dir = root_dir
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            root = Path(self.root_dir)
            if not root.is_dir():
                self.failed.emit("指定されたフォルダが存在しません。")
                return

            results: List[AudioFileInfo] = []
            count = 0
            for p in root.rglob("*"):
                if self._stop:
                    return
                if not p.is_file():
                    continue
                if p.suffix.lower() not in SUPPORTED_EXTS:
                    continue
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                try:
                    rel_parent = p.parent.relative_to(root)
                    rel_dir = "" if str(rel_parent) == "." else str(rel_parent).replace("\\", "/")
                except ValueError:
                    rel_dir = ""

                results.append(
                    AudioFileInfo(
                        path=p,
                        rel_dir=rel_dir,
                        name=p.name,
                        size=size,
                        ext=p.suffix.lower().lstrip("."),
                    )
                )
                count += 1
                if count % 25 == 0:
                    self.progress.emit(count)

            self.progress.emit(count)
            self.finished_scan.emit(results)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
