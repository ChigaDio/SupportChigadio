"""全体編集(イベント内の全Sub) / Sub編集(いま開いているSubのみ) ダイアログ。

JS 版 ScenarioEventTransition.js の handleOpenAllEditDialog / requestApplyAllEdit / handleApplyAllEdit /
handleOpenSubEditDialog / requestApplySubEdit / handleApplySubEdit / handleClose* に対応。
ツリーの組み立てと適用は core.transition_ops(テスト済み) が行い、ここは取得・確認・保存の段取りだけ。
"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QPlainTextEdit, QProgressBar, QVBoxLayout

from ...core import transition_ops as T
from ...core.dsl import js_string
from ..async_ import run_async
from ..widgets import common as C
from ..widgets.dsl_editor import DslEditor
from .diff_dialog import EditPreviewDialog

ALL_HELP = (
    "既存ノードのRole呼び出し内容(追加・削除・値の変更)をまとめて編集できます。"
    "「# 例:」で始まる行は書き方の案内で、残したまま適用しても無視されます。\n"
    "新しいグループを追加したい場合は、下のチェックを入れたうえで新しい見出し（# ==== SUB:番号 NODE:新しいID ====）を書き足してください。"
    "NODE:親ID/子ID のように「/」で区切ると、親グループの中に新しいサブグループを作成できます。"
    "新規作成したグループは他のノードと接続されないので、必要なら通常の画面で接続してください。既存の見出しコメントは削除・改変しないでください。\n"
    "Ctrl(⌘)+Alt+G で新しいグループの見出し、Ctrl(⌘)+Alt+H でカーソル位置のグループ内に新しいサブグループの見出しを、"
    "直前の見出しからIDを1つ増やして挿入できます（サブグループ設定の行「#@ is_wait_key=false ...」もデフォルト値で入ります）。\n"
    "見出し直下の「#@ ...」行は、そのサブグループの設定（入力待ち is_wait_key など。全イベント共通）です。省略した項目は今の値のままです。"
    "Vector2/3/4・color・bit・bezier も「{ フィールド名: 値, ... }」の書き方で入力できます"
    "（例: target={ x: 1, y: 0, z: 2.5 } / color={ r: 1, g: 0.5, b: 0, a: 1 }）。"
)
SUB_HELP = (
    "現在開いているSubだけを対象に、既存ノードのRole呼び出し内容(追加・削除・値の変更)をまとめて編集できます。"
    "「# 例:」で始まる行は書き方の案内で、残したまま適用しても無視されます。\n"
    "新しいグループを追加したい場合は、下のチェックを入れたうえで新しい見出し（# ==== SUB:{sub} NODE:新しいID ====）を書き足してください。"
    "他のSubをまとめて編集したい場合は「全体編集(全Sub一括)」を使ってください。\n"
    "Ctrl(⌘)+Alt+G / Ctrl(⌘)+Alt+H で見出しを挿入できます。見出し直下の「#@ ...」行はサブグループ設定です。\n"
    "セクションをコピー&貼り付けして並び替えると、実行順は貼り付けた位置になります。IDが重複したときは「重複IDを振り直す」で重複だけを解消できます。"
)
DISCARD_TEXT = "まだ「適用」していない編集内容があります。このまま閉じると入力した内容は失われます。よろしいですか？"


class DslEditDialog(QDialog):
    """kind: 'all' | 'sub'。

    env() -> {"ctx": EditContext, "role_names": [...], "setting_default_line": str}
        (呼ぶたびに画面の最新状態を返す)
    on_applied(touched_sub_ids:set[str]) : 適用・保存後に呼ばれる(開いているSubが含まれたら画面を再読み込みする等)
    """

    def __init__(self, parent, state, kind, event_id, sub_id, env, on_applied=None):
        super().__init__(parent)
        self.state, self.kind = state, kind
        self.event_id, self.sub_id = event_id, js_string(sub_id) if sub_id is not None else None
        self.env, self.on_applied = env, on_applied
        self.trees, self.targets = {}, {}
        self.original = ""
        self.loading = self.applying = False
        self.is_all = kind == "all"
        self.setWindowTitle(f"全体編集（{event_id} / 全Sub一括）" if self.is_all else f"Sub編集（{event_id} / SUB:{self.sub_id} のみ）")
        self.resize(1040, 760)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)
        lay.addWidget(C.label(self.windowTitle(), "h2"))
        help_text = ALL_HELP if self.is_all else SUB_HELP.replace("{sub}", str(self.sub_id))
        self.help = C.Banner(help_text, "info")
        self.help.lb.setStyleSheet("font-size:12px;")
        lay.addWidget(self.help)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        lay.addWidget(self.progress)

        self.allow_new = QCheckBox("新しいグループの追加を許可する（未知の見出しを新規ノードとして作成します。OFFの場合、未知の見出しは作成されず警告になります）")
        lay.addWidget(self.allow_new)

        self.editor = DslEditor(state)
        lay.addWidget(self.editor, 1)

        self.diag = QPlainTextEdit()
        self.diag.setReadOnly(True)
        self.diag.setMaximumHeight(130)
        self.diag.setProperty("banner", "err")
        self.diag.hide()
        lay.addWidget(self.diag)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.close_btn = C.button("閉じる", on_click=self.reject)
        self.reload_btn = C.button("再取得", icon_name="refresh", on_click=self.load)
        row.addWidget(self.close_btn)
        row.addWidget(self.reload_btn)
        self.renumber_btn = None
        if not self.is_all:
            self.renumber_btn = C.button("重複IDを振り直す", on_click=self.renumber_ids,
                                         tooltip="コピー&ペーストなどでNODE:のIDが重複した箇所を検出し、重複した側だけ未使用の新しいIDへ振り直します(実行順はテキスト上の位置のまま)")
            row.addWidget(self.renumber_btn)
        row.addStretch(1)
        self.apply_btn = C.button("適用", variant="primary", on_click=self.request_apply)
        row.addWidget(self.apply_btn)
        lay.addLayout(row)
        self._set_busy(True)

    # ---------------------------------------------------------------- 状態
    def _set_busy(self, loading=None, applying=None):
        if loading is not None:
            self.loading = loading
        if applying is not None:
            self.applying = applying
        busy = self.loading or self.applying
        self.progress.setVisible(busy)
        self.editor.setEnabled(not self.loading)
        self.allow_new.setEnabled(not busy)
        self.reload_btn.setEnabled(not busy)
        self.apply_btn.setEnabled(not busy)
        self.apply_btn.setText("適用中..." if self.applying else "適用")
        self.close_btn.setEnabled(not self.applying)
        if self.renumber_btn:
            self.renumber_btn.setEnabled(not busy)

    def is_dirty(self):
        return self.editor.text() != self.original

    def _toast(self, msg, level="info"):
        self.state.show_toast(msg, level)

    def _show_diag(self, diags):
        if not diags:
            self.diag.hide()
            return
        self.diag.setPlainText("\n".join(d["message"] for d in diags))
        self.diag.show()

    def _apply_schemas(self):
        env = self.env()
        ctx = env["ctx"]
        self.editor.set_schemas(env.get("role_names") or [], ctx.role_form_schemas, ctx.class_data_schemas,
                                ctx.setting_schema, env.get("setting_default_line") or "")

    # ---------------------------------------------------------------- 取得
    def load(self):
        if not self.event_id:
            return
        self._show_diag([])
        self._set_busy(loading=True)
        api = self.state.api
        event_id, only_sub = self.event_id, None if self.is_all else self.sub_id

        def work():
            if only_sub is not None:
                sub_ids = [only_sub]
            else:
                ev = next((e for e in (api.list_events() or []) if js_string(e.get("id")) == js_string(event_id)), None)
                sub_ids = [js_string(s.get("subId")) for s in ((ev or {}).get("subEvents") or [])]
            trees = {}
            for sid in sub_ids:
                try:
                    tree, _rev = api.get_transition(event_id, sid)
                except Exception:  # noqa: BLE001  JS: res.ok でなければ空ツリー
                    tree = {"nodes": [], "edges": []}
                trees[sid] = tree
            return trees

        def ok(trees):
            ctx = self.env()["ctx"]
            self.trees, self.targets = {}, {}
            lines = []
            for sid, tree in trees.items():
                tree = T.merge_local_role_data_into_tree(tree, sid, ctx)
                self.trees[sid] = tree
                lines.extend(T.build_edit_lines_for_sub(sid, tree, self.targets, ctx))
            joined = "\n".join(lines)
            self._apply_schemas()
            self.editor.set_text(joined)
            self.original = joined
            self._set_busy(loading=False)

        def err(e):
            self._set_busy(loading=False)
            self._toast("全体編集データの取得に失敗しました" if self.is_all else "Sub編集データの取得に失敗しました", "error")

        run_async(work, ok, err, self)

    # ---------------------------------------------------------------- 適用
    def _sections_and_foreign(self):
        text = self.editor.text()
        if self.is_all:
            return T.parse_edit_sections(text), []
        return T.split_sections_for_sub(text, self.sub_id)

    def _run_apply(self, dry_run):
        sections, foreign = self._sections_and_foreign()
        res = T.apply_edit_sections(sections, self.trees, self.targets, self.allow_new.isChecked(), self.env()["ctx"], dry_run=dry_run)
        res["diagnostics"].extend(T.foreign_section_diagnostics(foreign))
        return res

    def request_apply(self):
        if not self.event_id or (not self.is_all and not self.sub_id):
            return
        res = self._run_apply(True)
        self._show_diag(res["diagnostics"])
        if res["diagnostics"]:
            self._toast("エラーがあるため一部(またはすべて)適用できませんでした。内容を確認してください。" if self.is_all
                        else "エラーがあるため適用できませんでした。内容を確認してください。", "error")
            return
        if T.summarize_changes(res["changes"]) == 0:
            self._toast("変更はありません")
            return
        dlg = EditPreviewDialog(self, res["changes"])
        if dlg.exec():
            self.do_apply()

    def do_apply(self):
        self._set_busy(applying=True)
        res = self._run_apply(False)
        self._show_diag(res["diagnostics"])
        if res["diagnostics"]:
            self._toast("エラーがあるため一部(またはすべて)適用できませんでした。内容を確認してください。", "error")
            self._set_busy(applying=False)
            return
        touched = [s for s in self.trees if s in res["touchedSubIds"]]
        saves = [(sid, self.trees[sid]["nodes"], self.trees[sid]["edges"]) for sid in touched]
        api, event_id = self.state.api, self.event_id

        def work():
            for sid, nodes, edges in saves:
                try:
                    api.save_transition(event_id, sid, nodes, edges)
                except Exception as e:  # noqa: BLE001
                    raise RuntimeError(f"Sub {sid} の保存に失敗しました ({e})") from e
            return len(saves)

        def ok(n):
            self._set_busy(applying=False)
            self._toast(f"全体編集を適用しました（{n}件のSubを更新）" if self.is_all else "このSubの編集内容を適用しました", "success")
            self.original = self.editor.text()   # 閉じる確認を出さない
            self.accept()
            if self.on_applied:
                self.on_applied(set(touched))

        def err(e):
            self._set_busy(applying=False)
            self._toast(("全体編集" if self.is_all else "Sub編集") + f"の適用に失敗しました: {e}", "error")

        run_async(work, ok, err, self)

    # ---------------------------------------------------------------- 補助
    def renumber_ids(self):
        self.editor.renumber_duplicates()

    # 閉じる前の確認 (Escape / ×ボタン / 閉じる 全てここを通る)
    def reject(self):
        if self.applying:
            return
        if self.is_dirty() and not C.confirm(self, DISCARD_TEXT, "確認", "閉じる"):
            return
        super().reject()

    def closeEvent(self, e):
        if self.applying or (self.is_dirty() and not C.confirm(self, DISCARD_TEXT, "確認", "閉じる")):
            e.ignore()
            return
        e.accept()

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_loaded_once", False):
            self._loaded_once = True
            self.load()
