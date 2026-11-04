# 移植メモ: 取りこぼし・元の JS との差・疑わしい挙動

## 元の JS の疑わしい挙動 (そのまま移植。差分テストで JS と一致を確認済み)
- **Sub編集/全体編集でセクションを並べ替えても、既存ノードの実行順は変わらない。**
  `ScenarioEventTransition.js` の `ensureAllEditNodePath` に「出現順に末尾へ積み直す」処理があり、
  ダイアログの説明文も「並び順がテキストに追従する」と書いているが、既存ノードは
  `targetsRef` から直接引かれるためこの処理に到達しない(新規作成時だけ通る)。
  意図どおりにするなら `apply_edit_sections` で既存ノードも末尾へ積み直す。→ 要確認。

## 意図的に JS と変えた点
- **グループ間のノード移動 (`move_to_group`)**: JS は、読み込み前/未保存のサブグループタブへ移したノードが保存されない場合があった。
  移動先タブを必要なら読み込み、移動先グループの存在を検証し、移動元・移動先の両方を保存する。
- **編集ダイアログ(Sub編集/全体編集)を開く前に未保存の変更を保存**し、適用後はサーバーから再読込する。
- **ノード色・プリセット・コピー中の Role**: localStorage の代わりに設定フォルダの JSON に保存。
- **CSV 入力**: 確認ダイアログなしで取り込み(UTF-8 BOM 付き、Excel 想定)。取り消しは Ctrl+Z。
- **`fetchAllClassDataSchemas`** はこちらの JS 受領分に無かったため、`class_data_list` + `custom_class_list` → 各 `class_data(name)` から `LookupCache.all_class_data_schemas` として再実装。

## 未移植 / 不明
- Role 一覧の `OpenFileMenuButton`(「ファイルを開く」メニュー): バックエンドの挙動が不明なため未移植。
- `ScenarioEventTransition` 以外のページで、受領 JS に含まれない補助コンポーネントがあれば未対応。

## 推定したエンドポイント (app.py 未受領。`api/client.py` の `# inferred` を参照)
- 遷移: `.../transition/{nodePath}/subgroup` (GET/POST), `.../transition/{nodePath}/role`, `.../role-data-batch`, `.../rev`
- `POST /api/scenario-role/{name}/field-default`, `/api/class-data-matrix-id/{name}`, `/api/custom-class-data-id/{name}`
- `/api/sound/serve/...`(サウンド試聴)
- 削除前の参照チェック (`confirmDeleteWithReferenceCheck` は services/api.js で未受領): `/api/references?type=&name=` を仮定。
  存在しなければ「参照なし」扱いで続行する。
- `PUT /api/scenario-role/tags` は docsite の editor_patch で追加したもの。
- 応答の形を仮定: `/api/sound|texture|gameobject` は `{"groups": {name: {"items": [...]}}}`、`/api/story-setting/slot-defs` は `[{prefix, names}]`。
  実サーバーと違う場合は `api/client.py` / `api/lookups.py` の該当箇所を直す。

## テスト基盤の限界
- `tests/qt_stub.py` は PySide6 の偽物。`QTextDocument` / 描画 / レイアウト / シグナルの実タイミングは再現しない。
  このため DslEditor の lint 下線描画(`_extra_selections`)など一部経路は実機でしか確認できない。
