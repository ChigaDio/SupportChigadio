#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scenario Toolkit
=================
社内のシナリオイベント編集システム(Flask + React)向けの、
スタンドアロンPython(PySide6)製デスクトップGUIクライアント。

- ロール一覧管理  (ScenarioRoleGrid.js 相当)
- トランザクションDSLエディタ (ScenarioTransactionCodeEditor.js /
  scenarioTransactionDsl.js のトークナイザをQt用に移植)
- 条件タブ (ScenarioConditionsGrid.js のプレースホルダー相当・拡張用の土台)

既存のFlaskサーバー(/api/scenario-role, /api/role-form-schema/<name> など)
に対してHTTP経由でアクセスする、いわば「Reactフロントエンドの代わりに
動くネイティブGUI」という位置づけ。

依存パッケージ:
    pip install PySide6 requests

実行:
    python scenario_toolkit.py
"""

from __future__ import annotations

import os
import re
import sys
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from PySide6.QtCore import (
    Qt, QThreadPool, QRunnable, QObject, Signal, Slot, QRegularExpression,
    QRect, QSize,
)
from PySide6.QtGui import (
    QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QPainter, QTextFormat,
    QAction, QIcon, QPalette,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLabel, QLineEdit,
    QDialog, QDialogButtonBox, QFormLayout, QComboBox, QMessageBox, QPlainTextEdit,
    QStatusBar, QFrame, QToolBar, QSizePolicy, QAbstractItemView, QTextEdit,
    QSplitter, QListWidget, QListWidgetItem, QStackedWidget, QProgressBar,
    QCheckBox, QSpinBox, QDoubleSpinBox, QColorDialog, QInputDialog, QScrollArea,
    QTreeWidget, QTreeWidgetItem,
)

APP_ORG = "Kernel"
APP_NAME = "ScenarioToolkit"
DEFAULT_BASE_URL = "http://localhost:5000"

# 設定データはスクリプト位置から ../../../data に保存する
_SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = (_SCRIPT_DIR / ".." / ".." / ".." / "data").resolve()
SETTINGS_PATH = DATA_DIR / "scenario_toolkit_settings.json"


def ensure_data_dir() -> Path:
    """../../../data を作成して返す。"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return DATA_DIR


def load_app_settings() -> dict:
    ensure_data_dir()
    if SETTINGS_PATH.is_file():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_app_settings(settings: dict) -> None:
    ensure_data_dir()
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"[ScenarioToolkit] 設定の保存に失敗: {exc}", file=sys.stderr)


# ============================================================
# 配色 / スタイルシート ("おしゃれ" ダークテーマ)
# ============================================================

COLORS = {
    "bg": "#1a1b23",
    "bg_alt": "#20222c",
    "surface": "#262835",
    "surface_hover": "#2f3140",
    "border": "#383b4a",
    "text": "#e6e6f0",
    "text_dim": "#8b8da3",
    "accent": "#7c6cf0",
    "accent_hover": "#9384f5",
    "accent_dim": "#4a3f99",
    "success": "#3ecf8e",
    "warning": "#f0a742",
    "danger": "#f0596b",
    "branch_general": "#5aa9f0",
    "branch_branch": "#f0a742",
}

STYLE_SHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: "Segoe UI", "Yu Gothic UI", "Hiragino Sans", sans-serif;
    font-size: 13px;
}}

QToolBar {{
    background-color: {COLORS['bg_alt']};
    border: none;
    padding: 8px 12px;
    spacing: 8px;
}}

QStatusBar {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['text_dim']};
    border-top: 1px solid {COLORS['border']};
}}

QListWidget#NavList {{
    background-color: {COLORS['bg_alt']};
    border: none;
    border-right: 1px solid {COLORS['border']};
    padding: 10px 6px;
    outline: none;
}}
QListWidget#NavList::item {{
    padding: 10px 14px;
    border-radius: 8px;
    margin: 2px 4px;
    color: {COLORS['text_dim']};
}}
QListWidget#NavList::item:selected {{
    background-color: {COLORS['accent_dim']};
    color: {COLORS['text']};
    font-weight: 600;
}}
QListWidget#NavList::item:hover:!selected {{
    background-color: {COLORS['surface_hover']};
}}

QLabel#PageTitle {{
    font-size: 20px;
    font-weight: 700;
    color: {COLORS['text']};
    padding: 4px 0 2px 0;
}}
QLabel#PageSubtitle {{
    color: {COLORS['text_dim']};
    padding-bottom: 10px;
}}

QPushButton {{
    background-color: {COLORS['surface']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 7px 16px;
}}
QPushButton:hover {{ background-color: {COLORS['surface_hover']}; }}
QPushButton:pressed {{ background-color: {COLORS['border']}; }}

QPushButton#Primary {{
    background-color: {COLORS['accent']};
    border: none;
    color: white;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background-color: {COLORS['accent_hover']}; }}

QPushButton#Danger {{
    background-color: transparent;
    border: 1px solid {COLORS['danger']};
    color: {COLORS['danger']};
    padding: 4px 10px;
}}
QPushButton#Danger:hover {{ background-color: {COLORS['danger']}; color: white; }}

