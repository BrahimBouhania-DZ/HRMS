"""أمر إدارة: تشغيل ماسح التنبيهات المجدولة (انتهاء عقود/وثائق/تجربة) يوميًا.

مثال (cron يومي):
    30 6 * * * cd /path && .venv/bin/python manage.py run_scheduled_alerts --dry-run
    30 6 * * * cd /path && .venv/bin/python manage.py run_scheduled_alerts
"""

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _


class Command(BaseCommand):
    help = _("يفحص العقود والوثائق وفترات التجربة القريبة من الانتهاء وينشئ التنبيهات.")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help=_("عرض ما سيُطلق دون إنشاء سجلات"))

    def handle(self, *args, **options):
        from apps.notif.scheduler import run_all

        dry_run = options["dry_run"]
        if dry_run:
            stats = run_all(commit=False)
            self.stdout.write(self.style.WARNING(
                _("وضع التجربة (dry-run) — ستُطلق العقود التالية: %(contracts)s، وثائق: %(documents)s، تجربة: %(probation)s")
                % stats))
            return

        stats = run_all()
        self.stdout.write(self.style.SUCCESS(
            _("تم إطلاق التنبيهات — عقود: %(contracts)s، وثائق: %(documents)s، تجربة: %(probation)s")
            % stats))
