"""اختبارات الواجهات: Org و Employees (CRUD + صلاحيات + Scope)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.auth_app.models import Permission, Role, RoleMember
from apps.employees.models import Employee
from apps.org.models import Branch, Department, Position, Shift

User = get_user_model()


class OrgViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        view_perm = Permission.objects.create(code="org.branch.view", module="org", name_ar="عرض")
        create_perm = Permission.objects.create(code="org.branch.create", module="org", name_ar="إضافة")
        cls.hr_role = Role.objects.create(code="hr_manager", name_ar="مدير HR", is_system=True)
        cls.hr_role.permission_links.create(permission=view_perm)
        cls.hr_role.permission_links.create(permission=create_perm)
        cls.hr = User.objects.create_user(username="hr", password="pass")
        RoleMember.objects.create(user=cls.hr, role=cls.hr_role)
        cls.admin = User.objects.create_superuser(username="root", password="pass")

    def test_admin_can_create_branch(self):
        self.client.force_login(self.admin)
        url = reverse("org:branch_create")
        resp = self.client.post(url, {
            "code": "ALG-9", "name_ar": "فرع الجزائر 9",
            "country": "الجزائر", "city": "الجزائر",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Branch.objects.filter(code="ALG-9").exists())

    def test_hr_manager_can_view_branches(self):
        self.client.force_login(self.hr)
        resp = self.client.get(reverse("org:branch_list"))
        self.assertEqual(resp.status_code, 200)


class EmployeeScopeViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.emp_view = Permission.objects.create(code="employee.view", module="employees", name_ar="عرض")
        cls.branch = Branch.objects.create(code="A", name_ar="فرع أ")
        cls.dept = Department.objects.create(code="D1", branch=cls.branch, name_ar="قسم أ")
        cls.pos = Position.objects.create(code="P1", name_ar="منصب", department=cls.dept)

        cls.emp1 = Employee.objects.create(
            employee_code="E-1", first_name_ar="أول", last_name_ar="موظف",
            branch=cls.branch, department=cls.dept, position=cls.pos,
        )
        cls.emp2 = Employee.objects.create(employee_code="E-2", first_name_ar="ثاني", last_name_ar="موظف")

        # مشرف ينتمي لقسم أ
        cls.sup = User.objects.create_user(username="sup", password="pass")
        sup_profile = Employee.objects.create(
            employee_code="E-SUP", first_name_ar="مشرف", last_name_ar="س",
            branch=cls.branch, department=cls.dept,
            user=cls.sup,
        )
        sup_role = Role.objects.create(code="supervisor", name_ar="مشرف", is_system=True)
        sup_role.permission_links.create(permission=cls.emp_view)
        RoleMember.objects.create(user=cls.sup, role=sup_role)

        # موظف عادي (حسابه مرتبط بملفه)
        cls.employee_user = User.objects.create_user(username="empuser", password="pass")
        cls.employee_user.employee_profile = cls.emp1
        cls.employee_user.save()
        cls.emp1.user = cls.employee_user
        cls.emp1.save()
        emp_role = Role.objects.create(code="employee", name_ar="موظف", is_system=True)
        emp_role.permission_links.create(permission=cls.emp_view)
        RoleMember.objects.create(user=cls.employee_user, role=emp_role)

    def test_supervisor_list_limited_to_department(self):
        self.client.force_login(self.sup)
        resp = self.client.get(reverse("employees:employee_list"))
        self.assertContains(resp, "E-1")
        self.assertNotContains(resp, "E-2")

    def test_employee_cannot_see_others_profile(self):
        self.client.force_login(self.employee_user)
        resp = self.client.get(reverse("employees:employee_detail", args=[self.emp2.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_employee_can_see_own_profile(self):
        self.client.force_login(self.employee_user)
        resp = self.client.get(reverse("employees:employee_detail", args=[self.emp1.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get(reverse("employees:employee_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)
