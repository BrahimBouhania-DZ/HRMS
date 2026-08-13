"""مصادقة أجهزة QR لواجهة API (REST Framework).

الأجهزة القارئة الثابتة تستوثق عبر ترويسات:
  X-Device-Code + X-API-Key
(مثل مسار /attendance/api/v1/scan/ الأصلي) — تُعاد ككائن DeviceKeyAuthentication
حتى يتمكن العرض من تمييز مصدر المسح (fixed_reader) وضبط last_seen.
"""

import hashlib
import hmac

from django.contrib.auth.models import AnonymousUser
from django.utils.translation import gettext as _
from rest_framework import authentication
from rest_framework import exceptions

from apps.devices.models import QrDevice


class DeviceKeyAuthentication(authentication.BaseAuthentication):
    """مصادقة جهاز عبر مفتاح API (لا يتطلب جلسة/رمز).

    تعيد كائن مصادقة يحمل الجهاز؛ إن غابت الترويسات تعيد None
    ليجرّب DRF بقية المصادقات (Token ثم Session).
    """

    keyword = "ApiKey"

    def authenticate(self, request):
        code = request.headers.get("X-Device-Code")
        key = request.headers.get("X-API-Key")
        if not code and not key:
            return None
        if not code or not key:
            raise exceptions.AuthenticationFailed(_("X-Device-Code و X-API-Key مطلوبان معًا"))

        device = QrDevice.objects.filter(device_code=code, status=QrDevice.Status.ACTIVE).first()
        if device is None:
            raise exceptions.AuthenticationFailed(_("جهاز غير معروف أو غير نشط"))
        digest = hashlib.sha256(key.encode()).hexdigest()
        if not hmac.compare_digest(digest, device.api_key_hash):
            raise exceptions.AuthenticationFailed(_("مفتاح API غير صالح"))

        from django.utils import timezone

        device.last_seen = timezone.now()
        device.save(update_fields=["last_seen"])
        return (AnonymousUser(), DeviceKeyAuth(device))

    def authenticate_header(self, request):
        return self.keyword


class DeviceKeyAuth:
    """كائن auth يُخزَّن في request.auth لتحديد مصدر الجهاز."""

    def __init__(self, device):
        self.device = device
