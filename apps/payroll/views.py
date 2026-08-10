"""عروض الرواتب — عناصر، دورات، قسائم PDF، نهاية خدمة (v2).

المرجع: docs/10-roadmap.md v2 (Payroll) + docs/05 §4.6 (الصلاحيات) + docs/01 §6.8.
"""

from decimal import Decimal

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView

from apps.auth_app.mixins import PermissionRequiredMixin

from .forms import PayElementForm, PayRunGenerateForm
from .models import EndOfService, PayElement, PayRun, PayrollLine, Payslip
from .services import (
    PayrollError,
    approve_payrun,
    bank_rows,
    calculate_end_of_service,
    freeze_payrun,
    generate_payrun,
    review_payrun,
)

FROZEN_FINAL = (PayRun.Status.APPROVED, PayRun.Status.FROZEN)


# ---------------------------------------------------------------------------
# 1) عناصر الأجر (payroll.element.manage)
# ---------------------------------------------------------------------------

class PayElementListView(PermissionRequiredMixin, ListView):
    permission_code = "payroll.element.manage"
    model = PayElement
    template_name = "payroll/element_list.html"
    context_object_name = "elements"
    ordering = ("kind", "code")


class PayElementCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "payroll.element.manage"
    form_class = PayElementForm
    template_name = "payroll/element_form.html"
    success_url = reverse_lazy("payroll:element_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("أُضيف عنصر الأجر بنجاح"))
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# 2) الدورات (payroll.view / payroll.run.*)
# ---------------------------------------------------------------------------

class PayRunListView(PermissionRequiredMixin, ListView):
    """دورات الرواتب (ضمن النطاق)."""

    permission_code = "payroll.view"
    template_name = "payroll/payrun_list.html"
    context_object_name = "payruns"
    ordering = ("-period_code",)

    def get_queryset(self):
        return PayRun.objects.select_related("branch").order_by("-period_code")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["branches"] = _scoped_branches(self.request.user)
        ctx["can_generate"] = self.request.user.is_superuser or _has_perm(self.request.user, "payroll.run.generate")
        return ctx


class PayRunGenerateView(PermissionRequiredMixin, View):
    permission_code = "payroll.run.generate"

    def post(self, request):
        form = PayRunGenerateForm(request.POST, branches=_scoped_branches(request.user))
        if not form.is_valid():
            for err in form.non_field_errors():
                messages.error(request, err)
            return redirect("payroll:run_list")
        try:
            run = generate_payrun(
                form.cleaned_data["period_code"], form.cleaned_data["branch"], request.user
            )
        except PayrollError as exc:
            messages.error(request, str(exc))
            return redirect("payroll:run_list")
        messages.success(request, _("أُنشئت دورة %(period)s (%(count)s قسيمة)") % {"period": run.period_code, "count": run.payslips.count()})
        return redirect("payroll:run_detail", pk=run.pk)


class PayRunDetailView(PermissionRequiredMixin, TemplateView):
    """تفاصيل الدورة: ملخص + قسائم + إجراءات الحالة."""

    permission_code = "payroll.view"
    template_name = "payroll/payrun_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        run = get_object_or_404(PayRun.objects.select_related("branch"), pk=self.kwargs["pk"])
        ctx["payrun"] = run
        ctx["payslips"] = run.payslips.select_related("employee").order_by("employee__employee_code")
        ctx["can_review"] = self.request.user.is_superuser or _has_perm(self.request.user, "payroll.run.review")
        ctx["can_approve"] = self.request.user.is_superuser or _has_perm(self.request.user, "payroll.run.approve")
        ctx["can_export"] = self.request.user.is_superuser or _has_perm(self.request.user, "payroll.bank.export")
        ctx["finalized"] = run.status in FROZEN_FINAL
        return ctx


class PayRunStatusView(PermissionRequiredMixin, View):
    """POST فقط: review / approve / freeze — كل انتقال بصلاحية خاصة."""

    def dispatch(self, request, *args, **kwargs):
        action = kwargs.get("action")
        self.permission_code = {
            "review": "payroll.run.review",
            "approve": "payroll.run.approve",
            "freeze": "payroll.run.approve",
        }.get(action, "payroll.view")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk, action):
        run = get_object_or_404(PayRun, pk=pk)
        try:
            if action == "review":
                review_payrun(run, request.user)
            elif action == "approve":
                approve_payrun(run, request.user)
            elif action == "freeze":
                freeze_payrun(run, request.user)
            else:
                return JsonResponse({"ok": False, "error": _("إجراء غير معروف")}, status=400)
            messages.success(request, _("أصبحت الدورة: %(status)s") % {"status": run.get_status_display()})
        except PayrollError as exc:
            messages.error(request, str(exc))
        return redirect("payroll:run_detail", pk=pk)


# ---------------------------------------------------------------------------
# 3) القسائم (payroll.payslip.view)
# ---------------------------------------------------------------------------

