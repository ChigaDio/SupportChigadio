# 進捗チェックポイント

## 完了
- **core (Qt 非依存、元JSとの差分テストあり)**: dsl, diff, validation, node_utils, index_tools, subgroup_setting, presets, transition_ops, role_form, role_detail_ops, story_ops, event_ops
- **api**: client.py(全エンドポイント), lookups.py, tests/mock_server.py(Flask モック)
- **ui (PySide6)**: theme, async_, app_state, icons, main_window, pages(event_list / role_list / role_detail / subgroup_setting / story_setting / transition),
  widgets(common / field_editors / role_form / option_editors / dsl_editor / block_card / block_canvas), dialogs(index_tools / diff / edit / role_drawers)
- **検証ツール**: tools/lint_names.py(静的チェック), tests/qt_stub.py + tests/test_ui_smoke.py(PySide6 スタブのスモークテスト)
- main.py, requirements.txt, README.md, docs/*
- `python3 -m unittest discover -s tests` = 162 tests OK / lint 44 files 0 problems

## 未確認 (実機でのみ確認できる)
- PySide6 での実起動、見た目・レイアウト・D&D・フォーカス・テキスト編集のハイライト/補完ポップアップ
- 実サーバー(app.py)との通信(推定エンドポイントは docs/PORTING_GAPS.md)

## スモークテストで見つかり直した実バグ
- テーマ切替で側面バーを作り直すと、接続中でも「サーバーに接続できません」トーストが出ていた(main_window)
- RoleDataDrawer の `_empty` を未初期化のまま getattr で参照していた
