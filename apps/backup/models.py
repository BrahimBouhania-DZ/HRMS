"""نماذج النسخ الاحتياطي والاستعادة (v2).

المرجع: docs/09-security.md §7 (Backup & Restore) + docs/10-roadmap.md v2.
- BackupSettings: إعدادات وحيدة (singleton) للجدولة والاحتفاظ والوجهة.
- BackupJob: سجل كل نسخة (نجاح/فشل + checksum + تشفير) — للتدقيق والإشعارات.
- RestoreJob: سجل عمليات الاستعادة (اختبار استعادة شهري إلزامي).
"""

import hashlib
import json

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as _


class BackupSettings(models.Model):
    """T-044 — إعدادات النسخ الاحتياطي (سجل وحيد).

    الوجهة الافتراضية: <BASE_DIR>/backups (تُنشأ تلقائيًا).
    المفتاح يُقرأ من البيئة (HRMS_BACKUP_KEY) — ولا يُخزَّن في قاعدة البيانات.
    """

    enabled = models.BooleanField(_("تفعيل النسخ التلقائي"), default=True)
    backup_dir = models.CharField(_("مجلد الوجهة"), max_length=400, default="backups")
    retention_count = models.PositiveIntegerField(_("عدد النسخ المحتفَظ بها"), default=14)
    encrypt = models.BooleanField(_("تشفير النسخ (AES-256-GCM)"), default=True)
    notify_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("مستخدم الإشعارات (IT)"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_notify",
        help_text=_("يُرسل إليه إشعار نجاح/فشل النسخ"),
    )
    updated_at = models.DateTimeField(_("آخر تحديث"), auto_now=True)

    class Meta:
        verbose_name = _("إعداد النسخ الاحتياطي")
        verbose_name_plural = _("إعدادات النسخ الاحتياطي")

    def __str__(self):
        return _("إعداد النسخ الاحتياطي")

    @classmethod
    def get_default(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BackupJob(models.Model):
    """T-045 — سجل تشغيل نسخة احتياطية (لقطة تلقائية/يدوية)."""

    class Kind(models.TextChoices):
        MANUAL = "manual", _("يدوي")
        DAILY = "daily", _("يومي")
        WEEKLY = "weekly", _("أسبوعي")

    class Status(models.TextChoices):
        RUNNING = "running", _("قيد التشغيل")
        SUCCESS = "success", _("نجحت")
        FAILED = "failed", _("فشلت")

    kind = models.CharField(_("النوع"), max_length=10, choices=Kind.choices, default=Kind.MANUAL)
    status = models.CharField(_("الحالة"), max_length=10, choices=Status.choices, default=Status.RUNNING)
    file_path = models.CharField(_("ملف النسخة"), max_length=500, blank=True)
    file_size = models.PositiveBigIntegerField(_("الحجم (بايت)"), default=0)
    checksum = models.CharField(_("SHA-256"), max_length=64, blank=True)
    encrypted = models.BooleanField(_("مشفرة"), default=False)
    error = models.TextField(_("الخطأ"), blank=True)
    started_at = models.DateTimeField(_("بداية"), default=timezone.now)
    finished_at = models.DateTimeField(_("النهاية"), null=True, blank=True)
    duration_seconds = models.FloatField(_("المدة (ثواني)"), default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("من قِبَل"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backup_jobs",
    )

    class Meta:
        verbose_name = _("سجل نسخة")
        verbose_name_plural = _("سجل النسخ")
        ordering = ("-started_at",)

    def __str__(self):
        return f"{self.get_kind_display()} @ {self.started_at:%Y-%m-%d %H:%M} — {self.get_status_display()}"


class RestoreJob(models.Model):
    """T-046 — سجل عملية استعادة (اختبار استعادة شهري إلزامي).

    يسجَّل كل restore ناجح/فاشل مع التحقق من checksum للتدقيق (audit_restorejob).
    """

    class Status(models.TextChoices):
        SUCCESS = "success", _("نجحت")
        FAILED = "failed", _("فشلت")

    source_file = models.CharField(_("ملف المصدر"), max_length=500)
    checksum_verified = models.BooleanField(_("تم التحقق من checksum"), default=False)
    status = models.CharField(
        _("الحالة"), max_length=10, choices=Status.choices, default=Status.FAILED
    )
    error = models.TextField(_("الخطأ"), blank=True)
    restored_at = models.DateTimeField(_("وقت الاستعادة"), default=timezone.now)
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("من قِبَل"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restore_jobs",
    )

    class Meta:
        verbose_name = _("سجل استعادة")
        verbose_name_plural = _("سجل الاستعادة")
        ordering = ("-restored_at",)

    def __str__(self):
        return f"{self.source_file} — {self.get_status_display()}"
