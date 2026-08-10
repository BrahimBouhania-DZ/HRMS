"""أمر بيانات تجريبية (Demo) — هيكل تنظيمي + موظفون + حضور + إجازات + رواتب.

الاستخدام:
    python manage.py seed_demo                        # ~15 موظفًا + بيانات تشغيلية
    python manage.py seed_demo --employees 12         # عدد موظفين محدد
    python manage.py seed_demo --no-users             # بدون حسابات مستخدمين
    python manage.py seed_demo --no-attendance        # بدون أيام حضور
    python manage.py seed_demo --payrun               # + دورة رواتب معتمدة (2026-07)

مبدأ التشغيل: الأمر متكرر (idempotent) — لا يحذف أي بيانات؛ يتخطى السجلات الموجودة
بحسب المفاتيح الفريدة (رمز الفرع/القسم/المنصب/رقم الموظف...). كلمات مرور حسابات
الديمو ثابتة: Demo@2026! (للتجربة المحلية فقط، لا للإنتاج).
"""

import datetime
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.attendance.models import AttendanceDay, AttendanceException, AttendanceScan
from apps.devices.models import QrDevice
from apps.employees.models import Contract, Employee
from apps.leave.models import LeaveRequest, LeaveType, PublicHoliday
from apps.leave.services import WEEKEND_DAYS, approve_request, get_or_create_balance, submit_request
from apps.notif.models import Notification
from apps.org.models import Branch, Department, Position, Shift
from apps.payroll.models import PayElement, PayRun
from apps.payroll.services import approve_payrun, generate_payrun, review_payrun

DEMO_PASSWORD = "Demo@2026!"

BRANCHES = [
    {"code": "BR-HQ", "name_ar": "المقر الرئيسي — الجزائر", "name_fr": "Siège — Alger", "name_en": "Headquarters — Algiers",
     "country": "DZ", "city": "الجزائر", "timezone": "Africa/Algiers"},
    {"code": "BR-OR", "name_ar": "فرع وهران", "name_fr": "Agence d'Oran", "name_en": "Oran Branch",
     "country": "DZ", "city": "وهران", "timezone": "Africa/Algiers"},
]

SHIFTS = [
    {"code": "SH-MOR", "name_ar": "صباحي", "name_fr": "Matin", "name_en": "Morning",
     "start_time": "08:00", "end_time": "16:00"},
    {"code": "SH-AFT", "name_ar": "مسائي", "name_fr": "Après-midi", "name_en": "Afternoon",
     "start_time": "14:00", "end_time": "22:00"},
    {"code": "SH-ADM", "name_ar": "إداري", "name_fr": "Administratif", "name_en": "Administrative",
     "start_time": "09:00", "end_time": "17:00", "is_flexible": True, "grace_minutes": 20},
]

DEPARTMENTS = [
    {"code": "D-FIN", "name_ar": "المالية", "name_fr": "Finances", "name_en": "Finance"},
    {"code": "D-HR", "name_ar": "الموارد البشرية", "name_fr": "Ressources Humaines", "name_en": "Human Resources"},
    {"code": "D-IT", "name_ar": "تقنية المعلومات", "name_fr": "Informatique", "name_en": "IT"},
    {"code": "D-OPS", "name_ar": "العمليات", "name_fr": "Opérations", "name_en": "Operations"},
    {"code": "D-SLS", "name_ar": "المبيعات", "name_fr": "Ventes", "name_en": "Sales"},
]

POSITIONS = [
    {"code": "P-MGR", "name_ar": "مدير قسم", "name_fr": "Chef de département", "name_en": "Department Manager", "dept": "D-HR", "grade": "A1"},
    {"code": "P-ACC", "name_ar": "محاسب", "name_fr": "Comptable", "name_en": "Accountant", "dept": "D-FIN", "grade": "B2"},
    {"code": "P-DEV", "name_ar": "مطور برمجيات", "name_fr": "Développeur", "name_en": "Software Developer", "dept": "D-IT", "grade": "B1"},
    {"code": "P-SUP", "name_ar": "فني دعم", "name_fr": "Support technique", "name_en": "IT Support", "dept": "D-IT", "grade": "C1"},
    {"code": "P-HRO", "name_ar": "موظف موارد بشرية", "name_fr": "Chargé de RH", "name_en": "HR Officer", "dept": "D-HR", "grade": "B2"},
    {"code": "P-OPT", "name_ar": "مشغل عمليات", "name_fr": "Opérateur", "name_en": "Operator", "dept": "D-OPS", "grade": "C2"},
    {"code": "P-SRE", "name_ar": "مندوب مبيعات", "name_fr": "Représentant commercial", "name_en": "Sales Representative", "dept": "D-SLS", "grade": "B3"},
]

