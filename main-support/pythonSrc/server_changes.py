# =====================================================================
# server_changes.py  —  サーバー側の変更箇所(貼り付け用)
#
#  [scenario.py]  ① _write_json_atomic を追加  ② write_sub_event_transition の末尾を差し替え
#                 ③ get_sub_event_transition_rev を追加
#  [app.py]       ④ ロック/ヘルパーを追加  ⑤ handle_transition を丸ごと差し替え
#                 ⑥ handle_subgroup の POST を差し替え  ⑦ save_role_data を丸ごと差し替え
#                 ⑧ add_role を丸ごと差し替え  ⑨ 新規: role-data-batch / rev エンドポイント
# =====================================================================


# ---------------------------------------------------------------------
# [scenario.py] ①  read_sub_event_transition の直前あたりに追加
# ---------------------------------------------------------------------
def _write_json_atomic(path, obj):
    """JSONを一時ファイルへ書いてから os.replace で差し替える。
    書き込み途中でプロセスが落ちても _sub.json が壊れた半端な状態で残らない
    (以前は直接 'w' で開いていたので、保存中の中断=ファイル破損だった)。"""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------
# [scenario.py] ②  write_sub_event_transition の末尾
#   (sub_payload['subId'] = str(subId) の次の行からreturnまで)を、これに差し替える
# ---------------------------------------------------------------------
#     sub_payload = dict(tree) if isinstance(tree, dict) else {}
#     sub_payload['subId'] = str(subId)
#     _write_json_atomic(os.path.join(sub_dir, '_sub.json'), sub_payload)
#     return {"message": f"Sub {subId} を保存しました"}


# ---------------------------------------------------------------------
# [scenario.py] ③  write_sub_event_transition の直後に追加
# ---------------------------------------------------------------------
def get_sub_event_transition_rev(eventId, subId):
    """Sub 1件分のファイル(_sub.json)の更新リビジョン。「更新時刻(ns)-サイズ」。
    ファイルが無ければ '0'。他のタブ/ユーザーの更新検知(画面側の警告バナー)に使う。"""
    event_dir = _resolve_event_dir(eventId)
    if not event_dir or not os.path.isdir(event_dir):
        return '0'
    sub_dir = _find_sub_dir_by_id(event_dir, subId)
    if not sub_dir:
        return '0'
    try:
        st = os.stat(os.path.join(sub_dir, '_sub.json'))
    except OSError:
        return '0'
    return f"{st.st_mtime_ns}-{st.st_size}"


# =====================================================================
# [app.py] ④  `app = Flask(...)` より後ならどこでもOK(handle_transition の手前を推奨)
# =====================================================================
# --- Sub(_sub.json)の「読む→書き換える→書く」を直列化するロック ---
# 保存のたびに read-modify-write するため、複数のリクエストが並行すると
# 後発が古い内容を読んで先の保存を上書きする(ロストアップデート)。
# Sub単位のロックで直列化する(同一プロセス内。複数プロセス運用の場合は別途ファイルロックが必要)。
_SUB_LOCKS = {}
_SUB_LOCKS_GUARD = threading.Lock()


def _sub_lock(eventId, subId):
    key = (str(eventId), str(subId))
    with _SUB_LOCKS_GUARD:
        lock = _SUB_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _SUB_LOCKS[key] = lock
    return lock  # 使い方: with _sub_lock(eventId, subId): ...


def _find_transition_node(nodes, segments):
    """"親id/子id/孫id" を分解したリストから、該当ノードを1階層ずつ降りて探す。
    サブグループは「自分自身のidをキーに中身を持つ」規約(add_roleと同じ)。見つからなければNone。"""
    current = nodes
    target = None
    for i, seg in enumerate(segments):
        found = next((n for n in current if str(n.get('id')) == seg), None)
        if found is None:
            return None
        target = found
        if i < len(segments) - 1:
            data = found.setdefault('data', {})
            sgs = data.setdefault('subgroups', {})
            sg = sgs.setdefault(str(found.get('id')), {'nodes': [], 'edges': []})
            if not isinstance(sg.get('nodes'), list):
                sg['nodes'] = []
            current = sg['nodes']
    return target


def _apply_role_data(node, unique_id, form_data):
    """node.data.roles のうち uniqueId が一致するRoleの data を差し替える。更新した件数を返す。
    以前の save_role_data は role['id'](=Role名)で探していたが、画面が渡すのは uniqueId なので
    一致せず、何も書き込まないまま成功を返していた。
    uniqueId を持たない古いデータだけは、従来どおり id 一致で救済する。"""
    roles = (node.get('data') or {}).get('roles') or []
    updated = 0
    for i, r in enumerate(roles):
        if str(r.get('uniqueId')) == str(unique_id):
            roles[i] = {**r, 'data': form_data}
            updated += 1
    if updated == 0:
        for i, r in enumerate(roles):
            if r.get('uniqueId') in (None, '') and str(r.get('id')) == str(unique_id):
                roles[i] = {**r, 'data': form_data}
                updated += 1
    return updated


