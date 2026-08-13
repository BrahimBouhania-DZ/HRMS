"""أمر إدارة: علام الغياب التلقائي (BR-ATT-004) قبل توليد الرواتب.

مثال:
    python manage.py mark_absences --from 2026-08-01 --to 2026-08-31 --branch 3
    python manage.py mark_absences --from 2026-08-01 --to 2026-08-31 --dry-run
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _


class Command(BaseCommand):
    help = _("علام تلقائي لأيام العمل بلا مسح كغياب (إجازة/مهمة/غياب).")

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="from_date", required=True,
                            help=_("بداية الفترة (YYYY-MM-DD)"))
        parser.add_argument("--to", dest="to_date", required=True,
                            help=_("نهاية الفترة (YYYY-MM-DD)"))
        parser.add_argument("--branch", type=int, default=None,
                            help=_("معرّف الفرع (اختياري؛ الكل إن لم يُحدد)"))
        parser.add_argument("--dry-run", action="store_true",
                            help=_("عرض العدد دون إنشاء أي سجل"))

    def handle(self, *args, **options):
        from apps.attendance.services import auto_mark_absences
        from apps.org.models import Branch

        try:
            from_date = datetime.date.fromisoformat(options["from_date"])
            to_date = datetime.date.fromisoformat(options["to_date"])
        except ValueError:
            raise CommandError(_("صيغة تاريخ غير صالحة — استخدم YYYY-MM-DD"))
        if to_date < from_date:
            raise CommandError(_("نهاية الفترة يجب أن تكون بعد بدايتها"))

        branch = None
        if options["branch"]:
            branch = Branch.objects.filter(pk=options["branch"]).first()
            if branch is None:
                raise CommandError(_("فرع غير موجود: %s") % options["branch"])

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                _("وضع التجربة (dry-run): لن يُنشأ أي سجل.")))
            return

        created = auto_mark_absences(from_date, to_date, branch=branch, user=None)
        self.stdout.write(self.style.SUCCESS(
            _("تم تعليم %(n)s يومًا (غياب/إجازة/مهمة)") % {"n": created}))
