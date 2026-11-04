"""マスタ(enum / class_data / matrix / sound ...)の取得+メモ化 (Qt 非依存)。

BaseRoleInputForm / ScenarioEventTransition / ScenarioRoleDetailGrid / ScenarioStorySettingGrid が
個別に fetch していたものを 1 か所にまとめる。スレッドセーフ(ワーカースレッドから呼ばれる)。
"""
from __future__ import annotations

import threading

from .client import ApiClient, ApiError

BASIC_TYPES = ["int", "float", "bool", "string", "double", "byte", "char", "short", "long", "decimal", "object"]
UNITY_TYPES = ["GameObject", "Transform", "Vector2", "Vector3", "Vector4", "Quaternion", "Color", "Rect", "Bounds",
               "Matrix4x4", "AnimationCurve", "Sprite", "Texture", "Material", "Mesh", "Rigidbody", "Collider",
               "AudioClip", "ScriptableObject"]
SCENARIO_ONLY_TYPES = ["text_list_index", "voice_ref"]


class LookupCache:
    def __init__(self, api: ApiClient):
        self.api = api
        self._cache = {}
        self._lock = threading.RLock()

    def _memo(self, key, fn, default=None, swallow=True):
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        try:
            val = fn()
        except ApiError:
            if not swallow:
                raise
            return default
        with self._lock:
            self._cache[key] = val
        return val

    def invalidate(self, kind=None):
        """kind が None なら全消去。文字列なら、その接頭辞のキーを消す(例 'enum' / 'matrix')。"""
        with self._lock:
            if kind is None:
                self._cache.clear()
                return
            for k in [k for k in self._cache if k == kind or (isinstance(k, tuple) and k[0] == kind) or
                      (isinstance(k, str) and k.startswith(kind))]:
                del self._cache[k]

    # --- 一覧系
    def enum_ids(self):
        return self._memo("enum-id", self.api.enum_ids, [])

    def class_data_list(self):
        return self._memo("class-data", self.api.class_data_list, [])

    def class_data_ids(self):
        return self._memo("class-data-id", self.api.class_data_ids, [])

    def custom_options(self):
        return self._memo("custom-options", self.api.custom_class_data_type_options, {})

    def sounds(self):
        return self._memo("sound", self.api.sounds, {"groups": {}})

    def textures(self):
        return self._memo("texture", self.api.textures, {"groups": {}})

    def gameobjects(self):
        return self._memo("gameobject", self.api.gameobjects, {"groups": {}})

    def events(self, refresh=False):
        if refresh:
            self.invalidate("events")
        return self._memo("events", self.api.list_events, [])

    def roles(self, refresh=False):
        if refresh:
            self.invalidate("roles")
        return self._memo("roles", self.api.list_roles, [])

    # --- 個別
    def enum_members(self, type_name):
        """enum の取りうる値(文字列)の一覧。"""
        def load():
            out = []
            for item in self.api.enum(type_name) or []:
                p = item.get("property") or item.get("enum_property") or item if isinstance(item, dict) else item
                out.append(str(p))
            return out
        return self._memo(("enum", type_name), load, [])

    def class_data_id_members(self, type_name):
        def load():
            return [str(r.get("enum_property")) for r in (self.api.class_data_id(type_name).get("rows") or [])]
        return self._memo(("class-data-id", type_name), load, [])

    def custom_class_data_id_members(self, name):
        def load():
            return [str(r.get("enum_property")) for r in (self.api.custom_class_data_id(name).get("rows") or [])]
        return self._memo(("custom-class-data-id", name), load, [])

    def class_data(self, name):
        return self._memo(("class-data", name), lambda: self.api.class_data(name), None)

    def matrix_ids(self, matrix_name):
        return self._memo(("matrix", matrix_name), lambda: self.api.class_data_matrix_id(matrix_name), {"data": {}})

    def role_form_schema(self, role_name, force_refresh=False):
        if force_refresh:
            self.invalidate("schema")
        return self._memo(("schema", role_name), lambda: self.api.role_form_schema(role_name), None, swallow=False)

    def all_class_data_schemas(self, force=False):
        """class_data / CustomClassData の型名 -> フィールド一覧 (JS: fetchAllClassDataSchemas)。DSL・フォームに渡す。"""
        if force:
            self.invalidate("class-schemas")
            self.invalidate("class-data")

        def load():
            names = [i.get("name") for i in self.class_data_list() if i.get("name")]
            for n in (self.custom_options().get("custom_class_list") or []):
                if n not in names:
                    names.append(n)
            out = {}
            for n in names:
                fields = self.class_data(n)
                if isinstance(fields, dict):
                    fields = fields.get("fields")
                if isinstance(fields, list):
                    out[n] = fields
            return out
        return self._memo("class-schemas", load, {})

    # --- 型の選択肢 (ScenarioRoleDetailGrid の Fetch type suggestions)
    def type_options(self, setting_mode=False):
        enum_types = [i.get("name") for i in self.enum_ids()]
        class_types = [i.get("name") for i in self.class_data_list()]
        class_id_types = [i.get("name") for i in self.class_data_ids()]
        opt = self.custom_options()
        custom_class = opt.get("custom_class_list") or []
        custom_class_id = opt.get("custom_class_id_list") or []
        custom_value, seen = [], set()
        for t in list(opt.get("custom_types") or []) + ["dictionary"]:
            if t not in seen:
                seen.add(t)
                custom_value.append(t)
        all_types = [*BASIC_TYPES, *UNITY_TYPES, *enum_types, *class_types, *class_id_types,
                     *custom_class, *custom_class_id, *custom_value, *SCENARIO_ONLY_TYPES]
        if setting_mode:
            all_types = [t for t in all_types if t not in SCENARIO_ONLY_TYPES]
        return {"all": all_types, "enum": enum_types, "classDataId": class_id_types,
                "customClassDataId": custom_class_id}