QLineEdit, QComboBox {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 10px;
    color: {COLORS['text']};
    selection-background-color: {COLORS['accent']};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {COLORS['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['accent_dim']};
}}

QTableWidget {{
    background-color: {COLORS['bg']};
    alternate-background-color: {COLORS['bg_alt']};
    gridline-color: transparent;
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    selection-background-color: {COLORS['accent_dim']};
    selection-color: {COLORS['text']};
}}
QTableWidget::item {{ padding: 8px; border-bottom: 1px solid {COLORS['border']}; }}
QHeaderView::section {{
    background-color: {COLORS['surface']};
    color: {COLORS['text_dim']};
    padding: 10px 8px;
    border: none;
    border-bottom: 2px solid {COLORS['border']};
    font-weight: 600;
}}

QFrame#Card {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}

QDialog {{ background-color: {COLORS['bg_alt']}; }}

QPlainTextEdit#DslEditor {{
    background-color: #14151c;
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    font-family: "Cascadia Code", "Consolas", "Menlo", monospace;
    font-size: 13px;
    padding: 10px;
    selection-background-color: {COLORS['accent_dim']};
}}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border']}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {COLORS['text_dim']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QLabel#StatusPill {{
    border-radius: 9px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 11px;
}}
"""


# ============================================================
# 汎用: バックグラウンドHTTPワーカー (UIをブロックしない)
# ============================================================

class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class HttpWorker(QRunnable):
    """requestsでの呼び出しをスレッドプール上で実行する。"""

    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn()
            self.signals.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))


class ApiClient:
    """既存Flaskサーバーへの薄いHTTPクライアント。

    設定(base_url 等)は QSettings ではなく ../../../data/scenario_toolkit_settings.json に保存する。
    書き込み系API呼び出し時は busy コールバック経由で UI をロックできる。
    """

    def __init__(self):
        self._settings = load_app_settings()
        self.base_url: str = str(self._settings.get("base_url") or DEFAULT_BASE_URL)
        self.pool = QThreadPool.globalInstance()
        # MainWindow が set_busy / clear_busy を差し込む
        self.on_busy_start: Optional[Callable[[str], None]] = None
        self.on_busy_end: Optional[Callable[[], None]] = None

    def set_base_url(self, url: str):
        self.base_url = (url or DEFAULT_BASE_URL).rstrip("/")
        self._settings["base_url"] = self.base_url
        save_app_settings(self._settings)

    def _run(self, fn, on_success, on_error, busy_message: Optional[str] = None):
        """HTTP をスレッドプールで実行。busy_message 指定時は UI をロックする。"""
        if busy_message and self.on_busy_start:
            self.on_busy_start(busy_message)

        def _ok(result):
            if busy_message and self.on_busy_end:
                self.on_busy_end()
            on_success(result)

        def _err(msg):
            if busy_message and self.on_busy_end:
                self.on_busy_end()
            on_error(msg)

        worker = HttpWorker(fn)
        worker.signals.finished.connect(_ok)
        worker.signals.error.connect(_err)
        self.pool.start(worker)

    def get_scenario_roles(self, on_success, on_error):
        def _do():
            resp = requests.get(f"{self.base_url}/api/scenario-role", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error)

    def create_scenario_role(self, payload: dict, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/scenario-role", json=payload, timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="ロールを作成中…")

    def delete_scenario_role(self, name: str, on_success, on_error):
        def _do():
            resp = requests.patch(f"{self.base_url}/api/scenario-role", json={"name": name}, timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message=f"ロール「{name}」を削除中…")

    # ---- ロール詳細 (フィールドスキーマ) : ScenarioRoleDetailGrid.js 相当 ----

    def get_role_detail(self, name: str, on_success, on_error):
        def _do():
            resp = requests.get(f"{self.base_url}/api/scenario-role/{name}", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error)

    def save_role_detail(self, name: str, data: list, branch_type: str, on_success, on_error):
        def _do():
            resp = requests.post(
                f"{self.base_url}/api/scenario-role/{name}",
                json={"data": data, "branchType": branch_type}, timeout=8,
            )
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message=f"ロール「{name}」を保存中…")

    def delete_role(self, name: str, on_success, on_error):
        def _do():
            resp = requests.delete(f"{self.base_url}/api/scenario-role/{name}", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message=f"ロール「{name}」を削除中…")

    def generate_role_cs(self, name: str, data: list, branch_type: str, on_success, on_error):
        def _do():
            resp = requests.post(
                f"{self.base_url}/api/generate-scenario-role/{name}",
                json={"data": data, "branchType": branch_type}, timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message=f"ロール「{name}」のC#を生成中…")

    def get_type_options(self, on_success, on_error):
        """enum-id / class-data / class-data-id / custom-class-data-type-options をまとめて取得。
        ScenarioRoleDetailGrid.js のタイプ選択肢と同じ組み立て方。1つでも失敗したら空扱いにする。"""
        def _do():
            def safe_get(path):
                try:
                    r = requests.get(f"{self.base_url}{path}", timeout=5)
                    r.raise_for_status()
                    return r.json()
                except Exception:
                    return []
            enum_list = safe_get("/api/enum-id")
            class_list = safe_get("/api/class-data")
            class_id_list = safe_get("/api/class-data-id")
            custom = safe_get("/api/custom-class-data-type-options")
            if not isinstance(custom, dict):
                custom = {}
            return {
                "enum": [i.get("name") for i in enum_list if isinstance(i, dict) and i.get("name")],
                "class": [i.get("name") for i in class_list if isinstance(i, dict) and i.get("name")],
                "class_id": [i.get("name") for i in class_id_list if isinstance(i, dict) and i.get("name")],
                "custom_class": custom.get("custom_class_list", []),
                "custom_class_id": custom.get("custom_class_id_list", []),
                "custom_value": list(dict.fromkeys((custom.get("custom_types", []) or []) + ["dictionary"])),
            }
        self._run(_do, on_success, on_error)

    def get_enum_values(self, enum_type: str, on_success, on_error):
        def _do():
            resp = requests.get(f"{self.base_url}/api/enum/{enum_type}", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error)

    def get_role_form_schema(self, role_name: str, on_success, on_error):
        def _do():
            resp = requests.get(f"{self.base_url}/api/role-form-schema/{role_name}", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error)

    # ---- ストーリー設定 : ScenarioStorySettingGrid.js 相当 ----

    def get_story_slot_defs(self, on_success, on_error):
        def _do():
            resp = requests.get(f"{self.base_url}/api/story-setting/slot-defs", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error)

    def get_story_setting(self, event_id, sub_id, on_success, on_error):
        def _do():
            resp = requests.get(f"{self.base_url}/api/scenario-event/{event_id}/sub/{sub_id}/story", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error)

    def save_story_setting(self, event_id, sub_id, payload: dict, on_success, on_error):
        def _do():
            resp = requests.post(
                f"{self.base_url}/api/scenario-event/{event_id}/sub/{sub_id}/story",
                json=payload, timeout=8,
            )
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="ストーリー設定を保存中…")

    def get_assets(self, kind: str, on_success, on_error):
        """kind: texture / sound / gameobject"""
        def _do():
            resp = requests.get(f"{self.base_url}/api/{kind}", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error)

    def generate_story_setting(self, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/story-setting/generate", timeout=15)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="ストーリー設定バイナリを生成中…")

    def generate_voice_role(self, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/story-setting/generate-voice-role", timeout=15)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="Voiceロールを生成中…")

    # ---- シナリオイベント一覧 : ScenarioEventGrid.js 相当 ----

    def get_events(self, on_success, on_error):
        def _do():
            resp = requests.get(f"{self.base_url}/api/scenario-event", timeout=5)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error)

    def create_event(self, payload: dict, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/scenario-event", json=payload, timeout=8)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="イベントを作成中…")

    def update_event(self, event_id, payload: dict, on_success, on_error):
        def _do():
            resp = requests.patch(f"{self.base_url}/api/scenario-event/{event_id}", json=payload, timeout=8)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="イベントを更新中…")

    def delete_event(self, event_id, on_success, on_error):
        def _do():
            resp = requests.delete(f"{self.base_url}/api/scenario-event/{event_id}", timeout=8)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message=f"イベント {event_id} を削除中…")

    def copy_event(self, event_id, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/scenario-event/{event_id}/copy", timeout=8)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message=f"イベント {event_id} を複製中…")

    def add_sub(self, event_id, payload: dict, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/scenario-event/{event_id}/sub", json=payload, timeout=8)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="Subを作成中…")

    def update_sub(self, event_id, sub_id, payload: dict, on_success, on_error):
        def _do():
            resp = requests.patch(
                f"{self.base_url}/api/scenario-event/{event_id}/sub/{sub_id}", json=payload, timeout=8,
            )
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="Subを更新中…")

    def delete_sub(self, event_id, sub_id, on_success, on_error):
        def _do():
            resp = requests.delete(f"{self.base_url}/api/scenario-event/{event_id}/sub/{sub_id}", timeout=8)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message=f"Sub {sub_id} を削除中…")

    def copy_sub(self, event_id, sub_id, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/scenario-event/{event_id}/sub/{sub_id}/copy", timeout=8)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message=f"Sub {sub_id} を複製中…")

    def fix_all_events(self, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/fix-all-events", timeout=30)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="全イベントを修正中… (しばらくお待ちください)")

    def generate_all_event_bin(self, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/generate-all-event-bin", timeout=60)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="全イベントバイナリを生成中… (しばらくお待ちください)")

    def migrate_legacy_events(self, on_success, on_error):
        def _do():
            resp = requests.post(f"{self.base_url}/api/scenario-event/migrate-legacy", timeout=30)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="レガシーイベントを移行中…")

    # ---- トランジション(ノードツリー)とロールデータ入力 : ScenarioEventTransition.js 相当 ----

    def get_transition(self, event_id, sub_id, on_success, on_error):
        def _do():
            resp = requests.get(f"{self.base_url}/api/scenario-event/{event_id}/sub/{sub_id}/transition", timeout=8)
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="ノードツリーを読み込み中…")

    def save_role_instance_data(self, event_id, sub_id, node_id, unique_id, data: list, on_success, on_error):
        def _do():
            resp = requests.post(
                f"{self.base_url}/api/save-role-data/{event_id}/{sub_id}/{node_id}/{unique_id}",
                json={"data": data}, timeout=8,
            )
            resp.raise_for_status()
            return resp.json()
        self._run(_do, on_success, on_error, busy_message="ロールデータを保存中…")


# ============================================================
# ステータスピル (接続状態 / タイプバッジ 等の小さな色付きラベル)
# ============================================================

def make_pill(text: str, bg: str, fg: str = "#0d0e12") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("StatusPill")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"background-color: {bg}; color: {fg};")
    return lbl


# ============================================================
# ページ 1: ロール一覧管理 (ScenarioRoleGrid.js 相当)
# ============================================================

class AddRoleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新しいロールの作成")
        self.setMinimumWidth(360)
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例: ShowHideCharacter")
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("このロールの説明")
        self.branch_combo = QComboBox()
        self.branch_combo.addItems(["General", "Branch"])

        layout.addRow("ロール名 *", self.name_edit)
        layout.addRow("説明", self.desc_edit)
        layout.addRow("タイプ", self.branch_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("作成")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.button(QDialogButtonBox.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
            "branchType": self.branch_combo.currentText(),
        }


class RoleListPage(QWidget):
    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.rows: list[dict] = []
        self._build_ui()
        self.reload()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("シナリオロール")
        title.setObjectName("PageTitle")
        subtitle = QLabel("登録済みのロール一覧。行の色でタイプを見分けられます。")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.reload_btn = QPushButton("再読み込み")
        self.reload_btn.clicked.connect(self.reload)
        header.addWidget(self.reload_btn)

        add_btn = QPushButton("+  追加")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self.on_add)
        header.addWidget(add_btn)
        root.addLayout(header)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "名前", "説明", "タイプ", ""])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 90)
        self.table.verticalHeader().setDefaultSectionSize(46)
        root.addWidget(self.table)

        self.empty_label = QLabel("ロールがまだありません。「追加」から作成してください。")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {COLORS['text_dim']}; padding: 40px;")
        self.empty_label.hide()
        root.addWidget(self.empty_label)

    def reload(self):
        self.reload_btn.setText("読み込み中…")
        self.reload_btn.setEnabled(False)
        self.api.get_scenario_roles(self._on_loaded, self._on_error)

    def _on_loaded(self, data):
        self.reload_btn.setText("再読み込み")
        self.reload_btn.setEnabled(True)
        if not isinstance(data, list):
            data = []
        self.rows = data
        self._render_rows()

    def _on_error(self, message: str):
        self.reload_btn.setText("再読み込み")
        self.reload_btn.setEnabled(True)
        self.rows = []
        self._render_rows()
        self._toast(f"取得エラー: サーバーに接続できませんでした ({message})", error=True)

    def _render_rows(self):
        self.table.setRowCount(0)
        self.empty_label.setVisible(len(self.rows) == 0)
        self.table.setVisible(len(self.rows) > 0)

        for row in self.rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            name = row.get("name", "不明")
            branch_type = row.get("branchType", "General")

            self.table.setItem(r, 0, QTableWidgetItem(str(row.get("id", ""))))
            name_item = QTableWidgetItem(name)
            name_font = name_item.font()
            name_font.setBold(True)
            name_item.setFont(name_font)
            self.table.setItem(r, 1, name_item)
            self.table.setItem(r, 2, QTableWidgetItem(row.get("description", "")))

            color = COLORS["branch_branch"] if branch_type == "Branch" else COLORS["branch_general"]
            pill_wrap = QWidget()
            pill_layout = QHBoxLayout(pill_wrap)
            pill_layout.setContentsMargins(6, 4, 6, 4)
            pill_layout.addWidget(make_pill(branch_type, color))
            pill_layout.addStretch()
            self.table.setCellWidget(r, 3, pill_wrap)

            del_btn = QPushButton("削除")
            del_btn.setObjectName("Danger")
            del_btn.clicked.connect(lambda _=False, n=name: self.on_delete(n))
            del_wrap = QWidget()
            del_layout = QHBoxLayout(del_wrap)
            del_layout.setContentsMargins(6, 2, 6, 2)
            del_layout.addWidget(del_btn)
            self.table.setCellWidget(r, 4, del_wrap)

    def on_add(self):
        dialog = AddRoleDialog(self)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.values()
            if not values["name"]:
                self._toast("ロール名を入力してください", error=True)
                return
            self.api.create_scenario_role(
                values,
                lambda result: (self._toast(result.get("message", "作成しました")), self.reload()),
                lambda msg: self._toast(f"作成エラー: {msg}", error=True),
            )

    def on_delete(self, name: str):
        confirm = QMessageBox.question(
            self, "確認", f"ロール「{name}」を削除しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.api.delete_scenario_role(
            name,
            lambda result: (self._toast(result.get("message", "削除しました")), self.reload()),
            lambda msg: self._toast(f"削除エラー: {msg}", error=True),
        )

    def _toast(self, message: str, error: bool = False):
        main_window = self.window()
        if hasattr(main_window, "show_status"):
            main_window.show_status(message, error=error)


# ============================================================
# ページ 2: トランザクションDSLエディタ
#   (scenarioTransactionDsl.js の TOKEN_PATTERN / tokenizeLine を移植)
# ============================================================

# JS: /#.*$|"(?:[^"\\]|\\.)*"|[(){}[\],=:]|-?\d+(?:\.\d+)?|[^\s(){}[\],="#:]+/g
TOKEN_PATTERN = re.compile(
    r'#.*$|"(?:[^"\\]|\\.)*"|[(){}\[\],=:]|-?\d+(?:\.\d+)?|[^\s(){}\[\],="#:]+'
)


def tokenize_line(line: str) -> list[dict]:
    tokens = []
    for m in TOKEN_PATTERN.finditer(line):
        raw = m.group(0)
        start, end = m.span()
        if raw.startswith("#"):
            ttype = "COMMENT"
        elif raw.startswith('"'):
            ttype = "STRING"
        elif raw == "(":
            ttype = "LPAREN"
        elif raw == ")":
            ttype = "RPAREN"
        elif raw == "[":
            ttype = "LBRACKET"
        elif raw == "]":
            ttype = "RBRACKET"
        elif raw == "{":
            ttype = "LBRACE"
        elif raw == "}":
            ttype = "RBRACE"
        elif raw == ":":
            ttype = "COLON"
        elif raw == ",":
            ttype = "COMMA"
        elif raw == "=":
            ttype = "EQUALS"
        elif re.match(r"^-?\d", raw):
            ttype = "NUMBER"
        else:
            ttype = "IDENT"
        tokens.append({"type": ttype, "value": raw, "from": start, "to": end})
    return tokens


class DslSyntaxHighlighter(QSyntaxHighlighter):
    """1行1コマンドのTransaction DSL用シンタックスハイライター。
    ScenarioTransactionCodeEditor.js の buildDslLanguage() と同じトークン→色の
    対応付けをQt側で再現している。
    """

    def __init__(self, document):
        super().__init__(document)
        self.formats = self._build_formats()

    @staticmethod
    def _fmt(color: str, bold=False, italic=False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Bold)
        f.setFontItalic(italic)
        return f

    def _build_formats(self):
        return {
            "comment": self._fmt("#6a7280", italic=True),
            "string": self._fmt("#e5b567"),
            "number": self._fmt("#8fd19e"),
            "operator": self._fmt("#e6e6f0"),
            "punctuation": self._fmt("#8b8da3"),
            "keyword": self._fmt("#c792ea", bold=True),   # ロール名 (行頭IDENT)
            "atom": self._fmt("#82aaff"),                   # true / false
            "variableName": self._fmt("#89ddff"),
        }

    def highlightBlock(self, text: str):
        tokens = tokenize_line(text)
        for idx, tok in enumerate(tokens):
            is_role_name = idx == 0
            ttype = tok["type"]
            if ttype == "COMMENT":
                style = "comment"
            elif ttype == "STRING":
                style = "string"
            elif ttype == "NUMBER":
                style = "number"
            elif ttype == "EQUALS":
                style = "operator"
            elif ttype in ("LPAREN", "RPAREN", "LBRACKET", "RBRACKET", "LBRACE", "RBRACE", "COMMA", "COLON"):
                style = "punctuation"
            elif ttype == "IDENT":
                if is_role_name:
                    style = "keyword"
                elif tok["value"] in ("true", "false"):
                    style = "atom"
                else:
                    style = "variableName"
            else:
                continue
            self.setFormat(tok["from"], tok["to"] - tok["from"], self.formats[style])


class LineNumberArea(QWidget):
    def __init__(self, editor: "DslEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class DslEditor(QPlainTextEdit):
    """行番号ガター付きのDSLエディタ本体。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DslEditor")
        self.line_numbers = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

    def line_number_area_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self.line_numbers.scroll(0, dy)
        else:
            self.line_numbers.update(0, rect.y(), self.line_numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_numbers.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def _highlight_current_line(self):
        extra = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(COLORS["surface"]))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra.append(selection)
        self.setExtraSelections(extra)

    def paint_line_numbers(self, event):
        painter = QPainter(self.line_numbers)
        painter.fillRect(event.rect(), QColor(COLORS["bg_alt"]))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        painter.setPen(QColor(COLORS["text_dim"]))
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, int(top), self.line_numbers.width() - 8, self.fontMetrics().height(),
                    Qt.AlignRight, str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1