# =====================================================================
# [app.py] ⑤  handle_transition を丸ごと差し替え
# =====================================================================
@app.route('/api/scenario-event/<eventId>/sub/<subId>/transition', methods=['GET', 'POST'])
def handle_transition(eventId, subId):
    app.logger.debug(f"Received eventId: {eventId}, subId: {subId}")
    if not eventId or eventId == 'undefined' or not subId or subId == 'undefined':
        app.logger.error(f"Invalid parameters: eventId={eventId}, subId={subId}")
        return jsonify({'error': 'Invalid eventId or subId'}), 400
    if request.method == 'GET':
        try:
            # このSub 1件分のファイルだけを読む(他のSubには一切触れない)
            with _sub_lock(eventId, subId):
                tree = scenario.read_sub_event_transition(eventId, subId)
                rev = scenario.get_sub_event_transition_rev(eventId, subId)
            resp = jsonify(tree)
            resp.headers['X-Sub-Rev'] = rev
            return resp
        except Exception as e:
            app.logger.error(f"Error reading transition for {eventId}/{subId}: {str(e)}")
            return jsonify({'error': str(e)}), 500
    else:  # POST
        try:
            data = request.get_json()
            # 物語設定(storySetting)など、遷移グラフ(nodes/edges)以外の
            # キーが既存のSubデータに同居している場合があるため、
            # 丸ごと置き換えず非破壊マージする（このAPIは遷移グラフの
            # 保存専用であり、物語設定を書き潰さないようにするため）。
            with _sub_lock(eventId, subId):
                existing_sub = scenario.read_sub_event_transition(eventId, subId)
                merged_sub = dict(existing_sub)
                merged_sub.update(data)
                # このSub 1件分のファイルだけを書く(他のSubには一切触れない)
                scenario.write_sub_event_transition(eventId, subId, merged_sub)
                rev = scenario.get_sub_event_transition_rev(eventId, subId)
            return jsonify({'message': 'Transition saved', 'rev': rev})
        except Exception as e:
            app.logger.error(f"Error saving transition for {eventId}/{subId}: {str(e)}")
            return jsonify({'error': str(e)}), 500


# =====================================================================
# [app.py] ⑥  handle_subgroup の `else:  # POST` ブロックを差し替え(GET側はそのまま)
# =====================================================================
#     else:  # POST
#         try:
#             data = request.get_json()
#             with _sub_lock(eventId, subId):
#                 sub_data = scenario.read_sub_event_transition(eventId, subId)
#                 nodes = sub_data.get('nodes', [])
#                 for node in nodes:
#                     if node['id'] == parentId:
#                         node['data']['subgroups'] = node['data'].get('subgroups', {})
#                         node['data']['subgroups'][parentId] = data
#                 sub_data['nodes'] = nodes
#                 scenario.write_sub_event_transition(eventId, subId, sub_data)
#                 rev = scenario.get_sub_event_transition_rev(eventId, subId)
#             return jsonify({'message': 'Subgroup saved', 'rev': rev})
#         except Exception as e:
#             app.logger.error(f"Error saving subgroup for {eventId}/{subId}/{parentId}: {str(e)}")
#             return jsonify({'error': str(e)}), 500


# =====================================================================
# [app.py] ⑦  save_role_data を丸ごと差し替え(旧クライアント互換用。新しい画面は role-data-batch を使う)
# =====================================================================
@app.route('/api/save-role-data/<eventId>/<subId>/<nodeId>/<roleId>', methods=['POST'])
def save_role_data(eventId, subId, nodeId, roleId):
    try:
        data = request.get_json()
        formData = data.get('formData', {})
        # このSub 1件分だけを読み書きする(他のSubには一切触れない)。
        # roleId には画面から uniqueId が渡される(_apply_role_data 参照)。
        with _sub_lock(eventId, subId):
            sub_data = scenario.read_sub_event_transition(eventId, subId)
            nodes = sub_data.get('nodes', [])
            updated = 0
            for node in nodes:
                if str(node['id']) == str(nodeId):
                    updated += _apply_role_data(node, roleId, formData)
                    break
                sg = (node.get('data') or {}).get('subgroups', {}).get(nodeId)
                if sg:
                    # 旧仕様: サブグループ内ノードは「そのサブグループの先頭ノード」だけを見ていた。
                    # 先頭に無ければ、同じサブグループ内の全ノードから uniqueId で探す。
                    for child in sg.get('nodes', []):
                        updated += _apply_role_data(child, roleId, formData)
                    break
            if updated:
                sub_data['nodes'] = nodes
                scenario.write_sub_event_transition(eventId, subId, sub_data)
            rev = scenario.get_sub_event_transition_rev(eventId, subId)
        return jsonify({'message': 'Role data saved', 'saved': updated, 'rev': rev})
    except Exception as e:
        app.logger.error(f"Error saving role data: {str(e)}")
        return jsonify({'error': str(e)}), 500


