# 🔗 API リファレンス

[← README に戻る](../README.md)

Flask バックエンドが提供する全 REST API エンドポイントの一覧です。実装場所（ファイル）も併記しています。
各カテゴリの詳しい仕様は対応する機能ドキュメントを参照してください。

---

## Enum / Class Data（`pythonSrc/class_data.py`）

| メソッド | パス |
|---|---|
| GET, POST, PATCH | `/api/enum-id` |
| GET, POST, DELETE | `/api/enum/<name>` |
| POST | `/api/generate-enum/<name>` |
| GET, POST, PATCH | `/api/class-data` |
| GET, POST, DELETE | `/api/class-data/<name>` |
| POST | `/api/generate-class/<name>` |
| POST | `/api/generate-all-binary` |
| POST | `/api/generate-table-id` |
| POST | `/api/generate-all-enums` |
| POST | `/api/generate-all-cs-header` |

## Class Data ID（`pythonSrc/class_data_id.py`）

| メソッド | パス |
|---|---|
| GET, POST, PATCH | `/api/class-data-id` |
| GET, POST, DELETE | `/api/class-data-id/<name>` |
| POST | `/api/generate-class-data-id/<name>` |
| POST | `/api/generate-binary/<name>` |
| GET, POST, PATCH | `/api/class-data-id-tags` |
| PUT | `/api/class-data-id-tags/<tag_id>` |
| PUT | `/api/class-data-id/<name>/tag` |

## Class Data Matrix ID（`pythonSrc/matrix.py`）

| メソッド | パス |
|---|---|
| GET, POST, PATCH | `/api/class-data-matrix-id` |
| GET, POST, DELETE | `/api/class-data-matrix-id/<name>` |
| POST | `/api/generate-class-data-matrix-id/<name>` |
| POST | `/api/generate-binary-matrix/<name>` |
| POST | `/api/generate-all-binary-matrix` |
| POST | `/api/generate-all-cs-matrix-header` |
| POST | `/api/generate-matrix-table-id` |
| POST | `/api/generate-class-data-memory-viewer` |
| GET, POST, PATCH | `/api/class-data-matrix-id-tags` |
| PUT | `/api/class-data-matrix-id-tags/<tag_id>` |
| PUT | `/api/class-data-matrix-id/<name>/tag` |

## Custom Class Data / ID（`pythonSrc/customclassdata.py`）

| メソッド | パス |
|---|---|
| GET, POST, PATCH | `/custom-class-data` |
| GET, POST, DELETE | `/custom-class-data/<name>` |
| GET | `/custom-class-data-type-options` |
| POST | `/generate-custom-class/<name>` |
| GET, POST, PATCH | `/custom-class-data-id` |
| GET, POST, PATCH | `/custom-class-data-id-tags` |
| PUT | `/custom-class-data-id-tags/<tag_id>` |
| PUT | `/custom-class-data-id/<name>/tag` |
| GET, POST, DELETE | `/custom-class-data-id/<name>` |
| POST | `/generate-custom-class-data-id/<name>` |
| POST | `/generate-all-custom-binary` |
| POST | `/generate-custom-table-id` |
| POST | `/generate-custom-cs-header` |

## Const Class Data（`pythonSrc/app.py`）

| メソッド | パス |
|---|---|
| GET, POST, PATCH | `/api/const-class-data` |
| GET, POST, DELETE | `/api/const-class-data/<name>` |
| POST | `/api/generate-const-class/<name>` |
| POST | `/api/generate-all-const-class` |

## State（`pythonSrc/state.py`）

| メソッド | パス |
|---|---|
| GET, POST, PATCH | `/api/state-data` |
| GET, POST, DELETE | `/api/state-data/<name>` |
| POST | `/api/generate-state/<name>` |
| GET | `/api/open-code/<state_name>/<node_label>` |

## Behavior（`pythonSrc/behavior_routes.py` → `behavior.py`）

| メソッド | パス |
|---|---|
| GET | `/api/behavior-data` |
| POST | `/api/behavior-data` |
| DELETE | `/api/behavior-data/<name>` |
| GET | `/api/behavior-data/<name>` |
| PUT | `/api/behavior-data/<name>` |
| POST | `/api/behavior-generate/<name>` |

