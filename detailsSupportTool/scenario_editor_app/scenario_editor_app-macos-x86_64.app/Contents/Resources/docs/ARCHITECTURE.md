# Scenario Editor (PySide6) — 設計書

元: React 版シナリオエディタ(`js_ref/src/*.js`) + Flask(`js_ref/src/scenario.py`)。
目標: **同じ Flask API に接続する PySide6 デスクトップアプリ**。元の JS が持つ全機能を移す。

## 大原則

1. **データ形は JS と完全に同じ**。サーバーの JSON を、そのまま Python の dict/list/str/int/float/bool/None で扱う。
   キー名(camelCase のまま: `uniqueId`, `branchType`, `arraySize` ...)は変えない。クラスにしない。
2. **関数名は機械的に変換**: `tokenizeLine` → `tokenize_line`, `compileDocument` → `compile_document`,
   `renumberDuplicateNodeIds` → `renumber_duplicate_node_ids`。定数は大文字のまま(`INDEX_TYPES` は `set`)。
   JS の戻り値オブジェクトは **dict(キー名そのまま)** で返す。`from` は Python 予約語なので、
   DSL のトークン等の dict キーは `"from"`(文字列キー)のまま、属性アクセスが必要なクラス(`DslIssue`)だけ `from_`。
3. **GUI(Qt)に依存しないコアと、Qt の層を分ける**。`core/` と `api/client.py`, `api/lookups.py` は
   PySide6 を import してはならない(ヘッドレスでテストするため)。
4. **正しさは元の JS との差分テストで担保する**: `js_ref/` の ESM 版 JS を Node で実行し、同じ入力で
   Python 実装と結果を比較する(`tests/` の `unittest`。pytest は無い)。JS 参照の呼び出しは
   `tests/jsref.py` の `run_js(module, fn, *args)` を使う(forks が最初に作る人が担当 → F1)。
5. テストは標準の `unittest` のみ。`python -m unittest discover -s tests` で全部通ること。
6. 日本語の UI 文言は元の JS の文言をそのまま使う(ボタン名・ツールチップ・エラー文)。

## パッケージ構成

```
scenario_editor_app/
  main.py                         起動 (QApplication, 接続先URL設定)
  scenario_editor/
    core/                         ← Qt 非依存・純Python
      dsl.py                      scenarioTransactionDsl.js 全体
      index_tools.py              scenarioIndexTools.js
      node_utils.py               scenarioNodeUtils.js
      diff.py                     scenarioDiff.js
      validation.py               scenarioValidation.js
      subgroup_setting.py         scenarioSubGroupSetting.js のうち純粋ロジック
      presets.py                  scenarioRolePresets.js (保存先は localStorage ではなく設定フォルダのJSON)
      transition_ops.py           ScenarioEventTransition.js の純粋ロジック (後述)
    api/
      client.py                   ApiClient: 全エンドポイントの薄いラッパ(同期, urllib)
      lookups.py                  LookupCache: enum/class_data/sound/matrix... 取得+キャッシュ
    ui/                           ← Qt 層
      async_.py                   run_async(fn, on_ok, on_err) (QThreadPool)
      theme.py                    ダーク/ライトの QSS + アイコン
      app_state.py                AppState: ApiClient, LookupCache, 設定, signals
      main_window.py
      widgets/                    再利用部品 (role_form.py, dsl_editor.py, ...)
      pages/                      画面 (event_list.py, transition.py, role_list.py, ...)
      dialogs/                    ダイアログ
  tests/ (mock_server.py, jsref.py, test_*.py)
  js_ref/src/                     元の JS / scenario.py (参照用。import に .js を付け済みで Node ESM で動く)
```

## API クライアント (`api/client.py`)

`ApiClient(base_url)`。同期。失敗は `ApiError(status, message, body)` を投げる。
JS が `fetch` している全エンドポイントを 1 メソッド 1 対 1 で提供する(メソッド名は snake_case):

- イベント: `list_events()`, `create_event(body)`, `update_event(id, body)`, `delete_event(id)`, `copy_event(id, body)`,
  `create_sub(event_id, body)`, `update_sub(event_id, sub_id, body)`?, `delete_sub(event_id, sub_id)`, `copy_sub(event_id, sub_id, body)`
- 遷移: `get_transition(event_id, sub_id)` → `(dict, rev)`(`X-Sub-Rev` ヘッダ), `save_transition(event_id, sub_id, nodes, edges)`,
  `get_subgroup(event_id, sub_id, parent_id)`, `save_subgroup(...)`, `save_role_data_batch(event_id, sub_id, updates)`,
  `get_rev(event_id, sub_id)`, `save_role(...)` (`.../transition/{nodePath}/role`)
- 操作: `fix_all_events()`, `generate_all_event_bin()`, `migrate_legacy_events()`
- Role 定義: `list_roles()`, `create_role()`, `delete_role(name)`(`DELETE /api/scenario-role/{name}` と `PATCH /api/scenario-role`)、
  `get_role(name)`/`save_role_definition(...)`、`role_form_schema(name)`、`update_role_tags(name, tags)`(`PUT /api/scenario-role/tags`)
