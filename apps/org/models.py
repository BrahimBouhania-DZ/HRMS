"""نماذج الهيكل التنظيمي (T-009..T-012)."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Branch(BaseModel):
    """T-009 — فرع/مقر."""

    code = models.CharField(_("رمز الفرع"), max_length=30, unique=True)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    country = models.CharField(_("الدولة"), max_length=100, blank=True)
    city = models.CharField(_("المدينة"), max_length=100, blank=True)
    address = models.TextField(_("العنوان"), blank=True)
    timezone = models.CharField(_("المنطقة الزمنية"), max_length=64, default="Africa/Algiers", blank=True)

    class Meta:
        verbose_name = _("فرع")
        verbose_name_plural = _("الفروع")

    def __str__(self):
        return self.name_ar


class Department(BaseModel):
    """T-010 — قسم (بنيوي: parent/children)."""

    code = models.CharField(_("رمز القسم"), max_length=30)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    branch = models.ForeignKey(
        Branch,
        verbose_name=_("الفرع"),
        on_delete=models.PROTECT,
        related_name="departments",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name=_("القسم الأب"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    manager = models.ForeignKey(
        "employees.Employee",
        verbose_name=_("مدير القسم"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_departments",
    )

    class Meta:
        unique_together = ("branch", "code")
        verbose_name = _("قسم")
        verbose_name_plural = _("الأقسام")

    def __str__(self):
        return self.name_ar


class Position(BaseModel):
    """T-011 — منصب/وظيفة."""

    code = models.CharField(_("رمز المنصب"), max_length=30, unique=True)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    department = models.ForeignKey(
        Department,
        verbose_name=_("القسم"),
        on_delete=models.PROTECT,
        related_name="positions",
    )
    grade = models.CharField(_("الدرجة"), max_length=20, blank=True)

    class Meta:
        verbose_name = _("منصب")
        verbose_name_plural = _("المناصب")

    def __str__(self):
        return self.name_ar


class Shift(BaseModel):
    """T-012 — جدول دوام."""

    code = models.CharField(_("رمز الدوام"), max_length=30, unique=True)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    start_time = models.TimeField(_("بداية الدوام"))
    end_time = models.TimeField(_("نهاية الدوام"))
    is_flexible = models.BooleanField(_("دوام مرن"), default=False)
    grace_minutes = models.PositiveSmallIntegerField(_("سماحية التأخير (دقيقة)"), default=10)

    class Meta:
        verbose_name = _("جدول دوام")
        verbose_name_plural = _("جداول الدوام")

    def __str__(self):
        return self.name_ar
