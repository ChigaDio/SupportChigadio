# 🗂️ マスタデータ機能

[← README に戻る](../README.md)

対象コンポーネント: `EnumIdGrid` / `EnumDetailGrid`, `ClassDataGrid` / `ClassDataDetailGrid`,
`ClassDataIdGrid` / `ClassDataIdDetailGrid`, `ClassDataMatrixIdGrid` / `ClassDataMatrixIdDetailGrid`,
`ConstClassDataGrid` / `ConstClassDataDetailGrid`
バックエンド: `pythonSrc/class_data.py`, `pythonSrc/class_data_id.py`, `pythonSrc/matrix.py`, `pythonSrc/app.py`（ConstClassData）

---

## 1. Enum ID

Unity 側で使う `enum` を GUI 上で定義・並び替え・生成できる機能。

- **一覧画面（`EnumIdGrid`）**: Enum の作成・削除
- **詳細画面（`EnumDetailGrid`）**:
  - 行（Property / Value / Description）の追加、ドラッグ＆ドロップによる並び替え
  - 並び替えると `value` が **1 始まりの連番** に自動採番される
  - 「デフォルト作成」で `{name}_{index}` という名前の行を指定数だけ一括生成
  - 保存前後で `description` の差分をハイライト表示（`originalData` との比較）
  - 「C#生成」ボタンで `{name}ID.cs` を出力（`None = 0` を先頭に、末尾に `Max` 値を自動付与）

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/api/enum-id` | Enum 一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/api/enum/<name>` | Enum 詳細（行データ）取得・保存・削除 |
| `POST` | `/api/generate-enum/<name>` | 指定 Enum の C# 生成 |
| `POST` | `/api/generate-all-enums` | 全 Enum の C# 一括生成 |

---

## 2. Class Data

フィールド構成（型・名前・説明）のみを持つ、いわば「構造体の設計図」。ClassDataID や他のテーブルから型として参照される。

- 一覧画面から新規クラスを作成し、詳細画面でフィールドを編集
- フィールド型には基本型（`int/float/bool/string/double/byte/char/short/long/decimal/object`）、Unity 型（`Vector3` 等）、Enum、他の ClassData / ClassDataID を指定可能

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/api/class-data` | ClassData 一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/api/class-data/<name>` | ClassData 詳細取得・保存・削除 |
| `POST` | `/api/generate-class/<name>` | 指定 ClassData の C# クラス生成 |
| `POST` | `/api/generate-all-cs-header` | 全 ClassData/ClassDataID の C# ヘッダー一括生成 |

---

## 3. Class Data ID（ID引きテーブル）

「ID + 名前」を持つ行の集合として、複数のフィールドを持つマスタテーブルを定義する、本ツールの中核機能。

### 主な UI 機能（`ClassDataIdDetailGrid`）
- 列（フィールド）の追加・型変更・削除
- セル編集用の専用エディタ:
  - **BitFieldEditor** / **ColorFieldEditor** / **BezierFieldEditor**（CustomClassData 由来の型を共有）
  - **Dictionary** 型のネスト編集（`Dictionary<T, List<~>>` や `Dictionary<T, Dictionary<TR, ~>>` など任意の入れ子に対応）
  - ネストしたデータのダイアログ編集・ミニテーブルプレビュー
  - `EnumSelectEditor`（ドロップダウンの意図しないクローズを防ぐ `open` 制御付き）
- 行単位でのタグ付け（後述のタグ管理と連携）
- 大量データ編集時のパフォーマンス最適化（ネストエディタの状態をローカルコンポーネントへ分離し、キー入力ごとの親再レンダリングを回避）

### タグ管理
ClassDataID・CustomClassDataID・ClassDataMatrixID はいずれも **タグ機能** を持ち、行を任意のグループ（カテゴリ）に分類できます。タグの追加・改名・削除、行への割り当てが GUI から可能です。

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/api/class-data-id` | ClassDataID 一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/api/class-data-id/<name>` | 行データの取得・保存・削除 |
| `POST` | `/api/generate-class-data-id/<name>` | 指定テーブルの C# クラス生成 |
| `POST` | `/api/generate-binary/<name>` | 指定テーブルのバイナリ（`.bytes`）生成 |
| `POST` | `/api/generate-all-binary` | 全 ClassDataID の一括バイナリ生成 |
| `POST` | `/api/generate-table-id` | テーブル ID 定義の生成 |
| `GET/POST/PATCH` | `/api/class-data-id-tags` | タグ一覧・新規作成・削除 |
| `PUT` | `/api/class-data-id-tags/<tag_id>` | タグの改名 |
| `PUT` | `/api/class-data-id/<name>/tag` | 行へのタグ割り当て |

生成されるバイナリは Unity 側で `BaseClassDataID` / `BaseTable` / `BaseClassDataRow` を継承したロード処理から読み込まれ、実行時に O(1) 相当のルックアップテーブルとして展開されます。

---

## 4. Class Data Matrix ID（マトリクス形式データ）

行・列の両方をキー（Enum または ClassDataID）から選べる、2 次元テーブル形式のマスタデータ。

- 行キー・列キーのどちらも **Enum** だけでなく **ClassDataID** を指定可能
- タグ管理（Class Data ID と同様の仕組み）
- 「メモリビューア生成」機能で、生成済みバイナリの構造を確認できるビューアコードを出力

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/api/class-data-matrix-id` | 一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/api/class-data-matrix-id/<name>` | データ取得・保存・削除 |
| `POST` | `/api/generate-class-data-matrix-id/<name>` | C# クラス生成 |
| `POST` | `/api/generate-binary-matrix/<name>` | バイナリ生成 |
| `POST` | `/api/generate-all-binary-matrix` | 全マトリクスの一括バイナリ生成 |
| `POST` | `/api/generate-all-cs-matrix-header` | 全マトリクスの C# ヘッダー一括生成 |
| `POST` | `/api/generate-matrix-table-id` | マトリクステーブル ID 生成 |
| `POST` | `/api/generate-class-data-memory-viewer` | メモリビューアコード生成 |
| `GET/POST/PATCH` | `/api/class-data-matrix-id-tags` | タグ管理 |
| `PUT` | `/api/class-data-matrix-id-tags/<tag_id>` | タグ改名 |
| `PUT` | `/api/class-data-matrix-id/<name>/tag` | 行タグ割り当て |

---

## 5. Const Class Data（定数クラス）

`int / uint / float / vector2 / vector3 / string` の定数値を、コメント付きで管理し、C# の `static class` として生成する機能。

### バリデーション
- `int`: `^-?\d+$` のみ許可
- `uint`: `^\d+$` のみ許可（符号・小数不可）
- `float`: `^-?\d+(\.\d+)?$` のみ許可
- `vector2` / `vector3`: 各成分が上記 `float` 相当のバリデーションを通過する必要あり
- 定数名は英数字とアンダースコアのみ、重複不可
- コメントは必須項目

### C# 生成ルール

| 型 | 生成される宣言 |
|---|---|
| `int / uint / float / string` | `public const {型} {名前} = {値};` |
| `vector2 / vector3` | `public static readonly Vector2/Vector3 {名前} = {値};`（`const` にできないため） |

出力ファイル名は `{name}ConstData.cs`、名前空間は `GameCore.Consts`。

### API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/api/const-class-data` | 一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/api/const-class-data/<name>` | 定数リストの取得・保存・削除 |
| `POST` | `/api/generate-const-class/<name>` | 指定 ConstClass の C# 生成 |
| `POST` | `/api/generate-all-const-class` | 全 ConstClass の一括生成 |

---

[← README に戻る](../README.md)