# =====================================================================
# [app.py] ⑧  add_role を丸ごと差し替え(変更点: ロック + レスポンスに rev)
# =====================================================================
@app.route('/api/scenario-event/<eventId>/sub/<int:subId>/transition/<path:nodeId>/role', methods=['POST'])
def add_role(eventId, subId, nodeId):
    """指定したノード(nodeId)にRoleを1つ追加する。
    nodeId は "親id/子id/孫id..." のようなパス形式を受け付ける(トップレベルのノードを指す場合は単に "id" のみ)。
    各階層でidが1から振り直されるため、1階層ずつ確実に降りて対象ノードを特定する(_find_transition_node)。"""
    try:
        data = request.get_json()
        path_segments = [seg for seg in nodeId.split('/') if seg != '']
        if not path_segments:
            return jsonify({'error': 'Invalid nodeId'}), 400

        # 新しく追加するRoleのdataは、そのRoleの現在のフィールド定義「全件」を埋めて初期化する
        # (scenario.build_default_role_data: 保存済みdefault → subFields再構築 → 候補一覧の先頭 → 型ごとの汎用初期値)。
        default_field_data = scenario.build_default_role_data(data.get('name'), DATA_DIR)

        with _sub_lock(eventId, subId):
            sub_data = scenario.read_sub_event_transition(eventId, subId)
            nodes = sub_data.get('nodes', [])
            if not isinstance(nodes, list):
                nodes = []
                sub_data['nodes'] = nodes

            target_node = _find_transition_node(nodes, path_segments)
            if target_node is None:
                return jsonify({'error': f'Node not found: {nodeId}'}), 404

            target_node.setdefault('data', {})
            target_node['data']['roles'] = target_node['data'].get('roles', []) + [{
                'id': data['roleId'],
                'name': data['name'],
                'branchType': data['branchType'],
                'uniqueId': data.get('uniqueId'),
                'data': default_field_data,
            }]

            sub_data['nodes'] = nodes
            scenario.write_sub_event_transition(eventId, subId, sub_data)
            rev = scenario.get_sub_event_transition_rev(eventId, subId)
        return jsonify({'message': 'Role added', 'data': default_field_data, 'rev': rev})
    except Exception as e:
        app.logger.error(f"Error adding role: {str(e)}")
        return jsonify({'error': str(e)}), 500


# =====================================================================
# [app.py] ⑨  新規エンドポイント(add_role の直後あたりに追加)
# =====================================================================
@app.route('/api/scenario-event/<eventId>/sub/<subId>/role-data-batch', methods=['POST'])
def save_role_data_batch(eventId, subId):
    """複数Role分のフィールド値を「1リクエスト・1回の読み書き」でまとめて保存する。
    body: {"updates": [{"nodePath": "親id/子id", "uniqueId": "...", "formData": [...]}, ...]}
    nodePath はトップレベルなら "id"、サブグループ内なら "親id/子id"(画面のnodePathと同じ)。
    戻り値: {"saved": 件数, "missed": [{nodePath, uniqueId}, ...], "rev": 新リビジョン}
      missed = サーバー上のファイルに該当Roleが無かったもの(まだ構造が保存されていない新規Role等)。
               画面側は、その分を通常のツリー保存で書き込む。"""
    try:
        payload = request.get_json(silent=True) or {}
        updates = payload.get('updates') or []
        saved = 0
        missed = []
        with _sub_lock(eventId, subId):
            sub_data = scenario.read_sub_event_transition(eventId, subId)
            nodes = sub_data.get('nodes', [])
            for u in updates:
                segments = [s for s in str(u.get('nodePath', '')).split('/') if s != '']
                target = _find_transition_node(nodes, segments) if segments else None
                if target is not None and _apply_role_data(target, u.get('uniqueId'), u.get('formData')) > 0:
                    saved += 1
                else:
                    missed.append({'nodePath': u.get('nodePath'), 'uniqueId': u.get('uniqueId')})
            if saved:
                sub_data['nodes'] = nodes
                scenario.write_sub_event_transition(eventId, subId, sub_data)
            rev = scenario.get_sub_event_transition_rev(eventId, subId)
        return jsonify({'message': 'Role data saved', 'saved': saved, 'missed': missed, 'rev': rev})
    except Exception as e:
        app.logger.error(f"Error saving role data batch: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/scenario-event/<eventId>/sub/<subId>/rev', methods=['GET'])
def get_sub_rev(eventId, subId):
    """Sub 1件分のリビジョンだけを返す軽量API(他のタブ/ユーザーによる更新の検知用)。"""
    try:
        return jsonify({'rev': scenario.get_sub_event_transition_rev(eventId, subId)})
    except Exception as e:
        app.logger.error(f"Error reading sub rev: {str(e)}")
        return jsonify({'error': str(e)}), 500
