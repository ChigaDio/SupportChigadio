# 🔄 State（ステートマシン）と Behavior Tree

[← README に戻る](../README.md)

対象コンポーネント: `StateGrid` / `StateDetailGrid`, `BehaviorGrid` / `BehaviorDetailGrid`
バックエンド: `pythonSrc/state.py`, `pythonSrc/behavior.py` / `pythonSrc/behavior_routes.py`

---

## 1. State（ステートマシン）

ゲーム内の状態遷移（プレイヤーステート、UI ステート等）を GUI 上で定義し、Unity 側の実行クラス一式を自動生成する機能。

### グループと ID 管理
- ステートは「グループ（`state_list.json` に登録される名前）」単位で管理され、グループの追加/削除の度に
  `regenerate_state_group_id()` が `StateGroupID.cs` を再生成し、C# 側の基準 ID を常に同期します。

### 生成されるクラス群

| ファイル | 役割 |
|---|---|
| `{name}StateID.cs` | ステートの enum ID（`generate_state_id`） |
| `{name}StateManagerData.cs` | ステート共有データ（`generate_state_manager_data`） |
| `{name}{label}StateBranch.cs` | 分岐条件クラス（`generate_state_branch`） — 複数の遷移先を持つステートの分岐ロジック |
| `{name}{label}State.cs` | 個々のステート実行クラス（`generate_state_classes`） |
| コントロールクラス | ステートマシン全体の実行制御（`generate_control_classes`） |

### ライフサイクル（Enter/Update/Exit 等）の同期/非同期切り替え

各ステートノードは `lifecycle` 設定（`{ enter: {sync, async}, update: {...}, exit: {...} }` 等）を持ち、
デフォルトから変更された項目だけが `UseXxxSync` / `UseXxxAsync` の `override` プロパティとして書き出されます
（`_build_lifecycle_block`）。

重要な設計ポイントとして、**既存の手動実装済み `.cs` ファイルを壊さずに差分更新**できるよう、
目印コメント `// __LIFECYCLE_OVERRIDES_START__` 〜 `// __LIFECYCLE_OVERRIDES_END__` で挟まれたブロックだけを
`ensure_lifecycle_in_state_class()` が書き換えます。マーカーが無い旧形式のファイルにはブロックを新規挿入します。

同様に `ensure_branchnext_in_state_class()` が、遷移先が 2 つ以上ある場合にのみ `BranchNextState()` を
自動的に追加／削除します（1 つ以下に戻ったら自動的に取り除かれる）。

### 分岐スイッチの 3 モード

`_write_branch_switch_cases()` が、以下 3 つの実行モードに対応するスイッチ文を **共通ロジックから生成**します。

- `BranchState()` — 同期のみ（`state.Exit()` → `state.Enter()`）
- `BranchStateAsync()` — 非同期のみ
- `BranchStateCombined()` — 同期・非同期を同時に扱う

### コードジャンプ機能

`/api/open-code/<state_name>/<node_label>` により、GUI 上のノードから対応する `.cs` ファイルを
VSCode / Visual Studio で直接開くことができます（`psutil` でエディタプロセスの起動状況を確認）。

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/api/state-data` | ステートグループ一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/api/state-data/<name>` | ステート定義（ノード/遷移）取得・保存・削除 |
| `POST` | `/api/generate-state/<name>` | 上記 C# クラス一式の生成 |
| `GET` | `/api/open-code/<state_name>/<node_label>` | 対応する `.cs` をエディタで開く |

---

## 2. Behavior Tree（AI ビヘイビアツリー）

GUI 上でノードをグラフとして組み立て、Unity 向けの汎用ビヘイビアツリー実行コードを生成する機能。

### 対応ノードタイプ

| ノードタイプ | 説明 |
|---|---|
| `root` / `sequence` | 子を順番に実行し、いずれかが失敗すると失敗を返す（`SequenceNode`） |
| `selector` | 子を順番に試し、いずれかが成功すると成功を返す（`SelectorNode`） |
| `parallel` | 複数の子を並行実行。成功/失敗ポリシー（`ALL`/`ANY` 等）を指定可能（`ParallelNode`） |
| `race` | 複数の子を並行実行し、最初に完了したものを採用（`RaceNode`） |
| `repeater` | 指定回数繰り返す（`RepeaterNode`） |
| `delay` | 指定秒数待ってから実行（`DelayNode`） |
| `timeout` | 指定秒数でタイムアウトさせる（`TimeoutNode`） |
| `inverter` | 子の成否を反転する（`InverterNode`） |
| `failer` | 常に失敗を返す（`FailerNode`） |
| `repeatUntilSuccess` | 成功するまで繰り返す（`RepeatUntilSuccessNode`） |
| `limiter` | 実行回数の上限を設ける（`LimiterNode`） |
| `custom`（action / condition） | ユーザー定義のカスタムノード。`{name}{custom}ActionNode` / `{name}{custom}ConditionNode` として生成 |
| `blackboard...` | Blackboard（ツリー間で共有する変数領域）の値を条件判定するノード |

全ノードは `<{name}BehaviorBlackboard, {name}BehaviorID>` のジェネリクスで統一されており、
`resetType`（ノードの状態リセットタイミング）も各ノードで指定可能です。

### 生成物

| ファイル | 内容 |
|---|---|
| `{name}BehaviorTree.cs` | ツリー構築コード（`generate_behavior_tree`） |
| `{name}BehaviorID.cs` | ノード ID の enum（`generate_custom_id_code`） |
| `{name}{custom}ActionNode.cs` / `{name}{custom}ConditionNode.cs` | カスタムノードの雛形（`generate_custom_node`） |
| カスタム条件・Blackboard 関連クラス | `generate_custom_condition`, `generate_custom_blackboard` |

カスタムアクション/条件ノードは、他のテーブル系機能と同様に基本型・Unity 型・Enum・ClassData・ClassDataID を
フィールド型として使用できます（`generate_custom_condition` / `generate_custom_blackboard` が `get_type_lists()` を
そのまま利用）。

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/behavior-data` | 一覧取得 |
| `POST` | `/api/behavior-data` | 新規作成 |
| `DELETE` | `/api/behavior-data/<name>` | 削除 |
| `GET` | `/api/behavior-data/<name>` | 詳細取得 |
| `PUT` | `/api/behavior-data/<name>` | 詳細保存 |
| `POST` | `/api/behavior-generate/<name>` | C# 一式の生成 |

---

[← README に戻る](../README.md)
