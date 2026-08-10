"""منطق الإجازات: حساب الأيام + دورة الطلب→الموافقة→خصم الرصيد (S4).

المرجع: docs/10-roadmap.md §4 (قبول v1: دورة إجازة كاملة) + docs/03 §3.5.
"""

import datetime
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import LeaveApproval, LeaveBalance, LeaveRequest, PublicHoliday

# أيام نهاية الأسبوع (date.weekday(): Mon=0 .. Sun=6) — قابلة للتكوين.
# الافتراضي: الجمعة(4) + السبت(5).
WEEKEND_DAYS = set(getattr(settings, "HRMS_WEEKEND_DAYS", [4, 5]))


class LeaveError(Exception):
    """رفض تجاري لقاعدة إجازات."""


def calculate_leave_days(from_date: datetime.date, to_date: datetime.date, branch=None) -> float:
    """أيام العمل الفعلية = الأيام − عطل نهاية الأسبوع − العطل الرسمية (غير المتكررة ضمن المدى)."""
    if to_date < from_date:
        raise LeaveError(_("نهاية الفترة يجب أن تكون بعد بدايتها"))

    count = 0
    d = from_date
    holidays = _holiday_dates(branch, from_date, to_date)
    while d <= to_date:
        if d.weekday() not in WEEKEND_DAYS and d not in holidays:
            count += 1
        d += datetime.timedelta(days=1)
    return float(count)


def _holiday_dates(branch, from_date=None, to_date=None):
    """تواريخ العطل الرسمية ضمن المدى (المتكررة تُدمج لكل سنة في المدى)."""
    from_date = from_date or datetime.date(2000, 1, 1)
    to_date = to_date or datetime.date(2100, 1, 1)
    dates = set()
    qs = PublicHoliday.objects.all()
    if branch:
        qs = qs.filter(branch=branch)
    for h in qs:
        if h.is_recurring:
            for year in range(from_date.year, to_date.year + 1):
                try:
                    dates.add(h.date.replace(year=year))
                except ValueError:
                    continue
        else:
            dates.add(h.date)
    return dates


def get_or_create_balance(employee, leave_type, year) -> LeaveBalance:
    """رصيد سنة (يُنشأ تلقائيًا مع منح أيام السنة عند أول طلب)."""
    balance, created = LeaveBalance.objects.get_or_create(
        employee=employee, leave_type=leave_type, year=year
    )
    if created and leave_type.days_per_year > 0:
        balance.granted = leave_type.days_per_year
        balance.save(update_fields=["granted"])
    return balance


def submit_request(employee, leave_type, from_date, to_date, reason="", requested_by=None) -> LeaveRequest:
    """تحقق + إنشاء طلب بحالة pending (الرصيد يُخصم عند الاعتماد فقط)."""
    if not leave_type.is_active:
        raise LeaveError(_("نوع الإجازة غير مفعّل"))
    days = calculate_leave_days(from_date, to_date, employee.branch)
    if days <= 0:
        raise LeaveError(_("الفترة لا تحتوي أي يوم عمل"))

    year = from_date.year
    if leave_type.days_per_year > 0 and not leave_type.is_unpaid:
        balance = get_or_create_balance(employee, leave_type, year)
        if balance.remaining < days:
            raise LeaveError(_("الرصيد غير كافٍ (المتبقي %s يوم)") % (balance.remaining,))

    request = LeaveRequest.objects.create(
        employee=employee,
        leave_type=leave_type,
        from_date=from_date,
        to_date=to_date,
        days=days,
        reason=reason,
        status=LeaveRequest.Status.PENDING,
        current_level=1,
        submitted_at=timezone.now(),
        requested_by=requested_by,
        created_by=requested_by,
    )
    from apps.notif.services import notify_leave_submitted

    notify_leave_submitted(request, requested_by)
    return request


def approve_request(request: LeaveRequest, approver, comment="") -> LeaveRequest:
    """خطوة اعتماد: يسجلها، يرفع المستوى أو يعتمد الطلب ويخصم الرصيد."""
    if request.status != LeaveRequest.Status.PENDING:
        raise LeaveError(_("الطلب ليس قيد الانتظار"))

    level = request.current_level
    if LeaveApproval.objects.filter(leave_request=request, level=level).exists():
        raise LeaveError(_("هذا المستوى أُعتمد مسبقًا"))

    LeaveApproval.objects.create(
        leave_request=request,
        level=level,
        approver=approver,
        action=LeaveApproval.Action.APPROVED,
        comment=comment,
        updated_by=approver,
    )

    if level < request.leave_type.requires_approval_levels:
        request.current_level = level + 1
        request.updated_by = approver
        request.save(update_fields=["current_level", "updated_at", "updated_by"])
        return request

    request.status = LeaveRequest.Status.APPROVED
    request.updated_by = approver
    request.save(update_fields=["status", "updated_at", "updated_by"])
    _deduct_balance(request)
    from apps.notif.services import notify_leave_decided

    notify_leave_decided(request, True, approver)
    return request


def reject_request(request: LeaveRequest, approver, comment="") -> LeaveRequest:
    """رفض نهائي في أي مستوى."""
    if request.status != LeaveRequest.Status.PENDING:
        raise LeaveError(_("الطلب ليس قيد الانتظار"))

    LeaveApproval.objects.create(
        leave_request=request,
        level=request.current_level,
        approver=approver,
        action=LeaveApproval.Action.REJECTED,
        comment=comment,
        updated_by=approver,
    )
    request.status = LeaveRequest.Status.REJECTED
    request.updated_by = approver
    request.save(update_fields=["status", "updated_at", "updated_by"])
    from apps.notif.services import notify_leave_decided

    notify_leave_decided(request, False, approver)
    return request


def cancel_request(request: LeaveRequest, user) -> LeaveRequest:
    """إلغاء الطلب من صاحبه (قبل الاعتماد فقط)."""
    if request.status not in (LeaveRequest.Status.PENDING, LeaveRequest.Status.DRAFT):
        raise LeaveError(_("لا يمكن إلغاء طلب غير معلق"))
    request.status = LeaveRequest.Status.CANCELLED
    request.updated_by = user
    request.save(update_fields=["status", "updated_at", "updated_by"])
    from apps.notif.services import notify_leave_cancelled

    notify_leave_cancelled(request)
    return request


def adjust_balance(employee, leave_type, year, amount, user) -> LeaveBalance:
    """تسوية رصيد (leave.balance.adjust)."""
    balance = get_or_create_balance(employee, leave_type, year)
    balance.adjusted = (balance.adjusted or 0) + amount
    balance.updated_by = user
    balance.save(update_fields=["adjusted", "updated_at", "updated_by"])
    return balance


def _deduct_balance(request: LeaveRequest) -> None:
    """خصم أيام الطلب المعتمد من رصيد السنة (لا يُخصم تحت الصفر)."""
    balance = get_or_create_balance(request.employee, request.leave_type, request.from_date.year)
    balance.used = (balance.used or 0) + Decimal(str(request.days))
    balance.updated_by = request.updated_by
    balance.save(update_fields=["used", "updated_at", "updated_by"])