SAMPLE_DSL = """# ==== SUB:1 NODE:1 ====
ShowHideCharacter(characterId=GuestCharacterID.GuestCharacter_01, visible=true)
SetBackground(imageId="bg_park_day", fadeSeconds=0.5)

# ==== SUB:1 NODE:1/1 ====
PlayVoice(voiceRef=VoiceLine.Guest01_Greeting_01, waitForFinish=true)
"""


class DslEditorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("トランザクション DSL エディタ")
        title.setObjectName("PageTitle")
        subtitle = QLabel("1行1コマンドのDSLをシンタックスハイライト付きで編集します。")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        sample_btn = QPushButton("サンプルを挿入")
        sample_btn.clicked.connect(self.insert_sample)
        header.addWidget(sample_btn)

        clear_btn = QPushButton("クリア")
        clear_btn.clicked.connect(lambda: self.editor.clear())
        header.addWidget(clear_btn)
        root.addLayout(header)

        legend = QHBoxLayout()
        legend.setSpacing(14)
        for label, color in [
            ("ロール名", "#c792ea"), ("文字列", "#e5b567"), ("数値", "#8fd19e"),
            ("真偽値", "#82aaff"), ("変数/値", "#89ddff"), ("コメント", "#6a7280"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")
            text = QLabel(label)
            text.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
            pair = QHBoxLayout()
            pair.setSpacing(4)
            pair_wrap = QWidget()
            pair.addWidget(dot)
            pair.addWidget(text)
            pair_wrap.setLayout(pair)
            legend.addWidget(pair_wrap)
        legend.addStretch()
        root.addLayout(legend)

        self.editor = DslEditor()
        self.editor.setPlaceholderText("ここにDSLを入力… 例: ShowHideCharacter(characterId=..., visible=true)")
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(11)
        self.editor.setFont(mono)
        self.highlighter = DslSyntaxHighlighter(self.editor.document())
        self.editor.setPlainText(SAMPLE_DSL)
        root.addWidget(self.editor)

    def insert_sample(self):
        cursor = self.editor.textCursor()
        cursor.insertText(SAMPLE_DSL)


# ============================================================
# ページ 3: 条件 (ScenarioConditionsGrid.js 相当・拡張用の土台)
# ============================================================

class ConditionsPage(QWidget):
    """ScenarioConditionsGrid.js 相当。

    現状 Web 側もプレースホルダーのみで、専用 API エンドポイントが未整備のため、
    クライアント側では設計パターンを揃えた土台 UI を用意している。
    バックエンドに /api/scenario-condition 等が追加されたら ApiClient 経由で接続する。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("条件")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "条件(Conditions)の管理。Web版(ScenarioConditionsGrid.js)と同様、"
            "専用APIがまだ無いためプレースホルダーです。"
        )
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        msg = QLabel(
            "■ 現状\n"
            "  Web の ScenarioConditionsGrid.js もプレースホルダーのみで、\n"
            "  /api/scenario-condition 等のエンドポイントは未実装です。\n\n"
            "■ 拡張の進め方\n"
            "  1. Flask 側に条件 CRUD API を追加\n"
            "  2. ApiClient に get/create/update/delete メソッドを追加\n"
            "  3. ロール一覧(RoleListPage)と同じくテーブル + ダイアログで実装\n\n"
            "設定ファイルは ../../../data/scenario_toolkit_settings.json に保存されます。"
        )
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {COLORS['text_dim']};")
        card_layout.addWidget(msg)
        root.addWidget(card)
        root.addStretch()


# ============================================================
# 共通: フィールド型 / デフォルト値 (BaseRoleInputForm.js の getDefaultValue移植)
# ============================================================

BASIC_TYPES = ["int", "short", "long", "byte", "float", "double", "decimal", "char", "bool", "string", "object"]
UNITY_TYPES = [
    "GameObject", "Transform", "Vector2", "Vector3", "Vector4", "Quaternion", "Color", "Rect",
    "Bounds", "Matrix4x4", "AnimationCurve", "Sprite", "Texture", "Material", "Mesh",
    "Rigidbody", "Collider", "AudioClip", "ScriptableObject",
]
EXTRA_TYPES = ["voice_ref", "text_list_index", "bit", "color", "bezier", "dictionary"]
VECTOR_SIZES = {"vector2": 2, "vector3": 3, "vector4": 4}


def get_default_value(field_type: str, array_size: int = 0):
    """BaseRoleInputForm.js の getDefaultValue() 相当。"""
    if array_size and array_size > 0:
        return [get_default_value(field_type, 0) for _ in range(array_size)]
    if array_size == -1:
        return []
    t = (field_type or "").lower()
    if t in ("int", "short", "long", "byte"):
        return 0
    if t in ("float", "double", "decimal"):
        return 0.0
    if t == "char":
        return ""
    if t == "bool":
        return False
    if t == "string":
        return ""
    if t in VECTOR_SIZES:
        return [0] * VECTOR_SIZES[t]
    return ""


# ============================================================
# 動的フィールドウィジェット (BaseRoleInputForm.js のフィールド描画部分を移植)
#   - 数値・真偽値・文字列・Vector2/3/4 はネイティブなQtウィジェットで編集
#   - enum型は/api/enum/<type>で取得できればコンボボックスに、できなければテキスト
#   - class参照・voice_ref・bit・bezier・dictionary等の特殊型は簡易テキスト編集
#     (元システムほどのリッチな専用UIではない旨をヒントラベルで明示する)
# ============================================================

@dataclass
class SingleWidget:
    widget: QWidget
    get_value: Callable[[], Any]
    set_value: Callable[[Any], None]


def build_single_value_widget(field_type: str, value: Any, enum_values: Optional[list] = None) -> SingleWidget:
    t = (field_type or "").lower()

    if t in ("int", "short", "long", "byte"):
        box = _spin_int()
        box.setValue(int(value) if isinstance(value, (int, float)) else 0)
        return SingleWidget(box, lambda: box.value(), lambda v: box.setValue(int(v) if v else 0))

    if t in ("float", "double", "decimal"):
        box = _spin_float()
        box.setValue(float(value) if isinstance(value, (int, float)) else 0.0)
        return SingleWidget(box, lambda: box.value(), lambda v: box.setValue(float(v) if v else 0.0))

    if t == "bool":
        chk = QCheckBox("true / false")
        chk.setChecked(bool(value))
        return SingleWidget(chk, lambda: chk.isChecked(), lambda v: chk.setChecked(bool(v)))

    if t in ("string", "char", "object"):
        edit = QLineEdit(str(value) if value not in (None, "") else "")
        return SingleWidget(edit, lambda: edit.text(), lambda v: edit.setText(str(v) if v is not None else ""))

    if t in VECTOR_SIZES:
        size = VECTOR_SIZES[t]
        vals = value if isinstance(value, list) and len(value) == size else [0] * size
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        boxes = []
        for i, axis in enumerate(["x", "y", "z", "w"][:size]):
            lbl = QLabel(axis)
            lbl.setStyleSheet(f"color: {COLORS['text_dim']};")
            box = _spin_float()
            box.setValue(float(vals[i]) if i < len(vals) else 0.0)
            row.addWidget(lbl)
            row.addWidget(box)
            boxes.append(box)
        row.addStretch()
        return SingleWidget(
            container,
            lambda: [b.value() for b in boxes],
            lambda v: [boxes[i].setValue(float(v[i])) for i in range(size) if isinstance(v, list) and i < len(v)],
        )

    if t == "color":
        # 保存形式は {r,g,b,a} (0〜1)。表示は #RRGGBB + アルファスライダ相当のスピン。
        def _obj_to_hex(v):
            if isinstance(v, dict):
                r = int(max(0, min(1, float(v.get("r", 1)))) * 255)
                g = int(max(0, min(1, float(v.get("g", 1)))) * 255)
                b = int(max(0, min(1, float(v.get("b", 1)))) * 255)
                return f"#{r:02x}{g:02x}{b:02x}", float(v.get("a", 1))
            if isinstance(v, str) and v.startswith("#"):
                return v[:7], 1.0
            return "#ffffff", 1.0

        hex0, a0 = _obj_to_hex(value)
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        edit = QLineEdit(hex0)
        swatch = QPushButton("　")
        swatch.setFixedWidth(34)
        alpha = _spin_float()
        alpha.setRange(0.0, 1.0)
        alpha.setSingleStep(0.01)
        alpha.setValue(a0)
        alpha.setPrefix("A ")
        alpha.setFixedWidth(90)

        def _refresh_swatch():
            swatch.setStyleSheet(f"background-color: {edit.text() or '#FFFFFF'}; border-radius: 6px;")

        def _pick():
            c = QColorDialog.getColor(QColor(edit.text() or "#FFFFFF"))
            if c.isValid():
                edit.setText(c.name())
                _refresh_swatch()

        def _get():
            hx = (edit.text() or "#ffffff").lstrip("#")
            try:
                r = int(hx[0:2], 16) / 255.0
                g = int(hx[2:4], 16) / 255.0
                b = int(hx[4:6], 16) / 255.0
            except (ValueError, IndexError):
                r = g = b = 1.0
            return {"r": r, "g": g, "b": b, "a": alpha.value()}

        def _set(v):
            hx, aa = _obj_to_hex(v)
            edit.setText(hx)
            alpha.setValue(aa)
            _refresh_swatch()

        swatch.clicked.connect(_pick)
        edit.textChanged.connect(_refresh_swatch)
        _refresh_swatch()
        row.addWidget(edit)
        row.addWidget(swatch)
        row.addWidget(alpha)
        return SingleWidget(container, _get, _set)

    if t == "bit":
        # {size, bits: [...]} を簡易テキスト(JSON)で編集 + サイズ表示
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        size = 8
        bits: list = []
        if isinstance(value, dict):
            size = int(value.get("size") or 8)
            bits = list(value.get("bits") or [])
        size_box = _spin_int()
        size_box.setRange(1, 256)
        size_box.setValue(size)
        size_box.setPrefix("size ")
        size_box.setFixedWidth(100)
        edit = QLineEdit(json.dumps(bits))
        edit.setPlaceholderText("選択ビット番号の配列 例: [0, 2, 5]")

        def _get_bit():
            try:
                arr = json.loads(edit.text() or "[]")
                if not isinstance(arr, list):
                    arr = []
            except json.JSONDecodeError:
                arr = []
            return {"size": size_box.value(), "bits": [int(x) for x in arr if isinstance(x, (int, float))]}

        def _set_bit(v):
            if isinstance(v, dict):
                size_box.setValue(int(v.get("size") or 8))
                edit.setText(json.dumps(v.get("bits") or []))
            else:
                edit.setText(json.dumps(v) if v else "[]")

        row.addWidget(size_box)
        row.addWidget(edit, 1)
        return SingleWidget(container, _get_bit, _set_bit)

    if enum_values:
        combo = QComboBox()
        combo.addItem("None", f"{field_type}ID.None")
        for member in enum_values:
            combo.addItem(member, f"{field_type}ID.{member}")
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        return SingleWidget(combo, lambda: combo.currentData(), lambda v: combo.setCurrentIndex(max(0, combo.findData(v))))

    # フォールバック: class_data参照・voice_ref・bezier・dictionary・カスタムクラス等
    # オブジェクトはJSONテキストで編集可能にする
    if isinstance(value, (dict, list)):
        initial = json.dumps(value, ensure_ascii=False)
    else:
        initial = "" if value is None else str(value)
    edit = QLineEdit(initial)
    edit.setPlaceholderText(f"({field_type}) JSON / テキスト簡易編集")

    def _get_fallback():
        text = edit.text().strip()
        if not text:
            return None
        if text.startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return text

    def _set_fallback(v):
        if isinstance(v, (dict, list)):
            edit.setText(json.dumps(v, ensure_ascii=False))
        else:
            edit.setText("" if v is None else str(v))

    return SingleWidget(edit, _get_fallback, _set_fallback)


def _spin_int():
    box = QSpinBox()
    box.setRange(-2_147_483_648, 2_147_483_647)
    return box


def _spin_float():
    box = QDoubleSpinBox()
    box.setRange(-1_000_000_000.0, 1_000_000_000.0)
    box.setDecimals(4)
    return box


class FieldRowWidget(QFrame):
    """1フィールド分の入力行。arraySize==0は単一値、-1は可変長配列、>0は固定長配列。"""

    def __init__(self, field: dict, value: Any, enum_values: Optional[list] = None, parent=None):
        super().__init__(parent)
        self.field = field
        self.array_size = field.get("arraySize", 0) or 0
        self.enum_values = enum_values
        self.setObjectName("Card")
        self.setStyleSheet(f"QFrame#Card {{ background-color: {COLORS['bg_alt']}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        name_lbl = QLabel(field.get("name", ""))
        name_lbl.setStyleSheet("font-weight: 600;")
        header.addWidget(name_lbl)
        if field.get("required", True):
            header.addWidget(make_pill("必須", COLORS["danger"], fg="white"))
        header.addWidget(make_pill(field.get("type", ""), COLORS["surface_hover"], fg=COLORS["text"]))
        header.addStretch()
        outer.addLayout(header)

        if field.get("description"):
            desc = QLabel(field["description"])
            desc.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
            desc.setWordWrap(True)
            outer.addWidget(desc)

        self.body = QVBoxLayout()
        self.body.setSpacing(4)
        outer.addLayout(self.body)

        self._single_slots: list[SingleWidget] = []
        self._dynamic_container: Optional[QVBoxLayout] = None

        if self.array_size == 0:
            sw = build_single_value_widget(field.get("type"), value, enum_values)
            self._single_slots.append(sw)
            self.body.addWidget(sw.widget)
        elif self.array_size > 0:
            vals = value if isinstance(value, list) else get_default_value(field.get("type"), self.array_size)
            for i in range(self.array_size):
                row_val = vals[i] if i < len(vals) else get_default_value(field.get("type"), 0)
                row = QHBoxLayout()
                idx_lbl = QLabel(f"[{i}]")
                idx_lbl.setFixedWidth(28)
                idx_lbl.setStyleSheet(f"color: {COLORS['text_dim']};")
                sw = build_single_value_widget(field.get("type"), row_val, enum_values)
                row.addWidget(idx_lbl)
                row.addWidget(sw.widget, 1)
                wrap = QWidget()
                wrap.setLayout(row)
                self.body.addWidget(wrap)
                self._single_slots.append(sw)
        else:  # dynamic (-1)
            self._dynamic_widgets: list[SingleWidget] = []
            self._dynamic_body = QVBoxLayout()
            self._dynamic_body.setSpacing(4)
            self.body.addLayout(self._dynamic_body)
            vals = value if isinstance(value, list) else []
            for v in vals:
                self._add_dynamic_row(v)
            add_btn = QPushButton("＋ 要素を追加")
            add_btn.clicked.connect(lambda: self._add_dynamic_row(get_default_value(field.get("type"), 0)))
            self.body.addWidget(add_btn)

    def _add_dynamic_row(self, value):
        sw = build_single_value_widget(self.field.get("type"), value, self.enum_values)
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(sw.widget, 1)
        remove_btn = QPushButton("✕")
        remove_btn.setFixedWidth(30)
        remove_btn.setObjectName("Danger")

        def _remove():
            self._dynamic_widgets.remove(sw)
            row_widget.setParent(None)
            row_widget.deleteLater()

        remove_btn.clicked.connect(_remove)
        row.addWidget(remove_btn)
        self._dynamic_body.addWidget(row_widget)
        self._dynamic_widgets.append(sw)

    def get_value(self):
        if self.array_size == 0:
            return self._single_slots[0].get_value()
        if self.array_size > 0:
            return [sw.get_value() for sw in self._single_slots]
        return [sw.get_value() for sw in self._dynamic_widgets]


class RoleDataForm(QWidget):
    """BaseRoleInputForm.js 相当: スキーマ+現在値からデータ入力フォームを組み立てる。"""

    def __init__(self, schema_fields: list, initial_data: list, enum_values_by_type: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.rows: dict[str, FieldRowWidget] = {}
        enum_values_by_type = enum_values_by_type or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        data_by_name = {d.get("name"): d.get("value") for d in (initial_data or []) if isinstance(d, dict)}
        for field in schema_fields:
            name = field.get("name")
            current = data_by_name.get(name, get_default_value(field.get("type"), field.get("arraySize", 0)))
            row = FieldRowWidget(field, current, enum_values_by_type.get(field.get("type")))
            self.rows[name] = row
            layout.addWidget(row)

    def get_data(self) -> list:
        return [{"name": name, "value": row.get_value()} for name, row in self.rows.items()]


# ============================================================
# ページ: ロール定義 (フィールドスキーマ編集) — ScenarioRoleDetailGrid.js 相当
# ============================================================

class FieldEditDialog(QDialog):
    def __init__(self, type_options: list, field: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("フィールドの編集" if field else "フィールドの追加")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        layout.setSpacing(10)
        field = field or {}
        opts = field.get("options") or {}

        self.name_edit = QLineEdit(field.get("name", ""))
        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.addItems(type_options)
        if field.get("type"):
            idx = self.type_combo.findText(field["type"])
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            else:
                self.type_combo.setCurrentText(field["type"])
        self.desc_edit = QLineEdit(field.get("description", ""))
        self.array_edit = _spin_int()
        self.array_edit.setRange(-1, 999)
        self.array_edit.setValue(field.get("arraySize", 0) or 0)
        self.array_edit.setToolTip("0=単一値 / -1=可変長配列 / 1以上=固定長配列")
        self.required_chk = QCheckBox("必須フィールドにする")
        self.required_chk.setChecked(field.get("required", True))

        # bit / bezier / text_list_index 用の簡易オプション
        self.bit_size = _spin_int()
        self.bit_size.setRange(1, 256)
        self.bit_size.setValue(int(opts.get("size") or 8))
        self.bezier_min = _spin_float()
        self.bezier_min.setValue(float(opts.get("min") if opts.get("min") is not None else 0))
        self.bezier_max = _spin_float()
        self.bezier_max.setValue(float(opts.get("max") if opts.get("max") is not None else 1))
        self.matrix_name = QLineEdit(str(opts.get("matrixName") or "ScenarioText"))
        self.field_name_opt = QLineEdit(str(opts.get("fieldName") or "texts"))
        self.preview_lang = QLineEdit(str(opts.get("previewLanguage") or "Ja"))

        layout.addRow("名前 *", self.name_edit)
        layout.addRow("タイプ *", self.type_combo)
        layout.addRow("説明", self.desc_edit)
        layout.addRow("配列サイズ", self.array_edit)
        layout.addRow("", self.required_chk)
        layout.addRow("bit.size", self.bit_size)
        layout.addRow("bezier.min", self.bezier_min)
        layout.addRow("bezier.max", self.bezier_max)
        layout.addRow("text_list matrix", self.matrix_name)
        layout.addRow("text_list field", self.field_name_opt)
        layout.addRow("text_list 言語", self.preview_lang)

        hint = QLabel("※ options はタイプに応じて保存されます (bit / bezier / text_list_index)")
        hint.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        layout.addRow(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.button(QDialogButtonBox.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict:
        t = self.type_combo.currentText().strip()
        result = {
            "name": self.name_edit.text().strip(),
            "type": t,
            "description": self.desc_edit.text().strip(),
            "arraySize": self.array_edit.value(),
            "required": self.required_chk.isChecked(),
        }
        if t == "bit":
            result["options"] = {
                "sizeMode": "manual",
                "size": self.bit_size.value(),
                "mode": "multiple",
                "allowSelectAll": True,
                "flagNames": [f"Flag{i}" for i in range(self.bit_size.value())],
            }
        elif t == "bezier":
            result["options"] = {
                "valueType": "float",
                "min": self.bezier_min.value(),
                "max": self.bezier_max.value(),
            }
        elif t == "text_list_index":
            result["options"] = {
                "matrixName": self.matrix_name.text().strip() or "ScenarioText",
                "fieldName": self.field_name_opt.text().strip() or "texts",
                "previewLanguage": self.preview_lang.text().strip() or "Ja",
            }
        return result


class RoleDetailPage(QWidget):
    """ロールを選んでフィールド定義(スキーマ)を編集する画面。"""

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.current_role: Optional[str] = None
        self.fields: list[dict] = []
        self.branch_type = "General"
        self.type_options: list[str] = BASIC_TYPES + UNITY_TYPES + EXTRA_TYPES
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ロール定義 (フィールドスキーマ)")
        title.setObjectName("PageTitle")
        subtitle = QLabel("ロールを選んでフィールドの型・必須・順序を編集します。")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        picker = QHBoxLayout()
        picker.addWidget(QLabel("ロール名:"))
        self.role_edit = QLineEdit()
        self.role_edit.setPlaceholderText("例: ShowHideCharacter")
        self.role_edit.setFixedWidth(240)
        picker.addWidget(self.role_edit)
        load_btn = QPushButton("読み込み")
        load_btn.clicked.connect(self.load_role)
        picker.addWidget(load_btn)
        picker.addStretch()

        self.branch_pill = make_pill("未読み込み", COLORS["text_dim"])
        picker.addWidget(self.branch_pill)
        root.addLayout(picker)

        actions = QHBoxLayout()
        add_btn = QPushButton("＋ フィールド追加")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self.on_add_field)
        actions.addWidget(add_btn)
        actions.addStretch()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.on_save)
        actions.addWidget(save_btn)
        gen_btn = QPushButton("C#生成")
        gen_btn.clicked.connect(self.on_generate_cs)
        actions.addWidget(gen_btn)
        del_btn = QPushButton("ロール削除")
        del_btn.setObjectName("Danger")
        del_btn.clicked.connect(self.on_delete_role)
        actions.addWidget(del_btn)
        root.addLayout(actions)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["順序", "必須", "名前", "タイプ", "説明", "アクション"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 140)
        self.table.setColumnWidth(5, 190)
        self.table.verticalHeader().setDefaultSectionSize(44)
        root.addWidget(self.table)

        self.api.get_type_options(self._on_type_options, lambda _e: None)

    def _on_type_options(self, opts: dict):
        merged = list(dict.fromkeys(
            BASIC_TYPES + UNITY_TYPES + EXTRA_TYPES
            + opts.get("enum", []) + opts.get("class", []) + opts.get("class_id", [])
            + opts.get("custom_class", []) + opts.get("custom_class_id", []) + opts.get("custom_value", [])
        ))
        self.type_options = merged

    def load_role(self):
        name = self.role_edit.text().strip()
        if not name:
            self._toast("ロール名を入力してください", error=True)
            return
        self.current_role = name
        self.api.get_role_detail(name, self._on_role_loaded, self._on_role_error)

    def _on_role_loaded(self, payload: dict):
        self.fields = payload.get("data", []) or []
        for i, f in enumerate(self.fields):
            f.setdefault("order", i)
            f.setdefault("required", f.get("required", True) is not False)
        self.branch_type = payload.get("branchType", "General")
        color = COLORS["branch_branch"] if self.branch_type == "Branch" else COLORS["branch_general"]
        self.branch_pill.setText(self.branch_type)
        self.branch_pill.setStyleSheet(f"background-color: {color}; color: #0d0e12;")
        self._render_table()
        self._toast(f"「{self.current_role}」を読み込みました")

    def _on_role_error(self, msg: str):
        self._toast(f"読み込みエラー: {msg}", error=True)

    def _render_table(self):
        self.table.setRowCount(0)
        for row_idx, f in enumerate(self.fields):
            r = self.table.rowCount()
            self.table.insertRow(r)

            order_wrap = QWidget()
            order_layout = QHBoxLayout(order_wrap)
            order_layout.setContentsMargins(4, 2, 4, 2)
            up_btn = QPushButton("▲")
            up_btn.setFixedWidth(26)
            down_btn = QPushButton("▼")
            down_btn.setFixedWidth(26)
            up_btn.clicked.connect(lambda _=False, i=row_idx: self._move_field(i, -1))
            down_btn.clicked.connect(lambda _=False, i=row_idx: self._move_field(i, 1))
            order_layout.addWidget(up_btn)
            order_layout.addWidget(down_btn)
            self.table.setCellWidget(r, 0, order_wrap)

            lock_btn = QPushButton("🔒" if f.get("required", True) else "🔓")
            lock_btn.setFixedWidth(36)
            lock_btn.clicked.connect(lambda _=False, i=row_idx: self._toggle_required(i))
            lock_wrap = QWidget()
            lock_layout = QHBoxLayout(lock_wrap)
            lock_layout.setContentsMargins(6, 2, 6, 2)
            lock_layout.addWidget(lock_btn)
            self.table.setCellWidget(r, 1, lock_wrap)

            name_item = QTableWidgetItem(f.get("name", ""))
            font = name_item.font()
            font.setBold(True)
            name_item.setFont(font)
            self.table.setItem(r, 2, name_item)

            type_pill_wrap = QWidget()
            type_layout = QHBoxLayout(type_pill_wrap)
            type_layout.setContentsMargins(6, 4, 6, 4)
            type_layout.addWidget(make_pill(f.get("type", ""), COLORS["surface_hover"], fg=COLORS["text"]))
            type_layout.addStretch()
            self.table.setCellWidget(r, 3, type_pill_wrap)

            self.table.setItem(r, 4, QTableWidgetItem(f.get("description", "")))

            action_wrap = QWidget()
            action_layout = QHBoxLayout(action_wrap)
            action_layout.setContentsMargins(6, 2, 6, 2)
            edit_btn = QPushButton("編集")
            edit_btn.clicked.connect(lambda _=False, i=row_idx: self.on_edit_field(i))
            del_btn = QPushButton("削除")
            del_btn.setObjectName("Danger")
            del_btn.clicked.connect(lambda _=False, i=row_idx: self.on_delete_field(i))
            action_layout.addWidget(edit_btn)
            action_layout.addWidget(del_btn)
            self.table.setCellWidget(r, 5, action_wrap)

    def _move_field(self, index: int, delta: int):
        new_index = index + delta
        if new_index < 0 or new_index >= len(self.fields):
            return
        self.fields[index], self.fields[new_index] = self.fields[new_index], self.fields[index]
        self._render_table()

    def _toggle_required(self, index: int):
        self.fields[index]["required"] = not self.fields[index].get("required", True)
        self._render_table()

    def on_add_field(self):
        if not self.current_role:
            self._toast("先にロールを読み込んでください", error=True)
            return
        dialog = FieldEditDialog(self.type_options, parent=self)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.values()
            if not values["name"] or not values["type"]:
                self._toast("名前とタイプは必須です", error=True)
                return
            values["id"] = len(self.fields) + 1
            self.fields.append(values)
            self._render_table()

    def on_edit_field(self, index: int):
        dialog = FieldEditDialog(self.type_options, self.fields[index], parent=self)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.values()
            self.fields[index].update(values)
            self._render_table()

    def on_delete_field(self, index: int):
        del self.fields[index]
        self._render_table()

    def on_save(self):
        if not self.current_role:
            self._toast("先にロールを読み込んでください", error=True)
            return
        self.api.save_role_detail(
            self.current_role, self.fields, self.branch_type,
            lambda result: self._toast(result.get("message", "保存しました")),
            lambda msg: self._toast(f"保存エラー: {msg}", error=True),
        )

    def on_generate_cs(self):
        if not self.current_role:
            return
        self.api.generate_role_cs(
            self.current_role, self.fields, self.branch_type,
            lambda result: self._toast(result.get("message", "C#を生成しました")),
            lambda msg: self._toast(f"生成エラー: {msg}", error=True),
        )

    def on_delete_role(self):
        if not self.current_role:
            return
        confirm = QMessageBox.question(
            self, "確認", f"ロール「{self.current_role}」を削除しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.api.delete_role(
            self.current_role,
            lambda result: self._toast(result.get("message", "削除しました")),
            lambda msg: self._toast(f"削除エラー: {msg}", error=True),
        )

    def _toast(self, message: str, error: bool = False):
        main_window = self.window()
        if hasattr(main_window, "show_status"):
            main_window.show_status(message, error=error)


# ============================================================
# ページ: ストーリー設定 — ScenarioStorySettingGrid.js 相当 (簡易版)
# ============================================================

STORY_SLOT_KINDS = ["img", "se", "bgm", "effect", "voice"]


class StorySettingPage(QWidget):
    """イベント/Subを指定して、img/se/bgm/effect/voiceのスロットにアセットを割り当てる。"""

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.slot_defs: list[dict] = []
        self.slot_rows: dict[str, QComboBox] = {}
        self.retain_boxes: dict[str, QCheckBox] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ストーリー設定")
        title.setObjectName("PageTitle")
        subtitle = QLabel("イベント/Subごとの画像・SE・BGM・エフェクト・ボイススロットを設定します。")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        picker = QHBoxLayout()
        picker.addWidget(QLabel("イベントID:"))
        self.event_edit = QLineEdit()
        self.event_edit.setFixedWidth(100)
        picker.addWidget(self.event_edit)
        picker.addWidget(QLabel("SubID:"))
        self.sub_edit = QLineEdit()
        self.sub_edit.setFixedWidth(100)
        picker.addWidget(self.sub_edit)
        load_btn = QPushButton("読み込み")
        load_btn.clicked.connect(self.load)
        picker.addWidget(load_btn)
        picker.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self.save)
        picker.addWidget(save_btn)
        root.addLayout(picker)

        gen_row = QHBoxLayout()
        gen_btn = QPushButton("バイナリ生成")
        gen_btn.clicked.connect(lambda: self.api.generate_story_setting(
            lambda r: self._toast(r.get("message", "生成しました")),
            lambda m: self._toast(f"生成エラー: {m}", error=True),
        ))
        gen_voice_btn = QPushButton("Voiceロール生成")
        gen_voice_btn.clicked.connect(lambda: self.api.generate_voice_role(
            lambda r: self._toast(r.get("message", "生成しました")),
            lambda m: self._toast(f"生成エラー: {m}", error=True),
        ))
        gen_row.addWidget(gen_btn)
        gen_row.addWidget(gen_voice_btn)
        gen_row.addStretch()
        root.addLayout(gen_row)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.kind_lists: dict[str, QVBoxLayout] = {}
        for kind in STORY_SLOT_KINDS:
            page = QWidget()
            box = QVBoxLayout(page)
            box.setContentsMargins(12, 12, 12, 12)
            box.setSpacing(8)
            box.addStretch()
            self.kind_lists[kind] = box
            self.tabs.addTab(page, kind)

        self.api.get_story_slot_defs(self._on_slot_defs, lambda _e: None)

    def _on_slot_defs(self, defs):
        self.slot_defs = defs if isinstance(defs, list) else []
        self._render_slots({})

    def _render_slots(self, current_by_slot: dict):
        for kind, layout in self.kind_lists.items():
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self.slot_rows.clear()
        self.retain_boxes.clear()

        by_kind: dict[str, list] = {k: [] for k in STORY_SLOT_KINDS}
        for d in self.slot_defs:
            kind = d.get("kind", "img")
            by_kind.setdefault(kind, []).append(d)

        for kind, defs in by_kind.items():
            layout = self.kind_lists.get(kind)
            if layout is None:
                continue
            for d in defs:
                slot_name = d.get("slot", "")
                row_widget = QFrame()
                row_widget.setObjectName("Card")
                row = QHBoxLayout(row_widget)
                row.setContentsMargins(12, 8, 12, 8)
                lbl = QLabel(slot_name)
                lbl.setFixedWidth(160)
                lbl.setStyleSheet("font-weight: 600;")
                combo = QComboBox()
                combo.setEditable(True)
                combo.addItem("(未設定)", "")
                current = current_by_slot.get(slot_name, {})
                cur_id = current.get("id", "")
                if cur_id:
                    combo.addItem(str(cur_id), cur_id)
                    combo.setCurrentIndex(1)
                retain_chk = QCheckBox("保持(retain)")
                retain_chk.setChecked(bool(current.get("retain", False)))
                row.addWidget(lbl)
                row.addWidget(combo, 1)
                row.addWidget(retain_chk)
                layout.addWidget(row_widget)
                self.slot_rows[slot_name] = combo
                self.retain_boxes[slot_name] = retain_chk
            layout.addStretch()

    def load(self):
        event_id = self.event_edit.text().strip()
        sub_id = self.sub_edit.text().strip()
        if not event_id or not sub_id:
            self._toast("イベントIDとSubIDを入力してください", error=True)
            return
        self.api.get_story_setting(event_id, sub_id, self._on_loaded, self._on_error)

    def _on_loaded(self, payload):
        slots = payload.get("slots", []) if isinstance(payload, dict) else []
        current_by_slot = {s.get("slot"): s for s in slots if isinstance(s, dict)}
        self._render_slots(current_by_slot)
        self._toast("読み込みました")

    def _on_error(self, msg):
        self._toast(f"読み込みエラー: {msg}", error=True)

    def save(self):
        event_id = self.event_edit.text().strip()
        sub_id = self.sub_edit.text().strip()
        if not event_id or not sub_id:
            self._toast("イベントIDとSubIDを入力してください", error=True)
            return
        slots = []
        for slot_name, combo in self.slot_rows.items():
            slots.append({
                "slot": slot_name,
                "id": combo.currentData() or combo.currentText(),
                "retain": self.retain_boxes[slot_name].isChecked(),
            })
        self.api.save_story_setting(
            event_id, sub_id, {"slots": slots},
            lambda r: self._toast(r.get("message", "保存しました")),
            lambda m: self._toast(f"保存エラー: {m}", error=True),
        )

    def _toast(self, message: str, error: bool = False):
        main_window = self.window()
        if hasattr(main_window, "show_status"):
            main_window.show_status(message, error=error)


# ============================================================
# ページ: イベント一覧 — ScenarioEventGrid.js 相当
# ============================================================

class EventsPage(QWidget):
    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.events: list[dict] = []
        self._build_ui()
        self.reload()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("シナリオイベント")
        title.setObjectName("PageTitle")
        subtitle = QLabel("イベントとSub(サブイベント)の一覧。行を選ぶとSubが表示されます。")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        reload_btn = QPushButton("再読み込み")
        reload_btn.clicked.connect(self.reload)
        header.addWidget(reload_btn)
        add_btn = QPushButton("＋ イベント追加")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self.on_add_event)
        header.addWidget(add_btn)
        root.addLayout(header)

        utility_row = QHBoxLayout()
        for label, fn in [
            ("全イベント修正", self.api.fix_all_events),
            ("全イベントバイナリ生成", self.api.generate_all_event_bin),
            ("レガシー移行", self.api.migrate_legacy_events),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, f=fn: f(
                lambda r: (self._toast(r.get("message", "完了しました")), self.reload()),
                lambda m: self._toast(f"エラー: {m}", error=True),
            ))
            utility_row.addWidget(btn)
        utility_row.addStretch()
        root.addLayout(utility_row)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        self.event_table = QTableWidget(0, 4)
        self.event_table.setHorizontalHeaderLabels(["ID", "名前", "Sub数", "操作"])
        self.event_table.setAlternatingRowColors(True)
        self.event_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.event_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.event_table.verticalHeader().setVisible(False)
        self.event_table.setShowGrid(False)
        self.event_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.event_table.verticalHeader().setDefaultSectionSize(44)
        self.event_table.itemSelectionChanged.connect(self._on_event_selected)
        splitter.addWidget(self.event_table)

        sub_panel = QWidget()
        sub_layout = QVBoxLayout(sub_panel)
        sub_header = QHBoxLayout()
        sub_title = QLabel("Sub一覧")
        sub_title.setStyleSheet("font-weight: 700;")
        sub_header.addWidget(sub_title)
        sub_header.addStretch()
        self.add_sub_btn = QPushButton("＋ Sub追加")
        self.add_sub_btn.clicked.connect(self.on_add_sub)
        self.add_sub_btn.setEnabled(False)
        sub_header.addWidget(self.add_sub_btn)
        sub_layout.addLayout(sub_header)

        self.sub_table = QTableWidget(0, 3)
        self.sub_table.setHorizontalHeaderLabels(["SubID", "名前", "操作"])
        self.sub_table.setAlternatingRowColors(True)
        self.sub_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sub_table.verticalHeader().setVisible(False)
        self.sub_table.setShowGrid(False)
        self.sub_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        sub_layout.addWidget(self.sub_table)
        splitter.addWidget(sub_panel)
        splitter.setSizes([550, 450])

    def reload(self):
        self.api.get_events(self._on_loaded, self._on_error)

    def _on_loaded(self, data):
        self.events = data if isinstance(data, list) else []
        self._render_events()

    def _on_error(self, msg):
        self.events = []
        self._render_events()
        self._toast(f"取得エラー: {msg}", error=True)

    def _render_events(self):
        self.event_table.setRowCount(0)
        for ev in self.events:
            r = self.event_table.rowCount()
            self.event_table.insertRow(r)
            self.event_table.setItem(r, 0, QTableWidgetItem(str(ev.get("id", ""))))
            name_item = QTableWidgetItem(ev.get("name", "不明"))
            font = name_item.font()
            font.setBold(True)
            name_item.setFont(font)
            self.event_table.setItem(r, 1, name_item)
            subs = ev.get("subs", []) or []
            self.event_table.setItem(r, 2, QTableWidgetItem(str(len(subs))))

            action_wrap = QWidget()
            action_layout = QHBoxLayout(action_wrap)
            action_layout.setContentsMargins(6, 2, 6, 2)
            copy_btn = QPushButton("複製")
            copy_btn.clicked.connect(lambda _=False, eid=ev.get("id"): self.api.copy_event(
                eid, lambda r: (self._toast(r.get("message", "複製しました")), self.reload()),
                lambda m: self._toast(f"複製エラー: {m}", error=True),
            ))
            del_btn = QPushButton("削除")
            del_btn.setObjectName("Danger")
            del_btn.clicked.connect(lambda _=False, eid=ev.get("id"): self.on_delete_event(eid))
            action_layout.addWidget(copy_btn)
            action_layout.addWidget(del_btn)
            self.event_table.setCellWidget(r, 3, action_wrap)

    def _on_event_selected(self):
        rows = self.event_table.selectionModel().selectedRows()
        self.sub_table.setRowCount(0)
        if not rows:
            self.add_sub_btn.setEnabled(False)
            return
        idx = rows[0].row()
        if idx >= len(self.events):
            return
        self.add_sub_btn.setEnabled(True)
        event = self.events[idx]
        for sub in event.get("subs", []) or []:
            r = self.sub_table.rowCount()
            self.sub_table.insertRow(r)
            self.sub_table.setItem(r, 0, QTableWidgetItem(str(sub.get("id", ""))))
            self.sub_table.setItem(r, 1, QTableWidgetItem(sub.get("name", "")))
            action_wrap = QWidget()
            action_layout = QHBoxLayout(action_wrap)
            action_layout.setContentsMargins(6, 2, 6, 2)
            copy_btn = QPushButton("複製")
            eid, sid = event.get("id"), sub.get("id")
            copy_btn.clicked.connect(lambda _=False, e=eid, s=sid: self.api.copy_sub(
                e, s, lambda r: (self._toast(r.get("message", "複製しました")), self.reload()),
                lambda m: self._toast(f"複製エラー: {m}", error=True),
            ))
            del_btn = QPushButton("削除")
            del_btn.setObjectName("Danger")
            del_btn.clicked.connect(lambda _=False, e=eid, s=sid: self.on_delete_sub(e, s))
            action_layout.addWidget(copy_btn)
            action_layout.addWidget(del_btn)
            self.sub_table.setCellWidget(r, 2, action_wrap)

    def on_add_event(self):
        name, ok = self._prompt("新しいイベント", "イベント名:")
        if ok and name:
            self.api.create_event(
                {"name": name},
                lambda r: (self._toast(r.get("message", "作成しました")), self.reload()),
                lambda m: self._toast(f"作成エラー: {m}", error=True),
            )

    def on_add_sub(self):
        rows = self.event_table.selectionModel().selectedRows()
        if not rows:
            return
        event = self.events[rows[0].row()]
        name, ok = self._prompt("新しいSub", "Sub名:")
        if ok and name:
            self.api.add_sub(
                event.get("id"), {"name": name},
                lambda r: (self._toast(r.get("message", "作成しました")), self.reload()),
                lambda m: self._toast(f"作成エラー: {m}", error=True),
            )

    def on_delete_event(self, event_id):
        confirm = QMessageBox.question(self, "確認", f"イベント {event_id} を削除しますか？",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.api.delete_event(
            event_id,
            lambda r: (self._toast(r.get("message", "削除しました")), self.reload()),
            lambda m: self._toast(f"削除エラー: {m}", error=True),
        )

    def on_delete_sub(self, event_id, sub_id):
        confirm = QMessageBox.question(self, "確認", f"Sub {sub_id} を削除しますか？",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.api.delete_sub(
            event_id, sub_id,
            lambda r: (self._toast(r.get("message", "削除しました")), self.reload()),
            lambda m: self._toast(f"削除エラー: {m}", error=True),
        )

    def _prompt(self, title, label):
        from PySide6.QtWidgets import QInputDialog
        return QInputDialog.getText(self, title, label)

    def _toast(self, message: str, error: bool = False):
        main_window = self.window()
        if hasattr(main_window, "show_status"):
            main_window.show_status(message, error=error)


# ============================================================
# ページ: ノード/ロールデータ入力 — ScenarioEventTransition.js の
#   「データ入力」部分のみを移植 (ドラッグ&ドロップの視覚的ツリー編集は対象外)
# ============================================================

class TransitionDataPage(QWidget):
    """イベント/Subを指定してノードツリーを閲覧し、ノードに紐づくロールの
    実データをBaseRoleInputForm相当のフォームで入力・保存する。
    ※ ノードの追加/移動などの視覚的な編集(ScenarioEventTransition.jsの
      ドラッグ&ドロップキャンバス)は対象外。あくまで「データ入力」に特化。
    """

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.event_id = None
        self.sub_id = None
        self.tree_data = None
        self._node_by_item = {}
        self._current_node = None
        self._current_form: Optional[RoleDataForm] = None
        self._current_role_meta = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ノード・ロールデータ入力")
        title.setObjectName("PageTitle")
        subtitle = QLabel("イベント/Subのノードツリーからロールを選び、フィールド値を入力します。")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        picker = QHBoxLayout()
        picker.addWidget(QLabel("イベントID:"))
        self.event_edit = QLineEdit()
        self.event_edit.setFixedWidth(100)
        picker.addWidget(self.event_edit)
        picker.addWidget(QLabel("SubID:"))
        self.sub_edit = QLineEdit()
        self.sub_edit.setFixedWidth(100)
        picker.addWidget(self.sub_edit)
        load_btn = QPushButton("ツリー読み込み")
        load_btn.clicked.connect(self.load_tree)
        picker.addWidget(load_btn)
        picker.addStretch()
        root.addLayout(picker)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["ノード / ロール"])
        self.tree.itemClicked.connect(self._on_item_clicked)
        splitter.addWidget(self.tree)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.form_title = QLabel("ロールを選択してください")
        self.form_title.setStyleSheet("font-weight: 700;")
        right_layout.addWidget(self.form_title)

        from PySide6.QtWidgets import QScrollArea
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.form_container = QWidget()
        self.form_container_layout = QVBoxLayout(self.form_container)
        self.form_container_layout.addStretch()
        self.scroll.setWidget(self.form_container)
        right_layout.addWidget(self.scroll, 1)

        self.save_form_btn = QPushButton("このロールのデータを保存")
        self.save_form_btn.setObjectName("Primary")
        self.save_form_btn.setEnabled(False)
        self.save_form_btn.clicked.connect(self.save_current_form)
        right_layout.addWidget(self.save_form_btn)

        splitter.addWidget(right_panel)
        splitter.setSizes([420, 580])

    def load_tree(self):
        self.event_id = self.event_edit.text().strip()
        self.sub_id = self.sub_edit.text().strip()
        if not self.event_id or not self.sub_id:
            self._toast("イベントIDとSubIDを入力してください", error=True)
            return
        self.api.get_transition(self.event_id, self.sub_id, self._on_tree_loaded, self._on_tree_error)

    def _on_tree_error(self, msg):
        self._toast(f"読み込みエラー: {msg}", error=True)

    def _on_tree_loaded(self, data):
        self.tree_data = data if isinstance(data, dict) else {"nodes": []}
        self._render_tree()
        self._toast("ツリーを読み込みました")

    def _render_tree(self):
        from PySide6.QtWidgets import QTreeWidgetItem
        self.tree.clear()
        self._node_by_item.clear()
        nodes = (self.tree_data or {}).get("nodes", [])
        for node in nodes:
            self._add_node_item(self.tree, node)
        self.tree.expandAll()

    def _add_node_item(self, parent, node: dict):
        from PySide6.QtWidgets import QTreeWidgetItem
        data = node.get("data", {}) or {}
        label = data.get("label") or node.get("id", "?")
        is_sub_group = bool(data.get("isSubGroup"))
        item = QTreeWidgetItem([f"{'📁' if is_sub_group else '🔹'} {label}  (id={node.get('id')})"])
        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)
        self._node_by_item[id(item)] = ("node", node)

        for role in data.get("roles", []) or []:
            role_item = QTreeWidgetItem([f"👤 {role.get('name', role.get('id'))}"])
            item.addChild(role_item)
            self._node_by_item[id(role_item)] = ("role", (node, role))

        subgroups = data.get("subgroups", {}) or {}
        for sg_id, sg in subgroups.items():
            for child_node in (sg.get("nodes", []) or []):
                self._add_node_item(item, child_node)
        return item

    def _on_item_clicked(self, item, _column):
        entry = self._node_by_item.get(id(item))
        if not entry:
            return
        kind, payload = entry
        if kind != "role":
            return
        node, role = payload
        self._current_node = node
        self._current_role_meta = role
        role_name = role.get("name") or role.get("id")
        self.form_title.setText(f"{role_name}  ({role.get('uniqueId', '')})")
        self.api.get_role_form_schema(role_name, self._on_schema_loaded, self._on_schema_error)

    def _on_schema_error(self, msg):
        self._toast(f"スキーマ取得エラー: {msg}", error=True)

    def _on_schema_loaded(self, schema):
        if not isinstance(schema, dict) or schema.get("error"):
            self._toast(f"スキーマエラー: {(schema or {}).get('error', '不明')}", error=True)
            return
        fields = schema.get("fields", []) or []
        initial_data = self._current_role_meta.get("data", []) or []

        while self.form_container_layout.count():
            item = self.form_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._current_form = RoleDataForm(fields, initial_data)
        self.form_container_layout.addWidget(self._current_form)
        self.form_container_layout.addStretch()
        self.save_form_btn.setEnabled(True)

    def save_current_form(self):
        if not (self._current_form and self._current_node and self._current_role_meta):
            return
        data = self._current_form.get_data()
        unique_id = self._current_role_meta.get("uniqueId")
        node_id = self._current_node.get("id")
        self.api.save_role_instance_data(
            self.event_id, self.sub_id, node_id, unique_id, data,
            lambda r: self._toast(r.get("message", "保存しました")),
            lambda m: self._toast(f"保存エラー: {m}", error=True),
        )

    def _toast(self, message: str, error: bool = False):
        main_window = self.window()
        if hasattr(main_window, "show_status"):
            main_window.show_status(message, error=error)


# ============================================================
# メインウィンドウ
# ============================================================

class BusyOverlay(QWidget):
    """保存・バイナリ生成中にメインUIを覆い、操作できないようにする半透明オーバーレイ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet(
            f"background-color: rgba(10, 12, 20, 180); color: {COLORS['text']};"
        )
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.label = QLabel("処理中…")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 16px; font-weight: 600; background: transparent;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # indeterminate
        self.bar.setFixedWidth(280)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']};"
            f" border-radius: 6px; height: 10px; }}"
            f"QProgressBar::chunk {{ background: {COLORS['accent']}; border-radius: 5px; }}"
        )
        layout.addWidget(self.label)
        layout.addWidget(self.bar, 0, Qt.AlignCenter)
        self.hide()

    def show_message(self, message: str):
        self.label.setText(message or "処理中…")
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scenario Toolkit")
        self.resize(1180, 760)
        ensure_data_dir()
        self.api = ApiClient()
        self._busy = False

        # ルート: 中央コンテンツ + オーバーレイ用のスタック
        root_central = QWidget()
        self.setCentralWidget(root_central)
        root_layout = QVBoxLayout(root_central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        content = QWidget()
        outer = QHBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- 左サイドナビ ---
        self.nav = QListWidget()
        self.nav.setObjectName("NavList")
        self.nav.setFixedWidth(220)
        self.nav.setSpacing(2)
        nav_labels = [
            "🗂  ロール一覧",
            "🧬  ロール定義",
            "📥  データ入力",
            "🎬  イベント一覧",
            "🎨  ストーリー設定",
            "📝  トランザクションDSL",
            "🔀  条件",
        ]
        for label in nav_labels:
            item = QListWidgetItem(label)
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        outer.addWidget(self.nav)

        # --- 右ページスタック ---
        self.stack = QStackedWidget()
        self.role_page = RoleListPage(self.api)
        self.role_detail_page = RoleDetailPage(self.api)
        self.transition_page = TransitionDataPage(self.api)
        self.events_page = EventsPage(self.api)
        self.story_setting_page = StorySettingPage(self.api)
        self.dsl_page = DslEditorPage()
        self.conditions_page = ConditionsPage()
        for page in [
            self.role_page, self.role_detail_page, self.transition_page,
            self.events_page, self.story_setting_page, self.dsl_page, self.conditions_page,
        ]:
            self.stack.addWidget(page)
        outer.addWidget(self.stack, 1)

        root_layout.addWidget(content, 1)

        # 半透明オーバーレイ (content 全体を覆う)
        self.busy_overlay = BusyOverlay(root_central)
        self.busy_overlay.hide()

        self.nav.setCurrentRow(0)

        self._build_toolbar()

        # ステータスバー (常時表示 + 進行状況)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_message_label = QLabel("")
        self.status_message_label.setStyleSheet(f"color: {COLORS['text_dim']}; padding-left: 8px;")
        self.status.addWidget(self.status_message_label, 1)
        self.busy_pill = make_pill("待機中", COLORS["success"], fg="#0d0e12")
        self.status.addPermanentWidget(self.busy_pill)
        self.connection_pill = make_pill("未接続", COLORS["text_dim"], fg="#0d0e12")
        self.status.addPermanentWidget(self.connection_pill)
        self.data_path_label = QLabel(f"設定: {SETTINGS_PATH}")
        self.data_path_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; padding-right: 8px;")
        self.status.addPermanentWidget(self.data_path_label)

        # API の busy コールバックを接続
        self.api.on_busy_start = self.set_busy
        self.api.on_busy_end = self.clear_busy

        self.show_status(f"接続先: {self.api.base_url} ／ 設定ディレクトリ: {DATA_DIR}")
        self.connection_pill.setText("待機中")
        self.connection_pill.setStyleSheet(f"background-color: {COLORS['success']}; color: #0d0e12;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.busy_overlay.isVisible():
            self.busy_overlay.setGeometry(self.centralWidget().rect())

    def set_busy(self, message: str = "処理中…"):
        """保存・生成中は UI を操作不可にする。"""
        self._busy = True
        self.busy_overlay.show_message(message)
        self.nav.setEnabled(False)
        self.stack.setEnabled(False)
        if hasattr(self, "url_edit"):
            self.url_edit.setEnabled(False)
        if hasattr(self, "connect_btn"):
            self.connect_btn.setEnabled(False)
        self.busy_pill.setText("処理中")
        self.busy_pill.setStyleSheet(f"background-color: {COLORS['warning']}; color: #0d0e12;")
        self.status_message_label.setText(message)
        self.status.showMessage(message)

    def clear_busy(self):
        self._busy = False
        self.busy_overlay.hide()
        self.nav.setEnabled(True)
        self.stack.setEnabled(True)
        if hasattr(self, "url_edit"):
            self.url_edit.setEnabled(True)
        if hasattr(self, "connect_btn"):
            self.connect_btn.setEnabled(True)
        self.busy_pill.setText("待機中")
        self.busy_pill.setStyleSheet(f"background-color: {COLORS['success']}; color: #0d0e12;")

    def _build_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        logo = QLabel("✦ Scenario Toolkit")
        logo.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text']}; padding-right: 12px;")
        toolbar.addWidget(logo)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        toolbar.addWidget(QLabel("APIサーバー:"))
        self.url_edit = QLineEdit(self.api.base_url)
        self.url_edit.setFixedWidth(240)
        toolbar.addWidget(self.url_edit)

        self.connect_btn = QPushButton("接続")
        self.connect_btn.setObjectName("Primary")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        toolbar.addWidget(self.connect_btn)

    def _on_connect_clicked(self):
        self.api.set_base_url(self.url_edit.text().strip() or DEFAULT_BASE_URL)
        self.show_status(f"接続先を更新しました: {self.api.base_url} (設定を {SETTINGS_PATH} に保存)")
        self.connection_pill.setText("接続済")
        self.connection_pill.setStyleSheet(f"background-color: {COLORS['accent']}; color: white;")
        self.role_page.reload()
        self.events_page.reload()

    def _on_nav_changed(self, index: int):
        if self._busy:
            return
        self.stack.setCurrentIndex(index)

    def show_status(self, message: str, error: bool = False):
        self.status_message_label.setText(message)
        self.status.showMessage(message, 8000 if not error else 12000)
        if error:
            self.connection_pill.setText("エラー")
            self.connection_pill.setStyleSheet(f"background-color: {COLORS['danger']}; color: white;")
        elif not self._busy:
            self.connection_pill.setText("待機中")
            self.connection_pill.setStyleSheet(f"background-color: {COLORS['success']}; color: #0d0e12;")


def main():
    ensure_data_dir()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
