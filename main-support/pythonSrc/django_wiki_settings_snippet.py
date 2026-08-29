# settings.py への追加分（django-wiki を動かしているDjangoプロジェクト側）
#
# 実際のsettings.pyの適切な場所（INSTALLED_APPS定義の後など）に、以下の
# 内容をマージすること。既存のdjango-wiki用設定（WIKI_ACCOUNT_HANDLING等）
# には触れていない。
import os

# --- SupportChigadioとのSSO ---
# 必ず SupportChigadio 側の環境変数 WIKI_SSO_SECRET と同じ値にする。
WIKI_SSO_SECRET = os.environ.get("WIKI_SSO_SECRET", "")

INSTALLED_APPS = INSTALLED_APPS + ["sso"]  # 既存のINSTALLED_APPSに追加

# SupportChigadio側からiframeで埋め込みたい場合はSAMEORIGINへ緩める。
# 別オリジンで埋め込む場合はnginx等のリバースプロキシで同一オリジンに
# 揃えるか、django-xframeoptions等でホワイトリスト運用にすること。
X_FRAME_OPTIONS = "SAMEORIGIN"


# --- django-wikiの読み書き権限をグループ単位で制御 ---
# sso/views.py が SupportChigadio のロールに応じて付与するグループ名と
# 対応させている（Wiki Admins / Wiki Editors / Wiki Viewers）。
def wiki_can_read(article, user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Wiki Admins", "Wiki Editors", "Wiki Viewers"]).exists()


def wiki_can_write(article, user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Wiki Admins", "Wiki Editors"]).exists()


def wiki_can_delete(article, user):
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name="Wiki Admins").exists()


WIKI_CAN_READ = wiki_can_read
WIKI_CAN_WRITE = wiki_can_write
WIKI_CAN_DELETE = wiki_can_delete
WIKI_CAN_MODERATE = wiki_can_delete
WIKI_ANONYMOUS = False  # 未ログインでの閲覧は不可にする（SSO経由のみ許可）
