"""تنفيذ التقارير المجدولة (T-REP-5).

يُشغَّل عبر cron يوميًا:  manage.py run_scheduled_reports
المرجع: docs/12-operations.md §3 (الجدولة اليومية).
"""

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from ...scheduling import run_scheduled_reports


class Command(BaseCommand):
    help = _("ينفّذ التقارير التي حان موعد جدولتها ويُشعر المستلمين")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help=_("محاكاة فقط دون أي كتابة"))

    def handle(self, *args, **options):
        if options["dry_run"]:
            jobs = run_scheduled_reports(commit=False)
            self.stdout.write(_("محاكاة: %s تقريرًا سيتنفذ الآن.") % len(jobs))
            return
        jobs = run_scheduled_reports(commit=True)
        done = sum(1 for j in jobs if j.status == "done")
        failed = sum(1 for j in jobs if j.status == "failed")
        self.stdout.write(self.style.SUCCESS(_("نُفّذ %s تقريرًا (نجح %s، فشل %s).") % (len(jobs), done, failed)))
