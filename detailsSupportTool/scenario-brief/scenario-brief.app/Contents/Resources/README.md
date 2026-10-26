# シナリオ演出依頼資料集

## 起動
- Windows: `run.bat` をダブルクリック / Mac・Linux: `./run.sh`（Python 3.8+、追加インストール不要）
- ブラウザが自動で開きます。初回は「表紙」でプロジェクト名、上部で自分の名前を入力。
- 保存先は `scenario-data/`（`--data パス` で変更可）。このフォルダをGitで管理します。
  - `project.json` / `chapters/` / `dictionary/` / `users/<名前>/` に1ファイルずつ保存。自分の書き込みは `users/<自分の名前>/` だけに書かれます。
  - `scenario-data/.local/`（自分の名前）は `.gitignore` 済み。
- `git pull` のあとは画面上部の「🔄 再読込」。

## 実行ファイル化 (PyInstaller)
- `build.bat`（Windows） / `./build.sh`（Mac）→ `dist/ScenarioBrief(.exe)`
- 各OS上でビルドしてください（クロスビルド不可）。exeと同じ場所に `scenario-data/` が作られます。

## PDF
「📄 PDF出力(A4)」→ 印刷画面で送信先「PDFに保存」、用紙A4・余白なし・背景のグラフィックON。

## 画像
`🖼画像` / Ctrl+V貼り付け / ドラッグ&ドロップ → `scenario-data/images/<ハッシュ>_<名前>.png` に保存し、JSONには相対パス `images/…` だけを書きます（同じ画像は同じファイル名になるので競合しません）。画像もGitに含めてください。
