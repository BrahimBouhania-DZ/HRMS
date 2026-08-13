"""اختبارات وحدة التدريب (T-032..T-035, v3).

يغطي: تسجيل فريد (BR-TRN-001)، سعة الاعتماد (BR-TRN-002)،
إصدار الشهادات عند إكمال الجلسة (BR-TRN-003)، إلغاء الجلسة (BR-TRN-004)،
والصلاحيات عبر العروض.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.auth_app.models import Permission, Role, RoleMember
from apps.employees.models import Employee
from apps.training.models import TrainingCertificate, TrainingCourse, TrainingEnrollment, TrainingSession
from apps.training.services import (
    TrainingError,
    approve_enrollment,
    cancel_session,
    complete_session,
    enroll_employee,
    reject_enrollment,
)

User = get_user_model()


def _employee(code="TR-001", **kw):
    defaults = {
        "employee_code": code,
        "first_name_ar": "تدريب",
        "last_name_ar": code,
        "hire_date": datetime.date(2024, 1, 1),
    }
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def _course(**kw):
    defaults = {"code": "CRS-01", "title_ar": "إدارة الوقت"}
    defaults.update(kw)
    return TrainingCourse.objects.create(**defaults)


def _session(course=None, **kw):
    defaults = {
        "course": course or _course(),
        "start_date": datetime.date(2026, 6, 1),
        "end_date": datetime.date(2026, 6, 5),
        "capacity": 5,
    }
    defaults.update(kw)
    return TrainingSession.objects.create(**defaults)


def _permission(code):
    return Permission.objects.get_or_create(code=code, defaults={"module": "training", "name_ar": code})[0]


def _user_with_role(username, *permission_codes, role_code="hr_manager"):
    role = Role.objects.create(code=role_code, name_ar=role_code, is_system=True)
    for code in permission_codes:
        role.permission_links.create(permission=_permission(code))
    user = User.objects.create_user(username=username, password="pass")
    RoleMember.objects.create(user=user, role=role)
    return user


class TrainingServiceTests(TestCase):
    def setUp(self):
        self.course = _course()
        self.session = _session(course=self.course)
        self.emp = _employee()
        self.user = User.objects.create_user(username="mgr", password="pass")

    def test_enroll_creates_pending_and_is_unique(self):
        enroll_employee(self.session, self.emp, user=self.user)
        enrollment = TrainingEnrollment.objects.get()
        self.assertEqual(enrollment.status, TrainingEnrollment.Status.PENDING)
        enroll_employee(self.session, self.emp)
        self.assertEqual(TrainingEnrollment.objects.count(), 1)

    def test_enroll_rejected_on_completed_session(self):
        self.session.status = TrainingSession.Status.COMPLETED
        self.session.save()
        with self.assertRaises(TrainingError):
            enroll_employee(self.session, self.emp)

    def test_approve_moves_to_approved(self):
        enrollment = enroll_employee(self.session, self.emp, user=self.user)
        approve_enrollment(enrollment, user=self.user)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, TrainingEnrollment.Status.APPROVED)
        self.assertEqual(enrollment.approved_by, self.user)
        self.assertIsNotNone(enrollment.approved_at)

    def test_approve_when_full_raises(self):
        for i in range(self.session.capacity):
            e = _employee(code=f"TR-F{i}")
            en = enroll_employee(self.session, e)
            approve_enrollment(en, user=self.user)
        extra = enroll_employee(self.session, _employee(code="TR-EXTRA"))
        with self.assertRaises(TrainingError):
            approve_enrollment(extra, user=self.user)
        extra.refresh_from_db()
        self.assertEqual(extra.status, TrainingEnrollment.Status.PENDING)

    def test_approve_non_pending_raises(self):
        enrollment = enroll_employee(self.session, self.emp)
        reject_enrollment(enrollment, user=self.user)
        with self.assertRaises(TrainingError):
            approve_enrollment(enrollment, user=self.user)

    def test_reject_sets_failed(self):
        enrollment = enroll_employee(self.session, self.emp)
        reject_enrollment(enrollment, user=self.user)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, TrainingEnrollment.Status.FAILED)

    def test_complete_session_issues_certificates(self):
        en1 = enroll_employee(self.session, self.emp)
        en2 = enroll_employee(self.session, _employee(code="TR-002"))
        approve_enrollment(en1, user=self.user)
        approve_enrollment(en2, user=self.user)
        count = complete_session(self.session, user=self.user)
        self.assertEqual(count, 2)
        self.assertEqual(TrainingCertificate.objects.count(), 2)
        en1.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(en1.status, TrainingEnrollment.Status.COMPLETED)
        self.assertEqual(self.session.status, TrainingSession.Status.COMPLETED)
        cert = en1.certificate
        self.assertEqual(cert.enrollment, en1)
        self.assertEqual(cert.title, "شهادة إتمام: إدارة الوقت — 2026-06-01")

    def test_complete_session_is_idempotent_per_certificate(self):
        en1 = enroll_employee(self.session, self.emp)
        approve_enrollment(en1, user=self.user)
        complete_session(self.session, user=self.user)
        with self.assertRaises(TrainingError):
            complete_session(self.session, user=self.user)
        self.assertEqual(TrainingCertificate.objects.count(), 1)

    def test_cancel_session_fails_enrollments_no_certificates(self):
        en1 = enroll_employee(self.session, self.emp)
        approve_enrollment(en1, user=self.user)
        updated = cancel_session(self.session, user=self.user)
        self.assertEqual(updated, 1)
        en1.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(en1.status, TrainingEnrollment.Status.FAILED)
        self.assertEqual(self.session.status, TrainingSession.Status.CANCELLED)
        self.assertEqual(TrainingCertificate.objects.count(), 0)

    def test_seats_left(self):
        self.assertEqual(self.session.seats_left, 5)
        enroll_employee(self.session, self.emp)
        self.assertEqual(self.session.seats_left, 5)


class TrainingViewTests(TestCase):
    def setUp(self):
        self.manager = _user_with_role("manager", "training.manage")
        self.emp_manager = _user_with_role("hr", "training.enroll", role_code="employee")
        self.emp = _employee()
        self.course = _course()
        self.session = _session(course=self.course)

    def _enroll_approved(self):
        en = enroll_employee(self.session, self.emp, user=self.manager)
        approve_enrollment(en, user=self.manager)
        return en

    def test_course_list_requires_permission(self):
        response = self.client.get(reverse("training:course_list"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.manager)
        response = self.client.get(reverse("training:course_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course.title_ar)

    def test_course_create(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("training:course_create"),
            {"code": "CRS-02", "title_ar": "لغة فرنسية"},
        )
        self.assertRedirects(response, reverse("training:course_list"))
        self.assertTrue(TrainingCourse.objects.filter(code="CRS-02").exists())

    def test_enroll_via_view(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("training:session_enroll", args=[self.session.pk]),
            {"employee_ids": [self.emp.pk]},
        )
        self.assertRedirects(response, reverse("training:session_detail", args=[self.session.pk]))
        self.assertTrue(TrainingEnrollment.objects.filter(session=self.session, employee=self.emp).exists())

    def test_approve_via_view(self):
        en = enroll_employee(self.session, self.emp, user=self.manager)
        self.client.force_login(self.manager)
        response = self.client.post(reverse("training:enroll_approve", args=[self.session.pk, en.pk]))
        self.assertRedirects(response, reverse("training:session_detail", args=[self.session.pk]))
        en.refresh_from_db()
        self.assertEqual(en.status, TrainingEnrollment.Status.APPROVED)

    def test_complete_via_view(self):
        self._enroll_approved()
        self.client.force_login(self.manager)
        response = self.client.post(reverse("training:session_complete", args=[self.session.pk]))
        self.assertRedirects(response, reverse("training:session_detail", args=[self.session.pk]))
        self.assertEqual(TrainingCertificate.objects.count(), 1)

    def test_my_certificates_scoped_to_employee(self):
        self._enroll_approved()
        complete_session(self.session, user=self.manager)
        self.emp.user = self.emp_manager
        self.emp.save()
        self.client.force_login(self.emp_manager)
        response = self.client.get(reverse("training:my_certificates"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "إدارة الوقت")
