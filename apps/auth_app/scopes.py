"""نطاق البيانات (Data Scope) — T-RBAC-5.

المرجع: docs/05-rbac.md §7. النطاقات: GLOBAL / BRANCH / DEPARTMENT / TEAM / SELF / NONE.
القرار في طبقة الخدمات لا في الواجهة — تُستخدم لتصفية كل QuerySet حرج.
"""

from apps.employees.models import Employee

SCOPE_GLOBAL = "global"
SCOPE_BRANCH = "branch"
SCOPE_DEPARTMENT = "department"
SCOPE_TEAM = "team"
SCOPE_SELF = "self"
SCOPE_NONE = "none"


def employee_scope_queryset(user):
    """يرجع QuerySet الموظفين المسموح برؤيتهم حسب نطاق المستخدم."""
    qs = Employee.objects.all()

    if user.is_superuser:
        return qs.filter(is_active=True)

    # التحديد حسب الأدوار (الأعلى نطاقًا يسبق الأدنى)
    role_codes = set(user.role_memberships.values_list("role__code", flat=True))
    branch_scopes = list(
        user.role_memberships.exclude(branch_scope__isnull=True)
        .values_list("branch_scope_id", flat=True)
    )

    if "admin" in role_codes or "hr_manager" in role_codes:
        return qs.filter(is_active=True)  # GLOBAL

    if "supervisor" in role_codes:
        # TEAM: يقصد قسمه — مبسطًا على موظفي القسم الذي يشرف عليه
        emp = getattr(user, "employee_profile", None)
        if emp is not None and emp.department_id:
            return qs.filter(is_active=True, department_id=emp.department_id)
        return qs.none()

    if "accountant" in role_codes:
        # GLOBAL ماليًا لكن بدون بيانات بنكية/راتب يُتحقق منها في طبقة العرض
        return qs.filter(is_active=True)

    if "employee" in role_codes or role_codes == {"employee"}:
        return qs.filter(is_active=True, user=user)

    if branch_scopes:
        return qs.filter(is_active=True, branch_id__in=branch_scopes)

    return qs.none()


def scoped_departments(user):
    """الأقسام المسموح رؤيتها (يستعمل في قوائم org)."""
    from apps.org.models import Department

    if user.is_superuser:
        return Department.objects.all()
    role_codes = set(user.role_memberships.values_list("role__code", flat=True))
    if role_codes & {"admin", "hr_manager"}:
        return Department.objects.all()
    return Department.objects.none()
