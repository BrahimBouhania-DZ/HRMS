"""وسيط سياق التدقيق — يلتقط المستخدم وIP للطلبات الحالية (سجل التدقيق)."""

import threading

_local = threading.local()


class AuditContextMiddleware:
    """يخزّن مستخدم/IP الطلب في خيط التنفيذ لقراءتهما من إشارات النماذج."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.user = getattr(request, "user", None)
        _local.ip = request.META.get("REMOTE_ADDR", "") or ""
        try:
            response = self.get_response(request)
        finally:
            _local.user = None
            _local.ip = ""
        return response


def audit_context():
    """(المستخدم، IP) الحاليان — قد يكونان None خارج الطلب (أوامر إدارة/اختبارات)."""
    return getattr(_local, "user", None), getattr(_local, "ip", "")