PAY_ELEMENTS = [
    {"code": "E-TRANS", "name_ar": "بدل النقل", "name_fr": "Indemnité transport", "name_en": "Transport allowance",
     "kind": "earning", "calculation": "fixed", "amount": 4000},
    {"code": "E-MEAL", "name_ar": "بدل المأكل", "name_fr": "Indemnité repas", "name_en": "Meal allowance",
     "kind": "earning", "calculation": "fixed", "amount": 3000},
    {"code": "E-SOC", "name_ar": "اشتراك الضمان الاجتماعي", "name_fr": "Sécurité sociale", "name_en": "Social security",
     "kind": "deduction", "calculation": "percent_of_basic", "percent": 9},
]

EMPLOYEES = [
    # (code, first_ar, last_ar, first_fr, last_fr, gender, dept, position, shift, status, hire_date)
    ("EMP-101", "أحمد", "بن يوسف", "Ahmed", "Ben Youcef", "M", "D-HR", "P-MGR", "SH-ADM", "active", "2018-03-01"),
    ("EMP-102", "سارة", "مرابط", "Sara", "Merabet", "F", "D-FIN", "P-ACC", "SH-MOR", "active", "2019-07-15"),
    ("EMP-103", "يوسف", "بوعلام", "Youcef", "Boualem", "M", "D-IT", "P-DEV", "SH-MOR", "active", "2020-01-06"),
    ("EMP-104", "أمينة", "قاسمي", "Amina", "Kacemi", "F", "D-IT", "P-SUP", "SH-MOR", "active", "2021-09-01"),
    ("EMP-105", "محمد", "عثماني", "Mohamed", "Othmani", "M", "D-SLS", "P-SRE", "SH-MOR", "active", "2020-05-11"),
    ("EMP-106", "خديجة", "بلقاسم", "Khadija", "Belkacem", "F", "D-HR", "P-HRO", "SH-ADM", "active", "2021-02-22"),
    ("EMP-107", "إلياس", "سعدي", "Ilyes", "Saadi", "M", "D-OPS", "P-OPT", "SH-MOR", "active", "2022-04-04"),
    ("EMP-108", "نور الهدى", "شريف", "Nour El Houda", "Cherif", "F", "D-FIN", "P-ACC", "SH-MOR", "active", "2020-10-12"),
    ("EMP-109", "عبد القادر", "لونيسي", "Abdelkader", "Lounici", "M", "D-OPS", "P-OPT", "SH-AFT", "active", "2021-11-01"),
    ("EMP-110", "فاطمة الزهراء", "طيب", "Fatima Zahra", "Tayeb", "F", "D-SLS", "P-SRE", "SH-MOR", "active", "2022-01-17"),
    ("EMP-111", "رضا", "بوراس", "Redha", "Bouras", "M", "D-IT", "P-SUP", "SH-AFT", "active", "2022-06-13"),
    ("EMP-112", "مريم", "حجاج", "Meriem", "Hadjadj", "F", "D-HR", "P-HRO", "SH-ADM", "active", "2023-03-06"),
    ("EMP-113", "سفيان", "زروقي", "Sofiane", "Zerrouki", "M", "D-IT", "P-DEV", "SH-MOR", "probation", "2026-05-04"),
    ("EMP-114", "حنان", "بوقرة", "Hanane", "Bouguerra", "F", "D-FIN", "P-ACC", "SH-MOR", "probation", "2026-06-01"),
    ("EMP-115", "جمال", "دحماني", "Djamel", "Dahmani", "M", "D-SLS", "P-SRE", "SH-MOR", "active", "2019-12-02"),
]

HOLIDAYS = [
    ("2026-01-01", "رأس السنة الميلادية", "Nouvel an", "New Year"),
    ("2026-05-01", "عيد العمال", "Fête du travail", "Labour Day"),
    ("2026-07-05", "عيد الاستقلال", "Fête de l'indépendance", "Independence Day"),
]


