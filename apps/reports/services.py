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
    from apps.attendance.models import AttendanceScan
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
