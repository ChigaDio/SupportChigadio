"""Flask 製の簡易モックサーバー (実サーバーと同じ形の JSON を返す、インメモリ)。

    from mock_server import start_mock
    srv = start_mock()          # port=0 で空きポート
    srv.url                     # 'http://127.0.0.1:PORT'
    srv.state                   # 中身を直接覗ける dict
    srv.stop()

手動起動: ``python tests/mock_server.py 5000``  (GUI をサーバー無しで試す用)
"""
from __future__ import annotations

import copy
import threading
import time

from flask import Flask, jsonify, request
from werkzeug.serving import make_server


def initial_state():
    return {
        "events": {"1": {"name": "Prologue", "description": "はじまり", "subs": {"1": {"name": "Intro", "description": ""}}}},
        "transitions": {"1/1": {"nodes": [{"id": "1", "type": "scenarioNode", "position": {"x": 0, "y": 0},
                                              "data": {"label": "Start", "roles": []}}], "edges": []}},
        "rev": {"1/1": "r0"},
        "roles": {"Say": {"id": 1, "name": "Say", "description": "台詞", "branchType": "General",
                            "data": [{"id": 1, "name": "text", "type": "string", "required": True},
                                     {"id": 2, "name": "speed", "type": "float", "required": False}]}},
        "setting": {"data": [{"id": 1, "name": "is_wait_key", "type": "bool", "required": True, "default": False}]},
        "presets": {},
        "stories": {},
        "enums": {"Chara": ["Alice", "Bob"]},
        "story_slots": [{"prefix": "img", "names": ["img_a", "img_b"]}, {"prefix": "sound_se", "names": ["sound_se_a"]},
                        {"prefix": "sound_bgm", "names": ["sound_bgm_a"]}, {"prefix": "effect", "names": ["effect_a"]}],
    }


