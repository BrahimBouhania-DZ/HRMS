"""ديكورات التفويض (T-RBAC-4) — تحقق الخادم قبل تنفيذ العرض.

المرجع: docs/05-rbac.md §8 — المستوى 2 (التفويض).
القاعدة: لا تثق بالواجهة — الأزرار تخفى للـ UX لكن التحقق إجباري هنا.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from .services import has_perm


def require_permission(permission_code: str):
    """يُغلق العرض أمام من لا يملك الصلاحية (401/403)."""

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not has_perm(request.user, permission_code):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
