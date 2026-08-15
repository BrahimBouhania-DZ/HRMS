"""اختبارات واجهة API للموبايل (apps/api) — تسجيل دخول، مسح، ملفي، سجل الحضور.

يغطي: الحصول على رمز Token (موظف فقط)، الإبطال، مسح QR بصلاحية/بجهاز،
منع رموز الآخرين، ملف الموظف، واستعلام سجل الحضور.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.attendance.models import AttendanceDay, AttendanceScan
from apps.auth_app.models import Permission, Role, RoleMember
from apps.devices.models import QrDevice
from apps.devices.services import hash_api_key
from apps.employees.models import Employee
from apps.employees.qr_service import get_qr_payload, issue_qr
from apps.org.models import Branch, Shift

User = get_user_model()


def _grant(user, code, module="attendance"):
    perm = Permission.objects.create(code=code, module=module, name_ar=code)
    role = Role.objects.create(code=f"r-{code.replace('.', '-')}", name_ar=code, is_system=True)
    role.permission_links.create(permission=perm)
    RoleMember.objects.create(user=user, role=role)


def _shift():
    return Shift.objects.create(
        code="SH-API", name_ar="صباحي", start_time="08:00", end_time="16:00", grace_minutes=10
    )


class ApiAuthTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="emp1", password="pass1234")
        self.employee = Employee.objects.create(
            employee_code="E-API1", first_name_ar="ع", last_name_ar="ر",
            branch=Branch.objects.create(code="B-API1", name_ar="فرع"),
            shift=_shift(),
            user=self.user,
        )
        self.login_url = reverse("api:api_login")

    def test_login_returns_token_and_profile(self):
        resp = self.client.post(self.login_url, {"username": "emp1", "password": "pass1234"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.data)
        self.assertEqual(resp.data["employee"]["employee_code"], "E-API1")
        token = Token.objects.get(user=self.user)
        self.assertEqual(resp.data["token"], token.key)

    def test_login_wrong_password(self):
        resp = self.client.post(self.login_url, {"username": "emp1", "password": "wrong"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("token", resp.data)

    def test_login_rejects_non_employee_account(self):
        admin = User.objects.create_user(username="boss", password="pass1234", is_staff=True)
        resp = self.client.post(self.login_url, {"username": "boss", "password": "pass1234"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_logout_invalidates_token(self):
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        resp = self.client.post(reverse("api:api_logout"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.user).exists())


class ApiScanTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scanner", password="pass1234")
        self.employee = Employee.objects.create(
            employee_code="E-SC", first_name_ar="م", last_name_ar="س",
            branch=Branch.objects.create(code="B-SC", name_ar="فرع"),
            shift=_shift(),
            user=self.user,
        )
        _grant(self.user, "attendance.scan")
        issue_qr(self.employee)
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.url = reverse("api:api_scan")

    def _scan(self, payload):
        return self.client.post(self.url, {"payload": payload}, format="json")

    def test_checkin_with_token(self):
        resp = self._scan(get_qr_payload(self.employee))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["ok"])
        self.assertEqual(resp.data["decision"], "check_in")
        day = AttendanceDay.objects.get(employee=self.employee)
        self.assertIsNotNone(day.check_in)

    def test_second_scan_checkout(self):
        AttendanceDay.objects.create(
            employee=self.employee,
            work_date=timezone.localdate(),
            state=AttendanceDay.State.PRESENT,
            check_in=timezone.now() - timezone.timedelta(hours=2),
        )
        resp = self._scan(get_qr_payload(self.employee))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["decision"], "check_out")

    def test_requires_permission(self):
        user = User.objects.create_user(username="noperm", password="pass1234")
        emp = Employee.objects.create(
            employee_code="E-NP", first_name_ar="ب", last_name_ar="ل", user=user
        )
        issue_qr(emp)
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        resp = self._scan(get_qr_payload(emp))
        self.assertEqual(resp.status_code, 403)

    def test_rejects_foreign_qr(self):
        other = Employee.objects.create(employee_code="E-FR", first_name_ar="غ", last_name_ar="ر")
        issue_qr(other)
        resp = self._scan(get_qr_payload(other))
        self.assertEqual(resp.status_code, 422)
        self.assertIn("لا يخص", resp.data["error"])

    def test_requires_authentication(self):
        self.client.credentials()
        resp = self._scan(get_qr_payload(self.employee))
        self.assertEqual(resp.status_code, 401)

    def test_device_api_key_scan(self):
        device = QrDevice.objects.create(
            device_code="D-SC",
            branch=self.employee.branch,
            api_key_hash=hash_api_key("secret-key-123"),
        )
        self.client.credentials(HTTP_X_DEVICE_CODE="D-SC", HTTP_X_API_KEY="secret-key-123")
        resp = self._scan(get_qr_payload(self.employee))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["decision"], "check_in")
        scan = AttendanceScan.objects.get(employee=self.employee)
        self.assertEqual(scan.source, AttendanceScan.Source.FIXED_READER)

    def test_device_scan_accepts_any_employee(self):
        other = Employee.objects.create(
            employee_code="E-DEV",
            first_name_ar="خ", last_name_ar="ر",
            branch=self.employee.branch,
            shift=self.employee.shift,
        )
        issue_qr(other)
        QrDevice.objects.create(
            device_code="D-SC2",
            branch=self.employee.branch,
            api_key_hash=hash_api_key("k"),
        )
        self.client.credentials(HTTP_X_DEVICE_CODE="D-SC2", HTTP_X_API_KEY="k")
        resp = self._scan(get_qr_payload(other))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["decision"], "check_in")

    def test_bad_device_key_rejected(self):
        self.client.credentials(HTTP_X_DEVICE_CODE="D-X", HTTP_X_API_KEY="wrong")
        resp = self._scan(get_qr_payload(self.employee))
        self.assertEqual(resp.status_code, 401)


class ApiMeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="me", password="pass1234")
        self.employee = Employee.objects.create(
            employee_code="E-ME", first_name_ar="ذ", last_name_ar="ي",
            branch=Branch.objects.create(code="B-ME", name_ar="فرع"),
            shift=_shift(),
            user=self.user,
        )
        issue_qr(self.employee)
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_me_returns_profile_and_qr(self):
        resp = self.client.get(reverse("api:api_me"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["employee_code"], "E-ME")
        self.assertIsNotNone(resp.data["qr_payload"])
        self.assertIsNone(resp.data["today"])

    def test_me_attendance_range(self):
        day = AttendanceDay.objects.create(
            employee=self.employee, work_date="2026-01-10", state="present"
        )
        resp = self.client.get(reverse("api:api_my_attendance"), {"from": "2026-01-01", "to": "2026-01-31"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["work_date"], "2026-01-10")

    def test_me_attendance_bad_date(self):
        resp = self.client.get(reverse("api:api_my_attendance"), {"from": "bad"})
        self.assertEqual(resp.status_code, 400)

    def test_me_requires_auth(self):
        self.client.credentials()
        resp = self.client.get(reverse("api:api_me"))
        self.assertEqual(resp.status_code, 401)


class ApiRecruitmentTests(APITestCase):
    """تغطية endpoints التوظيف: قائمة الإعلانات، التفاصيل، قائمة/إنشاء المرشحين."""

    def setUp(self):
        self.mgr = User.objects.create_user(username="rec_mgr", password="pass1234")
        for code in [
            "recruitment.posting.view",
            "recruitment.candidate.view",
            "recruitment.candidate.manage",
        ]:
            _grant(self.mgr, code, module="recruitment")
        self.token, _ = Token.objects.get_or_create(user=self.mgr)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        from apps.recruitment.models import Candidate, JobPosting

        self.posting = JobPosting.objects.create(
            code="JOB-API", title_ar="محاسب", employment_type="full_time",
            status=JobPosting.Status.PUBLISHED, openings_count=2,
        )
        self.candidate = Candidate.objects.create(
            posting=self.posting, first_name_ar="سعيد", last_name_ar="أ",
            email="s@example.com", status=Candidate.Status.NEW,
        )

    def test_posting_list_requires_permission(self):
        user = User.objects.create_user(username="no_perm", password="pass1234")
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        resp = self.client.get(reverse("api:api_recruitment_postings"))
        self.assertEqual(resp.status_code, 403)

    def test_posting_list_returns_published(self):
        resp = self.client.get(reverse("api:api_recruitment_postings"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["code"], "JOB-API")
        self.assertEqual(resp.data[0]["candidate_count"], 1)

    def test_posting_detail(self):
        resp = self.client.get(reverse("api:api_recruitment_posting_detail", args=[self.posting.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["openings_count"], 2)

    def test_candidate_create(self):
        resp = self.client.post(
            reverse("api:api_recruitment_candidates"),
            {
                "posting": self.posting.pk,
                "first_name_ar": "ليلى",
                "last_name_ar": "ب",
                "email": "l@example.com",
                "phone": "0550",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["email"], "l@example.com")
        self.assertEqual(resp.data["status"], "new")

    def test_candidate_create_rejects_closed_posting(self):
        self.posting.status = "closed"
        self.posting.save()
        resp = self.client.post(
            reverse("api:api_recruitment_candidates"),
            {
                "posting": self.posting.pk,
                "first_name_ar": "ليلى",
                "last_name_ar": "ب",
                "email": "l2@example.com",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_candidate_list_filters(self):
        resp = self.client.get(reverse("api:api_recruitment_candidates"), {"status": "new"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["email"], "s@example.com")
