"""خدمة جدولة التقارير (T-REP-5) — توليد دوري + إشعارات المستلمين.

المرجع: docs/08-reports.md §5 + docs/03 §3.12.
- يُشغَّل عبر cron: manage.py run_scheduled_reports
- يستخدم نفس العروض/الخدمات (get_rows + header) بلا HTTP.
- الملفات تُخزَّن تحت MEDIA_ROOT/reports/ مع انتهاء صلاحية.
"""

import io
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.models import AuditLog
from apps.notif.services import notify as notify_user

from .models import ReportDefinition, ReportGeneratedFile, ReportJob
from .views import _BaseReportView, _report_meta

REPORT_RETENTION_DAYS = 30
SYSTEM_NOTIFICATION_TYPE = "system"


def _view_for_code(code: str):
    """يعيد كلاس عرض التقرير حسب رمزه (REP-XX)."""
    for cls in _BaseReportView.__subclasses__():
        if getattr(cls, "report_code", None) == code:
            return cls
    return None


def _output_dir():
    path = settings.MEDIA_ROOT / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _render(definition: ReportDefinition, user) -> bytes:
    """يولّد ملف التقرير (pdf/xlsx/csv) من التعريف ويعيد محتواه بايتات."""
    from . import services

    view_cls = _view_for_code(definition.code)
    if view_cls is None:
        raise ValueError(_("رمز تقرير غير معروف: %s") % definition.code)

    filters = definition.filters_json or {}
    rows = view_cls().get_rows(user, filters)
    header = _report_meta(definition.code).get("header", [])

    if definition.template_type == ReportDefinition.Template.CSV:
        buffer = io.StringIO()
        services.export_csv(buffer, header, rows)
        return buffer.getvalue().encode("utf-8")

    if definition.template_type == ReportDefinition.Template.XLSX:
        buffer = io.BytesIO()
        services.export_xlsx(buffer, header, rows, definition.name_ar)
        return buffer.getvalue()

    buffer = io.BytesIO()
    services.export_pdf(buffer, header, rows, definition.name_ar)
    return buffer.getvalue()


def _stamp_filename(definition: ReportDefinition) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{definition.code}_{ts}.{definition.template_type}"


def generate_report(definition: ReportDefinition, user) -> ReportJob:
    """ينفّذ تقريرًا (يدويًا/دوريًا) وينشئ تنفيذًا + ملفًا ناتجًا."""
    job = ReportJob.objects.create(report=definition, requested_by=user, status=ReportJob.Status.RUNNING,
                                   started_at=timezone.now())
    try:
        data = _render(definition, user)
        rel = _output_dir() / _stamp_filename(definition)
        rel.write_bytes(data)
        ReportGeneratedFile.objects.create(
            job=job, file_path=str(rel), format=definition.template_type,
            size_bytes=len(data),
            expires_at=timezone.now() + timedelta(days=REPORT_RETENTION_DAYS),
        )
        job.status = ReportJob.Status.DONE
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "finished_at"])
    except Exception as exc:  # noqa: BLE001 — فشل التنفيذ لا يوقف بقية التعريفات
        job.status = ReportJob.Status.FAILED
        job.finished_at = timezone.now()
        job.error = str(exc)[:500]
        job.save(update_fields=["status", "finished_at", "error"])
    return job


def _is_due(definition: ReportDefinition, now) -> bool:
    """هل حان موعد تنفيذ التقرير الآن؟ (يومي/أسبوعي/شهري + وقت)."""
    if not definition.is_active or definition.schedule == ReportDefinition.Schedule.MANUAL:
        return False
    if definition.run_at is not None and now.time() < definition.run_at:
        return False
    if definition.schedule == ReportDefinition.Schedule.WEEKLY:
        if definition.weekday is None or now.weekday() != definition.weekday:
            return False
    if definition.schedule == ReportDefinition.Schedule.MONTHLY:
        if definition.day_of_month is None or now.day != definition.day_of_month:
            return False
    if definition.last_run_at is not None:
        last = timezone.localtime(definition.last_run_at)
        same_window = last.date() == now.date()
        if same_window:
            return False
        if definition.schedule == ReportDefinition.Schedule.WEEKLY and last.isocalendar()[:2] == now.isocalendar()[:2]:
            return False
        if definition.schedule == ReportDefinition.Schedule.MONTHLY and last.month == now.month and last.year == now.year:
            return False
    return True


def _recipients(definition: ReportDefinition):
    """مستلمو إشعار التنفيذ: مستخدمون محددون + أعضاء الأدوار (بلا تكرار)."""
    users = set(definition.notify_users.all())
    from apps.auth_app.models import RoleMember

    for role in definition.notify_roles.all():
        users.update(RoleMember.objects.filter(role=role).select_related("user").values_list("user", flat=True))
    return [u for u in users if u is not None]


def run_scheduled_reports(commit: bool = True) -> list[ReportJob]:
    """يُنفّذ كل التعريفات التي حان موعدها؛ commit=False للمحاكاة بلا كتابة.

    يرجع قائمة الوظائف المنفذة.
    """
    now = timezone.localtime()
    due = [d for d in ReportDefinition.objects.select_related("owner").filter(is_active=True) if _is_due(d, now)]
    if not commit:
        return []

    jobs = []
    for definition in due:
        job = generate_report(definition, definition.owner)
        jobs.append(job)
        definition.last_run_at = timezone.now()
        definition.save(update_fields=["last_run_at"])
        if job.status == ReportJob.Status.DONE:
            title = _("تقرير جاهز: %s") % definition.name_ar
            for user in _recipients(definition):
                notify_user(user, SYSTEM_NOTIFICATION_TYPE, title, _("التقرير متاح الآن في تقاريري."))
            AuditLog.objects.create(
                user=definition.owner,
                action=AuditLog.Action.EXPORT,
                model_name="reportjob",
                object_id=str(job.pk),
                object_repr=f"{definition.code} {definition.template_type}",
                detail="scheduled",
            )
    return jobs
