"""أمر بيانات التدريب (Demo) — دورات + جلسات + تسجيلات + شهادات واقعية.

الاستخدام:
    python manage.py seed_training                   # كل الدورات/الجلسات/التسجيلات
    python manage.py seed_training --employees 20    # حدّ أقصى للموظفين المشاركين
    python manage.py seed_training --no-certificates # دون إصدار شهادات

مبدأ التشغيل: الأمر متكرر (idempotent) — لا يحذف أي بيانات؛ يتخطى السجلات الموجودة
بحسب المفاتيح الفريدة (رمز الدورة، وقيود التسجيل الفريدة). يتطلب بيانات ديمو موظفين
(seed_demo) كي تُنشأ التسجيلات؛ إن لم يوجد موظفون يُنشئ الدورات والجلسات فقط.
"""

import datetime
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.employees.models import Employee
from apps.training.models import TrainingCertificate, TrainingCourse, TrainingEnrollment, TrainingSession

COURSES = [
    {
        "code": "TR-001", "category": "إدارة", "provider": "FormPro DZ", "cost": 45000,
        "title_ar": "إدارة الموارد البشرية الحديثة",
        "title_fr": "Gestion moderne des ressources humaines",
        "title_en": "Modern Human Resource Management",
        "description": "ممارسات الموارد البشرية المعاصرة: التوظيف، التقييم، التطوير.",
    },
    {
        "code": "TR-002", "category": "معلومية", "provider": "MicroSkills", "cost": 30000,
        "title_ar": "Excel المتقدم وتحليل البيانات",
        "title_fr": "Excel avancé et analyse de données",
        "title_en": "Advanced Excel and Data Analysis",
        "description": "الجداول المحورية، الدوال المتقدمة، ومقاييس التحليل العملي.",
    },
    {
        "code": "TR-003", "category": "أمن", "provider": "SecuTech", "cost": 38000,
        "title_ar": "الأمن السيبراني الأساسي",
        "title_fr": "Cybersécurité de base",
        "title_en": "Fundamentals of Cybersecurity",
        "description": "أمن المعلومات للمستخدم النهائي: كلمات المرور، التصيد، والتوعية.",
    },
    {
        "code": "TR-004", "category": "قيادة", "provider": "Leadership Academy", "cost": 55000,
        "title_ar": "قيادة الفرق وإدارة الاجتماعات",
        "title_fr": "Leadership et conduite de réunions",
        "title_en": "Team Leadership and Meeting Management",
        "description": "مهارات القيادة الميدانية، التواصل، وقيادة الاجتماعات الفعّالة.",
    },
    {
        "code": "TR-005", "category": "سلامة", "provider": "Preventa", "cost": 27000,
        "title_ar": "السلامة المهنية ISO 45001",
        "title_fr": "Sécurité au travail ISO 45001",
        "title_en": "Occupational Safety ISO 45001",
        "description": "مبادئ الصحة والسلامة المهنية وفق المعيار الدولي ISO 45001.",
    },
    {
        "code": "TR-006", "category": "لغات", "provider": "LanguePro", "cost": 25000,
        "title_ar": "لغة الأعمال الفرنسية",
        "title_fr": "Français des affaires",
        "title_en": "Business French",
        "description": "المصطلحات الإدارية والتجارية لبيئة عمل متعددة اللغات.",
    },
    {
        "code": "TR-007", "category": "مالية", "provider": "Compta+", "cost": 42000,
        "title_ar": "المحاسبة التحليلية وإعداد التقارير",
        "title_fr": "Comptabilité analytique et reporting",
        "title_en": "Management Accounting and Reporting",
        "description": "تحليل التكاليف، الموازنات، وإعداد تقارير مالية إدارية.",
    },
    {
        "code": "TR-008", "category": "خدمة", "provider": "QualiServe", "cost": 22000,
        "title_ar": "خدمة الزبائن المتميزة",
        "title_fr": "Service client d'excellence",
        "title_en": "Customer Service Excellence",
        "description": "التعامل مع الزبائن، إدارة الشكاوى، وبناء تجربة إيجابية.",
    },
]

# (code, الفئة المناسبة، التاريخ، الحالة) لكل جلسة
SESSIONS = [
    ("TR-002", "2026-03-02", "2026-03-05", TrainingSession.Status.COMPLETED),
    ("TR-003", "2026-04-13", "2026-04-16", TrainingSession.Status.COMPLETED),
    ("TR-006", "2026-05-04", "2026-05-07", TrainingSession.Status.COMPLETED),
    ("TR-008", "2026-06-08", "2026-06-10", TrainingSession.Status.COMPLETED),
    ("TR-001", "2026-07-20", "2026-07-23", TrainingSession.Status.RUNNING),
    ("TR-005", "2026-09-14", "2026-09-17", TrainingSession.Status.PLANNED),
    ("TR-004", "2026-10-05", "2026-10-08", TrainingSession.Status.PLANNED),
    ("TR-007", "2026-11-02", "2026-11-05", TrainingSession.Status.PLANNED),
]

TRAINERS = [
    "كريمة بلحاج", "سمير عياش", "ليلى بودربالة", "ناصر حمداني",
    "Karima Belhadj", "Samir Ayache", "Lila Bouderbala", "Nacer Hamdani",
]

