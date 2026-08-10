"""خدمات RBAC — حساب الصلاحيات الفعلية للمستخدم (T-RBAC-3).

القاعدة (docs/05-rbac.md §8):
    effective = (اتحاد أدوار المستخدم + صلاحيات مباشرة Grant)
                − (Deny المباشر)
                + (ميراث الدور الأب)
التحقق لحظي من قاعدة البيانات بدون كاش: أي تغيير على دور/صلاحية ينعكس فورًا
(لا خطر نتائج قديمة — القاعدة 8.2: الفقدان الفوري).
"""

from django.contrib.auth import get_user_model

from ..models import Permission, Role, RoleMember, UserPermission

User = get_user_model()


def effective_permissions(user) -> set[str]:
    """رموز الصلاحيات الفعلية للمستخدم (Union + ميراث + Grant − Deny)."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(Permission.objects.values_list("code", flat=True))

    perms: set[str] = set()

    # 1) اتحاد أدوار المستخدم (مع ميراث آباء الأدوار)
    role_memberships = RoleMember.objects.filter(user=user).select_related("role")
    for membership in role_memberships:
        perms |= _role_codes(membership.role_id)

    # 2) الاستثناءات المباشرة — Deny يتفوق دائمًا
    direct = UserPermission.objects.filter(user=user).select_related("permission")
    for exc in direct:
        if exc.action == UserPermission.GRANT:
            perms.add(exc.permission.code)
        else:
            perms.discard(exc.permission.code)

    return perms


def _role_codes(role_id: int, _visited: set[int] | None = None) -> set[str]:
    """رموز دور + ميراث آبائه (التراجع التكراري مع كسر الحلقات)."""
    _visited = _visited or set()
    if role_id in _visited:
        return set()
    _visited.add(role_id)

    role = Role.objects.only("id", "parent_id").get(id=role_id)
    codes = set(
        Permission.objects.filter(
            role_links__role_id=role_id
        ).values_list("code", flat=True)
    )
    if role.parent_id:
        codes |= _role_codes(role.parent_id, _visited)
    return codes


def has_perm(user, permission_code: str) -> bool:
    return permission_code in effective_permissions(user)


def user_roles(user) -> list[Role]:
    """أدوار المستخدم الحالية."""
    return list(Role.objects.filter(members__user=user).distinct())
