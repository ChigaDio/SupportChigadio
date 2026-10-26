# シナリオ辞典 ジェネレーター

Role 定義（JSON）・enum・ClassDataID・RoleAction.cs を読み取り、
**検索できる辞書つきのドキュメントサイト（1ファイルのHTML）** を自動で作ります。

## 1. 用意するもの

- Python 3.9 以上
- `pip install -r requirements.txt`（markdown ライブラリだけ）

## 2. 作り方

```bash
python build_docs.py --data-dir <エディタの data フォルダ> --out-dir dist
```

**1ページ1ファイル** で `dist/` に出力します（`index.html` から開く）。

| ファイル | 内容 |
|---|---|
| `index.html` | トップ |
| `roles.html` / `role-<Role名>.html` | Role辞典 / 各Roleのページ |
| `types.html` / `type-<型名>.html` | 型・選択肢辞典 / 各型のページ |
| `glossary.html` | 用語集 |
| `guide-<id>.html` | ガイド（はじめに・DSL・エディタ・ビルド手順・困ったとき） |
| `assets/style.css` `assets/app.js` `assets/data.js` | 全ページ共通 |

- 前回のビルドで作った `*.html` は、毎回消してから作り直します（削除したRoleのページが残らないため）。`assets/` 以外の手置きファイルを `dist/` に入れないでください。
- ページの本文は、共通の `assets/data.js` を読んでブラウザで組み立てます（JavaScript が必要）。サーバー不要で、`file://` でも動きます。
- 1ファイルにまとめたい（メール添付など）ときだけ: `python build_docs.py --data-dir ... --single dist/all.html`

サンプルで試す: `python build_docs.py --data-dir sample_data`

### data フォルダから読み取るもの

| パス | 内容 | 無いとき |
|---|---|---|
| `scenario_data/scenario_role/scenario_role_list.json` | Role 一覧（`tags` があれば分類・検索に使う） | **必須** |
| `scenario_data/scenario_role/<Role>/<Role>.json` | Role の項目定義 | その Role をスキップ（警告） |
| `scenario_data/scenario_role/<Role>/<Role>RoleAction.cs` | 動作状況（未実装・スキップ対応）の自動判定 | 判定なしで表示 |
| `enum/enum_list.json`, `enum/<名前>/<名前>.json` | enum の値 | 型辞典に「候補なし」と表示 |
| `class_data_id/class_data_id_list.json`, `class_data_id/<名前>/<名前>.json` | ID表の値 | 同上 |

## 3. 文章を書く・直す（プログラマー不要）

文章は `content/` にあります。Markdown と JSON を編集して、もう一度ビルドするだけです。

| ファイル | 役割 |
|---|---|
| `content/role_notes.json` | Role ごとの説明（使いどころ・コツ・注意・例・分類）。**新しい Role を足したら、ここに同名の項目を追加** |
| `content/type_notes.json` | 型・選択肢の説明と、確認済みの値 |
| `content/glossary.json` | 用語集 |
| `content/guides/*.md` | ガイド記事（先頭の `---` 部分で title / summary / group を指定。ファイル名の番号順に並ぶ） |
| `content/project.json` | プロジェクト固有の値（エディタの起動方法・bin の置き場所・担当者名）。ガイド内の `{{project.xxx}}` に差し込まれる |

`role_notes.json` の書式:

```json
"TalkWriter": {
  "category": "会話",
  "when": "どんな時に使うか",
  "tips": ["コツ"],
  "watch": ["注意"],
  "examples": [{"title": "例の題", "lines": ["TalkWriter ..."]}]
}
```

ガイド内の ` ```dsl ` ブロックは DSL として色付けされ、コピーボタンが付きます。`!!! warning "題"` で注意枠が作れます。

## 4. 自動で作られるもの

- Role ごとのページ: 項目表（型・必須・既定値・条件）、**DSL 1行ビルダー**（値を入れるとコピーできる1行ができる）
- 動作状況: RoleAction.cs から「未実装」「高速スキップ対応」「クリックで飛ばせる」を推定（目安です）
- 型・選択肢辞典、用語集、ガイド、全文検索（`/` または Ctrl/Cmd+K。ひらがな・カタカナ区別なし）

## 5. 更新の流れ

1. Role 定義が変わった / 説明を直した
2. `python build_docs.py --data-dir ...`
3. `dist/index.html` を差し替えて公開

`--strict` を付けると、警告があれば失敗します（CI で使えます）。

## 6. 注意

- 自動判定（未実装など）は C# の行数からの推定です。外れたら `role_notes.json` の `watch` に書いてください。
- 日本語フォントは Google Fonts から読みます。オフラインでは OS の標準フォントになります。

## 7. Roleのタグ（分類）をエディタで付ける

Role辞典の分類（会話・キャラクター・音 …）は、`scenario_role_list.json` の各Roleの `tags`（先頭が分類、2つ目以降は検索用）から読みます。
タグが無いRoleは、`content/role_notes.json` の `category`、それも無ければ「その他」に入り、ビルド時に警告が出ます。

エディタ側でタグを付けられるようにする追加分は `editor_patch/` にあります。
- `ScenarioRoleGrid.js` / `ScenarioRoleGrid.diff`: Role一覧に「タグ」列と編集ダイアログ（既存タグの候補つき）を追加
- `scenario_role_tags.py`: `PUT /api/scenario-role/tags` と、一覧APIで `tags` を通すときの注意