def make_app(state):
    app = Flask(__name__)
    lock = threading.RLock()

    def bump(key):
        state["rev"][key] = "r%d" % int(time.time() * 1000000)
        return state["rev"][key]

    def ev_list():
        return [{"id": int(i) if i.isdigit() else i, "name": e["name"], "description": e["description"],
                 "subEvents": [{"subId": int(s) if s.isdigit() else s, **v} for s, v in e["subs"].items()]}
                for i, e in state["events"].items()]

    @app.route("/api/scenario-event", methods=["GET", "POST"])
    def events():
        with lock:
            if request.method == "GET":
                return jsonify(ev_list())
            b = request.get_json() or {}
            state["events"][str(b["id"])] = {"name": b.get("name", ""), "description": b.get("description", ""), "subs": {}}
            return jsonify({"message": "イベントを追加しました"})

    @app.route("/api/scenario-event/<eid>", methods=["PATCH", "DELETE"])
    def event_one(eid):
        with lock:
            if eid not in state["events"]:
                return jsonify({"error": "not found"}), 404
            if request.method == "DELETE":
                del state["events"][eid]
                return jsonify({"message": "削除しました"})
            b = request.get_json() or {}
            state["events"][eid].update({k: b[k] for k in ("name", "description") if k in b})
            return jsonify({"message": "更新しました"})

    @app.route("/api/scenario-event/<eid>/copy", methods=["POST"])
    def event_copy(eid):
        with lock:
            new = str(max(int(k) for k in state["events"]) + 1)
            src = copy.deepcopy(state["events"][eid])
            if not (request.get_json() or {}).get("copySubs"):
                src["subs"] = {}
            state["events"][new] = src
            return jsonify({"message": "コピーしました", "id": int(new)})

    @app.route("/api/scenario-event/<eid>/sub", methods=["POST"])
    def sub_create(eid):
        with lock:
            subs = state["events"][eid]["subs"]
            sid = str(max([int(k) for k in subs] or [0]) + 1)
            b = request.get_json() or {}
            subs[sid] = {"name": b.get("name", ""), "description": b.get("description", "")}
            state["transitions"][f"{eid}/{sid}"] = {"nodes": [], "edges": []}
            state["rev"][f"{eid}/{sid}"] = "r0"
            return jsonify({"message": "追加しました", "subId": int(sid)})

    @app.route("/api/scenario-event/<eid>/sub/<sid>", methods=["PATCH", "DELETE"])
    def sub_one(eid, sid):
        with lock:
            subs = state["events"].get(eid, {}).get("subs", {})
            if sid not in subs:
                return jsonify({"error": "not found"}), 404
            if request.method == "DELETE":
                del subs[sid]
                return jsonify({"message": "削除しました"})
            b = request.get_json() or {}
            subs[sid].update({k: b[k] for k in ("name", "description") if k in b})
            return jsonify({"message": "更新しました"})

    @app.route("/api/scenario-event/<eid>/sub/<sid>/copy", methods=["POST"])
    def sub_copy(eid, sid):
        with lock:
            tgt = str((request.get_json() or {}).get("targetEventId"))
            subs = state["events"][tgt]["subs"]
            nid = str(max([int(k) for k in subs] or [0]) + 1)
            subs[nid] = copy.deepcopy(state["events"][eid]["subs"][sid])
            state["transitions"][f"{tgt}/{nid}"] = copy.deepcopy(state["transitions"].get(f"{eid}/{sid}", {"nodes": [], "edges": []}))
            state["rev"][f"{tgt}/{nid}"] = "r0"
            return jsonify({"message": "コピーしました", "subId": int(nid)})

    @app.route("/api/fix-all-events", methods=["POST"])
    def fix_all():
        return jsonify({"message": "全イベントを修復しました"})

    @app.route("/api/generate-all-event-bin", methods=["POST"])
    def gen_bin():
        return jsonify({"message": "all_events.bytes を生成しました"})

    @app.route("/api/scenario-event/migrate-legacy", methods=["POST"])
    def migrate():
        return jsonify({"migrated": ["1"], "failed": []})

    # ---- 遷移
    @app.route("/api/scenario-event/<eid>/sub/<sid>/transition", methods=["GET", "POST"])
    def transition(eid, sid):
        key = f"{eid}/{sid}"
        with lock:
            if key not in state["transitions"]:
                return jsonify({"error": "not found"}), 404
            if request.method == "GET":
                r = jsonify(state["transitions"][key])
                r.headers["X-Sub-Rev"] = state["rev"][key]
                return r
            b = request.get_json() or {}
            state["transitions"][key] = {"nodes": b.get("nodes", []), "edges": b.get("edges", [])}
            return jsonify({"message": "保存しました", "rev": bump(key)})

    def find_node(key, path):
        parts = str(path).split("/")
        nodes = state["transitions"][key]["nodes"]
        node = None
        for i, p in enumerate(parts):
            node = next((n for n in nodes if str(n["id"]) == p), None)
            if node is None:
                return None
            if i < len(parts) - 1:
                nodes = (node.get("data", {}).get("subgroups", {}).get(parts[i + 1]) or {}).get("nodes", [])
        return node

    @app.route("/api/scenario-event/<eid>/sub/<sid>/transition/<path:np>/subgroup", methods=["GET", "POST"])
    def subgroup(eid, sid, np):
        key = f"{eid}/{sid}"
        with lock:
            node = find_node(key, np)
            if node is None:
                return jsonify({"error": "node not found"}), 404
            sgs = node.setdefault("data", {}).setdefault("subgroups", {})
            pid = str(np).split("/")[-1]
            if request.method == "GET":
                return jsonify(sgs.get(pid, {"nodes": [], "edges": []}))
            b = request.get_json() or {}
            sgs[pid] = {"nodes": b.get("nodes", []), "edges": b.get("edges", [])}
            return jsonify({"message": "保存しました", "rev": bump(key)})

    @app.route("/api/scenario-event/<eid>/sub/<sid>/transition/<path:np>/role", methods=["POST"])
    def add_role(eid, sid, np):
        key = f"{eid}/{sid}"
        with lock:
            node = find_node(key, np)
            if node is None:
                return jsonify({"error": "node not found"}), 404
            b = request.get_json() or {}
            role = state["roles"].get(b.get("name"))
            data = [{"name": f["name"], "type": f["type"], "value": f.get("default")} for f in (role or {}).get("data", [])]
            node.setdefault("data", {}).setdefault("roles", []).append(
                {"uniqueId": b.get("uniqueId"), "id": b.get("roleId"), "name": b.get("name"),
                 "branchType": b.get("branchType"), "data": data})
            return jsonify({"message": "追加しました", "rev": bump(key), "data": data})

    @app.route("/api/scenario-event/<eid>/sub/<sid>/role-data-batch", methods=["POST"])
    def role_batch(eid, sid):
        key = f"{eid}/{sid}"
        with lock:
            for u in (request.get_json() or {}).get("updates", []):
                node = find_node(key, u["nodePath"])
                if node is None:
                    continue
                for r in node.get("data", {}).get("roles", []):
                    if str(r.get("uniqueId")) == str(u["uniqueId"]):
                        r["data"] = u["formData"]
            return jsonify({"message": "保存しました", "rev": bump(key)})

    @app.route("/api/scenario-event/<eid>/sub/<sid>/rev")
    def get_rev(eid, sid):
        return jsonify({"rev": state["rev"].get(f"{eid}/{sid}")})

    # ---- Role
    @app.route("/api/scenario-role", methods=["GET", "POST", "PATCH"])
    def roles():
        with lock:
            if request.method == "GET":
                return jsonify([{k: r[k] for k in ("id", "name", "description", "branchType")} for r in state["roles"].values()])
            b = request.get_json() or {}
            if request.method == "PATCH":
                state["roles"].pop(b.get("name"), None)
                return jsonify({"message": "削除しました"})
            nid = max([r["id"] for r in state["roles"].values()] or [0]) + 1
            state["roles"][b["name"]] = {"id": nid, "name": b["name"], "description": b.get("description", ""),
                                         "branchType": b.get("branchType", "General"), "data": []}
            return jsonify({"message": "追加しました", "data": {"id": nid}})

    @app.route("/api/scenario-role/tags", methods=["PUT"])
    def role_tags():
        with lock:
            for name, tags in ((request.get_json() or {}).get("tags") or {}).items():
                if name in state["roles"]:
                    state["roles"][name]["tags"] = tags
            return jsonify({"message": "タグを保存しました"})

    @app.route("/api/scenario-role/<name>", methods=["GET", "POST", "DELETE"])
    def role_one(name):
        with lock:
            r = state["roles"].get(name)
            if r is None:
                return jsonify({"error": "not found"}), 404
            if request.method == "GET":
                return jsonify({"data": r["data"], "branchType": r["branchType"]})
            if request.method == "DELETE":
                del state["roles"][name]
                return jsonify({"message": "削除しました"})
            b = request.get_json() or {}
            r["data"] = b.get("data", [])
            r["branchType"] = b.get("branchType", r["branchType"])
            return jsonify({"message": "保存しました"})

    @app.route("/api/scenario-role/<name>/field-default", methods=["POST"])
    def role_field_default(name):
        b = request.get_json() or {}
        for f in state["roles"].get(name, {}).get("data", []):
            if f["name"] == b.get("fieldName"):
                f["default"] = b.get("value")
        return jsonify({"message": "ok"})

    @app.route("/api/generate-scenario-role/<name>", methods=["POST"])
    def gen_role(name):
        return jsonify({"message": f"{name}.cs を生成しました"})

    @app.route("/api/role-form-schema/<name>")
    def role_schema(name):
        r = state["roles"].get(name)
        if r is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"role": name, "branchType": r["branchType"], "fields": r["data"]})

    # ---- サブグループ設定
    S = "/api/scenario-subgroup-setting"

    @app.route(S, methods=["GET", "POST"])
    def setting():
        if request.method == "GET":
            return jsonify(state["setting"])
        state["setting"] = {"data": (request.get_json() or {}).get("data", [])}
        return jsonify({"message": "サブグループ設定を保存しました", "sync": {"nodes_touched": 0}, "error_detail": None})

    @app.route(S + "/form-schema")
    def setting_schema():
        fields = state["setting"]["data"]
        return jsonify({"schema": {"fields": fields},
                        "defaults": [{"name": f["name"], "type": f["type"], "value": f.get("default")} for f in fields]})

    @app.route(S + "/field-default", methods=["POST", "DELETE"])
    def setting_field_default():
        b = request.get_json(silent=True) or {}
        name = b.get("fieldName") or request.args.get("fieldName")
        for f in state["setting"]["data"]:
            if f["name"] == name:
                if request.method == "POST":
                    f["default"] = b.get("value")
                else:
                    f.pop("default", None)
                return jsonify({"message": "ok"})
        return jsonify({"error": "not found"}), 404

    @app.route(S + "/defaults", methods=["POST"])
    def setting_defaults():
        values = (request.get_json() or {}).get("values") or {}
        for f in state["setting"]["data"]:
            if f["name"] in values:
                f["default"] = values[f["name"]]
        return jsonify({"message": "デフォルト値を保存しました"})

    @app.route(S + "/generate", methods=["POST"])
    def setting_gen():
        return jsonify({"message": "ScenarioSubGroupSetting.cs を生成しました", "path": "x"})

    @app.route(S + "/sync", methods=["POST"])
    def setting_sync():
        return jsonify({"message": "全シナリオへ反映しました", "sync": {"nodes_touched": 0}})

    # ---- マスタ
    @app.route("/api/enum-id")
    def enum_id():
        return jsonify([{"name": n} for n in state["enums"]])

    @app.route("/api/enum/<t>")
    def enum_t(t):
        return jsonify([{"property": p} for p in state["enums"].get(t, [])])

    @app.route("/api/class-data")
    def class_data():
        return jsonify([{"name": "Pos"}])

    @app.route("/api/class-data/<n>")
    def class_data_one(n):
        return jsonify([{"name": "x", "type": "float"}, {"name": "y", "type": "float"}])

    @app.route("/api/class-data-id")
    def class_data_id_list():
        return jsonify([{"name": "ItemID"}])

    @app.route("/api/class-data-id/<t>")
    def class_data_id_one(t):
        return jsonify({"rows": [{"enum_property": "Potion"}, {"enum_property": "Sword"}]})

    @app.route("/api/custom-class-data-type-options")
    def custom_opts():
        return jsonify({"custom_class_list": [], "custom_class_id_list": [], "custom_types": ["bit", "color", "bezier"]})

    @app.route("/api/class-data-matrix-id/<m>")
    def matrix(m):
        return jsonify({"data": {"Ja": ["1_1"]}})

    assets = {
        "sound": {"groups": {"Main": {"items": [
            {"name": "bgm_a", "type": "BGM", "desc": "bgm"}, {"name": "se_b", "type": "SE", "desc": "se"},
            {"name": "v1", "type": "VOICE", "subgroup": "Ja"}, {"name": "v2", "type": "VOICE", "subgroup": "Ja"}]}}},
        "texture": {"groups": {"Bg": {"items": [{"name": "bg_a"}, {"name": "bg_b", "subgroup": "Night"}]}}},
        "gameobject": {"groups": {"Fx": {"items": [{"name": "Obj1"}]}}},
    }
    for ep, body in assets.items():
        app.add_url_rule(f"/api/{ep}", ep, lambda body=body: jsonify(body))

    # ---- ストーリー
    @app.route("/api/story-setting/slot-defs")
    def slot_defs():
        return jsonify(state["story_slots"])

    @app.route("/api/scenario-event/<eid>/sub/<sid>/story", methods=["GET", "POST"])
    def story(eid, sid):
        key = f"{eid}/{sid}"
        if request.method == "GET":
            return jsonify(state["stories"].get(key, {"slots": [], "voiceSeriesId": None}))
        state["stories"][key] = request.get_json() or {}
        return jsonify({"message": "保存しました"})

    @app.route("/api/story-setting/generate", methods=["POST"])
    def story_gen():
        return jsonify({"message": "生成しました"})

    @app.route("/api/story-setting/generate-voice-role", methods=["POST"])
    def story_voice():
        return jsonify({"message": "ボイスRoleを生成しました"})

    # ---- プリセット
    P = "/api/scenario-role-presets"

    @app.route(P, methods=["GET", "POST", "DELETE"])
    def presets():
        with lock:
            if request.method == "GET":
                return jsonify({"presets": state["presets"]})
            if request.method == "POST":
                b = request.get_json() or {}
                lst = state["presets"].setdefault(b["roleName"], [])
                lst[:] = [p for p in lst if p["name"] != b["name"]] + [{"name": b["name"], "data": b["data"], "savedAt": 1}]
                return jsonify({"presets": state["presets"]})
            rn, n = request.args.get("roleName"), request.args.get("name")
            state["presets"][rn] = [p for p in state["presets"].get(rn, []) if p["name"] != n]
            return jsonify({"presets": state["presets"]})

    @app.route(P + "/import", methods=["POST"])
    def presets_import():
        with lock:
            imported = skipped = 0
            for rn, lst in ((request.get_json() or {}).get("presets") or {}).items():
                cur = state["presets"].setdefault(rn, [])
                names = {p["name"] for p in cur}
                for p in lst:
                    if p["name"] in names:
                        skipped += 1
                    else:
                        cur.append(p)
                        imported += 1
            return jsonify({"presets": state["presets"], "imported": imported, "skipped": skipped})

    return app


class MockServer:
    def __init__(self, port=0):
        self.state = initial_state()
        self.app = make_app(self.state)
        self._srv = make_server("127.0.0.1", port, self.app, threaded=True)
        self.port = self._srv.server_port
        self.url = f"http://127.0.0.1:{self.port}"
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._srv.shutdown()
        self._t.join(timeout=5)


def start_mock(port=0) -> MockServer:
    return MockServer(port).start()


if __name__ == "__main__":
    import sys
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    s = start_mock(p)
    print("mock server:", s.url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        s.stop()
