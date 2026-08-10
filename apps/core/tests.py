"""اختبارات لوحة المؤشرات + البحث الموحّد (S5)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.auth_app.models import Role, RoleMember
from apps.attendance.models import AttendanceDay
from apps.employees.models import Employee
from apps.leave.models import LeaveRequest, LeaveType
from apps.org.models import Branch, Department, Position

User = get_user_model()


def _branch(name="فرع A", code="BR-S5"):
    return Branch.objects.create(code=code, name_ar=name)


def _employee(code, branch, first="محمد", last="س5", dept=None, pos=None, user=None):
    return Employee.objects.create(
        employee_code=code, first_name_ar=first, last_name_ar=last,
        branch=branch, department=dept, position=pos, user=user,
        employment_status=Employee.EmploymentStatus.ACTIVE,
    )


def _grant_employee_role(user):
    role, _ = Role.objects.get_or_create(code="employee", name_ar="موظف")
    RoleMember.objects.get_or_create(user=user, role=role)
    return role


class DashboardKPITests(TestCase):
    """قيم KPI + النطاقات."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(username="dash_admin", password="pass")
        cls.branch = _branch()
        cls.emp_user = User.objects.create_user(username="dash_emp", password="pass")
        _grant_employee_role(cls.emp_user)
        cls.emp = _employee("S5-001", cls.branch, user=cls.emp_user)
        cls.emp2 = _employee("S5-002", cls.branch)
        cls.today = date(2026, 8, 9)
        AttendanceDay.objects.create(employee=cls.emp, work_date=cls.today,
                                     state=AttendanceDay.State.PRESENT, late_minutes=10)
        AttendanceDay.objects.create(employee=cls.emp2, work_date=cls.today,
                                     state=AttendanceDay.State.ABSENT)
        cls.lt = LeaveType.objects.create(code="s5", name_ar="سنوية", days_per_year=30)
        LeaveRequest.objects.create(employee=cls.emp, leave_type=cls.lt,
                                    from_date=date(2026, 9, 1), to_date=date(2026, 9, 3), days=3,
                                    status=LeaveRequest.Status.PENDING)

    def test_kpis_scoped_global(self):
        from apps.core.dashboard import dashboard_kpis

        data = dashboard_kpis(self.superuser, today=self.today)
        k = data["kpis"]
        self.assertEqual(k["employees_total"], 2)
        self.assertEqual(k["present_today"], 1)
        self.assertEqual(k["absent_today"], 1)
        self.assertEqual(k["late_minutes_today"], 10)
        self.assertEqual(k["pending_leaves"], 1)

    def test_kpis_scoped_self_employee(self):
        from apps.core.dashboard import dashboard_kpis

        data = dashboard_kpis(self.emp_user, today=self.today)
        k = data["kpis"]
        self.assertEqual(k["employees_total"], 1)
        self.assertEqual(k["present_today"], 1)
        self.assertEqual(k["pending_leaves"], 1)

    def test_home_view_requires_login_and_renders(self):
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.status_code, 302)
        self.client.force_login(self.superuser)
        resp = self.client.get(reverse("core:home"))
        self.assertContains(resp, "حاضر اليوم")


class UnifiedSearchTests(TestCase):
    """البحث الموحّد + النطاقات."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(username="s_admin", password="pass")
        cls.branch = _branch(code="BR-S6", name="فرع البحث")
        cls.dept = Department.objects.create(code="DEP-S6", name_ar="تقنية", branch=cls.branch)
        cls.pos = Position.objects.create(code="POS-S6", name_ar="مطوّر", department=cls.dept)
        cls.emp = _employee("S6-001", cls.branch, first="مريم", dept=cls.dept, pos=cls.pos)

    def test_search_finds_employee(self):
        from apps.core.search import unified_search

        res = unified_search(self.superuser, "مريم")
        self.assertIn(self.emp, list(res["employees"]))

    def test_search_finds_by_code(self):
        from apps.core.search import unified_search

        res = unified_search(self.superuser, "S6-001")
        self.assertIn(self.emp, list(res["employees"]))

    def test_search_finds_department_and_position(self):
        from apps.core.search import unified_search

        res = unified_search(self.superuser, "تقنية")
        self.assertIn(self.dept, list(res["departments"]))
        res2 = unified_search(self.superuser, "مطوّر")
        self.assertIn(self.pos, list(res2["positions"]))

    def test_empty_query_returns_empty(self):
        from apps.core.search import unified_search

        self.assertEqual(unified_search(self.superuser, "   "), {})

    def test_search_view(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(reverse("core:search"), {"q": "مريم"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "مريم")
        self.assertContains(resp, "نتائج البحث")
