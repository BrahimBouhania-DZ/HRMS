"""مولّد بيانات تدريب واقعية لنماذج التنبؤ (seed_ai_data).

يُنشئ عيّنة تاريخية من الموظفين — بعضهم مغادر (مثال إيجابي للتنبؤ بمخاطر
الاستقالة) — مع حضور/إجازات/تقييمات/عقود واقعية على مدى آخر سنتين.
كل خصائص التدريب تُحسب لاحقًا من قاعدة البيانات (apps/ai/features.py).

الاستخدام:
    python manage.py seed_ai_data                       # 60 موظفًا، 20٪ مغادرون
    python manage.py seed_ai_data --employees 80 --departed 0.25
    python manage.py seed_ai_data --dry-run             # لا يُنشئ بيانات

مبدأ التشغيل: متكرر (idempotent) — يتخطى الموظفين الموجودين برقمهم؛ ويضمن
الهيكل التنظيمي (branch/department/position/shift) عبر seed_demo إن غاب.
"""

import datetime
import random

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.attendance.models import AttendanceDay
from apps.employees.models import Contract, Employee
from apps.leave.models import LeaveRequest, LeaveType, PublicHoliday
from apps.leave.services import WEEKEND_DAYS
from apps.org.models import Branch, Position, Shift
from apps.perf.models import PerfCycle, PerfReview, PerfTemplate

FIRST_NAMES = [
    ("أحمد", "Ahmed"), ("محمد", "Mohamed"), ("يوسف", "Youcef"), ("عبد الرحمن", "Abderrahmane"),
    ("إسلام", "Islam"), ("رياض", "Riad"), ("مهدي", "Mehdi"), ("وليد", "Walid"),
    ("أنس", "Anis"), ("زياد", "Ziad"), ("هشام", "Hichem"), ("أيوب", "Ayoub"),
    ("سارة", "Sara"), ("أمينة", "Amina"), ("خديجة", "Khadija"), ("نور", "Nour"),
    ("مريم", "Meriem"), ("إيمان", "Imane"), ("رانية", "Rania"), ("يسرى", "Yousra"),
    ("دليلة", "Dalila"), ("هاجر", "Hadjar"), ("سلمى", "Salma"), ("لينة", "Lina"),
]

LAST_NAMES = [
    ("بن يوسف", "Ben Youcef"), ("مرابط", "Merabet"), ("بوعلام", "Boualem"), ("قاسمي", "Kacemi"),
    ("عثماني", "Othmani"), ("بلقاسم", "Belkacem"), ("سعدي", "Saadi"), ("شريف", "Cherif"),
    ("لونيسي", "Lounici"), ("طيب", "Tayeb"), ("بوراس", "Bouras"), ("حجاج", "Hadjadj"),
    ("زروقي", "Zerrouki"), ("بوقرة", "Bouguerra"), ("دحماني", "Dahmani"), ("حمادي", "Hammadi"),
    ("بوضياف", "Boudiaf"), ("رابحي", "Rabehi"), ("قندوز", "Gandouz"), ("سعيداني", "Saïdani"),
]


