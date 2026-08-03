# 🖼️ アセット管理機能

[← README に戻る](../README.md)

対象コンポーネント: `AnimatorDataGrid` / `AnimatorDataDetailGrid`（Sound/Texture/GameObject/Material は現状 Grid 未実装、API のみ提供）
バックエンド: `pythonSrc/assets.py`（Sound/Texture/GameObject/Material）, `pythonSrc/animation.py`（Animator）,
`pythonSrc/scene.py`（Scene）, `pythonSrc/addressableInit.py`（Addressables 基盤）
ルート登録先: `pythonSrc/app.py`

---

## 1. 共通データモデル：グループ／サブグループ構造

Sound・Texture・GameObject・Material は共通の構造を持ちます。

```
{category}（Sound/Texture/GameObject/Material）
└─ groups: {
      "GroupA": {
        items: [ { name, desc, ... , subgroup: "SubGroupX" | null }, ... ],
        subgroups: ["SubGroupX", "SubGroupY", ...]   # 登録順 = SubGroup enum の ID 順
      },
      ...
   }
```

- 旧フォーマット（アイテムのリストのみ）からの自動移行処理（`migrate_groups_data` / `_migrate_group_value`）を備え、後方互換性を確保
- サブグループを削除しても所属アイテムは削除されず、「サブグループなし」に戻される
- 各グループ・カテゴリごとに Enum が自動生成・同期される（`register_enum_names`, `sync_subgroup_enum_files`）ため、
  Unity 側では `enum` を介してアセットを型安全に参照できる

### SubGroup ベース Enum の O(1) アクセス（開発中）

サブグループ単位の Enum（`generate_subgroup_enum_csharp` / `generate_subgroup_enum_details_csharp`）に対して、
`LoadSingle` / `UnloadSingle` のようなアクセサをルックアップテーブルで O(1) 化する拡張が進行中です。

---

## 2. Sound

- グループ／サブグループの追加・削除
- サウンド登録（`add_sound`）: 名前・説明・音量・種別（BGM/SE 等）・所属サブグループ
- ファイル選択（`select_file` — OS のファイルダイアログ経由でオーディオファイルを指定）、Unity プロジェクトパスの取得・接続
- 「再読み込み」（`reload_sound_file`）で参照ファイルの情報を更新
- 生成物: C#（`generate_sound_csharp`, `generate_sound_core_subgroups`）、バイナリ（`generate_sound_bin`）

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/sound` | 一覧取得 |
| `POST` | `/api/sound/add_group` `/delete_group` | グループ追加・削除 |
| `POST` | `/api/sound/add_subgroup` `/delete_subgroup` | サブグループ追加・削除 |
| `POST` | `/api/sound/add_sound` `/delete_sound` `/edit_sound` | サウンド登録・削除・編集 |
| `POST` | `/api/sound/reload_sound` | ファイル再読み込み |
| `POST` | `/api/sound/generate` | C#/バイナリ生成 |
| `GET` | `/api/sound/serve/<group_name>/<index>` | 音声ファイルの配信（プレビュー再生用） |

---

## 3. Texture

Sound と同様のグループ／サブグループ構造に加え、スプライト情報の取得（`get_sprite_info`）や
スプライト単位の Enum 生成（`generate_texture_sprite_enum`）を持ちます。

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/texture` | 一覧取得 |
| `POST` | `/api/texture/add_group` `/delete_group` `/add_subgroup` `/delete_subgroup` | グループ/サブグループ管理 |
| `POST` | `/api/texture/add_texture` `/delete_texture` `/edit_texture` `/reload_texture` | テクスチャ登録・削除・編集・再読み込み |
| `POST` | `/api/texture/generate` | C#/バイナリ生成 |
| `GET` | `/api/texture/serve/<group_name>/<index>` | 画像ファイルの配信（プレビュー用） |

---

## 4. GameObject

