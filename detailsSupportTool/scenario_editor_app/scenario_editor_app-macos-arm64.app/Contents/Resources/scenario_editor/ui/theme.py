"""ダーク / ライトのテーマ (QSS)。色は TOKENS に集約し、ウィジェット側は ``color(name)`` で引く。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication

TOKENS = {
    "dark": {
        "bg0": "#0f1218", "bg1": "#151922", "bg2": "#1b202b", "bg3": "#242a37", "bg4": "#2d3544",
        "border": "#2b3240", "border2": "#3a4357",
        "text": "#e8ebf2", "muted": "#8f99ae", "faint": "#5d667a",
        "accent": "#7aa2ff", "accentFg": "#0a1020", "accentSoft": "#1d2a4a",
        "ok": "#4cc38a", "okSoft": "#143225", "warn": "#f2b84b", "warnSoft": "#3a2d12",
        "err": "#ef6b73", "errSoft": "#3b1a1f", "info": "#5ec2e8", "infoSoft": "#12303b",
        "wait": "#f2b84b", "scrim": "rgba(5,8,14,150)",
    },
    "light": {
        "bg0": "#eef0f5", "bg1": "#f8f9fc", "bg2": "#ffffff", "bg3": "#eceff5", "bg4": "#e1e5ee",
        "border": "#d8dce7", "border2": "#bfc6d6",
        "text": "#1b2130", "muted": "#667089", "faint": "#99a1b5",
        "accent": "#3558d8", "accentFg": "#ffffff", "accentSoft": "#e3e9fc",
        "ok": "#1f9d68", "okSoft": "#dff4ea", "warn": "#b9770e", "warnSoft": "#fbefd5",
        "err": "#d6414c", "errSoft": "#fbe3e5", "info": "#1d89b3", "infoSoft": "#def1f8",
        "wait": "#d98a00", "scrim": "rgba(20,26,40,110)",
    },
}

# ノード背景色プリセットの表示にも使う、見出し用フォント
UI_FONTS = ["Yu Gothic UI", "Meiryo UI", "Hiragino Sans", "Noto Sans CJK JP", "Segoe UI", "Helvetica Neue", "sans-serif"]
MONO_FONTS = ["Cascadia Mono", "Consolas", "SF Mono", "Menlo", "Noto Sans Mono CJK JP", "monospace"]

_current = "dark"


def current_theme() -> str:
    return _current


def color(name: str, theme: str | None = None) -> str:
    return TOKENS[theme or _current][name]


def qcolor(name: str, theme: str | None = None) -> QColor:
    return QColor(color(name, theme))


def mono_font(size: int = 10) -> QFont:
    f = QFont()
    f.setFamilies(MONO_FONTS)
    f.setPointSize(size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def build_qss(theme: str) -> str:
    t = TOKENS[theme]
    return f"""
* {{ outline: 0; }}
QWidget {{ background: transparent; color: {t['text']}; }}
QMainWindow, QDialog, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {t['bg0']}; }}
QDialog {{ background: {t['bg1']}; }}
QToolTip {{ background: {t['bg4']}; color: {t['text']}; border: 1px solid {t['border2']}; padding: 4px 8px; }}

QLabel[role="title"] {{ font-size: 20px; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: 15px; font-weight: 700; }}
QLabel[role="muted"] {{ color: {t['muted']}; }}
QLabel[role="faint"] {{ color: {t['faint']}; }}
QLabel[role="mono"] {{ font-family: "Cascadia Mono", Consolas, Menlo, monospace; }}

