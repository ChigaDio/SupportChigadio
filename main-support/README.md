# Unity Data Tool

> Unity プロジェクトのデータ定義・アセット・シナリオを、一つの管理画面から編集して生成するローカルツール。

| 領域 | 主な機能 | ガイド |
| --- | --- | --- |
| データ定義 | Enum / ClassData / ID・Matrix・定数 / State / Behavior / SaveData | [データ生成](docs/features/data-generation.md) |
| アセット | Sound / Texture / GameObject / Material / Animator / Scene | [アセット管理](docs/features/assets.md) |
| シナリオ | ロール、イベント、遷移、条件、バイナリ出力 | [シナリオ](docs/features/scenario.md) |
| チーム運用 | 認証・権限、バージョン、ログ、配布、告知 | [運用機能](docs/features/operations.md) |

## クイックスタート

Node.js（npm）と Python 3 を用意します。

```powershell
npm install
pip install Flask psutil websockets
npm run build
python app.py Normal
```

画面は `http://localhost:8000` で開きます。`Normal` はローカルで全編集を許可し、`Server` はログインと権限管理を有効にします。起動モードを省略した場合はダイアログで選択します。

> `npm start` は React の UI だけを開発用に起動します。通常利用では、`npm run build` の後に Flask を起動してください。

## ドキュメント

- [アーキテクチャ](docs/architecture.md) — 全体の構造とソースの対応
- [データ生成](docs/features/data-generation.md) — 型・テーブル・状態・生成物
- [アセット管理](docs/features/assets.md) — Unity アセットの整理と生成
- [シナリオ](docs/features/scenario.md) — ロール、イベント、遷移、バイナリ
- [運用機能](docs/features/operations.md) — 認証、履歴、配布、告知

## ディレクトリ早見表

```text
main-support/
├─ app.py          # Flask の起動・統合 API
├─ pythonSrc/      # 生成ロジック、Flask Blueprint、運用サービス
├─ src/            # React 管理画面
├─ data/           # 編集データと生成物
└─ build/          # npm run build の出力（Flask が配信）
```
