"""منطق الحضور: خوارزمية قرار المسح + حساب التأخير (T-QR-3, T-019).

المرجع: docs/06-qr-system.md §5 (خوارزمية القرار) و §6 (منع التكرار).
"""

import datetime

from django.db import transaction
from django.db.models.fields import TimeField
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.employees.models import Employee, EmployeeQR
from apps.employees.qr_engine import verify_payload

from .models import AttendanceDay, AttendanceScan

# نافذة منع التكرار (ثوانٍ)
SCAN_COOLDOWN_SECONDS = 60


def auto_mark_absences(from_date, to_date, branch=None, employee=None, user=None):
    """BR-ATT-004 — تعليم أيام العمل التي لا يوجد لها مسح كغياب.

    يُستثنى من العلام:
        - أيام نهاية الأسبوع والعطل الرسمية (نفس قاعدة official_workdays).
        - الأيام المغطاة بإجازة معتمدة → تُسجَّل LEAVE.
        - الأيام المغطاة بمهمة معتمدة → تُسجَّل MISSION.
    العلام idempotent: لا يلمس الأيام الموجودة فعلًا.

    تُرجع عدد الأيام المنشأة.
    """
    from apps.leave.models import LeaveRequest
    from apps.leave.services import _holiday_dates

    from .models import AttendanceException

    qs = Employee.objects.filter(
        is_active=True,
        employment_status__in=(
            Employee.EmploymentStatus.ACTIVE,
            Employee.EmploymentStatus.PROBATION,
        ),
        hire_date__lte=to_date,
    )
    if branch:
        qs = qs.filter(branch=branch)
    if employee:
        qs = qs.filter(pk=employee.pk)
    qs = qs.order_by("employee_code")

    holidays = _holiday_dates(branch, from_date, to_date)
    weekdays = set(range(5))  # الاثنين..الجمعة (متوافق مع official_workdays)

    # إجازات معتمدة تغطي الفترة → تواريخ لكل موظف
    leaves_by_emp = {}
    for req in LeaveRequest.objects.filter(
        status=LeaveRequest.Status.APPROVED,
        from_date__lte=to_date,
        to_date__gte=from_date,
    ).values("employee_id", "from_date", "to_date"):
        d = max(req["from_date"], from_date)
        e = min(req["to_date"], to_date)
        dates = leaves_by_emp.setdefault(req["employee_id"], set())
        while d <= e:
            dates.add(d)
            d += datetime.timedelta(days=1)

    # مهام معتمدة تغطي الفترة → تواريخ لكل موظف
    missions_by_emp = {}
    for ex in AttendanceException.objects.filter(
        status=AttendanceException.Status.APPROVED,
        type=AttendanceException.Type.MISSION,
        from_time__date__lte=to_date,
        to_time__date__gte=from_date,
    ).values("employee_id", "from_time", "to_time"):
        d = max(ex["from_time"].date(), from_date)
        e = min(ex["to_time"].date(), to_date)
        dates = missions_by_emp.setdefault(ex["employee_id"], set())
        while d <= e:
            dates.add(d)
            d += datetime.timedelta(days=1)

    emp_ids = list(qs.values_list("id", flat=True))
    existing = set(
        AttendanceDay.objects.filter(
            employee_id__in=emp_ids,
            work_date__gte=from_date,
            work_date__lte=to_date,
        ).values_list("employee_id", "work_date")
    )

    created = 0
    for emp in qs:
        leave_dates = leaves_by_emp.get(emp.pk, set())
        mission_dates = missions_by_emp.get(emp.pk, set())
        d = max(from_date, emp.hire_date or from_date)
        while d <= to_date:
            if d.weekday() in weekdays and d not in holidays and (emp.pk, d) not in existing:
                if d in leave_dates:
                    state = AttendanceDay.State.LEAVE
                elif d in mission_dates:
                    state = AttendanceDay.State.MISSION
                else:
                    state = AttendanceDay.State.ABSENT
                AttendanceDay.objects.create(
                    employee=emp,
                    work_date=d,
                    branch=emp.branch,
                    shift=emp.shift,
                    state=state,
                    created_by=user,
                )
                created += 1
            d += datetime.timedelta(days=1)
    return created


