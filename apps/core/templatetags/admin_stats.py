"""تاج قالب — إحصائيات لوحة الإدارة (تُعرض أعلى صفحة /admin/)."""

from django import template
from django.utils import timezone
from django.utils.translation import gettext as _

register = template.Library()


@register.filter
def get_item(value, key):
    """فلتر عام للوصول إلى عنصر من قاموس داخل القالب (e.g. row|get_item:col)."""
    try:
        return value.get(key, "—")
    except (AttributeError, TypeError):
        return "—"


@register.simple_tag
def admin_stats():
    """أرقام سريعة للوحة الإدارة — تُحسب لحظيًا من قاعدة البيانات."""
    from django.apps import apps

    Employee = apps.get_model("employees", "Employee")
    Branch = apps.get_model("org", "Branch")
    AttendanceDay = apps.get_model("attendance", "AttendanceDay")
    LeaveRequest = apps.get_model("leave", "LeaveRequest")
    QrDevice = apps.get_model("devices", "QrDevice")
    EmployeeQR = apps.get_model("employees", "EmployeeQR")

    today = timezone.localdate()
    return [
        {
            "label": _("موظف نشط"),
            "value": Employee.objects.filter(is_active=True).count(),
            "icon": "👥",
            "tone": "blue",
        },
        {
            "label": _("الفروع"),
            "value": Branch.objects.count(),
            "icon": "🏢",
            "tone": "gold",
        },
        {
            "label": _("حاضر اليوم"),
            "value": AttendanceDay.objects.filter(
                work_date=today, state=AttendanceDay.State.PRESENT
            ).count(),
            "icon": "✅",
            "tone": "green",
        },
        {
            "label": _("طلبات إجازة معلقة"),
            "value": LeaveRequest.objects.filter(
                status=LeaveRequest.Status.PENDING
            ).count(),
            "icon": "⏳",
            "tone": "amber",
        },
        {
            "label": _("أجهزة QR نشطة"),
            "value": QrDevice.objects.filter(status=QrDevice.Status.ACTIVE).count(),
            "icon": "📡",
            "tone": "blue",
        },
        {
            "label": _("رموز QR نشطة"),
            "value": EmployeeQR.objects.filter(
                status=EmployeeQR.Status.ACTIVE
            ).count(),
            "icon": "🪪",
            "tone": "gold",
        },
    ]
