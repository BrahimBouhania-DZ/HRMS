"""خدمات الرواتب — توليد الدورات، انتقالات الحالة، تصدير البنك، نهاية الخدمة (v2).

المرجع: docs/03 §3.6 + docs/01 §8.6 (BR-PAY) + docs/10-roadmap.md v2 (Payroll).

القواعد:
    BR-PAY-001  الفترة مغلقة بعد الاعتماد/التجميد؛ التعديل بإذن وأثر تدقيق.
    BR-PAY-002  الخصم اليومي = (الأجر الأساسي / أيام العمل الرسمية للفترة).
    BR-PAY-003  لا تُدرج قسائم الموظفين غير المفعّلين إلا بعد تسوية نهاية الخدمة.
    BR-PAY-004  المكافأة/الخصم اليدوي يتطلب مستندًا مساندًا (note إلزامي).
    BR-PAY-005  نهاية الخدمة تُحسب آليًا بقواعد قابلة للتكوين.

إشارة الأسطر: PayrollLine.amount مُوقَّعة — موجب = إضافة، سالب = خصم.
"""

import calendar
import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.attendance.models import AttendanceDay
from apps.leave.models import PublicHoliday
from apps.org.models import Branch

from .models import EndOfService, PayElement, PayrollLine, PayRun, Payslip


class PayrollError(Exception):
    """خطأ منطقي في دورة الرواتب (يُعرض للمستخدم)."""


# ---- تكوين قابل للتعديل (BR-PAY-005) --------------------------------------

# عامل مكافأة نهاية الخدمة: (سنوات الخدمة × الأجر اليومي × هذا العامل)
EOS_REWARD_FACTOR = 0.5


def _period_range(period_code: str) -> tuple[datetime.date, datetime.date]:
    """يحلل '2026-08' إلى (بداية الشهر، نهاية الشهر)."""
    try:
        year, month = (int(x) for x in period_code.split("-"))
        last_day = calendar.monthrange(year, month)[1]
        return datetime.date(year, month, 1), datetime.date(year, month, last_day)
    except (ValueError, AttributeError):
        raise PayrollError(_("صيغة فترة غير صالحة: %(code)s (مثال: 2026-08)") % {"code": period_code})


def official_workdays(period_code: str, branch: Branch) -> int:
    """أيام العمل الرسمية للفترة = أيام العمل الأسبوعية − العطل الرسمية (BR-PAY-002)."""
    start, end = _period_range(period_code)
    days = 0
    day = start
    while day <= end:
        if day.weekday() < 5:  # الاثنين..الجمعة
            days += 1
        day += datetime.timedelta(days=1)
    holidays = PublicHoliday.objects.filter(branch=branch, date__gte=start, date__lte=end).count()
    return max(days - holidays, 1)


def _employee_base_salary(employee) -> float:
    """الأجر الأساسي من أحدث عقد للموظف (أساسي للحساب)."""
    from apps.employees.models import Contract

    contract = Contract.objects.filter(employee=employee).order_by("-start_date", "-pk").first()
    return float(contract.base_salary) if contract else 0.0


def _element_amount(element: PayElement, base_salary, attended_days: int) -> float:
    """مبلغ عنصر أجر (بالمقدار الموجب؛ الإشارة حسب kind عند التسجيل)."""
    if element.calculation == PayElement.Calculation.PERCENT_OF_BASIC:
        return base_salary * float(element.percent) / 100
    if element.calculation == PayElement.Calculation.ATTENDANCE_BASED:
        return float(element.amount) * attended_days
    return float(element.amount)


@transaction.atomic
def generate_payrun(period_code: str, branch: Branch, user, *, force=False) -> PayRun:
    """يُنشئ دورة رواتب: قسائم + أسطر لكل الموظفين النشطين في الفرع.

    force=True يتجاوز فحص وجود دورة (للاختبارات).
    """
    start, end = _period_range(period_code)
    if not force and PayRun.objects.filter(period_code=period_code, branch=branch).exists():
        raise PayrollError(_("توجد دورة رواتب مسبقًا للفترة %(period)s في %(branch)s") % {"period": period_code, "branch": branch})

    from apps.employees.models import Employee

    workdays = official_workdays(period_code, branch)
    elements = list(PayElement.objects.filter(is_active=True).order_by("code"))

    employees = Employee.objects.filter(
        branch=branch,
        is_active=True,
        employment_status__in=(Employee.EmploymentStatus.ACTIVE, Employee.EmploymentStatus.PROBATION),
        hire_date__lte=end,
    ).order_by("employee_code")

    payrun = PayRun.objects.create(
        period_code=period_code,
        branch=branch,
        status=PayRun.Status.DRAFT,
        generated_by=user,
        generated_at=timezone.now(),
        created_by=user,
        updated_by=user,
    )

    run_earnings = run_deductions = 0

    for emp in employees:
        base = _employee_base_salary(emp)
        days = AttendanceDay.objects.filter(employee=emp, work_date__gte=start, work_date__lte=end)
        attended = days.filter(state=AttendanceDay.State.PRESENT).count()
        absent = days.filter(state=AttendanceDay.State.ABSENT).count()
        leave = days.filter(state=AttendanceDay.State.LEAVE).count()

        lines = []
        for element in elements:
            if not element.applies_to_all:
                continue
            value = _element_amount(element, base, attended)
            if value == 0:
                continue
            signed = value if element.kind == PayElement.Kind.EARNING else -value
            lines.append(PayrollLine(
                pay_run=payrun, employee=emp, element=element,
                amount=signed, created_by=user, updated_by=user,
            ))

        # خصم الغياب (BR-PAY-002): (الأساسي / أيام العمل) × أيام الغياب
        if absent and workdays:
            daily = base / workdays
            absence_deduction = daily * absent
            lines.append(PayrollLine(
                pay_run=payrun, employee=emp, element=None,
                amount=-absence_deduction, note=_("خصم غياب %(days)s يوم") % {"days": absent},
                created_by=user, updated_by=user,
            ))

        earnings = sum(l.amount for l in lines if l.amount > 0)
        deductions = -sum(l.amount for l in lines if l.amount < 0)
        net = base + earnings - deductions

        PayrollLine.objects.bulk_create(lines)
        Payslip.objects.create(
            pay_run=payrun, employee=emp,
            basic_salary=base,
            total_earnings=earnings,
            total_deductions=deductions,
            net=net,
            attended_days=attended,
            absent_days=absent,
            leave_days=leave,
            created_by=user, updated_by=user,
        )
        run_earnings += earnings
        run_deductions += deductions

    payrun.total_earnings = run_earnings
    payrun.total_deductions = run_deductions
    payrun.total_net = sum(p.net for p in payrun.payslips.all())
    payrun.save(update_fields=["total_earnings", "total_deductions", "total_net", "updated_at"])

    if not payrun.payslips.exists():
        raise PayrollError(_("لا موظفون نشطون في هذا الفرع للفترة المحددة"))

    return payrun


