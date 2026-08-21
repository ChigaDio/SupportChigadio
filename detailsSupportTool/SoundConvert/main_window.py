# -*- coding: utf-8 -*-
"""
サウンド拡張子変換GUIツール - メインウィンドウ
"""
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QToolButton, QFileDialog, QTreeWidget, QTreeWidgetItem,
    QSlider, QComboBox, QCheckBox, QProgressBar, QMessageBox, QMenu,
    QStatusBar, QSizePolicy, QFrame
)

import config_manager as cfg
from audio_scanner import AudioFileInfo, ScanWorker
from converter import ConversionWorker, TARGET_FORMATS, ffmpeg_available

COL_CHECK, COL_NAME, COL_SIZE, COL_EXT, COL_CTRL = range(5)


def ms_to_str(ms: int) -> str:
    if ms < 0:
        ms = 0
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


class RowControls(QWidget):
    """1レコード分の再生コントロール(再生ボタン/シークバー/音量/個別変換)"""

    def __init__(self, info: AudioFileInfo, main_window: "MainWindow"):
        super().__init__()
        self.info = info
        self.main_window = main_window

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        self.play_btn = QToolButton()
        self.play_btn.setText("▶")
        self.play_btn.setFixedSize(28, 28)
        self.play_btn.clicked.connect(self._on_play_clicked)
        layout.addWidget(self.play_btn)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setFixedWidth(80)
        self.time_label.setStyleSheet("color:#9aa0b4;")
        layout.addWidget(self.time_label)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        layout.addWidget(self.seek_slider, stretch=3)

        vol_label = QLabel("🔊")
        vol_label.setFixedWidth(18)
        layout.addWidget(vol_label)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(70)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self.vol_slider, stretch=1)

        self.convert_btn = QPushButton("変換")
        self.convert_btn.setFixedWidth(60)
        self.convert_btn.clicked.connect(self._on_convert_clicked)
        layout.addWidget(self.convert_btn)

        self._seeking = False

    def _on_play_clicked(self):
        self.main_window.toggle_play(self)

    def _on_seek_pressed(self):
        self._seeking = True

    def _on_seek_released(self):
        self._seeking = False
        self.main_window.seek_active(self.seek_slider.value())

    def _on_volume_changed(self, value: int):
        self.main_window.set_volume_if_active(self, value / 100.0)

    def _on_convert_clicked(self):
        self.main_window.convert_files([self.info])

    def set_playing_icon(self, playing: bool):
        self.play_btn.setText("⏸" if playing else "▶")

    def update_position(self, position_ms: int, duration_ms: int):
        if not self._seeking and duration_ms > 0:
            self.seek_slider.setValue(int(position_ms / duration_ms * 1000))
        self.time_label.setText(f"{ms_to_str(position_ms)} / {ms_to_str(duration_ms)}")