QFrame[card="true"] {{ background: {t['bg2']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QFrame[card="flat"] {{ background: {t['bg1']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QFrame[sidebar="true"] {{ background: {t['bg1']}; border-right: 1px solid {t['border']}; }}
QFrame[toolbar="true"] {{ background: {t['bg1']}; border-bottom: 1px solid {t['border']}; }}
QFrame[drawer="true"] {{ background: {t['bg1']}; border-left: 1px solid {t['border2']}; }}
QFrame#scrim {{ background: {t['scrim']}; }}
QFrame[sep="h"] {{ background: {t['border']}; max-height: 1px; min-height: 1px; border: none; }}
QFrame[sep="v"] {{ background: {t['border']}; max-width: 1px; min-width: 1px; border: none; }}

QPushButton {{ background: {t['bg3']}; border: 1px solid {t['border']}; border-radius: 7px; padding: 6px 13px; }}
QPushButton:hover {{ background: {t['bg4']}; border-color: {t['border2']}; }}
QPushButton:pressed {{ background: {t['bg2']}; }}
QPushButton:disabled {{ color: {t['faint']}; background: {t['bg2']}; border-color: {t['border']}; }}
QPushButton:focus {{ border-color: {t['accent']}; }}
QPushButton[variant="primary"] {{ background: {t['accent']}; color: {t['accentFg']}; border-color: {t['accent']}; font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {t['accent']}; border-color: {t['text']}; }}
QPushButton[variant="primary"]:disabled {{ background: {t['bg4']}; color: {t['faint']}; border-color: {t['border']}; }}
QPushButton[variant="danger"] {{ background: transparent; color: {t['err']}; border-color: {t['err']}; }}
QPushButton[variant="danger"]:hover {{ background: {t['errSoft']}; }}
QPushButton[variant="ghost"] {{ background: transparent; border-color: transparent; }}
QPushButton[variant="ghost"]:hover {{ background: {t['bg3']}; }}
QPushButton[variant="ok"] {{ background: {t['ok']}; color: {t['accentFg']}; border-color: {t['ok']}; font-weight: 600; }}
QPushButton[variant="warn"] {{ background: transparent; color: {t['warn']}; border-color: {t['warn']}; }}
QPushButton[variant="warn"]:hover {{ background: {t['warnSoft']}; }}
QPushButton[variant="small"] {{ padding: 3px 9px; font-size: 12px; border-radius: 6px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: {t['bg3']}; }}
QToolButton:checked {{ background: {t['accentSoft']}; border-color: {t['accent']}; }}
QToolButton:disabled {{ opacity: .4; }}
QToolButton::menu-indicator {{ image: none; }}

QPushButton[nav="true"] {{ text-align: left; background: transparent; border: none; border-radius: 8px; padding: 9px 12px; color: {t['muted']}; font-weight: 600; }}
QPushButton[nav="true"]:hover {{ background: {t['bg3']}; color: {t['text']}; }}
QPushButton[nav="true"]:checked {{ background: {t['accentSoft']}; color: {t['accent']}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
  background: {t['bg3']}; border: 1px solid {t['border']}; border-radius: 7px; padding: 5px 8px;
  selection-background-color: {t['accent']}; selection-color: {t['accentFg']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {t['faint']}; background: {t['bg2']}; }}
QLineEdit[invalid="true"] {{ border-color: {t['err']}; }}
QLineEdit[flat="true"] {{ background: transparent; border: 1px solid transparent; }}
QLineEdit[flat="true"]:hover {{ border-color: {t['border']}; }}
QLineEdit[flat="true"]:focus {{ background: {t['bg3']}; border-color: {t['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {t['bg2']}; border: 1px solid {t['border2']}; selection-background-color: {t['accentSoft']}; selection-color: {t['text']}; outline: 0; padding: 3px; }}

QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t['border2']}; border-radius: 4px; background: {t['bg3']}; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}
QCheckBox::indicator:disabled {{ background: {t['bg2']}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {t['border2']}; border-radius: 8px; background: {t['bg3']}; }}
QRadioButton::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['bg4']}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {t['border2']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['bg4']}; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}

QTabBar::tab {{ background: transparent; color: {t['muted']}; padding: 7px 14px; border: none; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:hover {{ color: {t['text']}; }}
QTabBar::tab:selected {{ color: {t['accent']}; border-bottom-color: {t['accent']}; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {t['border']}; }}

QMenu {{ background: {t['bg2']}; border: 1px solid {t['border2']}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t['accentSoft']}; }}
QMenu::item:disabled {{ color: {t['faint']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}

QTableWidget, QTableView, QListWidget, QTreeWidget {{ background: {t['bg2']}; alternate-background-color: {t['bg1']}; border: 1px solid {t['border']}; border-radius: 8px; gridline-color: {t['border']}; selection-background-color: {t['accentSoft']}; selection-color: {t['text']}; }}
QTableWidget::item {{ padding: 4px 6px; border: none; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: {t['accentSoft']}; }}
QListWidget::item {{ padding: 5px 8px; border-radius: 5px; }}
QListWidget::item:hover {{ background: {t['bg3']}; }}
QHeaderView::section {{ background: {t['bg1']}; color: {t['muted']}; border: none; border-bottom: 1px solid {t['border']}; padding: 6px 8px; font-weight: 600; }}

QGroupBox {{ border: 1px solid {t['border']}; border-radius: 8px; margin-top: 12px; padding: 12px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; color: {t['muted']}; }}

QSlider::groove:horizontal {{ height: 4px; background: {t['bg4']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t['accent']}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QProgressBar {{ background: {t['bg3']}; border: none; border-radius: 4px; height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}
QSplitter::handle {{ background: {t['border']}; }}
QStatusBar {{ background: {t['bg1']}; border-top: 1px solid {t['border']}; color: {t['muted']}; }}

QLabel[chip="true"] {{ background: {t['bg3']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 1px 9px; font-size: 12px; }}
QLabel[chip="accent"] {{ background: {t['accentSoft']}; color: {t['accent']}; border: 1px solid {t['accent']}; border-radius: 10px; padding: 1px 9px; font-size: 12px; }}
QLabel[chip="ok"] {{ background: {t['okSoft']}; color: {t['ok']}; border: 1px solid {t['ok']}; border-radius: 10px; padding: 1px 9px; font-size: 12px; }}
QLabel[chip="warn"] {{ background: {t['warnSoft']}; color: {t['warn']}; border: 1px solid {t['warn']}; border-radius: 10px; padding: 1px 9px; font-size: 12px; }}
QLabel[chip="err"] {{ background: {t['errSoft']}; color: {t['err']}; border: 1px solid {t['err']}; border-radius: 10px; padding: 1px 9px; font-size: 12px; }}
QLabel[chip="info"] {{ background: {t['infoSoft']}; color: {t['info']}; border: 1px solid {t['info']}; border-radius: 10px; padding: 1px 9px; font-size: 12px; }}
QLabel[chip="mono"] {{ background: {t['bg3']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 1px 7px; font-family: "Cascadia Mono", Consolas, Menlo, monospace; font-size: 12px; }}
QFrame[banner="info"] {{ background: {t['infoSoft']}; border: 1px solid {t['info']}; border-radius: 8px; }}
QFrame[banner="warn"] {{ background: {t['warnSoft']}; border: 1px solid {t['warn']}; border-radius: 8px; }}
QFrame[banner="err"] {{ background: {t['errSoft']}; border: 1px solid {t['err']}; border-radius: 8px; }}
QFrame[banner="ok"] {{ background: {t['okSoft']}; border: 1px solid {t['ok']}; border-radius: 8px; }}
QFrame[toast="info"] {{ background: {t['bg4']}; border: 1px solid {t['border2']}; border-radius: 9px; }}
QFrame[toast="success"] {{ background: {t['okSoft']}; border: 1px solid {t['ok']}; border-radius: 9px; }}
QFrame[toast="warning"] {{ background: {t['warnSoft']}; border: 1px solid {t['warn']}; border-radius: 9px; }}
QFrame[toast="error"] {{ background: {t['errSoft']}; border: 1px solid {t['err']}; border-radius: 9px; }}
"""


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    global _current
    _current = theme if theme in TOKENS else "dark"
    font = QFont()
    font.setFamilies(UI_FONTS)
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(build_qss(_current))


def repolish(widget) -> None:
    """プロパティ(variant など)を変えたあとにスタイルを再適用する。"""
    st = widget.style()
    st.unpolish(widget)
    st.polish(widget)
    widget.update()
