"""اختبارات الحضور + نظام QR (T-018..T-021, T-QR).

يغطي: توقيع QR، إصدار/إعادة توليد/إلغاء، قرارات المسح (دخول/خروج/تكرار/تحذير)،
التحقق الأمني (تزوير/نسخة قديمة/موظف غير نشط)، وعرض السجل ضمن النطاق.
"""

import base64
import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import AttendanceDay, AttendanceScan
from apps.attendance.services import decide_and_record_scan, verify_qr_token
from apps.auth_app.models import Permission, Role, RoleMember
from apps.employees.models import Employee
from apps.employees.qr_engine import generate_payload, verify_payload
from apps.employees.qr_service import get_active_qr, get_qr_payload, issue_qr, revoke_qr
from apps.org.models import Branch, Shift

User = get_user_model()


def _shift():
    return Shift.objects.create(
        code="SH-A", name_ar="صباحي", start_time="08:00", end_time="16:00", grace_minutes=10
    )


class QrEngineTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(employee_code="QR-1", first_name_ar="س", last_name_ar="ع")

    def test_payload_roundtrip(self):
        payload = generate_payload(self.employee.id, 1)
        header = verify_payload(payload)
        self.assertIsNotNone(header)
        self.assertEqual(header["employee_id"], self.employee.id)
        self.assertEqual(header["v"], 1)

    def test_tampered_payload_rejected(self):
        payload = generate_payload(self.employee.id, 1)
        self.assertIsNone(verify_payload(payload + "x"))
        # تعديل حقل eid دون إعادة توقيع
        parts = payload.split(".")
        self.assertIsNone(verify_payload(f"{parts[0][:-2]}{'aa' if not parts[0].endswith('aa') else 'bb'}.{parts[1]}"))

    def test_employee_id_is_not_plaintext(self):
        payload = generate_payload(self.employee.id, 1)
        header = payload.split(".", 1)[0]
        decoded = json.loads(base64.urlsafe_b64decode(header + "=="))
        self.assertNotEqual(decoded["eid"], str(self.employee.id))


class QrLifecycleTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(employee_code="QR-2", first_name_ar="س", last_name_ar="ع")

    def test_issue_creates_active_v1(self):
        qr = issue_qr(self.employee)
        self.assertEqual(qr.version, 1)
        self.assertEqual(qr.status, "active")
        self.assertEqual(qr.secret, qr.secret[:32])

    def test_regenerate_bumps_version_and_single_row(self):
        qr1 = issue_qr(self.employee)
        qr2 = issue_qr(self.employee)
        self.assertEqual(qr1.pk, qr2.pk)
        self.assertEqual(qr2.version, 2)

    def test_revoke_marks_inactive(self):
        issue_qr(self.employee)
        revoke_qr(self.employee)
        self.employee.qr_record.refresh_from_db()
        self.assertEqual(self.employee.qr_record.status, "revoked")
        self.assertIsNone(get_qr_payload(self.employee))

    def test_qr_payload_reflects_active_version(self):
        qr = issue_qr(self.employee)
        payload = get_qr_payload(self.employee)
        self.assertIsNotNone(payload)
        header = verify_payload(payload)
        self.assertEqual(header["v"], qr.version)


class ScanDecisionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(code="BR", name_ar="فرع")
        cls.shift = _shift()
        cls.employee = Employee.objects.create(
            employee_code="E-SCAN", first_name_ar="م", last_name_ar="ن",
            branch=cls.branch, shift=cls.shift,
        )

    def setUp(self):
        self.qr = issue_qr(self.employee)
        self.shift.refresh_from_db()

    def test_first_scan_is_check_in(self):
        scan = decide_and_record_scan(self.employee, self.qr)
        self.assertEqual(scan.decision, AttendanceScan.Decision.CHECK_IN)
        day = AttendanceDay.objects.get(employee=self.employee)
        self.assertIsNotNone(day.check_in)
        self.assertEqual(day.state, AttendanceDay.State.PRESENT)

    def test_second_scan_is_check_out_and_worked_computed(self):
        start = datetime.datetime.combine(
            timezone.localdate(), self.shift.start_time, tzinfo=timezone.get_current_timezone()
        ) - timezone.timedelta(minutes=10)
        first = decide_and_record_scan(self.employee, self.qr, scanned_at=start)
        second = decide_and_record_scan(
            self.employee, self.qr, scanned_at=start + timezone.timedelta(hours=8)
        )
        self.assertEqual(second.decision, AttendanceScan.Decision.CHECK_OUT)
        day = AttendanceDay.objects.get(employee=self.employee)
        self.assertEqual(day.worked_minutes, 8 * 60)
        self.assertEqual(day.late_minutes, 0)

    def test_duplicate_scan_within_cooldown_rejected(self):
        first = decide_and_record_scan(self.employee, self.qr)
        dup = decide_and_record_scan(
            self.employee, self.qr, scanned_at=first.scanned_at + timezone.timedelta(seconds=5)
        )
        self.assertEqual(dup.decision, AttendanceScan.Decision.REJECTED)

    def test_third_scan_after_checkout_is_warning(self):
        start = datetime.datetime.combine(
            timezone.localdate(), self.shift.start_time, tzinfo=timezone.get_current_timezone()
        ) - timezone.timedelta(minutes=10)
        first = decide_and_record_scan(self.employee, self.qr, scanned_at=start)
        decide_and_record_scan(
            self.employee, self.qr, scanned_at=start + timezone.timedelta(hours=8)
        )
        third = decide_and_record_scan(
            self.employee, self.qr, scanned_at=start + timezone.timedelta(hours=9)
        )
        self.assertEqual(third.decision, AttendanceScan.Decision.WARNING)

    def test_late_calculation(self):
        self.shift.refresh_from_db()
        late_time = datetime.datetime.combine(
            timezone.localdate(),
            self.shift.start_time,
            tzinfo=timezone.get_current_timezone(),
        ) + datetime.timedelta(minutes=15)
        decide_and_record_scan(self.employee, self.qr, scanned_at=late_time)
        day = AttendanceDay.objects.get(employee=self.employee)
        self.assertEqual(day.late_minutes, 5)

    def test_verify_token_rejects_stale_version(self):
        # الإصدار الحالي v1 → إعادة توليد → أي QR بـ v1 أصبح قديمًا
        old_header = verify_payload(get_qr_payload(self.employee))
        self.assertEqual(old_header["v"], 1)
        issue_qr(self.employee)
        stale = generate_payload(self.employee.id, old_header["v"])
        employee, qr, error = verify_qr_token(stale)
        self.assertIsNone(employee)
        self.assertIn("قديم", error)
        self.assertEqual(get_active_qr(self.employee).version, 2)

    def test_verify_token_rejects_inactive_employee(self):
        self.employee.is_active = False
        self.employee.save()
        employee, qr, error = verify_qr_token(get_qr_payload(self.employee))
        self.assertIsNone(employee)
        self.assertIn("غير نشط", error)


class ScanApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(code="B-API", name_ar="فرع")
        cls.shift = _shift()
        cls.user = User.objects.create_user(username="emp", password="pass")
        cls.employee = Employee.objects.create(
            employee_code="E-API", first_name_ar="ع", last_name_ar="ر",
            branch=cls.branch, shift=cls.shift, user=cls.user,
        )
        perm = Permission.objects.create(code="attendance.scan", module="attendance", name_ar="مسح")
        role = Role.objects.create(code="employee", name_ar="موظف", is_system=True)
        role.permission_links.create(permission=perm)
        RoleMember.objects.create(user=cls.user, role=role)

    def _login_with_csrf(self, user):
        self.client.get(reverse("auth_app:login"))
        token = self.client.cookies["csrftoken"].value
        self.client.force_login(user)
        return token

    def _post_scan(self, payload):
        token = self._login_with_csrf(self.user)
        return self.client.post(
            reverse("attendance:api_scan"),
            {"payload": payload},
            HTTP_X_CSRFTOKEN=token,
        )

    def test_api_checkin_with_valid_payload(self):
        issue_qr(self.employee)
        resp = self._post_scan(get_qr_payload(self.employee))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["decision"], "check_in")

    def test_api_rejects_missing_csrf(self):
        issue_qr(self.employee)
        self.client.force_login(self.user)
        resp = self.client.post(reverse("attendance:api_scan"), {"payload": get_qr_payload(self.employee)})
        self.assertEqual(resp.status_code, 403)

    def test_api_rejects_foreign_qr_for_logged_user(self):
        other = Employee.objects.create(employee_code="E-OTHER", first_name_ar="غ", last_name_ar="ر")
        issue_qr(other)
        resp = self._post_scan(get_qr_payload(other))
        self.assertEqual(resp.status_code, 422)
        self.assertIn("لا يخص", resp.json()["error"])

    def test_api_requires_permission(self):
        no_perm = User.objects.create_user(username="noperm", password="pass")
        issue_qr(self.employee)
        token = self._login_with_csrf(no_perm)
        resp = self.client.post(
            reverse("attendance:api_scan"),
            {"payload": get_qr_payload(self.employee)},
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(resp.status_code, 403)

    def test_api_rejects_tampered_payload(self):
        issue_qr(self.employee)
        resp = self._post_scan("tampered.payload")
        self.assertEqual(resp.status_code, 422)

    def test_fixed_reader_auth_checkin(self):
        import hashlib

        from apps.devices.models import QrDevice

        api_key = "device-secret"
        QrDevice.objects.create(
            device_code="READER-1",
            branch=self.branch,
            api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
        )
        issue_qr(self.employee)
        resp = self.client.post(
            reverse("attendance:api_scan"),
            {"payload": get_qr_payload(self.employee)},
            HTTP_X_DEVICE_CODE="READER-1",
            HTTP_X_API_KEY=api_key,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["decision"], "check_in")
        scan = AttendanceScan.objects.get(employee=self.employee)
        self.assertEqual(scan.source, AttendanceScan.Source.FIXED_READER)

    def test_fixed_reader_wrong_key_rejected(self):
        import hashlib

        from apps.devices.models import QrDevice

        QrDevice.objects.create(
            device_code="READER-2",
            branch=self.branch,
            api_key_hash=hashlib.sha256(b"right-key").hexdigest(),
        )
        resp = self.client.post(
            reverse("attendance:api_scan"),
            {"payload": "whatever"},
            HTTP_X_DEVICE_CODE="READER-2",
            HTTP_X_API_KEY="wrong-key",
        )
        self.assertEqual(resp.status_code, 401)


class AttendanceViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(code="B-V", name_ar="فرع")
        cls.view_perm = Permission.objects.create(code="attendance.view", module="attendance", name_ar="عرض")
        cls.correct_perm = Permission.objects.create(code="attendance.correct", module="attendance", name_ar="تصحيح")
        cls.hr = User.objects.create_user(username="hr", password="pass")
        hr_role = Role.objects.create(code="hr_manager", name_ar="HR", is_system=True)
        hr_role.permission_links.create(permission=cls.view_perm)
        hr_role.permission_links.create(permission=cls.correct_perm)
        RoleMember.objects.create(user=cls.hr, role=hr_role)

        cls.employee = Employee.objects.create(
            employee_code="E-V", first_name_ar="ح", last_name_ar="ض",
            branch=cls.branch,
        )
        cls.day = AttendanceDay.objects.create(
            employee=cls.employee, work_date=timezone.localdate(),
            state=AttendanceDay.State.PRESENT, worked_minutes=480,
        )

    def test_list_requires_permission(self):
        anon = User.objects.create_user(username="anon", password="pass")
        self.client.force_login(anon)
        resp = self.client.get(reverse("attendance:attendance_day_list"))
        self.assertEqual(resp.status_code, 403)

    def test_hr_can_list_and_detail(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse("attendance:attendance_day_list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("attendance:attendance_day_detail", args=[self.day.pk])).status_code, 200
        )

    def test_correction_marks_is_corrected(self):
        self.client.force_login(self.hr)
        resp = self.client.post(
            reverse("attendance:attendance_day_correct", args=[self.day.pk]),
            {
                "work_date": self.day.work_date.isoformat(),
                "state": "present",
                "worked_minutes": "500",
                "late_minutes": "0",
                "early_minutes": "0",
                "overtime_minutes": "0",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.day.refresh_from_db()
        self.assertTrue(self.day.is_corrected)
        self.assertEqual(self.day.worked_minutes, 500)


class AutoAbsenceTests(TestCase):
    """BR-ATT-004 — العلام التلقائي للغياب."""

    def setUp(self):
        self.branch = Branch.objects.create(code="BR-AA", name_ar="فرع غياب")
        self.employee = Employee.objects.create(
            employee_code="AA-1", first_name_ar="س", last_name_ar="ع",
            branch=self.branch, is_active=True, shift=_shift(),
            employment_status=Employee.EmploymentStatus.ACTIVE,
            hire_date=datetime.date(2026, 1, 1),
        )

    def test_marks_missing_workdays_as_absent(self):
        from apps.attendance.services import auto_mark_absences

        created = auto_mark_absences(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31), branch=self.branch)
        # أغسطس 2026: 21 يوم عمل (الاثنين..الجمعة)
        self.assertEqual(created, 21)
        self.assertEqual(
            AttendanceDay.objects.filter(employee=self.employee, work_date__year=2026,
                                         work_date__month=8, state=AttendanceDay.State.ABSENT).count(),
            21,
        )

    def test_is_idempotent(self):
        from apps.attendance.services import auto_mark_absences

        auto_mark_absences(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31), branch=self.branch)
        created = auto_mark_absences(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31), branch=self.branch)
        self.assertEqual(created, 0)

    def test_existing_present_day_is_not_touched(self):
        from apps.attendance.services import auto_mark_absences

        AttendanceDay.objects.create(
            employee=self.employee, work_date=datetime.date(2026, 8, 3), state=AttendanceDay.State.PRESENT,
        )
        created = auto_mark_absences(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31), branch=self.branch)
        self.assertEqual(created, 20)
        self.assertTrue(AttendanceDay.objects.filter(
            employee=self.employee, work_date=datetime.date(2026, 8, 3), state=AttendanceDay.State.PRESENT).exists())

    def test_approved_leave_marks_leave_not_absent(self):
        from apps.attendance.services import auto_mark_absences
        from apps.leave.models import LeaveRequest, LeaveType

        leave_type = LeaveType.objects.create(code="ANNUAL", name_ar="سنوية", days_per_year=30)
        LeaveRequest.objects.create(
            employee=self.employee, leave_type=leave_type,
            from_date=datetime.date(2026, 8, 10), to_date=datetime.date(2026, 8, 14),
            days=5, status=LeaveRequest.Status.APPROVED,
        )
        auto_mark_absences(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31), branch=self.branch)
        leave_days = AttendanceDay.objects.filter(
            employee=self.employee, state=AttendanceDay.State.LEAVE).count()
        absent_days = AttendanceDay.objects.filter(
            employee=self.employee, state=AttendanceDay.State.ABSENT).count()
        self.assertEqual(leave_days, 5)
        self.assertEqual(absent_days, 16)

    def test_public_holiday_skipped(self):
        from apps.attendance.services import auto_mark_absences
        from apps.leave.models import PublicHoliday

        PublicHoliday.objects.create(
            branch=self.branch, name_ar="عيد", date=datetime.date(2026, 8, 10),
        )
        created = auto_mark_absences(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31), branch=self.branch)
        # 2026-08-10 إثنين = يوم عمل لكنه عطلة رسمية
        self.assertEqual(created, 20)
