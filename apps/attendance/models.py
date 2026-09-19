"""نماذج الحضور والانصراف (T-019..T-021).

المرجع: docs/03-database-design.md §3.4 + docs/06-qr-system.md.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class AttendanceDay(BaseModel):
    """T-019 — نتيجة يوم حضور موظف (UNIQUE employee+work_date)."""

    class State(models.TextChoices):
        PRESENT = "present", _("حاضر")
        ABSENT = "absent", _("غائب")
        LEAVE = "leave", _("إجازة")
        MISSION = "mission", _("مأمورية")
        EXCEPTION = "exception", _("استثناء")
        WEEKEND = "weekend", _("عطلة")

    employee = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("الموظف"),
        on_delete=models.PROTECT,
        related_name="attendance_days",
    )
    work_date = models.DateField(_("تاريخ العمل"))
    shift = models.ForeignKey(
        "org.Shift",
        verbose_name=_("جدول الدوام"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    branch = models.ForeignKey(
        "org.Branch",
        verbose_name=_("الفرع"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    state = models.CharField(_("الحالة"), max_length=20, choices=State.choices, default=State.PRESENT)
    check_in = models.DateTimeField(_("دخول"), null=True, blank=True)
    check_out = models.DateTimeField(_("خروج"), null=True, blank=True)
    worked_minutes = models.PositiveSmallIntegerField(_("دقائق العمل"), default=0)
    late_minutes = models.PositiveSmallIntegerField(_("دقائق التأخير"), default=0)
    early_minutes = models.PositiveSmallIntegerField(_("دقائق الخروج المبكر"), default=0)
    overtime_minutes = models.PositiveSmallIntegerField(_("دقائق إضافية"), default=0)
    is_corrected = models.BooleanField(_("مُصحّح"), default=False)

    class Meta:
        verbose_name = _("يوم حضور")
        verbose_name_plural = _("أيام الحضور")
        unique_together = ("employee", "work_date")
        indexes = [
            models.Index(fields=["work_date"]),
            models.Index(fields=["branch", "work_date"]),
        ]

    def __str__(self):
        return f"{self.employee} — {self.work_date}"


class AttendanceScan(BaseModel):
    """T-020 — كل عملية مسح QR (قرار + مصدر + سبب)."""

    class Source(models.TextChoices):
        PHONE = "phone", _("هاتف")
        FIXED_READER = "fixed_reader", _("قارئ ثابت")
        MANUAL = "manual", _("يدوي")

    class Decision(models.TextChoices):
        CHECK_IN = "check_in", _("دخول")
        CHECK_OUT = "check_out", _("خروج")
        REJECTED = "rejected", _("مرفوض")
        WARNING = "warning", _("تحذير")

    attendanceday = models.ForeignKey(
        AttendanceDay,
        verbose_name=_("يوم الحضور"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scans",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("الموظف"),
        on_delete=models.PROTECT,
        related_name="scans",
    )
    scanned_at = models.DateTimeField(_("زمن المسح"), default=timezone.now)
    source = models.CharField(_("المصدر"), max_length=20, choices=Source.choices, default=Source.PHONE)
    device = models.ForeignKey(
        "devices.QrDevice",
        verbose_name=_("الجهاز"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scans",
    )
    ip_address = models.GenericIPAddressField(_("عنوان IP"), null=True, blank=True)
    decision = models.CharField(_("القرار"), max_length=20, choices=Decision.choices)
    qr_version = models.PositiveSmallIntegerField(_("إصدار QR"), default=1)
    result_detail = models.CharField(_("السبب/النتيجة"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("عملية مسح")
        verbose_name_plural = _("عمليات المسح")
        indexes = [
            models.Index(fields=["employee", "-scanned_at"]),
            models.Index(fields=["scanned_at"]),
        ]

    def __str__(self):
        return f"{self.employee} — {self.decision} @ {self.scanned_at}"


class AttendanceException(BaseModel):
    """T-021 — إذن/مأمورية/تعويض/تصحيح."""

    class Type(models.TextChoices):
        PERMISSION = "permission", _("إذن")
        MISSION = "mission", _("مأمورية")
        COMPENSATORY = "compensatory", _("تعويض")
        CORRECTION = "correction", _("تصحيح")

    class Status(models.TextChoices):
        PENDING = "pending", _("قيد الانتظار")
        APPROVED = "approved", _("معتمد")
        REJECTED = "rejected", _("مرفوض")

    employee = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("الموظف"),
        on_delete=models.PROTECT,
        related_name="attendance_exceptions",
    )
    attendanceday = models.ForeignKey(
        AttendanceDay,
        verbose_name=_("يوم الحضور"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exceptions",
    )
    type = models.CharField(_("النوع"), max_length=20, choices=Type.choices, default=Type.PERMISSION)
    from_time = models.DateTimeField(_("من"))
    to_time = models.DateTimeField(_("إلى"))
    hours = models.DecimalField(_("الساعات"), max_digits=5, decimal_places=2, default=0)
    reason = models.TextField(_("السبب"), blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("الطالب"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("المعتمد"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("استثناء حضور")
        verbose_name_plural = _("استثناءات الحضور")

    def __str__(self):
        return f"{self.employee} — {self.get_type_display()}"
