# -*- coding: utf-8 -*-
"""
pythonSrc/generate_all.py

各カテゴリにバラバラに存在する「C#生成」「バイナリ生成」「TableID生成」等の
ボタンを1画面に集約し、"Generate All" で選択したカテゴリをまとめて
再生成する機能。

実装方針:
各カテゴリの生成処理は既にFlaskのエンドポイントとして実装済みであり、
中身（内部関数）を個別にimportして呼び直すと、モジュールごとに異なる
関数シグネチャ・引数（get_type_lists()の戻り値等）を揃える必要があり
壊れやすい。そのため、Flaskの `app.test_client()` を使って既存の
エンドポイントをそのままHTTP経由で（プロセス内で）呼び出す方式にした。
これにより、各カテゴリの生成ロジック自体には一切手を加えず、実績のある
既存のルートをオーケストレーションするだけで済む。

ジョブの進捗管理は pythonSrc/csproj_sync.py と同じ方式
（バックグラウンドスレッド + メモリ上のjob辞書 + ポーリング用API）を踏襲。
"""
import threading
import time
import uuid

from flask import jsonify, request

APP = None
DATA_DIR = None

_jobs_lock = threading.Lock()
_jobs = {}

# 各ステップの定義。
#   kind='bulk'       : 1回のPOSTで対象カテゴリ全件を生成するエンドポイント
#   kind='list_each'  : list_url(GET)で一覧を取得し、各itemの'name'を
#                        url_template に埋め込んでPOSTをループ実行する
#   kind='fixed_list' : items にあらかじめ決め打ちの名前一覧を持つ
#                        （SaveDataのSystemData/PlayerDataなど）
STEPS = [
    {"id": "enum", "label": "Enum（全C#生成）", "kind": "bulk", "url": "/api/generate-all-enums"},
    {"id": "const_class_data", "label": "ConstClassData（全静的クラス生成）", "kind": "bulk", "url": "/api/generate-all-const-class"},
    {"id": "class_data_header", "label": "ClassData（C#ヘッダー）", "kind": "bulk", "url": "/api/generate-all-cs-header"},
    {"id": "class_data_binary", "label": "ClassData（バイナリ）", "kind": "bulk", "url": "/api/generate-all-binary"},
    {"id": "class_data_table_id", "label": "ClassData（TableID）", "kind": "bulk", "url": "/api/generate-table-id"},
    {"id": "custom_class_data_header", "label": "CustomClassData（C#ヘッダー）", "kind": "bulk", "url": "/api/generate-custom-cs-header"},
    {"id": "custom_class_data_binary", "label": "CustomClassData（バイナリ）", "kind": "bulk", "url": "/api/generate-all-custom-binary"},
    {"id": "custom_class_data_table_id", "label": "CustomClassData（TableID）", "kind": "bulk", "url": "/api/generate-custom-table-id"},
    {"id": "class_data_matrix_id_header", "label": "ClassDataMatrixID（C#ヘッダー）", "kind": "bulk", "url": "/api/generate-all-cs-matrix-header"},
    {"id": "class_data_matrix_id_binary", "label": "ClassDataMatrixID（バイナリ）", "kind": "bulk", "url": "/api/generate-all-binary-matrix"},
    {"id": "class_data_matrix_id_table_id", "label": "ClassDataMatrixID（TableID）", "kind": "bulk", "url": "/api/generate-matrix-table-id"},
    {"id": "state_data", "label": "State（各Stateを個別生成）", "kind": "list_each",
     "list_url": "/api/state-data", "url_template": "/api/generate-state/{name}"},
    {"id": "behavior_data", "label": "Behavior（各Behaviorを個別生成）", "kind": "list_each",
     "list_url": "/api/behavior-data", "url_template": "/api/behavior-generate/{name}"},
    {"id": "scenario_role", "label": "ScenarioRole（各Roleを個別生成）", "kind": "list_each",
     "list_url": "/api/scenario-role", "url_template": "/api/generate-scenario-role/{name}"},
    {"id": "scenario_event_bin", "label": "ScenarioEvent（バイナリ）", "kind": "bulk", "url": "/api/generate-all-event-bin"},
    {"id": "animator", "label": "Animator（全生成）", "kind": "bulk", "url": "/api/generate-all-animator"},
    {"id": "save_data", "label": "SaveData（System/Player）", "kind": "fixed_list",
     "url_template": "/api/generate-save-data/{name}", "items": ["SystemData", "PlayerData"]},
    {"id": "sound", "label": "Sound（C#/バイナリ生成）", "kind": "bulk", "url": "/api/sound/generate"},
    {"id": "texture", "label": "Texture（C#/バイナリ生成）", "kind": "bulk", "url": "/api/texture/generate"},
    {"id": "gameobject", "label": "GameObject（C#/バイナリ生成）", "kind": "bulk", "url": "/api/gameobject/generate"},
    {"id": "material", "label": "Material（C#/バイナリ生成）", "kind": "bulk", "url": "/api/material/generate"},
    {"id": "scene", "label": "Scene（C#生成）", "kind": "bulk", "url": "/api/scene/generate"},
]

