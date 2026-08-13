"""نماذج التدريب (T-032..T-035).

المرجع: docs/03-database-design.md §3.7 + docs/10-roadmap.md v3 (Training).
القواعد:
    BR-TRN-001  التسجيل وحيد لكل (جلسة، موظف) — لا تكرار (unique constraint).
    BR-TRN-002  الاعتماد لا يتجاوز سعة الجلسة.
    BR-TRN-003  شهادة واحدة لكل تسجيل مكتمل، تُصدر عند إكمال الجلسة.
    BR-TRN-004  الجلسات الملغاة تُحوّل تسجيلاتها إلى "فاشل" بدون شهادة.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class TrainingCourse(BaseModel):
    """T-032 — دورة تدريبية (عنوان ثلاثي اللغات + فئة + مزوّد)."""

    code = models.CharField(_("رمز الدورة"), max_length=30, unique=True)
    title_ar = models.CharField(_("العنوان (عربي)"), max_length=200)
    title_fr = models.CharField(_("العنوان (فرنسي)"), max_length=200, blank=True)
    title_en = models.CharField(_("العنوان (إنجليزي)"), max_length=200, blank=True)
    description = models.TextField(_("الوصف"), blank=True)
    category = models.CharField(_("الفئة"), max_length=50, blank=True)
    provider = models.CharField(_("المزوّد"), max_length=100, blank=True)
    cost = models.DecimalField(_("التكلفة"), max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("دورة تدريبية")
        verbose_name_plural = _("الدورات التدريبية")
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} — {self.title_ar}"


class TrainingSession(BaseModel):
    """T-033 — جلسة تدريبية لدورة (مواعيد + مدرب + سعة + حالة)."""

    class Status(models.TextChoices):
        PLANNED = "planned", _("مجدولة")
        RUNNING = "running", _("قيد التنفيذ")
        COMPLETED = "completed", _("مكتملة")
        CANCELLED = "cancelled", _("ملغاة")

    course = models.ForeignKey(
        TrainingCourse,
        verbose_name=_("الدورة"),
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    start_date = models.DateField(_("تاريخ البدء"))
    end_date = models.DateField(_("تاريخ الانتهاء"))
    trainer = models.CharField(_("المدرب"), max_length=100, blank=True)
    location = models.CharField(_("المكان"), max_length=100, blank=True)
    capacity = models.PositiveSmallIntegerField(_("السعة"), default=20)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.PLANNED)

    class Meta:
        verbose_name = _("جلسة تدريبية")
        verbose_name_plural = _("الجلسات التدريبية")
        ordering = ("-start_date",)

    def __str__(self):
        return f"{self.course.code} — {self.start_date}"

    @property
    def enrolled_count(self):
        return self.enrollments.filter(
            status__in=[TrainingEnrollment.Status.APPROVED, TrainingEnrollment.Status.COMPLETED]
        ).count()

    @property
    def seats_left(self):
        return max(0, self.capacity - self.enrolled_count)


class TrainingEnrollment(BaseModel):
    """T-034 — تسجيل موظف في جلسة (حالة + معتمِد)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("قيد الانتظار")
        APPROVED = "approved", _("معتمد")
        COMPLETED = "completed", _("مكتمل")
        FAILED = "failed", _("فاشل")

    session = models.ForeignKey(
        TrainingSession,
        verbose_name=_("الجلسة"),
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("الموظف"),
        on_delete=models.CASCADE,
        related_name="training_enrollments",
    )
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("اعتمده"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    approved_at = models.DateTimeField(_("وقت الاعتماد"), null=True, blank=True)

    class Meta:
        verbose_name = _("تسجيل تدريبي")
        verbose_name_plural = _("التسجيلات التدريبية")
        ordering = ("session__start_date", "employee__employee_code")
        constraints = [
            models.UniqueConstraint(fields=["session", "employee"], name="uniq_training_enrollment_session_employee"),
        ]

    def __str__(self):
        return f"{self.employee} — {self.session}"


class TrainingCertificate(BaseModel):
    """T-035 — شهادة إتمام تصدر عند إكمال الجلسة (واحدة لكل تسجيل)."""

    enrollment = models.OneToOneField(
        TrainingEnrollment,
        verbose_name=_("التسجيل"),
        on_delete=models.CASCADE,
        related_name="certificate",
    )
    title = models.CharField(_("العنوان"), max_length=200)
    issued_date = models.DateField(_("تاريخ الإصدار"))
    file_path = models.CharField(_("مسار الملف"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("شهادة تدريب")
        verbose_name_plural = _("شهادات التدريب")
        ordering = ("-issued_date",)

    def __str__(self):
        return f"{self.title} — {self.enrollment.employee}"
