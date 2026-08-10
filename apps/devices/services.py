"""خدمات أجهزة QR — تسجيل، مفاتيح API، تغيير الحالة (S6).

المرجع: docs/03 §3.11 + docs/06 §8 + docs/05 §8 (device.manage).
المفتاح يُعرض مرة واحدة عند الإنشاء فقط؛ يُخزَّن هاش SHA-256.
"""

import hashlib
import secrets

from django.utils.translation import gettext as _

from apps.core.models import BaseModel  # noqa: F401  (توثيق BaseModel المشترك)

from .models import QrDevice, QrDeviceAudit


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def register_device(device_code, branch, user, location="", api_key=None) -> tuple[QrDevice, str]:
    """يسجل جهازًا جديدًا ويعيد (الجهاز، المفتاح) — المفتاح يُعرض مرة واحدة."""
    api_key = api_key or generate_api_key()
    device = QrDevice.objects.create(
        device_code=device_code,
        branch=branch,
        location=location,
        api_key_hash=hash_api_key(api_key),
        created_by=user,
        updated_by=user,
    )
    QrDeviceAudit.objects.create(device=device, action="register", detail=_("تسجيل الجهاز"), created_by=user)
    return device, api_key


def set_device_status(device, status, user) -> QrDevice:
    """يغيّر حالة الجهاز (active/inactive/maintenance) مع سجل تدقيق."""
    old = device.status
    if old == status:
        return device
    device.status = status
    device.updated_by = user
    device.save(update_fields=["status", "updated_at", "updated_by"])
    QrDeviceAudit.objects.create(
        device=device,
        action=f"status:{old}->{status}",
        detail=_("تغيير الحالة من %(old)s إلى %(new)s") % {"old": old, "new": status},
        created_by=user,
    )
    return device