class PayslipListView(PermissionRequiredMixin, ListView):
    """قسائم موظف ضمن دورة (الموظف يرى قسائمه فقط — نطاق SELF)."""

    permission_code = "payroll.payslip.view"
    template_name = "payroll/payslip_list.html"
    context_object_name = "payslips"

    def get_queryset(self):
        run = get_object_or_404(PayRun, pk=self.kwargs["pk"])
        qs = run.payslips.select_related("employee", "pay_run__branch")
        emp = getattr(self.request.user, "employee_profile", None)
        if not self.request.user.is_superuser and not _has_perm(self.request.user, "payroll.view"):
            qs = qs.filter(employee=emp) if emp else qs.none()
        return qs.order_by("employee__employee_code")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["payrun"] = get_object_or_404(PayRun, pk=self.kwargs["pk"])
        return ctx


class MyPayslipsView(PermissionRequiredMixin, ListView):
    """قسائمي (كل الدورات المعتمدة/المجمدة)."""

    permission_code = "payroll.payslip.view"
    template_name = "payroll/my_payslips.html"
    context_object_name = "payslips"

    def get_queryset(self):
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is None:
            return Payslip.objects.none()
        return (
            Payslip.objects.filter(employee=emp, pay_run__status__in=FROZEN_FINAL)
            .select_related("pay_run__branch")
            .order_by("-pay_run__period_code")
        )


class PayslipPdfView(PermissionRequiredMixin, TemplateView):
    """قسيمة PDF — يتطلب أن تكون الدورة معتمدة أو مجمدة."""

    permission_code = "payroll.payslip.view"
    template_name = "payroll/payslip_pdf.html"

    def get(self, request, *args, **kwargs):
        slip = get_object_or_404(Payslip.objects.select_related("employee", "pay_run__branch"), pk=kwargs["pk"])
        emp = getattr(request.user, "employee_profile", None)
        if not request.user.is_superuser and not _has_perm(request.user, "payroll.view"):
            if emp is None or emp.id != slip.employee_id:
                return HttpResponse(_("غير مصرح لك بعرض هذه القسيمة"), status=403)
        if slip.pay_run.status not in FROZEN_FINAL:
            return HttpResponse(_("القسيمة تُتاح بعد اعتماد الدورة"), status=400)

        from apps.reports.services import export_pdf

        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="payslip-{slip.pk}.pdf"'
        context = {"slip": slip, "lines": slip.pay_run.lines.filter(employee=slip.employee)}
        return export_pdf(response, [], [], _("قسيمة راتب"), request=request, extra=context)


# ---------------------------------------------------------------------------
# 4) نهاية الخدمة (payroll.eos.manage)
# ---------------------------------------------------------------------------

class EndOfServiceListView(PermissionRequiredMixin, ListView):
    permission_code = "payroll.eos.manage"
    template_name = "payroll/eos_list.html"
    context_object_name = "records"

    def get_queryset(self):
        return EndOfService.objects.select_related("employee").order_by("-termination_date")


class EndOfServiceCreateView(PermissionRequiredMixin, View):
    """حساب آلي لنهاية الخدمة (POST: employee, termination_date)."""

    permission_code = "payroll.eos.manage"

    def get(self, request):
        from apps.employees.models import Employee

        return render(request, "payroll/eos_form.html", {
            "employees": Employee.objects.filter(is_active=True).order_by("employee_code"),
        })

    def post(self, request):
        from apps.employees.models import Employee

        emp = get_object_or_404(Employee, pk=request.POST.get("employee"))
        termination = request.POST.get("termination_date")
        if not termination:
            messages.error(request, _("حدّد تاريخ نهاية الخدمة"))
            return redirect("payroll:eos_create")
        record = calculate_end_of_service(emp, termination, request.user)
        messages.success(request, _("حُسبت نهاية الخدمة (الصافي: %(net)s)") % {"net": record.net})
        return redirect("payroll:eos_list")


# ---------------------------------------------------------------------------
# 5) تصدير البنك (payroll.bank.export)
# ---------------------------------------------------------------------------

class BankExportView(PermissionRequiredMixin, View):
    """تصدير كشف الرواتب إلى البنك (Excel/CSV) — يتطلب اعتمادًا."""

    permission_code = "payroll.bank.export"

    def get(self, request, pk, fmt):
        from apps.reports.services import export_csv, export_xlsx

        run = get_object_or_404(PayRun, pk=pk)
        if run.status not in FROZEN_FINAL:
            return HttpResponse(_("التصدير بعد اعتماد الدورة"), status=400)

        rows = [[r["employee_code"], r["name"], r["bank_account"], str(r["net"])] for r in bank_rows(run)]
        header = [_("رقم الموظف"), _("الاسم"), _("الحساب البنكي"), _("الصافي")]
        filename = f"bank-{run.period_code}"

        if fmt == "xlsx":
            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
            return export_xlsx(response, header, rows, _("تصدير بنك %(code)s") % {"code": run.period_code})

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        return export_csv(response, header, rows)


# ---------------------------------------------------------------------------
# مساعدون
# ---------------------------------------------------------------------------

def _scoped_branches(user):
    from apps.auth_app.services import effective_permissions
    from apps.org.models import Branch

    if user.is_superuser or "payroll.view" in effective_permissions(user):
        return Branch.objects.all().order_by("name_ar")
    return Branch.objects.none()


def _has_perm(user, code) -> bool:
    from apps.auth_app.services import has_perm

    return has_perm(user, code)
