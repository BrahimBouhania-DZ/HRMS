"""عروض الموظفين — قائمة + ملف + إضافة/تعديل (Sprint 2).

المرجع: docs/10-roadmap.md S2 (Employees) + docs/05-rbac.md §8 (Scope في طبقة الخدمات).
"""

from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.auth_app.scopes import employee_scope_queryset
from apps.auth_app.services import has_perm

from .forms import ContractForm, DocumentForm, EmployeeForm
from .models import Contract, Document, Employee
from .qr_service import get_active_qr, get_qr_payload, issue_qr, regenerate_qr

CARDS_PER_PAGE = 6  # بطاقات 100×70mm على ورقة A4 (2×3)


def _card_ctx(employee):
    """سياق بطاقة واحدة (بيانات الموظف + رمز QR)."""
    return {
        "employee": employee,
        "qr": get_active_qr(employee),
        "payload": get_qr_payload(employee),
    }


def _build_sheets(card_contexts):
    """توزيع البطاقات على أوراق A4 (6 بطاقات لكل ورقة)."""
    return [
        {"cards": card_contexts[i : i + CARDS_PER_PAGE]}
        for i in range(0, len(card_contexts), CARDS_PER_PAGE)
    ]


class EmployeeListView(PermissionRequiredMixin, ListView):
    permission_code = "employee.view"
    model = Employee
    template_name = "employees/employee_list.html"
    context_object_name = "employees"
    paginate_by = 25

    def get_queryset(self):
        qs = employee_scope_queryset(self.request.user)
        qs = qs.select_related("branch", "department", "position", "shift")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(first_name_ar__icontains=q)
                | Q(last_name_ar__icontains=q)
                | Q(employee_code__icontains=q)
            )
        return qs.order_by("employee_code")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        return ctx


class EmployeeDetailView(PermissionRequiredMixin, DetailView):
    permission_code = "employee.view"
    model = Employee
    template_name = "employees/employee_detail.html"
    context_object_name = "employee"

    def get_queryset(self):
        return employee_scope_queryset(self.request.user).select_related(
            "branch", "department", "position", "shift"
        )


class EmployeeCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "employee.create"
    model = Employee
    form_class = EmployeeForm
    template_name = "employees/employee_form.html"
    success_url = reverse_lazy("employees:employee_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("تمت إضافة الموظف"))
        return super().form_valid(form)


class EmployeeUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "employee.edit"
    model = Employee
    form_class = EmployeeForm
    template_name = "employees/employee_form.html"
    success_url = reverse_lazy("employees:employee_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("تم تحديث بيانات الموظف"))
        return super().form_valid(form)


class EmployeeQrCardView(PermissionRequiredMixin, DetailView):
    """بطاقة موظف جاهزة للطباعة (اسم + رقم وظيفي + رمز QR).

    العرض: صلاحية employee.view (ضمن Scope الموظفين).
    إصدار/إعادة توليد الرمز: صلاحية employee.qr.manage (T-QR-1).
    """

    permission_code = "employee.view"
    model = Employee
    template_name = "employees/employee_card.html"
    context_object_name = "employee"

    def get_queryset(self):
        return employee_scope_queryset(self.request.user).select_related(
            "branch", "department", "position", "shift"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        employee = self.object
        can_manage = has_perm(self.request.user, "employee.qr.manage")
        qr = get_active_qr(employee)
        if qr is None and can_manage:
            qr = issue_qr(employee, issued_by=self.request.user)
        ctx["qr"] = qr
        ctx["payload"] = get_qr_payload(employee)
        ctx["can_manage"] = can_manage
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not has_perm(request.user, "employee.qr.manage"):
            messages.error(request, _("لا تملك صلاحية إدارة QR"))
        else:
            regenerate_qr(self.object, issued_by=request.user)
            messages.success(request, _("تم توليد رمز QR جديد (نسخة محدثة)"))
        return redirect(reverse("employees:employee_card", kwargs={"pk": self.object.pk}))


class EmployeeCardPrintView(PermissionRequiredMixin, DetailView):
    """ورقة طباعة بطاقة موظف واحد — يملأ ورقة A4 بست نسخ (2×3).

    صلاحية العرض: employee.view (مثل بطاقة الموظف العادية).
    الصفحة قائمة بذاتها (بدون base.html) لطباعة نظيفة، وتفتح نافذة الطباعة تلقائيًا.
    """

    permission_code = "employee.view"
    model = Employee
    template_name = "employees/employee_card_print.html"
    context_object_name = "employee"

    def get_queryset(self):
        return employee_scope_queryset(self.request.user).select_related(
            "branch", "department", "position", "shift"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        employee = self.object
        ctx["sheets"] = _build_sheets([_card_ctx(employee)] * CARDS_PER_PAGE)
        return ctx


class EmployeeCardsPrintView(PermissionRequiredMixin, TemplateView):
    """طباعة متعددة — بطاقات مجموعة موظفين مختارة (معرّفة عبر ?ids=1,2,3).

    صلاحية العرض: employee.view ضمن Scope الموظفين.
    تُعرض كل بطاقة مرة واحدة، 6 بطاقات لكل ورقة A4.
    """

    permission_code = "employee.view"
    template_name = "employees/employee_card_print.html"

    def get(self, request, *args, **kwargs):
        ids = request.GET.get("ids", "")
        pks = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if not pks:
            messages.error(request, _("لم يتم اختيار أي موظف للطباعة"))
            return redirect("employees:employee_list")
        employees = (
            employee_scope_queryset(request.user)
            .filter(pk__in=pks)
            .select_related("branch", "department", "position", "shift")
            .order_by("employee_code")
        )
        sheets = _build_sheets([_card_ctx(emp) for emp in employees])
        context = self.get_context_data(sheets=sheets)
        return self.render_to_response(context)


# ---------------------------------------------------------------------------
# العقود (employee.contract.view / manage) — v2
# ---------------------------------------------------------------------------

class ContractListView(PermissionRequiredMixin, ListView):
    permission_code = "employee.contract.view"
    model = Contract
    template_name = "employees/contract_list.html"
    context_object_name = "contracts"
    paginate_by = 25

    def get_queryset(self):
        emp_qs = employee_scope_queryset(self.request.user)
        qs = Contract.objects.filter(employee__in=emp_qs).select_related("employee__branch", "employee__department")
        today = timezone.localdate()
        status = self.request.GET.get("status")
        if status == "expired":
            qs = qs.filter(end_date__lt=today)
        elif status == "expiring":
            qs = qs.filter(end_date__gte=today, end_date__lte=today + timezone.timedelta(days=30))
        elif status == "active":
            qs = qs.filter(Q(end_date__gt=today + timezone.timedelta(days=30)) | Q(end_date__isnull=True))
        return qs.order_by("-start_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status"] = self.request.GET.get("status", "")
        return ctx


class ContractCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "employee.contract.manage"
    model = Contract
    form_class = ContractForm
    template_name = "employees/contract_form.html"
    success_url = reverse_lazy("employees:contract_list")

    def get_initial(self):
        initial = super().get_initial()
        employee_pk = self.request.GET.get("employee")
        if employee_pk:
            emp = employee_scope_queryset(self.request.user).filter(pk=employee_pk).first()
            if emp:
                initial["employee"] = emp
        previous = self.request.GET.get("renew")
        if previous:
            prev = Contract.objects.filter(pk=previous).first()
            if prev:
                initial["employee"] = prev.employee
                initial["previous_contract"] = prev
                initial["contract_type"] = prev.contract_type
                initial["start_date"] = (prev.end_date or timezone.localdate()) + timezone.timedelta(days=1)
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("تمت إضافة العقد"))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("employees:contract_list")


class ContractUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "employee.contract.manage"
    model = Contract
    form_class = ContractForm
    template_name = "employees/contract_form.html"

    def get_queryset(self):
        return Contract.objects.filter(employee__in=employee_scope_queryset(self.request.user))

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("تم تحديث العقد"))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("employees:contract_list")


# ---------------------------------------------------------------------------
# الوثائق (employee.document.view / manage) — v2
# ---------------------------------------------------------------------------

class DocumentListView(PermissionRequiredMixin, ListView):
    permission_code = "employee.document.view"
    model = Document
    template_name = "employees/document_list.html"
    context_object_name = "documents"
    paginate_by = 25

    def get_queryset(self):
        emp_qs = employee_scope_queryset(self.request.user)
        qs = Document.objects.filter(employee__in=emp_qs).select_related("employee__branch", "employee__department")
        today = timezone.localdate()
        status = self.request.GET.get("status")
        if status == "expired":
            qs = qs.filter(expiry_date__lt=today)
        elif status == "expiring":
            qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timezone.timedelta(days=30))
        return qs.order_by("expiry_date", "-issued_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status"] = self.request.GET.get("status", "")
        return ctx


class DocumentUploadView(PermissionRequiredMixin, CreateView):
    permission_code = "employee.document.manage"
    model = Document
    form_class = DocumentForm
    template_name = "employees/document_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("تم رفع المستند"))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("employees:document_list")


class DocumentUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "employee.document.manage"
    model = Document
    form_class = DocumentForm
    template_name = "employees/document_form.html"

    def get_queryset(self):
        return Document.objects.filter(employee__in=employee_scope_queryset(self.request.user))

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("تم تحديث المستند"))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("employees:document_list")


class DocumentDownloadView(PermissionRequiredMixin, DetailView):
    """تنزيل ملف المستند (عرض فقط — employee.document.view)."""

    permission_code = "employee.document.view"
    model = Document

    def get_queryset(self):
        return Document.objects.filter(employee__in=employee_scope_queryset(self.request.user))

    def get(self, request, *args, **kwargs):
        document = self.get_object()
        if not document.file:
            raise Http404
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.title)
