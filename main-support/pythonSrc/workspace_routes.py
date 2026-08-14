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

    @app.route("/api/workspace/logs/all", methods=["GET"])
    def workspace_logs_all():
        """直近7日分だけでなく、アーカイブ済みの過去分も含めた全体ログを
        フィルタ・キーワード検索・ページネーション付きで返す。"""
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 100))
        entries, total = activity_log.read_all(
            user=request.args.get("user") or None,
            method=request.args.get("method") or None,
            category=request.args.get("category") or None,
            date_from=request.args.get("dateFrom") or None,
            date_to=request.args.get("dateTo") or None,
            keyword=request.args.get("keyword") or None,
            offset=offset,
            limit=limit,
        )
        return jsonify({"entries": entries, "total": total, "offset": offset, "limit": limit})

    @app.route("/api/workspace/logs/filters", methods=["GET"])
    def workspace_logs_filters():
        """全体ログ画面のフィルタ用プルダウンに使う選択肢一覧。"""
        return jsonify({
            "users": activity_log.list_users(),
            "categories": activity_log.list_categories(),
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE"],
        })