class Command(BaseCommand):
    help = "بيانات تجريبية: فروع/أقسام/مناصب/دوام + موظفون + عقود + حضور + إجازات + رواتب"

    def add_arguments(self, parser):
        parser.add_argument("--employees", type=int, default=15, help="عدد الموظفين (يُقيَّد بالبيانات المتاحة)")
        parser.add_argument("--no-users", action="store_true", help="لا تُنشئ حسابات مستخدمين للموظفين")
        parser.add_argument("--no-attendance", action="store_true", help="لا تُنشئ أيام حضور")
        parser.add_argument("--payrun", action="store_true", help="أنشئ دورة رواتب 2026-07 معتمدة")

    def handle(self, *args, **options):
        self._seed_org()
        self._seed_elements()
        self._seed_devices()
        self._seed_holidays()
        employees = self._seed_employees(options["employees"])
        if not options["no_users"]:
            self._seed_users(employees)
        self._seed_qr(employees)
        self._seed_balances()
        if not options["no_attendance"]:
            self._seed_attendance(employees)
        self._seed_operational(employees)
        if options["payrun"]:
            self._seed_payrun()
        self.stdout.write(self.style.SUCCESS("اكتملت البيانات التجريبية (seed_demo)."))

    # ------------------------------------------------------------------ الهيكل التنظيمي
    def _seed_org(self):
        created = {"branches": 0, "departments": 0, "positions": 0, "shifts": 0}
        branches = {}
        for b in BRANCHES:
            obj, c = Branch.objects.get_or_create(code=b["code"], defaults=b)
            branches[b["code"]] = obj
            created["branches"] += int(c)
        shifts = {}
        for s in SHIFTS:
            obj, c = Shift.objects.get_or_create(code=s["code"], defaults=s)
            shifts[s["code"]] = obj
            created["shifts"] += int(c)
        depts, positions = {}, {}
        for d in DEPARTMENTS:
            obj, c = Department.objects.get_or_create(
                branch=branches["BR-HQ"], code=d["code"], defaults={**d, "branch": branches["BR-HQ"]},
            )
            depts[d["code"]] = obj
            created["departments"] += int(c)
        for p in POSITIONS:
            defaults = {k: v for k, v in p.items() if k != "dept"}
            defaults["department"] = depts[p["dept"]]
            obj, c = Position.objects.get_or_create(code=p["code"], defaults=defaults)
            positions[p["code"]] = obj
            created["positions"] += int(c)
        self.stdout.write(self.style.SUCCESS(
            f"الهيكل التنظيمي: فروع {created['branches']} | أقسام {created['departments']} | "
            f"مناصب {created['positions']} | دوام {created['shifts']} (جديد)"
        ))
        self._org = {"branches": branches, "depts": depts, "positions": positions, "shifts": shifts}

    def _seed_elements(self):
        created = 0
        for e in PAY_ELEMENTS:
            _, c = PayElement.objects.get_or_create(code=e["code"], defaults=e)
            created += int(c)
        self.stdout.write(self.style.SUCCESS(f"عناصر الأجر: {len(PAY_ELEMENTS)} (جديد: {created})"))

    def _seed_devices(self):
        branch = Branch.objects.get(code="BR-HQ")
        data = [
            {"device_code": "DEV-001", "branch": branch, "api_key_hash": "demo-hash-001", "location": "المدخل الرئيسي"},
            {"device_code": "DEV-002", "branch": branch, "api_key_hash": "demo-hash-002", "location": "الطابق الأرضي"},
        ]
        created = 0
        for d in data:
            _, c = QrDevice.objects.get_or_create(device_code=d["device_code"], defaults=d)
            created += int(c)
        self.stdout.write(self.style.SUCCESS(f"قارئات QR: {len(data)} (جديد: {created})"))

    def _seed_holidays(self):
        branch = Branch.objects.get(code="BR-HQ")
        created = 0
        for date_str, ar, fr, en in HOLIDAYS:
            _, c = PublicHoliday.objects.get_or_create(
                branch=branch, date=datetime.date.fromisoformat(date_str),
                defaults={"name_ar": ar, "name_fr": fr, "name_en": en, "is_recurring": True},
            )
            created += int(c)
        self.stdout.write(self.style.SUCCESS(f"العطل الرسمية: {len(HOLIDAYS)} (جديد: {created})"))

    # ------------------------------------------------------------------ الموظفون والعقود
    def _seed_employees(self, limit):
        org = self._org
        branches, depts, positions, shifts = org["branches"], org["depts"], org["positions"], org["shifts"]
        employees, created_count = [], 0
        for code, f_ar, l_ar, f_fr, l_fr, gender, dept, pos, shift, status, hire in EMPLOYEES[:limit]:
            rng = random.Random(code)
            hire_date = datetime.date.fromisoformat(hire)
            birth_date = hire_date - datetime.timedelta(days=rng.randint(9000, 14000))
            emp, created = Employee.objects.get_or_create(
                employee_code=code,
                defaults={
                    "first_name_ar": f_ar, "last_name_ar": l_ar,
                    "first_name_fr": f_fr, "last_name_fr": l_fr,
                    "first_name_en": f_fr, "last_name_en": l_fr,
                    "gender": gender, "birth_date": birth_date,
                    "hire_date": hire_date, "is_active": True,
                    "phone": f"+213 5{rng.randint(10000000, 99999999)}",
                    "email": f"{code.lower()}@hrms.local",
                    "bank_account": f"DZ{rng.randint(10000000000, 99999999999)}",
                    "employment_status": status,
                    "branch": branches["BR-HQ"], "department": depts[dept],
                    "position": positions[pos], "shift": shifts[shift],
                },
            )
            if created:
                base = round(rng.uniform(35000, 80000), 2)
                allowance = round(rng.uniform(3000, 8000), 2)
                Contract.objects.create(
                    contract_number=f"CTR-{code}",
                    employee=emp, contract_type=Contract.ContractType.CDI,
                    start_date=hire_date,
                    gross_salary=base + allowance, base_salary=base, allowance=allowance,
                )
                created_count += 1
            employees.append(emp)
        self.stdout.write(self.style.SUCCESS(
            f"الموظفون: {len(employees)} (جديد: {created_count}) — كلمات مرور الديمو: {DEMO_PASSWORD}"
        ))
        return employees

    def _seed_users(self, employees):
        User = get_user_model()
        created = 0
        for emp in employees:
            if emp.user_id:
                continue
            username = emp.employee_code.lower()
            user, c = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": emp.email or "",
                    "first_name": emp.first_name_fr or emp.first_name_ar,
                    "last_name": emp.last_name_fr or emp.last_name_ar,
                },
            )
            if c:
                user.set_password(DEMO_PASSWORD)
                user.save()
                emp.user = user
                emp.save(update_fields=["user"])
                created += 1
        self.stdout.write(self.style.SUCCESS(f"حسابات مستخدمين: {created} (جديد)"))

    def _seed_qr(self, employees):
        from apps.employees.qr_service import issue_qr

        created = 0
        for emp in employees:
            if not hasattr(emp, "qr_record"):
                issue_qr(emp)
                created += 1
        self.stdout.write(self.style.SUCCESS(f"رموز QR: {created} (جديد)"))

    def _seed_balances(self):
        year = timezone.localdate().year
        count = 0
        for lt in LeaveType.objects.filter(is_active=True):
            for emp in Employee.objects.filter(is_active=True):
                if lt.applicable_to == "gender_female" and emp.gender != "F":
                    continue
                get_or_create_balance(emp, lt, year)
                count += 1
        self.stdout.write(self.style.SUCCESS(f"أرصدة الإجازات {year}: {count} (ممنوح = أيام السنة)"))

    # ------------------------------------------------------------------ الحضور
    def _seed_attendance(self, employees):
        rng = random.Random(42)
        today = timezone.localdate()
        holidays = set(
            h.date for h in PublicHoliday.objects.all()
            if h.date.year == today.year or h.is_recurring
        )
        workdays = []
        d = today - datetime.timedelta(days=1)
        while len(workdays) < 10:
            if d.weekday() not in WEEKEND_DAYS and d not in holidays:
                workdays.append(d)
            d -= datetime.timedelta(days=1)
        device = QrDevice.objects.filter(status=QrDevice.Status.ACTIVE).first()
        created = 0
        for emp in employees:
            if emp.hire_date and emp.hire_date > workdays[0]:
                continue
            shift = emp.shift
            if not shift:
                continue
            for wd in workdays:
                late = rng.choice([0, 0, 0, 5, 8, 15, 30])
                tz = timezone.get_current_timezone()
                check_in = timezone.make_aware(
                    datetime.datetime.combine(wd, shift.start_time) + datetime.timedelta(minutes=late), tz
                )
                end = timezone.make_aware(datetime.datetime.combine(wd, shift.end_time), tz)
                check_out = end + datetime.timedelta(minutes=rng.choice([0, 5, 10]))
                worked = max(0, int((check_out - check_in).total_seconds() // 60))
                day, c = AttendanceDay.objects.get_or_create(
                    employee=emp, work_date=wd,
                    defaults={
                        "shift": shift, "branch": emp.branch,
                        "state": AttendanceDay.State.PRESENT,
                        "check_in": check_in, "check_out": check_out,
                        "worked_minutes": worked, "late_minutes": late,
                    },
                )
                if c:
                    created += 1
                    if late > 0 and device:
                        AttendanceScan.objects.create(
                            employee=emp, attendanceday=day,
                            source=AttendanceScan.Source.FIXED_READER, device=device,
                            decision=AttendanceScan.Decision.CHECK_IN,
                        )
        self.stdout.write(self.style.SUCCESS(f"أيام الحضور: {created} (جديد)"))

    # ------------------------------------------------------------------ بيانات تشغيلية
    def _seed_operational(self, employees):
        leave_types = {lt.code: lt for lt in LeaveType.objects.filter(is_active=True)}
        annual = leave_types.get("annual")
        requests_created = 0
        # طلبان: أحدهما يُعتمد والآخر يبقى بانتظار
        for emp, from_d, to_d, approve in [
            (employees[1], "2026-08-17", "2026-08-20", True),
            (employees[4], "2026-09-01", "2026-09-03", False),
        ]:
            if emp is None or annual is None or emp.user_id is None:
                continue
            from_date = datetime.date.fromisoformat(from_d)
            to_date = datetime.date.fromisoformat(to_d)
            if LeaveRequest.objects.filter(
                employee=emp, leave_type=annual,
                from_date=from_date, to_date=to_date,
                status__in=(LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED),
            ).exists():
                continue
            try:
                req = submit_request(
                    emp, annual, from_date, to_date,
                    reason="بيانات تجريبية", requested_by=emp.user,
                )
                if approve:
                    approve_request(req, emp.user)
                requests_created += 1
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"تخطّي طلب إجازة {emp.employee_code}: {exc}"))
        self.stdout.write(self.style.SUCCESS(f"طلبات الإجازات: {requests_created} (جديد)"))

        exc_created = 0
        if employees and employees[0].user_id:
            day = AttendanceDay.objects.filter(employee=employees[0]).first()
            if day:
                _, c = AttendanceException.objects.get_or_create(
                    employee=employees[0], attendanceday=day, type=AttendanceException.Type.PERMISSION,
                    defaults={
                        "from_time": timezone.make_aware(
                            datetime.datetime.combine(day.work_date, datetime.time(8, 0)),
                            timezone.get_current_timezone(),
                        ),
                        "to_time": timezone.make_aware(
                            datetime.datetime.combine(day.work_date, datetime.time(10, 0)),
                            timezone.get_current_timezone(),
                        ),
                        "hours": 2, "reason": "إذن خروج للطوارئ",
                        "status": AttendanceException.Status.APPROVED,
                        "requested_by": employees[0].user, "approved_by": employees[0].user,
                    },
                )
                exc_created += int(c)
        self.stdout.write(self.style.SUCCESS(f"استثناءات الحضور: {exc_created} (جديد)"))

        if employees and employees[0].user_id and not Notification.objects.filter(user=employees[0].user).exists():
            Notification.objects.create(
                user=employees[0].user, type=Notification.Type.SYSTEM,
                title="بيانات تجريبية", body="مرحبًا بك في نظام إدارة الموارد البشرية.",
            )

    # ------------------------------------------------------------------ الرواتب
    def _seed_payrun(self):
        branch = Branch.objects.get(code="BR-HQ")
        admin = get_user_model().objects.filter(is_superuser=True).first()
        run = PayRun.objects.filter(period_code="2026-07", branch=branch).first()
        if not run:
            if not admin:
                self.stdout.write(self.style.WARNING("تخطّي دورة الرواتب: لا يوجد مشرف لإنشائها"))
                return
            run = generate_payrun("2026-07", branch, admin)
        if run.status in (PayRun.Status.APPROVED, PayRun.Status.FROZEN):
            self.stdout.write(self.style.SUCCESS(
                f"دورة الرواتب 2026-07 موجودة بالفعل ({run.get_status_display()})."
            ))
            return
        try:
            if run.status == PayRun.Status.DRAFT:
                run = review_payrun(run, admin)
            if run.status == PayRun.Status.REVIEWING:
                run = approve_payrun(run, admin)
            self.stdout.write(self.style.SUCCESS(
                f"دورة الرواتب 2026-07: {run.payslips.count()} قسيمة — {run.get_status_display()}."
            ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"لم تُعتمد دورة الرواتب: {exc}"))
