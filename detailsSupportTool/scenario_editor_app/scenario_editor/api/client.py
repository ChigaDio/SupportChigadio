"""Flask(scenario.py / app.py) の REST API クライアント (Qt 非依存・標準ライブラリのみ)。

JS が `fetch` している全エンドポイントを 1 メソッド 1 対 1 で提供する。
scenario.py に無いルート(app.py 側)は JS の呼び出し側から推定したもので、
そのメソッドの docstring に ``# inferred from <file>:<line>`` を付けている。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://localhost:5000"


class ApiError(Exception):
    """HTTP エラー・通信エラー。status=0 は通信自体の失敗。"""

    def __init__(self, status: int, message: str, body=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.body = body

    def __str__(self):
        return f"HTTP {self.status}: {self.message}" if self.status else self.message


def _q(s) -> str:
    return urllib.parse.quote(str(s), safe="")


class ApiClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ 低レベル
    def request(self, method: str, path: str, body=None, headers=None, want_headers=False):
        """JSON を送受信する。want_headers=True なら (json, headers) を返す。"""
        url = self.base_url + path
        data = None
        hdrs = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        elif method in ("POST", "PUT", "PATCH"):
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                raw = res.read()
                rh = res.headers
        except urllib.error.HTTPError as e:
            raw = e.read() or b""
            parsed = _try_json(raw)
            msg = parsed.get("error") if isinstance(parsed, dict) and parsed.get("error") else \
                (raw.decode("utf-8", "replace")[:300] or e.reason)
            raise ApiError(e.code, str(msg), parsed) from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            reason = getattr(e, "reason", e)
            raise ApiError(0, f"サーバーに接続できません ({self.base_url}): {reason}") from None
        parsed = _try_json(raw) if raw else None
        return (parsed, rh) if want_headers else parsed

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body if body is not None else {}, **kw)

    def request_json(self, url, method="GET", body=None):
        """PresetManager 用: (ok, status, body) を返し、例外は投げない。"""
        try:
            return True, 200, self.request(method, url, body)
        except ApiError as e:
            return False, e.status, e.body

    def ping(self) -> bool:
        try:
            self.list_events()
            return True
        except ApiError:
            return False

    # ------------------------------------------------------------------ イベント
    def list_events(self):
        return self.get("/api/scenario-event") or []

    def create_event(self, body):
        """body: {id, name, description}"""
        return self.post("/api/scenario-event", body)

    def update_event(self, event_id, body):
        return self.request("PATCH", f"/api/scenario-event/{_q(event_id)}", body)

    def delete_event(self, event_id):
        return self.request("DELETE", f"/api/scenario-event/{_q(event_id)}")

    def copy_event(self, event_id, body):
        """body: {copySubs: bool}"""
        return self.post(f"/api/scenario-event/{_q(event_id)}/copy", body)

    def create_sub(self, event_id, body):
        """-> {message, subId}"""
        return self.post(f"/api/scenario-event/{_q(event_id)}/sub", body)

    def update_sub(self, event_id, sub_id, body):
        return self.request("PATCH", f"/api/scenario-event/{_q(event_id)}/sub/{_q(sub_id)}", body)

    def delete_sub(self, event_id, sub_id):
        return self.request("DELETE", f"/api/scenario-event/{_q(event_id)}/sub/{_q(sub_id)}")

    def copy_sub(self, event_id, sub_id, body):
        """body: {targetEventId}"""
        return self.post(f"/api/scenario-event/{_q(event_id)}/sub/{_q(sub_id)}/copy", body)

    # ------------------------------------------------------------------ 一括操作
    def fix_all_events(self):
        return self.post("/api/fix-all-events")

    def generate_all_event_bin(self):
        return self.post("/api/generate-all-event-bin")

    def migrate_legacy_events(self):
        """-> {migrated: [], failed: []}"""
        return self.post("/api/scenario-event/migrate-legacy")

    # ------------------------------------------------------------------ 遷移(ノード/エッジ)
    def _sub(self, event_id, sub_id):
        return f"/api/scenario-event/{_q(event_id)}/sub/{_q(sub_id)}"

    def get_transition(self, event_id, sub_id):
        """-> ({nodes, edges}, rev)。rev はレスポンスヘッダ X-Sub-Rev (無ければ None)。"""
        data, hdrs = self.get(self._sub(event_id, sub_id) + "/transition", want_headers=True)
        return (data or {"nodes": [], "edges": []}), hdrs.get("X-Sub-Rev")

    def save_transition(self, event_id, sub_id, nodes, edges):
        """-> {rev?, ...}"""
        return self.post(self._sub(event_id, sub_id) + "/transition", {"nodes": nodes, "edges": edges}) or {}

    def get_subgroup(self, event_id, sub_id, node_path):
        """ノード(node_path = 'parentId' など)内のサブグループ {nodes, edges}。
        # inferred from ScenarioEventTransition.js:3181"""
        return self.get(self._sub(event_id, sub_id) + f"/transition/{node_path}/subgroup") or {"nodes": [], "edges": []}

    def save_subgroup(self, event_id, sub_id, node_path, nodes, edges):
        """# inferred from ScenarioEventTransition.js:3097"""
        return self.post(self._sub(event_id, sub_id) + f"/transition/{node_path}/subgroup",
                         {"nodes": nodes, "edges": edges}) or {}

    def add_role_to_node(self, event_id, sub_id, node_path, role_id, name, branch_type="General", unique_id=None):
        """-> {rev, data, ...}  # inferred from ScenarioEventTransition.js:1284"""
        return self.post(self._sub(event_id, sub_id) + f"/transition/{node_path}/role",
                         {"roleId": role_id, "name": name, "branchType": branch_type or "General",
                          "uniqueId": unique_id}) or {}

    # 旧名(設計書の save_role)
    save_role = add_role_to_node

    def save_role_data_batch(self, event_id, sub_id, updates):
        """updates: [{nodePath, uniqueId, formData}] -> {rev}  # inferred from ScenarioEventTransition.js:3413"""
        return self.post(self._sub(event_id, sub_id) + "/role-data-batch", {"updates": updates}) or {}

    def get_rev(self, event_id, sub_id):
        """-> {rev}  # inferred from ScenarioEventTransition.js:3603"""
        return self.get(self._sub(event_id, sub_id) + "/rev") or {}

    # ------------------------------------------------------------------ Role 定義
    def list_roles(self):
        r = self.get("/api/scenario-role")
        return r if isinstance(r, list) else []

    def create_role(self, name, description="", branch_type="General"):
        """-> {message, data:{id}}"""
        return self.post("/api/scenario-role", {"name": name, "description": description, "branchType": branch_type})

    def delete_role(self, name):
        """一覧画面の削除(PATCH, 本文に name)。 # ScenarioRoleGrid.js:88"""
        return self.request("PATCH", "/api/scenario-role", {"name": name})

    def delete_role_definition(self, name):
        """詳細画面の削除 (DELETE /api/scenario-role/{name})。 # ScenarioRoleDetailGrid.js:709"""
        return self.request("DELETE", f"/api/scenario-role/{_q(name)}")

    def get_role(self, name):
        """-> {data:[field...], branchType}"""
        return self.get(f"/api/scenario-role/{_q(name)}")

    def save_role_definition(self, name, data, branch_type="General"):
        return self.post(f"/api/scenario-role/{_q(name)}", {"data": data, "branchType": branch_type})

    def generate_role_cs(self, name, data, branch_type="General"):
        return self.post(f"/api/generate-scenario-role/{_q(name)}", {"data": data, "branchType": branch_type})

    def role_form_schema(self, name):
        return self.get(f"/api/role-form-schema/{_q(name)}")

    def save_role_field_default(self, name, field_name, value):
        """# inferred from BaseRoleInputForm.js:1586"""
        return self.post(f"/api/scenario-role/{_q(name)}/field-default", {"fieldName": field_name, "value": value})

    def update_role_tags(self, tags_by_role):
        """PUT /api/scenario-role/tags (docsite の editor_patch で追加したエンドポイント)。
        tags_by_role: {roleName: [tag...]}"""
        return self.request("PUT", "/api/scenario-role/tags", {"tags": tags_by_role})

    def check_references(self, kind, name):
        """削除前の参照チェック。services/api.js (未受領) の confirmDeleteWithReferenceCheck 相当。
        サーバーに該当ルートが無ければ空を返す(= 参照なし扱い)。
        # inferred: JS 側ソース無し。/api/references?type=&name= を試す"""
        try:
            r = self.get(f"/api/references?type={_q(kind)}&name={_q(name)}")
        except ApiError:
            return {"references": []}
        return r if isinstance(r, dict) else {"references": r or []}

    # ------------------------------------------------------------------ サブグループ設定
    SETTING = "/api/scenario-subgroup-setting"

    def get_subgroup_setting(self):
        return self.get(self.SETTING)

    def save_subgroup_setting(self, data, branch_type="General"):
        """-> {message, sync:{nodes_touched,...}, error_detail}  (JS は { data, branchType } を送る)"""
        return self.post(self.SETTING, {"data": data, "branchType": branch_type})

    def subgroup_setting_form_schema(self):
        """-> {schema, defaults}"""
        return self.get(self.SETTING + "/form-schema")

    def save_subgroup_setting_field_default(self, field_name, value):
        return self.post(self.SETTING + "/field-default", {"fieldName": field_name, "value": value})

    def clear_subgroup_setting_field_default(self, field_name):
        return self.request("DELETE", self.SETTING + "/field-default", {"fieldName": field_name})

    def save_subgroup_setting_defaults(self, values):
        return self.post(self.SETTING + "/defaults", {"values": values})

    def generate_subgroup_setting_cs(self, data=None, branch_type="General"):
        return self.post(self.SETTING + "/generate", {"data": data, "branchType": branch_type} if data is not None else {})

    def sync_subgroup_setting(self):
        return self.post(self.SETTING + "/sync")

    # ------------------------------------------------------------------ マスタ
    def enum(self, type_name):
        """# ScenarioRoleDetailGrid.js:473"""
        return self.get(f"/api/enum/{_q(type_name)}") or []

    def enum_ids(self):
        return self.get("/api/enum-id") or []

    def class_data_list(self):
        return self.get("/api/class-data") or []

    def class_data(self, name):
        return self.get(f"/api/class-data/{_q(name)}")

    def class_data_ids(self):
        return self.get("/api/class-data-id") or []

    def class_data_id(self, type_name):
        """-> {rows:[{enum_property,...}]}"""
        return self.get(f"/api/class-data-id/{_q(type_name)}") or {"rows": []}

    def custom_class_data_type_options(self):
        return self.get("/api/custom-class-data-type-options") or {}

    def class_data_matrix_id(self, matrix_name):
        """-> {data:{rowKey: ...}}  # inferred from BaseRoleInputForm.js"""
        return self.get(f"/api/class-data-matrix-id/{_q(matrix_name)}") or {"data": {}}

    def custom_class_data_id(self, name):
        """-> {rows:[{enum_property,...}]}  # inferred from BaseRoleInputForm.js:1486"""
        return self.get(f"/api/custom-class-data-id/{_q(name)}") or {"rows": []}

    def sound_serve_url(self, group, index) -> str:
        """試聴用の音声 URL (GET /api/sound/serve/{group}/{index})。 # BaseRoleInputForm.js:265"""
        return f"{self.base_url}/api/sound/serve/{_q(group)}/{index}"

    def sounds(self):
        return self.get("/api/sound") or {"groups": {}}

    def textures(self):
        return self.get("/api/texture") or {"groups": {}}

    def gameobjects(self):
        return self.get("/api/gameobject") or {"groups": {}}

    # ------------------------------------------------------------------ ストーリー設定
    def story_slot_defs(self):
        return self.get("/api/story-setting/slot-defs")

    def get_story(self, event_id, sub_id):
        return self.get(self._sub(event_id, sub_id) + "/story")

    def save_story(self, event_id, sub_id, slots, voice_series_id):
        return self.post(self._sub(event_id, sub_id) + "/story", {"slots": slots, "voiceSeriesId": voice_series_id})

    def generate_story_all(self):
        return self.post("/api/story-setting/generate")

    def generate_story_voice_role(self):
        return self.post("/api/story-setting/generate-voice-role")

    # ------------------------------------------------------------------ プリセット
    PRESET = "/api/scenario-role-presets"

    def list_presets(self):
        return self.get(self.PRESET)

    def save_preset(self, role_name, name, data):
        return self.post(self.PRESET, {"roleName": role_name, "name": name, "data": data})

    def delete_preset(self, role_name, name):
        return self.request("DELETE", f"{self.PRESET}?roleName={_q(role_name)}&name={_q(name)}")

    def import_presets(self, presets):
        """-> {presets, imported, skipped}"""
        return self.post(self.PRESET + "/import", {"presets": presets})


def _try_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
