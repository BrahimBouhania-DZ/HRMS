"""منطق الحضور: خوارزمية قرار المسح + حساب التأخير (T-QR-3, T-019).

المرجع: docs/06-qr-system.md §5 (خوارزمية القرار) و §6 (منع التكرار).
"""

from datetime import datetime

from django.db import transaction
from django.db.models.fields import TimeField
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.employees.models import Employee, EmployeeQR
from apps.employees.qr_engine import verify_payload

from .models import AttendanceDay, AttendanceScan

# نافذة منع التكرار (ثوانٍ)
SCAN_COOLDOWN_SECONDS = 60


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
    return datetime.combine(work_date, t, tzinfo=timezone.get_current_timezone())


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
