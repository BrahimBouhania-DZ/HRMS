"""نماذج الإشعارات (T-041..T-043).

المرجع: docs/03-database-design.md §3.9 + docs/10-roadmap.md S4.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """T-041 — إشعار داخل التطبيق (in_app)."""

    class Type(models.TextChoices):
        LEAVE_SUBMITTED = "leave_submitted", _("طلب إجازة جديد")
        LEAVE_APPROVED = "leave_approved", _("اعتماد إجازة")
        LEAVE_REJECTED = "leave_rejected", _("رفض إجازة")
        LEAVE_CANCELLED = "leave_cancelled", _("إلغاء إجازة")
        ATTENDANCE_WARNING = "attendance_warning", _("تنبيه حضور")
        CONTRACT_EXPIRING = "contract_expiring", _("انتهاء عقد")
        DOCUMENT_EXPIRING = "document_expiring", _("انتهاء صلاحية وثيقة")
        PROBATION_END = "probation_end", _("نهاية فترة التجربة")
        SYSTEM = "system", _("نظام")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("المستخدم"),
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(_("النوع"), max_length=30, choices=Type.choices, default=Type.SYSTEM)
    title = models.CharField(_("العنوان"), max_length=200)
    body = models.TextField(_("النص"), blank=True)
    related_model = models.CharField(_("النموذج المرتبط"), max_length=50, blank=True)
    related_id = models.PositiveIntegerField(_("المعرّف المرتبط"), null=True, blank=True)
    is_read = models.BooleanField(_("مقروء"), default=False)
    created_at = models.DateTimeField(_("أُنشئ في"), auto_now_add=True)

    class Meta:
        verbose_name = _("إشعار")
        verbose_name_plural = _("الإشعارات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self):
        return f"{self.user} — {self.title}"


class NotificationPref(models.Model):
    """T-042 — تفضيل قناة لنوع إشعار."""

    class Channel(models.TextChoices):
        IN_APP = "in_app", _("داخل التطبيق")
        EMAIL = "email", _("بريد")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("المستخدم"),
        on_delete=models.CASCADE,
        related_name="notification_prefs",
    )
    type = models.CharField(_("النوع"), max_length=30, choices=Notification.Type.choices)
    channel = models.CharField(_("القناة"), max_length=20, choices=Channel.choices, default=Channel.IN_APP)
    enabled = models.BooleanField(_("مفعّل"), default=True)

    class Meta:
        verbose_name = _("تفضيل إشعار")
        verbose_name_plural = _("تفضيلات الإشعارات")
        unique_together = ("user", "type", "channel")

    def __str__(self):
        return f"{self.user} — {self.type} / {self.channel}: {self.enabled}"


class ScheduledAlert(models.Model):
    """T-043 — تنبيه مؤجّل (تنفيذ v2 عبر مهام خلفية).

    السجل وحيد لكل (alert_type + target_date + reference): يُمنع التكرار
    عبر الجدولة اليومية — كل سجل يمثل تنبيهًا وُلد لموضوع معين.
    """

    alert_type = models.CharField(_("نوع التنبيه"), max_length=30)
    target_date = models.DateField(_("تاريخ الاستهداف"))
    reference = models.CharField(_("المرجع"), max_length=200, default="", blank=True)
    payload_json = models.JSONField(_("الحمولة"), default=dict, blank=True)
    fired_at = models.DateTimeField(_("أُطلق في"), null=True, blank=True)

    class Meta:
        verbose_name = _("تنبيه مؤجل")
        verbose_name_plural = _("التنبيهات المؤجلة")
        constraints = [
            models.UniqueConstraint(
                fields=["alert_type", "target_date", "reference"],
                name="uniq_scheduled_alert",
            ),
        ]

    def __str__(self):
        return f"{self.alert_type} @ {self.target_date} ({self.reference})"
