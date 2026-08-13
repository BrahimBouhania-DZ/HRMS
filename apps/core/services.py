"""خدمات عامة للوحدة الأساسية — تسجيل أحداث تدقيق يدوية (تصدير/استيراد)."""

from .middleware import audit_context
from .models import AuditLog


def record_audit(model_name, action, object_id="", detail="", user=None):
    """ينشئ سجل تدقيق يدوي (تصدير/استيراد/إجراءات ليست كتابة نموذج).

    تُسجَّل كتابات النماذج تلقائيًا عبر الإشارات (apps/core/signals.py).
    """
    ctx_user, ip = audit_context()
    actor = user if user is not None else ctx_user
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return AuditLog.objects.create(
        user=actor,
        action=action,
        model_name=model_name,
        object_id=str(object_id or "")[:50],
        object_repr=detail[:255],
        detail=detail,
        ip=ip or None,
    )
