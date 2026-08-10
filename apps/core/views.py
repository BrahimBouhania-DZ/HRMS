"""عروض الوحدة الأساسية — لوحة المؤشرات + البحث الموحّد (S5)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

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
