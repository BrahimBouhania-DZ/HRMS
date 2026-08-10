"""عروض الإجازات — طلبات + موافقات + أرصدة + أنواع + عطل رسمية (S4).

المرجع: docs/10-roadmap.md S4 + docs/03 §3.5 + docs/05 §8 (النطاقات).
"""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.auth_app.scopes import employee_scope_queryset

from .forms import BalanceAdjustForm, LeaveRequestForm, LeaveTypeForm, PublicHolidayForm
from .models import LeaveApproval, LeaveBalance, LeaveRequest, LeaveType, PublicHoliday
from .services import (
    LeaveError,
    adjust_balance,
    approve_request,
    cancel_request,
    calculate_leave_days,
    reject_request,
)


# ---------------------------------------------------------------------------
# 1) طلبات الموظف (بطاقتي)
# ---------------------------------------------------------------------------

class MyLeaveView(PermissionRequiredMixin, ListView):
    """طلبات الموظف + أرصدته (نطاق SELF)."""

    permission_code = "leave.balance.view"
    template_name = "leave/my_leave.html"
    context_object_name = "requests"

    def get_queryset(self):
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is None:
            return LeaveRequest.objects.none()
        return LeaveRequest.objects.filter(employee=emp).select_related("leave_type").order_by("-submitted_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = getattr(self.request.user, "employee_profile", None)
        ctx["balances"] = (
            LeaveBalance.objects.filter(employee=emp, year=timezone.localdate().year)
            .select_related("leave_type")
            .order_by("leave_type__code")
            if emp else LeaveBalance.objects.none()
        )
        return ctx


class LeaveRequestCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "leave.request"
    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = "leave/request_form.html"
    success_url = reverse_lazy("leave:my_leave")

    def form_valid(self, form):
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is None:
            messages.error(self.request, _("حسابك غير مرتبط بملف موظف"))
            return redirect("leave:my_leave")
        try:
            request = form.save(commit=False)
            request.employee = emp
            request.requested_by = self.request.user
            request.created_by = self.request.user
            from .services import submit_request
            submit_request(
                emp, request.leave_type,
                request.from_date, request.to_date,
                request.reason, self.request.user,
            )
        except LeaveError as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, _("أُرسل طلب الإجازة للمراجعة"))
        return redirect("leave:my_leave")


class LeaveRequestDetailView(PermissionRequiredMixin, DetailView):
    permission_code = "leave.balance.view"
    model = LeaveRequest
    template_name = "leave/request_detail.html"
    context_object_name = "request"

    def get_queryset(self):
        emp_qs = employee_scope_queryset(self.request.user)
        return LeaveRequest.objects.filter(employee__in=emp_qs).select_related("employee", "leave_type")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["approvals"] = self.object.approvals.order_by("level")
        return ctx


class LeaveRequestCancelView(PermissionRequiredMixin, View):
    """إلغاء الطلب من صاحبه (قبل الاعتماد)."""

    permission_code = "leave.request"

    def post(self, request, pk):
        lreq = get_object_or_404(LeaveRequest, pk=pk)
        emp = getattr(request.user, "employee_profile", None)
        if lreq.employee_id != getattr(emp, "id", None):
            messages.error(request, _("لا يمكنك إلغاء طلب غير طلبك"))
            return redirect("leave:my_leave")
        try:
            cancel_request(lreq, request.user)
            messages.success(request, _("أُلغي الطلب"))
        except LeaveError as exc:
            messages.error(request, str(exc))
        return redirect("leave:my_leave")


# ---------------------------------------------------------------------------
# 2) قائمة الموافقات (HR / مشرف)
# ---------------------------------------------------------------------------

class LeaveRequestListView(PermissionRequiredMixin, ListView):
    """كل طلبات النطاق + صف الانتظار للموافقة."""

    permission_code = "leave.approve"
    model = LeaveRequest
    template_name = "leave/request_list.html"
    context_object_name = "requests"
    paginate_by = 25

    def get_queryset(self):
        emp_qs = employee_scope_queryset(self.request.user)
        qs = LeaveRequest.objects.filter(employee__in=emp_qs).select_related("employee", "leave_type")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("status", "-submitted_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status"] = self.request.GET.get("status", "")
        ctx["statuses"] = LeaveRequest.Status.choices
        emp_qs = employee_scope_queryset(self.request.user)
        ctx["pending_count"] = LeaveRequest.objects.filter(
            employee__in=emp_qs, status=LeaveRequest.Status.PENDING
        ).count()
        return ctx


