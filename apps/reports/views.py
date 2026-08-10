"""عروض التقارير الأساسية + التصدير CSV/Excel (S5).

كل تقرير: قائمة بفلاتر + زر تصدير (csv/xlsx) يعيد نفس البيانات عبر GET.
المرجع: docs/08-reports.md §2.1–2.3.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.generic import TemplateView

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.auth_app.services import effective_permissions as _effective_permissions

from . import services

REPORTS = [
    {
        "code": "REP-01", "title": _("قائمة الموظفين"), "url": "reports:rep01",
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("المنصب"), _("الفرع"), _("الحالة"), _("الهاتف")],
    },
    {
        "code": "REP-10", "title": _("الحضور اليومي"), "url": "reports:rep10",
        "header": [_("التاريخ"), _("الرمز"), _("الاسم"), _("القسم"), _("دخول"), _("خروج"), _("دقائق العمل"), _("تأخير"), _("الحالة")],
    },
    {
        "code": "REP-12", "title": _("الغياب"), "url": "reports:rep12",
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("عدد الأيام")],
    },
    {
        "code": "REP-13", "title": _("التأخر"), "url": "reports:rep13",
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("عدد المرات"), _("مجموع الدقائق")],
    },
    {
        "code": "REP-20", "title": _("أرصدة الإجازات"), "url": "reports:rep20",
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("السنة"), _("النوع"), _("مستحق"), _("مستخدم"), _("تسوية"), _("متبقي")],
    },
    {
        "code": "REP-21", "title": _("طلبات الإجازات"), "url": "reports:rep21",
        "header": [_("الرمز"), _("الاسم"), _("النوع"), _("من"), _("إلى"), _("أيام"), _("الحالة")],
    },
    {
        "code": "REP-16", "title": _("سجل مسحات QR"), "url": "reports:rep16",
        "header": [_("الوقت"), _("الموظف"), _("المصدر"), _("الجهاز"), _("القرار"), _("النتيجة")],
    },
    {
        "code": "REP-17", "title": _("المسحات المرفوضة"), "url": "reports:rep17",
        "header": [_("الرمز"), _("الاسم"), _("الجهاز"), _("السبب"), _("عدد المرات")],
    },
    {
        "code": "REP-30", "title": _("كشف الرواتب (ملخص)"), "url": "reports:rep30",
        "header": [_("الفترة"), _("الفرع"), _("الحالة"), _("الموظفون"), _("الإضافات"), _("الخصومات"), _("الصافي")],
    },
]


class ReportIndexView(PermissionRequiredMixin, TemplateView):
    permission_code = "reports.view"
    template_name = "reports/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["reports"] = REPORTS
        return ctx


class _BaseReportView(PermissionRequiredMixin, TemplateView):
    permission_code = "reports.view"
    template_name = "reports/report.html"
    title = ""
    columns = []
    show_scan_filters = False

    def get_rows(self, user, filters):
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = {k: v for k, v in self.request.GET.items() if v}
        ctx["title"] = self.title
        ctx["columns"] = self.columns
        ctx["rows"] = self.get_rows(self.request.user, filters)
        ctx["filters"] = filters
        ctx["options"] = services.filter_options()
        ctx["show_scan_filters"] = self.show_scan_filters
        return ctx


class Rep01View(_BaseReportView):
    title = _("REP-01 قائمة الموظفين")
    columns = REPORTS[0]["header"]

    def get_rows(self, user, filters):
        qs = services.employee_list(
            user,
            branch=filters.get("branch"),
            department=filters.get("department"),
            employment_status=filters.get("employment_status"),
        )
        return [
            (e.employee_code, str(e), e.department and e.department.name_ar or "",
             e.position and e.position.name_ar or "", e.branch and e.branch.name_ar or "",
             e.get_employment_status_display(), e.phone or "")
            for e in qs
        ]


class Rep10View(_BaseReportView):
    title = _("REP-10 الحضور اليومي")
    columns = REPORTS[1]["header"]

    def get_rows(self, user, filters):
        qs = services.attendance_daily(
            user,
            work_date=filters.get("work_date") or None,
            branch=filters.get("branch"),
            department=filters.get("department"),
        )
        return [
            (str(d.work_date), d.employee.employee_code, str(d.employee),
             d.employee.department and d.employee.department.name_ar or "",
             d.check_in and d.check_in.strftime("%H:%M") or "",
             d.check_out and d.check_out.strftime("%H:%M") or "",
             d.worked_minutes, d.late_minutes, d.get_state_display())
            for d in qs
        ]


class Rep12View(_BaseReportView):
    title = _("REP-12 الغياب")
    columns = REPORTS[2]["header"]

    def get_rows(self, user, filters):
        rows = services.absence_summary(
            user,
            from_date=filters.get("from_date") or None,
            to_date=filters.get("to_date") or None,
            department=filters.get("department"),
            justified=filters.get("kind") == "justified",
        )
        return [
            (r["employee__employee_code"],
             f"{r['employee__first_name_ar']} {r['employee__last_name_ar']}",
             r["employee__department__name_ar"] or "", r["days"])
            for r in rows
        ]


class Rep13View(_BaseReportView):
    title = _("REP-13 التأخر")
    columns = REPORTS[3]["header"]

    def get_rows(self, user, filters):
        rows = services.lateness_summary(
            user,
            from_date=filters.get("from_date") or None,
            to_date=filters.get("to_date") or None,
            department=filters.get("department"),
        )
        return [
            (r["employee__employee_code"],
             f"{r['employee__first_name_ar']} {r['employee__last_name_ar']}",
             r["employee__department__name_ar"] or "", r["times"], r["total_minutes"])
            for r in rows
        ]


class Rep20View(_BaseReportView):
    title = _("REP-20 أرصدة الإجازات")
    columns = REPORTS[4]["header"]

    def get_rows(self, user, filters):
        qs = services.leave_balances(
            user,
            year=filters.get("year") or None,
            leave_type=filters.get("leave_type"),
            department=filters.get("department"),
        )
        return [
            (b.employee.employee_code, str(b.employee),
             b.employee.department and b.employee.department.name_ar or "",
             b.year, b.leave_type.name_ar, b.granted, b.used,
             b.adjusted, b.remaining)
            for b in qs
        ]


class Rep21View(_BaseReportView):
    title = _("REP-21 طلبات الإجازات")
    columns = REPORTS[5]["header"]

    def get_rows(self, user, filters):
        qs = services.leave_requests(
            user,
            from_date=filters.get("from_date") or None,
            to_date=filters.get("to_date") or None,
            status=filters.get("status"),
            leave_type=filters.get("leave_type"),
        )
        return [
            (r.employee.employee_code, str(r.employee), r.leave_type.name_ar,
             str(r.from_date), str(r.to_date), r.days, r.get_status_display())
            for r in qs
        ]


class Rep16View(_BaseReportView):
    title = _("REP-16 سجل مسحات QR")
    columns = REPORTS[6]["header"]
    show_scan_filters = True

    def get_rows(self, user, filters):
        qs = services.scan_log(
            user,
            day=filters.get("work_date") or None,
            device=filters.get("device"),
            decision=filters.get("decision"),
        )
        return [
            (s.scanned_at.strftime("%Y-%m-%d %H:%M"), str(s.employee),
             s.get_source_display(), s.device and s.device.device_code or "—",
             s.get_decision_display(), s.result_detail)
            for s in qs
        ]


class Rep17View(_BaseReportView):
    title = _("REP-17 المسحات المرفوضة")
    columns = REPORTS[7]["header"]
    show_scan_filters = True

    def get_rows(self, user, filters):
        rows = services.rejected_scans(
            user,
            from_date=filters.get("from_date") or None,
            to_date=filters.get("to_date") or None,
            device=filters.get("device"),
        )
        return [
            (r["employee__employee_code"],
             f"{r['employee__first_name_ar']} {r['employee__last_name_ar']}",
             r["device__device_code"] or "—", r["result_detail"] or "—", r["times"])
            for r in rows
        ]


class Rep30View(_BaseReportView):
    """REP-30 كشف الرواتب — مالي، يتطلب صلاحية payroll.payslip.view."""

    permission_code = "payroll.payslip.view"
    title = _("REP-30 كشف الرواتب (ملخص)")
    columns = REPORTS[8]["header"]

    def get_rows(self, user, filters):
        return [
            (r["period_code"], r["branch"], r["status"], r["employees"],
             f"{r['total_earnings']:.2f}", f"{r['total_deductions']:.2f}", f"{r['total_net']:.2f}")
            for r in services.payroll_summary(
                user,
                period_code=filters.get("period_code") or None,
                branch=filters.get("branch") or None,
            )
        ]


def _stream(request, rows, header, fmt, filename, title=None):
    from django.http import HttpResponse

    if fmt == "xlsx":
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return services.export_xlsx(response, header, rows, title or filename)

    if fmt == "pdf":
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
        return services.export_pdf(response, header, rows, title or filename, request=request)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    return services.export_csv(response, header, rows)


@login_required
def export(request, report_code, fmt):
    """تصدير CSV/XLSX — يعيد نفس فلاتر القائمة (يتطلب reports.export)."""
    if not request.user.is_superuser and "reports.export" not in _effective_permissions(request.user):
        raise PermissionDenied
    # التصدير المالي (REP-30) يتطلب صلاحية كشف الرواتب
    if report_code == "rep30" and not request.user.is_superuser and \
            "payroll.payslip.view" not in _effective_permissions(request.user):
        raise PermissionDenied
    if report_code == "rep01":
        rows = Rep01View().get_rows(request.user, request.GET)
        header = REPORTS[0]["header"]
    elif report_code == "rep10":
        rows = Rep10View().get_rows(request.user, request.GET)
        header = REPORTS[1]["header"]
    elif report_code == "rep12":
        rows = Rep12View().get_rows(request.user, request.GET)
        header = REPORTS[2]["header"]
    elif report_code == "rep13":
        rows = Rep13View().get_rows(request.user, request.GET)
        header = REPORTS[3]["header"]
    elif report_code == "rep20":
        rows = Rep20View().get_rows(request.user, request.GET)
        header = REPORTS[4]["header"]
    elif report_code == "rep21":
        rows = Rep21View().get_rows(request.user, request.GET)
        header = REPORTS[5]["header"]
    elif report_code == "rep16":
        rows = Rep16View().get_rows(request.user, request.GET)
        header = REPORTS[6]["header"]
    elif report_code == "rep17":
        rows = Rep17View().get_rows(request.user, request.GET)
        header = REPORTS[7]["header"]
    elif report_code == "rep30":
        rows = Rep30View().get_rows(request.user, request.GET)
        header = REPORTS[8]["header"]
    else:
        raise Http404
    _index = int(report_code.removeprefix("rep")) - 1
    title = REPORTS[_index]["title"] if 0 <= _index < len(REPORTS) else report_code
    return _stream(request, rows, header, fmt, report_code, title=title)
