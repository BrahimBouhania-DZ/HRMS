"""عروض الهيكل التنظيمي — CRUD + شجرة الأقسام (Sprint 2).

المرجع: docs/10-roadmap.md S2 (Org) + docs/05-rbac.md §8.
"""

from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.auth_app.mixins import PermissionRequiredMixin

from .forms import BranchForm, DepartmentForm, PositionForm, ShiftForm
from .models import Branch, Department, Position, Shift

ORG_INDEX_URL = reverse_lazy("org:branch_list")


# ---------------- الفروع ----------------
class BranchListView(PermissionRequiredMixin, ListView):
    permission_code = "org.branch.view"
    model = Branch
    template_name = "org/branch_list.html"
    context_object_name = "branches"


class BranchCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "org.branch.create"
    model = Branch
    form_class = BranchForm
    template_name = "org/branch_form.html"
    success_url = ORG_INDEX_URL

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("تمت إضافة الفرع"))
        return super().form_valid(form)


class BranchUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "org.branch.edit"
    model = Branch
    form_class = BranchForm
    template_name = "org/branch_form.html"
    success_url = ORG_INDEX_URL

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("تم تحديث الفرع"))
        return super().form_valid(form)


class BranchDeleteView(PermissionRequiredMixin, DeleteView):
    permission_code = "org.branch.disable"
    model = Branch
    success_url = ORG_INDEX_URL
    template_name = "org/branch_confirm_delete.html"


# ---------------- الأقسام ----------------
class DepartmentListView(PermissionRequiredMixin, ListView):
    permission_code = "org.department.view"
    model = Department
    template_name = "org/department_list.html"
    context_object_name = "departments"

    def get_queryset(self):
        qs = super().get_queryset().select_related("branch", "parent", "manager")
        return qs.filter(parent__isnull=True).prefetch_related("children")


class DepartmentCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "org.department.create"
    model = Department
    form_class = DepartmentForm
    template_name = "org/department_form.html"
    success_url = reverse_lazy("org:department_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("تمت إضافة القسم"))
        return super().form_valid(form)


class DepartmentUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "org.department.edit"
    model = Department
    form_class = DepartmentForm
    template_name = "org/department_form.html"
    success_url = reverse_lazy("org:department_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("تم تحديث القسم"))
        return super().form_valid(form)


class DepartmentDeleteView(PermissionRequiredMixin, DeleteView):
    permission_code = "org.department.disable"
    model = Department
    success_url = reverse_lazy("org:department_list")
    template_name = "org/department_confirm_delete.html"


# ---------------- المناصب ----------------
class PositionListView(PermissionRequiredMixin, ListView):
    permission_code = "org.position.view"
    model = Position
    template_name = "org/position_list.html"
    context_object_name = "positions"

    def get_queryset(self):
        return super().get_queryset().select_related("department").order_by("department__name_ar")


class PositionCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "org.position.create"
    model = Position
    form_class = PositionForm
    template_name = "org/position_form.html"
    success_url = reverse_lazy("org:position_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("تمت إضافة المنصب"))
        return super().form_valid(form)


class PositionUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "org.position.edit"
    model = Position
    form_class = PositionForm
    template_name = "org/position_form.html"
    success_url = reverse_lazy("org:position_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("تم تحديث المنصب"))
        return super().form_valid(form)


# ---------------- جداول الدوام ----------------
class ShiftListView(PermissionRequiredMixin, ListView):
    permission_code = "org.shift.view"
    model = Shift
    template_name = "org/shift_list.html"
    context_object_name = "shifts"


class ShiftCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "org.shift.create"
    model = Shift
    form_class = ShiftForm
    template_name = "org/shift_form.html"
    success_url = reverse_lazy("org:shift_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("تمت إضافة جدول الدوام"))
        return super().form_valid(form)


class ShiftUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "org.shift.edit"
    model = Shift
    form_class = ShiftForm
    template_name = "org/shift_form.html"
    success_url = reverse_lazy("org:shift_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("تم تحديث جدول الدوام"))
        return super().form_valid(form)
