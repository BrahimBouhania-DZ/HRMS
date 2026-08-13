"""عروض الوحدة الأساسية — لوحة المؤشرات + البحث الموحّد + سجل التدقيق (S5/v2)."""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.views.generic import ListView

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.core.models import AuditLog

from .dashboard import dashboard_kpis
from .search import unified_search


def home(request):
    """لوحة المؤشرات — تقرأ KPIs حسب نطاق المستخدم."""
    ctx = dashboard_kpis(request.user)
    ctx["reports_menu"] = _visible_reports(request.user)
    return render(request, "core/home.html", ctx)


def _visible_reports(user):
    """التقارير المسموح برؤيتها (أرقام REP) لعرضها في اللوحة."""
    from apps.auth_app.services import effective_permissions
    from apps.reports.views import REPORTS

    if user.is_superuser:
        return list(REPORTS)
    perms = set(effective_permissions(user))
    menu = []
    for rep in REPORTS:
        if rep["code"] == "REP-30":
            if "payroll.payslip.view" in perms:
                menu.append(rep)
        elif "reports.view" in perms:
            menu.append(rep)
    return menu


@login_required
def search(request):
    """بحث موحّد عبر الموظفين والهيكل والإجازات."""
    ctx = unified_search(request.user, request.GET.get("q", ""))
    return render(request, "core/search.html", ctx)


class AuditLogView(PermissionRequiredMixin, ListView):
    """سجل التدقيق (system.audit.view) — قراءة فقط، مع فلاتر."""

    permission_code = "system.audit.view"
    model = AuditLog
    template_name = "core/audit_log.html"
    context_object_name = "entries"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user")
        action = self.request.GET.get("action")
        if action:
            qs = qs.filter(action=action)
        model = self.request.GET.get("model")
        if model:
            qs = qs.filter(model_name__icontains=model)
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(object_repr__icontains=q) | Q(user__username__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = self.request.GET.get("action", "")
        ctx["model"] = self.request.GET.get("model", "")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["actions"] = AuditLog.Action.choices
        return ctx