_STEP_BY_ID = {s["id"]: s for s in STEPS}


def init(app, data_dir):
    global APP, DATA_DIR
    APP = app
    DATA_DIR = data_dir


def _call(client, method, url):
    resp = client.open(url, method=method)
    ok = 200 <= resp.status_code < 300
    try:
        payload = resp.get_json(silent=True) or {}
    except Exception:
        payload = {}
    message = payload.get("message") or payload.get("error") or f"HTTP {resp.status_code}"
    return ok, message


def _expand_step_calls(client, step):
    """1ステップ分の実際のHTTP呼び出し一覧 [(sub_label, method, url), ...] を返す。"""
    kind = step["kind"]
    if kind == "bulk":
        return [(step["label"], "POST", step["url"])]
    if kind == "fixed_list":
        return [(f"{step['label']}: {name}", "POST", step["url_template"].format(name=name))
                for name in step["items"]]
    if kind == "list_each":
        ok, names = _fetch_names(client, step["list_url"])
        if not ok:
            return []
        return [(f"{step['label']}: {name}", "POST", step["url_template"].format(name=name))
                for name in names]
    return []


def _fetch_names(client, list_url):
    try:
        resp = client.get(list_url)
        if resp.status_code != 200:
            return False, []
        data = resp.get_json(silent=True) or []
        names = [item.get("name") for item in data if isinstance(item, dict) and item.get("name")]
        return True, names
    except Exception:
        return False, []


def _run_job(job_id, step_ids):
    job = _jobs[job_id]
    client = APP.test_client()

    # まず全ステップの実際の呼び出し一覧を展開してtotalを確定させる
    # （list_each系は対象件数が事前に分からないため）
    calls = []  # [(step_id, sub_label, method, url)]
    for step_id in step_ids:
        step = _STEP_BY_ID.get(step_id)
        if not step:
            continue
        for sub_label, method, url in _expand_step_calls(client, step):
            calls.append((step_id, sub_label, method, url))

    with _jobs_lock:
        job["total"] = len(calls)
        job["message"] = f"{len(calls)}件の生成処理を開始します"

    results = []
    error_count = 0
    for idx, (step_id, sub_label, method, url) in enumerate(calls, start=1):
        ok, message = _call(client, method, url)
        if not ok:
            error_count += 1
        results.append({"stepId": step_id, "label": sub_label, "ok": ok, "message": message})
        with _jobs_lock:
            job["done"] = idx
            job["message"] = f"{'✓' if ok else '✗'} {sub_label}"
            job["results"] = results
            job["errorCount"] = error_count

    with _jobs_lock:
        job["status"] = "done"
        job["message"] = (
            f"完了しました（成功 {len(calls) - error_count}件 / 失敗 {error_count}件）"
            if calls else "対象の生成処理がありませんでした"
        )


def start_job(step_ids):
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "total": 0,
            "done": 0,
            "status": "running",
            "message": "準備中...",
            "results": [],
            "errorCount": 0,
        }
    t = threading.Thread(target=_run_job, args=(job_id, step_ids), daemon=True)
    t.start()
    return job_id


def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def register(app, data_dir):
    init(app, data_dir)

    @app.route("/api/generate-all/steps", methods=["GET"])
    def generate_all_steps():
        return jsonify([{"id": s["id"], "label": s["label"]} for s in STEPS])

    @app.route("/api/generate-all/start", methods=["POST"])
    def generate_all_start():
        body = request.get_json(silent=True) or {}
        step_ids = body.get("stepIds") or [s["id"] for s in STEPS]
        unknown = [sid for sid in step_ids if sid not in _STEP_BY_ID]
        if unknown:
            return jsonify({"error": f"未知のステップIDです: {', '.join(unknown)}"}), 400
        job_id = start_job(step_ids)
        return jsonify({"jobId": job_id})

    @app.route("/api/generate-all/progress/<job_id>", methods=["GET"])
    def generate_all_progress(job_id):
        job = get_job(job_id)
        if job is None:
            return jsonify({"error": "指定されたジョブが見つかりません"}), 404
        return jsonify(job)
