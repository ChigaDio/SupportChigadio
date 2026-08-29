# sso/views.py
#
# django-wiki を動かしている別プロセスのDjangoプロジェクトに、新規に小さな
# アプリ("sso")としてこのファイルを追加する。SupportChigadio側
# (pythonSrc/wiki_bridge.py) が発行したHMAC署名付きトークンを検証し、対応
# するDjangoのUserでログインさせた上で、SupportChigadio側のロール
# (admin/editor/viewer) をこのプロジェクトのグループへ反映する。
#
# 手動セットアップ:
#   1. `django-admin startapp sso` し、このファイルを sso/views.py として保存
#   2. settings.py の INSTALLED_APPS に "sso" を追加
#   3. settings.py に WIKI_SSO_SECRET を追加（SupportChigadio側のWIKI_SSO_SECRET
#      と必ず同じ値にする。settings_snippet.py 参照）
#   4. プロジェクトの urls.py に以下を追加:
#        from sso.views import sso_login
#        urlpatterns = [ path("sso/login/", sso_login, name="sso_login"), ... ]
import base64
import binascii
import hashlib
import hmac
import time

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import Group
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect

User = get_user_model()

# SupportChigadioのロール -> このDjangoプロジェクト上のグループ名。
# settings_snippet.py の WIKI_CAN_READ / WIKI_CAN_WRITE と対応させている。
ROLE_GROUPS = {
    "admin": "Wiki Admins",
    "editor": "Wiki Editors",
    "viewer": "Wiki Viewers",
}


def _verify(token):
    """トークンを検証し、成功すれば (username, role) を返す。失敗はNone。"""
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        username, role, exp_s, sig = raw.rsplit("|", 3)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None
    payload = f"{username}|{role}|{exp_s}"
    expected = hmac.new(
        settings.WIKI_SSO_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        if int(exp_s) < int(time.time()):
            return None
    except ValueError:
        return None
    return username, role


def sso_login(request):
    result = _verify(request.GET.get("token", ""))
    if result is None:
        return HttpResponseBadRequest(
            "SSOトークンが無効、または期限切れです。SupportChigadio側から開き直してください。"
        )
    username, role = result

    user, _created = User.objects.get_or_create(username=username, defaults={"email": ""})
    user.is_staff = role == "admin"
    user.save()

    # グループはロールに対応する1つだけを持たせる（前回のロールが残らないよう
    # 一旦すべて外してから、今回のロールのグループだけを付け直す）
    for group_name in ROLE_GROUPS.values():
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.remove(group)
    target_group, _ = Group.objects.get_or_create(name=ROLE_GROUPS.get(role, "Wiki Viewers"))
    user.groups.add(target_group)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(request.GET.get("next") or "/")