class Command(BaseCommand):
    help = "بيانات تدريب واقعية لنماذج التنبؤ (موظفون/حضور/إجازات/تقييمات/عقود)"

    def add_arguments(self, parser):
        parser.add_argument("--employees", type=int, default=60, help="عدد الموظفين الجدد")
        parser.add_argument("--departed", type=float, default=0.20, help="نسبة المغادرين (أمثلة إيجابية)")
        parser.add_argument("--dry-run", action="store_true", help="اعرض الخطة فقط دون إنشاء بيانات")

    def handle(self, *args, **options):
        n = options["employees"]
        departed_ratio = min(0.5, max(0.05, options["departed"]))
        self._ensure_org()

        holidays = self._holidays()
        cycles = self._ensure_perf_cycles()
        template = self._ensure_template()
        rng = random.Random(7)

        positions = list(Position.objects.all())
        shifts = list(Shift.objects.all())
        if not positions:
            self.stderr.write("لا توجد مناصب — شغّل seed_demo أولًا.")
            return
        if not shifts:
            self.stderr.write("لا توجد جداول دوام — شغّل seed_demo أولًا.")
            return

        planned = {"employees": 0, "departed": 0, "attendance": 0, "leaves": 0, "reviews": 0, "contracts": 0}
        for i in range(n):
            risk = rng.random()
            departed = risk > (1 - departed_ratio)
            code = f"EMP-{2001 + i}"
            if Employee.objects.filter(employee_code=code).exists():
                continue
            if options["dry_run"]:
                planned["employees"] += 1
                planned["departed"] += int(departed)
                continue
            self._create_employee(code, i, rng, risk, departed, positions, shifts, holidays, cycles, template, planned)

        self.stdout.write(self.style.SUCCESS(
            f"بيانات التدريب: {planned['employees']} موظفًا (مغادرون {planned['departed']}) | "
            f"حضور {planned['attendance']} | إجازات {planned['leaves']} | تقييمات {planned['reviews']} | "
            f"عقود {planned['contracts']}."
        ))
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("وضع التجربة (--dry-run): لم تُنشأ بيانات."))

    # ------------------------------------------------------------------ ضمانات
    def _ensure_org(self):
        if Branch.objects.exists() and Position.objects.exists():
            return
        self.stdout.write(self.style.WARNING("لا يوجد هيكل تنظيمي — أُنشئ عبر seed_demo أولًا..."))
        call_command("seed_demo", "--employees", "5", "--no-attendance")

    def _holidays(self):
        today = timezone.localdate()
        return set(
            h.date for h in PublicHoliday.objects.all()
            if h.date.year == today.year or h.is_recurring
        )

    def _ensure_perf_cycles(self):
        today = timezone.localdate()
        created, cycles = 0, []
        specs = [
            ("تقييم 2025-س2", "Évaluation 2025-S2", "2025 Review H2", datetime.date(today.year - 1, 7, 1), datetime.date(today.year - 1, 12, 31)),
            ("تقييم 2026-س1", "Évaluation 2026-S1", "2026 Review H1", datetime.date(today.year, 1, 1), datetime.date(today.year, 6, 30)),
        ]
        for ar, fr, en, start, end in specs:
            obj, c = PerfCycle.objects.get_or_create(
                name_ar=ar, period_start=start,
                defaults={"name_fr": fr, "name_en": en, "period_end": end, "status": PerfCycle.Status.CLOSED},
            )
            created += int(c)
            cycles.append(obj)
        if created:
            self.stdout.write(self.style.SUCCESS(f"دورات التقييم: {created} (جديد)"))
        return cycles

    def _ensure_template(self):
        obj, _ = PerfTemplate.objects.get_or_create(
            name_ar="قالب عام",
            defaults={
                "name_fr": "Modèle général", "name_en": "General template",
                "criteria_json": [{"title": "الإنتاجية", "weight": 60}, {"title": "المواظبة", "weight": 40}],
                "is_active": True,
            },
        )
        return obj

    # ------------------------------------------------------------------ الموظف
    def _create_employee(self, code, idx, rng, risk, departed, positions, shifts, holidays, cycles, template, planned):
        today = timezone.localdate()
        first_ar, first_fr = FIRST_NAMES[rng.randrange(len(FIRST_NAMES))]
        last_ar, last_fr = LAST_NAMES[rng.randrange(len(LAST_NAMES))]
        gender = "F" if first_ar in {
            "سارة", "أمينة", "خديجة", "نور", "مريم", "إيمان", "رانية", "يسرى", "دليلة", "هاجر", "سلمى", "لينة",
        } else "M"

        if departed:
            end_date = today - datetime.timedelta(days=rng.randint(30, 540))
            tenure = datetime.timedelta(days=rng.randint(365, 6 * 365))
            hire_date = end_date - tenure
            status = rng.choice([Employee.EmploymentStatus.RESIGNED, Employee.EmploymentStatus.TERMINATED])
            is_active = False
        else:
            hire_date = today - datetime.timedelta(days=rng.randint(365, 10 * 365))
            end_date = None
            status = Employee.EmploymentStatus.ACTIVE
            is_active = True

        position = rng.choice(positions)
        department = position.department
        branch = department.branch
        shift = rng.choice(shifts)

        emp = Employee.objects.create(
            employee_code=code,
            first_name_ar=first_ar, last_name_ar=last_ar,
            first_name_fr=first_fr, last_name_fr=last_fr,
            first_name_en=first_fr, last_name_en=last_fr,
            gender=gender,
            birth_date=hire_date - datetime.timedelta(days=rng.randint(10000, 15000)),
            hire_date=hire_date, is_active=is_active,
            employment_status=status,
            branch=branch, department=department, position=position, shift=shift,
            phone=f"+213 5{rng.randint(10000000, 99999999)}",
            email=f"{code.lower()}@hrms.local",
        )
        planned["employees"] += 1
        if departed:
            planned["departed"] += 1

        self._create_contract(emp, hire_date, end_date, rng)
        planned["contracts"] += 1

        self._create_attendance(emp, hire_date, end_date or today, risk, departed, end_date, shift, holidays, rng, planned)
        self._create_leaves(emp, hire_date, end_date or today, risk, rng, planned)
        self._create_reviews(emp, hire_date, risk, cycles, template, rng, planned)

    # ------------------------------------------------------------------ العقود
    def _create_contract(self, emp, hire_date, end_date, rng):
        base = round(rng.uniform(30000, 90000), 2)
        allowance = round(rng.uniform(3000, 9000), 2)
        c = Contract.objects.create(
            contract_number=f"AI-{emp.employee_code}",
            employee=emp,
            contract_type=Contract.ContractType.CDI,
            start_date=hire_date,
            end_date=end_date,
            gross_salary=base + allowance, base_salary=base, allowance=allowance,
        )
        return c

    # ------------------------------------------------------------------ الحضور
    def _create_attendance(self, emp, start, stop, risk, departed, end_date, shift, holidays, rng, planned):
        start = max(start, stop - datetime.timedelta(days=730))
        if not shift:
            return
        rows = []
        d = start
        while d <= stop:
            if d.weekday() in WEEKEND_DAYS or d in holidays:
                d += datetime.timedelta(days=1)
                continue
            degradation = 0.0
            if departed and end_date and (end_date - d).days <= 90:
                degradation = 0.15
            present_prob = 0.97 - 0.22 * risk - degradation
            roll = rng.random()
            state = AttendanceDay.State.PRESENT if roll < present_prob else AttendanceDay.State.ABSENT
            late = 0
            overtime = 0
            worked = 480
            if state == AttendanceDay.State.PRESENT:
                if rng.random() < 0.06 + 0.40 * risk:
                    late = rng.choice([5, 8, 15, 30, 45])
                    worked = max(0, 480 - late)
                if rng.random() < 0.15:
                    overtime = rng.choice([30, 60, 90, 120])
            rows.append(AttendanceDay(
                employee=emp, work_date=d,
                shift=shift, branch=emp.branch,
                state=state,
                check_in=None, check_out=None,
                worked_minutes=worked if state == AttendanceDay.State.PRESENT else 0,
                late_minutes=late, overtime_minutes=overtime,
            ))
            d += datetime.timedelta(days=1)
        AttendanceDay.objects.bulk_create(rows, batch_size=2000, ignore_conflicts=True)
        planned["attendance"] += len(rows)

    # ------------------------------------------------------------------ الإجازات
    def _create_leaves(self, emp, start, stop, risk, rng, planned):
        start = max(start, stop - datetime.timedelta(days=730))
        annual = LeaveType.objects.filter(code="annual").first()
        sick = LeaveType.objects.filter(code="sick").first()
        rows = []
        for leave_type, count in [
            (annual, rng.randint(1, 3)),
            (sick, rng.randint(0, int(2 + 3 * risk))),
        ]:
            if leave_type is None:
                continue
            for _ in range(count):
                anchor = rng.randint(0, max(0, (stop - start).days - 7))
                from_date = start + datetime.timedelta(days=anchor)
                days = rng.randint(1, 5) if leave_type.code == "annual" else rng.randint(1, 3)
                to_date = min(stop, from_date + datetime.timedelta(days=days - 1))
                rows.append(LeaveRequest(
                    employee=emp, leave_type=leave_type,
                    from_date=from_date, to_date=to_date, days=days,
                    reason="بيانات تدريب (seed_ai_data)",
                    status=LeaveRequest.Status.APPROVED,
                ))
        LeaveRequest.objects.bulk_create(rows, batch_size=200, ignore_conflicts=True)
        planned["leaves"] += len(rows)

    # ------------------------------------------------------------------ التقييمات
    def _create_reviews(self, emp, hire_date, risk, cycles, template, rng, planned):
        for cycle in cycles:
            if hire_date > cycle.period_end:
                continue
            score = round(max(45.0, min(98.0, 95.0 - 32.0 * risk + rng.uniform(-5, 5))), 2)
            review, c = PerfReview.objects.get_or_create(
                employee=emp, cycle=cycle,
                defaults={
                    "template": template,
                    "final_score": score, "manager_score": score,
                    "status": PerfReview.Status.DONE,
                },
            )
            if c:
                planned["reviews"] += 1
