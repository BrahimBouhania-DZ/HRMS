"""اختبارات الواجهات: Org و Employees (CRUD + صلاحيات + Scope)."""

import datetime
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.auth_app.models import Permission, Role, RoleMember
from apps.employees.models import Contract, Document, Employee
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


class ContractDocumentViewTests(TestCase):
    """العقود والوثائق (v2) — صلاحيات + نطاق + حالة + تجديد + تنزيل."""

    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(code="CD", name_ar="فرع")
        cls.dept = Department.objects.create(code="D-CD", branch=cls.branch, name_ar="قسم")
        cls.pos = Position.objects.create(code="P-CD", name_ar="منصب", department=cls.dept)

        cls.emp_in = Employee.objects.create(
            employee_code="E-CD1", first_name_ar="داخل", last_name_ar="النطاق",
            branch=cls.branch, department=cls.dept, position=cls.pos,
        )
        cls.emp_out = Employee.objects.create(
            employee_code="E-CD2", first_name_ar="خارج", last_name_ar="النطاق",
            branch=Branch.objects.create(code="CD-2", name_ar="فرع آخر"),
        )

        cls.contract_view = Permission.objects.create(code="employee.contract.view", module="employees", name_ar="عرض عقود")
        cls.contract_manage = Permission.objects.create(code="employee.contract.manage", module="employees", name_ar="إدارة عقود")
        cls.doc_view = Permission.objects.create(code="employee.document.view", module="employees", name_ar="عرض وثائق")
        cls.doc_manage = Permission.objects.create(code="employee.document.manage", module="employees", name_ar="إدارة وثائق")

        # HR: كل الصلاحيات
        cls.hr = User.objects.create_user(username="cd_hr", password="pass")
        hr_role = Role.objects.create(code="hr_manager", name_ar="HR", is_system=True)
        for p in (cls.contract_view, cls.contract_manage, cls.doc_view, cls.doc_manage):
            hr_role.permission_links.create(permission=p)
        RoleMember.objects.create(user=cls.hr, role=hr_role)

        # مشرف: عرض فقط + مرتبط بقسم النطاق
        cls.sup = User.objects.create_user(username="cd_sup", password="pass")
        sup_emp = Employee.objects.create(
            employee_code="E-SUP2", first_name_ar="مشرف", last_name_ar="س",
            branch=cls.branch, department=cls.dept, user=cls.sup,
        )
        sup_role = Role.objects.create(code="supervisor", name_ar="مشرف", is_system=True)
        sup_role.permission_links.create(permission=cls.contract_view)
        sup_role.permission_links.create(permission=cls.doc_view)
        RoleMember.objects.create(user=cls.sup, role=sup_role)

    def _make_contract(self, employee, **kw):
        defaults = {
            "contract_number": "C-%d" % Contract.objects.count(),
            "employee": employee,
            "contract_type": "cdi",
            "start_date": datetime.date(2025, 1, 1),
            "gross_salary": 50000, "base_salary": 40000,
        }
        defaults.update(kw)
        return Contract.objects.create(**defaults)

    def test_contract_status(self):
        c_active = self._make_contract(self.emp_in, end_date=None)
        c_expiring = self._make_contract(self.emp_in, end_date=timezone.localdate() + datetime.timedelta(days=10))
        c_expired = self._make_contract(self.emp_in, end_date=timezone.localdate() - datetime.timedelta(days=1))
        self.assertEqual(c_active.status, "active")
        self.assertEqual(c_expiring.status, "expiring")
        self.assertEqual(c_expired.status, "expired")
        self.assertEqual(c_expiring.days_to_expiry, 10)

    def test_contract_list_requires_permission(self):
        plain = User.objects.create_user(username="cd_noperm", password="pass")
        self.client.force_login(plain)
        self.assertEqual(self.client.get(reverse("employees:contract_list")).status_code, 403)

    def test_contract_list_scoped_to_department(self):
        self._make_contract(self.emp_in)
        self._make_contract(self.emp_out)
        self.client.force_login(self.sup)
        resp = self.client.get(reverse("employees:contract_list"))
        self.assertContains(resp, "C-")
        self.assertContains(resp, "E-CD1")
        self.assertNotContains(resp, "E-CD2")

    def test_contract_create_requires_manage(self):
        self.client.force_login(self.sup)
        resp = self.client.post(reverse("employees:contract_create"), {
            "contract_number": "C-X", "employee": self.emp_in.pk,
            "contract_type": "cdi", "start_date": "2026-01-01",
            "gross_salary": "50000", "base_salary": "40000",
        })
        self.assertEqual(resp.status_code, 403)

    def test_contract_create_by_hr(self):
        self.client.force_login(self.hr)
        resp = self.client.post(reverse("employees:contract_create"), {
            "contract_number": "C-HR", "employee": self.emp_in.pk,
            "contract_type": "cdi", "start_date": "2026-01-01",
            "gross_salary": "50000", "base_salary": "40000",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Contract.objects.filter(contract_number="C-HR").exists())

    def test_contract_renewal_prefills_previous(self):
        prev = self._make_contract(self.emp_in, contract_number="C-REN", end_date=datetime.date(2026, 12, 31))
        self.client.force_login(self.hr)
        resp = self.client.get(reverse("employees:contract_create") + f"?renew={prev.pk}")
        self.assertContains(resp, f'value="{prev.pk}"')  # previous_contract مُسبق
        # إرسال عقد التجديد
        resp = self.client.post(
            reverse("employees:contract_create"),
            {
                "contract_number": "C-REN2", "employee": self.emp_in.pk,
                "contract_type": "cdi", "start_date": "2027-01-01",
                "gross_salary": "50000", "base_salary": "40000",
                "previous_contract": prev.pk,
            },
        )
        self.assertEqual(resp.status_code, 302)
        renewed = Contract.objects.get(contract_number="C-REN2")
        self.assertEqual(renewed.previous_contract, prev)
        self.assertEqual(prev.renewal, renewed)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_document_upload_and_download(self):
        self.client.force_login(self.hr)
        uploaded = SimpleUploadedFile("cv.pdf", b"PDF-CONTENT", content_type="application/pdf")
        resp = self.client.post(reverse("employees:document_upload"), {
            "employee": self.emp_in.pk, "document_type": "cv",
            "title": "السيرة الذاتية", "file": uploaded,
        })
        self.assertEqual(resp.status_code, 302)
        doc = Document.objects.get(title="السيرة الذاتية")
        dl = self.client.get(reverse("employees:document_download", args=[doc.pk]))
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(b"".join(dl.streaming_content), b"PDF-CONTENT")

    def test_document_upload_requires_manage(self):
        self.client.force_login(self.sup)
        resp = self.client.post(reverse("employees:document_upload"), {
            "employee": self.emp_in.pk, "document_type": "cv",
            "title": "سيرة", "file": SimpleUploadedFile("a.pdf", b"x"),
        })
        self.assertEqual(resp.status_code, 403)

    def test_document_list_scoped(self):
        Document.objects.create(employee=self.emp_in, document_type="cv", title="داخل")
        Document.objects.create(employee=self.emp_out, document_type="cv", title="خارج")
        self.client.force_login(self.sup)
        resp = self.client.get(reverse("employees:document_list"))
        self.assertContains(resp, "داخل")
        self.assertNotContains(resp, "خارج")
