"""اختبارات الإجازات (T-022..T-026, S4).

يغطي: حساب أيام العمل (عطلة نهاية الأسبوع + العطل الرسمية)،
دورة الطلب→الموافقة→خصم الرصيد، سلاسل الموافقات متعددة المستويات،
الرفض/الإلغاء، وصلاحيات النطاقات.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auth_app.models import Permission, Role, RoleMember
from apps.employees.models import Employee
from apps.org.models import Branch
from apps.leave.models import (
    LeaveApproval,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    PublicHoliday,
)
from apps.leave.services import (
    LeaveError,
    adjust_balance,
    approve_request,
    calculate_leave_days,
    cancel_request,
    reject_request,
    submit_request,
)

User = get_user_model()


def _branch():
    return Branch.objects.create(code="BR-L", name_ar="فرع")


def _annual(**kwargs):
    defaults = {
        "code": "annual", "name_ar": "سنوية", "days_per_year": 30,
        "requires_approval_levels": 1, "is_active": True,
    }
    defaults.update(kwargs)
    return LeaveType.objects.create(**defaults)


class LeaveDayCalculationTests(TestCase):
    def setUp(self):
        self.branch = _branch()

    def test_counts_only_workdays(self):
        # 2026-08-10 (الإثنين) ← 2026-08-14 (الجمعة): الجمعة والسبت خارج؟
        # 10=Mon,11=Tue,12=Wed,13=Thu,14=Fri → 4 أيام عمل (الجمعة والسبت عطلة)
        days = calculate_leave_days(datetime.date(2026, 8, 10), datetime.date(2026, 8, 15), self.branch)
        self.assertEqual(days, 4)

    def test_public_holiday_excluded(self):
        PublicHoliday.objects.create(
            branch=self.branch, date=datetime.date(2026, 8, 12), name_ar="عيد"
        )
        days = calculate_leave_days(datetime.date(2026, 8, 10), datetime.date(2026, 8, 14), self.branch)
        self.assertEqual(days, 3)

    def test_recurring_holiday_applies_other_years(self):
        PublicHoliday.objects.create(
            branch=self.branch, date=datetime.date(2024, 7, 5), name_ar="عيد متكرر", is_recurring=True
        )
        # 2026-07-05 هو الأحد (عطلة نهاية أسبوع بالصدفة؟ نتحقق: لا) — يبقى محسوبًا كعطلة
        days = calculate_leave_days(datetime.date(2026, 7, 6), datetime.date(2026, 7, 7), self.branch)
        self.assertEqual(days, 2)  # لا تداخل مع 7/5

        days2 = calculate_leave_days(datetime.date(2026, 7, 5), datetime.date(2026, 7, 5), self.branch)
        self.assertEqual(days2, 0)

    def test_invalid_range(self):
        with self.assertRaises(LeaveError):
            calculate_leave_days(datetime.date(2026, 8, 14), datetime.date(2026, 8, 10), self.branch)


class LeaveRequestFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = _branch()
        cls.employee = Employee.objects.create(
            employee_code="E-LV", first_name_ar="إ", last_name_ar="ج",
            branch=cls.branch,
        )
        cls.approver = User.objects.create_user(username="approver", password="pass")

    def setUp(self):
        self.annual = _annual()
        self.balance = LeaveBalance.objects.create(
            employee=self.employee, leave_type=self.annual,
            year=2026, granted=30,
        )

    def _range(self):
        return datetime.date(2026, 8, 10), datetime.date(2026, 8, 14)

    def test_submit_creates_pending_and_days(self):
        req = submit_request(self.employee, self.annual, *self._range(), reason="رحلة")
        self.assertEqual(req.status, LeaveRequest.Status.PENDING)
        self.assertEqual(req.current_level, 1)
        self.assertIsNotNone(req.submitted_at)
        self.assertEqual(req.days, 4)

    def test_submit_auto_grants_balance_on_first_use(self):
        other = LeaveType.objects.create(code="other", name_ar="أخرى", days_per_year=10)
        submit_request(self.employee, other, *self._range())
        bal = LeaveBalance.objects.get(employee=self.employee, leave_type=other, year=2026)
        self.assertEqual(bal.granted, 10)

    def test_submit_rejects_insufficient_balance(self):
        self.balance.used = 28
        self.balance.save()
        with self.assertRaises(LeaveError):
            submit_request(self.employee, self.annual, *self._range())

    def test_submit_rejects_inactive_type(self):
        self.annual.is_active = False
        self.annual.save()
        with self.assertRaises(LeaveError):
            submit_request(self.employee, self.annual, *self._range())

    def test_approval_deducts_balance(self):
        req = submit_request(self.employee, self.annual, *self._range())
        req = approve_request(req, self.approver)
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.used, 4)
        self.assertEqual(self.balance.remaining, 26)

    def test_approval_chain_multilevel(self):
        self.annual.requires_approval_levels = 2
        self.annual.save()
        req = submit_request(self.employee, self.annual, *self._range())
        req = approve_request(req, self.approver)
        self.assertEqual(req.status, LeaveRequest.Status.PENDING)
        self.assertEqual(req.current_level, 2)
        self.assertEqual(LeaveApproval.objects.filter(leave_request=req).count(), 1)
        # الرصيد لم يُخصم بعد
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.used, 0)
        req = approve_request(req, self.approver)
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.used, 4)

    def test_reject_stops_flow(self):
        req = submit_request(self.employee, self.annual, *self._range())
        req = reject_request(req, self.approver, comment="لا داعي")
        self.assertEqual(req.status, LeaveRequest.Status.REJECTED)
        self.assertEqual(req.approvals.count(), 1)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.used, 0)

    def test_cancel_only_when_pending(self):
        req = submit_request(self.employee, self.annual, *self._range())
        cancel_request(req, self.approver)
        req.refresh_from_db()
        self.assertEqual(req.status, LeaveRequest.Status.CANCELLED)
        req2 = submit_request(self.employee, self.annual, *self._range())
        approve_request(req2, self.approver)
        with self.assertRaises(LeaveError):
            cancel_request(req2, self.approver)

    def test_adjust_balance(self):
        adjust_balance(self.employee, self.annual, 2026, 2, None)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.adjusted, 2)
        adjust_balance(self.employee, self.annual, 2026, -1, None)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.adjusted, 1)


class LeaveViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = _branch()
        cls.view_perm = Permission.objects.create(code="leave.balance.view", module="leave", name_ar="عرض")
        cls.request_perm = Permission.objects.create(code="leave.request", module="leave", name_ar="طلب")
        cls.approve_perm = Permission.objects.create(code="leave.approve", module="leave", name_ar="اعتماد")
        cls.adjust_perm = Permission.objects.create(code="leave.balance.adjust", module="leave", name_ar="تسوية")

        cls.hr = User.objects.create_user(username="hr", password="pass")
        hr_role = Role.objects.create(code="hr_manager", name_ar="HR", is_system=True)
        for p in (cls.view_perm, cls.approve_perm, cls.adjust_perm):
            hr_role.permission_links.create(permission=p)
        RoleMember.objects.create(user=cls.hr, role=hr_role)

        cls.employee = Employee.objects.create(
            employee_code="E-V", first_name_ar="م", last_name_ar="ل",
            branch=cls.branch,
        )
        cls.emp_user = User.objects.create_user(username="empl", password="pass")
        cls.employee.user = cls.emp_user
        cls.employee.save()
        emp_role = Role.objects.create(code="employee", name_ar="موظف", is_system=True)
        emp_role.permission_links.create(permission=cls.view_perm)
        emp_role.permission_links.create(permission=cls.request_perm)
        RoleMember.objects.create(user=cls.emp_user, role=emp_role)

    def test_employee_submits_request(self):
        annual = _annual()
        self.client.force_login(self.emp_user)
        resp = self.client.post(
            reverse("leave:request_create"),
            {
                "leave_type": annual.pk,
                "from_date": "2026-09-07",
                "to_date": "2026-09-09",
                "reason": "عائلية",
            },
        )
        self.assertEqual(resp.status_code, 302)
        req = LeaveRequest.objects.get(employee=self.employee)
        self.assertEqual(req.days, 3)
        self.assertEqual(req.status, LeaveRequest.Status.PENDING)

    def test_employee_my_leave_shows_balances(self):
        annual = _annual()
        LeaveBalance.objects.create(employee=self.employee, leave_type=annual, year=2026, granted=30)
        self.client.force_login(self.emp_user)
        resp = self.client.get(reverse("leave:my_leave"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "سنوية")

    def test_hr_approves_via_queue(self):
        annual = _annual()
        req = submit_request(self.employee, annual, datetime.date(2026, 9, 7), datetime.date(2026, 9, 9))
        self.client.force_login(self.hr)
        resp = self.client.post(
            reverse("leave:request_approve", args=[req.pk, "approve"]),
            {"comment": "موافق"},
        )
        self.assertEqual(resp.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)
        bal = LeaveBalance.objects.get(employee=self.employee, leave_type=annual, year=2026)
        self.assertEqual(bal.used, 3)

    def test_employee_cannot_see_queue(self):
        self.client.force_login(self.emp_user)
        resp = self.client.get(reverse("leave:request_list"))
        self.assertEqual(resp.status_code, 403)

    def test_balance_adjust_requires_permission(self):
        annual = _annual()
        bal = LeaveBalance.objects.create(employee=self.employee, leave_type=annual, year=2026, granted=30)
        self.client.force_login(self.emp_user)
        resp = self.client.post(reverse("leave:balance_adjust", args=[bal.pk]), {"amount": "5"})
        self.assertEqual(resp.status_code, 403)
