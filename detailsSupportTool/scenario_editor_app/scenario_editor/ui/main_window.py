"""メインウィンドウ: サイドバー(ナビ・最近・接続・テーマ) + ページスタック + トースト + コマンドパレット(Ctrl+K)。"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from ..api.client import DEFAULT_BASE_URL
from . import icons, theme
from .async_ import run_async
from .pages.event_list import EventListPage
from .pages.role_detail import RoleDetailPage, SubGroupSettingPage
from .pages.role_list import RoleListPage
from .pages.story_setting import StorySettingPage
from .pages.transition import TransitionPage
from .widgets import common as C

PAGES = {
    "event_list": EventListPage, "role_list": RoleListPage, "role_detail": RoleDetailPage,
    "subgroup_setting": SubGroupSettingPage, "story_setting": StorySettingPage, "transition": TransitionPage,
}
NAV = [("event_list", "イベント", "events"), ("role_list", "Role", "role"), ("subgroup_setting", "サブグループ設定", "tune")]
NAV_OWNER = {"role_detail": "role_list"}   # 下位ページはどのナビ項目の配下か
SHORTCUTS = [
    ("Ctrl+K", "コマンドパレット(ページ・イベント・Roleへ移動)"), ("Ctrl+1 / 2 / 3", "イベント / Role / サブグループ設定"),
    ("Alt+←", "前のページへ戻る"), ("Ctrl+Z / Ctrl+Y", "遷移エディタ: 元に戻す / やり直す"),
    ("Ctrl+Alt+G / H", "テキスト編集: グループ / サブグループの見出しを挿入"), ("Ctrl+Space", "テキスト編集: 補完候補を出す"),
    ("Alt+↑ / ↓", "データ入力: 前 / 次のサブグループへ"), ("Tab / Shift+Tab", "テキスト編集: インデント / 解除"),
]


class ConnectionDialog(QDialog):
    def __init__(self, parent, state):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("サーバー接続設定")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        lay.addWidget(C.label("既存のシナリオエディタ(Flask)サーバーのアドレスを指定します。", "muted", wrap=True))
        self.url = QLineEdit(state.settings.get("baseUrl") or DEFAULT_BASE_URL)
        self.url.setPlaceholderText(DEFAULT_BASE_URL)
        lay.addWidget(self.url)
        row = QHBoxLayout()
        self.test_btn = C.button("接続テスト", on_click=self.test)
        self.result = C.label("", "muted")
        row.addWidget(self.test_btn)
        row.addWidget(self.result, 1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addStretch(1)
        row2.addWidget(C.button("キャンセル", on_click=self.reject))
        row2.addWidget(C.button("保存して接続", "primary", on_click=self.accept))
        lay.addLayout(row2)

    def test(self):
        from ..api.client import ApiClient
        url = self.url.text().strip().rstrip("/") or DEFAULT_BASE_URL
        self.result.setText("接続中...")
        run_async(lambda: ApiClient(url, timeout=5).ping(),
                  lambda ok: self.result.setText("接続できました" if ok else "接続できませんでした(アドレスとサーバーの起動を確認してください)"),
                  lambda e: self.result.setText(f"エラー: {e}"), self)

    def value(self):
        return self.url.text().strip().rstrip("/") or DEFAULT_BASE_URL


class CommandPalette(QDialog):
    """Ctrl+K。入力で絞り込み、Enter で実行。"""

    def __init__(self, parent, commands):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.commands = commands
        self.resize(560, 420)
        self.setStyleSheet(f"QDialog{{background:{theme.color('bg2')};border:1px solid {theme.color('border2')};border-radius:12px;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        self.q = QLineEdit()
        self.q.setPlaceholderText("移動・操作を検索…（例: 遷移 / Role / テーマ）")
        self.q.textChanged.connect(self._fill)
        lay.addWidget(self.q)
        self.list = QListWidget()
        self.list.itemActivated.connect(self._run)
        self.list.itemClicked.connect(self._run)
        lay.addWidget(self.list, 1)
        self.chosen = None
        self._fill("")
        self.q.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.q and ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                n = self.list.count()
                if n:
                    self.list.setCurrentRow((self.list.currentRow() + (1 if k == Qt.Key.Key_Down else -1)) % n)
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                it = self.list.currentItem()
                if it:
                    self._run(it)
                return True
        return super().eventFilter(obj, ev)

    def _fill(self, text):
        terms = [t for t in text.lower().split() if t]
        self.list.clear()
        for c in self.commands:
            hay = (c["label"] + " " + c.get("hint", "")).lower()
            if all(t in hay for t in terms):
                it = QListWidgetItem(icons.icon(c.get("icon", "info"), theme.color("accent"), 16), c["label"] + (f"    {c['hint']}" if c.get("hint") else ""))
                it.setData(Qt.ItemDataRole.UserRole, c)
                self.list.addItem(it)
            if self.list.count() >= 60:
                break
        if self.list.count():
            self.list.setCurrentRow(0)

    def _run(self, item):
        self.chosen = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.pages = {}
        self.current = None
        self.back_stack = []
        self._was_connected = False
        self.setWindowTitle("Scenario Editor")
        self.resize(1360, 860)
        self.setMinimumSize(980, 620)
        w = state.settings.get("window")
        if isinstance(w, list) and len(w) == 4:
            self.setGeometry(*[int(x) for x in w])

        root = QWidget()
        self.setCentralWidget(root)
        hl = QHBoxLayout(root)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        hl.addWidget(self.stack, 1)
        self.toasts = C.ToastHost(root)
        state.toast.connect(self.toasts.show_toast)
        state.navigate.connect(self.go)
        state.connectionChanged.connect(self._connection_changed)
        self._build_menu()
        for key, page in (("Ctrl+1", "event_list"), ("Ctrl+2", "role_list"), ("Ctrl+3", "subgroup_setting")):
            QShortcut(QKeySequence(key), self, activated=lambda p=page: self.go(p, {}))
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.open_palette)
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.go_back)
        self.ping_timer = QTimer(self)
        self.ping_timer.setInterval(15000)
        self.ping_timer.timeout.connect(self.check_connection)
        self.ping_timer.start()
        self.check_connection()
        self.go("event_list", {})

    # ------------------------------------------------------------------ 構築
    def _build_sidebar(self):
        sb = QFrame()
        sb.setProperty("sidebar", True)
        sb.setFixedWidth(232)
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(4)
        title = QLabel("Scenario Editor")
        title.setStyleSheet("font-size:17px;font-weight:800;letter-spacing:0.5px;")
        sub = C.label("シナリオ・Role・遷移の編集", "muted")
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(14)
        self.nav_btns = {}
        for pid, text, ic in NAV:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setIcon(icons.icon(ic))
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("nav", True)
            b.clicked.connect(lambda _=False, p=pid: self.go(p, {}))
            lay.addWidget(b)
            self.nav_btns[pid] = b
        lay.addSpacing(10)
        lay.addWidget(C.label("最近開いた", "muted"))
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(2)
        lay.addLayout(self.recent_box)
        lay.addStretch(1)
        pal = C.button("コマンドパレット  Ctrl+K", "ghost", "search", on_click=self.open_palette, small=True)
        lay.addWidget(pal)
        self.conn_btn = QPushButton()
        self.conn_btn.setProperty("variant", "ghost")
        self.conn_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.conn_btn.clicked.connect(self.open_connection)
        lay.addWidget(self.conn_btn)
        self.theme_btn = C.button("", "ghost", None, "ダーク/ライトを切り替え", self.toggle_theme, small=True)
        lay.addWidget(self.theme_btn)
        self._update_theme_btn()
        self._render_connection(bool(self.state.connected))
        self._refresh_recent()
        sb.setStyleSheet(sb.styleSheet() + f"QPushButton[nav=\"true\"]{{text-align:left;padding:8px 12px;border:none;border-radius:8px;background:transparent;}}"
                         f"QPushButton[nav=\"true\"]:hover{{background:{theme.color('bg3')};}}"
                         f"QPushButton[nav=\"true\"]:checked{{background:{theme.color('accentSoft')};color:{theme.color('accent')};font-weight:700;}}")
        self.sidebar = sb
        return sb

    def _build_menu(self):
        mb = self.menuBar()
        f = mb.addMenu("ファイル")
        f.addAction("サーバー接続設定…", self.open_connection)
        f.addSeparator()
        a = QAction("終了", self)
        a.triggered.connect(self.close)
        a.setShortcut(QKeySequence("Ctrl+Q"))
        f.addAction(a)
        v = mb.addMenu("表示")
        v.addAction("コマンドパレット", self.open_palette)
        v.addAction("ダーク / ライト切り替え", self.toggle_theme)
        h = mb.addMenu("ヘルプ")
        h.addAction("ショートカット一覧", self.show_shortcuts)

    # ------------------------------------------------------------------ ナビゲーション
    def _page(self, pid):
        if pid not in self.pages:
            p = PAGES[pid](self.state)
            self.pages[pid] = p
            self.stack.addWidget(p)
        return self.pages[pid]

    def go(self, pid, params=None, record=True):
        params = dict(params or {})
        if pid not in PAGES:
            return
        if self.current is not None and not self.pages[self.current].can_leave():
            self._sync_nav()
            return
        prev = self.current
        if prev is not None and record and not (prev == pid and self.pages[prev].params == params):
            self.back_stack.append((prev, dict(self.pages[prev].params)))
            self.back_stack = self.back_stack[-30:]
        page = self._page(pid)
        self.current = pid
        self.stack.setCurrentWidget(page)
        page.load(params)
        self.setWindowTitle(f"{page.page_title() or 'Scenario Editor'} — Scenario Editor")
        self._sync_nav()
        self._refresh_recent()
        page.on_activated()

    def go_back(self):
        if self.back_stack:
            pid, params = self.back_stack.pop()
            self.go(pid, params, record=False)

    def _sync_nav(self):
        owner = NAV_OWNER.get(self.current, self.current)
        for pid, b in self.nav_btns.items():
            b.setChecked(pid == owner)

    def _refresh_recent(self):
        C.clear_layout(self.recent_box)
        recent = self.state.settings.get("recent") or []
        if not recent:
            self.recent_box.addWidget(C.label("まだありません", "muted"))
        for r in recent[:6]:
            b = QPushButton(r.get("label") or r.get("kind"))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{text-align:left;padding:4px 8px;border:none;border-radius:6px;background:transparent;"
                            f"color:{theme.color('muted')};font-size:12px;}}QPushButton:hover{{background:{theme.color('bg3')};color:{theme.color('text')};}}")
            b.clicked.connect(lambda _=False, r=r: self.go(r.get("kind"), r.get("params") or {}))
            self.recent_box.addWidget(b)

    # ------------------------------------------------------------------ 接続
    def check_connection(self):
        api = self.state.api
        run_async(api.ping, lambda ok: self._set_connected(ok), lambda e: self._set_connected(False), self)

    def _set_connected(self, ok):
        if ok != self.state.connected:
            self.state.connected = ok
            self.state.connectionChanged.emit(ok)

    def _render_connection(self, ok):
        col = theme.color("ok") if ok else theme.color("err")
        self.conn_btn.setText(("● 接続中  " if ok else "● 未接続  ") + (self.state.settings.get("baseUrl") or ""))
        self.conn_btn.setStyleSheet(f"QPushButton{{text-align:left;padding:5px 8px;border:none;border-radius:6px;background:transparent;"
                                    f"color:{col};font-size:11px;}}QPushButton:hover{{background:{theme.color('bg3')};}}")
        self.conn_btn.setToolTip("クリックでサーバー接続設定を開く")

    def _connection_changed(self, ok):
        self._render_connection(ok)
        if self._was_connected and not ok:
            self.state.show_toast("サーバーに接続できません。起動とアドレスを確認してください", "error")
        self._was_connected = ok

    def open_connection(self):
        d = ConnectionDialog(self, self.state)
        if d.exec():
            self.state.set_base_url(d.value())
            self.state.connected = False
            self._was_connected = False
            self._connection_changed(False)
            self.check_connection()
            for p in self.pages.values():
                p.shutdown()
            if self.current:
                self.pages[self.current].load(self.pages[self.current].params)
            self.state.show_toast(f"接続先を変更しました: {d.value()}", "success")

    # ------------------------------------------------------------------ テーマ
    def _update_theme_btn(self):
        dark = theme.current_theme() == "dark"
        self.theme_btn.setText("ライトテーマにする" if dark else "ダークテーマにする")
        self.theme_btn.setIcon(icons.icon("sun" if dark else "moon"))

    def toggle_theme(self):
        if self.current is not None and not self.pages[self.current].can_leave():
            return
        new = "light" if theme.current_theme() == "dark" else "dark"
        theme.apply_theme(QApplication.instance(), new)
        self.state.settings["theme"] = new
        self.state.save_settings()
        # アイコン等は生成時の色で描かれているので、ページと側面バーを作り直す
        cur, params = self.current, dict(self.pages[self.current].params) if self.current else {}
        for p in self.pages.values():
            p.shutdown()
            self.stack.removeWidget(p)
            p.deleteLater()
        self.pages.clear()
        self.current = None
        old = self.sidebar
        self.centralWidget().layout().replaceWidget(old, self._build_sidebar())
        old.deleteLater()
        self.state.themeChanged.emit(new)
        self.go(cur or "event_list", params, record=False)

    # ------------------------------------------------------------------ コマンドパレット
    def _commands(self):
        cmds = [{"label": text, "hint": "ページ", "icon": ic, "run": lambda p=pid: self.go(p, {})} for pid, text, ic in NAV]
        cmds += [
            {"label": "サーバー接続設定…", "hint": "設定", "icon": "settings", "run": self.open_connection},
            {"label": "ダーク / ライト切り替え", "hint": "テーマ", "icon": "sun", "run": self.toggle_theme},
            {"label": "ショートカット一覧", "hint": "ヘルプ", "icon": "keyboard", "run": self.show_shortcuts},
        ]
        for r in (self.state.settings.get("recent") or [])[:8]:
            cmds.append({"label": f"最近: {r.get('label')}", "hint": "", "icon": "bookmark",
                         "run": lambda r=r: self.go(r.get("kind"), r.get("params") or {})})
        try:
            for ev in self.state.lookups.events() or []:
                for s in ev.get("subEvents") or []:
                    base = f"{ev.get('id')}/{s.get('subId')} {ev.get('name', '')} {s.get('name', '')}"
                    prm = {"eventId": ev["id"], "subId": s["subId"]}
                    cmds.append({"label": f"遷移: {base}", "hint": "遷移エディタ", "icon": "graph", "run": lambda p=prm: self.go("transition", p)})
                    cmds.append({"label": f"物語設定: {base}", "hint": "物語設定", "icon": "book", "run": lambda p=prm: self.go("story_setting", p)})
            for r in self.state.lookups.roles() or []:
                cmds.append({"label": f"Role: {r.get('name')}", "hint": r.get("description") or "", "icon": "role",
                             "run": lambda n=r.get("name"): self.go("role_detail", {"name": n})})
        except Exception:  # noqa: BLE001  オフライン時はページ系のコマンドだけにする
            pass
        return cmds

    def open_palette(self):
        d = CommandPalette(self, self._commands())
        geo = self.geometry()
        d.move(geo.x() + (geo.width() - d.width()) // 2, geo.y() + 90)
        if d.exec() and d.chosen:
            d.chosen["run"]()

    def show_shortcuts(self):
        C.message(self, "\n".join(f"{k:<20}{v}" for k, v in SHORTCUTS), "ショートカット一覧")

    # ------------------------------------------------------------------ 終了
    def closeEvent(self, e):
        if self.current is not None and not self.pages[self.current].can_leave():
            e.ignore()
            return
        g = self.geometry()
        self.state.settings["window"] = [g.x(), g.y(), g.width(), g.height()]
        self.state.save_settings()
        for p in self.pages.values():
            p.shutdown()
        e.accept()
