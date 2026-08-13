"""خدمات التقارير الأساسية REP-01,10,12,13,20,21 + التصدير CSV/Excel (S5).

المرجع: docs/08-reports.md §2.1–2.3 + §3 (تصدير CSV/Excel؛ PDF مؤجل لـ S6).
كل تقرير مقيد بنطاق المستخدم (employee_scope_queryset).
"""

import csv
from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils.translation import gettext as _

from apps.attendance.models import AttendanceDay
from apps.auth_app.scopes import employee_scope_queryset
from apps.employees.models import Employee
from apps.leave.models import LeaveBalance, LeaveRequest, LeaveType
from apps.org.models import Branch, Department


def scoped_employee_ids(user):
    return list(employee_scope_queryset(user).values_list("id", flat=True))


def employee_list(user, branch=None, department=None, employment_status=None):
    qs = employee_scope_queryset(user).filter(is_active=True)
    if branch:
        qs = qs.filter(branch_id=branch)
    if department:
        qs = qs.filter(department_id=department)
    if employment_status:
        qs = qs.filter(employment_status=employment_status)
    return qs.select_related("branch", "department", "position").order_by("employee_code")


def attendance_daily(user, work_date=None, branch=None, department=None):
    ids = scoped_employee_ids(user)
    qs = AttendanceDay.objects.filter(employee_id__in=ids)
    if work_date:
        qs = qs.filter(work_date=work_date)
    if branch:
        qs = qs.filter(branch_id=branch)
    if department:
        qs = qs.filter(employee__department_id=department)
    return qs.select_related("employee", "employee__department").order_by("work_date")


def absence_summary(user, from_date=None, to_date=None, department=None, justified=False):
    """عدّ أيام الغياب (غير مبرر) أو الإجازات (مبرر) لكل موظف في الفترة."""
    ids = scoped_employee_ids(user)
    state = AttendanceDay.State.LEAVE if justified else AttendanceDay.State.ABSENT
    qs = AttendanceDay.objects.filter(employee_id__in=ids, state=state)
    if from_date:
        qs = qs.filter(work_date__gte=from_date)
    if to_date:
        qs = qs.filter(work_date__lte=to_date)
    if department:
        qs = qs.filter(employee__department_id=department)
    return qs.values("employee_id", "employee__employee_code", "employee__first_name_ar",
                     "employee__last_name_ar", "employee__department__name_ar").annotate(
        days=Count("id")).order_by("-days")


def lateness_summary(user, from_date=None, to_date=None, department=None):
    ids = scoped_employee_ids(user)
    qs = AttendanceDay.objects.filter(employee_id__in=ids, late_minutes__gt=0)
    if from_date:
        qs = qs.filter(work_date__gte=from_date)
    if to_date:
        qs = qs.filter(work_date__lte=to_date)
    if department:
        qs = qs.filter(employee__department_id=department)
    return qs.values("employee_id", "employee__employee_code", "employee__first_name_ar",
                     "employee__last_name_ar", "employee__department__name_ar").annotate(
        times=Count("id"), total_minutes=Sum("late_minutes")).order_by("-total_minutes")


def operational_summary(user, from_date=None, to_date=None, branch=None, department=None):
    """REP-11 — الملخص التشغيلي: إحصاءات عامة + تفصيل لكل موظف في الفترة."""
    ids = scoped_employee_ids(user)
    qs = AttendanceDay.objects.filter(employee_id__in=ids)
    if from_date:
        qs = qs.filter(work_date__gte=from_date)
    if to_date:
        qs = qs.filter(work_date__lte=to_date)
    if branch:
        qs = qs.filter(branch_id=branch)
    if department:
        qs = qs.filter(employee__department_id=department)

    present = qs.filter(state=AttendanceDay.State.PRESENT).count()
    absent = qs.filter(state=AttendanceDay.State.ABSENT).count()
    leave = qs.filter(state=AttendanceDay.State.LEAVE).count()
    late_times = qs.filter(late_minutes__gt=0).count()
    late_minutes = qs.aggregate(m=Sum("late_minutes"))["m"] or 0
    overtime_minutes = qs.aggregate(m=Sum("overtime_minutes"))["m"] or 0
    total = qs.count()

    summary = {
        "days_total": total,
        "present": present,
        "absent": absent,
        "leave": leave,
        "late_times": late_times,
        "late_minutes": late_minutes,
        "overtime_hours": round(overtime_minutes / 60, 1),
        "attendance_rate": round(present / total * 100, 1) if total else 0,
        "employees": qs.values("employee_id").distinct().count(),
    }

    rows = (
        qs.values(
            "employee_id", "employee__employee_code", "employee__first_name_ar",
            "employee__last_name_ar", "employee__department__name_ar",
        )
        .annotate(
            present=Count("id", filter=Q(state=AttendanceDay.State.PRESENT)),
            absent=Count("id", filter=Q(state=AttendanceDay.State.ABSENT)),
            leave=Count("id", filter=Q(state=AttendanceDay.State.LEAVE)),
            late_times=Count("id", filter=Q(late_minutes__gt=0)),
            late_minutes=Sum("late_minutes"),
            overtime=Sum("overtime_minutes"),
        )
        .order_by("employee__employee_code")
    )
    return summary, rows


