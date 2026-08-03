# 🎬 Scenario（会話・分岐シナリオ）

[← README に戻る](../README.md)

対象コンポーネント: `ScenarioRoleGrid` / `ScenarioRoleDetailGrid`, `ScenarioEventGrid` / `ScenarioEventTransition`,
`ScenarioConditionsGrid`, `Flow.js`（遷移図）
バックエンド: `pythonSrc/scenario.py`（本体ロジック）、ルートは `pythonSrc/app.py` に実装

会話イベント・分岐演出などのシナリオを、「ロール（役割）」「イベント」「条件」の 3 要素で構築するシステムです。

---

## 1. Scenario Role（ロール）

シナリオ上で発生する「アクション単位」の型定義です。例えば「キャラクターを喋らせる」「画面を揺らす」といった
個々の演出アクションをロールとして定義し、フィールド（型・名前・説明）を持たせます。

- **branchType**: `General`（通常アクション） / `Branch`（分岐アクション）の 2 種類
  - `Branch` の場合、生成される Action クラスは `BaseScenarioRoleBranchAction<T>` を継承
  - それ以外は `BaseScenarioRoleAction<T>` を継承
- ロールのフィールド型には、基本型・Unity 型・Enum・ClassData・ClassDataID に加え、
  **CustomClassData / CustomClassDataID（bit・color・bezier・dictionary 含む）** も指定可能

### C# 生成物（`/api/generate-scenario-role/<name>`）

| ファイル | 内容 |
|---|---|
| `{name}RoleData.cs` | `BaseScenarioRoleData` を継承したデータクラス。`ReadBinary()` でバイナリ読み込みを実装 |
| `{name}RoleAction.cs` | `OnInitialize/OnExecute/OnFinalize`（同期・非同期両方）を持つ Action クラスの雛形。既存ファイルがある場合は上書きしない（手動実装を保護） |
| `ScenarioRoleFactory.cs` / `ScenarioRoleID.cs`（enum） | 全ロールを登録するたびに再生成されるファクトリ・enum |

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/api/scenario-role` | ロール一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/api/scenario-role/<name>` | ロールのフィールド定義取得・保存・削除 |
| `POST` | `/api/generate-scenario-role/<name>` | ロールの C# 生成（Data/Action/Factory） |
| `GET` | `/api/role-form-schema/<roleName>` | ロールのフィールド定義から **動的フォームスキーマ** を生成（後述） |

### ロールフォームスキーマの自動生成

`generate_role_form_schema()` は、ロールが持つフィールド定義から「イベントエディタ上でそのロールの値を入力するための
フォーム構造」を動的に組み立てます。

- Enum 型なら選択肢一覧を実データから解決
- CustomClassData 型ならネストしたフィールド（`subFields`）を **最大深度（デフォルト 3）まで再帰的に展開**
- bit / color / bezier / dictionary はそのまま `options` を引き渡し、フロント側の専用エディタに委譲
- ClassData 型（ネストしたクラス）も同様に再帰的にサブフィールドを展開

これにより、ロール定義を変更するだけで、イベントエディタ側のロール入力フォームが自動的に追従します。

---

## 2. Scenario Event（イベント）

「会話イベント」や「演出イベント」の単位。1 つのイベントは複数の **サブイベント（subEvents）** を持ち、
各サブイベントはさらに **ノード・エッジのグラフ構造（transition）** で分岐/遷移を表現します。

### データ構造

```
ScenarioEvent（イベント本体）
└─ subEvents: [{ subId, name }, ...]
    └─ subgroups[subId] = { nodes: [...], edges: [...] }   ← 遷移グラフ
        └─ 各 node は data.roles（そのノードで実行するロールのインスタンス配列）を持つ
        └─ ノードはさらに data.subgroups[nodeId] として "サブグループ"（ネストした遷移グラフ）を持てる
```

- サブグループはノードの中にさらに遷移グラフを埋め込む仕組みで、**イベントの中に入れ子のフロー**を作れます
- 各ノードにロールを追加すると `roles` 配列にエントリが積まれ、`/api/save-role-data/...` でロールごとの入力値（`formData`）を保存

### 遷移図エディタ（`ScenarioEventTransition.js` / `Flow.js`）
React Flow を用いてノード・エッジをドラッグ＆ドロップで編集できるビジュアルエディタです。

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST` | `/api/scenario-event` | イベント一覧取得・新規作成 |
| `PATCH/DELETE` | `/api/scenario-event/<id>` | イベント更新・削除 |
| `POST` | `/api/scenario-event/<id>/sub` | サブイベント追加 |
| `PATCH/DELETE` | `/api/scenario-event/<id>/sub/<subId>` | サブイベントの改名・削除 |
| `GET/POST` | `/api/scenario-event/<eventId>/sub/<subId>/transition` | サブイベントの遷移グラフ（nodes/edges）取得・保存 |
| `GET/POST` | `/api/scenario-event/<eventId>/sub/<subId>/transition/<parentId>/subgroup` | ノード内のネストした遷移グラフ（サブグループ）取得・保存 |
| `POST` | `/api/scenario-event/<eventId>/sub/<subId>/transition/<nodeId>/role` | ノードへのロール割り当て |
| `POST` | `/api/save-role-data/<eventId>/<subId>/<nodeId>/<roleId>` | ノード上の特定ロールインスタンスへの入力値保存 |
| `POST` | `/api/fix-all-events` | 全イベントデータの整合性修復（`fix_all_events` / `fix_roles`） |
| `POST` | `/api/generate-all-event-bin` | 全イベントのバイナリ一括生成 |

### バイナリ生成

`generate_all_event_bin()` は各イベント・サブイベント・ノード・ロールを走査し、`write_7bit_encoded_int` による可変長整数エンコードを交えた
コンパクトなバイナリフォーマットで `.bytes` を出力します。ロールの各フィールド値は `pack_value` / `write_field_value` によって、
CustomClassData を含む全型に対応した形でシリアライズされます。

---

## 3. Scenario Conditions

シナリオの分岐条件を管理する機能です（`ScenarioConditionsGrid`）。現状は他カテゴリと同様の CRUD 基盤の上に、
条件式の内容を今後拡張していく土台として用意されています。

---

[← README に戻る](../README.md)
