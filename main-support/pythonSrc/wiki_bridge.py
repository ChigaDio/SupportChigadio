# -*- coding: utf-8 -*-
"""
pythonSrc/wiki_bridge.py

Wikiは自前実装ではなく、別プロセスで動かす django-wiki を使う方針に変更した
ため、このモジュールは「SupportChigadioのログイン状態から django-wiki 側へ
シングルサインオンするための署名付きトークンを発行する」だけの薄いブリッジ
に徹する（旧 pythonSrc/wiki.py のページCRUD一式はもう使わない。app.pyへは
登録しないこと）。

- 共有シークレット(環境変数 WIKI_SSO_SECRET)をdjango-wiki側とも共有し、
  HMAC-SHA256で署名した短命(60秒)トークンを発行する。django-wiki側に追加
  する /sso/login/ がこのトークンを検証してDjangoのUserでログインさせ、
  SupportChigadioのロール(admin/editor/viewer)をDjangoのグループへ反映する
  （対応するDjango側コードは別途 sso_auth_views.py として渡す）。
- トークンはURLクエリとして一度だけ使われる想定のため有効期限を短くしている
  （ブラウザ履歴等への残留リスクを抑えるため）。
- ローカルモードでは認証の概念が無いため、環境変数 WIKI_LOCAL_USERNAME
  （既定"local"）・WIKI_LOCAL_ROLE（既定"admin"）を使った固定ユーザーで
  SSOする。
"""
import base64
import hashlib
import hmac
import os
import time

WIKI_BASE_URL = os.environ.get("WIKI_BASE_URL", "http://localhost:8001")
WIKI_SSO_SECRET = os.environ.get("WIKI_SSO_SECRET", "")
_TOKEN_TTL_SECONDS = 60


def _sign(payload):
    return hmac.new(WIKI_SSO_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_token(username, role):
    exp = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{username}|{role}|{exp}"
    raw = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def register(app, data_dir, server_mode=False):
    from flask import jsonify
    import pythonSrc.auth as auth

    @app.route("/api/wiki-bridge/launch", methods=["GET"])
    def wiki_bridge_launch():
        if not WIKI_SSO_SECRET:
            return jsonify({"error": "WIKI_SSO_SECRET が設定されていません（サーバーの環境変数を確認してください）"}), 500
        if server_mode:
            user = auth.current_user()
            if user is None:
                return jsonify({"error": "ログインが必要です"}), 401
            username, role = user["username"], user["role"]
        else:
            username = os.environ.get("WIKI_LOCAL_USERNAME", "local")
            role = os.environ.get("WIKI_LOCAL_ROLE", "admin")
        token = issue_token(username, role)
        return jsonify({"url": f"{WIKI_BASE_URL.rstrip('/')}/sso/login/?token={token}"})
