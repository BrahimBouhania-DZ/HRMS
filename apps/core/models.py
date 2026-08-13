"""نموذج أساسي مشترك (T-019)."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """يضيف created_at/updated_at لكل نموذج يرثه."""

    created_at = models.DateTimeField(_("أُنشئ في"), auto_now_add=True)
    updated_at = models.DateTimeField(_("حُدّث في"), auto_now=True)

    class Meta:
        abstract = True


class BaseModel(TimeStampedModel):
    """TimeStamped + تتبع من أنشأ/عدّل (أمني — 09-security.md)."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("أنشأه"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("حدّثه"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True


class CompanySettings(models.Model):
    """T-020 — هوية الشركة (الاسم + الشعار) لإظهارها في رأس الموقع وطباعة البطاقات.

    سجل وحيد (singleton): يُنشأ افتراضيًا عبر seed_branding مع شعار مبدئي،
    ويمكن تعديله من لوحة الإدارة (العلامة التجارية).
    """

    company_name_ar = models.CharField(_("اسم الشركة (عربي)"), max_length=200, default="HRMS")
    company_name_fr = models.CharField(_("اسم الشركة (فرنسي)"), max_length=200, blank=True)
    company_name_en = models.CharField(_("اسم الشركة (إنجليزي)"), max_length=200, blank=True)
    tagline = models.CharField(_("الشعار النصي"), max_length=300, blank=True, default=_("نظام إدارة الموارد البشرية"))
    logo = models.ImageField(_("شعار الشركة"), upload_to="branding/", null=True, blank=True)
    show_logo_watermark = models.BooleanField(
        _("إظهار الشعار في خلفية ورقة طباعة البطاقات"),
        default=True,
    )
    watermark_opacity = models.PositiveSmallIntegerField(
        _("شفافية الشعار في الخلفية (٪)"),
        default=8,
        help_text=_("قيمة من 0 (شفاف تمامًا) إلى 100 (واضح)"),
    )

    class Meta:
        verbose_name = _("هوية الشركة")
        verbose_name_plural = _("هوية الشركة")

    def __str__(self):
        return self.company_name_ar

    @classmethod
    def get_default(cls):
        """أول سجل (يُستخدم في المعالج العام للقوالب)."""
        return cls.objects.first()


class AuditLog(models.Model):
    """T-021 — سجل تدقيق عام (append-only): كل عملية كتابة عبر الإشارات.

    لا يُحذف ولا يُعدَّل (delete() مرفوع استثناء، والإدارة للقراءة فقط).
    المرجع: docs/09-security.md + docs/10-roadmap.md v2 (Audit).
    """

    class Action(models.TextChoices):
        CREATE = "create", _("إضافة")
        UPDATE = "update", _("تعديل")
        DELETE = "delete", _("حذف")
        LOGIN = "login", _("دخول")
        LOGOUT = "logout", _("خروج")
        EXPORT = "export", _("تصدير")
        IMPORT = "import", _("استيراد")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("المستخدم"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    action = models.CharField(_("الإجراء"), max_length=20, choices=Action.choices)
    model_name = models.CharField(_("النموذج"), max_length=150, blank=True)
    object_id = models.CharField(_("المعرّف"), max_length=50, blank=True)
    object_repr = models.CharField(_("الوصف"), max_length=255, blank=True)
    detail = models.TextField(_("التفاصيل"), blank=True)
    ip = models.GenericIPAddressField(_("العنوان IP"), null=True, blank=True)
    created_at = models.DateTimeField(_("في"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تدقيق")
        verbose_name_plural = _("سجل التدقيق")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["model_name", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def delete(self, *args, **kwargs):
        raise NotImplementedError(_("سجل التدقيق غير قابل للحذف (append-only)"))

    def __str__(self):
        return f"{self.action} {self.model_name} #{self.object_id} — {self.user or 'نظام'}"
