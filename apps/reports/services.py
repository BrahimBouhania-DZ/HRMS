"""خدمات التقارير الأساسية REP-01,10,12,13,20,21 + التصدير CSV/Excel (S5).

المرجع: docs/08-reports.md §2.1–2.3 + §3 (تصدير CSV/Excel؛ PDF مؤجل لـ S6).
كل تقرير مقيد بنطاق المستخدم (employee_scope_queryset).
"""

import csv
from datetime import date

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
    from apps.payroll.models import PayRun

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
