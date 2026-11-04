設定資料集エディタ（ローカル版）

起動: start.bat（Windows）または start.sh（Mac/Linux）を実行 → http://localhost:8000/
  ※ Python が必要です。ほかの静的サーバーでも動きます（例: npx serve）。
  ※ index.html をダブルクリックで直接開いても編集はできますが、
    ブラウザの制限で PDF 書き出しと一部の画像読み込みが使えません。

構成: index.html（本体） / lib/（zip・PDF 用ライブラリ。オフラインで動作）
保存: 編集内容はブラウザ内に自動保存。「サイト書き出し(zip)」で
  index.html + project.js + images/（相対パス）を書き出し、
  「読み込み」「フォルダ読み込み」で戻せます。
