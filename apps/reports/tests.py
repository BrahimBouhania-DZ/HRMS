"""اختبارات التقارير الأساسية + التصدير (S5)."""

import csv
import datetime
import io
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.auth_app.models import Permission
from apps.attendance.models import AttendanceDay
from apps.employees.models import Employee
from apps.leave.models import LeaveBalance, LeaveRequest, LeaveType
from apps.org.models import Branch, Department
from apps.reports.scheduling import run_scheduled_reports

User = get_user_model()


class ReportTests(TestCase):
    """تغطية REP-01,10,12,13,20,21 + CSV/XLSX + النطاقات."""

    @classmethod
    def setUpTestData(cls):
        Permission.objects.create(code="reports.view", module="core", name_ar="التقارير")
        Permission.objects.create(code="reports.export", module="core", name_ar="تصدير")
        cls.admin = User.objects.create_superuser(username="rep_admin", password="pass")
        cls.emp_user = User.objects.create_user(username="rep_emp", password="pass")
        cls.branch = Branch.objects.create(code="BR-R", name_ar="فرع R")
        cls.dept = Department.objects.create(code="DEP-R", name_ar="قسم R", branch=cls.branch)
        cls.emp = Employee.objects.create(
            employee_code="R-001", first_name_ar="رأفت", last_name_ar="ر",
            branch=cls.branch, department=cls.dept, user=cls.emp_user,
            employment_status=Employee.EmploymentStatus.ACTIVE, phone="0550",
        )
        cls.emp2 = Employee.objects.create(
            employee_code="R-002", first_name_ar="رانية", last_name_ar="ر",
            branch=cls.branch, department=cls.dept,
            employment_status=Employee.EmploymentStatus.ACTIVE,
        )
        cls.today = datetime.date(2026, 8, 9)
        AttendanceDay.objects.create(employee=cls.emp, work_date=cls.today,
                                     state=AttendanceDay.State.PRESENT, late_minutes=15,
                                     worked_minutes=480)
        AttendanceDay.objects.create(employee=cls.emp2, work_date=cls.today,
                                     state=AttendanceDay.State.ABSENT)
        cls.lt = LeaveType.objects.create(code="rep-lt", name_ar="سنوية", days_per_year=30)
        LeaveBalance.objects.create(employee=cls.emp, leave_type=cls.lt, year=2026,
                                    granted=30, used=4)
        LeaveRequest.objects.create(employee=cls.emp, leave_type=cls.lt,
                                    from_date=datetime.date(2026, 9, 1),
                                    to_date=datetime.date(2026, 9, 3), days=3,
                                    status=LeaveRequest.Status.PENDING)

    def setUp(self):
        self.client.force_login(self.admin)

    def _get(self, name, params=None):
        return self.client.get(reverse(name), params or {})

    def test_index_and_all_reports_200(self):
        for name in ["reports:index", "reports:rep01", "reports:rep10",
                     "reports:rep12", "reports:rep13", "reports:rep20", "reports:rep21"]:
            self.assertEqual(self._get(name).status_code, 200, name)

    def test_employee_without_perm_forbidden(self):
        self.client.force_login(self.emp_user)
        self.assertEqual(self.client.get(reverse("reports:index")).status_code, 403)

    def test_rep01_lists_employees(self):
        resp = self._get("reports:rep01")
        self.assertContains(resp, "R-001")
        self.assertContains(resp, "رأفت")

    def test_rep10_filters_today(self):
        resp = self._get("reports:rep10", {"work_date": "2026-08-09"})
        self.assertContains(resp, "15")
        self.assertContains(resp, "480")

    def test_rep12_absence_counts(self):
        resp = self._get("reports:rep12", {"from_date": "2026-08-01", "to_date": "2026-08-31"})
        self.assertContains(resp, "R-002")

    def test_rep13_lateness_sums(self):
        resp = self._get("reports:rep13", {"from_date": "2026-08-01", "to_date": "2026-08-31"})
        self.assertContains(resp, "15")

    def test_rep20_balances(self):
        resp = self._get("reports:rep20", {"year": "2026"})
        self.assertContains(resp, "30")

    def test_rep21_requests(self):
        resp = self._get("reports:rep21")
        self.assertContains(resp, "قيد الانتظار")

    def test_export_csv(self):
        resp = self.client.get(reverse("reports:export", args=["rep01", "csv"]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8"))))
        self.assertEqual(rows[0], ["الرمز", "الاسم", "القسم", "المنصب", "الفرع", "الحالة", "الهاتف"])
        self.assertEqual(rows[1][0], "R-001")

    def test_export_xlsx(self):
        resp = self.client.get(reverse("reports:export", args=["rep01", "xlsx"]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertGreater(len(resp.content), 100)

    def test_export_pdf(self):
        resp = self.client.get(reverse("reports:export", args=["rep01", "pdf"]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_export_requires_perm(self):
        self.client.force_login(self.emp_user)
        resp = self.client.get(reverse("reports:export", args=["rep01", "csv"]))
        self.assertEqual(resp.status_code, 403)


class ScanReportTests(TestCase):
    """REP-16/17 — سجل المسحات والمرفوضات."""

    @classmethod
    def setUpTestData(cls):
        from apps.attendance.models import AttendanceDay, AttendanceScan
        from apps.devices.models import QrDevice

        Permission.objects.create(code="reports.view", module="core", name_ar="التقارير")
        Permission.objects.create(code="reports.export", module="core", name_ar="تصدير")
        cls.admin = User.objects.create_superuser(username="scan_admin", password="pass")
        cls.branch = Branch.objects.create(code="BR-S", name_ar="فرع S")
        cls.device = QrDevice.objects.create(
            device_code="DEV-R1", branch=cls.branch, api_key_hash="hash", status="active",
        )
        cls.emp = Employee.objects.create(
            employee_code="S-001", first_name_ar="سعد", last_name_ar="س",
            branch=cls.branch, employment_status=Employee.EmploymentStatus.ACTIVE,
        )
        cls.day = AttendanceDay.objects.create(
            employee=cls.emp, work_date=datetime.date(2026, 8, 9),
            state=AttendanceDay.State.PRESENT,
        )
        AttendanceScan.objects.create(
            attendanceday=cls.day, employee=cls.emp, device=cls.device,
            source=AttendanceScan.Source.FIXED_READER,
            decision=AttendanceScan.Decision.CHECK_IN,
        )
        AttendanceScan.objects.create(
            employee=cls.emp, device=cls.device,
            source=AttendanceScan.Source.FIXED_READER,
            decision=AttendanceScan.Decision.REJECTED, result_detail="مفتاح غير صالح",
        )
        AttendanceScan.objects.create(
            employee=cls.emp, device=cls.device,
            source=AttendanceScan.Source.FIXED_READER,
            decision=AttendanceScan.Decision.REJECTED, result_detail="QR منتهي",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_rep16_lists_scans(self):
        resp = self.client.get(reverse("reports:rep16"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "دخول")
        self.assertContains(resp, "مرفوض")

    def test_rep16_filters_by_decision(self):
        resp = self.client.get(reverse("reports:rep16"), {"decision": "rejected"})
        self.assertContains(resp, "QR منتهي")
        self.assertContains(resp, "مفتاح غير صالح")
        self.assertNotContains(resp, "<td>دخول</td>")

    def test_rep17_groups_rejected(self):
        resp = self.client.get(reverse("reports:rep17"))
        self.assertEqual(resp.status_code, 200)
        # صفّان: واحد لكل (موظف/جهاز/سبب) بتكرار 1
        self.assertEqual(resp.content.count(b"<tr><td>S-001"), 2)
        self.assertContains(resp, "QR منتهي")
        self.assertContains(resp, "مفتاح غير صالح")

    def test_rep17_export_csv(self):
        resp = self.client.get(reverse("reports:export", args=["rep17", "csv"]))
        self.assertEqual(resp.status_code, 200)
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8"))))
        self.assertEqual(rows[0], ["الرمز", "الاسم", "الجهاز", "السبب", "عدد المرات"])
        self.assertEqual(rows[1][0], "S-001")


class PayrollReportTests(TestCase):
    """REP-30 — كشف الرواتب (ملخص) + صلاحيات التصدير المالي."""

    @classmethod
    def setUpTestData(cls):
        from apps.employees.models import Contract
        from apps.payroll.models import PayElement
        from apps.payroll.services import generate_payrun

        Permission.objects.create(code="reports.view", module="core", name_ar="التقارير")
        Permission.objects.create(code="reports.export", module="core", name_ar="تصدير")
        Permission.objects.create(code="payroll.payslip.view", module="payroll",
                                  name_ar="كشف الرواتب")
        cls.admin = User.objects.create_superuser(username="pr_admin", password="pass")
        cls.finance = User.objects.create_user(username="pr_fin", password="pass")
        cls.peon = User.objects.create_user(username="pr_peon", password="pass")
        cls.branch = Branch.objects.create(code="BR-PR", name_ar="فرع PR")
        cls.emp = Employee.objects.create(
            employee_code="PR-001", first_name_ar="مالي", last_name_ar="1",
            branch=cls.branch, employment_status=Employee.EmploymentStatus.ACTIVE,
            hire_date=datetime.date(2023, 1, 1), bank_account="ACC-PR",
        )
        Contract.objects.create(
            contract_number="CTR-PR", employee=cls.emp,
            start_date=datetime.date(2023, 1, 1), end_date=None,
            base_salary=Decimal("50000"), gross_salary=Decimal("50000"), allowance=0,
        )
        PayElement.objects.create(code="BASIC-PR", name_ar="أساسي", kind="earning",
                                  calculation="fixed", amount=Decimal("0"),
                                  applies_to_all=True, is_active=True)
        cls.payrun = generate_payrun("2026-08", cls.branch, cls.admin)

    def setUp(self):
        self.client.force_login(self.admin)

    def test_rep30_shows_summary(self):
        resp = self.client.get(reverse("reports:rep30"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2026-08")
        self.assertContains(resp, "50000.00")

    def test_rep30_requires_payroll_perm(self):
        self.client.force_login(self.peon)
        self.assertEqual(self.client.get(reverse("reports:rep30")).status_code, 403)

    def test_rep30_export_financial_guard(self):
        self.client.force_login(self.peon)
        resp = self.client.get(reverse("reports:export", args=["rep30", "csv"]))
        self.assertEqual(resp.status_code, 403)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("reports:export", args=["rep30", "csv"]))
        self.assertEqual(resp.status_code, 200)
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8"))))
        self.assertEqual(rows[0][0], "الفترة")
        self.assertEqual(rows[1][0], "2026-08")

    def test_rep30_filter_by_period(self):
        resp = self.client.get(reverse("reports:rep30"), {"period_code": "2026-08"})
        self.assertContains(resp, "2026-08")
        resp = self.client.get(reverse("reports:rep30"), {"period_code": "1999-01"})
        self.assertContains(resp, "لا بيانات مطابقة")
        self.assertNotContains(resp, "<td>2026-08</td>")


class ReportV2Tests(TestCase):
    """REP-04/31/33/42/43/50/51/53 + حماية التقارير الحساسة."""

    @classmethod
    def setUpTestData(cls):
        Permission.objects.get_or_create(code="reports.view", defaults={"module": "core", "name_ar": "التقارير"})
        Permission.objects.get_or_create(code="payroll.payslip.view", defaults={"module": "payroll", "name_ar": "قسائم"})
        Permission.objects.get_or_create(code="system.audit.view", defaults={"module": "core", "name_ar": "تدقيق"})
        Permission.objects.get_or_create(code="system.backup.manage", defaults={"module": "core", "name_ar": "نسخ"})
        Permission.objects.get_or_create(code="device.manage", defaults={"module": "devices", "name_ar": "أجهزة"})
        cls.admin = User.objects.create_superuser(username="repv2_admin", password="pass")
        cls.peon = User.objects.create_user(username="repv2_peon", password="pass")
        cls.branch = Branch.objects.create(code="BR-V2", name_ar="فرع V2")
        cls.dept = Department.objects.create(code="DEP-V2", name_ar="قسم V2", branch=cls.branch)
        cls.emp = Employee.objects.create(
            employee_code="V2-001", first_name_ar="فائز", last_name_ar="V",
            branch=cls.branch, department=cls.dept, hire_date=datetime.date(2023, 1, 1),
        )
        from apps.employees.models import Contract

        cls.contract = Contract.objects.create(
            contract_number="CTR-V2", employee=cls.emp,
            contract_type=Contract.ContractType.CDD,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date.today() + datetime.timedelta(days=10),
            gross_salary=Decimal("50000"), base_salary=Decimal("45000"),
        )
        from apps.payroll.models import PayRun, Payslip, PayElement, PayrollLine, EndOfService

        cls.payrun = PayRun.objects.create(period_code="2026-08", branch=cls.branch,
                                           status=PayRun.Status.FROZEN)
        Payslip.objects.create(pay_run=cls.payrun, employee=cls.emp,
                               basic_salary=Decimal("45000"),
                               total_earnings=Decimal("50000"),
                               total_deductions=Decimal("5000"),
                               net=Decimal("45000"))
        cls.bonus = PayElement.objects.create(
            code="V2-BONUS", name_ar="مكافأة", kind=PayElement.Kind.EARNING,
            calculation=PayElement.Calculation.FIXED, amount=Decimal("5000"),
        )
        cls.deduct = PayElement.objects.create(
            code="V2-DED", name_ar="خصم غياب", kind=PayElement.Kind.DEDUCTION,
            calculation=PayElement.Calculation.FIXED, amount=Decimal("1000"),
        )
        PayrollLine.objects.create(pay_run=cls.payrun, employee=cls.emp,
                                   element=cls.bonus, amount=Decimal("5000"))
        PayrollLine.objects.create(pay_run=cls.payrun, employee=cls.emp,
                                   element=cls.deduct, amount=Decimal("1000"))
        EndOfService.objects.create(
            employee=cls.emp, termination_date=datetime.date(2026, 7, 31),
            total_years=Decimal("3.5"), service_reward=Decimal("40000"),
            unused_leave_comp=Decimal("5000"), notice_period=Decimal("0"),
            deductions=Decimal("2000"), net=Decimal("43000"),
            status=EndOfService.Status.APPROVED,
        )
        from apps.perf.models import PerfCycle, PerfReview, PipPlan

        cls.cycle = PerfCycle.objects.create(
            name_ar="دورة V2", period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 6, 30),
        )
        cls.review = PerfReview.objects.create(
            employee=cls.emp, cycle=cls.cycle,
            self_score=Decimal("80"), manager_score=Decimal("90"),
            final_score=Decimal("85"), status=PerfReview.Status.DONE,
        )
        PipPlan.objects.create(
            review=cls.review, start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 8, 1), action_items="تدريب",
        )
        from apps.backup.models import BackupJob

        BackupJob.objects.create(kind=BackupJob.Kind.DAILY, status=BackupJob.Status.SUCCESS)
        from apps.core.models import AuditLog

        AuditLog.objects.create(action=AuditLog.Action.CREATE, model_name="employee",
                                object_repr="V2-001", detail="اختبار")
        AuditLog.objects.create(action=AuditLog.Action.LOGIN, model_name="auth",
                                object_repr="repv2_admin", ip="10.0.0.1")
        from apps.devices.models import QrDevice
        from apps.attendance.models import AttendanceScan

        cls.device = QrDevice.objects.create(
            device_code="QR-V2", branch=cls.branch, api_key_hash="h", status=QrDevice.Status.ACTIVE,
        )
        AttendanceScan.objects.create(
            employee=cls.emp, device=cls.device, decision=AttendanceScan.Decision.CHECK_IN,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_rep04_lists_expiring_contracts(self):
        resp = self.client.get(reverse("reports:rep04"))
        self.assertContains(resp, "V2-001")

    def test_rep31_detail(self):
        resp = self.client.get(reverse("reports:rep31"))
        self.assertContains(resp, "V2-001")
        self.assertContains(resp, "45000")

    def test_rep33_cost(self):
        resp = self.client.get(reverse("reports:rep33"))
        self.assertContains(resp, "فرع V2")
        self.assertContains(resp, "45000")

    def test_rep34_bonuses_deductions(self):
        resp = self.client.get(reverse("reports:rep34"))
        self.assertContains(resp, "مكافأة")
        self.assertContains(resp, "خصم غياب")
        resp = self.client.get(reverse("reports:rep34"), {"kind": "earning"})
        self.assertContains(resp, "مكافأة")
        self.assertNotContains(resp, "خصم غياب")

    def test_rep35_end_of_service(self):
        resp = self.client.get(reverse("reports:rep35"))
        self.assertContains(resp, "V2-001")
        self.assertContains(resp, "43000")
        resp = self.client.get(reverse("reports:rep35"), {"status": "approved"})
        self.assertContains(resp, "V2-001")

    def test_rep52_daily_activity(self):
        resp = self.client.get(reverse("reports:rep52"))
        self.assertContains(resp, "repv2_admin")
        self.assertContains(resp, "10.0.0.1")

    def test_rep54_device_status(self):
        resp = self.client.get(reverse("reports:rep54"))
        self.assertContains(resp, "QR-V2")
        self.assertContains(resp, "فرع V2")

    def test_rep42_perf_results(self):
        resp = self.client.get(reverse("reports:rep42"))
        self.assertContains(resp, "85")

    def test_rep43_pip(self):
        resp = self.client.get(reverse("reports:rep43"))
        self.assertContains(resp, "V2-001")

    def test_rep50_audit(self):
        resp = self.client.get(reverse("reports:rep50"))
        self.assertContains(resp, "اختبار")

    def test_rep51_users(self):
        resp = self.client.get(reverse("reports:rep51"))
        self.assertContains(resp, "repv2_admin")

    def test_rep53_backup(self):
        resp = self.client.get(reverse("reports:rep53"))
        self.assertContains(resp, "يومي")

    def test_financial_guards(self):
        self.client.force_login(self.peon)
        self.assertEqual(self.client.get(reverse("reports:rep31")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:rep33")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:rep34")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:rep35")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:rep50")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:rep52")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:rep53")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:rep54")).status_code, 403)

    def test_rep42_export_csv(self):
        resp = self.client.get(reverse("reports:export", args=["rep42", "csv"]))
        self.assertEqual(resp.status_code, 200)
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8"))))
        self.assertEqual(rows[0][0], "الموظف")
        self.assertIn("V2-001", rows[1][0])


class ScheduledReportTests(TestCase):
    """التقارير المجدولة (T-REP-5): التنفيذ + الإشعارات + التنزيل."""

    @classmethod
    def setUpTestData(cls):
        Permission.objects.get_or_create(code="reports.view", defaults={"module": "core", "name_ar": "التقارير"})
        Permission.objects.get_or_create(code="reports.export", defaults={"module": "core", "name_ar": "تصدير"})
        cls.admin = User.objects.create_superuser(username="sch_admin", password="pass")
        cls.recipient = User.objects.create_user(username="sch_rec", password="pass")
        cls.branch = Branch.objects.create(code="BR-S", name_ar="فرع S")
        cls.dept = Department.objects.create(code="DEP-S", name_ar="قسم S", branch=cls.branch)
        cls.emp = Employee.objects.create(
            employee_code="S-001", first_name_ar="سامي", last_name_ar="S",
            branch=cls.branch, department=cls.dept,
        )
        from apps.reports.models import ReportDefinition

        cls.definition = ReportDefinition.objects.create(
            code="REP-01", name_ar="قائمة الموظفين", owner=cls.admin,
            template_type=ReportDefinition.Template.CSV, schedule=ReportDefinition.Schedule.DAILY,
            run_at=datetime.time(8, 30), filters_json={},
        )
        cls.definition.notify_users.add(cls.recipient)

    def setUp(self):
        from apps.reports.models import ReportDefinition

        now = datetime.datetime.now().replace(hour=8, minute=30)
        ReportDefinition.objects.filter(pk=self.definition.pk).update(last_run_at=None)
        self._now = now

    def test_is_due_daily(self):
        from apps.reports.scheduling import _is_due
        from apps.reports.models import ReportDefinition

        due = _is_due(self.definition, datetime.datetime.now().replace(hour=9, minute=0))
        self.assertTrue(due)
        not_due = _is_due(self.definition, datetime.datetime.now().replace(hour=8, minute=0))
        self.assertFalse(not_due)

    def test_run_creates_job_and_file(self):
        from apps.notif.models import Notification
        from apps.reports.models import ReportJob

        jobs = run_scheduled_reports()
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.status, ReportJob.Status.DONE)
        self.assertEqual(job.files.count(), 1)
        f = job.files.first()
        self.assertEqual(f.format, "csv")
        self.assertGreater(f.size_bytes, 0)
        self.assertTrue(Path(f.file_path).exists())
        self.assertTrue(Notification.objects.filter(user=self.recipient).exists())

    def test_no_rerun_same_window(self):
        from apps.reports.models import ReportJob

        self.assertEqual(len(run_scheduled_reports()), 1)
        self.assertEqual(len(run_scheduled_reports()), 0)
        self.assertEqual(ReportJob.objects.count(), 1)

    def test_invalid_code_fails_job(self):
        from apps.reports.models import ReportDefinition, ReportJob

        ReportDefinition.objects.create(
            code="REP-99", name_ar="غير معروف", owner=self.admin,
            template_type=ReportDefinition.Template.CSV, schedule=ReportDefinition.Schedule.DAILY,
            run_at=datetime.time(8, 30),
        )
        jobs = run_scheduled_reports()
        failed = [j for j in jobs if j.status == ReportJob.Status.FAILED]
        self.assertEqual(len(failed), 1)

    def test_generated_list_and_download(self):
        self.client.force_login(self.admin)
        run_scheduled_reports()
        resp = self.client.get(reverse("reports:generated"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "قائمة الموظفين")
        f = self.definition.jobs.first().files.first()
        resp = self.client.get(reverse("reports:generated_download", args=[f.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_download_guard(self):
        self.client.force_login(self.recipient)
        self.assertEqual(self.client.get(reverse("reports:generated")).status_code, 403)
