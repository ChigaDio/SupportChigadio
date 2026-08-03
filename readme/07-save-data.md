# 💾 Save Data（セーブデータ）

[← README に戻る](../README.md)

対象コンポーネント: `SaveDataGrid`
バックエンド: `pythonSrc/savedata.py`, ルートは `pythonSrc/app.py`

`SystemData`（音量設定などシステム全体の設定）と `PlayerData`（プレイヤーの進行状況）の
フィールド定義を GUI から編集し、暗号化・非同期対応のセーブ/ロード基盤一式を自動生成する機能。

---

## 1. データモデル

`SaveDataGrid` はタブ切り替えで `SystemData` / `PlayerData` の 2 系統を編集します。各フィールドは以下を持ちます。

| 項目 | 説明 |
|---|---|
| `type` | 基本型・Unity 型・Enum・ClassData・ClassDataID に加え、**CustomClassData / CustomClassDataID**（`bezier` を除く）も指定可 |
| `name` | フィールド名 |
| `description` | 説明 |
| `arraySize` | 配列サイズ（0 で単一値） |

> ⚠️ **bezier（AnimationCurve）は SaveData では非対応**です。Save は Unity の `JsonUtility` ベースのシリアライズを使うため、
> `BinaryFormatter` 的な任意型シリアライズが前提の bezier 型は選択肢から除外されています
> （`customValueTypes = [t for t in custom_types if t != 'bezier']`）。一方 bit / color は `[Serializable]` 型として
> 解決されるため問題なく使用できます。

---

## 2. 生成される C# 基盤（初回起動時に自動生成）

`savedata.py` の `generate_base()` が、以下のファイルを **存在しない場合のみ** 生成します（既存の手動実装を上書きしません）。

| ファイル | 役割 |
|---|---|
| `SaveManagerCore.cs` | `BaseSingleton<SaveManagerCore>` を継承したシングルトン。`SystemSettings` / `PlayerProgress` へのアクセサ、`LoadAllDataAsync` / `SaveAllDataAsync` 等の公開 API を提供 |
| `SaveManager.cs` | 実処理本体。XOR ベースの簡易暗号化（`EncryptDecrypt`）、`UniTask.RunOnThreadPool` によるスレッドプールでの非同期読み書き、`IsSaving` / `IsLoading` の状態管理 |
| `BaseSystemData.cs` / `BasePlayerData.cs` | ユーザー拡張用の空の基底クラス |
| `SystemData.cs` / `PlayerData.cs` | 上記基底クラスを継承する具象クラス（初期状態では `seVolume` / `bgmVolume` のみ） |

### 保存フロー

1. `JsonUtility.ToJson()` でオブジェクトを JSON 文字列化 → UTF-8 バイトへ変換（`SerializeToBinary`）
2. 固定 8 バイトの XOR キーで暗号化（`EncryptDecrypt`）
3. `Application.dataPath/SaveData/{systemData|playerData}.bytes` へ書き込み

### 読み込みフロー

1. ファイルが存在すれば復号 → JSON デシリアライズ
2. 存在しなければデフォルトインスタンスを生成し、即座に保存（初回起動時の自動初期化）

すべての読み書きは `UniTask` による非同期処理で、キャンセルトークン（`CancellationTokenSource`）を
紐付けた GameObject の破棄と連動して安全にキャンセルされます。

---

## 3. API

| メソッド | パス | 用途 |
|---|---|---|
| `GET/POST` | `/api/save-data/<SystemData\|PlayerData>` | フィールド定義の取得・保存 |
| `POST` | `/api/generate-save-data/<name>` | `SystemData`/`PlayerData` クラスおよび関連コードの生成 |

---

[← README に戻る](../README.md)
