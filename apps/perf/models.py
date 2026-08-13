"""نماذج تقييم الأداء (T-036..T-040).

المرجع: docs/03-database-design.md §3.8 + docs/10-roadmap.md v2 (Performance).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class PerfCycle(BaseModel):
    """T-036 — دورة تقييم (نصف سنوية/سنوية)."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("مسودة")
        OPEN = "open", _("مفتوحة")
        CLOSED = "closed", _("مغلقة")

    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    period_start = models.DateField(_("بداية الفترة"))
    period_end = models.DateField(_("نهاية الفترة"))
    self_review_deadline = models.DateField(_("آخر موعد للتقييم الذاتي"), null=True, blank=True)
    manager_review_deadline = models.DateField(_("آخر موعد لتقييم المدير"), null=True, blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        verbose_name = _("دورة تقييم")
        verbose_name_plural = _("دورات التقييم")
        ordering = ("-period_start",)

    def __str__(self):
        return self.name_ar


class PerfTemplate(BaseModel):
    """T-037 — قالب تقييم بمعايير مرجّحة (criteria_json)."""

    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    criteria_json = models.JSONField(_("المعايير (بالأوزان)"), default=list, blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("قالب تقييم")
        verbose_name_plural = _("قوالب التقييم")
        ordering = ("name_ar",)

    def __str__(self):
        return self.name_ar


class PerfReview(BaseModel):
    """T-038 — مراجعة تقييم موظف في دورة معينة (تقييم ذاتي + مدير + نهائي)."""

    class Status(models.TextChoices):
        PENDING_SELF = "pending_self", _("بانتظار التقييم الذاتي")
        PENDING_MANAGER = "pending_manager", _("بانتظار تقييم المدير")
        DONE = "done", _("مكتمل")
        CLOSED = "closed", _("مغلق")

    employee = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("الموظف"),
        on_delete=models.CASCADE,
        related_name="perf_reviews",
    )
    cycle = models.ForeignKey(
        PerfCycle,
        verbose_name=_("الدورة"),
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    template = models.ForeignKey(
        PerfTemplate,
        verbose_name=_("القالب"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
    )
    self_score = models.DecimalField(_("درجة التقييم الذاتي"), max_digits=5, decimal_places=2, null=True, blank=True)
    manager_score = models.DecimalField(_("درجة المدير"), max_digits=5, decimal_places=2, null=True, blank=True)
    final_score = models.DecimalField(_("الدرجة النهائية"), max_digits=5, decimal_places=2, null=True, blank=True)
    self_comment = models.TextField(_("تعليق الموظف"), blank=True)
    manager_comment = models.TextField(_("تعليق المدير"), blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.PENDING_SELF)

    class Meta:
        verbose_name = _("مراجعة تقييم")
        verbose_name_plural = _("مراجعات التقييم")
        ordering = ("employee__employee_code",)
        constraints = [
            models.UniqueConstraint(fields=["employee", "cycle"], name="uniq_perf_review_employee_cycle"),
        ]

    def __str__(self):
        return f"{self.employee} — {self.cycle}"


class PerfObjective(BaseModel):
    """T-039 — هدف/KPI ضمن مراجعة (وزن + هدف + محقق + درجة)."""

    review = models.ForeignKey(
        PerfReview,
        verbose_name=_("المراجعة"),
        on_delete=models.CASCADE,
        related_name="objectives",
    )
    kpi_title = models.CharField(_("عنوان الهدف/KPI"), max_length=200)
    weight = models.DecimalField(_("الوزن (٪)"), max_digits=5, decimal_places=2, default=100)
    target = models.DecimalField(_("الهدف"), max_digits=15, decimal_places=2, null=True, blank=True)
    achieved = models.DecimalField(_("المحقق"), max_digits=15, decimal_places=2, null=True, blank=True)
    score = models.DecimalField(_("الدرجة (من 100)"), max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = _("هدف أداء")
        verbose_name_plural = _("أهداف الأداء")
        ordering = ("id",)

    def __str__(self):
        return f"{self.kpi_title} — {self.review}"


class PipPlan(BaseModel):
    """T-040 — خطة تحسين الأداء (PIP) لمراجعة تقييم منخفضة."""

    class Status(models.TextChoices):
        OPEN = "open", _("مفتوحة")
        CLOSED = "closed", _("مغلقة")

    review = models.ForeignKey(
        PerfReview,
        verbose_name=_("المراجعة"),
        on_delete=models.CASCADE,
        related_name="pip_plans",
    )
    start_date = models.DateField(_("تاريخ البدء"))
    end_date = models.DateField(_("تاريخ الانتهاء"))
    action_items = models.TextField(_("بنود التحسين"))
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.OPEN)
    supervisor_note = models.TextField(_("ملاحظة المشرف"), blank=True)

    class Meta:
        verbose_name = _("خطة تحسين أداء")
        verbose_name_plural = _("خطط تحسين الأداء")
        ordering = ("-start_date",)

    def __str__(self):
        return f"PIP — {self.review}"
