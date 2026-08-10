"""Mixins التفويض للعروض العامة (CBV) — T-RBAC-4.

المرجع: docs/05-rbac.md §8 — المستوى 2 (التفويض).
- المستخدم غير المسجل: إعادة توجيه لتسجيل الدخول (302).
- المستخدم بلا صلاحية: 403.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .services import has_perm


class PermissionRequiredMixin(LoginRequiredMixin):
    """يتطلب صلاحية محددة قبل السماح بالعرض."""

    permission_code: str = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not has_perm(request.user, self.permission_code):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