# ---- انتقالات الحالة (BR-PAY-001) ------------------------------------------

def review_payrun(payrun: PayRun, user) -> PayRun:
    """draft → reviewing (مراجعة الكشف)."""
    if payrun.status != PayRun.Status.DRAFT:
        raise PayrollError(_("لا يمكن المراجعة إلا من حالة المسودة"))
    return _set_status(payrun, PayRun.Status.REVIEWING, user)


def approve_payrun(payrun: PayRun, user) -> PayRun:
    """reviewing → approved (اعتماد وتجميد الفترة)."""
    if payrun.status != PayRun.Status.REVIEWING:
        raise PayrollError(_("الاعتماد يتم فقط بعد المراجعة"))
    payrun.approved_by = user
    payrun.approved_at = timezone.now()
    _set_status(payrun, PayRun.Status.APPROVED, user)
    payrun.save(update_fields=["approved_by", "approved_at", "updated_at"])
    return payrun


def freeze_payrun(payrun: PayRun, user) -> PayRun:
    """approved → frozen (إغلاق نهائي؛ أي تعديل لاحق ممنوع — BR-PAY-001)."""
    if payrun.status != PayRun.Status.APPROVED:
        raise PayrollError(_("التجميد يتم فقط بعد الاعتماد"))
    return _set_status(payrun, PayRun.Status.FROZEN, user)


def _set_status(payrun: PayRun, status: str, user) -> PayRun:
    payrun.status = status
    payrun.updated_by = user
    payrun.save(update_fields=["status", "updated_at", "updated_by"])
    return payrun


# ---- تصدير البنك (FR-PAY-008) ----------------------------------------------

def bank_rows(payrun: PayRun) -> list[dict]:
    """أسطر تصدير البنك (الموظفون الذين لديهم حساب بنكي)."""
    rows = []
    for p in payrun.payslips.select_related("employee").order_by("employee__employee_code"):
        emp = p.employee
        if not emp.bank_account:
            continue
        rows.append({
            "employee_code": emp.employee_code,
            "name": f"{emp.first_name_ar} {emp.last_name_ar}",
            "bank_account": emp.bank_account,
            "net": p.net,
        })
    return rows


# ---- نهاية الخدمة (BR-PAY-005) ---------------------------------------------

def calculate_end_of_service(employee, termination_date, user, *, reward_factor: float = EOS_REWARD_FACTOR) -> EndOfService:
    """يحسب نهاية الخدمة آليًا ويُنشئ سجلًا بحالة مسودة.

    reward = سنوات الخدمة × الأجر اليومي × العامل (قابل للتكوين)
    unused_leave = (أيام إجازة متبقية) × الأجر اليومي
    notice = شهر أساسي واحد افتراضي.
    """
    from apps.leave.models import LeaveBalance, LeaveType
    from django.db.models import Sum

    hire = employee.hire_date or employee.created_at.date()
    years = max((termination_date - hire).days / 365.25, 0)
    base = _employee_base_salary(employee)
    daily = base / 30

    annual = LeaveType.objects.filter(is_unpaid=False).first()
    remaining = 0
    if annual:
        agg = LeaveBalance.objects.filter(
            employee=employee, leave_type=annual, year=termination_date.year
        ).aggregate(total=Sum("granted") - Sum("used") - Sum("carried_from") - Sum("adjusted"))
        remaining = max(float(agg["total"] or 0), 0)

    reward = years * daily * reward_factor
    unused = remaining * daily
    notice = base
    net = reward + unused + notice

    return EndOfService.objects.create(
        employee=employee,
        termination_date=termination_date,
        total_years=round(years, 2),
        service_reward=round(reward, 2),
        unused_leave_comp=round(unused, 2),
        notice_period=round(notice, 2),
        deductions=0,
        net=round(net, 2),
        created_by=user, updated_by=user,
    )
