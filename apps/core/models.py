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
