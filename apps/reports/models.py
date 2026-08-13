"""نماذج التقارير المجدولة (T-049..T-051).

المرجع: docs/03-database-design.md §3.12 + docs/08-reports.md §5.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class ReportDefinition(BaseModel):
    """T-049 — تعريف تقرير مجدول (قالب + فلاتر + جدولة)."""

    class Template(models.TextChoices):
        PDF = "pdf", _("PDF")
        XLSX = "xlsx", _("Excel")
        CSV = "csv", _("CSV")

    class Schedule(models.TextChoices):
        MANUAL = "manual", _("يدوي")
        DAILY = "daily", _("يومي")
        WEEKLY = "weekly", _("أسبوعي")
        MONTHLY = "monthly", _("شهري")

    code = models.CharField(_("رمز التقرير"), max_length=50, unique=True)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    template_type = models.CharField(_("الصيغة"), max_length=10, choices=Template.choices, default=Template.PDF)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("المالك"), on_delete=models.PROTECT, related_name="report_definitions"
    )
    filters_json = models.JSONField(_("الفلاتر"), default=dict, blank=True)
    is_shared = models.BooleanField(_("مشترك"), default=False)

    schedule = models.CharField(_("الجدولة"), max_length=10, choices=Schedule.choices, default=Schedule.MANUAL)
    run_at = models.TimeField(_("وقت التنفيذ"), null=True, blank=True)
    weekday = models.PositiveSmallIntegerField(_("يوم الأسبوع (0=الأحد)"), null=True, blank=True)
    day_of_month = models.PositiveSmallIntegerField(_("يوم الشهر (1-31)"), null=True, blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    last_run_at = models.DateTimeField(_("آخر تنفيذ"), null=True, blank=True)

    notify_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_("مستلمو الإشعار"), blank=True, related_name="scheduled_reports"
    )
    notify_roles = models.ManyToManyField(
        "auth_app.Role", verbose_name=_("أدوار المستلمين"), blank=True, related_name="scheduled_reports"
    )

    class Meta:
        verbose_name = _("تقرير مجدول")
        verbose_name_plural = _("التقارير المجدولة")

    def __str__(self):
        return f"{self.name_ar} ({self.code})"


class ReportJob(BaseModel):
    """T-050 — تنفيذ لتقرير (نتيجة تنفيذ دوري أو يدوي)."""

    class Status(models.TextChoices):
        QUEUED = "queued", _("في الانتظار")
        RUNNING = "running", _("قيد التنفيذ")
        DONE = "done", _("مكتمل")
        FAILED = "failed", _("فشل")

    report = models.ForeignKey(ReportDefinition, verbose_name=_("التقرير"), on_delete=models.CASCADE, related_name="jobs")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("طلب التنفيذ"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="report_jobs",
    )
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(_("البداية"), null=True, blank=True)
    finished_at = models.DateTimeField(_("النهاية"), null=True, blank=True)
    error = models.TextField(_("الخطأ"), blank=True)

    class Meta:
        verbose_name = _("تنفيذ تقرير")
        verbose_name_plural = _("تنفيذات التقارير")
        ordering = ("-started_at",)

    def __str__(self):
        return f"{self.report} — {self.get_status_display()}"


class ReportGeneratedFile(models.Model):
    """T-051 — ملف ناتج عن تنفيذ تقرير."""

    job = models.ForeignKey(ReportJob, verbose_name=_("التنفيذ"), on_delete=models.CASCADE, related_name="files")
    file_path = models.CharField(_("المسار"), max_length=500)
    format = models.CharField(_("الصيغة"), max_length=10)
    size_bytes = models.BigIntegerField(_("الحجم (بايت)"), default=0)
    expires_at = models.DateTimeField(_("انتهاء الصلاحية"), null=True, blank=True)
    created_at = models.DateTimeField(_("أُنشئ في"), auto_now_add=True)

    class Meta:
        verbose_name = _("ملف تقرير")
        verbose_name_plural = _("ملفات التقارير")

    def __str__(self):
        return self.file_path
