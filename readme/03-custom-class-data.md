# 🧩 Custom Class Data（拡張データ型）

[← README に戻る](../README.md)

対象コンポーネント: `CustomClassDataGrid` / `CustomClassDataDetailGrid`, `CustomClassDataIdGrid` / `CustomClassDataIdDetailGrid`
バックエンド: `pythonSrc/customclassdata.py`

Class Data / Class Data ID の **拡張版**。各フィールドに「型ごとの詳細オプション」を持たせられるのが最大の特徴で、
本ツールの中でも特に作り込まれたサブシステムです。

---

## 1. CustomClassData（フィールド定義側）

ClassData 同様「型・名前」のフィールド集合ですが、フィールドの型に応じて以下のような追加オプションを持てます。

| 型 | 概要 | オプション |
|---|---|---|
| 数値型（`int/float/double/byte/short/long`） | 通常の数値フィールド | `min` / `max`（C# の `[Range]` 属性を自動生成） |
| **bit** | オン/オフの複数ビットフラグ | 詳細は下記「Bit フィールド」参照 |
| **color** | RGBA カラー値 | `UnityEngine.Color` として保持 |
| **bezier** | 数値（int/float）用のベジェカーブ | 各キーポイントの `time` / `value` + `in`/`out` タンジェントを保持し、`UnityEngine.AnimationCurve` を生成 |
| Enum / ClassData / ClassDataID / 他の CustomClassData / Vector2 / Vector3 等 | 素の参照型として扱う | なし |
| Dictionary | 任意の型を Key/Value に持つ辞書 | 再帰的にネスト可能（`Dictionary<T, List<~>>`、`Dictionary<T, Dictionary<TR, ~>>` 等） |

### Bit フィールド（フラグ管理）

もっとも複雑な型で、以下の設計になっています。

- **サイズ決定方式 `sizeMode`**
  - `manual` — ビット数を直接指定
  - `enum` — 参照 Enum の要素数からビット数を自動算出
  - `classDataId` / `customClassDataId` — 参照テーブルの行数からビット数を自動算出
- **保持方式**: 64bit 以下は `ulong`、65bit 以上は `ulong[]` を使う専用クラス `CustomBitField` を介して保持（C# 側の型は自動判定）
- **選択モード `mode`**
  - `multiple` — 複数選択可能なフラグ集合
  - `single` — 排他選択（ラジオボタン的）
- **`allowSelectAll`** — 「全選択」ボタンの表示可否

フラグ名は `_bit_source_entries()` によって「参照している Enum / ClassDataID / CustomClassDataID の実データ」から動的に解決され（`_refresh_live_bit_flag_names`）、参照元が変更されると自動的に追従します。

さらに `_generate_bit_extension_code()` によって、フラグ操作を型安全に行うための拡張メソッド群 `{Field}BitExtensions.cs` が生成されます（例: `Has(Flag)`, `Set(Flag)`, `Clear(Flag)` に相当する操作）。

### CustomClassData の API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/custom-class-data` | 一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/custom-class-data/<name>` | フィールド定義の取得・保存・削除 |
| `GET` | `/custom-class-data-type-options` | 型選択肢一覧（CustomClassData / CustomClassDataID / カスタム値型の候補をまとめて返す。他 Grid の型 Autocomplete からも利用） |
| `POST` | `/generate-custom-class/<name>` | C# クラス生成 |

---

## 2. CustomClassDataID（ID引きテーブル側）

ClassDataID の拡張版で、列（column）の型に CustomClassData を指定できます。
セル編集時には、CustomClassData 側で定義したオプション（`min/max`、bit、color、bezier）に応じた専用エディタが自動的に選ばれ、
フロントエンドにはそのためのスキーマが提供されます。

- `ClassDataIdDetailGrid.js` と共通の `BitFieldEditor` / `ColorFieldEditor` / `BezierFieldEditor` を利用
- タグ管理（追加・改名・削除・行への割当）を装備
- 「Binary生成」「C#ヘッダー生成」を一覧画面から直接実行可能

### CustomClassDataID の API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST/PATCH` | `/custom-class-data-id` | 一覧取得・新規作成・削除 |
| `GET/POST/DELETE` | `/custom-class-data-id/<name>` | 行データ取得・保存・削除 |
| `POST` | `/generate-custom-class-data-id/<name>` | C# クラス生成（`generate_custom_class_data_id_cs`） |
| `POST` | `/generate-all-custom-binary` | 全 CustomClassDataID の一括バイナリ生成 |
| `POST` | `/generate-custom-table-id` | テーブル ID 定義生成 |
| `POST` | `/generate-custom-cs-header` | C# ヘッダー一括生成 |
| `GET/POST/PATCH` | `/custom-class-data-id-tags` | タグ管理（一覧・追加・削除） |
| `PUT` | `/custom-class-data-id-tags/<tag_id>` | タグ改名 |
| `PUT` | `/custom-class-data-id/<name>/tag` | 行タグ割り当て |

---

## 3. バイナリシリアライズ設計

`_write_custom_single_value()` が **Bit / Color / Bezier を含む全カスタム型シリアライズの単一の実装源**として扱われ、
他の書き込み処理（`_write_custom_schema_value`, `_write_custom_field_value`）はここに委譲します。この一元化により、
「新しい型を 1 箇所直せば全テーブルに反映される」設計になっています（`generate_custom_binary_data` → `.bytes` 出力）。

生成される C# 側の実行時基盤は ClassDataID と対になる構成です。

- `{name}Table.cs` — テーブル本体
- `CustomClassDataHeader.cs` — ヘッダー情報
- `CustomClassDataIDCore.cs` — コア読み込みロジック
- `SupportFiles.cs` へのパッチ（`_ensure_support_files_custom_entries`）— 生成されたバイナリファイルへの参照を自動登録

---

## 4. Dictionary 型のネスト設計

`generate_csharp_field`（`data_utils.py`）と `_dict_cs_type_name` / `_dict_read_single_stmts` / `_dict_read_dictionary_stmts` の組み合わせにより、
Dictionary の Value 部分が「単一値」でも「別の Dictionary」でも再帰的に解決される設計です。フロント側も `DictionaryOptionsEditor` が再帰コンポーネントとして実装されており、
任意の深さのネストを GUI から編集できます。

---

[← README に戻る](../README.md)