def org_structure(user, branch=None):
    """REP-02 — الهيكل التنظيمي: فرع/قسم/منصب + عدد الموظفين (مقيد بالنطاق)."""
    ids = scoped_employee_ids(user)
    branches = Branch.objects.all()
    if branch:
        branches = branches.filter(id=branch)
    rows = []
    for b in branches.prefetch_related("departments__positions"):
        for dep in b.departments.all():
            for pos in dep.positions.all():
                count = Employee.objects.filter(
                    id__in=ids, position_id=pos.id, is_active=True
                ).count()
                rows.append({
                    "branch": b.name_ar,
                    "department": dep.name_ar,
                    "position": pos.name_ar,
                    "employees": count,
                })
    return rows


def new_employees(user, from_date=None, to_date=None, branch=None):
    """REP-03 — الموظفون الجدد حسب فترة التوظيف."""
    qs = employee_scope_queryset(user).filter(is_active=True)
    if from_date:
        qs = qs.filter(hire_date__gte=from_date)
    if to_date:
        qs = qs.filter(hire_date__lte=to_date)
    if branch:
        qs = qs.filter(branch_id=branch)
    return [
        {
            "code": e.employee_code,
            "name": str(e),
            "hire_date": e.hire_date,
            "department": e.department and e.department.name_ar or "—",
            "branch": e.branch and e.branch.name_ar or "—",
        }
        for e in qs.select_related("department", "branch").order_by("-hire_date")
    ]


def early_departure_summary(user, from_date=None, to_date=None, department=None):
    """REP-14 — الانصراف المبكر: مرات + مجموع دقائق لكل موظف."""
    ids = scoped_employee_ids(user)
    qs = AttendanceDay.objects.filter(employee_id__in=ids, early_minutes__gt=0)
    if from_date:
        qs = qs.filter(work_date__gte=from_date)
    if to_date:
        qs = qs.filter(work_date__lte=to_date)
    if department:
        qs = qs.filter(employee__department_id=department)
    return qs.values("employee_id", "employee__employee_code", "employee__first_name_ar",
                     "employee__last_name_ar", "employee__department__name_ar").annotate(
        times=Count("id"), total_minutes=Sum("early_minutes")).order_by("-total_minutes")


def overtime_summary(user, from_date=None, to_date=None, department=None):
    """REP-15 — ساعات العمل الإضافية: دقائق OT لكل موظف."""
    ids = scoped_employee_ids(user)
    qs = AttendanceDay.objects.filter(employee_id__in=ids, overtime_minutes__gt=0)
    if from_date:
        qs = qs.filter(work_date__gte=from_date)
    if to_date:
        qs = qs.filter(work_date__lte=to_date)
    if department:
        qs = qs.filter(employee__department_id=department)
    return qs.values("employee_id", "employee__employee_code", "employee__first_name_ar",
                     "employee__last_name_ar", "employee__department__name_ar").annotate(
        times=Count("id"), total_minutes=Sum("overtime_minutes")).order_by("-total_minutes")


def attendance_exceptions(user, from_date=None, to_date=None, status=None):
    """REP-18 — استثناءات الحضور (إذن/مأمورية/تعويض/تصحيح)."""
    from apps.attendance.models import AttendanceException

    ids = scoped_employee_ids(user)
    qs = AttendanceException.objects.filter(employee_id__in=ids)
    if from_date:
        qs = qs.filter(from_time__date__gte=from_date)
    if to_date:
        qs = qs.filter(from_time__date__lte=to_date)
    if status:
        qs = qs.filter(status=status)
    return [
        {
            "employee": f"{e.employee.employee_code} — {e.employee}",
            "type": e.get_type_display(),
            "from": e.from_time.strftime("%Y-%m-%d %H:%M"),
            "to": e.to_time.strftime("%Y-%m-%d %H:%M"),
            "hours": e.hours,
            "status": e.get_status_display(),
            "approved_by": e.approved_by and e.approved_by.username or "—",
        }
        for e in qs.select_related("employee", "approved_by").order_by("-from_time")
    ]


