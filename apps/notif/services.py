"""خدمة الإشعارات — إنشاء in_app + بريد LAN مع احترام التفضيلات (S4/v2).

المرجع: docs/03 §3.9 + docs/10-roadmap.md v2 (بريد LAN).
القناة البريدية تُفعَّل لكل نوع عبر تفضيل NotificationPref (channel=email)،
وتُرسل عبر إعدادات البريد في base.py — مفتوحة على SMTP LAN.
"""

from django.utils.translation import gettext as _

from .models import Notification, NotificationPref


def _pref_enabled(user, type, channel) -> bool:
    """تفضيل القناة لنوع معين — غياب التفضيل يعني مفعّلًا (افتراضي)."""
    pref = NotificationPref.objects.filter(user=user, type=type, channel=channel).first()
    return pref is None or pref.enabled


def notify(user, type, title, body="", related=None):
    """ينشئ إشعار in_app إن كانت قناة in_app مفعّلة، ويرسل بريد LAN إن كان مفعّلًا."""
    if user is None:
        return None

    notification = None
    if _pref_enabled(user, type, NotificationPref.Channel.IN_APP):
        related_model = related_id = None
        if related is not None:
            related_model = related.__class__.__name__.lower()
            related_id = related.pk

        notification = Notification.objects.create(
            user=user,
            type=type,
            title=title,
            body=body,
            related_model=related_model or "",
            related_id=related_id,
        )

    if _pref_enabled(user, type, NotificationPref.Channel.EMAIL):
        _send_email_notification(user, type, title, body)

    return notification


def _send_email_notification(user, type, title, body):
    """يرسل بريد LAN إن كانت الميزة مفعّلة (HRMS_EMAIL_ENABLED) وبريد المستخدم معروف."""
    address = getattr(user, "email", "") or ""
    if not address:
        return False
    from django.conf import settings
    from django.core.mail import send_mail

    if not settings.HRMS_EMAIL_ENABLED:
        return False
    send_mail(
        subject=f"[HRMS] {title}",
        message=body or title,
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=[address],
        fail_silently=True,
    )
    return True


def set_notification_pref(user, type, channel, enabled):
    """يضبط تفضيل قناة لنوع إشعار (إنشاء/تحديث)."""
    pref, _ = NotificationPref.objects.get_or_create(
        user=user, type=type, channel=channel,
        defaults={"enabled": enabled},
    )
    if pref.enabled != enabled:
        pref.enabled = enabled
        pref.save(update_fields=["enabled"])
    return pref


def email_prefs(user) -> dict:
    """خريطة النوع ← الحالة الفعلية للقناة البريدية (غياب التفضيل = مفعّل)."""
    disabled = set(
        NotificationPref.objects.filter(user=user, channel=NotificationPref.Channel.EMAIL)
        .filter(enabled=False).values_list("type", flat=True)
    )
    return {t: t not in disabled for t, _ in Notification.Type.choices}


def notify_leave_submitted(request, requester):
    """يحذّر المعتمدين المحتملين (leave.approve) بطلب جديد ضمن نطاقهم."""
    from apps.auth_app.scopes import employee_scope_queryset

    for user in _potential_approvers():
        # النطاق: لا يشمل الموظف صاحب الطلب ولا من لا يراه
        scope = employee_scope_queryset(user)
        if scope.filter(pk=request.employee_id).exists() and user != requester:
            notify(
                user,
                Notification.Type.LEAVE_SUBMITTED,
                _("طلب إجازة جديد من %(employee)s") % {"employee": request.employee},
                _("%(type)s — %(from)s إلى %(to)s (%(days)s يوم)") % {"type": request.leave_type, "from": request.from_date, "to": request.to_date, "days": request.days},
                related=request,
            )


def notify_leave_decided(request, approved: bool, decider=None):
    """يخبر الموظف بنتيجة طلبه."""
    employee_user = getattr(request.employee, "user", None)
    if employee_user is None:
        return
    if approved:
        notify(
            employee_user,
            Notification.Type.LEAVE_APPROVED,
            _("تم اعتماد إجازتك"),
            _("%(type)s — %(from)s إلى %(to)s") % {"type": request.leave_type, "from": request.from_date, "to": request.to_date},
            related=request,
        )
    else:
        notify(
            employee_user,
            Notification.Type.LEAVE_REJECTED,
            _("تم رفض طلب إجازتك"),
            _("%(type)s — %(from)s إلى %(to)s") % {"type": request.leave_type, "from": request.from_date, "to": request.to_date},
            related=request,
        )


def notify_leave_cancelled(request):
    """يخبر الموظف (عادة من فعل الإلغاء) والجهة التي اعتمدت — مبسط: صاحب الطلب فقط."""
    employee_user = getattr(request.employee, "user", None)
    if employee_user is None:
        return
    notify(
        employee_user,
        Notification.Type.LEAVE_CANCELLED,
        _("أُلغي طلب إجازتك"),
        _("%(type)s — %(from)s إلى %(to)s") % {"type": request.leave_type, "from": request.from_date, "to": request.to_date},
        related=request,
    )


def _potential_approvers():
    """مستخدمون بصلاحية leave.approve أو مشرفون/HR (يُصفّى بالنطاق في المتلقي)."""
    from django.contrib.auth import get_user_model

    from apps.auth_app.models import RoleMember

    User = get_user_model()
    role_codes = ("hr_manager", "supervisor")
    ids = set(RoleMember.objects.filter(role__code__in=role_codes).values_list("user_id", flat=True))
    ids.update(
        User.objects.filter(is_superuser=True).values_list("id", flat=True)
    )
    return User.objects.filter(id__in=ids, is_active=True)


def mark_as_read(user, notification_id):
    Notification.objects.filter(pk=notification_id, user=user).update(is_read=True)


def mark_all_as_read(user):
    Notification.objects.filter(user=user, is_read=False).update(is_read=True)


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, is_read=False).count()
