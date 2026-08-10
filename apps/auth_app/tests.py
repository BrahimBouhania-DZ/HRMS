"""اختبارات RBAC (T-RBAC-7): الصلاحيات، الميراث، الاستثناءات، النطاقات."""

from django.test import TestCase

from apps.employees.models import Employee
from apps.org.models import Branch, Department, Position

from .models import Permission, Role, RoleMember, User, UserPermission
from .scopes import employee_scope_queryset
from .services import effective_permissions, has_perm


class EffectivePermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.view_perm = Permission.objects.create(code="employee.view", module="employees", name_ar="عرض")
        cls.create_perm = Permission.objects.create(code="employee.create", module="employees", name_ar="إضافة")
        cls.salary_perm = Permission.objects.create(code="employee.salary.view", module="employees", name_ar="راتب")

        cls.hr_role = Role.objects.create(code="hr_manager", name_ar="مدير HR", is_system=True)
        cls.hr_role.permission_links.create(permission=cls.view_perm)
        cls.hr_role.permission_links.create(permission=cls.create_perm)

        cls.user = User.objects.create_user(username="omar", password="pass")
        RoleMember.objects.create(user=cls.user, role=cls.hr_role)

    def test_union_of_roles(self):
        self.assertTrue(has_perm(self.user, "employee.view"))
        self.assertTrue(has_perm(self.user, "employee.create"))
        self.assertFalse(has_perm(self.user, "employee.salary.view"))

    def test_direct_grant_and_deny(self):
        UserPermission.objects.create(user=self.user, permission=self.salary_perm, action=UserPermission.GRANT)
        self.assertTrue(has_perm(self.user, "employee.salary.view"))

        # Deny يتفوق على Grant
        UserPermission.objects.create(user=self.user, permission=self.create_perm, action=UserPermission.DENY)
        self.assertFalse(has_perm(self.user, "employee.create"))
        self.assertTrue(has_perm(self.user, "employee.view"))

    def test_superuser_has_everything(self):
        Permission.objects.create(code="anything.whatever", module="core", name_ar="ش")
        admin = User.objects.create_superuser(username="root", password="pass")
        self.assertTrue(has_perm(admin, "anything.whatever"))


class RoleInheritanceTests(TestCase):
    def test_child_role_inherits_parent(self):
        parent = Role.objects.create(code="parent", name_ar="أب")
        child = Role.objects.create(code="child", name_ar="ابن", parent=parent)
        perm = Permission.objects.create(code="x.view", module="x", name_ar="عرض")
        parent.permission_links.create(permission=perm)

        user = User.objects.create_user(username="kid", password="pass")
        RoleMember.objects.create(user=user, role=child)
        self.assertTrue(has_perm(user, "x.view"))


class ScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch_a = Branch.objects.create(code="A", name_ar="فرع أ")
        cls.branch_b = Branch.objects.create(code="B", name_ar="فرع ب")
        cls.dept_a = Department.objects.create(code="D1", branch=cls.branch_a, name_ar="قسم أ")
        cls.pos = Position.objects.create(code="P1", name_ar="منصب", department=cls.dept_a)

        cls.emp_a = Employee.objects.create(
            employee_code="E-A", first_name_ar="موظف", last_name_ar="أ", branch=cls.branch_a,
            department=cls.dept_a, position=cls.pos,
        )
        cls.emp_b = Employee.objects.create(
            employee_code="E-B", first_name_ar="موظف", last_name_ar="ب", branch=cls.branch_b,
        )

        cls.supervisor = User.objects.create_user(username="sup", password="pass")
        Employee.objects.create(
            employee_code="E-SUP", first_name_ar="مشرف", last_name_ar="س",
            branch=cls.branch_a, department=cls.dept_a, user=cls.supervisor,
        )
        RoleMember.objects.create(
            user=cls.supervisor,
            role=Role.objects.create(code="supervisor", name_ar="مشرف", is_system=True),
        )

    def test_supervisor_sees_only_own_department(self):
        qs = employee_scope_queryset(self.supervisor)
        self.assertIn(self.emp_a, qs)
        self.assertNotIn(self.emp_b, qs)

    def test_admin_sees_all(self):
        admin = User.objects.create_superuser(username="root", password="pass")
        qs = employee_scope_queryset(admin)
        self.assertIn(self.emp_a, qs)
        self.assertIn(self.emp_b, qs)

    def test_employee_sees_only_self(self):
        emp_user = User.objects.create_user(username="emp1", password="pass")
        self.emp_a.user = emp_user
        self.emp_a.save()
        RoleMember.objects.create(
            user=emp_user,
            role=Role.objects.create(code="employee", name_ar="موظف", is_system=True),
        )
        qs = employee_scope_queryset(emp_user)
        self.assertEqual(list(qs), [self.emp_a])
