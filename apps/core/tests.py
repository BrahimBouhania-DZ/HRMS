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


class AuditLogTests(TestCase):
    """سجل التدقيق (v2) — تسجيل عمليات الكتابة + حماية append-only + الصلاحية."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(username="aud_admin", password="pass")

    def test_create_and_update_and_delete_recorded(self):
        from apps.core.models import AuditLog
        from apps.org.models import Branch

        branch = Branch.objects.create(code="AU-1", name_ar="فرع")
        self.assertEqual(AuditLog.objects.filter(model_name="org.Branch", object_id=str(branch.pk)).count(), 1)

        branch.name_ar = "فرع محدث"
        branch.save()
        self.assertEqual(
            AuditLog.objects.filter(model_name="org.Branch", object_id=str(branch.pk), action="update").count(), 1
        )

        pk = branch.pk
        branch.delete()
        self.assertTrue(
            AuditLog.objects.filter(model_name="org.Branch", object_id=str(pk), action="delete").exists()
        )

    def test_auditlog_itself_not_recorded(self):
        from apps.core.models import AuditLog
        from apps.org.models import Branch

        Branch.objects.create(code="AU-3", name_ar="فرع")
        count = AuditLog.objects.count()
        entry = AuditLog.objects.first()
        entry.object_repr = "تعديل غير مسموح"  # لن يُسجَّل تعديل عليه
        entry.save()
        self.assertEqual(AuditLog.objects.count(), count)

    def test_delete_raises(self):
        from apps.core.models import AuditLog
        from apps.org.models import Branch

        Branch.objects.create(code="AU-4", name_ar="فرع")
        with self.assertRaises(NotImplementedError):
            AuditLog.objects.first().delete()

    def test_login_recorded(self):
        from apps.core.models import AuditLog
        from apps.org.models import Branch

        Branch.objects.create(code="AU-2", name_ar="فرع")
        self.client.login(username="aud_admin", password="pass")
        self.assertTrue(AuditLog.objects.filter(action="login", user__username="aud_admin").exists())

    def test_audit_view_requires_permission(self):
        from django.contrib.auth import get_user_model

        from apps.auth_app.models import Permission

        User = get_user_model()
        plain = User.objects.create_user(username="au_plain", password="pass")
        self.client.force_login(plain)
        self.assertEqual(self.client.get(reverse("core:audit_log")).status_code, 403)

        perm = Permission.objects.create(code="system.audit.view", module="core", name_ar="سجل")
        role, _ = Role.objects.get_or_create(code="auditor", name_ar="مدقق")
        role.permission_links.create(permission=perm)
        RoleMember.objects.create(user=plain, role=role)
        resp = self.client.get(reverse("core:audit_log"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "سجل التدقيق")
