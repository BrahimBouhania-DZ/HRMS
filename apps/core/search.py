"""بحث موحّد عبر الوحدات (S5).

المرجع: docs/10-roadmap.md S5 + docs/04 §4.10 (البحث في الـ Topbar).
كل وحدة تُصفّى بنطاق المستخدم.
"""

from django.db.models import Q

from apps.auth_app.scopes import employee_scope_queryset
from apps.employees.models import Employee
from apps.leave.models import LeaveRequest
from apps.org.models import Branch, Department, Position


def unified_search(user, q, limit=6):
    """يرجع نتائج موحّدة (dict) للاستعلام q ضمن نطاق المستخدم."""
    q = (q or "").strip()
    if not q:
        return {}

    employees = employee_scope_queryset(user).filter(
        Q(employee_code__icontains=q)
        | Q(first_name_ar__icontains=q)
        | Q(last_name_ar__icontains=q)
        | Q(first_name_en__icontains=q)
        | Q(last_name_en__icontains=q)
        | Q(phone__icontains=q)
    )[:limit]

    branches = Branch.objects.filter(Q(code__icontains=q) | Q(name_ar__icontains=q))[:limit]
    departments = Department.objects.filter(Q(code__icontains=q) | Q(name_ar__icontains=q))[:limit]
    positions = Position.objects.filter(Q(code__icontains=q) | Q(name_ar__icontains=q))[:limit]

    scoped_ids = list(employee_scope_queryset(user).values_list("id", flat=True))
    leave_requests = LeaveRequest.objects.filter(employee_id__in=scoped_ids).filter(
        Q(employee__employee_code__icontains=q)
        | Q(employee__first_name_ar__icontains=q)
        | Q(leave_type__name_ar__icontains=q)
    )[:limit]

    return {
        "employees": employees,
        "branches": branches,
        "departments": departments,
        "positions": positions,
        "leave_requests": leave_requests,
        "q": q,
    }
