"""عروض الموظفين — قائمة + ملف + إضافة/تعديل (Sprint 2).

المرجع: docs/10-roadmap.md S2 (Employees) + docs/05-rbac.md §8 (Scope في طبقة الخدمات).
"""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.auth_app.scopes import employee_scope_queryset
from apps.auth_app.services import has_perm

from .forms import EmployeeForm
from .models import Employee
from .qr_service import get_active_qr, get_qr_payload, issue_qr, regenerate_qr


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
    """ورقة طباعة البطاقة — 4 بطاقات في صفحة A4 + خلفية رمز الشركة.

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
        qr = get_active_qr(employee)
        ctx["qr"] = qr
        ctx["payload"] = get_qr_payload(employee)
        return ctx