class OverlayWidget(QWidget):
    """変換中に画面全体を覆い、他の操作を受け付けないようにするオーバーレイ"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OverlayWidget")
        self.hide()

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("OverlayCard")
        card.setFixedWidth(420)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(12)

        self.title_label = QLabel("変換中...")
        self.title_label.setStyleSheet("font-size:16px; font-weight:600;")
        card_layout.addWidget(self.title_label)

        self.file_label = QLabel("")
        self.file_label.setStyleSheet("color:#9aa0b4;")
        self.file_label.setWordWrap(True)
        card_layout.addWidget(self.file_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        card_layout.addWidget(self.progress_bar)

        self.count_label = QLabel("0 / 0")
        self.count_label.setAlignment(Qt.AlignRight)
        self.count_label.setStyleSheet("color:#9aa0b4;")
        card_layout.addWidget(self.count_label)

        outer.addWidget(card)

    def start(self, total: int):
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(0)
        self.count_label.setText(f"0 / {total}")
        self.file_label.setText("")
        self.show()
        self.raise_()

    def update_progress(self, current: int, total: int, filename: str):
        self.progress_bar.setValue(current)
        self.count_label.setText(f"{current} / {total}")
        self.file_label.setText(f"変換中: {filename}")

    def finish(self):
        self.hide()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sound Ext Converter")
        self.resize(1180, 760)
        self.setMinimumSize(860, 520)

        self.work_dir: Optional[str] = cfg.get_work_dir()
        self.all_files: List[AudioFileInfo] = []
        self.group_items: Dict[str, QTreeWidgetItem] = {}
        self.file_items: Dict[str, QTreeWidgetItem] = {}  # path str -> item

        self.scan_worker: Optional[ScanWorker] = None
        self.conv_worker: Optional[ConversionWorker] = None

        # --- メディアプレイヤー(単一インスタンスを使い回し、重量化を回避) ---
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.active_row: Optional[RowControls] = None
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._duration_ms = 0

        self._build_ui()
        self._apply_saved_target_ext()

        if self.work_dir:
            self.path_edit.setText(self.work_dir)
            QTimer.singleShot(150, self.start_scan)
        else:
            self.status_bar.showMessage("作業フォルダを選択してください。")

        if not ffmpeg_available():
            QTimer.singleShot(300, self._warn_no_ffmpeg)

    # ------------------------------------------------------------------ UI 構築
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---- トップバー(フォルダ選択) ----
        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(8)

        title = QLabel("🎵  Sound Ext Converter")
        title.setStyleSheet("font-size:16px; font-weight:700;")
        top_layout.addWidget(title)
        top_layout.addSpacing(20)

        top_layout.addWidget(QLabel("作業フォルダ:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("フォルダパスを入力 or 右のボタンから選択")
        self.path_edit.returnPressed.connect(self._on_path_entered)
        top_layout.addWidget(self.path_edit, stretch=1)

        browse_btn = QPushButton("📂 選択...")
        browse_btn.clicked.connect(self._on_browse_clicked)
        top_layout.addWidget(browse_btn)

        apply_btn = QPushButton("適用")
        apply_btn.clicked.connect(self._on_path_entered)
        top_layout.addWidget(apply_btn)

        rescan_btn = QPushButton("🔄 再検索")
        rescan_btn.clicked.connect(self.start_scan)
        top_layout.addWidget(rescan_btn)

        root_layout.addWidget(top_bar)

        # ---- フィルタ行 ----
        filter_bar = QWidget()
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(16, 8, 16, 8)
        filter_layout.setSpacing(8)

        search_icon = QLabel("🔍")
        filter_layout.addWidget(search_icon)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("ファイル名 / サブフォルダ名で検索...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_edit, stretch=2)

        filter_layout.addWidget(QLabel("拡張子:"))
        self.ext_filter_combo = QComboBox()
        self.ext_filter_combo.addItem("すべて", None)
        self.ext_filter_combo.currentIndexChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.ext_filter_combo)

        filter_layout.addWidget(QLabel("サブフォルダ:"))
        self.subfolder_filter_combo = QComboBox()
        self.subfolder_filter_combo.addItem("すべて", None)
        self.subfolder_filter_combo.currentIndexChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.subfolder_filter_combo, stretch=1)

        clear_filter_btn = QPushButton("✕ クリア")
        clear_filter_btn.clicked.connect(self._clear_filters)
        filter_layout.addWidget(clear_filter_btn)

        self.match_count_label = QLabel("")
        self.match_count_label.setStyleSheet("color:#9aa0b4;")
        filter_layout.addWidget(self.match_count_label)

        root_layout.addWidget(filter_bar)

        # ---- ツリー(一覧) ----
        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["", "ファイル名", "サイズ", "拡張子", "再生 / 個別変換"])
        self.tree.setColumnWidth(COL_CHECK, 34)
        self.tree.setColumnWidth(COL_NAME, 340)
        self.tree.setColumnWidth(COL_SIZE, 80)
        self.tree.setColumnWidth(COL_EXT, 70)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        root_layout.addWidget(self.tree, stretch=1)

        # ---- 下部バー(一括変換) ----
        bottom_bar = QWidget()
        bottom_bar.setObjectName("TopBar")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
        bottom_layout.setSpacing(10)

        bottom_layout.addWidget(QLabel("変換先拡張子:"))
        self.target_combo = QComboBox()
        for key, fmt in TARGET_FORMATS.items():
            self.target_combo.addItem(fmt["label"], key)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        bottom_layout.addWidget(self.target_combo)

        self.delete_original_check = QCheckBox("変換後に元ファイルを削除")
        self.delete_original_check.setChecked(cfg.get_delete_original())
        self.delete_original_check.toggled.connect(cfg.set_delete_original)
        bottom_layout.addWidget(self.delete_original_check)

        bottom_layout.addStretch(1)

        self.selected_count_label = QLabel("選択中: 0件")
        self.selected_count_label.setStyleSheet("color:#9aa0b4;")
        bottom_layout.addWidget(self.selected_count_label)

        convert_selected_btn = QPushButton("✓ 選択したファイルを変換")
        convert_selected_btn.setObjectName("AccentButton")
        convert_selected_btn.clicked.connect(self._on_convert_selected_clicked)
        bottom_layout.addWidget(convert_selected_btn)

        convert_all_btn = QPushButton("⚡ 表示中すべてを変換")
        convert_all_btn.clicked.connect(self._on_convert_all_clicked)
        bottom_layout.addWidget(convert_all_btn)

        root_layout.addWidget(bottom_bar)

        # ---- ステータスバー ----
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # ---- 進捗オーバーレイ(central widget の上に重ねる) ----
        self.overlay = OverlayWidget(central)
        self.overlay.setGeometry(central.rect())
        central.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.centralWidget() and event.type() == event.Type.Resize:
            self.overlay.setGeometry(self.centralWidget().rect())
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------ フォルダ設定
    def _on_browse_clicked(self):
        start_dir = self.work_dir or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "作業フォルダを選択", start_dir)
        if selected:
            self.path_edit.setText(selected)
            self._commit_work_dir(selected)

    def _on_path_entered(self):
        text = self.path_edit.text().strip()
        if not text:
            return
        if not Path(text).is_dir():
            QMessageBox.warning(self, "エラー", "指定されたパスはフォルダとして存在しません。")
            return
        self._commit_work_dir(text)

    def _commit_work_dir(self, path: str):
        self.work_dir = path
        cfg.set_work_dir(path)
        self.status_bar.showMessage(f"作業フォルダを設定しました: {path}")
        self.start_scan()

    # ---------------------------------------------------------------- スキャン
    def start_scan(self):
        if not self.work_dir:
            QMessageBox.information(self, "案内", "先に作業フォルダを設定してください。")
            return
        if self.scan_worker and self.scan_worker.isRunning():
            return

        self._stop_playback()
        self.tree.clear()
        self.group_items.clear()
        self.file_items.clear()
        self.all_files = []
        self.status_bar.showMessage("検索中...")
        self.match_count_label.setText("検索中...")

        # フィルタ欄をリセット(新しい検索結果に合わせて選択肢を作り直すため)
        self.filter_edit.blockSignals(True)
        self.filter_edit.clear()
        self.filter_edit.blockSignals(False)
        self.ext_filter_combo.blockSignals(True)
        self.ext_filter_combo.clear()
        self.ext_filter_combo.addItem("すべて", None)
        self.ext_filter_combo.blockSignals(False)
        self.subfolder_filter_combo.blockSignals(True)
        self.subfolder_filter_combo.clear()
        self.subfolder_filter_combo.addItem("すべて", None)
        self.subfolder_filter_combo.blockSignals(False)

        self.scan_worker = ScanWorker(self.work_dir)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished_scan.connect(self._on_scan_finished)
        self.scan_worker.failed.connect(self._on_scan_failed)
        self.scan_worker.start()

    def _on_scan_progress(self, count: int):
        self.status_bar.showMessage(f"検索中... {count}件見つかりました")

    def _on_scan_failed(self, message: str):
        self.status_bar.showMessage("検索に失敗しました")
        QMessageBox.warning(self, "検索エラー", message)

    def _on_scan_finished(self, results: List[AudioFileInfo]):
        self.all_files = results
        self._populate_tree(results)
        self._populate_filter_options(results)
        self.status_bar.showMessage(f"完了: {len(results)}件のサウンドファイルを検出しました。")
        self._apply_filter()

    def _populate_filter_options(self, files: List[AudioFileInfo]):
        """検出結果から拡張子・サブフォルダの絞り込み候補を作成する"""
        self.ext_filter_combo.blockSignals(True)
        self.subfolder_filter_combo.blockSignals(True)
        try:
            self.ext_filter_combo.clear()
            self.ext_filter_combo.addItem("すべて", None)
            for ext in sorted({f.ext.lower() for f in files}):
                self.ext_filter_combo.addItem(ext.upper(), ext)

            self.subfolder_filter_combo.clear()
            self.subfolder_filter_combo.addItem("すべて", None)
            rel_dirs = sorted({f.rel_dir for f in files}, key=lambda s: (s != "", s))
            for rd in rel_dirs:
                label = "(ルート直下)" if rd == "" else rd
                self.subfolder_filter_combo.addItem(label, rd)
        finally:
            self.ext_filter_combo.blockSignals(False)
            self.subfolder_filter_combo.blockSignals(False)

    def _populate_tree(self, files: List[AudioFileInfo]):
        self.tree.blockSignals(True)
        try:
            groups: Dict[str, List[AudioFileInfo]] = {}
            for f in files:
                groups.setdefault(f.rel_dir, []).append(f)

            for rel_dir in sorted(groups.keys(), key=lambda s: (s != "", s)):
                items_in_group = sorted(groups[rel_dir], key=lambda f: f.name.lower())
                label = "📁 (ルート直下)" if rel_dir == "" else f"📁 {rel_dir}"
                group_item = QTreeWidgetItem(self.tree, [f"{label}  —  {len(items_in_group)}件"])
                group_item.setFirstColumnSpanned(True)
                group_item.setData(0, Qt.UserRole, {"type": "group", "rel_dir": rel_dir})
                group_item.setFlags(group_item.flags() | Qt.ItemIsAutoTristate | Qt.ItemIsUserCheckable)
                group_item.setCheckState(0, Qt.Unchecked)
                self.group_items[rel_dir] = group_item

                for info in items_in_group:
                    child = QTreeWidgetItem(group_item)
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                    child.setCheckState(COL_CHECK, Qt.Unchecked)
                    child.setText(COL_NAME, info.name)
                    child.setText(COL_SIZE, info.size_str)
                    child.setText(COL_EXT, info.ext.upper())
                    child.setData(0, Qt.UserRole, {"type": "file", "info": info})
                    self.file_items[str(info.path)] = child
        finally:
            self.tree.blockSignals(False)
        self.tree.expandToDepth(0) if len(self.all_files) <= 60 else None

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """遅延ロード: グループを開いたタイミングで子行に再生コントロールを設置する(高速化)"""
        data = item.data(0, Qt.UserRole)
        if not data or data.get("type") != "group":
            return
        for i in range(item.childCount()):
            child = item.child(i)
            if self.tree.itemWidget(child, COL_CTRL) is not None:
                continue
            child_data = child.data(0, Qt.UserRole)
            info: AudioFileInfo = child_data["info"]
            controls = RowControls(info, self)
            self.tree.setItemWidget(child, COL_CTRL, controls)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != COL_CHECK and column != 0:
            return
        self._update_selected_count()

    def _update_selected_count(self):
        n = len(self._get_checked_files())
        self.selected_count_label.setText(f"選択中: {n}件")

    def _get_checked_files(self) -> List[AudioFileInfo]:
        checked = []
        for path_str, item in self.file_items.items():
            if item.checkState(COL_CHECK) == Qt.Checked:
                data = item.data(0, Qt.UserRole)
                checked.append(data["info"])
        return checked

    def _clear_filters(self):
        self.filter_edit.blockSignals(True)
        self.filter_edit.clear()
        self.filter_edit.blockSignals(False)
        self.ext_filter_combo.blockSignals(True)
        self.ext_filter_combo.setCurrentIndex(0)
        self.ext_filter_combo.blockSignals(False)
        self.subfolder_filter_combo.blockSignals(True)
        self.subfolder_filter_combo.setCurrentIndex(0)
        self.subfolder_filter_combo.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self, *_args):
        """検索テキスト・拡張子・サブフォルダの3条件を組み合わせて一覧を絞り込む"""
        text = self.filter_edit.text().strip().lower()
        ext_filter = self.ext_filter_combo.currentData()
        subfolder_filter = self.subfolder_filter_combo.currentData()
        any_filter_active = bool(text) or ext_filter is not None or subfolder_filter is not None

        total_visible = 0
        for rel_dir, group in self.group_items.items():
            visible_children = 0
            for i in range(group.childCount()):
                child = group.child(i)
                data = child.data(0, Qt.UserRole)
                info: AudioFileInfo = data["info"]

                match = True
                if text and text not in info.name.lower() and text not in info.rel_dir.lower():
                    match = False
                if match and ext_filter is not None and info.ext.lower() != ext_filter:
                    match = False
                if match and subfolder_filter is not None and info.rel_dir != subfolder_filter:
                    match = False

                child.setHidden(not match)
                if match:
                    visible_children += 1

            group.setHidden(visible_children == 0)
            if any_filter_active and visible_children > 0:
                group.setExpanded(True)
            total_visible += visible_children

        total_all = len(self.all_files)
        if any_filter_active:
            self.match_count_label.setText(f"該当: {total_visible} / 全{total_all}件")
        else:
            self.match_count_label.setText(f"{total_all}件")

    # -------------------------------------------------------------- 再生制御
    def toggle_play(self, row: RowControls):
        if self.active_row is row and self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            row.set_playing_icon(False)
            return

        if self.active_row is row and self.player.playbackState() == QMediaPlayer.PausedState:
            self.player.play()
            row.set_playing_icon(True)
            return

        # 別ファイルへの切り替え
        if self.active_row and self.active_row is not row:
            self.active_row.set_playing_icon(False)
            self.active_row.update_position(0, self.active_row.seek_slider.maximum())

        self.active_row = row
        self.player.setSource(QUrl.fromLocalFile(str(row.info.path)))
        self.audio_output.setVolume(row.vol_slider.value() / 100.0)
        self.player.play()
        row.set_playing_icon(True)

    def seek_active(self, slider_value: int):
        if self.active_row is None or self._duration_ms <= 0:
            return
        pos = int(slider_value / 1000 * self._duration_ms)
        self.player.setPosition(pos)

    def set_volume_if_active(self, row: RowControls, volume: float):
        if self.active_row is row:
            self.audio_output.setVolume(volume)

    def _on_position_changed(self, position_ms: int):
        if self.active_row:
            self.active_row.update_position(position_ms, self._duration_ms)

    def _on_duration_changed(self, duration_ms: int):
        self._duration_ms = duration_ms

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.active_row:
            self.active_row.set_playing_icon(False)

    def _stop_playback(self):
        self.player.stop()
        if self.active_row:
            self.active_row.set_playing_icon(False)
        self.active_row = None

    # ------------------------------------------------------------- 変換操作
    def _apply_saved_target_ext(self):
        key = cfg.get_last_target_ext()
        idx = self.target_combo.findData(key)
        if idx >= 0:
            self.target_combo.setCurrentIndex(idx)

    def _on_target_changed(self, _idx: int):
        key = self.target_combo.currentData()
        if key:
            cfg.set_last_target_ext(key)

    def current_target_key(self) -> str:
        return self.target_combo.currentData()

    def _on_convert_selected_clicked(self):
        files = self._get_checked_files()
        if not files:
            QMessageBox.information(self, "案内", "変換するファイルにチェックを入れてください。")
            return
        self.convert_files(files)

    def _on_convert_all_clicked(self):
        # フィルタ非表示のものは除外し、現在ツリーに表示中の全ファイルを対象にする
        visible_files = []
        for path_str, item in self.file_items.items():
            if not item.isHidden():
                data = item.data(0, Qt.UserRole)
                visible_files.append(data["info"])
        if not visible_files:
            QMessageBox.information(self, "案内", "対象のファイルがありません。")
            return
        reply = QMessageBox.question(
            self, "確認",
            f"表示中の {len(visible_files)} 件をすべて "
            f"{TARGET_FORMATS[self.current_target_key()]['label']} に変換します。よろしいですか?"
        )
        if reply == QMessageBox.Yes:
            self.convert_files(visible_files)

    def _on_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data or data.get("type") != "group":
            return
        rel_dir = data["rel_dir"]

        menu = QMenu(self)
        act_select = menu.addAction("このフォルダ以下を全て選択")
        act_deselect = menu.addAction("このフォルダ以下の選択を解除")
        menu.addSeparator()
        act_convert = menu.addAction(
            f"このフォルダ以下を再帰的にすべて変換 ({TARGET_FORMATS[self.current_target_key()]['label']})"
        )
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))

        if action == act_select:
            self._set_group_checked(item, True)
        elif action == act_deselect:
            self._set_group_checked(item, False)
        elif action == act_convert:
            files = [self.file_items[p].data(0, Qt.UserRole)["info"]
                     for p in self.file_items
                     if self.file_items[p].data(0, Qt.UserRole)["info"].rel_dir.startswith(rel_dir)]
            if files:
                reply = QMessageBox.question(
                    self, "確認",
                    f"「{rel_dir or '(ルート直下)'}」以下の {len(files)} 件を再帰的に変換します。よろしいですか?"
                )
                if reply == QMessageBox.Yes:
                    self.convert_files(files)

    def _set_group_checked(self, group_item: QTreeWidgetItem, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        self.tree.blockSignals(True)
        for i in range(group_item.childCount()):
            group_item.child(i).setCheckState(COL_CHECK, state)
        self.tree.blockSignals(False)
        self._update_selected_count()

    def convert_files(self, files: List[AudioFileInfo]):
        if not files:
            return
        if not ffmpeg_available():
            self._warn_no_ffmpeg()
            return
        if self.conv_worker and self.conv_worker.isRunning():
            QMessageBox.information(self, "案内", "現在他の変換処理が実行中です。")
            return

        self._stop_playback()
        target_key = self.current_target_key()
        delete_original = self.delete_original_check.isChecked()

        self._set_ui_busy(True)
        self.overlay.start(len(files))

        self.conv_worker = ConversionWorker(files, target_key, delete_original)
        self.conv_worker.progress.connect(self.overlay.update_progress)
        self.conv_worker.finished_all.connect(self._on_conversion_finished)
        self.conv_worker.start()

    def _on_conversion_finished(self, success: int, failed: int):
        self.overlay.finish()
        self._set_ui_busy(False)
        msg = f"変換完了: 成功 {success}件"
        if failed:
            msg += f" / 失敗 {failed}件"
        self.status_bar.showMessage(msg)
        QMessageBox.information(self, "変換完了", msg)
        # 変換結果を反映するため再検索
        self.start_scan()

    def _set_ui_busy(self, busy: bool):
        for w in self.findChildren(QWidget):
            if w is self.overlay or self._is_descendant(self.overlay, w):
                continue
        self.centralWidget().setEnabled(not busy)
        self.overlay.setEnabled(True)

    @staticmethod
    def _is_descendant(parent: QWidget, widget: QWidget) -> bool:
        w = widget
        while w is not None:
            if w is parent:
                return True
            w = w.parentWidget()
        return False

    def _warn_no_ffmpeg(self):
        QMessageBox.warning(
            self, "ffmpegが見つかりません",
            "拡張子変換には ffmpeg が必要です。\n"
            "ffmpeg をインストールし、PATHが通った状態でこのアプリを起動してください。\n"
            "( https://ffmpeg.org/download.html )"
        )

    def closeEvent(self, event):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.scan_worker.wait(1000)
        if self.conv_worker and self.conv_worker.isRunning():
            reply = QMessageBox.question(
                self, "確認", "変換処理が実行中です。終了してよろしいですか?"
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self.conv_worker.stop()
            self.conv_worker.wait(2000)
        self.player.stop()
        super().closeEvent(event)
