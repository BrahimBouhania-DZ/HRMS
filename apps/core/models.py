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