プレハブ／ゲームオブジェクト参照のグループ管理。構造は Sound/Texture と同様です。

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/gameobject` | 一覧取得 |
| `POST` | `/api/gameobject/add_group` `/delete_group` `/add_subgroup` `/delete_subgroup` | グループ/サブグループ管理 |
| `POST` | `/api/gameobject/add_gameobject` `/delete_gameobject` `/edit_gameobject` `/reload_gameobject` | 登録・削除・編集・再読み込み |
| `POST` | `/api/gameobject/generate` | C# 生成 |

---

## 5. Material

他のアセットと異なり **2 つの管理モード** を持ちます。

1. **通常モード** — Enum 登録・バイナリ梱包を行う、Sound/Texture 同様のフルフロー
2. **CS Only モード**（`cs_only`）— Enum への登録やバイナリ生成を一切行わず、C# クラス生成のみを行う独立した管理領域

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/material` | 一覧取得 |
| `POST` | `/api/material/add_group` `/delete_group` `/add_subgroup` `/delete_subgroup` | グループ/サブグループ管理 |
| `POST` | `/api/material/select_file` | マテリアルファイル選択 |
| `POST` | `/api/material/generate` `/regenerate` `/delete` | 生成・再生成・削除（通常モード） |
| `GET` | `/api/material/cs_only` | CS Only モードの一覧取得 |
| `POST` | `/api/material/cs_only/generate` `/regenerate` `/delete` | CS Only モードの生成・再生成・削除 |

---

## 6. Animator

Animator コントローラーに紐づく「イベント定義（型・名前・説明）」を管理する機能。`AnimatorDataGrid` / `AnimatorDataDetailGrid` として
フル実装された GUI を持つ数少ないアセットカテゴリです。

- 一覧画面: Animator の新規作成（グループ指定可）・削除・全 Animator 一括 C# 生成
- 詳細画面: イベント（型・名前・説明）の追加・削除・ドラッグ＆ドロップ並び替え、型は他の Grid と共通の Autocomplete（基本型・Unity 型・Enum・ClassData・ClassDataID）
- Animator コントローラー情報の取得（`get_animator_controller_info`）、Unity プロジェクトとの接続（`connect_to_unity` / `send_to_unity`）
- 生成物: 個別 Animator の C#（`generate_single_animator_csharp`）に加え、全 Animator をまとめる **Hub クラス**（`_generate_animator_hub_csharp_core`）

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/animator-data` | 一覧取得 |
| `POST` | `/api/animator-create` | 新規作成 |
| `PATCH` | `/api/animator-data` | 削除 |
| `POST` | `/api/generate-all-animator` | 全 Animator 一括生成 |
| `GET/POST` | `/api/animator-data/<name>` | 詳細取得・保存 |
| `POST` | `/api/generate-animator/<name>` | 指定 Animator の C# 生成 |

---

## 7. Scene

シーン一覧を管理し、Unity のビルド設定・シーンローダーと連携する機能。シーンは ClassData/Enum 側で共有される
`GameScene` という名前の Enum（C# 型名は `GameSceneID`）として実装されており、Scene 管理専用の Enum を新規に作るのではなく、
既存の Enum 基盤へ登録・同期する設計です（`sync_scene_enum` / `_ensure_scene_enum_registered`）。

- シーンの追加・削除（enumName・sceneType を指定）
- 生成物:
  - `generate_scene_list_cs` — シーン一覧の enum/リスト
  - `generate_scene_build_cs` — Unity Build Settings と連携するコード
  - `generate_scene_loader_cs` — シーン読み込み処理

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/scene/get` | シーン一覧取得 |
| `POST` | `/api/scene/add` `/delete` | シーン追加・削除 |
| `POST` | `/api/scene/generate` | C# 生成（リスト・ビルド設定・ローダー） |

---

## 8. Addressables 初期化サポート

`pythonSrc/addressableInit.py` は、Unity Addressables を利用するための **サポートライブラリ（`AdressableSupportLib/`）** を
初回起動時に自動生成します（`UniTask` + `AddressableAssets` を用いた非同期ロードのラッパー等）。他のアセットカテゴリが
アドレサブルとしてアセットをロードする際の共通基盤として機能します。

---

[← README に戻る](../README.md)
