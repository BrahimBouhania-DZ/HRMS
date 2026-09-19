"""إشارات سجل التدقيق: تسجيل كل عملية كتابة (إضافة/تعديل/حذف) + الدخول/الخروج.

يُربط لكل نموذج ملموس (باستثناء AuditLog نفسه وجدول سجلّ الهجرات)،
ويقرأ هوية/عنوان المستخدم من وسيط AuditContextMiddleware (thread-local).
المرجع: docs/10-roadmap.md v2 (Audit — append-only) + docs/09-security.md.
"""

import json

from django.apps import apps
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import class_prepared, post_delete, post_save

from .middleware import audit_context
from .models import AuditLog

_HOOKED = set()


def _excluded(sender):
    """نماذج لا يُسجَّل لها تدقيق: سجل التدقيق نفسه + سجلّ الهجرات (django_migrations)."""
    meta = sender._meta
    return sender is AuditLog or meta.auto_created or meta.db_table == "django_migrations"


def _record(sender, instance, action, snapshot=True):
    user, ip = audit_context()
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None

    SENSITIVE_FIELDS = {"gross_salary", "base_salary", "allowance", "bank_account", "national_id", "net", "amount"}
    
    detail = ""
    if snapshot and action in (AuditLog.Action.CREATE, AuditLog.Action.UPDATE):
        fields = {}
        for f in sender._meta.concrete_fields:
            if f.primary_key:
                continue
            try:
                if f.name in SENSITIVE_FIELDS:
                    fields[f.name] = "***"
                else:
                    fields[f.name] = str(getattr(instance, f.name, ""))
            except Exception:
                fields[f.name] = ""
        detail = json.dumps(fields, ensure_ascii=False)[:2000]

    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=sender._meta.label,
        object_id=str(instance.pk or "")[:50],
        object_repr=str(instance)[:255],
        detail=detail,
        ip=ip or None,
    )


def _record_save(sender, instance, created, **kwargs):
    action = AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE
    _record(sender, instance, action)


def _record_delete(sender, instance, **kwargs):
    _record(sender, instance, AuditLog.Action.DELETE, snapshot=False)


def _hook_model(sender, **kwargs):
    if _excluded(sender):
        return
    label = f"{sender._meta.app_label}.{sender._meta.model_name}"
    if label in _HOOKED:
        return
    _HOOKED.add(label)
    post_save.connect(_record_save, sender=sender, weak=False, dispatch_uid=f"audit-save-{label}")
    post_delete.connect(_record_delete, sender=sender, weak=False, dispatch_uid=f"audit-del-{label}")


class_prepared.connect(_hook_model, weak=False)


def hook_all_models():
    """يُربط الإشارات بكل النماذج المحمّلة — يُستدعى من CoreConfig.ready().

    class_prepared وحده لا يكفي لأن ready() يُنفَّذ بعد تجهيز كل النماذج.
    """
    for model in apps.get_models():
        _hook_model(model)


def _log_auth(action):
    def handler(sender, user, request, **kwargs):
        _, ip = audit_context()
        AuditLog.objects.create(
            user=user,
            action=action,
            model_name="auth.user",
            object_id=str(user.pk),
            object_repr=str(user),
            ip=ip or None,
        )

    return handler


user_logged_in.connect(_log_auth(AuditLog.Action.LOGIN), weak=False, dispatch_uid="audit-login")
user_logged_out.connect(_log_auth(AuditLog.Action.LOGOUT), weak=False, dispatch_uid="audit-logout")