def decide_and_record_scan(
    employee,
    qr,
    *,
    source=AttendanceScan.Source.PHONE,
    device=None,
    ip_address=None,
    scanned_at=None,
):
    """يقبل/يرفض مسحة ويسجلها — داخل Transaction مع قفل صف اليوم (Atomic)."""
    scanned_at = scanned_at or timezone.now()
    work_date = timezone.localdate(scanned_at)

    with transaction.atomic():
        # قفل اليوم (إن وُجد) لمنع سباق من جهازين بنفس اللحظة
        day = AttendanceDay.objects.select_for_update().filter(
            employee=employee, work_date=work_date
        ).first()

        # منع التكرار الزمني
        last = AttendanceScan.objects.filter(employee=employee).order_by("-scanned_at").first()
        if last and (scanned_at - last.scanned_at).total_seconds() < SCAN_COOLDOWN_SECONDS:
            return _record_scan(employee, day, source, device, ip_address,
                                AttendanceScan.Decision.REJECTED, qr.version,
                                _("مسح متكرر خلال نافذة الأمان"), scanned_at)

        # أول مسح اليوم = دخول، ثاني = خروج
        if day is None:
            day = AttendanceDay.objects.create(
                employee=employee,
                work_date=work_date,
                shift=employee.shift,
                branch=employee.branch,
                state=AttendanceDay.State.PRESENT,
                check_in=scanned_at,
                created_by=qr.created_by,
            )
            scan = _record_scan(employee, day, source, device, ip_address,
                                AttendanceScan.Decision.CHECK_IN, qr.version,
                                _("دخول"), scanned_at)
            _update_worked_and_late(day)
            return scan

        if day.check_out is None:
            day.check_out = scanned_at
            day.save(update_fields=["check_out", "updated_at"])
            scan = _record_scan(employee, day, source, device, ip_address,
                                AttendanceScan.Decision.CHECK_OUT, qr.version,
                                _("خروج"), scanned_at)
            _update_worked_and_late(day)
            return scan

        # مسح ثالث: تحذير (لا يُرفض)
        return _record_scan(employee, day, source, device, ip_address,
                            AttendanceScan.Decision.WARNING, qr.version,
                            _("مسح إضافي بعد الخروج"), scanned_at)


def verify_qr_token(payload: str):
    """التحقق الأمني من QR → (employee, qr, error).

    employee/qr = None عند أي فشل مع error وصف السبب.
    """
    header = verify_payload(payload)
    if header is None:
        return None, None, _("توقيع غير صالح (تزوير محتمل)")

    employee = Employee.objects.filter(id=header["employee_id"]).first()
    if not employee:
        return None, None, _("موظف غير معروف")

    blocked = {
        Employee.EmploymentStatus.SUSPENDED,
        Employee.EmploymentStatus.TERMINATED,
        Employee.EmploymentStatus.RESIGNED,
        Employee.EmploymentStatus.RETIRED,
    }
    if not employee.is_active or employee.employment_status in blocked:
        return None, None, _("حساب الموظف غير نشط")

    qr = EmployeeQR.objects.filter(employee=employee, status=EmployeeQR.Status.ACTIVE).first()
    if not qr:
        return None, None, _("لا يوجد QR نشط للموظف")
    if qr.version != header["v"]:
        return None, None, _("إصدار QR قديم (أُعيد توليده)")

    return employee, qr, None


def _record_scan(employee, day, source, device, ip_address, decision, qr_version, detail, scanned_at):
    return AttendanceScan.objects.create(
        attendanceday=day,
        employee=employee,
        source=source,
        device=device,
        ip_address=ip_address,
        decision=decision,
        qr_version=qr_version,
        result_detail=detail,
        scanned_at=scanned_at,
    )


def _as_time(value):
    """يحمّل القيمة كـ datetime.time (دفاع عن الكائنات غير المحمّلة من DB)."""
    if isinstance(value, str):
        value = TimeField().to_python(value)
    return value


def _shift_datetime(work_date, shift, attr):
    t = _as_time(getattr(shift, attr))
    return datetime.datetime.combine(work_date, t, tzinfo=timezone.get_current_timezone())


def _update_worked_and_late(day: AttendanceDay) -> None:
    """يحسب دقائق العمل والتأخير عند اكتمال الدخول/الخروج (الساعة من الخادم)."""
    if not day.check_in:
        return
    out = day.check_out or timezone.now()
    delta = out - day.check_in
    worked = max(0, int(delta.total_seconds() // 60))

    late = 0
    shift = day.shift
    if shift and not shift.is_flexible and getattr(shift, "start_time", None):
        shift_start = _shift_datetime(day.work_date, shift, "start_time")
        diff_min = (day.check_in - shift_start).total_seconds() // 60
        if diff_min > shift.grace_minutes:
            late = int(diff_min - shift.grace_minutes)

    day.worked_minutes = worked
    day.late_minutes = late
    day.save(update_fields=["worked_minutes", "late_minutes", "updated_at"])


def is_within_shift(day: AttendanceDay, now=None) -> bool:
    now = now or timezone.now()
    shift = day.shift
    if not shift or not getattr(shift, "start_time", None):
        return True
    start = _shift_datetime(day.work_date, shift, "start_time")
    end = _shift_datetime(day.work_date, shift, "end_time")
    return start <= now <= end