def ongoing_approved_leaves(user, on_date=None):
    """REP-22 — الإجازات المعتمدة الجارية في تاريخ معين."""
    from apps.leave.models import LeaveRequest

    ids = scoped_employee_ids(user)
    on_date = on_date or date.today()
    qs = LeaveRequest.objects.filter(
        employee_id__in=ids, status=LeaveRequest.Status.APPROVED,
        from_date__lte=on_date, to_date__gte=on_date,
    )
    return [
        {
            "employee": f"{r.employee.employee_code} — {r.employee}",
            "leave_type": r.leave_type.name_ar,
            "from_date": r.from_date,
            "to_date": r.to_date,
            "days": r.days,
        }
        for r in qs.select_related("employee", "leave_type").order_by("from_date")
    ]


def public_holidays(user, year=None, branch=None):
    """REP-23 — العطل الرسمية حسب السنة/الفرع."""
    from apps.leave.models import PublicHoliday

    qs = PublicHoliday.objects.all()
    if year:
        qs = qs.filter(date__year=year)
    if branch:
        qs = qs.filter(branch_id=branch)
    return [
        {
            "date": h.date,
            "name": h.name_ar,
            "branch": h.branch.name_ar,
            "recurring": _("نعم") if h.is_recurring else _("لا"),
        }
        for h in qs.select_related("branch").order_by("date")
    ]


def leave_balances(user, year=None, leave_type=None, department=None):
    ids = scoped_employee_ids(user)
    qs = LeaveBalance.objects.filter(employee_id__in=ids)
    if year:
        qs = qs.filter(year=year)
    if leave_type:
        qs = qs.filter(leave_type_id=leave_type)
    if department:
        qs = qs.filter(employee__department_id=department)
    return qs.select_related("employee", "employee__department", "leave_type").order_by(
        "employee__employee_code", "leave_type__name_ar")


def leave_requests(user, from_date=None, to_date=None, status=None, leave_type=None):
    ids = scoped_employee_ids(user)
    qs = LeaveRequest.objects.filter(employee_id__in=ids)
    if from_date:
        qs = qs.filter(from_date__gte=from_date)
    if to_date:
        qs = qs.filter(to_date__lte=to_date)
    if status:
        qs = qs.filter(status=status)
    if leave_type:
        qs = qs.filter(leave_type_id=leave_type)
    return qs.select_related("employee", "employee__department", "leave_type").order_by("-created_at")


def scan_log(user, day=None, device=None, decision=None):
    """REP-16 — سجل مسحات QR (مقيد بالنطاق)."""
    from apps.attendance.models import AttendanceScan

    ids = scoped_employee_ids(user)
    qs = AttendanceScan.objects.filter(employee_id__in=ids)
    if day:
        qs = qs.filter(scanned_at__date=day)
    if device:
        qs = qs.filter(device_id=device)
    if decision:
        qs = qs.filter(decision=decision)
    return qs.select_related("employee", "device").order_by("-scanned_at")


