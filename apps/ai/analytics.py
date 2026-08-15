"""محرك التحليلات (Analytics Engine) — T-AI-1.

المرجع: docs/07-ai-module.md §3 (مؤشرات الحضور/الرواتب/الأداء/التخطيط) + §9 (ai_analyticsjob).

المبادئ:
- **محلّل لكل مجال**: كل دالة محلّل ترجع بنية موحدة {kpis, columns, rows} قابلة للتحويل
  إلى جدول/رسم/تقرير — لا تُبنى الرسوم داخل المحلّل.
- **مقيد بالنطاق**: كل استعلام يمر عبر employee_scope_queryset(user) — لا يتجاوزه.
- **قراءة فقط**: لا تكتب إلا عبر save_analytics_job عند طلب صريح.
- **صفر تعميم**: كل رقم محسوب من قاعدة البيانات مع مصدره وفترته.
"""

import datetime

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.attendance.models import AttendanceDay
from apps.auth_app.scopes import employee_scope_queryset
from apps.leave.models import LeaveRequest
from apps.org.models import Department
from apps.perf.models import PerfReview
from apps.payroll.models import PayRun, Payslip

# --------------------------------------------------------------------- فترات


def _range(period: str) -> tuple[datetime.date | None, datetime.date | None]:
    """يرجع (start, end) للفترة المطلوبة — end غير شامل عند المقارنة."""
    today = timezone.localdate()
    if period == "today":
        return today, today + datetime.timedelta(days=1)
    if period == "week":
        start = today - datetime.timedelta(days=today.weekday())
        return start, start + datetime.timedelta(days=7)
    if period == "month":
        start = today.replace(day=1)
        nxt = (start + datetime.timedelta(days=32)).replace(day=1)
        return start, nxt
    if period == "year":
        return today.replace(month=1, day=1), today.replace(month=12, day=31) + datetime.timedelta(days=1)
    return None, None  # الكل


# --------------------------------------------------------------------- محلّلات


def attendance(user, period="month", group_by=None):
    """3.1 الحضور/الغياب/الإجازات في الفترة — حسب يوم أو قسم.

    group_by: None (إجمالي) | "department" (حسب القسم)
    """
    start, end = _range(period)
    qs = AttendanceDay.objects.filter(employee__in=employee_scope_queryset(user))
    if start:
        qs = qs.filter(work_date__gte=start, work_date__lt=end)
    if group_by == "department":
        qs = qs.values("employee__department__name_ar").annotate(
            present=Count("id", filter=Q(state=AttendanceDay.State.PRESENT)),
            absent=Count("id", filter=Q(state=AttendanceDay.State.ABSENT)),
            leave=Count("id", filter=Q(state=AttendanceDay.State.LEAVE)),
            late_minutes=Sum("late_minutes"),
            total=Count("id"),
        )
        rows = [
            {
                "name": r["employee__department__name_ar"] or "—",
                "present": r["present"],
                "absent": r["absent"],
                "leave": r["leave"],
                "late_minutes": int(r["late_minutes"] or 0),
                "total": r["total"],
            }
            for r in qs.order_by("-present")
        ]
        columns = ["name", "present", "absent", "leave", "late_minutes", "total"]
    else:
        agg = qs.aggregate(
            present=Count("id", filter=Q(state=AttendanceDay.State.PRESENT)),
            absent=Count("id", filter=Q(state=AttendanceDay.State.ABSENT)),
            leave=Count("id", filter=Q(state=AttendanceDay.State.LEAVE)),
            late_minutes=Sum("late_minutes"),
            total=Count("id"),
        )
        rows = [
            {
                "name": "—",
                "present": agg["present"],
                "absent": agg["absent"],
                "leave": agg["leave"],
                "late_minutes": int(agg["late_minutes"] or 0),
                "total": agg["total"],
            }
        ]
        columns = ["name", "present", "absent", "leave", "late_minutes", "total"]
    kpis = {
        "present": rows[0]["present"] if rows else 0,
        "absent": rows[0]["absent"] if rows else 0,
        "leave": rows[0]["leave"] if rows else 0,
        "late_minutes": rows[0]["late_minutes"] if rows else 0,
    }
    return {"kpis": kpis, "columns": columns, "rows": rows}


def payroll(user, period="month", group_by=None):
    """3.2 الرواتب: توزيع الأجور + نمو كتلة الأجور (مقارنة آخر دورتين)."""
    start, end = _range(period)
    runs = PayRun.objects.filter(status__in=[PayRun.Status.APPROVED, PayRun.Status.FROZEN])
    if start:
        runs = runs.filter(period_code__gte=f"{start.year:04d}-{start.month:02d}",
                           period_code__lt=f"{end.year:04d}-{end.month:02d}")
    runs = runs.order_by("-period_code")
    columns = ["period_code", "slips", "total_net", "avg_net"]
    rows = []
    for run in runs[:6]:
        slips = Payslip.objects.filter(pay_run=run, employee__in=employee_scope_queryset(user))
        agg = slips.aggregate(total=Sum("net"), n=Count("id"), avg=Avg("net"))
        rows.append({
            "period_code": run.period_code,
            "slips": agg["n"] or 0,
            "total_net": float(agg["total"] or 0),
            "avg_net": float(agg["avg"] or 0),
        })
    kpis = {
        "periods": len(rows),
        "latest_total": rows[0]["total_net"] if rows else 0,
        "latest_avg": rows[0]["avg_net"] if rows else 0,
    }
    if len(rows) >= 2 and rows[0]["total_net"]:
        prev = rows[1]["total_net"] or 0
        kpis["growth_pct"] = round((rows[0]["total_net"] - prev) / prev * 100, 1) if prev else 0.0
    else:
        kpis["growth_pct"] = 0.0
    return {"kpis": kpis, "columns": columns, "rows": rows}


