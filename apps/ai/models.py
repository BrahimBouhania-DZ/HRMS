"""نماذج وحدة الذكاء الاصطناعي (T-052..T-054).

المرجع: docs/03-database-design.md §3.13 + docs/07-ai-module.md.
    T-052 ai_aiquery       سجل كل سؤال/إجابة (تدقيق كامل — أمني).
    T-053 ai_analyticsjob  نتائج التحليلات المجدولة (status/result_json).
    T-054 ai_prediction    تنبؤات (احتمال + خصائص + إصدار النموذج).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AIQuery(models.Model):
    """T-052 — سؤال مستخدم وإجابته (قراءة فقط للتدقيق)."""

    class Meta:
        verbose_name = _("سؤال ذكي")
        verbose_name_plural = _("الأسئلة الذكية")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("المستخدم"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_queries",
    )
    prompt = models.TextField(_("السؤال"))
    answer_json = models.JSONField(_("الإجابة (JSON)"), default=dict, blank=True)
    language = models.CharField(_("اللغة"), max_length=5, default="ar")
    was_helpful = models.BooleanField(_("مفيدة؟"), null=True, blank=True,
                                      help_text=_("تقييم المستخدم (نعم/لا) — يدخل في حلقة تحسين المساعد"))
    analytics_ref = models.CharField(_("مرجع تحليلي"), max_length=100, blank=True)
    created_at = models.DateTimeField(_("في"), auto_now_add=True)

    def __str__(self):
        return f"{self.user or '?'} — {self.prompt[:50]}"


class AnalyticsJob(models.Model):
    """T-053 — مهمة تحليل (نتيجة JSON قابلة للتحويل إلى جداول/رسوم)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("بانتظار التنفيذ")
        RUNNING = "running", _("قيد التنفيذ")
        DONE = "done", _("مكتمل")
        FAILED = "failed", _("فشل")

    class Meta:
        verbose_name = _("مهمة تحليل")
        verbose_name_plural = _("مهام التحليل")
        ordering = ("-created_at",)

    analysis_type = models.CharField(
        _("نوع التحليل"),
        max_length=50,
        choices=[
            ("kpi_dashboard", _("لوحة المؤشرات")),
            ("absence", _("الغياب")),
            ("attendance", _("الحضور")),
            ("performance", _("الأداء")),
            ("payroll", _("الرواتب")),
            ("turnover", _("التنقل الوظيفي")),
            ("productivity", _("الإنتاجية")),
        ],
    )
    period_start = models.DateField(_("بداية الفترة"), null=True, blank=True)
    period_end = models.DateField(_("نهاية الفترة"), null=True, blank=True)
    scope_json = models.JSONField(_("النطاق (JSON)"), default=dict, blank=True)
    result_json = models.JSONField(_("النتيجة (JSON)"), default=dict, blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(_("الخطأ"), blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("طلبها"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(_("أُنشئت في"), auto_now_add=True)

    def __str__(self):
        return f"{self.get_analysis_type_display()} — {self.status}"


class AIPrediction(models.Model):
    """T-054 — تنبؤ (احتمال + خصائص + إصدار النموذج)."""

    class Type(models.TextChoices):
        RESIGNATION = "resignation", _("مخاطر الاستقالة")
        ABSENCE_RISK = "absence_risk", _("مخاطر الغياب")

    class Meta:
        verbose_name = _("تنبؤ ذكي")
        verbose_name_plural = _("التنبؤات الذكية")
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "prediction_type"],
                name="uniq_ai_prediction_employee_type",
            )
        ]

    employee = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("الموظف"),
        on_delete=models.CASCADE,
        related_name="ai_predictions",
    )
    prediction_type = models.CharField(
        _("نوع التنبؤ"),
        max_length=20,
        choices=Type.choices,
        default=Type.RESIGNATION,
    )
    probability = models.DecimalField(_("الاحتمال"), max_digits=4, decimal_places=3)
    level = models.CharField(
        _("المستوى"),
        max_length=20,
        choices=[
            ("low", _("منخفض")),
            ("medium", _("متوسط")),
            ("high", _("مرتفع")),
        ],
        default="low",
    )
    features_json = models.JSONField(_("الخصائص (JSON)"), default=dict, blank=True)
    model_version = models.CharField(_("إصدار النموذج"), max_length=20, blank=True)
    created_at = models.DateTimeField(_("أُنشئ في"), auto_now_add=True)

    def __str__(self):
        return f"{self.employee} — {self.get_prediction_type_display()} {self.probability}"
