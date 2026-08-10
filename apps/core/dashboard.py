"""لوحة المؤشرات (Dashboard KPI) — S5.

المرجع: docs/10-roadmap.md S5 + docs/04 §4.2.
جميع الأرقام مقيدة بنطاق المستخدم (employee_scope_queryset).
"""

from django.db.models import Q, Sum
from django.utils import timezone

from apps.attendance.models import AttendanceDay
from apps.auth_app.scopes import employee_scope_queryset
from apps.employees.models import Employee
from apps.leave.models import LeaveRequest


def dashboard_kpis(user, today=None):
    """يرجع قواميس KPI + أحدث الأنشطة حسب نطاق المستخدم."""
    today = today or timezone.localdate()
    employees = employee_scope_queryset(user).filter(is_active=True)
    employee_ids = list(employees.values_list("id", flat=True))

    present_today = AttendanceDay.objects.filter(
        employee_id__in=employee_ids, work_date=today, state=AttendanceDay.State.PRESENT
    )
    absent_today = AttendanceDay.objects.filter(
        employee_id__in=employee_ids, work_date=today, state=AttendanceDay.State.ABSENT
    )
    on_leave_today = AttendanceDay.objects.filter(
        employee_id__in=employee_ids, work_date=today, state=AttendanceDay.State.LEAVE
    )

    kpis = {
        "employees_total": len(employee_ids),
        "present_today": present_today.count(),
        "absent_today": absent_today.count(),
        "on_leave_today": on_leave_today.count(),
        "late_minutes_today": present_today.aggregate(t=Sum("late_minutes"))["t"] or 0,
        "pending_leaves": _pending_leaves(employee_ids).count(),
    }

    # أحدث النشاط (مقيد بالنطاق)
    recent_leaves = _pending_leaves(employee_ids).select_related(
        "employee", "leave_type"
    ).order_by("-created_at")[:5]
    recent_days = AttendanceDay.objects.filter(
        employee_id__in=employee_ids
    ).select_related("employee").order_by("-work_date", "-created_at")[:5]

    return {
        "kpis": kpis,
        "recent_leaves": recent_leaves,
        "recent_days": recent_days,
        "today": today,
    }


def _pending_leaves(employee_ids):
    return LeaveRequest.objects.filter(
        employee_id__in=employee_ids,
        status=LeaveRequest.Status.PENDING,
    )