def rejected_scans(user, from_date=None, to_date=None, device=None):
    """REP-17 — المسحات المرفوضة مجمّعة (موظف/سبب/جهاز/تكرار)."""
    from apps.attendance.models import AttendanceScan

    ids = scoped_employee_ids(user)
    qs = AttendanceScan.objects.filter(employee_id__in=ids, decision=AttendanceScan.Decision.REJECTED)
    if from_date:
        qs = qs.filter(scanned_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(scanned_at__date__lte=to_date)
    if device:
        qs = qs.filter(device_id=device)
    return qs.values("employee_id", "employee__employee_code", "employee__first_name_ar",
                     "employee__last_name_ar", "device__device_code",
                     "result_detail").annotate(times=Count("id")).order_by("-times")


# ---- فلاتر (للقوالب) ------------------------------------------------------

def filter_options():
    from apps.attendance.models import AttendanceException, AttendanceScan
    from apps.devices.models import QrDevice
    from apps.payroll.models import PayElement, PayRun, EndOfService
    from apps.perf.models import PerfCycle

    return {
        "branches": Branch.objects.all().order_by("name_ar"),
        "departments": Department.objects.all().order_by("name_ar"),
        "statuses": Employee.EmploymentStatus.choices,
        "leave_statuses": LeaveRequest.Status.choices,
        "leave_types": LeaveType.objects.all().order_by("name_ar"),
        "devices": QrDevice.objects.all().order_by("device_code"),
        "scan_decisions": AttendanceScan.Decision.choices,
        "period_codes": (
            PayRun.objects.values_list("period_code", flat=True)
            .distinct().order_by("-period_code")
        ),
        "cycles": PerfCycle.objects.all().order_by("-period_start"),
        "element_kinds": PayElement.Kind.choices,
        "eos_statuses": EndOfService.Status.choices,
        "exception_statuses": AttendanceException.Status.choices,
    }


# ---- الرواتب (v2) ---------------------------------------------------------

def payroll_summary(user, period_code=None, branch=None):
    """REP-30 — ملخص دورات الصرف حسب الفترة/الفرع (مقيد بالنطاق)."""
    from apps.auth_app.scopes import employee_scope_queryset
    from apps.payroll.models import PayRun

    if user.is_superuser:
        qs = PayRun.objects.all()
    else:
        branch_ids = set(
            employee_scope_queryset(user)
            .exclude(branch_id__isnull=True)
            .values_list("branch_id", flat=True)
        )
        qs = PayRun.objects.filter(branch_id__in=branch_ids)
    if period_code:
        qs = qs.filter(period_code=period_code)
    if branch:
        qs = qs.filter(branch_id=branch)
    return [
        {
            "period_code": r.period_code,
            "branch": r.branch.name_ar,
            "status": r.get_status_display(),
            "employees": r.payslips.count(),
            "total_earnings": r.total_earnings,
            "total_deductions": r.total_deductions,
            "total_net": r.total_net,
        }
        for r in qs.order_by("-period_code")
    ]


# ---- العقود (v2) ----------------------------------------------------------

def contract_expiry_list(user, days=30, branch=None):
    """REP-04 — عقود تنتهي خلال (days) يومًا (دون المسحوب سابقًا)."""
    from apps.employees.models import Contract

    today = date.today()
    ids = scoped_employee_ids(user)
    horizon = today + timedelta(days=days)
    qs = Contract.objects.filter(
        employee_id__in=ids, end_date__isnull=False,
        end_date__gte=today, end_date__lte=horizon,
        renewal__isnull=True,
    )
    if branch:
        qs = qs.filter(employee__branch_id=branch)
    rows = []
    for c in qs.select_related("employee", "employee__branch").order_by("end_date"):
        rows.append({
            "employee": f"{c.employee.employee_code} — {c.employee}",
            "contract_type": c.get_contract_type_display(),
            "end_date": c.end_date,
            "days_left": c.days_to_expiry,
            "branch": c.employee.branch and c.employee.branch.name_ar or "",
        })
    return rows


# ---- الرواتب التفصيلية (v2) -----------------------------------------------

def _payroll_scope(user, period_code=None, branch=None, department=None):
    from apps.payroll.models import PayRun, Payslip

    if user.is_superuser:
        qs = Payslip.objects.all()
    else:
        branch_ids = set(
            employee_scope_queryset(user)
            .exclude(branch_id__isnull=True)
            .values_list("branch_id", flat=True)
        )
        qs = Payslip.objects.filter(pay_run__branch_id__in=branch_ids)
    if period_code:
        qs = qs.filter(pay_run__period_code=period_code)
    if branch:
        qs = qs.filter(pay_run__branch_id=branch)
    if department:
        qs = qs.filter(employee__department_id=department)
    return qs.select_related("employee", "employee__department", "pay_run")


def payroll_detail(user, period_code=None, department=None):
    """REP-31 — كشف رواتب تفصيلي: موظف + صافي (عناصر مُجمّعة في النص)."""
    from apps.payroll.models import PayrollLine

    lines = []
    for p in _payroll_scope(user, period_code=period_code, department=department).order_by(
            "employee__employee_code"):
        details = ", ".join(
            f"{ln.element.name_ar if ln.element else ln.note}: {ln.amount:g}"
            for ln in PayrollLine.objects.filter(pay_run=p.pay_run, employee=p.employee)
        )
        lines.append({
            "employee": f"{p.employee.employee_code} — {p.employee}",
            "department": p.employee.department and p.employee.department.name_ar or "",
            "period": p.pay_run.period_code,
            "earnings": p.total_earnings,
            "deductions": p.total_deductions,
            "net": p.net,
            "details": details,
        })
    return lines


def payroll_cost_by_branch(user, period_code=None, branch=None):
    """REP-33 — تكلفة الرواتب مجمّعة حسب الفرع/القسم (SQL Aggregation)."""
    qs = _payroll_scope(user, period_code=period_code, branch=branch)
    rows = (
        qs.values("pay_run__branch__name_ar", "employee__department__name_ar")
        .annotate(
            employees=Count("id", distinct=True),
            total_net=Sum("net"),
            total_earnings=Sum("total_earnings"),
        )
        .order_by("-total_net")
    )
    return [
        {
            "branch": r["pay_run__branch__name_ar"] or "—",
            "department": r["employee__department__name_ar"] or "—",
            "employees": r["employees"],
            "total_earnings": r["total_earnings"] or 0,
            "total_net": r["total_net"] or 0,
            "average": round((r["total_net"] or 0) / r["employees"], 2) if r["employees"] else 0,
        }
        for r in rows
    ]


def bonus_deduction_list(user, period_code=None, kind=None):
    """REP-34 — المكافآت والخصومات من أسطر عناصر الأجر (مقيد بالنطاق)."""
    from apps.payroll.models import PayrollLine

    ids = scoped_employee_ids(user)
    qs = PayrollLine.objects.filter(employee_id__in=ids)
    if period_code:
        qs = qs.filter(pay_run__period_code=period_code)
    rows = []
    for ln in qs.select_related("pay_run", "employee", "employee__department", "element").order_by(
            "pay_run__period_code", "employee__employee_code"):
        elem_kind = ln.element.kind if ln.element else ""
        if kind and elem_kind != kind:
            continue
        rows.append({
            "period": ln.pay_run.period_code,
            "employee": f"{ln.employee.employee_code} — {ln.employee}",
            "element": ln.element.name_ar if ln.element else (ln.note or "—"),
            "kind": ln.element.get_kind_display() if ln.element else _("—"),
            "amount": ln.amount,
        })
    return rows


def end_of_service_list(user, from_date=None, to_date=None, status=None):
    """REP-35 — نهايات الخدمة ومستحقاتها (مقيد بالنطاق)."""
    from apps.payroll.models import EndOfService

    ids = scoped_employee_ids(user)
    qs = EndOfService.objects.filter(employee_id__in=ids)
    if from_date:
        qs = qs.filter(termination_date__gte=from_date)
    if to_date:
        qs = qs.filter(termination_date__lte=to_date)
    if status:
        qs = qs.filter(status=status)
    return [
        {
            "employee": f"{r.employee.employee_code} — {r.employee}",
            "termination_date": r.termination_date,
            "years": r.total_years,
            "reward": r.service_reward,
            "leave_comp": r.unused_leave_comp,
            "notice": r.notice_period,
            "deductions": r.deductions,
            "net": r.net,
            "status": r.get_status_display(),
        }
        for r in qs.select_related("employee").order_by("-termination_date")
    ]


# ---- الأداء (v2) ----------------------------------------------------------

def perf_results(user, cycle=None):
    """REP-42 — نتائج تقييمات دورة: موظف + ذاتي + مدير + نهائي."""
    from apps.perf.models import PerfReview

    ids = scoped_employee_ids(user)
    qs = PerfReview.objects.filter(employee_id__in=ids)
    if cycle:
        qs = qs.filter(cycle_id=cycle)
    return [
        {
            "employee": f"{r.employee.employee_code} — {r.employee}",
            "cycle": r.cycle.name_ar,
            "self_score": r.self_score,
            "manager_score": r.manager_score,
            "final_score": r.final_score,
            "status": r.get_status_display(),
        }
        for r in qs.select_related("employee", "cycle").order_by("employee__employee_code")
    ]


def pip_list(user, status=None):
    """REP-43 — خطط تحسين الأداء (PIP)."""
    from apps.perf.models import PipPlan

    ids = scoped_employee_ids(user)
    qs = PipPlan.objects.filter(review__employee_id__in=ids)
    if status:
        qs = qs.filter(status=status)
    return [
        {
            "employee": f"{p.review.employee.employee_code} — {p.review.employee}",
            "cycle": p.review.cycle.name_ar,
            "start_date": p.start_date,
            "end_date": p.end_date,
            "status": p.get_status_display(),
        }
        for p in qs.select_related("review__employee", "review__cycle").order_by("-start_date")
    ]


# ---- الموظفون: تقاعد وتغييرات (v3) ------------------------------------------

def _to_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def retirement_list(user, from_date=None, to_date=None, branch=None, retirement_age=60):
    """REP-05 — الموظفون المقبلون على التقاعد (تاريخ الميلاد + سن التقاعد).

    النطاق الافتراضي: من اليوم إلى سنة قادمة. سن التقاعد الافتراضي 60 سنة.
    """
    qs = employee_scope_queryset(user).filter(
        birth_date__isnull=False,
        employment_status__in=[
            Employee.EmploymentStatus.ACTIVE,
            Employee.EmploymentStatus.PROBATION,
        ],
    )
    if branch:
        qs = qs.filter(branch_id=branch)

    today = date.today()
    f_from = _to_date(from_date) or today
    f_to = _to_date(to_date) or (today + timedelta(days=365))

    rows = []
    for e in qs.select_related("branch", "department").order_by("employee_code"):
        retirement_date = _add_years(e.birth_date, retirement_age)
        if f_from <= retirement_date <= f_to:
            rows.append({
                "code": e.employee_code,
                "name": str(e),
                "birth": e.birth_date,
                "retire": retirement_date,
                "days": (retirement_date - today).days,
                "department": e.department and e.department.name_ar or "",
                "branch": e.branch and e.branch.name_ar or "",
            })
    return rows


def job_changes(user, from_date=None, to_date=None, change_type=None, branch=None):
    """REP-06 — تغييرات الوظائف (تعيين/ترقية منصب/نقل) من السجل الوظيفي."""
    from apps.employees.models import EmploymentHistory

    ids = scoped_employee_ids(user)
    qs = EmploymentHistory.objects.filter(employee_id__in=ids).select_related(
        "employee", "branch", "department", "position",
    )
    if from_date:
        qs = qs.filter(effective_from__gte=from_date)
    if to_date:
        qs = qs.filter(effective_from__lte=to_date)
    if branch:
        qs = qs.filter(branch_id=branch)
    qs = qs.order_by("employee_id", "effective_from", "id")

    rows = []
    prev_by_emp = {}
    for h in qs:
        prev = prev_by_emp.get(h.employee_id)
        if prev is None:
            kind = "hire"
        elif h.position_id and h.position_id != prev.position_id:
            kind = "promotion"
        elif h.department_id != prev.department_id or h.branch_id != prev.branch_id:
            kind = "transfer"
        else:
            kind = "update"
        prev_by_emp[h.employee_id] = h
        if change_type and kind != change_type:
            continue

        if kind == "promotion":
            frm = prev.position and prev.position.name_ar or ""
            to = h.position and h.position.name_ar or ""
        elif kind == "transfer":
            frm = prev.department and prev.department.name_ar or ""
            to = h.department and h.department.name_ar or ""
        elif kind == "update":
            frm = prev.position and prev.position.name_ar or ""
            to = h.position and h.position.name_ar or ""
        else:  # hire
            frm = _("—")
            to = h.position and h.position.name_ar or ""
            if h.department:
                to = f"{to} — {h.department.name_ar}"

        rows.append({
            "code": h.employee.employee_code,
            "name": str(h.employee),
            "kind": _("تعيين") if kind == "hire"
                else _("ترقية/منصب") if kind == "promotion"
                else _("نقل") if kind == "transfer"
                else _("تحديث سجل"),
            "from": frm,
            "to": to,
            "date": h.effective_from,
            "branch": h.branch and h.branch.name_ar or "",
        })
    return rows


# ---- تنفيذية: ملخص وKPI ودوران (v3) -----------------------------------------

def _active_statuses():
    return [Employee.EmploymentStatus.ACTIVE, Employee.EmploymentStatus.PROBATION]


def executive_summary(user, from_date=None, to_date=None, branch=None):
    """REP-60 — ملخص تنفيذي حسب الفرع: توظيف، مغادرة، حضور، رواتب."""
    from apps.attendance.models import AttendanceDay
    from apps.payroll.models import EndOfService, PayRun, Payslip

    ids = scoped_employee_ids(user)
    branches = Branch.objects.filter(id__in=employee_scope_queryset(user)
                                     .values_list("branch_id", flat=True).distinct())
    if branch:
        branches = branches.filter(pk=branch)

    f_from = _to_date(from_date) or date.today().replace(day=1)
    f_to = _to_date(to_date) or date.today()
    if f_to < f_from:
        f_from, f_to = f_to, f_from

    rows = []
    for b in branches:
        emp_qs = Employee.objects.filter(branch=b, id__in=ids)
        active = emp_qs.filter(employment_status__in=_active_statuses()).count()
        hires = emp_qs.filter(hire_date__range=(f_from, f_to)).count()
        departures = EndOfService.objects.filter(
            employee__branch=b, employee_id__in=ids,
            termination_date__range=(f_from, f_to),
        ).count()

        att = AttendanceDay.objects.filter(branch=b, employee_id__in=ids,
                                           work_date__range=(f_from, f_to))
        present = att.filter(state=AttendanceDay.State.PRESENT).count()
        absent = att.filter(state=AttendanceDay.State.ABSENT).count()
        total = att.count()

        last_payrun = PayRun.objects.filter(branch=b, status=PayRun.Status.FROZEN) \
            .order_by("-period_code").first()
        net = 0
        if last_payrun:
            net = Payslip.objects.filter(pay_run=last_payrun).aggregate(n=Sum("net"))["n"] or 0

        avg_salary = round(net / active, 2) if active else 0
        rows.append({
            "branch": b.name_ar,
            "active": active,
            "hires": hires,
            "departures": departures,
            "absent": absent,
            "attendance_rate": round(present / total * 100, 1) if total else 0,
            "net": net,
            "avg_salary": avg_salary,
        })
    return rows


def kpi_summary(user, from_date=None, to_date=None, branch=None):
    """REP-61 — مؤشرات KPI للفترة: حضور/غياب/إجازة/تأخر/دوران/رواتب."""
    from apps.payroll.models import EndOfService, PayRun, Payslip

    ids = scoped_employee_ids(user)
    f_from = _to_date(from_date) or date.today().replace(day=1)
    f_to = _to_date(to_date) or date.today()
    if f_to < f_from:
        f_from, f_to = f_to, f_from

    summary, op_rows = operational_summary(user, from_date=f_from, to_date=f_to, branch=branch)
    active = Employee.objects.filter(id__in=ids, employment_status__in=_active_statuses()).count()
    if branch:
        active = Employee.objects.filter(id__in=ids, branch_id=branch,
                                         employment_status__in=_active_statuses()).count()

    hires = Employee.objects.filter(id__in=ids, hire_date__range=(f_from, f_to)).count()
    if branch:
        hires = Employee.objects.filter(id__in=ids, branch_id=branch,
                                        hire_date__range=(f_from, f_to)).count()
    departures = EndOfService.objects.filter(
        employee_id__in=ids, termination_date__range=(f_from, f_to),
    ).count()
    if branch:
        departures = EndOfService.objects.filter(
            employee__branch_id=branch, employee_id__in=ids,
            termination_date__range=(f_from, f_to),
        ).count()

    start_hc = active + departures - hires
    avg_hc = (start_hc + active) / 2 if (start_hc + active) else 1
    turnover = round(departures / avg_hc * 100, 1) if departures else 0

    total = summary["days_total"]
    absence_rate = round(summary["absent"] / total * 100, 1) if total else 0
    leave_rate = round(summary["leave"] / total * 100, 1) if total else 0
    late_per_emp = round(summary["late_times"] / summary["employees"], 2) if summary["employees"] else 0

    payruns = PayRun.objects.filter(status=PayRun.Status.FROZEN)
    if branch:
        payruns = payruns.filter(branch_id=branch)
    net_total = Payslip.objects.filter(pay_run__in=payruns).aggregate(n=Sum("net"))["n"] or 0

    def ratio(value, target, invert=False):
        if target is None or target == 0:
            return "—"
        if invert:
            return round(min(1.0, target / value) * 100, 1) if value else 100.0
        return round(min(1.0, value / target) * 100, 1)

    return [
        {"kpi": _("نسبة الحضور"), "value": f"{summary['attendance_rate']}%",
         "target": _("95%"), "score": ratio(summary["attendance_rate"], 95)},
        {"kpi": _("نسبة الغياب"), "value": f"{absence_rate}%",
         "target": _("3%"), "score": ratio(absence_rate, 3, invert=True)},
        {"kpi": _("نسبة الإجازات"), "value": f"{leave_rate}%",
         "target": _("15%"), "score": ratio(leave_rate, 15, invert=True)},
        {"kpi": _("التأخر (مرات/موظف)"), "value": f"{late_per_emp}",
         "target": _("1"), "score": ratio(late_per_emp, 1, invert=True)},
        {"kpi": _("ساعات الإضافي"), "value": f"{summary['overtime_hours']}",
         "target": "—", "score": "—"},
        {"kpi": _("معدل الدوران"), "value": f"{turnover}%",
         "target": _("5%"), "score": ratio(turnover, 5, invert=True)},
        {"kpi": _("إجمالي الرواتب (صافي)"), "value": f"{net_total}",
         "target": "—", "score": "—"},
        {"kpi": _("الموظفون النشطون"), "value": f"{active}",
         "target": "—", "score": "—"},
    ]


def turnover_report(user, from_date=None, to_date=None, branch=None):
    """REP-62 — الدوران الوظيفي حسب القسم: معدل مغادرة/تعيين."""
    from apps.payroll.models import EndOfService

    ids = scoped_employee_ids(user)
    f_from = _to_date(from_date) or date.today().replace(day=1)
    f_to = _to_date(to_date) or date.today()
    if f_to < f_from:
        f_from, f_to = f_to, f_from

    emps = employee_scope_queryset(user).filter(employment_status__in=_active_statuses())
    if branch:
        emps = emps.filter(branch_id=branch)

    rows = []
    for dept in Department.objects.filter(id__in=emps.values_list("department_id", flat=True).distinct()):
        dept_emps = emps.filter(department=dept)
        end_hc = dept_emps.count()
        hires = Employee.objects.filter(id__in=ids, department=dept,
                                        hire_date__range=(f_from, f_to)).count()
        if branch:
            hires = Employee.objects.filter(id__in=ids, department=dept, branch_id=branch,
                                            hire_date__range=(f_from, f_to)).count()
        departures = EndOfService.objects.filter(
            employee__department=dept, employee_id__in=ids,
            termination_date__range=(f_from, f_to),
        ).count()
        start_hc = end_hc + departures - hires
        avg_hc = (start_hc + end_hc) / 2 if (start_hc + end_hc) else 0
        rate = round(departures / avg_hc * 100, 1) if avg_hc else 0
        rows.append({
            "department": dept.name_ar,
            "branch": dept.branch and dept.branch.name_ar or "",
            "end_hc": end_hc,
            "hires": hires,
            "departures": departures,
            "rate": rate,
        })
    return rows


# ---- النظام والأمان (v2) --------------------------------------------------

def audit_log_list(user, from_date=None, to_date=None, model_name=None):
    """REP-50 — سجل التدقيق (يُستدعى فقط بصلاحية system.audit.view)."""
    from apps.core.models import AuditLog

    qs = AuditLog.objects.all()
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if model_name:
        qs = qs.filter(model_name=model_name)
    return [
        {
            "time": r.created_at.strftime("%Y-%m-%d %H:%M"),
            "user": r.user and r.user.username or "—",
            "action": r.get_action_display(),
            "model": r.model_name,
            "object": r.object_repr,
            "detail": r.detail,
        }
        for r in qs.select_related("user")[:2000]
    ]


def users_roles_list(user, role=None):
    """REP-51 — المستخدمون وأدوارهم (إداري/أمان)."""
    from django.contrib.auth import get_user_model

    from apps.auth_app.models import RoleMember

    User = get_user_model()
    rows = []
    for u in User.objects.filter(is_active=True).order_by("username"):
        roles = list(RoleMember.objects.filter(user=u).select_related("role"))
        if role and not any(r.role.code == role for r in roles):
            continue
        rows.append({
            "username": u.username,
            "full_name": u.get_full_name(),
            "roles": ", ".join(r.role.name_ar for r in roles) or "—",
            "is_active": _("نعم") if u.is_active else _("لا"),
            "last_login": u.last_login and u.last_login.strftime("%Y-%m-%d %H:%M") or "—",
        })
    return rows


def backup_status_list(user, from_date=None, to_date=None):
    """REP-53 — حالة النسخ الاحتياطي (إداري/أمان)."""
    from apps.backup.models import BackupJob

    qs = BackupJob.objects.all()
    if from_date:
        qs = qs.filter(started_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(started_at__date__lte=to_date)
    return [
        {
            "kind": r.get_kind_display(),
            "started": r.started_at.strftime("%Y-%m-%d %H:%M"),
            "finished": r.finished_at and r.finished_at.strftime("%Y-%m-%d %H:%M") or "—",
            "status": r.get_status_display(),
            "size": r.file_size,
            "encrypted": _("نعم") if r.encrypted else _("لا"),
        }
        for r in qs.order_by("-started_at")[:500]
    ]


def daily_activity_list(user, from_date=None, to_date=None):
    """REP-52 — النشاط اليومي (دخول/خروج) من سجل التدقيق (إداري/أمان)."""
    from apps.core.models import AuditLog

    qs = AuditLog.objects.filter(action__in=[AuditLog.Action.LOGIN, AuditLog.Action.LOGOUT])
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    return [
        {
            "time": r.created_at.strftime("%Y-%m-%d %H:%M"),
            "user": r.user and r.user.username or "—",
            "action": r.get_action_display(),
            "ip": r.ip or "—",
        }
        for r in qs.select_related("user").order_by("-created_at")[:2000]
    ]


def device_status_list(user, branch=None):
    """REP-54 — حالة أجهزة QR وعدد مسحاتها (إداري)."""
    from django.db.models import Count

    from apps.attendance.models import AttendanceScan
    from apps.devices.models import QrDevice

    qs = QrDevice.objects.annotate(
        total_scans=Count("scans"),
    )
    if branch:
        qs = qs.filter(branch_id=branch)
    rows = []
    for d in qs.select_related("branch").order_by("device_code"):
        today_scans = AttendanceScan.objects.filter(
            device=d, scanned_at__date=date.today()
        ).count()
        rows.append({
            "device": d.device_code,
            "branch": d.branch.name_ar,
            "location": d.location or "—",
            "status": d.get_status_display(),
            "last_seen": d.last_seen and d.last_seen.strftime("%Y-%m-%d %H:%M") or "—",
            "today_scans": today_scans,
            "total_scans": d.total_scans,
        })
    return rows


# ---- التصدير --------------------------------------------------------------

def export_csv(response, header, rows):
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return response


def export_xlsx(response, header, rows, title):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = (title or _("تقرير"))[:31]
    ws.append(header)
    for row in rows:
        ws.append(row)
    wb.save(response)
    return response


def export_pdf(response, header, rows, title, request=None, extra=None):
    from django.template.loader import render_to_string

    from weasyprint import HTML

    context = {"title": title, "header": header, "rows": rows,
               "generated_at": date.today().isoformat()}
    if extra:
        context.update(extra)
    html = render_to_string(
        "reports/pdf_report.html",
        context,
        request=request,
    )
    HTML(string=html).write_pdf(response)
    return response