LOCATIONS = ["قاعة التدريب — المقر الرئيسي", "قاعة الاجتماعات B — المقر الرئيسي", "مركز التدريب — فرع وهران"]


class Command(BaseCommand):
    help = "بيانات التدريب التجريبية: دورات + جلسات + تسجيلات + شهادات"

    def add_arguments(self, parser):
        parser.add_argument("--employees", type=int, default=0, help="حدّ أقصى للموظفين المشاركين (0 = الكل)")
        parser.add_argument("--no-certificates", action="store_true", help="لا تُصدر شهادات إتمام")

    def handle(self, *args, **options):
        rng = random.Random(2026)
        courses = self._seed_courses()
        sessions = self._seed_sessions(courses, rng)
        employees = list(Employee.objects.filter(is_active=True).order_by("employee_code"))
        if options["employees"]:
            employees = employees[: options["employees"]]
        if employees:
            self._seed_enrollments(sessions, employees, options["no_certificates"])
        else:
            self.stdout.write(self.style.WARNING(
                "لا يوجد موظفون نشطون — أُنشئت الدورات والجلسات فقط (شغّل seed_demo أولًا)."
            ))
        self.stdout.write(self.style.SUCCESS("اكتملت بيانات التدريب (seed_training)."))

    # ------------------------------------------------------------------ الدورات
    def _seed_courses(self):
        created = 0
        courses = []
        for c in COURSES:
            defaults = {k: v for k, v in c.items() if k != "code"}
            obj, c_created = TrainingCourse.objects.get_or_create(code=c["code"], defaults=defaults)
            courses.append(obj)
            created += int(c_created)
        self.stdout.write(self.style.SUCCESS(
            f"الدورات: {len(courses)} (جديد: {created})"
        ))
        return courses

    # ------------------------------------------------------------------ الجلسات
    def _seed_sessions(self, courses, rng):
        by_code = {c.code: c for c in courses}
        created = 0
        sessions = []
        for code, start_s, end_s, status in SESSIONS:
            course = by_code[code]
            start = datetime.date.fromisoformat(start_s)
            end = datetime.date.fromisoformat(end_s)
            if TrainingSession.objects.filter(course=course, start_date=start).exists():
                sessions.append(TrainingSession.objects.get(course=course, start_date=start))
                continue
            obj = TrainingSession.objects.create(
                course=course, start_date=start, end_date=end,
                trainer=rng.choice(TRAINERS), location=rng.choice(LOCATIONS),
                capacity=rng.randint(15, 25), status=status,
            )
            sessions.append(obj)
            created += 1
        self.stdout.write(self.style.SUCCESS(f"الجلسات: {len(sessions)} (جديد: {created})"))
        return sessions

    # ------------------------------------------------------------------ التسجيلات والشهادات
    def _seed_enrollments(self, sessions, employees, skip_certificates):
        completed, approved, pending = [], [], []
        for s in sessions:
            if s.status == TrainingSession.Status.COMPLETED:
                completed.append(s)
            elif s.status == TrainingSession.Status.RUNNING:
                approved.append(s)
            else:
                pending.append(s)

        created = {"enrollments": 0, "certificates": 0}
        approver = self._approver()

        def pick(session, n):
            """اختيار حتمي (مستقر بين التشغيلات) — من موضع يبدأ من معرف الجلسة."""
            offset = (session.id * 7) % len(employees)
            step = max(1, len(employees) // n) if n else 1
            return [employees[(offset + k * step) % len(employees)] for k in range(n)]

        for session, n, status in [
            (s, min(len(employees), max(8, s.capacity // 2)), TrainingEnrollment.Status.COMPLETED) for s in completed
        ] + [
            (s, min(len(employees), max(6, s.capacity // 2)), TrainingEnrollment.Status.APPROVED) for s in approved
        ] + [
            (s, min(len(employees), max(4, s.capacity // 3)), TrainingEnrollment.Status.PENDING) for s in pending
        ]:
            for emp in pick(session, n):
                obj, c = TrainingEnrollment.objects.get_or_create(
                    session=session, employee=emp,
                    defaults={
                        "status": status,
                        "approved_by": approver,
                        "approved_at": (
                            timezone.make_aware(datetime.datetime.combine(session.end_date or session.start_date, datetime.time(12, 0)))
                            if status != TrainingEnrollment.Status.PENDING else None
                        ),
                    },
                )
                if c:
                    created["enrollments"] += 1
                if status == TrainingEnrollment.Status.COMPLETED and not skip_certificates:
                    issued = session.end_date or session.start_date
                    _, cert_created = TrainingCertificate.objects.get_or_create(
                        enrollment=obj,
                        defaults={
                            "title": f"{session.course.title_ar} — شهادة إتمام",
                            "issued_date": issued,
                        },
                    )
                    created["certificates"] += int(cert_created)

        self.stdout.write(self.style.SUCCESS(
            f"التسجيلات: {created['enrollments']} (جديد) | الشهادات: {created['certificates']} (جديد)"
        ))

    def _approver(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first()
        return user or User.objects.filter(is_staff=True).first()
