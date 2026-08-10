"""اختبارات إدارة أجهزة QR (S6)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.attendance.models import AttendanceDay, AttendanceScan
from apps.auth_app.models import Permission
from apps.devices.models import QrDevice, QrDeviceAudit
from apps.devices.services import (
    hash_api_key,
    register_device,
    set_device_status,
)
from apps.employees.models import Employee
from apps.employees.qr_service import get_qr_payload, issue_qr
from apps.org.models import Branch, Shift

User = get_user_model()


class DeviceServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="dev_admin", password="pass")
        self.branch = Branch.objects.create(code="BR-D", name_ar="فرع D")

    def test_register_returns_one_time_key_and_stores_hash(self):
        device, key = register_device("DEV-1", self.branch, self.admin)
        self.assertTrue(key)
        self.assertEqual(device.api_key_hash, hash_api_key(key))
        self.assertNotEqual(device.api_key_hash, key)
        self.assertEqual(QrDeviceAudit.objects.filter(device=device, action="register").count(), 1)

    def test_status_change_audits(self):
        device, _ = register_device("DEV-2", self.branch, self.admin)
        set_device_status(device, "inactive", self.admin)
        device.refresh_from_db()
        self.assertEqual(device.status, "inactive")
        self.assertTrue(QrDeviceAudit.objects.filter(device=device, action="status:active->inactive").exists())

    def test_generate_api_key_unique_and_random(self):
        from apps.devices.services import generate_api_key

        keys = {generate_api_key() for _ in range(50)}
        self.assertEqual(len(keys), 50)


class DeviceViewTests(TestCase):
    def setUp(self):
        Permission.objects.create(code="device.manage", module="devices", name_ar="إدارة")
        self.admin = User.objects.create_superuser(username="dev_view", password="pass")
        self.emp = User.objects.create_user(username="dev_emp", password="pass")
        self.branch = Branch.objects.create(code="BR-DV", name_ar="فرع V")
        self.device, self.key = register_device("DEV-V", self.branch, self.admin)

    def test_list_requires_device_manage(self):
        self.client.force_login(self.emp)
        self.assertEqual(self.client.get(reverse("devices:list")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("devices:list")), "DEV-V")

    def test_create_shows_key_once(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("devices:create"), {
            "device_code": "DEV-NEW", "branch": self.branch.pk, "location": "بوابة",
        })
        device = QrDevice.objects.get(device_code="DEV-NEW")
        self.assertRedirects(resp, reverse("devices:detail", args=[device.pk]), fetch_redirect_response=False)
        detail = self.client.get(reverse("devices:detail", args=[device.pk]))
        self.assertContains(detail, "مفتاح API")
        # المفتاح لا يظهر مرة ثانية
        detail2 = self.client.get(reverse("devices:detail", args=[device.pk]))
        self.assertNotContains(detail2, "مفتاح API")

    def test_status_view_requires_post(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("devices:status", args=[self.device.pk, "inactive"]))
        self.assertEqual(resp.status_code, 405)
        resp = self.client.post(reverse("devices:status", args=[self.device.pk, "maintenance"]))
        self.assertRedirects(resp, reverse("devices:detail", args=[self.device.pk]))
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, "maintenance")


class DeviceScanIntegrationTests(TestCase):
    """S6 تكامل: جهاز → مسح API → تسجيل حضور → تقرير (REP-16)."""

    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(code="BR-IT", name_ar="فرع تكامل")
        Permission.objects.create(code="reports.view", module="core", name_ar="التقارير")
        cls.shift = Shift.objects.create(
            code="SH-IT", name_ar="صباحي", start_time="08:00", end_time="16:00", grace_minutes=10
        )
        cls.admin = User.objects.create_superuser(username="it_admin", password="pass")
        cls.employee = Employee.objects.create(
            employee_code="E-IT1", first_name_ar="تكامل", last_name_ar="جهاز",
            branch=cls.branch, shift=cls.shift,
        )
        cls.device, cls.key = register_device("DEV-IT", cls.branch, cls.admin)
        issue_qr(cls.employee)

    def _scan_from_device(self, device_code, key):
        return self.client.post(
            reverse("attendance:api_scan"),
            {"payload": get_qr_payload(self.employee)},
            HTTP_X_DEVICE_CODE=device_code,
            HTTP_X_API_KEY=key,
        )

    def test_device_scan_records_attendance_and_report(self):
        # 1) دخول عبر جهاز (جلسة مجهولة = قارئ خارجي)
        resp = self._scan_from_device("DEV-IT", self.key)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["decision"], "check_in")

        # 2) مسح متكرر خلال نافذة الأمان (60 ث) يُرفض عبر نفس القناة
        resp = self._scan_from_device("DEV-IT", self.key)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["decision"], "rejected")

        # 3) يوم حضور واحد + مسحتان مرتبطتان بالجهاز (دخول + مرفوض)
        self.assertEqual(AttendanceDay.objects.filter(employee=self.employee).count(), 1)
        scans = AttendanceScan.objects.filter(employee=self.employee, device=self.device)
        self.assertEqual(scans.count(), 2)

        # 4) REP-16 يعرض المسحات (بصلاحية reports.view)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("reports:rep16"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "DEV-IT")
        self.assertContains(resp, "دخول")

    def test_device_auth_rejects_bad_or_inactive(self):
        # مفتاح خاطئ
        resp = self._scan_from_device("DEV-IT", "wrong-key")
        self.assertEqual(resp.status_code, 401)
        # جهاز غير معروف
        resp = self._scan_from_device("DEV-X", self.key)
        self.assertEqual(resp.status_code, 401)
        # جهاز معطّل لا يقبل المسح
        set_device_status(self.device, "inactive", self.admin)
        resp = self._scan_from_device("DEV-IT", self.key)
        self.assertEqual(resp.status_code, 401)
