"""اختبارات الرواتب (T-027..T-031, v2).

يغطي: حساب عناصر الأجر، توليد الدورة بالحضور وخصم الغياب (BR-PAY-002)،
انتقالات الحالة والتجميد (BR-PAY-001)، تصدير البنك، نهاية الخدمة،
والصلاحيات عبر العروض.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.attendance.models import AttendanceDay
from apps.auth_app.models import Permission
from apps.employees.models import Contract, Employee
from apps.org.models import Branch, Shift
from apps.payroll.models import EndOfService, PayElement, PayRun, PayrollLine, Payslip
from apps.payroll.services import (
    PayrollError,
    approve_payrun,
    bank_rows,
    calculate_end_of_service,
    freeze_payrun,
    generate_payrun,
    official_workdays,
    review_payrun,
)

User = get_user_model()


def _branch():
    return Branch.objects.create(code="BR-P", name_ar="فرع رواتب")


def _shift():
    return Shift.objects.get_or_create(
        code="SH-P", defaults={"name_ar": "صباحي", "start_time": "08:00", "end_time": "16:00"})[0]


def _employee(code="P-001", branch=None, **kw):
    defaults = {
        "employee_code": code, "first_name_ar": "راتب", "last_name_ar": code,
        "branch": branch or _branch(), "shift": _shift(),
        "employment_status": Employee.EmploymentStatus.ACTIVE,
        "is_active": True, "hire_date": datetime.date(2023, 1, 1), "bank_account": "ACC-001",
    }
    defaults.update(kw)
    emp = Employee.objects.create(**defaults)
    if kw.get("skip_contract"):
        return emp
    Contract.objects.create(
        contract_number=f"CTR-{code}", employee=emp,
        start_date=emp.hire_date, end_date=None,
        base_salary=Decimal("60000"), gross_salary=Decimal("60000"), allowance=0,
    )
    return emp


def _element(code, kind="earning", calculation="fixed", amount=Decimal("5000"), percent=0):
    return PayElement.objects.create(
        code=code, name_ar=code, kind=kind, calculation=calculation,
        amount=amount, percent=percent, applies_to_all=True, is_active=True,
    )


class PayrollServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="pay_admin", password="pass")
        self.branch = _branch()
        self.emp = _employee(branch=self.branch)

    def test_official_workdays(self):
        # أغسطس 2026 يبدأ السبت — العمل = أيام الأحد..الخميس (أسبوع فرنسي 5 أيام: Mon-Fri)
        self.assertEqual(official_workdays("2026-08", self.branch), 21)

    def test_generate_payrun_with_attendance(self):
        basic = _element("BASIC", "earning", "fixed", Decimal("1000"))
        housing = _element("HOUSING", "earning", "percent_of_basic", percent=Decimal("20"))
        tax = _element("TAX", "deduction", "percent_of_basic", percent=Decimal("5"))
        attend = _element("TRANS", "earning", "attendance_based", amount=Decimal("200"))

        # أغسطس 2026: حاضر 20 يوم + غائب 1
        AttendanceDay.objects.create(employee=self.emp, work_date=datetime.date(2026, 8, 1),
                                     state=AttendanceDay.State.PRESENT)
        AttendanceDay.objects.create(employee=self.emp, work_date=datetime.date(2026, 8, 2),
                                     state=AttendanceDay.State.PRESENT)
        AttendanceDay.objects.create(employee=self.emp, work_date=datetime.date(2026, 8, 3),
                                     state=AttendanceDay.State.ABSENT)

        run = generate_payrun("2026-08", self.branch, self.user)
        self.assertEqual(run.status, PayRun.Status.DRAFT)
        self.assertEqual(run.payslips.count(), 1)

        slip = run.payslips.get(employee=self.emp)
        # أساسي 60000 + ثابت 1000 + نسبة 20% (12000) + حضور 200×2=400 − ضريبة 5% (3000)
        self.assertEqual(slip.total_earnings, Decimal("13400"))
        # خصم الغياب: (60000/21)×1 = 2857.14 + ضريبة 3000
        self.assertAlmostEqual(float(slip.total_deductions), 5857.142857, places=2)
        self.assertAlmostEqual(float(slip.net),
                               float(60000 + 13400 - (60000 / 21) - 3000), places=2)
        self.assertEqual(slip.attended_days, 2)
        self.assertEqual(slip.absent_days, 1)
        self.assertTrue(PayrollLine.objects.filter(pay_run=run, note__startswith="خصم غياب").exists())

    def test_duplicate_run_rejected(self):
        generate_payrun("2026-08", self.branch, self.user)
        with self.assertRaises(PayrollError):
            generate_payrun("2026-08", self.branch, self.user)

    def test_status_lifecycle_and_freeze(self):
        run = generate_payrun("2026-08", self.branch, self.user)
        with self.assertRaises(PayrollError):
            approve_payrun(run, self.user)  # لا اعتماد قبل المراجعة
        review_payrun(run, self.user)
        self.assertEqual(run.status, PayRun.Status.REVIEWING)
        approve_payrun(run, self.user)
        self.assertEqual(run.status, PayRun.Status.APPROVED)
        self.assertEqual(run.approved_by, self.user)
        freeze_payrun(run, self.user)
        self.assertEqual(run.status, PayRun.Status.FROZEN)
        with self.assertRaises(PayrollError):
            review_payrun(run, self.user)  # مجمد = نهائي (BR-PAY-001)

    def test_bank_rows_only_with_account(self):
        other = _employee("P-002", branch=self.branch, bank_account="")
        run = generate_payrun("2026-08", self.branch, self.user)
        rows = bank_rows(run)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bank_account"], "ACC-001")
        self.assertNotIn(other.pk, [r["employee_code"] for r in rows])

    def test_end_of_service_calculation(self):
        eos = calculate_end_of_service(self.emp, datetime.date(2026, 8, 9), self.user)
        years = (datetime.date(2026, 8, 9) - datetime.date(2023, 1, 1)).days / 365.25
        daily = 60000 / 30
        self.assertAlmostEqual(float(eos.total_years), years, places=2)
        self.assertAlmostEqual(float(eos.service_reward), years * daily * 0.5, places=2)
        self.assertEqual(eos.status, EndOfService.Status.DRAFT)
        self.assertGreater(float(eos.net), 0)

    def test_salary_base_days_override(self):
        from apps.payroll.models import PayrollSettings

        AttendanceDay.objects.create(employee=self.emp, work_date=datetime.date(2026, 8, 3),
                                     state=AttendanceDay.State.ABSENT)
        settings_row, _ = PayrollSettings.objects.get_or_create(
            pk=1, defaults={"salary_base_days": 26, "absence_grace_days": 0,
                            "absence_deduction_enabled": True, "auto_mark_absent": False,
                            "eos_reward_factor": "0.50"})
        settings_row.salary_base_days = 26
        settings_row.save(update_fields=["salary_base_days"])

        run = generate_payrun("2026-08", self.branch, self.user)
        slip = run.payslips.get(employee=self.emp)
        # خصم = (60000/26)×1 بدلاً من (60000/21)
        self.assertAlmostEqual(float(slip.total_deductions), 60000 / 26, places=2)

    def test_absence_grace_days_exempts_deduction(self):
        from apps.payroll.models import PayrollSettings

        AttendanceDay.objects.create(employee=self.emp, work_date=datetime.date(2026, 8, 3),
                                     state=AttendanceDay.State.ABSENT)
        settings_row, _ = PayrollSettings.objects.get_or_create(
            pk=1, defaults={"salary_base_days": 0, "absence_grace_days": 0,
                            "absence_deduction_enabled": True, "auto_mark_absent": False,
                            "eos_reward_factor": "0.50"})
        settings_row.absence_grace_days = 2  # سماح 2 أيام ← غياب واحد لا يُخصم
        settings_row.save(update_fields=["absence_grace_days"])

        run = generate_payrun("2026-08", self.branch, self.user)
        self.assertFalse(
            PayrollLine.objects.filter(pay_run=run, note__startswith="خصم غياب").exists())

    def test_auto_mark_absent_on_generate(self):
        from apps.payroll.models import PayrollSettings

        settings_row, _ = PayrollSettings.objects.get_or_create(
            pk=1, defaults={"salary_base_days": 0, "absence_grace_days": 0,
                            "absence_deduction_enabled": True, "auto_mark_absent": False,
                            "eos_reward_factor": "0.50"})
        settings_row.auto_mark_absent = True
        settings_row.save(update_fields=["auto_mark_absent"])

        run = generate_payrun("2026-08", self.branch, self.user)
        slip = run.payslips.get(employee=self.emp)
        # لا أيام حضور مُدخلة يدويًا → العلام التلقائي يعيّن أيام العمل كغياب
        self.assertGreater(slip.absent_days, 0)
        self.assertEqual(slip.attended_days, 0)
        self.assertTrue(PayrollLine.objects.filter(pay_run=run, note__startswith="خصم غياب").exists())


class PayrollViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for code in ("payroll.view", "payroll.run.generate", "payroll.run.review",
                     "payroll.run.approve", "payroll.payslip.view", "payroll.bank.export"):
            Permission.objects.create(code=code, module="payroll", name_ar=code)
        cls.branch = _branch()
        cls.emp = _employee(branch=cls.branch)
        cls.admin = User.objects.create_superuser(username="pv_admin", password="pass")
        cls.emp_user = User.objects.create_user(username="pv_emp", password="pass")
        cls.emp.user = cls.emp_user
        cls.emp.save()
        _element("BASIC", "earning", "fixed", Decimal("1000"))

    def setUp(self):
        self.client.force_login(self.admin)

    def test_list_requires_permission(self):
        self.client.force_login(self.emp_user)
        self.assertEqual(self.client.get(reverse("payroll:run_list")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("payroll:run_list")).status_code, 200)

    def test_generate_via_view(self):
        resp = self.client.post(reverse("payroll:run_generate"), {
            "period_code": "2026-08", "branch": self.branch.pk,
        })
        run = PayRun.objects.get(period_code="2026-08")
        self.assertRedirects(resp, reverse("payroll:run_detail", args=[run.pk]))
        self.assertEqual(run.payslips.count(), 1)

    def test_status_flow_via_views(self):
        run = generate_payrun("2026-08", self.branch, self.admin)
        for action in ("review", "approve", "freeze"):
            resp = self.client.post(reverse("payroll:run_status", args=[run.pk, action]))
            self.assertRedirects(resp, reverse("payroll:run_detail", args=[run.pk]))
        run.refresh_from_db()
        self.assertEqual(run.status, PayRun.Status.FROZEN)

    def test_payslip_pdf_requires_approved(self):
        run = generate_payrun("2026-08", self.branch, self.admin)
        slip = run.payslips.first()
        resp = self.client.get(reverse("payroll:payslip_pdf", args=[slip.pk]))
        self.assertEqual(resp.status_code, 400)
        review_payrun(run, self.admin)
        approve_payrun(run, self.admin)
        resp = self.client.get(reverse("payroll:payslip_pdf", args=[slip.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_bank_export_only_after_approval(self):
        run = generate_payrun("2026-08", self.branch, self.admin)
        resp = self.client.get(reverse("payroll:bank_export", args=[run.pk, "csv"]))
        self.assertEqual(resp.status_code, 400)
        review_payrun(run, self.admin)
        approve_payrun(run, self.admin)
        resp = self.client.get(reverse("payroll:bank_export", args=[run.pk, "csv"]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("ACC-001", content)
        self.assertIn("61000.00", content)
