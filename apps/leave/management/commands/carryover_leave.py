"""أمر إدارة: ترحيل أرصدة الإجازات من سنة إلى سنة (S4).

مثال:
    python manage.py carryover_leave --year 2026 --dry-run
    python manage.py carryover_leave --year 2026 --branch 3
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _

from apps.employees.models import Employee


class Command(BaseCommand):
    help = _("ترحيل المتبقي من أرصدة العام السابق إلى السنة المستهدفة.")

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, required=True,
                            help=_("السنة المستهدفة (تستلم رصيد العام السابق)"))
        parser.add_argument("--branch", type=int, default=None,
                            help=_("معرّف الفرع (اختياري؛ الكل إن لم يُحدد)"))
        parser.add_argument("--dry-run", action="store_true",
                            help=_("عرض العدد دون أي تغيير"))

    def handle(self, *args, **options):
        from apps.leave.models import LeaveType
        from apps.leave.services import LeaveError, carryover_balance

        to_year = options["year"]
        from_year = to_year - 1

        employees = Employee.objects.filter(is_active=True)
        if options["branch"]:
            from apps.org.models import Branch

            branch = Branch.objects.filter(pk=options["branch"]).first()
            if branch is None:
                raise CommandError(_("فرع غير موجود: %s") % options["branch"])
            employees = employees.filter(branch=branch)

        carried = 0
        skipped = 0
        for lt in LeaveType.objects.filter(is_active=True, carryover_allowed=True):
            for emp in employees:
                if lt.applicable_to == "gender_female" and emp.gender != "F":
                    continue
                if options["dry_run"]:
                    carried += 1
                    continue
                try:
                    carryover_balance(emp, lt, from_year, to_year, user=None)
                    carried += 1
                except LeaveError:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            _("تم ترحيل أرصدة %(n)s حالة (سنة %(to)s)") % {"n": carried, "to": to_year}))
        if skipped:
            self.stdout.write(self.style.WARNING(_("حالات لم تُرحّل: %s") % skipped))
