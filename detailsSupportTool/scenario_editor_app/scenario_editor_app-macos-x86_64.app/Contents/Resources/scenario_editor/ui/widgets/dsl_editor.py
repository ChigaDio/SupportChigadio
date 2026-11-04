"""テキストDSLエディタ (ScenarioTransactionCodeEditor.js)。

構文ハイライト(tokenize_line をそのまま利用) / リアルタイムのリント(波線) / カスケード補完 /
Ctrl(Cmd)+Alt+G・H で見出し挿入 / Utils メニュー (見出し挿入・ID振り直し・インデックス一括調整) / Ctrl+Z で戻せる。
"""
from __future__ import annotations

import re

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QKeySequence, QPainter, QShortcut, QSyntaxHighlighter, QTextCharFormat,
                           QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit,
                               QPushButton, QTextEdit, QToolTip, QVBoxLayout, QWidget)

from ...core import dsl as DSL
from ...core import index_tools as IT
from .. import icons, theme
from ..dialogs.index_tools_dialog import IndexToolsDialog

HEADER_LINE_RE = re.compile(r"^#\s*====\s*SUB:\S+\s+NODE:\S+.*?====\s*$")


# --- UTF-16 位置 (Qt) と Python の文字位置の変換。BMP 外の文字 (絵文字) が混じっても位置がずれないようにする。
def cp_to_u16(line: str, idx: int) -> int:
    return len(line[:idx].encode("utf-16-le")) // 2


def u16_to_cp(line: str, idx: int) -> int:
    n = 0
    for i, ch in enumerate(line):
        if n >= idx:
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(line)


