# -*- coding: utf-8 -*-
"""
pythonSrc/workspace_routes.py

ワークスペースページ用の集約API。
- 現在のアクティブバージョン
- 各ユーザーの直近の編集ログ(最大7日分)
- お知らせの最新一覧
"""
from flask import jsonify, request

import pythonSrc.activity_log as activity_log
import pythonSrc.versioning as versioning
import pythonSrc.announcements as announcements


def register(app, data_dir, server_mode):
    @app.route("/api/workspace", methods=["GET"])
    def workspace_summary():
        limit = int(request.args.get("limit", 50))
        return jsonify({
            "serverMode": server_mode,
            "currentVersion": versioning.get_active(),
            "recentLogs": activity_log.read_recent(limit=limit),
            "announcements": announcements.list_all()[:5],
        })

    @app.route("/api/workspace/logs", methods=["GET"])
    def workspace_logs():
        limit = int(request.args.get("limit", 200))
        user = request.args.get("user")
        return jsonify(activity_log.read_recent(limit=limit, user=user))
