"""أمر تهيئة الإجازات: أنواع قياسية + أرصدة سنة (S4).

الاستخدام:
    python manage.py seed_leave                       # أنواع فقط
    python manage.py seed_leave --year 2026           # أنواع + أرصدة السنة
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.employees.models import Employee
from apps.leave.models import LeaveType
from apps.leave.services import get_or_create_balance

STANDARD_TYPES = [
    {
        "code": "annual", "name_ar": "سنوية", "name_fr": "Annuelle", "name_en": "Annual",
        "days_per_year": 30, "carryover_allowed": True, "max_carryover_days": 15,
        "is_unpaid": False, "requires_approval_levels": 1,
    },
    {
        "code": "sick", "name_ar": "مرضية", "name_fr": "Maladie", "name_en": "Sick",
        "days_per_year": 30, "carryover_allowed": False, "max_carryover_days": 0,
        "is_unpaid": False, "requires_approval_levels": 1,
    },
    {
        "code": "maternity", "name_ar": "أمومة", "name_fr": "Maternité", "name_en": "Maternity",
        "days_per_year": 98, "carryover_allowed": False, "max_carryover_days": 0,
        "is_unpaid": False, "requires_approval_levels": 1, "applicable_to": "gender_female",
    },
    {
        "code": "unpaid", "name_ar": "بدون أجر", "name_fr": "Sans solde", "name_en": "Unpaid",
        "days_per_year": 0, "carryover_allowed": False, "max_carryover_days": 0,
        "is_unpaid": True, "requires_approval_levels": 2,
    },
]


class Command(BaseCommand):
    help = "تهيئة أنواع الإجازات القياسية وأرصدة السنة (T-022/T-023)"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=None, help="منح أرصدة السنة المحددة")

    def handle(self, *args, **options):
        created = 0
        for item in STANDARD_TYPES:
            _, was_created = LeaveType.objects.get_or_create(code=item["code"], defaults=item)
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"أنواع الإجازات: {len(STANDARD_TYPES)} (جديد: {created})"))

        year = options["year"]
        if year:
            employees = Employee.objects.filter(is_active=True)
            balances = 0
            for lt in LeaveType.objects.filter(is_active=True):
                for emp in employees:
                    if lt.applicable_to == "gender_female" and emp.gender != "F":
                        continue
                    get_or_create_balance(emp, lt, year)
                    balances += 1
            self.stdout.write(
                self.style.SUCCESS(f"أرصدة {year}: {balances} سجلًا (ممنوح = أيام السنة عند الإنشاء)")
            )
        else:
            self.stdout.write("استخدم --year لتوليد أرصدة السنة.")