## Scenario Role / Event / Conditions（`pythonSrc/app.py` + `scenario.py`）

| メソッド | パス |
|---|---|
| GET, POST, PATCH | `/api/scenario-role` |
| GET, POST, DELETE | `/api/scenario-role/<name>` |
| POST | `/api/generate-scenario-role/<name>` |
| GET, POST | `/api/scenario-event` |
| PATCH, DELETE | `/api/scenario-event/<id>` |
| POST | `/api/scenario-event/<id>/sub` |
| PATCH, DELETE | `/api/scenario-event/<id>/sub/<subId>` |
| GET, POST | `/api/scenario-event/<eventId>/sub/<subId>/transition` |
| GET, POST | `/api/scenario-event/<eventId>/sub/<subId>/transition/<parentId>/subgroup` |
| POST | `/api/scenario-event/<eventId>/sub/<subId>/transition/<nodeId>/role` |
| GET | `/api/role-form-schema/<roleName>` |
| POST | `/api/save-role-data/<eventId>/<subId>/<nodeId>/<roleId>` |
| POST | `/api/fix-all-events` |
| POST | `/api/generate-all-event-bin` |

## Texture / GameObject / Material / Sound（`pythonSrc/app.py` + `assets.py`）

| メソッド | パス |
|---|---|
| GET | `/api/texture` |
| POST | `/api/texture/add_group`, `/delete_group`, `/add_subgroup`, `/delete_subgroup` |
| POST | `/api/texture/add_texture`, `/delete_texture`, `/edit_texture`, `/reload_texture` |
| POST | `/api/texture/generate` |
| GET | `/api/texture/serve/<group_name>/<index>` |
| GET | `/api/gameobject` |
| POST | `/api/gameobject/add_group`, `/delete_group`, `/add_subgroup`, `/delete_subgroup` |
| POST | `/api/gameobject/add_gameobject`, `/delete_gameobject`, `/edit_gameobject`, `/reload_gameobject` |
| POST | `/api/gameobject/generate` |
| GET | `/api/material` |
| POST | `/api/material/add_group`, `/delete_group`, `/add_subgroup`, `/delete_subgroup` |
| POST | `/api/material/select_file` |
| POST | `/api/material/generate`, `/regenerate`, `/delete` |
| GET | `/api/material/cs_only` |
| POST | `/api/material/cs_only/generate`, `/regenerate`, `/delete` |
| GET | `/api/sound` |
| POST | `/api/sound/add_group`, `/delete_group`, `/add_subgroup`, `/delete_subgroup` |
| POST | `/api/sound/add_sound`, `/delete_sound`, `/edit_sound`, `/reload_sound` |
| POST | `/api/sound/generate` |
| GET | `/api/sound/serve/<group_name>/<index>` |

## Animator（`pythonSrc/app.py` + `animation.py`）

| メソッド | パス |
|---|---|
| GET | `/api/animator-data` |
| POST | `/api/animator-create` |
| PATCH | `/api/animator-data` |
| POST | `/api/generate-all-animator` |
| GET | `/api/animator-data/<name>` |
| POST | `/api/animator-data/<name>` |
| POST | `/api/generate-animator/<name>` |

## Scene（`pythonSrc/app.py` + `scene.py`）

| メソッド | パス |
|---|---|
| GET | `/api/scene/get` |
| POST | `/api/scene/add` |
| POST | `/api/scene/delete` |
| POST | `/api/scene/generate` |

## Save Data（`pythonSrc/app.py` + `savedata.py`）

| メソッド | パス |
|---|---|
| GET, POST | `/api/save-data/<name>` |
| POST | `/api/generate-save-data/<name>` |

## Debug Command（`pythonSrc/debugcommand.py`）

| メソッド | パス |
|---|---|
| GET, POST, PATCH | `/api/debug-command` |
| GET, POST | `/api/debug-command/<name>` |
| GET | `/api/debug-command-full` |
| POST | `/api/generate-debug-command/<name>` |
| POST | `/api/generate-all-debug-command` |

## 静的ファイル配信（`pythonSrc/app.py`）

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/`, `/<path:path>` | React ビルド成果物（`build/`）の配信（SPA ルーティング対応） |

---

[← README に戻る](../README.md)
