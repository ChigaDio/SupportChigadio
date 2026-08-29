# wiki/management/commands/export_wiki_to_data_dir.py
#
# django-wiki 側の記事本文（DB保存）を、SupportChigadioのDATA_DIR配下へ
# Markdownファイルとしてエクスポートするコマンド。これにより、Wikiの内容も
# SupportChigadio側の pythonSrc/vcs.py（Git/SVN操作ページ）でバックアップ・
# 差分確認できるようになる（あくまでDB→ファイルへの一方向ミラーであり、
# このエクスポートファイルを直接編集しても記事には反映されない点に注意）。
#
# 実行例:
#   python manage.py export_wiki_to_data_dir --data-dir "/path/to/SupportChigadio/data"
# cron等で数分おきに実行するか、ArticleRevisionのpost_saveシグナルから
# 呼び出す形にしてもよい。
import os

from django.core.management.base import BaseCommand, CommandError

from wiki.models import URLPath


class Command(BaseCommand):
    help = "django-wikiの記事本文をDATA_DIR/wiki_export配下へMarkdownとしてエクスポートする"

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", required=True, help="SupportChigadioのDATA_DIRの絶対パス")

    def handle(self, *args, **options):
        data_dir = options["data_dir"]
        if not os.path.isdir(data_dir):
            raise CommandError(f"DATA_DIRが見つかりません: {data_dir}")
        export_root = os.path.join(data_dir, "wiki_export")
        os.makedirs(export_root, exist_ok=True)

        count = 0
        for urlpath in URLPath.objects.all():
            article = urlpath.article
            current = article.current_revision
            if current is None:
                continue
            rel = urlpath.path.strip("/") or "root"
            file_path = os.path.join(export_root, *rel.split("/")) + ".md"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# {current.title}\n\n{current.content}\n")
            count += 1

        self.stdout.write(self.style.SUCCESS(f"{count}件の記事を {export_root} へエクスポートしました"))
