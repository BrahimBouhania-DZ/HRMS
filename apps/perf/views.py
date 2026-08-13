"""عروض تقييم الأداء — دورات + مراجعات + أهداف + خطط تحسين (v2).

المرجع: docs/10-roadmap.md v2 (Performance) + docs/03 §3.8 + docs/05 §8 (النطاقات).
الصلاحيات: perf.manage (دورات/قوالب/خطط)، perf.review (تقييم المدير)، perf.self (ذاتي).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.auth_app.scopes import employee_scope_queryset

from .forms import (
    ManagerReviewForm,
    ObjectiveFormSet,
    PerfCycleForm,
    PerfTemplateForm,
    PipPlanForm,
    SelfReviewForm,
)
from .models import PerfCycle, PerfReview, PerfTemplate, PipPlan
from .services import (
    PerfError,
    close_cycle,
    close_pip,
    generate_reviews,
    open_pip,
    save_objectives,
    submit_manager_review,
    submit_self_review,
)


class CycleListView(PermissionRequiredMixin, ListView):
    """كل دورات التقييم + توليد مراجعات لدورة."""

    permission_code = "perf.manage"
    model = PerfCycle
    template_name = "perf/cycle_list.html"
    context_object_name = "cycles"
    ordering = ("-period_start",)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["templates"] = PerfTemplate.objects.filter(is_active=True)
        ctx["reviewable_count"] = employee_scope_queryset(self.request.user).count()
        return ctx


class CycleCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "perf.manage"
    model = PerfCycle
    form_class = PerfCycleForm
    template_name = "perf/cycle_form.html"
    success_url = reverse_lazy("perf:cycle_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("أُنشئت الدورة (مسودة)"))
        return super().form_valid(form)


class CycleOpenView(PermissionRequiredMixin, View):
    """فتح الدورة + توليد مراجعات لكل موظف نطاق المستخدم بقالب نشط."""

    permission_code = "perf.manage"

    def post(self, request, pk):
        cycle = get_object_or_404(PerfCycle, pk=pk)
        template_pk = request.POST.get("template") or ""
        if not template_pk:
            messages.error(request, _("اختر قالب تقييم نشطًا"))
            return redirect("perf:cycle_list")
        template = PerfTemplate.objects.filter(pk=template_pk, is_active=True).first()
        if template is None:
            messages.error(request, _("اختر قالب تقييم نشطًا"))
            return redirect("perf:cycle_list")
        employees = employee_scope_queryset(request.user)
        count = generate_reviews(cycle, template, employees, user=request.user)
        if cycle.status == PerfCycle.Status.DRAFT:
            cycle.status = PerfCycle.Status.OPEN
            cycle.updated_by = request.user
            cycle.save(update_fields=["status", "updated_by"])
        messages.success(request, _("فُتحت الدورة — أُنشئت %(n)s مراجعة") % {"n": count})
        return redirect("perf:cycle_list")


class CycleCloseView(PermissionRequiredMixin, View):
    """إغلاق الدورة (تتطلب اكتمال كل المراجعات)."""

    permission_code = "perf.manage"

    def post(self, request, pk):
        cycle = get_object_or_404(PerfCycle, pk=pk)
        try:
            close_cycle(cycle, user=request.user)
            messages.success(request, _("أُغلقت الدورة"))
        except PerfError as exc:
            messages.error(request, str(exc))
        return redirect("perf:cycle_list")


class ReviewListView(PermissionRequiredMixin, ListView):
    """مراجعات نطاق المستخدم (تقييم المدير)."""

    permission_code = "perf.review"
    model = PerfReview
    template_name = "perf/review_list.html"
    context_object_name = "reviews"
    paginate_by = 25

    def get_queryset(self):
        emp_qs = employee_scope_queryset(self.request.user)
        qs = PerfReview.objects.filter(employee__in=emp_qs).select_related("employee", "cycle", "template")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-cycle__period_start", "employee__employee_code")


class ReviewDetailView(PermissionRequiredMixin, DetailView):
    """تفاصيل مراجعة + تقييم مدير + أهداف."""

    permission_code = "perf.review"
    model = PerfReview
    template_name = "perf/review_detail.html"
    context_object_name = "review"

    def get_queryset(self):
        emp_qs = employee_scope_queryset(self.request.user)
        return PerfReview.objects.filter(employee__in=emp_qs).select_related("employee", "cycle", "template")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["objectives"] = self.object.objectives.order_by("id")
        ctx["manager_form"] = ManagerReviewForm(instance=self.object)
        ctx["objective_formset"] = ObjectiveFormSet(queryset=self.object.objectives.order_by("id"))
        ctx["pip_plan"] = self.object.pip_plans.first()
        ctx["pip_form"] = PipPlanForm()
        return ctx


class ReviewManagerSubmitView(PermissionRequiredMixin, View):
    """حفظ تقييم المدير + الأهداف."""

    permission_code = "perf.review"

    def post(self, request, pk):
        review = get_object_or_404(PerfReview, pk=pk)
        form = ManagerReviewForm(request.POST, instance=review)
        formset = ObjectiveFormSet(request.POST, queryset=review.objectives.order_by("id"))
        if not form.is_valid():
            messages.error(request, _("راجع بيانات تقييم المدير"))
            return redirect("perf:review_detail", pk=pk)
        review = form.save(commit=False)
        try:
            review = submit_manager_review(
                review, review.manager_score, review.manager_comment, user=request.user
            )
            if formset.is_valid():
                objectives = formset.save(commit=False)
                for obj in objectives:
                    obj.review = review
                    obj.updated_by = request.user
                    obj.save()
                # إعادة حساب النهائي بعد حفظ الأهداف
                from .services import weighted_final_score

                review.final_score = weighted_final_score(review)
                review.save(update_fields=["final_score"])
            messages.success(request, _("حُفظ تقييم المدير"))
        except PerfError as exc:
            messages.error(request, str(exc))
        return redirect("perf:review_detail", pk=pk)


class MyReviewListView(PermissionRequiredMixin, ListView):
    """مراجعاتي (تقييم ذاتي)."""

    permission_code = "perf.self"
    model = PerfReview
    template_name = "perf/my_reviews.html"
    context_object_name = "reviews"

    def get_queryset(self):
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is None:
            return PerfReview.objects.none()
        return PerfReview.objects.filter(employee=emp).select_related("cycle", "template").order_by("-cycle__period_start")


class MyReviewSelfView(PermissionRequiredMixin, UpdateView):
    """تعبئة التقييم الذاتي."""

    permission_code = "perf.self"
    model = PerfReview
    form_class = SelfReviewForm
    template_name = "perf/self_review_form.html"
    context_object_name = "review"

    def get_queryset(self):
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is None:
            return PerfReview.objects.none()
        return PerfReview.objects.filter(employee=emp)

    def form_valid(self, form):
        review = form.save(commit=False)
        try:
            submit_self_review(review, review.self_score, review.self_comment, user=self.request.user)
            messages.success(self.request, _("حُفظ تقييمك الذاتي"))
        except PerfError as exc:
            messages.error(self.request, str(exc))
            return redirect("perf:my_reviews")
        return redirect("perf:my_reviews")


class TemplateListView(PermissionRequiredMixin, ListView):
    permission_code = "perf.manage"
    model = PerfTemplate
    template_name = "perf/template_list.html"
    context_object_name = "templates"


class TemplateCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "perf.manage"
    model = PerfTemplate
    form_class = PerfTemplateForm
    template_name = "perf/template_form.html"
    success_url = reverse_lazy("perf:template_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("أُنشئ القالب"))
        return super().form_valid(form)


class PipCreateView(PermissionRequiredMixin, View):
    """فتح خطة تحسين لمراجعة."""

    permission_code = "perf.pip.manage"

    def post(self, request, pk):
        review = get_object_or_404(PerfReview, pk=pk)
        form = PipPlanForm(request.POST)
        if not form.is_valid():
            messages.error(request, _("راجع بيانات الخطة"))
            return redirect("perf:review_detail", pk=pk)
        try:
            open_pip(
                review,
                form.cleaned_data["start_date"],
                form.cleaned_data["end_date"],
                form.cleaned_data["action_items"],
                form.cleaned_data.get("supervisor_note", ""),
                user=request.user,
            )
            messages.success(request, _("فُتحت خطة التحسين"))
        except PerfError as exc:
            messages.error(request, str(exc))
        return redirect("perf:review_detail", pk=pk)


class PipCloseView(PermissionRequiredMixin, View):
    """إغلاق خطة تحسين."""

    permission_code = "perf.pip.manage"

    def post(self, request, pk):
        pip = get_object_or_404(PipPlan, pk=pk)
        try:
            close_pip(pip, user=request.user)
            messages.success(request, _("أُغلقت خطة التحسين"))
        except PerfError as exc:
            messages.error(request, str(exc))
        return redirect("perf:review_detail", pk=pip.review_id)
