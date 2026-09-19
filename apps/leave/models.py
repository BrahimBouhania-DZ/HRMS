"""نماذج الإجازات (T-022..T-026).

المرجع: docs/03-database-design.md §3.5 + docs/10-roadmap.md S4.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class LeaveType(BaseModel):
    """T-022 — نوع الإجازة (تكوين قابل للتغيير)."""

    code = models.CharField(_("الرمز"), max_length=30, unique=True)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    days_per_year = models.PositiveSmallIntegerField(_("أيام السنة"), default=0)
    carryover_allowed = models.BooleanField(_("الترحيل مسموح"), default=False)
    max_carryover_days = models.PositiveSmallIntegerField(_("أقصى ترحيل"), default=0)
    is_unpaid = models.BooleanField(_("غير مدفوعة"), default=False)
    requires_approval_levels = models.PositiveSmallIntegerField(_("مستويات الموافقة"), default=1)
    applicable_to = models.CharField(
        _("تطبق على"),
        max_length=30,
        choices=[("all", _("الجميع")), ("gender_male", _("ذكور")), ("gender_female", _("إناث"))],
        default="all",
    )
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("نوع إجازة")
        verbose_name_plural = _("أنواع الإجازات")

    def __str__(self):
        return self.name_ar


class LeaveBalance(BaseModel):
    """T-023 — رصيد موظف لنوع إجازة في سنة (UNIQUE employee+type+year)."""

    employee = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("الموظف"),
        on_delete=models.CASCADE,
        related_name="leave_balances",
    )
    leave_type = models.ForeignKey(
        LeaveType, verbose_name=_("نوع الإجازة"), on_delete=models.PROTECT, related_name="balances"
    )
    year = models.PositiveSmallIntegerField(_("السنة"))
    granted = models.DecimalField(_("ممنوح"), max_digits=5, decimal_places=1, default=0)
    used = models.DecimalField(_("مستعمل"), max_digits=5, decimal_places=1, default=0)
    carried_from = models.DecimalField(_("مُرحّل من السابق"), max_digits=5, decimal_places=1, default=0)
    adjusted = models.DecimalField(_("تسوية"), max_digits=5, decimal_places=1, default=0)

    class Meta:
        verbose_name = _("رصيد إجازة")
        verbose_name_plural = _("أرصدة الإجازات")
        unique_together = ("employee", "leave_type", "year")

    @property
    def remaining(self) -> float:
        """الرصيد المتاح = ممنوح + مُرحّل + تسوية − مستعمل."""
        total = (
            (self.granted or 0)
            + (self.carried_from or 0)
            + (self.adjusted or 0)
            - (self.used or 0)
        )
        return float(total)

    def __str__(self):
        return _("%s — %s %s (متبقٍ %s)") % (self.employee, self.leave_type, self.year, self.remaining)


class LeaveRequest(BaseModel):
    """T-024 — طلب إجازة."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("مسودة")
        PENDING = "pending", _("قيد الانتظار")
        APPROVED = "approved", _("معتمدة")
        REJECTED = "rejected", _("مرفوضة")
        CANCELLED = "cancelled", _("ملغاة")

    employee = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("الموظف"),
        on_delete=models.PROTECT,
        related_name="leave_requests",
    )
    leave_type = models.ForeignKey(
        LeaveType, verbose_name=_("نوع الإجازة"), on_delete=models.PROTECT, related_name="requests"
    )
    from_date = models.DateField(_("من"))
    to_date = models.DateField(_("إلى"))
    days = models.DecimalField(_("عدد الأيام"), max_digits=5, decimal_places=1, default=0)
    reason = models.TextField(_("السبب"), blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.DRAFT)
    current_level = models.PositiveSmallIntegerField(_("المستوى الحالي"), default=1)
    submitted_at = models.DateTimeField(_("أُرسل في"), null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("الطالب"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("طلب إجازة")
        verbose_name_plural = _("طلبات الإجازات")
        indexes = [
            models.Index(fields=["-submitted_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["employee", "status"]),
        ]

    def __str__(self):
        return f"{self.employee} — {self.leave_type} ({self.from_date}→{self.to_date})"


class LeaveApproval(BaseModel):
    """T-025 — خطوة موافقة في السلسلة (UNIQUE request+level)."""

    class Action(models.TextChoices):
        APPROVED = "approved", _("اعتماد")
        REJECTED = "rejected", _("رفض")
        ESCALATED = "escalated", _("تصعيد")

    leave_request = models.ForeignKey(
        LeaveRequest, verbose_name=_("الطلب"), on_delete=models.CASCADE, related_name="approvals"
    )
    level = models.PositiveSmallIntegerField(_("المستوى"))
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("المعتمد"),
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(_("الإجراء"), max_length=20, choices=Action.choices)
    comment = models.TextField(_("ملاحظة"), blank=True)
    at = models.DateTimeField(_("في"), auto_now_add=True)

    class Meta:
        verbose_name = _("موافقة إجازة")
        verbose_name_plural = _("موافقات الإجازات")
        unique_together = ("leave_request", "level")

    def __str__(self):
        return f"{self.leave_request} — L{self.level} {self.action}"


class PublicHoliday(BaseModel):
    """T-026 — عطلة رسمية (قد تكون متكررة سنويًا)."""

    branch = models.ForeignKey(
        "org.Branch",
        verbose_name=_("الفرع"),
        on_delete=models.CASCADE,
        related_name="public_holidays",
    )
    date = models.DateField(_("التاريخ"))
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    is_recurring = models.BooleanField(_("تتكرر سنويًا"), default=False)

    class Meta:
        verbose_name = _("عطلة رسمية")
        verbose_name_plural = _("العطل الرسمية")
        unique_together = ("branch", "date")

    def __str__(self):
        return f"{self.name_ar} — {self.date}"