- サブグループ設定: `/api/scenario-subgroup-setting` (GET/POST), `/form-schema`, `/field-default`, `/defaults`, `/generate`, `/sync`
- マスタ: `enum`, `enum-id`, `class-data`, `class-data-id`, `custom-class-data-type-options`, `class-data-matrix-id/{name}`, `sound`, `texture`, `gameobject`
- ストーリー設定: `/api/scenario-event/{e}/sub/{s}/story` (GET/POST), `/api/story-setting/slot-defs`, `/generate`, `/generate-voice-role`
- 各メソッドの URL・HTTP メソッド・ボディ・戻り値は **JS の呼び出し側と scenario.py を読んで決める**。
  scenario.py の `register_*_routes` に無いルートは(app.py 側にあり受領していない)呼び出し側 JS から推定し、
  推定したものには docstring に `# inferred from <file>:<line>` を書く。

## LookupCache (`api/lookups.py`)

BaseRoleInputForm / ScenarioEventTransition / ScenarioRoleDetailGrid / ScenarioStorySettingGrid が行っている
マスタ取得(enum・class_data・class_data_id・matrix・sound・scenario-event・custom class)を 1 か所にまとめ、メモ化する。
`invalidate(kind=None)` あり。Qt 非依存。

## Qt 層の共通部品の契約 (他の担当が前提にしてよい)

```python
# ui/app_state.py
class AppState(QObject):
    api: ApiClient
    lookups: LookupCache
    settings: dict            # 接続先URL, テーマ, 最近開いたSub, ウィンドウ配置
    toast = Signal(str, str)  # (message, level: 'info'|'success'|'warning'|'error')
    navigate = Signal(str, dict)   # ('event_list'|'transition'|'role_list'|'role_detail'|'subgroup_setting'|'story_setting', params)
    def show_toast(self, msg, level='info'): ...
# ui/async_.py
def run_async(fn, on_ok=None, on_err=None, parent=None): ...   # fn はワーカースレッド、コールバックは UI スレッド

# ui/widgets/role_form.py  (BaseRoleInputForm.js + RoleInputFactory.js)
class RoleForm(QWidget):
    changed = Signal(dict)                         # form_data 全体 (JS の onChange と同形)
    def __init__(self, role_name, schema, state: AppState, initial: dict | None = None, parent=None)
    def form_data(self) -> dict
    def set_form_data(self, data: dict) -> None
    def validate(self) -> list[dict]               # JS の検証と同じ

# ui/widgets/dsl_editor.py  (ScenarioTransactionCodeEditor.js)
class DslEditor(QWidget):
    textChanged = Signal()
    def __init__(self, state, parent=None)
    def set_text(self, s) ; def text(self) -> str
    def set_schemas(self, role_schemas: dict, setting_schema: list | None) -> None
    def diagnostics(self) -> list[dict]
    # Ctrl/Cmd+Alt+G / H、Utils メニュー、インデックス一括調整ダイアログ、Ctrl+Z

# ui/dialogs/diff_dialog.py   : DiffPreviewDialog(diff: dict, setting_changes: list, parent) -> exec() -> bool
# ui/dialogs/index_tools_dialog.py : IndexToolsDialog(...)
```

## 並行開発の分担 (バッチ1: Qt 非依存)

- **F1** `core/dsl.py` + `tests/jsref.py` + `tests/test_dsl.py`
- **F2** `core/{index_tools,node_utils,diff,validation,subgroup_setting,presets}.py` + tests
- **F3** `api/client.py`, `api/lookups.py`, `tests/mock_server.py`(Flask 製の簡易モック。実サーバーと同じ形の JSON を返す), tests
- **F4** `core/transition_ops.py` + tests: `ScenarioEventTransition.js` の **画面に依存しない全ロジック**
  (`buildEditLinesForSub` / `parseEditSections` / `applyEditSections` / `mergeLocalRoleDataIntoTree` /
  `withFieldTypes` / ノード・エッジ操作 / 重複 ID 振り直し連携 / クリップボード・プリセット適用 / Undo-Redo スタック /
  保存ペイロード組み立て / 検証連携 / フィルタ・自動色分けの純関数)。React の state に埋まっている純粋な計算は関数に切り出す。

バッチ2 (Qt): U1 土台(theme, async_, app_state, main_window, 共通部品) → 並行で U2 RoleForm, U3 一覧系ページ,
U4 DslEditor+ダイアログ, U5 遷移エディタ。

## 品質ゲート

- `python -m unittest discover -s tests` が全部通る。
- Qt 層は PySide6 が無い環境でも `python -m py_compile` が通り、`tools/lint_names.py`(未定義名チェック)が通る。
- 元の JS にある機能を取りこぼさない。取りこぼしは `docs/PORTING_GAPS.md` に理由つきで必ず書く。
