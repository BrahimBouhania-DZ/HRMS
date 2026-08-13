"""عروض النسخ الاحتياطي والاستعادة (system.backup.manage) — v2.

- قائمة النسخ + تشغيل نسخة يدوية (POST).
- تحميل نسخة مشفرة.
- اختبار استعادة (dry-run) من الواجهة + استعادة فعلية.
"""

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from apps.auth_app.mixins import PermissionRequiredMixin

from .models import BackupJob, BackupSettings, RestoreJob
from .services import BackupError, list_backups, restore_backup, run_backup


class BackupDownloadView(PermissionRequiredMixin, View):
    """تحميل نسخة مشفرة — يُسمح به فقط لمن يملك system.backup.manage."""

    permission_code = "system.backup.manage"

    def get(self, request):
        from pathlib import Path

        name = request.GET.get("name", "")
        if not name or "/" in name or ".." in name:
            raise Http404
        from .services import _backup_dir

        path = _backup_dir() / name
        if not path.exists() or not path.is_file():
            raise Http404
        response = FileResponse(path.open("rb"), as_attachment=True, filename=path.name)
        return response


class BackupView(PermissionRequiredMixin, View):
    """لوحة النسخ الاحتياطي: قائمة + تشغيل + تحميل + استعادة."""

    permission_code = "system.backup.manage"
    template_name = "backup/backup_page.html"

    def get(self, request):
        ctx = {
            "settings": BackupSettings.get_default(),
            "backups": list_backups(),
            "jobs": BackupJob.objects.select_related("created_by").order_by("-started_at")[:20],
            "restores": RestoreJob.objects.select_related("restored_by").order_by("-restored_at")[:10],
        }
        return render(request, self.template_name, ctx)

    def post(self, request):
        action = request.POST.get("action")

        if action == "backup":
            try:
                job = run_backup(kind=BackupJob.Kind.MANUAL, user=request.user)
                messages.success(request, _("تم إنشاء النسخة بنجاح — %(file)s") % {"file": job.file_path})
            except BackupError as exc:
                messages.error(request, _("فشل إنشاء النسخة: %(err)s") % {"err": exc})
            return redirect(reverse("backup:page"))

        if action == "restore":
            path = request.POST.get("path", "")
            dry = request.POST.get("dry_run") == "1"
            try:
                job = restore_backup(path, user=request.user, dry_run=dry)
                messages.success(
                    request,
                    _("استعادة %(verb)s ناجحة من %(file)s") % {"verb": _("تجريبية") if dry else _("فعلية"), "file": job.source_file},
                )
            except BackupError as exc:
                messages.error(request, _("فشلت الاستعادة: %(err)s") % {"err": exc})
            return redirect(reverse("backup:page"))

        messages.error(request, _("إجراء غير معروف"))
        return redirect(reverse("backup:page"))
