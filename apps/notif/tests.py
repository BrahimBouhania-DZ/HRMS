"""اختبارات الإشعارات + خطافات دورة الإجازة (S4).

المرجع: docs/03 §3.9 + docs/10-roadmap.md S4.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auth_app.models import Role, RoleMember, User
from apps.employees.models import Contract, Document, Employee
from apps.leave.models import LeaveRequest, LeaveType
from apps.leave.services import approve_request, reject_request, submit_request
from apps.notif.models import Notification, NotificationPref, ScheduledAlert


def make_user(username, is_superuser=False):
    return User.objects.create_user(
        username=username,
        password="Pass1234!",
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )


class NotificationServiceTests(TestCase):
    """إنشاء + تفضيلات + قراءة."""

    def setUp(self):
        self.user = make_user("emp_notif")
        self.hr = make_user("hr_notif")

    def test_notify_creates_in_app(self):
        from apps.notif.services import notify

        n = notify(self.user, Notification.Type.SYSTEM, "عنوان", "نص")
        self.assertEqual(Notification.objects.count(), 1)
        self.assertFalse(n.is_read)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_pref_disabled_blocks_notification(self):
        from apps.notif.services import notify

        NotificationPref.objects.create(
            user=self.user, type=Notification.Type.SYSTEM,
            channel=NotificationPref.Channel.IN_APP, enabled=False,
        )
        n = notify(self.user, Notification.Type.SYSTEM, "عنوان")
        self.assertIsNone(n)
        self.assertEqual(Notification.objects.count(), 0)

    def test_pref_enabled_allows_notification(self):
        from apps.notif.services import notify

        NotificationPref.objects.create(
            user=self.user, type=Notification.Type.SYSTEM,
            channel=NotificationPref.Channel.IN_APP, enabled=True,
        )
        self.assertIsNotNone(notify(self.user, Notification.Type.SYSTEM, "عنوان"))
        self.assertEqual(Notification.objects.count(), 1)

    def test_notify_with_related(self):
        from apps.notif.services import notify

        req = LeaveRequest(id=123)
        n = notify(self.user, Notification.Type.SYSTEM, "عنوان", related=req)
        self.assertEqual(n.related_model, "leaverequest")
        self.assertEqual(n.related_id, 123)

    def test_email_channel_sends_mail_when_enabled(self):
        from django.core import mail
        from django.test import override_settings

        from apps.notif.services import notify

        self.user.email = "emp@lan.local"
        self.user.save(update_fields=["email"])
        with override_settings(HRMS_EMAIL_ENABLED=True):
            notify(self.user, Notification.Type.SYSTEM, "بريد", "نص البريد")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["emp@lan.local"])
        self.assertIn("بريد", mail.outbox[0].subject)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_email_disabled_pref_blocks_mail(self):
        from django.core import mail
        from django.test import override_settings

        from apps.notif.services import notify

        self.user.email = "emp@lan.local"
        self.user.save(update_fields=["email"])
        NotificationPref.objects.create(
            user=self.user, type=Notification.Type.SYSTEM,
            channel=NotificationPref.Channel.EMAIL, enabled=False,
        )
        with override_settings(HRMS_EMAIL_ENABLED=True):
            notify(self.user, Notification.Type.SYSTEM, "بريد")
        self.assertEqual(len(mail.outbox), 0)

    def test_email_not_sent_when_feature_off(self):
        from django.core import mail
        from django.test import override_settings

        from apps.notif.services import notify

        self.user.email = "emp@lan.local"
        self.user.save(update_fields=["email"])
        with override_settings(HRMS_EMAIL_ENABLED=False):
            notify(self.user, Notification.Type.SYSTEM, "بريد")
        self.assertEqual(len(mail.outbox), 0)

    def test_no_email_address_skips_mail(self):
        from django.core import mail
        from django.test import override_settings

        from apps.notif.services import notify

        with override_settings(HRMS_EMAIL_ENABLED=True):
            notify(self.user, Notification.Type.SYSTEM, "بريد")
        self.assertEqual(len(mail.outbox), 0)

    def test_set_pref_and_email_prefs_map(self):
        from apps.notif.services import email_prefs, set_notification_pref

        set_notification_pref(self.user, Notification.Type.SYSTEM,
                              NotificationPref.Channel.EMAIL, False)
        self.assertFalse(email_prefs(self.user)[Notification.Type.SYSTEM])
        self.assertTrue(email_prefs(self.user)[Notification.Type.LEAVE_SUBMITTED])  # افتراضي
        set_notification_pref(self.user, Notification.Type.SYSTEM,
                              NotificationPref.Channel.EMAIL, True)
        self.assertTrue(email_prefs(self.user)[Notification.Type.SYSTEM])


class LeaveNotificationHooksTests(TestCase):
    """خطافات طلب/قرار الإجازة تولّد إشعارات للجهات الصحيحة."""

    def setUp(self):
        self.hr = make_user("hr_hook", is_superuser=True)
        self.emp_user = make_user("emp_hook")
        self.emp = Employee.objects.create(
            employee_code="EMP-N001",
            first_name_ar="علي",
            last_name_ar="محرك",
            hire_date=date(2024, 1, 1),
            user=self.emp_user,
            employment_status=Employee.EmploymentStatus.ACTIVE,
        )
        self.lt = LeaveType.objects.create(
            code="annual", name_ar="سنوية", days_per_year=30,
            requires_approval_levels=1, is_active=True,
        )
        self.approver = self.hr
        self.approver_user = self.hr

    def _days(self, d):
        return date(2026, 1, d)

    def test_submit_notifies_approvers(self):
        req = submit_request(self.emp, self.lt, self._days(4), self._days(7), "سبب", requested_by=self.emp_user)
        n = Notification.objects.filter(user=self.hr, type=Notification.Type.LEAVE_SUBMITTED).first()
        self.assertIsNotNone(n)
        self.assertEqual(n.related_id, req.pk)
        # صاحب الطلب لا يبلغ نفسه
        self.assertFalse(Notification.objects.filter(user=self.emp_user, type=Notification.Type.LEAVE_SUBMITTED).exists())

    def test_submit_only_notifies_potential_approvers(self):
        # مستخدم بلا أدوار ولا is_superuser ليس ضمن المعتمدين → لا يتلقى
        outsider = make_user("outsider")
        req = submit_request(self.emp, self.lt, self._days(4), self._days(7), requested_by=self.emp_user)
        self.assertFalse(
            Notification.objects.filter(user=outsider, type=Notification.Type.LEAVE_SUBMITTED).exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.hr, type=Notification.Type.LEAVE_SUBMITTED).exists()
        )

    def test_approve_notifies_employee(self):
        req = submit_request(self.emp, self.lt, self._days(4), self._days(7), requested_by=self.emp_user)
        approve_request(req, self.approver)
        n = Notification.objects.filter(user=self.emp_user, type=Notification.Type.LEAVE_APPROVED).first()
        self.assertIsNotNone(n)
        self.assertEqual(n.related_id, req.pk)
        self.assertEqual(req.status, LeaveRequest.Status.APPROVED)

    def test_reject_notifies_employee(self):
        req = submit_request(self.emp, self.lt, self._days(4), self._days(7), requested_by=self.emp_user)
        reject_request(req, self.approver)
        n = Notification.objects.filter(user=self.emp_user, type=Notification.Type.LEAVE_REJECTED).first()
        self.assertIsNotNone(n)
        self.assertEqual(req.status, LeaveRequest.Status.REJECTED)

    def test_mark_read_and_mark_all(self):
        from apps.notif.services import mark_all_as_read, mark_as_read, unread_count

        req = submit_request(self.emp, self.lt, self._days(4), self._days(7), requested_by=self.emp_user)
        approve_request(req, self.approver)
        n = Notification.objects.get(user=self.emp_user)
        self.assertEqual(unread_count(self.emp_user), 1)
        mark_as_read(self.emp_user, n.pk)
        self.assertTrue(Notification.objects.get(pk=n.pk).is_read)
        self.assertEqual(unread_count(self.emp_user), 0)
        # جميع
        self.emp_user.notifications.update(is_read=False)
        mark_all_as_read(self.emp_user)
        self.assertEqual(unread_count(self.emp_user), 0)


class NotificationViewTests(TestCase):
    """واجهات مركز الإشعارات."""

    def setUp(self):
        self.hr = make_user("hr_view", is_superuser=True)
        self.emp_user = make_user("emp_view")
        self.emp = Employee.objects.create(
            employee_code="EMP-N003",
            first_name_ar="سالم",
            last_name_ar="واجهة",
            hire_date=date(2024, 1, 1),
            user=self.emp_user,
            employment_status=Employee.EmploymentStatus.ACTIVE,
        )
        self.lt = LeaveType.objects.create(
            code="annual2", name_ar="سنوية", days_per_year=30,
            requires_approval_levels=1, is_active=True,
        )

    def test_list_requires_login(self):
        resp = self.client.get(reverse("notif:list"))
        self.assertEqual(resp.status_code, 302)

    def test_list_shows_only_own(self):
        Notification.objects.create(user=self.hr, title="للـ HR")
        self.client.force_login(self.emp_user)
        resp = self.client.get(reverse("notif:list"))
        self.assertContains(resp, "لا توجد إشعارات بعد")

    def test_mark_read(self):
        self.client.force_login(self.emp_user)
        n = Notification.objects.create(user=self.emp_user, title="عزيزي")
        resp = self.client.post(reverse("notif:mark_read", args=[n.pk]))
        self.assertRedirects(resp, reverse("notif:list"))
        self.assertTrue(Notification.objects.get(pk=n.pk).is_read)

    def test_mark_all_read(self):
        self.client.force_login(self.emp_user)
        Notification.objects.create(user=self.emp_user, title="واحد")
        Notification.objects.create(user=self.emp_user, title="اثنان")
        resp = self.client.post(reverse("notif:mark_all_read"))
        self.assertRedirects(resp, reverse("notif:list"))
        self.assertEqual(Notification.objects.filter(user=self.emp_user, is_read=False).count(), 0)

    def test_mark_read_foreign_denied(self):
        self.client.force_login(self.emp_user)
        n = Notification.objects.create(user=self.hr, title="سرية")
        resp = self.client.post(reverse("notif:mark_read", args=[n.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Notification.objects.get(pk=n.pk).is_read)

    def test_prefs_page_requires_login(self):
        resp = self.client.get(reverse("notif:prefs"))
        self.assertEqual(resp.status_code, 302)

    def test_prefs_page_lists_types(self):
        self.client.force_login(self.emp_user)
        resp = self.client.get(reverse("notif:prefs"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "بريد")

    def test_prefs_save_email_prefs(self):
        from apps.notif.services import email_prefs

        self.client.force_login(self.emp_user)
        resp = self.client.post(reverse("notif:prefs"), {
            "email": [Notification.Type.LEAVE_SUBMITTED, Notification.Type.LEAVE_APPROVED],
        })
        self.assertRedirects(resp, reverse("notif:prefs"))
        prefs = email_prefs(self.emp_user)
        self.assertTrue(prefs[Notification.Type.LEAVE_SUBMITTED])
        self.assertTrue(prefs[Notification.Type.LEAVE_APPROVED])
        self.assertFalse(prefs[Notification.Type.SYSTEM])


class ScheduledAlertScannerTests(TestCase):
    """ماسح التنبيهات المجدولة: عقود/وثائق/تجربة + منع التكرار."""

    def setUp(self):
        self.hr = make_user("hr_alerts", is_superuser=True)
        self.emp_user = make_user("emp_alerts")
        self.emp = Employee.objects.create(
            employee_code="EMP-AL1",
            first_name_ar="تتبع",
            last_name_ar="تنبيهات",
            hire_date=date.today() - timedelta(days=20),
            user=self.emp_user,
            employment_status=Employee.EmploymentStatus.PROBATION,
        )
        self.cdd = Contract.objects.create(
            contract_number="CTR-AL-1",
            employee=self.emp,
            contract_type=Contract.ContractType.CDD,
            start_date=date.today() - timedelta(days=100),
            end_date=date.today() + timedelta(days=10),
            gross_salary=50000,
            base_salary=45000,
        )

    def _doc(self, days=10, title="جواز سفر"):
        return Document.objects.create(
            employee=self.emp,
            document_type="passport",
            title=title,
            file="employees/documents/passport.pdf",
            expiry_date=date.today() + timedelta(days=days),
        )

    def test_contract_expiry_fires_notification(self):
        from apps.notif.scheduler import run_all

        stats = run_all()
        self.assertEqual(stats["contracts"], 1)
        n = Notification.objects.filter(
            user=self.hr, type=Notification.Type.CONTRACT_EXPIRING
        ).first()
        self.assertIsNotNone(n)
        self.assertIn("CTR-AL-1", n.title + n.body)

    def test_document_expiry_fires_notification(self):
        from apps.notif.scheduler import run_all

        self._doc(days=15)
        stats = run_all()
        self.assertEqual(stats["documents"], 1)
        n = Notification.objects.filter(
            user=self.hr, type=Notification.Type.DOCUMENT_EXPIRING
        ).first()
        self.assertIsNotNone(n)

    def test_probation_end_fires_notification(self):
        from apps.notif.scheduler import run_all

        # التجربة انتهت من 90 يومًا؟ اجعل تاريخ التوظيف قريبًا من النهاية
        self.emp.hire_date = date.today() - timedelta(days=85)
        self.emp.save()
        stats = run_all()
        self.assertEqual(stats["probation"], 1)
        n = Notification.objects.filter(
            user=self.hr, type=Notification.Type.PROBATION_END
        ).first()
        self.assertIsNotNone(n)

    def test_idempotent_second_run_fires_nothing(self):
        from apps.notif.scheduler import run_all

        run_all()
        first_alert_count = ScheduledAlert.objects.count()
        first_notif_count = Notification.objects.count()
        stats = run_all()
        self.assertEqual(stats["contracts"], 0)
        self.assertEqual(ScheduledAlert.objects.count(), first_alert_count)
        self.assertEqual(Notification.objects.count(), first_notif_count)

    def test_outside_window_ignored(self):
        from apps.notif.scheduler import run_all

        self.cdd.end_date = date.today() + timedelta(days=90)
        self.cdd.save()
        self._doc(days=90)
        stats = run_all()
        self.assertEqual(stats["contracts"], 0)
        self.assertEqual(stats["documents"], 0)

    def test_expired_contract_ignored(self):
        from apps.notif.scheduler import run_all

        self.cdd.end_date = date.today() - timedelta(days=1)
        self.cdd.save()
        stats = run_all()
        self.assertEqual(stats["contracts"], 0)

    def test_renewed_contract_not_re_alerted(self):
        """عقد استُبدل بعقد تجديد (renewal) لا يولّد تنبيها."""
        from apps.notif.scheduler import run_all

        Contract.objects.create(
            contract_number="CTR-AL-2",
            employee=self.emp,
            contract_type=Contract.ContractType.CDD,
            start_date=date.today() + timedelta(days=11),
            end_date=date.today() + timedelta(days=310),
            gross_salary=50000,
            base_salary=45000,
            previous_contract=self.cdd,
        )
        stats = run_all()
        self.assertEqual(stats["contracts"], 0)
        self.assertFalse(
            ScheduledAlert.objects.filter(alert_type="contract_expiry").exists()
        )

    def test_only_hr_recipients_notified(self):
        """موظف عادي بلا صلاحية HR لا يتلقى تنبيهات الانتهاء."""
        from apps.notif.scheduler import run_all

        outsider = make_user("outsider_alerts")
        run_all()
        self.assertFalse(
            Notification.objects.filter(user=outsider).exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.hr, type=Notification.Type.CONTRACT_EXPIRING).exists()
        )

    def test_dry_run_creates_nothing(self):
        """وضع التجربة يعرض الإحصاء دون إنشاء سجلات أو إشعارات."""
        from apps.notif.scheduler import run_all

        stats = run_all(commit=False)
        self.assertEqual(stats["contracts"], 1)
        self.assertEqual(ScheduledAlert.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_contract_expiry_includes_employee_in_payload(self):
        from apps.notif.scheduler import run_all

        run_all()
        alert = ScheduledAlert.objects.filter(alert_type="contract_expiry").first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.payload_json["contract"], "CTR-AL-1")
        self.assertEqual(alert.payload_json["employee"], str(self.emp))
