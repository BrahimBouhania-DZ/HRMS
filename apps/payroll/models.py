"""نماذج الرواتب (T-027..T-031).

المرجع: docs/03-database-design.md §3.6 + docs/01 §8.6 (BR-PAY) + docs/10-roadmap.md v2.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class PayElement(BaseModel):
    """T-027 — عنصر أجر قابل للتكوين (إضافة/خصم)."""

    class Kind(models.TextChoices):
        EARNING = "earning", _("إضافة")
        DEDUCTION = "deduction", _("خصم")

    class Calculation(models.TextChoices):
        FIXED = "fixed", _("مبلغ ثابت")
        PERCENT_OF_BASIC = "percent_of_basic", _("نسبة من الأساسي")
        ATTENDANCE_BASED = "attendance_based", _("حسب الحضور")

    code = models.CharField(_("الرمز"), max_length=30, unique=True)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    kind = models.CharField(_("النوع"), max_length=10, choices=Kind.choices)
    calculation = models.CharField(_("طريقة الحساب"), max_length=20, choices=Calculation.choices, default=Calculation.FIXED)
    amount = models.DecimalField(_("المبلغ"), max_digits=15, decimal_places=2, default=0)
    percent = models.DecimalField(_("النسبة %"), max_digits=5, decimal_places=2, default=0)
    applies_to_all = models.BooleanField(_("يطبق على الجميع"), default=True)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("عنصر أجر")
        verbose_name_plural = _("عناصر الأجر")

    def __str__(self):
        return self.name_ar


class PayRun(BaseModel):
    """T-028 — دورة رواتب (فترة+فرع) بمسار حالة: draft→reviewing→approved→frozen."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("مسودة")
        REVIEWING = "reviewing", _("قيد المراجعة")
        APPROVED = "approved", _("معتمد")
        FROZEN = "frozen", _("مجمّد")

    period_code = models.CharField(_("فترة الرواتب"), max_length=10, help_text=_("مثال: 2026-08"))
    branch = models.ForeignKey(
        "org.Branch", verbose_name=_("الفرع"), on_delete=models.PROTECT, related_name="pay_runs"
    )
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_earnings = models.DecimalField(_("إجمالي الإضافات"), max_digits=15, decimal_places=2, default=0)
    total_deductions = models.DecimalField(_("إجمالي الخصومات"), max_digits=15, decimal_places=2, default=0)
    total_net = models.DecimalField(_("صافي الإجمالي"), max_digits=15, decimal_places=2, default=0)
    generated_at = models.DateTimeField(_("أُنشئت في"), null=True, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("أنشأها"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="pay_runs_generated",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("اعتمدها"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="pay_runs_approved",
    )
    approved_at = models.DateTimeField(_("وقت الاعتماد"), null=True, blank=True)

    class Meta:
        verbose_name = _("دورة رواتب")
        verbose_name_plural = _("دورات الرواتب")
        constraints = [
            models.UniqueConstraint(fields=["period_code", "branch"], name="uniq_payrun_period_branch")
        ]

    def __str__(self):
        return f"{self.period_code} — {self.branch}"


class PayrollLine(BaseModel):
    """T-029 — سطر عنصر أجر داخل دورة (UNIQUE run+employee+element)."""

    pay_run = models.ForeignKey(PayRun, verbose_name=_("الدورة"), on_delete=models.CASCADE, related_name="lines")
    employee = models.ForeignKey(
        "employees.Employee", verbose_name=_("الموظف"), on_delete=models.CASCADE, related_name="payroll_lines"
    )
    element = models.ForeignKey(
        PayElement, verbose_name=_("العنصر"), null=True, blank=True, on_delete=models.PROTECT, related_name="lines"
    )
    hours = models.DecimalField(_("الساعات"), max_digits=8, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(_("المبلغ"), max_digits=15, decimal_places=2)
    note = models.CharField(_("ملاحظة"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("سطر راتب")
        verbose_name_plural = _("أسطر الرواتب")
        constraints = [
            models.UniqueConstraint(
                fields=["pay_run", "employee", "element"], name="uniq_payrollline_run_emp_elem"
            )
        ]

    def __str__(self):
        return f"{self.employee} — {self.element or self.note}: {self.amount}"


class Payslip(BaseModel):
    """T-030 — قسيمة راتب موظف ضمن دورة (UNIQUE run+employee)."""

    pay_run = models.ForeignKey(PayRun, verbose_name=_("الدورة"), on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey(
        "employees.Employee", verbose_name=_("الموظف"), on_delete=models.CASCADE, related_name="payslips"
    )
    basic_salary = models.DecimalField(_("الأجر الأساسي"), max_digits=15, decimal_places=2)
    total_earnings = models.DecimalField(_("إجمالي الإضافات"), max_digits=15, decimal_places=2)
    total_deductions = models.DecimalField(_("إجمالي الخصومات"), max_digits=15, decimal_places=2)
    net = models.DecimalField(_("الصافي"), max_digits=15, decimal_places=2)
    attended_days = models.PositiveSmallIntegerField(_("أيام الحضور"), default=0)
    absent_days = models.PositiveSmallIntegerField(_("أيام الغياب"), default=0)
    leave_days = models.PositiveSmallIntegerField(_("أيام الإجازة"), default=0)
    overtime_hours = models.DecimalField(_("ساعات إضافية"), max_digits=8, decimal_places=2, default=0)
    bank_export_ref = models.CharField(_("مرجع تصدير البنك"), max_length=100, blank=True)
    pdf_path = models.CharField(_("مسار PDF"), max_length=500, blank=True)
    generated_at = models.DateTimeField(_("أُنشئت في"), auto_now_add=True)

    class Meta:
        verbose_name = _("قسيمة راتب")
        verbose_name_plural = _("قسائم الرواتب")
        constraints = [
            models.UniqueConstraint(fields=["pay_run", "employee"], name="uniq_payslip_run_emp")
        ]

    def __str__(self):
        return f"{self.employee} — {self.pay_run.period_code}: {self.net}"


class EndOfService(BaseModel):
    """T-031 — نهاية خدمة (استقالة/فصل/تقاعد) بأثر مالي."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("مسودة")
        APPROVED = "approved", _("معتمد")
        PAID = "paid", _("مدفوع")

    employee = models.ForeignKey(
        "employees.Employee", verbose_name=_("الموظف"), on_delete=models.CASCADE, related_name="end_of_services"
    )
    termination_date = models.DateField(_("تاريخ النهاية"))
    total_years = models.DecimalField(_("إجمالي السنوات"), max_digits=5, decimal_places=2, default=0)
    service_reward = models.DecimalField(_("مكافأة الخدمة"), max_digits=15, decimal_places=2, default=0)
    unused_leave_comp = models.DecimalField(_("تعويض الإجازات المتبقية"), max_digits=15, decimal_places=2, default=0)
    notice_period = models.DecimalField(_("بدل الإشعار"), max_digits=15, decimal_places=2, default=0)
    deductions = models.DecimalField(_("الخصومات"), max_digits=15, decimal_places=2, default=0)
    net = models.DecimalField(_("الصافي"), max_digits=15, decimal_places=2, default=0)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("اعتمدها"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="eos_approved",
    )

    class Meta:
        verbose_name = _("نهاية خدمة")
        verbose_name_plural = _("نهايات الخدمة")

    def __str__(self):
        return f"{self.employee} — {self.termination_date}"
