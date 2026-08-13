"""أمر النسخ الاحتياطي — للجدولة عبر cron/systemd أو يدوي.

الاستعمال:
    python manage.py backup_db [--kind manual|daily|weekly] [--user <pk>]

مثال جدولة يومية 02:00 (crontab):
    0 2 * * * cd /path/to/hrms && .venv/bin/python manage.py backup_db --kind daily >> /var/log/hrms_backup.log 2>&1
"""

from django.core.management.base import BaseCommand

from apps.backup.models import BackupJob
from apps.backup.services import run_backup


class Command(BaseCommand):
    help = "ينفّذ نسخة احتياطية مشفرة لقاعدة البيانات (SQLite/PostgreSQL)."

    def add_arguments(self, parser):
        parser.add_argument("--kind", choices=BackupJob.Kind.values, default=BackupJob.Kind.MANUAL)
        parser.add_argument("--user", type=int, default=None, help="PK لمستخدم يظهر كمنشئ النسخة")

    def handle(self, *args, **options):
        user = None
        if options["user"]:
            from django.contrib.auth import get_user_model

            user = get_user_model().objects.filter(pk=options["user"]).first()
        job = run_backup(kind=options["kind"], user=user)
        self.stdout.write(self.style.SUCCESS(f"نسخة ناجحة: {job.file_path}"))
