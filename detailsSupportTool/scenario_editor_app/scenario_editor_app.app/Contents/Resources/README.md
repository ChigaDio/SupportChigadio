# Scenario Editor (PySide6)

Web 版シナリオエディタ(JS)のデスクトップアプリ版。既存の Flask サーバー(`scenario.py` / `app.py`)に
API 経由で接続するクライアントで、JS 側にある機能(イベント / Role / Role 詳細 / ストーリー設定 /
遷移ブロックエディタ / DSL テキスト編集 / インデックス操作 / プリセット / 差分プレビュー / CSV 入出力 ほか)を移植しています。

> **重要: この Qt UI は、作成環境に PySide6 を入れられなかったため一度も起動していません。**
> 実機での見た目・操作の確認は未実施です(下の「検証状況」参照)。初回起動で不具合が出る可能性があります。

## 使い方
```bash
pip install -r requirements.txt        # PySide6 (+ テスト用 Flask)
# 1) 既存の Flask サーバーを起動しておく
# 2) アプリを起動
python main.py                          # 接続先は左下の「● 接続中」から変更可
python main.py --url http://127.0.0.1:5000 --light --dir ./appdata
```
サーバーなしで画面だけ試すモック: `python tests/mock_server.py 5000` を起動して `--url http://127.0.0.1:5000`。

設定(接続先・テーマ・最近開いたもの・ノード色・プリセット・コピー中の Role など)は `--dir`(既定はユーザーの設定フォルダ)内の JSON に保存されます。
Web 版が localStorage に持っていた値はここに置き換えています。

## 画面
| ページ | 主な機能 |
|---|---|
| イベント | 一覧 / 作成 / 編集 / 削除(参照チェック) / 検索 |
| Role | 一覧 / 作成 / 削除 / タグ |
| Role 詳細 | フィールド編集(型別エディタ) / デフォルト値 / オプション |
| サブグループ設定 | スキーマ編集 / プリセット |
| ストーリー設定 | スロット定義(img / sound_se / sound_bgm / effect) |
| 遷移エディタ | ブロックカード / 接続 / 並べ替え(D&D) / 一括操作 / 色 / Undo・Redo / 自動保存 / 外部更新検知 / Role データドロワー / テキスト編集(DSL) / インデックス操作 / CSV |

## ショートカット
Ctrl+K コマンドパレット、Ctrl+1/2/3 ページ移動、Alt+← 戻る、Ctrl+Z / Ctrl+Y 取り消し・やり直し、
Ctrl+Alt+G / H 見出し挿入、Ctrl+Space 補完、Alt+↑/↓ サブグループ移動(データ入力)。

## 構成
- `scenario_editor/core/` … JS の純粋ロジックの移植(Qt 非依存・テスト済み)
- `scenario_editor/api/` … Flask API クライアントとルックアップキャッシュ(Qt 非依存)
- `scenario_editor/ui/` … PySide6 の画面(`pages/`, `widgets/`, `dialogs/`)
- `docs/ARCHITECTURE.md`(設計)、`docs/PORTING_GAPS.md`(移植メモ・疑わしい挙動・推定エンドポイント)、`docs/PROGRESS.md`

## テスト / 静的チェック
```bash
python3 -m unittest discover -s tests     # 162 tests。Flask が必要
python3 tools/lint_names.py               # 未定義名・属性綴りの静的チェック(Qt 実行の代替)
```

## 検証状況(正直な内訳)
- **確認済み**: `core/` は元 JS を Node で動かした結果との差分テストで一致。`api/` は Flask モックに対してテスト。
- **部分的**: Qt 層は PySide6 を偽物に差し替えたスモークテスト(`tests/qt_stub.py`)で、画面生成・load・主な操作(追加/削除/接続/並べ替え/Undo/保存/移動/CSV/編集ダイアログ/ページ遷移)が例外を出さず、
  サーバーに期待どおりの本文が保存されることまで確認。**描画・レイアウト・D&D・フォーカス・QSS の見た目・テキスト編集の行ハイライト/補完ポップアップなどは未確認。**
- **未確認**: 実際の PySide6 での起動。実サーバー(app.py)との通信(下記の推定エンドポイント)。

## 既知の制約
`docs/PORTING_GAPS.md` を参照(Role 一覧の OpenFileMenuButton は未移植、参照チェック API は推定、など)。
