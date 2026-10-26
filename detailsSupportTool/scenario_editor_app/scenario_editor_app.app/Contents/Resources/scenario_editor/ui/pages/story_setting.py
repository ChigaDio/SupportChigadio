"""物語設定 (ScenarioStorySettingGrid.js)。サブイベントごとに事前ロードする素材をスロットへ割り当てる。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from ...core import story_ops as S
from ..async_ import run_async
from ..widgets import common as C
from ..widgets import option_editors as OE
from .base import Page

TAB_LABELS = [("img", "画像"), ("se", "SE"), ("bgm", "BGM"), ("effect", "エフェクト")]


class SlotSection(QWidget):
    def __init__(self, page, kind):
        super().__init__()
        self.page, self.kind = page, kind
        self.has_sprite = kind == "img"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)
        card = C.Card()
        self.head = C.label("", "h2")
        card.body.addWidget(self.head)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(4)
        card.body.addLayout(self.list_box)
        card.body.addWidget(C.separator())
        card.body.addWidget(C.label("スロットを追加", "h2"))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.slot = QComboBox()
        self.slot.setMinimumWidth(150)
        self.asset = QComboBox()
        self.asset.setEditable(True)
        self.asset.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.asset.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.asset.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.asset.setMinimumWidth(300)
        self.asset.lineEdit().setPlaceholderText(f"{S.KIND_DEFS[kind]['label']}を検索")
        self.asset.currentIndexChanged.connect(self._asset_changed)
        self.sprite = QComboBox()
        self.sprite.setMinimumWidth(180)
        self.retain = QCheckBox("保持")
        self.add_btn = C.button("追加", "primary", "plus", None, self._add)
        row.addLayout(OE.BitOptionsEditor._labeled("スロット", self.slot))
        row.addLayout(OE.BitOptionsEditor._labeled(f"{S.KIND_DEFS[kind]['label']}を検索", self.asset), 1)
        if self.has_sprite:
            row.addLayout(OE.BitOptionsEditor._labeled("Sprite(任意)", self.sprite))
        row.addWidget(self.retain, 0, Qt.AlignmentFlag.AlignBottom)
        row.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignBottom)
        card.body.addLayout(row)
        lay.addWidget(card)
        lay.addStretch(1)
        self._options = []

    def refresh(self):
        p = self.page
        self._options = p.options.get(self.kind, [])
        mine = S.slots_for_kind(p.slots, self.kind)
        self.head.setText(f"割り当て済み（{len(mine)}件）")
        C.clear_layout(self.list_box)
        if not mine:
            self.list_box.addWidget(C.label("まだありません。", "muted"))
        for s in mine:
            r = QHBoxLayout()
            r.setSpacing(8)
            r.addWidget(C.Chip(s["slot"], "mono"))
            r.addWidget(QLabel(S.slot_summary(s)), 1)
            cb = QCheckBox("保持")
            cb.setChecked(bool(s.get("retain")))
            cb.toggled.connect(lambda _b, name=s["slot"]: p.toggle_retain(name))
            r.addWidget(cb)
            r.addWidget(C.icon_button("trash", "削除", lambda name=s["slot"]: p.remove_slot(name), color="#ef6b73"))
            w = QWidget()
            w.setLayout(r)
            self.list_box.addWidget(w)
        self.slot.clear()
        for n in S.available_slot_names(p.slot_defs, p.slots, self.kind):
            self.slot.addItem(n, n)
        self.asset.blockSignals(True)
        self.asset.clear()
        for o in self._options:
            self.asset.addItem(S.option_label(o), o)
        self.asset.setCurrentIndex(-1)
        self.asset.setEditText("")
        self.asset.blockSignals(False)
        self._asset_changed()
        self._update_add()

    def _asset(self):
        i = self.asset.currentIndex()
        return self.asset.itemData(i) if i >= 0 else None

    def _asset_changed(self, *_):
        a = self._asset()
        self.sprite.clear()
        self.sprite.addItem("", "")
        for sp in (a or {}).get("sprites") or []:
            self.sprite.addItem(sp, sp)
        self.sprite.setEnabled(bool(a and a.get("sprites")))
        self._update_add()

    def _update_add(self):
        self.add_btn.setEnabled(bool(self.slot.currentData()) and self._asset() is not None)

    def _add(self):
        a = self._asset()
        slot = self.slot.currentData()
        if not slot or not a:
            return
        self.page.add_slot(self.kind, slot, a, self.sprite.currentData() or "", self.retain.isChecked())
        self.retain.setChecked(False)


class VoiceSection(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        card = C.Card()
        card.body.addWidget(C.label(
            "Voice系列は個別のセリフではなく「大本」（Group + SubGroup）単位で1つだけ指定します。"
            "実際のセリフ選択（Transaction入力時）は、ここで指定したVoice系列に属するIDだけがカスケードで絞り込まれます"
            "（例: Sound_Scenario_TestScene 配下のみ選択可能になる）。", "muted", wrap=True))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.combo.setMinimumWidth(380)
        self.combo.activated.connect(self._picked)
        self.retain = QCheckBox("保持")
        self.retain.toggled.connect(self._retain)
        self.clear_btn = C.button("クリア", "danger", None, None, lambda: page.set_voice(None))
        row.addWidget(self.combo, 1)
        row.addWidget(self.retain)
        row.addWidget(self.clear_btn)
        card.body.addLayout(row)
        lay.addWidget(card)
        lay.addStretch(1)

    def refresh(self):
        p = self.page
        self.combo.blockSignals(True)
        self.combo.clear()
        for o in p.options.get("voiceSeries", []):
            self.combo.addItem(S.voice_series_label(o), o)
        sel = S.find_voice_option(p.voice_series, p.options.get("voiceSeries", []))
        i = next((k for k in range(self.combo.count()) if self.combo.itemData(k) is sel), -1) if sel else -1
        self.combo.setCurrentIndex(i)
        if i < 0:
            self.combo.setEditText("")
        self.combo.blockSignals(False)
        self.retain.blockSignals(True)
        self.retain.setChecked(bool((p.voice_series or {}).get("retain")))
        self.retain.setEnabled(p.voice_series is not None)
        self.retain.blockSignals(False)
        self.clear_btn.setEnabled(p.voice_series is not None)

    def _picked(self, i):
        o = self.combo.itemData(i)
        self.page.set_voice(S.select_voice_series(self.page.voice_series, o))

    def _retain(self, b):
        self.page.set_voice(S.set_voice_retain(self.page.voice_series, b))


class StorySettingPage(Page):
    PAGE_ID = "story_setting"

    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self.slots, self.voice_series, self.slot_defs = [], None, []
        self.options = {}
        self.dirty = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.dirty_chip = C.Chip("未保存の変更", "warn")
        self.dirty_chip.hide()
        hdr, self.title_lb = self.make_header("物語設定", None, back=self._back, widgets=[self.dirty_chip])
        root.addWidget(hdr)
        body = QVBoxLayout()
        body.setContentsMargins(20, 12, 20, 16)
        body.setSpacing(10)
        body.addWidget(C.label(
            "このサブイベント再生前に事前ロードしておく素材を、スロット単位で割り当てます。"
            "「保持」にチェックした項目は、サブイベントが切り替わってGroup/SubGroupが変わっても解放されず、次の物語設定でも再ロードされません。",
            "muted", wrap=True))
        self.err = C.Banner("", "err")
        self.err.hide()
        body.addWidget(self.err)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.save_btn = C.button("保存", "primary", "save", None, self.save)
        self.gen_btn = C.button("全サブイベント分をC#/バイナリ生成", None, "build", None, self.generate_all)
        bar.addWidget(self.save_btn)
        bar.addWidget(self.gen_btn)
        bar.addWidget(C.button("Voice専用Roleを生成", None, "build", None, self.generate_voice_role))
        bar.addStretch(1)
        body.addLayout(bar)
        self.tabs = QTabWidget()
        self.sections = {k: SlotSection(self, k) for k, _ in TAB_LABELS}
        for k, label in TAB_LABELS:
            self.tabs.addTab(self.sections[k], label)
        self.voice = VoiceSection(self)
        self.tabs.addTab(self.voice, "Voice系列")
        body.addWidget(self.tabs, 1)
        root.addLayout(body, 1)

    def _back(self):
        self.state.go("event_list")

    def page_title(self):
        return f"物語設定 {self.params.get('eventId')}/{self.params.get('subId')}"

    def can_leave(self):
        if not self.dirty:
            return True
        return C.confirm(self, "保存していない変更があります。破棄して移動しますか？", "未保存の変更", "破棄して移動", danger=True)

    def load(self, params):
        super().load(params)
        self.event_id, self.sub_id = params.get("eventId"), params.get("subId")
        self.title_lb.setText(f"物語設定: {self.event_id} / sub {self.sub_id}")
        self.err.hide()
        api = self.state.api

        def work():
            return (api.story_slot_defs(), api.get_story(self.event_id, self.sub_id), api.textures(), api.sounds(), api.gameobjects())

        def ok(r):
            defs, story, tex, snd, go = r
            self.slot_defs = defs or []
            self.slots = (story or {}).get("slots") or []
            self.voice_series = (story or {}).get("voiceSeriesId") or None
            self.options = S.build_options(tex, snd, go)
            self._set_dirty(False)
            self.refresh()

        def err(e):
            self.err.set_text(f"取得エラー: {e}")
            self.err.show()
        run_async(work, ok, err, self)

    def _set_dirty(self, d):
        self.dirty = d
        self.dirty_chip.setVisible(d)

    def refresh(self):
        for k, _ in TAB_LABELS:
            self.sections[k].refresh()
            self.tabs.setTabText(self.tabs.indexOf(self.sections[k]), f"{dict(TAB_LABELS)[k]} ({len(S.slots_for_kind(self.slots, k))})")
        self.voice.refresh()

    def add_slot(self, kind, slot, asset, sprite, retain):
        self.slots = S.add_slot(self.slots, kind, slot, asset, sprite, retain)
        self._set_dirty(True)
        self.refresh()

    def remove_slot(self, name):
        self.slots = S.remove_slot(self.slots, name)
        self._set_dirty(True)
        self.refresh()

    def toggle_retain(self, name):
        self.slots = S.toggle_retain(self.slots, name)
        self._set_dirty(True)

    def set_voice(self, v):
        self.voice_series = v
        self._set_dirty(True)
        self.voice.refresh()

    def save(self):
        body = S.save_body(self.slots, self.voice_series)
        self.save_btn.setEnabled(False)
        self.save_btn.setText("保存中...")

        def done():
            self.save_btn.setEnabled(True)
            self.save_btn.setText("保存")

        def ok(res):
            done()
            self._set_dirty(False)
            self.toast((res or {}).get("message") or (res or {}).get("error") or "保存しました", "success")
        run_async(lambda: self.state.api.save_story(self.event_id, self.sub_id, body["slots"], body["voiceSeriesId"]), ok,
                  lambda e: (done(), self.fail("保存エラー", e)), self)

    def generate_all(self):
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("生成中...")

        def done():
            self.gen_btn.setEnabled(True)
            self.gen_btn.setText("全サブイベント分をC#/バイナリ生成")
        run_async(lambda: self.state.api.generate_story_all(),
                  lambda res: (done(), self.toast((res or {}).get("message") or (res or {}).get("error") or "生成しました", "success")),
                  lambda e: (done(), self.fail("生成エラー", e)), self)

    def generate_voice_role(self):
        run_async(lambda: self.state.api.generate_story_voice_role(),
                  lambda res: self.toast((res or {}).get("message") or (res or {}).get("error") or "生成しました", "success"),
                  lambda e: self.fail("生成エラー", e), self)
