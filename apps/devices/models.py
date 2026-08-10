"""نماذج أجهزة QR (T-047, T-048).

المرجع: docs/03-database-design.md §3.11 + docs/06-qr-system.md §8.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class QrDevice(BaseModel):
    """T-047 — قارئ QR ثابت مرتبط بفرع."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("نشط")
        INACTIVE = "inactive", _("معطّل")
        MAINTENANCE = "maintenance", _("صيانة")

    device_code = models.CharField(_("رمز الجهاز"), max_length=50, unique=True)
    branch = models.ForeignKey(
        "org.Branch",
        verbose_name=_("الفرع"),
        on_delete=models.PROTECT,
        related_name="qr_devices",
    )
    api_key_hash = models.CharField(_("هاش مفتاح API"), max_length=128)
    location = models.CharField(_("الموقع"), max_length=100, blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.ACTIVE)
    last_seen = models.DateTimeField(_("آخر اتصال"), null=True, blank=True)

    class Meta:
        verbose_name = _("قارئ QR")
        verbose_name_plural = _("قارئات QR")

    def __str__(self):
        return f"{self.device_code} — {self.branch}"


class QrDeviceAudit(BaseModel):
    """T-048 — سجل عمليات الأجهزة."""

    device = models.ForeignKey(QrDevice, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(_("الإجراء"), max_length=30)
    detail = models.TextField(_("التفاصيل"), blank=True)

    class Meta:
        verbose_name = _("سجل جهاز")
        verbose_name_plural = _("سجلات الأجهزة")

    def __str__(self):
        return f"{self.device} — {self.action}"
