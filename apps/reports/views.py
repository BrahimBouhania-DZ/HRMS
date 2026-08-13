"""عروض التقارير الأساسية + التصدير CSV/Excel (S5).

كل تقرير: قائمة بفلاتر + زر تصدير (csv/xlsx) يعيد نفس البيانات عبر GET.
المرجع: docs/08-reports.md §2.1–2.3.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.generic import TemplateView

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.auth_app.services import effective_permissions as _effective_permissions

from . import services

REPORTS = [
    {
        "code": "REP-01", "title": _("قائمة الموظفين"), "url": "reports:rep01",
        "category": "operational",
        "desc": _("بيانات الموظفين الأساسية (الفرع/القسم/المنصب/الحالة)"),
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("المنصب"), _("الفرع"), _("الحالة"), _("الهاتف")],
    },
    {
        "code": "REP-02", "title": _("الهيكل التنظيمي"), "url": "reports:rep02",
        "category": "operational",
        "desc": _("شجرة الفروع/الأقسام/المناصب مع عدد الموظفين"),
        "header": [_("الفرع"), _("القسم"), _("المنصب"), _("عدد الموظفين")],
    },
    {
        "code": "REP-03", "title": _("الموظفون الجدد"), "url": "reports:rep03",
        "category": "operational",
        "desc": _("الموظفون حسب فترة التوظيف"),
        "header": [_("الرمز"), _("الاسم"), _("تاريخ التوظيف"), _("القسم"), _("الفرع")],
    },
    {
        "code": "REP-11", "title": _("الملخص التشغيلي"), "url": "reports:rep11",
        "category": "operational",
        "desc": _("إحصاءات عامة: حضور/غياب/إجازة/تأخر/إضافي مع تفصيل لكل موظف"),
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("حضور"), _("غياب"), _("إجازة"), _("مرات التأخر"), _("دقائق التأخر"), _("ساعات إضافية")],
    },
    {
        "code": "REP-10", "title": _("الحضور اليومي"), "url": "reports:rep10",
        "category": "operational",
        "desc": _("سجل الحضور والانصراف اليومي"),
        "header": [_("التاريخ"), _("الرمز"), _("الاسم"), _("القسم"), _("دخول"), _("خروج"), _("دقائق العمل"), _("تأخير"), _("الحالة")],
    },
    {
        "code": "REP-12", "title": _("الغياب"), "url": "reports:rep12",
        "category": "operational",
        "desc": _("عدد أيام الغياب لكل موظف في فترة محددة"),
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("عدد الأيام")],
    },
    {
        "code": "REP-13", "title": _("التأخر"), "url": "reports:rep13",
        "category": "operational",
        "desc": _("مرات التأخر ومجموع الدقائق لكل موظف"),
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("عدد المرات"), _("مجموع الدقائق")],
    },
    {
        "code": "REP-14", "title": _("الانصراف المبكر"), "url": "reports:rep14",
        "category": "operational",
        "desc": _("مرات الانصراف المبكر ومجموع الدقائق لكل موظف"),
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("عدد المرات"), _("مجموع الدقائق")],
    },
    {
        "code": "REP-15", "title": _("ساعات العمل الإضافية"), "url": "reports:rep15",
        "category": "operational",
        "desc": _("دقائق العمل الإضافي لكل موظف في الفترة"),
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("عدد المرات"), _("مجموع الدقائق")],
    },
    {
        "code": "REP-18", "title": _("استثناءات الحضور"), "url": "reports:rep18",
        "category": "operational",
        "desc": _("إذن/مأمورية/تعويض/تصحيح — مع الموافق"),
        "header": [_("الموظف"), _("النوع"), _("من"), _("إلى"), _("الساعات"), _("الحالة"), _("المعتمد")],
    },
    {
        "code": "REP-22", "title": _("الإجازات الجارية"), "url": "reports:rep22",
        "category": "operational",
        "desc": _("الإجازات المعتمدة الجارية في تاريخ معين"),
        "header": [_("الموظف"), _("النوع"), _("من"), _("إلى"), _("أيام")],
    },
    {
        "code": "REP-23", "title": _("العطل الرسمية"), "url": "reports:rep23",
        "category": "operational",
        "desc": _("العطل الرسمية حسب السنة/الفرع"),
        "header": [_("التاريخ"), _("الاسم"), _("الفرع"), _("متكررة")],
    },
    {
        "code": "REP-16", "title": _("سجل مسحات QR"), "url": "reports:rep16",
        "category": "operational",
        "desc": _("سجل كل عمليات مسح رموز QR"),
        "header": [_("الوقت"), _("الموظف"), _("المصدر"), _("الجهاز"), _("القرار"), _("النتيجة")],
    },
    {
        "code": "REP-17", "title": _("المسحات المرفوضة"), "url": "reports:rep17",
        "category": "operational",
        "desc": _("محاولات المسح المرفوضة مجمّعة"),
        "header": [_("الرمز"), _("الاسم"), _("الجهاز"), _("السبب"), _("عدد المرات")],
    },
    {
        "code": "REP-20", "title": _("أرصدة الإجازات"), "url": "reports:rep20",
        "category": "operational",
        "desc": _("أرصدة الإجازات المتاحة لكل موظف"),
        "header": [_("الرمز"), _("الاسم"), _("القسم"), _("السنة"), _("النوع"), _("مستحق"), _("مستخدم"), _("تسوية"), _("متبقي")],
    },
    {
        "code": "REP-21", "title": _("طلبات الإجازات"), "url": "reports:rep21",
        "category": "operational",
        "desc": _("طلبات الإجازات وحالاتها"),
        "header": [_("الرمز"), _("الاسم"), _("النوع"), _("من"), _("إلى"), _("أيام"), _("الحالة")],
    },
    {
        "code": "REP-30", "title": _("كشف الرواتب (ملخص)"), "url": "reports:rep30",
        "category": "financial",
        "desc": _("ملخص دورات الصرف: إضافات/خصومات/صافي"),
        "header": [_("الفترة"), _("الفرع"), _("الحالة"), _("الموظفون"), _("الإضافات"), _("الخصومات"), _("الصافي")],
    },
    {
        "code": "REP-31", "title": _("كشف الرواتب (تفصيلي)"), "url": "reports:rep31",
        "category": "financial",
        "desc": _("كل موظف مع صافيه وعناصره"),
        "header": [_("الموظف"), _("القسم"), _("الفترة"), _("الإضافات"), _("الخصومات"), _("الصافي"), _("العناصر")],
    },
    {
        "code": "REP-33", "title": _("تكلفة الرواتب"), "url": "reports:rep33",
        "category": "financial",
        "desc": _("تكلفة الرواتب حسب الفرع/القسم (متوسط + إجمالي)"),
        "header": [_("الفرع"), _("القسم"), _("الموظفون"), _("الإضافات"), _("الصافي"), _("المتوسط")],
    },
    {
        "code": "REP-34", "title": _("المكافآت والخصومات"), "url": "reports:rep34",
        "category": "financial",
        "desc": _("بنود الإضافات والخصومات لكل موظف في دورة"),
        "header": [_("الفترة"), _("الموظف"), _("العنصر"), _("النوع"), _("المبلغ")],
    },
    {
        "code": "REP-35", "title": _("نهاية الخدمة"), "url": "reports:rep35",
        "category": "financial",
        "desc": _("مستحقات نهاية الخدمة (مكافأة، إجازات، بدل إشعار)"),
        "header": [_("الموظف"), _("تاريخ النهاية"), _("السنوات"), _("المكافأة"), _("تعويض الإجازات"), _("بدل الإشعار"), _("الخصومات"), _("الصافي"), _("الحالة")],
    },
    {
        "code": "REP-04", "title": _("انتهاء العقود"), "url": "reports:rep04",
        "category": "operational",
        "desc": _("عقود تنتهي خلال 30 يومًا"),
        "header": [_("الموظف"), _("النوع"), _("الانتهاء"), _("المتبقي (يوم)"), _("الفرع")],
    },
    {
        "code": "REP-05", "title": _("المقبلون على التقاعد"), "url": "reports:rep05",
        "category": "operational",
        "desc": _("الموظفون المقبلون على سن التقاعد مع التاريخ المتوقع"),
        "header": [_("الرمز"), _("الاسم"), _("تاريخ الميلاد"), _("التقاعد المتوقع"), _("المتبقي (يوم)"), _("القسم"), _("الفرع")],
    },
    {
        "code": "REP-06", "title": _("تغييرات الوظائف"), "url": "reports:rep06",
        "category": "operational",
        "desc": _("التعيينات والترقيات والنقل من السجل الوظيفي"),
        "header": [_("الرمز"), _("الاسم"), _("النوع"), _("من"), _("إلى"), _("التاريخ"), _("الفرع")],
    },
    {
        "code": "REP-42", "title": _("نتائج التقييمات"), "url": "reports:rep42",
        "category": "performance",
        "desc": _("نتائج دورة تقييم: ذاتي/مدير/نهائي"),
        "header": [_("الموظف"), _("الدورة"), _("الذاتي"), _("المدير"), _("النهائي"), _("الحالة")],
    },
    {
        "code": "REP-43", "title": _("خطط التحسين (PIP)"), "url": "reports:rep43",
        "category": "performance",
        "desc": _("خطط تحسين الأداء وتواريخها"),
        "header": [_("الموظف"), _("الدورة"), _("البدء"), _("الانتهاء"), _("الحالة")],
    },
    {
        "code": "REP-50", "title": _("سجل التدقيق"), "url": "reports:rep50",
        "category": "admin",
        "desc": _("كل عمليات الكتابة في النظام (أمان)"),
        "header": [_("الوقت"), _("المستخدم"), _("الإجراء"), _("النموذج"), _("الكائن"), _("التفاصيل")],
    },
    {
        "code": "REP-51", "title": _("المستخدمون والأدوار"), "url": "reports:rep51",
        "category": "admin",
        "desc": _("المستخدمون وأدوارهم وآخر دخول"),
        "header": [_("المستخدم"), _("الاسم"), _("الأدوار"), _("نشط"), _("آخر دخول")],
    },
    {
        "code": "REP-53", "title": _("حالة النسخ الاحتياطي"), "url": "reports:rep53",
        "category": "admin",
        "desc": _("النسخ المنفذة ونجاحها وأحجامها"),
        "header": [_("النوع"), _("البداية"), _("النهاية"), _("الحالة"), _("الحجم"), _("مشفّر")],
    },
    {
        "code": "REP-52", "title": _("النشاط اليومي"), "url": "reports:rep52",
        "category": "admin",
        "desc": _("دخول/خروج المستخدمين وجلساتهم"),
        "header": [_("الوقت"), _("المستخدم"), _("الإجراء"), _("IP")],
    },
    {
        "code": "REP-54", "title": _("حالة الأجهزة (QR)"), "url": "reports:rep54",
        "category": "admin",
        "desc": _("أجهزة المسح وحالتها وعدد مسحاتها"),
        "header": [_("الجهاز"), _("الفرع"), _("الموقع"), _("الحالة"), _("آخر اتصال"), _("مسحات اليوم"), _("إجمالي المسحات")],
    },
    {
        "code": "REP-60", "title": _("ملخص تنفيذي شهري"), "url": "reports:rep60",
        "category": "executive",
        "desc": _("أرقام رئيسية حسب الفرع: توظيف، مغادرة، حضور، رواتب"),
        "header": [_("الفرع"), _("الموظفون"), _("معينون جدد"), _("مغادرون"), _("أيام غياب"), _("نسبة الحضور"), _("آخر صافي صرف"), _("متوسط الراتب")],
    },
    {
        "code": "REP-61", "title": _("مؤشرات KPI"), "url": "reports:rep61",
        "category": "executive",
        "desc": _("قياس مؤشرات الأداء الرئيسية للفترة مقابل الأهداف"),
        "header": [_("المؤشر"), _("القيمة"), _("الهدف"), _("نسبة التحقق")],
    },
    {
        "code": "REP-62", "title": _("الدوران الوظيفي"), "url": "reports:rep62",
        "category": "executive",
        "desc": _("معدل المغادرة/التعيين حسب القسم"),
        "header": [_("القسم"), _("الفرع"), _("الموظفون (نهاية)"), _("معينون"), _("مغادرون"), _("معدل الدوران %")],
    },
]


class ReportIndexView(PermissionRequiredMixin, TemplateView):
    permission_code = "reports.view"
    template_name = "reports/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["reports"] = REPORTS
        return ctx


def _report_meta(code):
    """إرجاع بيانات تقرير من الكتالوج حسب رمزه (REP-01...)."""
    return next((r for r in REPORTS if r["code"] == code), {})


class _BaseReportView(PermissionRequiredMixin, TemplateView):
    permission_code = "reports.view"
    template_name = "reports/report.html"
    title = ""
    columns = []
    report_code = ""
    show_scan_filters = False

    def get_rows(self, user, filters):
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = {k: v for k, v in self.request.GET.items() if v}
        ctx["title"] = self.title
        ctx["report_code"] = self.report_code
        ctx["columns"] = self.columns
        ctx["rows"] = self.get_rows(self.request.user, filters)
        ctx["filters"] = filters
        ctx["options"] = services.filter_options()
        ctx["show_scan_filters"] = self.show_scan_filters
        ctx["show_cycle_filter"] = getattr(self, "show_cycle_filter", False)
        ctx["show_kind_filter"] = getattr(self, "show_kind_filter", False)
        ctx["show_eos_status_filter"] = getattr(self, "show_eos_status_filter", False)
        ctx["show_exc_status_filter"] = getattr(self, "show_exc_status_filter", False)
        ctx["show_change_type_filter"] = getattr(self, "show_change_type_filter", False)
        ctx["summary"] = getattr(self, "summary", None)
        return ctx


class Rep01View(_BaseReportView):
    title = _("REP-01 قائمة الموظفين")
    report_code = "REP-01"
    columns = _report_meta("REP-01")["header"]

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


class Rep11View(_BaseReportView):
    title = _("REP-11 الملخص التشغيلي")
    report_code = "REP-11"
    columns = _report_meta("REP-11")["header"]

    def get_rows(self, user, filters):
        summary, rows = services.operational_summary(
            user,
            from_date=filters.get("from_date") or None,
            to_date=filters.get("to_date") or None,
            branch=filters.get("branch"),
            department=filters.get("department"),
        )
        self.summary = summary
        return [
            (r["employee__employee_code"],
             f"{r['employee__first_name_ar']} {r['employee__last_name_ar']}",
             r["employee__department__name_ar"] or "",
             r["present"], r["absent"], r["leave"],
             r["late_times"], r["late_minutes"] or 0,
             f"{round((r['overtime'] or 0) / 60, 1)}")
            for r in rows
        ]


class Rep10View(_BaseReportView):
    title = _("REP-10 الحضور اليومي")
    report_code = "REP-10"
    columns = _report_meta("REP-10")["header"]

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
    report_code = "REP-12"
    columns = _report_meta("REP-12")["header"]

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
    report_code = "REP-13"
    columns = _report_meta("REP-13")["header"]

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


class Rep02View(_BaseReportView):
    title = _("REP-02 الهيكل التنظيمي")
    report_code = "REP-02"
    columns = _report_meta("REP-02")["header"]

    def get_rows(self, user, filters):
        return [
            (r["branch"], r["department"], r["position"], r["employees"])
            for r in services.org_structure(user, branch=filters.get("branch"))
        ]


class Rep03View(_BaseReportView):
    title = _("REP-03 الموظفون الجدد")
    report_code = "REP-03"
    columns = _report_meta("REP-03")["header"]

    def get_rows(self, user, filters):
        return [
            (r["code"], r["name"], r["hire_date"], r["department"], r["branch"])
            for r in services.new_employees(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                branch=filters.get("branch"),
            )
        ]


class Rep14View(_BaseReportView):
    title = _("REP-14 الانصراف المبكر")
    report_code = "REP-14"
    columns = _report_meta("REP-14")["header"]

    def get_rows(self, user, filters):
        rows = services.early_departure_summary(
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


class Rep15View(_BaseReportView):
    title = _("REP-15 ساعات العمل الإضافية")
    report_code = "REP-15"
    columns = _report_meta("REP-15")["header"]

    def get_rows(self, user, filters):
        rows = services.overtime_summary(
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


class Rep18View(_BaseReportView):
    title = _("REP-18 استثناءات الحضور")
    report_code = "REP-18"
    columns = _report_meta("REP-18")["header"]
    show_exc_status_filter = True

    def get_rows(self, user, filters):
        return [
            (r["employee"], r["type"], r["from"], r["to"], f"{r['hours']:g}", r["status"], r["approved_by"])
            for r in services.attendance_exceptions(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                status=filters.get("status"),
            )
        ]


class Rep22View(_BaseReportView):
    title = _("REP-22 الإجازات الجارية")
    report_code = "REP-22"
    columns = _report_meta("REP-22")["header"]

    def get_rows(self, user, filters):
        return [
            (r["employee"], r["leave_type"], r["from_date"], r["to_date"], r["days"])
            for r in services.ongoing_approved_leaves(user, on_date=filters.get("work_date"))
        ]


class Rep23View(_BaseReportView):
    title = _("REP-23 العطل الرسمية")
    report_code = "REP-23"
    columns = _report_meta("REP-23")["header"]

    def get_rows(self, user, filters):
        return [
            (r["date"], r["name"], r["branch"], r["recurring"])
            for r in services.public_holidays(
                user, year=filters.get("year"), branch=filters.get("branch")
            )
        ]


class Rep20View(_BaseReportView):
    title = _("REP-20 أرصدة الإجازات")
    report_code = "REP-20"
    columns = _report_meta("REP-20")["header"]

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
    report_code = "REP-21"
    columns = _report_meta("REP-21")["header"]

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
    report_code = "REP-16"
    columns = _report_meta("REP-16")["header"]
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
    report_code = "REP-17"
    columns = _report_meta("REP-17")["header"]
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
    report_code = "REP-30"
    columns = _report_meta("REP-30")["header"]

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


class Rep04View(_BaseReportView):
    title = _("REP-04 انتهاء العقود")
    report_code = "REP-04"
    columns = _report_meta("REP-04")["header"]

    def get_rows(self, user, filters):
        return [
            (r["employee"], r["contract_type"], r["end_date"], r["days_left"], r["branch"])
            for r in services.contract_expiry_list(user, branch=filters.get("branch"))
        ]


class Rep05View(_BaseReportView):
    title = _("REP-05 المقبلون على التقاعد")
    report_code = "REP-05"
    columns = _report_meta("REP-05")["header"]

    def get_rows(self, user, filters):
        return [
            (r["code"], r["name"], r["birth"], r["retire"], r["days"], r["department"], r["branch"])
            for r in services.retirement_list(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                branch=filters.get("branch"),
            )
        ]


class Rep06View(_BaseReportView):
    title = _("REP-06 تغييرات الوظائف")
    report_code = "REP-06"
    columns = _report_meta("REP-06")["header"]
    show_change_type_filter = True

    def get_rows(self, user, filters):
        return [
            (r["code"], r["name"], r["kind"], r["from"], r["to"], r["date"], r["branch"])
            for r in services.job_changes(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                change_type=filters.get("change_type"), branch=filters.get("branch"),
            )
        ]


class Rep31View(_BaseReportView):
    permission_code = "payroll.payslip.view"
    title = _("REP-31 كشف الرواتب (تفصيلي)")
    report_code = "REP-31"
    columns = _report_meta("REP-31")["header"]

    def get_rows(self, user, filters):
        return [
            (r["employee"], r["department"], r["period"],
             f"{r['earnings']:g}", f"{r['deductions']:g}", f"{r['net']:g}", r["details"])
            for r in services.payroll_detail(
                user, period_code=filters.get("period_code"),
                department=filters.get("department"),
            )
        ]


class Rep33View(_BaseReportView):
    permission_code = "payroll.payslip.view"
    title = _("REP-33 تكلفة الرواتب")
    report_code = "REP-33"
    columns = _report_meta("REP-33")["header"]

    def get_rows(self, user, filters):
        return [
            (r["branch"], r["department"], r["employees"],
             f"{r['total_earnings']:g}", f"{r['total_net']:g}", f"{r['average']:g}")
            for r in services.payroll_cost_by_branch(
                user, period_code=filters.get("period_code"), branch=filters.get("branch")
            )
        ]


class Rep34View(_BaseReportView):
    permission_code = "payroll.payslip.view"
    title = _("REP-34 المكافآت والخصومات")
    report_code = "REP-34"
    columns = _report_meta("REP-34")["header"]
    show_kind_filter = True

    def get_rows(self, user, filters):
        return [
            (r["period"], r["employee"], r["element"], r["kind"], f"{r['amount']:g}")
            for r in services.bonus_deduction_list(
                user, period_code=filters.get("period_code"), kind=filters.get("kind")
            )
        ]


class Rep35View(_BaseReportView):
    permission_code = "payroll.payslip.view"
    title = _("REP-35 نهاية الخدمة")
    report_code = "REP-35"
    columns = _report_meta("REP-35")["header"]
    show_eos_status_filter = True

    def get_rows(self, user, filters):
        return [
            (r["employee"], r["termination_date"], f"{r['years']:g}", f"{r['reward']:g}",
             f"{r['leave_comp']:g}", f"{r['notice']:g}", f"{r['deductions']:g}",
             f"{r['net']:g}", r["status"])
            for r in services.end_of_service_list(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                status=filters.get("status"),
            )
        ]


class Rep42View(_BaseReportView):
    title = _("REP-42 نتائج التقييمات")
    report_code = "REP-42"
    columns = _report_meta("REP-42")["header"]
    show_cycle_filter = True

    def get_rows(self, user, filters):
        return [
            (r["employee"], r["cycle"], r["self_score"], r["manager_score"], r["final_score"], r["status"])
            for r in services.perf_results(user, cycle=filters.get("cycle"))
        ]


class Rep43View(_BaseReportView):
    title = _("REP-43 خطط التحسين (PIP)")
    report_code = "REP-43"
    columns = _report_meta("REP-43")["header"]

    def get_rows(self, user, filters):
        return [
            (r["employee"], r["cycle"], r["start_date"], r["end_date"], r["status"])
            for r in services.pip_list(user, status=filters.get("status"))
        ]


class Rep50View(_BaseReportView):
    permission_code = "system.audit.view"
    title = _("REP-50 سجل التدقيق")
    report_code = "REP-50"
    columns = _report_meta("REP-50")["header"]

    def get_rows(self, user, filters):
        return [
            (r["time"], r["user"], r["action"], r["model"], r["object"], r["detail"])
            for r in services.audit_log_list(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                model_name=filters.get("model_name"),
            )
        ]


class Rep51View(_BaseReportView):
    permission_code = "system.audit.view"
    title = _("REP-51 المستخدمون والأدوار")
    report_code = "REP-51"
    columns = _report_meta("REP-51")["header"]

    def get_rows(self, user, filters):
        return [
            (r["username"], r["full_name"], r["roles"], r["is_active"], r["last_login"])
            for r in services.users_roles_list(user, role=filters.get("role"))
        ]


class Rep53View(_BaseReportView):
    permission_code = "system.backup.manage"
    title = _("REP-53 حالة النسخ الاحتياطي")
    report_code = "REP-53"
    columns = _report_meta("REP-53")["header"]

    def get_rows(self, user, filters):
        return [
            (r["kind"], r["started"], r["finished"], r["status"], r["size"], r["encrypted"])
            for r in services.backup_status_list(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date")
            )
        ]


class Rep52View(_BaseReportView):
    permission_code = "system.audit.view"
    title = _("REP-52 النشاط اليومي")
    report_code = "REP-52"
    columns = _report_meta("REP-52")["header"]

    def get_rows(self, user, filters):
        return [
            (r["time"], r["user"], r["action"], r["ip"])
            for r in services.daily_activity_list(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date")
            )
        ]


class Rep54View(_BaseReportView):
    permission_code = "device.manage"
    title = _("REP-54 حالة الأجهزة (QR)")
    report_code = "REP-54"
    columns = _report_meta("REP-54")["header"]

    def get_rows(self, user, filters):
        return [
            (r["device"], r["branch"], r["location"], r["status"], r["last_seen"],
             r["today_scans"], r["total_scans"])
            for r in services.device_status_list(user, branch=filters.get("branch"))
        ]


class Rep60View(_BaseReportView):
    title = _("REP-60 ملخص تنفيذي شهري")
    report_code = "REP-60"
    columns = _report_meta("REP-60")["header"]

    def get_rows(self, user, filters):
        return [
            (r["branch"], r["active"], r["hires"], r["departures"], r["absent"],
             f"{r['attendance_rate']}%", f"{r['net']:g}", f"{r['avg_salary']:g}")
            for r in services.executive_summary(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                branch=filters.get("branch"),
            )
        ]


class Rep61View(_BaseReportView):
    title = _("REP-61 مؤشرات KPI")
    report_code = "REP-61"
    columns = _report_meta("REP-61")["header"]

    def get_rows(self, user, filters):
        return [
            (r["kpi"], r["value"], r["target"], r["score"])
            for r in services.kpi_summary(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                branch=filters.get("branch"),
            )
        ]


class Rep62View(_BaseReportView):
    title = _("REP-62 الدوران الوظيفي")
    report_code = "REP-62"
    columns = _report_meta("REP-62")["header"]

    def get_rows(self, user, filters):
        return [
            (r["department"], r["branch"], r["end_hc"], r["hires"], r["departures"],
             f"{r['rate']}%")
            for r in services.turnover_report(
                user, from_date=filters.get("from_date"), to_date=filters.get("to_date"),
                branch=filters.get("branch"),
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
    # التصدير المالي (REP-30/31/33/34/35) يتطلب صلاحية كشف الرواتب
    if report_code in ("rep30", "rep31", "rep33", "rep34", "rep35") and not request.user.is_superuser and \
            "payroll.payslip.view" not in _effective_permissions(request.user):
        raise PermissionDenied
    # التصدير الأمني (REP-50/51/52) يتطلب صلاحية سجل التدقيق
    if report_code in ("rep50", "rep51", "rep52") and not request.user.is_superuser and \
            "system.audit.view" not in _effective_permissions(request.user):
        raise PermissionDenied
    # تصدير النسخ الاحتياطي (REP-53) يتطلب صلاحية الإدارة
    if report_code == "rep53" and not request.user.is_superuser and \
            "system.backup.manage" not in _effective_permissions(request.user):
        raise PermissionDenied
    # تصدير حالة الأجهزة (REP-54) يتطلب صلاحية إدارة الأجهزة
    if report_code == "rep54" and not request.user.is_superuser and \
            "device.manage" not in _effective_permissions(request.user):
        raise PermissionDenied
    if report_code == "rep01":
        rows = Rep01View().get_rows(request.user, request.GET)
    elif report_code == "rep11":
        rows = Rep11View().get_rows(request.user, request.GET)
    elif report_code == "rep10":
        rows = Rep10View().get_rows(request.user, request.GET)
    elif report_code == "rep12":
        rows = Rep12View().get_rows(request.user, request.GET)
    elif report_code == "rep13":
        rows = Rep13View().get_rows(request.user, request.GET)
    elif report_code == "rep02":
        rows = Rep02View().get_rows(request.user, request.GET)
    elif report_code == "rep03":
        rows = Rep03View().get_rows(request.user, request.GET)
    elif report_code == "rep14":
        rows = Rep14View().get_rows(request.user, request.GET)
    elif report_code == "rep15":
        rows = Rep15View().get_rows(request.user, request.GET)
    elif report_code == "rep18":
        rows = Rep18View().get_rows(request.user, request.GET)
    elif report_code == "rep22":
        rows = Rep22View().get_rows(request.user, request.GET)
    elif report_code == "rep23":
        rows = Rep23View().get_rows(request.user, request.GET)
    elif report_code == "rep20":
        rows = Rep20View().get_rows(request.user, request.GET)
    elif report_code == "rep21":
        rows = Rep21View().get_rows(request.user, request.GET)
    elif report_code == "rep16":
        rows = Rep16View().get_rows(request.user, request.GET)
    elif report_code == "rep17":
        rows = Rep17View().get_rows(request.user, request.GET)
    elif report_code == "rep30":
        rows = Rep30View().get_rows(request.user, request.GET)
    elif report_code == "rep04":
        rows = Rep04View().get_rows(request.user, request.GET)
    elif report_code == "rep31":
        rows = Rep31View().get_rows(request.user, request.GET)
    elif report_code == "rep33":
        rows = Rep33View().get_rows(request.user, request.GET)
    elif report_code == "rep34":
        rows = Rep34View().get_rows(request.user, request.GET)
    elif report_code == "rep35":
        rows = Rep35View().get_rows(request.user, request.GET)
    elif report_code == "rep05":
        rows = Rep05View().get_rows(request.user, request.GET)
    elif report_code == "rep06":
        rows = Rep06View().get_rows(request.user, request.GET)
    elif report_code == "rep60":
        rows = Rep60View().get_rows(request.user, request.GET)
    elif report_code == "rep61":
        rows = Rep61View().get_rows(request.user, request.GET)
    elif report_code == "rep62":
        rows = Rep62View().get_rows(request.user, request.GET)
    elif report_code == "rep42":
        rows = Rep42View().get_rows(request.user, request.GET)
    elif report_code == "rep43":
        rows = Rep43View().get_rows(request.user, request.GET)
    elif report_code == "rep50":
        rows = Rep50View().get_rows(request.user, request.GET)
    elif report_code == "rep51":
        rows = Rep51View().get_rows(request.user, request.GET)
    elif report_code == "rep52":
        rows = Rep52View().get_rows(request.user, request.GET)
    elif report_code == "rep53":
        rows = Rep53View().get_rows(request.user, request.GET)
    elif report_code == "rep54":
        rows = Rep54View().get_rows(request.user, request.GET)
    else:
        raise Http404
    meta = _report_meta("REP-" + report_code.removeprefix("rep"))
    title = meta.get("title") or report_code
    return _stream(request, rows, meta.get("header") or [], fmt, report_code, title=title)


class GeneratedReportsView(PermissionRequiredMixin, TemplateView):
    """التقارير المجدولة: التعريفات + التنفيذات الأخيرة (reports.view)."""

    permission_code = "reports.view"
    template_name = "reports/generated.html"

    def get_context_data(self, **kwargs):
        from .models import ReportDefinition, ReportJob

        ctx = super().get_context_data(**kwargs)
        ctx["definitions"] = ReportDefinition.objects.filter(is_active=True).order_by("name_ar")
        jobs = ReportJob.objects.select_related("report", "requested_by")[:100]
        ctx["jobs"] = [
            {
                "pk": j.pk,
                "name": j.report.name_ar,
                "status": j.get_status_display(),
                "started": j.started_at and j.started_at.strftime("%Y-%m-%d %H:%M") or "—",
                "error": j.error,
                "files": [f for f in j.files.all()],
            }
            for j in jobs
        ]
        return ctx


def generated_download(request, pk):
    """تنزيل ملف تقرير مجدول (يتطلب reports.export)."""
    from pathlib import Path

    from django.http import FileResponse

    from .models import ReportGeneratedFile

    if not request.user.is_superuser and "reports.export" not in _effective_permissions(request.user):
        raise PermissionDenied
    obj = get_object_or_404(ReportGeneratedFile, pk=pk)
    path = Path(obj.file_path)
    if not path.exists():
        raise Http404
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)