def _fmt(color, bold=False, italic=False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class DslHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.rebuild()

    def rebuild(self):
        c = theme.color
        dark = theme.current_theme() == "dark"
        self.f_comment = _fmt(c("faint"), italic=True)
        self.f_header = _fmt(c("accent"), bold=True)
        self.f_string = _fmt("#8fd18a" if dark else "#1f7a3d")
        self.f_number = _fmt("#f0a96b" if dark else "#b45309")
        self.f_op = _fmt(c("muted"))
        self.f_punct = _fmt(c("muted"))
        self.f_keyword = _fmt(c("accent"), bold=True)
        self.f_atom = _fmt("#d99cf0" if dark else "#8e24aa")
        self.f_var = _fmt("#9ad0f5" if dark else "#0b6aa8")
        self.rehighlight()

    def highlightBlock(self, text):
        if DSL.GROUP_HEADER_RE.match(text):
            self.setFormat(0, len(text), self.f_header)
            return
        raw = text
        toks = DSL.tokenize_line("@@" + raw[2:] if DSL.is_sub_group_setting_line(raw) else raw)
        for idx, tok in enumerate(toks):
            fmt = None
            ty = tok["type"]
            if ty == "COMMENT":
                fmt = self.f_comment
            elif ty == "STRING":
                fmt = self.f_string
            elif ty == "NUMBER":
                fmt = self.f_number
            elif ty == "EQUALS":
                fmt = self.f_op
            elif ty in ("LPAREN", "RPAREN", "LBRACKET", "RBRACKET", "LBRACE", "RBRACE", "COMMA", "COLON"):
                fmt = self.f_punct
            elif ty == "IDENT":
                fmt = self.f_keyword if idx == 0 else (self.f_atom if tok["value"] in ("true", "false") else self.f_var)
            if fmt is not None:
                a = cp_to_u16(raw, tok["from"])
                b = cp_to_u16(raw, tok["to"])
                self.setFormat(a, b - a, fmt)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.ed = editor

    def sizeHint(self):
        return QSize(self.ed.line_number_width(), 0)

    def paintEvent(self, e):
        self.ed.paint_line_numbers(e)


class CompletionPopup(QListWidget):
    """入力位置の下に出す補完候補。キー操作は DslTextEdit が転送する (フォーカスは奪わない)。"""
    chosen = Signal(dict)

    def __init__(self, editor):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.ed = editor
        self.setMinimumWidth(280)
        self.setMaximumHeight(240)
        self.setStyleSheet(f"QListWidget{{background:{theme.color('bg2')};border:1px solid {theme.color('border2')};border-radius:8px;padding:3px;}}")
        self.itemClicked.connect(lambda it: self.chosen.emit(it.data(Qt.ItemDataRole.UserRole)))

    def set_items(self, items):
        self.clear()
        for it in items:
            icon = {"role": "role", "field": "tag"}.get(it.get("type"), "info")
            text = it["label"] + (f"   {it['detail']}" if it.get("detail") else "")
            li = QListWidgetItem(icons.icon(icon, theme.color("accent") if it.get("type") == "role" else theme.color("muted"), 14), text)
            li.setData(Qt.ItemDataRole.UserRole, it)
            self.addItem(li)
        if items:
            self.setCurrentRow(0)
        h = min(240, 26 * len(items) + 10)
        self.setFixedHeight(h)

    def move(self_, delta):  # noqa: N805  (QWidget.move と衝突しないよう別名を使う)
        pass

    def step(self, delta):
        n = self.count()
        if n:
            self.setCurrentRow((self.currentRow() + delta) % n)

    def current_item(self):
        li = self.currentItem()
        return li.data(Qt.ItemDataRole.UserRole) if li else None


class DslTextEdit(QPlainTextEdit):
    diagnosticsChanged = Signal(list)
    userEdited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(theme.mono_font(10))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 2)
        self.setUndoRedoEnabled(True)
        self.role_names, self.role_schemas, self.class_schemas = [], {}, {}
        self.setting_schema, self.setting_default_line = None, ""
        self.issues = []
        self.gutter = LineNumberArea(self)
        self.highlighter = DslHighlighter(self.document())
        self.popup = CompletionPopup(self)
        self.popup.chosen.connect(self.apply_completion)
        self._comp_range = None
        self._lint_timer = QTimer(self)
        self._lint_timer.setSingleShot(True)
        self._lint_timer.setInterval(400)
        self._lint_timer.timeout.connect(self.run_lint)
        self._typing = False
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._extra_selections)
        self.textChanged.connect(self._on_text)
        self._update_gutter_width()
        self.setMouseTracking(True)
        QShortcut(QKeySequence("Ctrl+Alt+G"), self, activated=self.insert_new_group, context=Qt.ShortcutContext.WidgetShortcut)
        QShortcut(QKeySequence("Ctrl+Alt+H"), self, activated=self.insert_new_subgroup, context=Qt.ShortcutContext.WidgetShortcut)
        QShortcut(QKeySequence("Ctrl+Space"), self, activated=lambda: self.show_completions(force=True), context=Qt.ShortcutContext.WidgetShortcut)
        self.message = lambda m: None

    # ---------------------------------------------------------------- 行番号
    def line_number_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * max(3, digits)

    def _update_gutter_width(self, *_):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    def paint_line_numbers(self, event):
        p = QPainter(self.gutter)
        p.fillRect(event.rect(), QColor(theme.color("bg1")))
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        cur = self.textCursor().blockNumber()
        bad = {i.line for i in self.issues if i.severity != "warning"}
        warn = {i.line for i in self.issues if i.severity == "warning"}
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                col = theme.color("err") if n in bad else (theme.color("warn") if n in warn else (theme.color("text") if n == cur else theme.color("faint")))
                p.setPen(QColor(col))
                p.drawText(0, top, self.gutter.width() - 8, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(n + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            n += 1

    # ---------------------------------------------------------------- スキーマ
    def set_schemas(self, role_names, role_schemas, class_schemas, setting_schema=None, setting_default_line=""):
        self.role_names = list(role_names or [])
        self.role_schemas = role_schemas or {}
        self.class_schemas = class_schemas or {}
        self.setting_schema = setting_schema
        self.setting_default_line = setting_default_line or ""
        self._lint_timer.start()

    # ---------------------------------------------------------------- リント
    def _on_text(self):
        self._lint_timer.start()
        if not self._typing:
            self.popup.hide()

    def run_lint(self):
        self.issues = DSL.lint_document(self.toPlainText(), self.role_schemas, self.class_schemas, self.setting_schema)
        self._extra_selections()
        self.gutter.update()
        self.diagnosticsChanged.emit(self.issues)

    def _extra_selections(self):
        sels = []
        cur = QTextEdit.ExtraSelection()
        cur.format.setBackground(QColor(theme.color("bg3")))
        cur.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        cur.cursor = self.textCursor()
        cur.cursor.clearSelection()
        sels.append(cur)
        doc = self.document()
        for iss in self.issues:
            blk = doc.findBlockByNumber(min(iss.line, doc.blockCount() - 1))
            if not blk.isValid():
                continue
            text = blk.text()
            a = cp_to_u16(text, min(iss.from_, len(text)))
            b = max(a, cp_to_u16(text, min(iss.to, len(text))))
            if b == a:
                b = min(a + 1, len(text))
            s = QTextEdit.ExtraSelection()
            fmt = s.format
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            fmt.setUnderlineColor(QColor(theme.color("warn") if iss.severity == "warning" else theme.color("err")))
            c = QTextCursor(blk)
            c.setPosition(blk.position() + a)
            c.setPosition(blk.position() + b, QTextCursor.MoveMode.KeepAnchor)
            s.cursor = c
            sels.append(s)
        self.setExtraSelections(sels)

    def issue_at(self, pos):
        cur = self.cursorForPosition(pos)
        blk = cur.block()
        n = blk.blockNumber()
        col = u16_to_cp(blk.text(), cur.positionInBlock())
        hits = [i for i in self.issues if i.line == n and i.from_ <= col <= max(i.to, i.from_ + 1)]
        return hits

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        hits = self.issue_at(e.position().toPoint())
        if hits:
            QToolTip.showText(e.globalPosition().toPoint(), "\n".join(h.message for h in hits), self)
        else:
            QToolTip.hideText()

    # ---------------------------------------------------------------- 補完
    def _word_start(self, text_before):
        m = re.search(r"[A-Za-z0-9_.]*$", text_before)
        return len(text_before) - (len(m.group(0)) if m else 0)

    def show_completions(self, force=False):
        cur = self.textCursor()
        blk = cur.block()
        line_text = blk.text()
        ch = u16_to_cp(line_text, cur.positionInBlock())
        before = line_text[:ch]
        full = self.toPlainText()
        cursor_line = blk.blockNumber()
        options = []
        # '#' / '#@' の入力でサブグループ設定行のひな形を出す
        if self.setting_schema is not None and self.setting_default_line and re.match(r"^#@?$", before):
            options = [{"label": "#@ サブグループ設定", "detail": self.setting_default_line, "type": "keyword",
                        "insertText": self.setting_default_line}]
            start = 0
        else:
            items = DSL.get_completions_at(full, cursor_line, ch, self.role_names, self.role_schemas, self.class_schemas, self.setting_schema)
            start = self._word_start(before)
            word = before[start:]
            if cursor_line > 0 and self.setting_schema is not None and self.setting_default_line and line_text.strip() == "":
                prev = self.document().findBlockByNumber(cursor_line - 1).text()
                if HEADER_LINE_RE.match(prev):
                    options.append({"label": "#@ サブグループ設定", "detail": self.setting_default_line, "type": "keyword",
                                    "insertText": self.setting_default_line})
            options += items
            if not force and word == "":
                options = [o for o in options if o.get("type") == "keyword"] if False else []
            elif word:
                lw = word.lower()
                options = [o for o in options if lw in o["label"].lower() or o.get("type") == "keyword"]
                options.sort(key=lambda o: (not o["label"].lower().startswith(lw), o["label"].lower()))
        if not options:
            self.popup.hide()
            return
        self._comp_range = (blk.blockNumber(), start, ch)
        self.popup.set_items(options[:60])
        rect = self.cursorRect()
        self.popup.move(self.viewport().mapToGlobal(QPoint(rect.left(), rect.bottom() + 4)))
        self.popup.show()

    def apply_completion(self, item):
        if not item or self._comp_range is None:
            return
        n, start, end = self._comp_range
        blk = self.document().findBlockByNumber(n)
        text = blk.text()
        a, b = cp_to_u16(text, start), cp_to_u16(text, end)
        c = QTextCursor(blk)
        c.setPosition(blk.position() + a)
        c.setPosition(blk.position() + b, QTextCursor.MoveMode.KeepAnchor)
        c.insertText(item.get("insertText") or item["label"])
        self.setTextCursor(c)
        self.popup.hide()
        self.setFocus()

    def keyPressEvent(self, e):
        k = e.key()
        if self.popup.isVisible():
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self.popup.step(1 if k == Qt.Key.Key_Down else -1)
                return
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                self.apply_completion(self.popup.current_item())
                return
            if k == Qt.Key.Key_Escape:
                self.popup.hide()
                return
        if k == Qt.Key.Key_Tab and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            c = self.textCursor()
            if c.hasSelection():
                self._indent_selection(+1)
            else:
                c.insertText("  ")
            return
        if k == Qt.Key.Key_Backtab or (k == Qt.Key.Key_Tab and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._indent_selection(-1)
            return
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            # 直前行のインデントを引き継ぐ
            c = self.textCursor()
            ind = re.match(r"[ \t]*", c.block().text()).group(0)
            c.insertText("\n" + ind)
            self.setTextCursor(c)
            return
        self._typing = True
        try:
            super().keyPressEvent(e)
        finally:
            self._typing = False
        txt = e.text()
        if txt and (txt.isalnum() or txt in "_.#@" or txt == "="):
            QTimer.singleShot(0, self.show_completions)
        elif k in (Qt.Key.Key_Backspace,) and self.popup.isVisible():
            QTimer.singleShot(0, self.show_completions)
        else:
            if not (k in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta)):
                self.popup.hide()

    def _indent_selection(self, sign):
        c = self.textCursor()
        doc = self.document()
        a, b = c.selectionStart(), c.selectionEnd()
        first = doc.findBlock(a).blockNumber()
        last = doc.findBlock(max(a, b - 1) if b > a else b).blockNumber()
        c.beginEditBlock()
        for n in range(first, last + 1):
            blk = doc.findBlockByNumber(n)
            cc = QTextCursor(blk)
            if sign > 0:
                cc.insertText("  ")
            else:
                t = blk.text()
                k = min(2, len(t) - len(t.lstrip(" ")))
                if k:
                    cc.setPosition(blk.position())
                    cc.setPosition(blk.position() + k, QTextCursor.MoveMode.KeepAnchor)
                    cc.removeSelectedText()
        c.endEditBlock()

    def focusOutEvent(self, e):
        self.popup.hide()
        super().focusOutEvent(e)

    # ---------------------------------------------------------------- 見出し挿入 (Ctrl/Cmd+Alt+G/H)
    def _header_text(self, sub_id, path_key):
        setting = self.setting_default_line or ""
        return f"# ==== SUB:{sub_id} NODE:{path_key} ====\n{setting + chr(10) if setting else ''}\n"

    def _insert_header(self, sub_id, path_key):
        c = self.textCursor()
        blk = c.block()
        text = self._header_text(sub_id, path_key)
        ins = QTextCursor(blk)
        ins.insertText(text)
        ins.setPosition(blk.position() + len(text))
        self.setTextCursor(ins)
        self.ensureCursorVisible()

    def insert_new_group(self):
        cur_line = self.textCursor().blockNumber()
        r = DSL.compute_next_group_header(self.toPlainText(), cur_line)
        self._insert_header(r["subId"], r["newPathKey"])
        return True

    def insert_new_subgroup(self):
        cur_line = self.textCursor().blockNumber()
        r = DSL.compute_next_subgroup_header(self.toPlainText(), cur_line)
        if not r:
            self.message("カーソルがどのグループの中にもありません(見出しの下で実行してください)")
            return False
        self._insert_header(r["subId"], r["newPathKey"])
        return True


class DslEditor(QWidget):
    """DslTextEdit + Utils ボタン/メッセージ。"""
    textChanged = Signal()

    def __init__(self, state=None, show_utils=True, parent=None):
        super().__init__(parent)
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = DslTextEdit()
        self.edit.message = self.flash
        self.edit.textChanged.connect(self.textChanged.emit)
        if show_utils:
            bar = QHBoxLayout()
            bar.setSpacing(8)
            self.utils_btn = QPushButton("Utils")
            self.utils_btn.setIcon(icons.icon("build"))
            self.utils_btn.setProperty("variant", "small")
            self.utils_btn.clicked.connect(self.open_utils)
            self.msg = QLabel("見出しの挿入・ID振り直し・インデックス一括調整など")
            self.msg.setProperty("role", "muted")
            bar.addWidget(self.utils_btn)
            bar.addWidget(self.msg, 1)
            lay.addLayout(bar)
            self._msg_timer = QTimer(self)
            self._msg_timer.setSingleShot(True)
            self._msg_timer.timeout.connect(lambda: self.msg.setText("見出しの挿入・ID振り直し・インデックス一括調整など"))
        lay.addWidget(self.edit, 1)

    # --- 公開
    def set_text(self, s):
        self.edit.setPlainText(s or "")

    def text(self):
        return self.edit.toPlainText()

    def set_schemas(self, *a, **k):
        self.edit.set_schemas(*a, **k)

    def diagnostics(self):
        return self.edit.issues

    def lint_now(self):
        self.edit.run_lint()
        return self.edit.issues

    def flash(self, m):
        if hasattr(self, "msg"):
            self.msg.setText(m)
            self._msg_timer.start(5000)

    # --- Utils メニュー
    def open_utils(self):
        text = self.text()
        cur_line = self.edit.textCursor().blockNumber()
        sib = IT.find_sibling_sections(text, cur_line)
        has_headers = len(sib["sections"]) > 0
        current = sib["current"]
        m = QMenu(self)

        def act(title, sub, fn, enabled=True):
            a = QAction(f"{title}\n    {sub}" if False else title, m)
            a.setToolTip(sub)
            a.setEnabled(enabled)
            a.triggered.connect(lambda _=False: fn())
            m.addAction(a)
            return a
        act("新しいグループの見出しを挿入（Ctrl/Cmd+Alt+G）", "直前のグループのIDに+1", self._ins_group)
        act("新しいサブグループの見出しを挿入（Ctrl/Cmd+Alt+H）", "今いるグループ内の直前のサブグループのIDに+1", self._ins_sub)
        m.addSeparator()
        act("重複しているIDを振り直す", "コピー&ペースト直後などで、同じ親の中でIDが重複した見出しを解消", self.renumber_duplicates, has_headers)
        act("インデックスを一括調整…", "カーソルのサブグループ以降の text_list_index / voice_ref をずらす・連番にする",
            self.open_index_tools, current is not None)
        m.setToolTipsVisible(True)
        m.exec(self.utils_btn.mapToGlobal(QPoint(0, self.utils_btn.height())))

    def _ins_group(self):
        self.edit.insert_new_group()
        self.edit.setFocus()

    def _ins_sub(self):
        ok = self.edit.insert_new_subgroup()
        if ok is False:
            self.flash("カーソルがどのグループの中にもありません(見出しの下で実行してください)")
        self.edit.setFocus()

    def renumber_duplicates(self):
        r = DSL.renumber_duplicate_node_ids(self.text())
        if not r["renamed"]:
            self.flash("重複しているIDは見つかりませんでした")
            return
        c = self.edit.textCursor()
        c.beginEditBlock()
        c.select(QTextCursor.SelectionType.Document)
        c.insertText(r["text"])
        c.endEditBlock()
        self.flash("ID重複を解消しました: " + ", ".join(f"{x['oldPath']} → {x['newPath']}" for x in r["renamed"]))
        self.edit.setFocus()

    def open_index_tools(self):
        text = self.text()
        cur_line = self.edit.textCursor().blockNumber()
        sib = IT.find_sibling_sections(text, cur_line)
        current, siblings = sib["current"], sib["siblings"]
        if not current:
            self.flash("カーソルを見出し(# ==== SUB:… NODE:… ====)の下に置いてから実行してください")
            return
        schemas = self.edit.role_schemas or {}

        def make_plan(o):
            sec = next((s for s in siblings if s["pathKey"] == o["start"]), None)
            return IT.plan_index_adjust_in_dsl(text, schemas, {
                "cursorLine": sec["headerLine"] if sec else current["headerLine"], "endPathKey": o["end"], "mode": o["mode"],
                "delta": o["delta"], "step": o["step"], "base": o["base"], "includeStart": o["includeStart"],
                "includeInt": o["includeInt"], "target": o["target"]})

        dlg = IndexToolsDialog(
            self, [{"value": s["pathKey"], "label": f"SUB:{s['subId']} NODE:{s['pathKey']}"} for s in siblings], current["pathKey"],
            lambda include_int: IT.collect_index_fields_in_dsl(text, schemas, {"includeInt": include_int}), make_plan,
            lambda c: {"where": f"NODE:{c['pathKey']}", "field": f"{c['roleName']}.{c['fieldName']}（{c['line'] + 1}行目）"},
            title="インデックス一括調整（DSL）")
        if dlg.exec() and dlg.plan.get("changes"):
            self.apply_index_plan(dlg.plan)

    def apply_index_plan(self, plan):
        """全文を置き換えず、変更のあった数値だけを書き換える(Ctrl+Z で1操作として戻せる・カーソルも保たれる)。"""
        doc = self.edit.document()
        c = self.edit.textCursor()
        c.beginEditBlock()
        # 後ろから書き換えると前の位置がずれない
        for ch in sorted(plan["changes"], key=lambda x: (-x["line"], -x["from"])):
            blk = doc.findBlockByNumber(ch["line"])
            t = blk.text()
            a, b = cp_to_u16(t, ch["from"]), cp_to_u16(t, ch["to"])
            cc = QTextCursor(blk)
            cc.setPosition(blk.position() + a)
            cc.setPosition(blk.position() + b, QTextCursor.MoveMode.KeepAnchor)
            cc.insertText(DSL.js_number_to_string(ch["toValue"]))
        c.endEditBlock()
        self.flash(f"{len(plan['changes'])}件のインデックスを書き換えました(Ctrl+Zで元に戻せます)")
        self.edit.setFocus()