def performance(user, period="month"):
    """3.3 الأداء: توزيع درجات التقييم حسب القسم + متوسط عام."""
    start, end = _range(period)
    qs = PerfReview.objects.filter(
        employee__in=employee_scope_queryset(user),
        status__in=[PerfReview.Status.DONE, PerfReview.Status.CLOSED],
    )
    if start:
        qs = qs.filter(cycle__period_start__gte=start, cycle__period_start__lt=end)
    agg = qs.aggregate(avg=Avg("final_score"), n=Count("id"))
    by_dept = list(
        qs.values("employee__department__name_ar")
        .annotate(avg=Avg("final_score"), n=Count("id"))
        .order_by("-avg")
    )
    rows = [
        {
            "name": r["employee__department__name_ar"] or "—",
            "avg": round(float(r["avg"] or 0), 1),
            "n": r["n"],
        }
        for r in by_dept
    ]
    kpis = {"avg": round(float(agg["avg"] or 0), 1), "n": agg["n"] or 0}
    return {"kpis": kpis, "columns": ["name", "avg", "n"], "rows": rows}


def leave(user, period="month", group_by=None):
    """3.1b الإجازات: أيام الإجازات المعتمدة حسب النوع في الفترة."""
    start, end = _range(period)
    qs = LeaveRequest.objects.filter(
        employee__in=employee_scope_queryset(user),
        status=LeaveRequest.Status.APPROVED,
    )
    if start:
        qs = qs.filter(from_date__lt=end, to_date__gte=start)
    if group_by == "type":
        qs = qs.values("leave_type__name_ar").annotate(days=Sum("days"), n=Count("id"))
        rows = [
            {"name": r["leave_type__name_ar"] or "—", "days": int(r["days"] or 0), "n": r["n"]}
            for r in qs.order_by("-days")
        ]
        columns = ["name", "days", "n"]
    else:
        rows, columns = [], ["name", "days", "n"]
    kpis = {"days": sum(r["days"] for r in rows), "requests": sum(r["n"] for r in rows)}
    return {"kpis": kpis, "columns": columns, "rows": rows}


def departments(user, period=None):
    """3.4 التخطيط: عبء كل قسم (موظفون نشطون) — أساس التغطية الموسمية."""
    from apps.employees.models import Employee

    qs = Employee.objects.filter(is_active=True).filter(
        id__in=employee_scope_queryset(user).values_list("id", flat=True)
    )
    rows = list(
        qs.values("department__name_ar")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    rows = [{"name": r["department__name_ar"] or "—", "n": r["n"]} for r in rows]
    kpis = {"departments": len(rows), "employees": sum(r["n"] for r in rows)}
    return {"kpis": kpis, "columns": ["name", "n"], "rows": rows}


def turnover(user, period=None):
    """تنبؤات مخاطر الاستقالة الحالية: توزيع حسب المستوى."""
    from apps.ai.models import AIPrediction

    preds = AIPrediction.objects.filter(
        employee__in=employee_scope_queryset(user),
        prediction_type=AIPrediction.Type.RESIGNATION,
    )
    rows = list(preds.values("level").annotate(n=Count("id")).order_by("level"))
    levels = {"high": 0, "medium": 0, "low": 0}
    for r in rows:
        if r["level"] in levels:
            levels[r["level"]] = r["n"]
    kpis = {
        "high": levels["high"],
        "medium": levels["medium"],
        "low": levels["low"],
        "total": sum(levels.values()),
    }
    return {"kpis": kpis, "columns": ["level", "n"],
            "rows": [{"name": lv, "n": n} for lv, n in levels.items() if n]}


# --------------------------------------------------------------------- تشغيل


def run_all(user, period="month"):
    """يشغّل كل المحلّلات ويعيد قاموسًا كاملًا (لتكوين لوحة تحليلات)."""
    return {
        "attendance": attendance(user, period),
        "payroll": payroll(user, period),
        "performance": performance(user, period),
        "leave": leave(user, period, group_by="type"),
        "departments": departments(user),
        "turnover": turnover(user),
    }


def save_analytics_job(user, analysis_type: str, result: dict, period="month") -> int:
    """يحفظ نتيجة تحليل في ai_analyticsjob (تدقيق + قابلية لإعادة العرض)."""
    from apps.ai.models import AnalyticsJob

    start, end = _range(period)
    job = AnalyticsJob.objects.create(
        analysis_type=analysis_type,
        period_start=start,
        period_end=(end - datetime.timedelta(days=1)) if end else None,
        scope_json={"user_id": user.id, "superuser": user.is_superuser},
        result_json=result,
        status=AnalyticsJob.Status.DONE,
        requested_by=user,
    )
    return job.id
