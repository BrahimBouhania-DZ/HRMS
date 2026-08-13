"""ماسح التنبيهات المجدولة — انتهاء العقود/الوثائق + نهاية فترة التجربة (v2).

المرجع: docs/10-roadmap.md v2 (Notifications — جدولة انتهاء) + docs/03 §3.9.
- يُشغَّل يوميًا عبر cron: manage.py run_scheduled_alerts
- يعتمد على ScheduledAlert (سجل وحيد لكل reference) لمنع التكرار.
- المتلقون: أصحاب صلاحية HR/إشراف + المشرفون (مثل معتمدي الإجازات).
- commit=False (وضع التجربة): يعرض الإحصاء دون أي كتابة في قاعدة البيانات.
"""

from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Notification, ScheduledAlert

# نوافذ التنبيه (أيام قبل الاستحقاق)
CONTRACT_WINDOW_DAYS = 30
DOCUMENT_WINDOW_DAYS = 30
PROBATION_WINDOW_DAYS = 14
PROBATION_PERIOD_DAYS = 90  # فترة تجربة نموذجية 3 أشهر


def _fire(alert_type, notif_type, target_date, reference, payload, recipients, title, body):
    """يُنشئ التنبيه مرة واحدة فقط لكل (type+date+reference) ويُشعل الإشعارات.

    يرجع True إن أُطلق تنبيه جديد، False إن سبق إطلاقه.
    """
    alert, created = ScheduledAlert.objects.get_or_create(
        alert_type=alert_type,
        target_date=target_date,
        reference=reference,
        defaults={"payload_json": payload, "fired_at": timezone.now()},
    )
    if not created:
        return False

    from .services import notify

    for user in recipients:
        notify(user, notif_type, title, body)
    return True


def _window(start_date, days: int):
    return start_date + timedelta(days=days)


def _count(fired_flags):
    return sum(1 for f in fired_flags if f)


def scan_contract_expiries(today=None, commit=True):
    """عقود تنتهي خلال CONTRACT_WINDOW_DAYS (ولم تنتهِ بعد، ولم تُجدَّد)."""
    from apps.employees.models import Contract

    today = today or timezone.localdate()
    horizon = _window(today, CONTRACT_WINDOW_DAYS)
    # استثناء العقود التي استُبدلت بعقد تجديد (previous_contract → renewal)
    qs = (
        Contract.objects.filter(
            end_date__isnull=False,
            end_date__gte=today,
            end_date__lte=horizon,
            renewal__isnull=True,
        )
        .select_related("employee")
        .order_by("end_date")
    )
    recipients = _recipients()
    results = []
    for contract in qs:
        if not commit:
            results.append(True)
            continue
        results.append(_fire(
            "contract_expiry",
            Notification.Type.CONTRACT_EXPIRING,
            contract.end_date,
            f"contract:{contract.pk}",
            {"contract": contract.contract_number, "employee": str(contract.employee)},
            recipients,
            _("عقد يقترب من الانتهاء"),
            _("عقد %(num)s للموظف %(emp)s ينتهي في %(date)s (%(days)s يومًا)") % {
                "num": contract.contract_number, "emp": contract.employee,
                "date": contract.end_date, "days": (contract.end_date - today).days,
            },
        ))
    return _count(results)


def scan_document_expiries(today=None, commit=True):
    """وثائق تنتهي خلال DOCUMENT_WINDOW_DAYS (ولم تنتهِ بعد)."""
    from apps.employees.models import Document

    today = today or timezone.localdate()
    horizon = _window(today, DOCUMENT_WINDOW_DAYS)
    qs = (
        Document.objects.filter(
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=horizon,
        )
        .select_related("employee")
        .order_by("expiry_date")
    )
    recipients = _recipients()
    results = []
    for doc in qs:
        if not commit:
            results.append(True)
            continue
        results.append(_fire(
            "document_expiry",
            Notification.Type.DOCUMENT_EXPIRING,
            doc.expiry_date,
            f"document:{doc.pk}",
            {"document": doc.title, "employee": str(doc.employee)},
            recipients,
            _("وثيقة تنتهي صلاحيتها"),
            _("وثيقة %(doc)s للموظف %(emp)s تنتهي في %(date)s") % {
                "doc": doc.title, "emp": doc.employee, "date": doc.expiry_date,
            },
        ))
    return _count(results)


def scan_probation_end(today=None, commit=True):
    """موظفون تحت التجربة تنتهي مدتها خلال PROBATION_WINDOW_DAYS."""
    from apps.employees.models import Employee

    today = today or timezone.localdate()
    horizon = _window(today, PROBATION_WINDOW_DAYS)
    qs = Employee.objects.filter(
        employment_status=Employee.EmploymentStatus.PROBATION,
        hire_date__isnull=False,
        hire_date__gte=today - timedelta(days=PROBATION_PERIOD_DAYS),
        hire_date__lte=horizon - timedelta(days=PROBATION_PERIOD_DAYS),
    ).order_by("hire_date")
    recipients = _recipients()
    results = []
    for emp in qs:
        end = emp.hire_date + timedelta(days=PROBATION_PERIOD_DAYS)
        if not commit:
            results.append(True)
            continue
        results.append(_fire(
            "probation_end",
            Notification.Type.PROBATION_END,
            end,
            f"probation:{emp.pk}",
            {"employee": str(emp)},
            recipients,
            _("نهاية فترة التجربة"),
            _("تنتهي فترة تجربة الموظف %(emp)s في %(date)s (%(days)s يومًا)") % {
                "emp": emp, "date": end, "days": (end - today).days,
            },
        ))
    return _count(results)


def run_all(today=None, commit=True) -> dict:
    """يشغّل كل الماسحات ويعيد إحصاء ما أُطلق (أو ما سَيُطلق في وضع التجربة)."""
    today = today or timezone.localdate()
    return {
        "contracts": scan_contract_expiries(today, commit),
        "documents": scan_document_expiries(today, commit),
        "probation": scan_probation_end(today, commit),
    }


def _recipients():
    """المستخدمون المتلقون لتنبيهات النظام (HR/مشرفون/مشرفو النظام)."""
    from apps.notif.services import _potential_approvers

    return _potential_approvers()