class LeaveRequestApproveView(PermissionRequiredMixin, View):
    """اعتماد / رفض طلب (leave.approve) — يعمل فقط على مستوى الطلب الحالي."""

    permission_code = "leave.approve"

    def post(self, request, pk, action):
        lreq = get_object_or_404(LeaveRequest, pk=pk)
        if lreq.status != LeaveRequest.Status.PENDING:
            messages.error(request, _("الطلب ليس قيد الانتظار"))
            return redirect("leave:request_list")
        comment = request.POST.get("comment", "")
        try:
            if action == "approve":
                approve_request(lreq, request.user, comment)
                messages.success(request, _("تم اعتماد الطلب"))
            elif action == "reject":
                reject_request(lreq, request.user, comment)
                messages.warning(request, _("تم رفض الطلب"))
            else:
                messages.error(request, _("إجراء غير معروف"))
        except LeaveError as exc:
            messages.error(request, str(exc))
        return redirect("leave:request_list")


# ---------------------------------------------------------------------------
# 3) الأرصدة
# ---------------------------------------------------------------------------

class BalanceListView(PermissionRequiredMixin, ListView):
    permission_code = "leave.balance.view"
    model = LeaveBalance
    template_name = "leave/balance_list.html"
    context_object_name = "balances"
    paginate_by = 25

    def get_queryset(self):
        emp_qs = employee_scope_queryset(self.request.user)
        qs = LeaveBalance.objects.filter(employee__in=emp_qs).select_related("employee", "leave_type")
        year = self.request.GET.get("year")
        if year:
            qs = qs.filter(year=year)
        return qs.order_by("employee__employee_code", "leave_type__code")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["year"] = self.request.GET.get("year", timezone.localdate().year)
        return ctx


class BalanceAdjustView(PermissionRequiredMixin, View):
    """تسوية رصيد (leave.balance.adjust) — إدخال +/− بلا حذف."""

    permission_code = "leave.balance.adjust"

    def post(self, request, pk):
        balance = get_object_or_404(LeaveBalance, pk=pk)
        form = BalanceAdjustForm(request.POST)
        if form.is_valid():
            adjust_balance(
                balance.employee, balance.leave_type, balance.year,
                form.cleaned_data["amount"], request.user,
            )
            messages.success(request, _("تمت التسوية"))
        else:
            messages.error(request, _("مقدار تسوية غير صالح"))
        return redirect("leave:balance_list")


# ---------------------------------------------------------------------------
# 4) الأنواع والعطل الرسمية (إعدادات)
# ---------------------------------------------------------------------------

class LeaveTypeListView(PermissionRequiredMixin, ListView):
    permission_code = "leave.type.manage"
    model = LeaveType
    template_name = "leave/leave_type_list.html"
    context_object_name = "leave_types"


class LeaveTypeCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "leave.type.manage"
    model = LeaveType
    form_class = LeaveTypeForm
    template_name = "leave/leave_type_form.html"
    success_url = reverse_lazy("leave:leave_type_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("أُضيف نوع الإجازة"))
        return super().form_valid(form)


class LeaveTypeUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "leave.type.manage"
    model = LeaveType
    form_class = LeaveTypeForm
    template_name = "leave/leave_type_form.html"
    success_url = reverse_lazy("leave:leave_type_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("حُدّث نوع الإجازة"))
        return super().form_valid(form)


class PublicHolidayListView(PermissionRequiredMixin, ListView):
    permission_code = "leave.type.manage"
    model = PublicHoliday
    template_name = "leave/public_holiday_list.html"
    context_object_name = "holidays"

    def get_queryset(self):
        return PublicHoliday.objects.select_related("branch").order_by("-date", "branch__code")


class PublicHolidayCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "leave.type.manage"
    model = PublicHoliday
    form_class = PublicHolidayForm
    template_name = "leave/public_holiday_form.html"
    success_url = reverse_lazy("leave:public_holiday_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("أُضيفت العطلة الرسمية"))
        return super().form_valid(form)


class PublicHolidayDeleteView(PermissionRequiredMixin, View):
    permission_code = "leave.type.manage"

    def post(self, request, pk):
        holiday = get_object_or_404(PublicHoliday, pk=pk)
        holiday.delete()
        messages.success(request, _("حُذفت العطلة"))
        return redirect("leave:public_holiday_list")
