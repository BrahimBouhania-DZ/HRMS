"""عروض التدريب — دورات + جلسات + تسجيلات + شهادات (v3).

المرجع: docs/10-roadmap.md v3 (Training) + docs/03 §3.7 + docs/05 §8 (النطاقات).
الصلاحيات: training.manage (إدارة دورات/جلسات/تسجيلات/شهادات)، training.enroll (تسجيل/عرض شهاداتي).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.auth_app.scopes import employee_scope_queryset

from .forms import CourseForm, EnrollForm, SessionForm
from .models import TrainingCertificate, TrainingCourse, TrainingEnrollment, TrainingSession
from .services import (
    TrainingError,
    approve_enrollment,
    cancel_session,
    complete_session,
    enroll_employee,
    reject_enrollment,
)


class CourseListView(PermissionRequiredMixin, ListView):
    permission_code = "training.manage"
    model = TrainingCourse
    template_name = "training/course_list.html"
    context_object_name = "courses"

    def get_queryset(self):
        qs = TrainingCourse.objects.all()
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(title_ar__icontains=q)
        return qs


class CourseCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "training.manage"
    model = TrainingCourse
    form_class = CourseForm
    template_name = "training/course_form.html"
    success_url = reverse_lazy("training:course_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("أُنشئت الدورة"))
        return super().form_valid(form)


class CourseUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "training.manage"
    model = TrainingCourse
    form_class = CourseForm
    template_name = "training/course_form.html"
    success_url = reverse_lazy("training:course_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("حُدّثت الدورة"))
        return super().form_valid(form)


class SessionListView(PermissionRequiredMixin, ListView):
    permission_code = "training.manage"
    model = TrainingSession
    template_name = "training/session_list.html"
    context_object_name = "sessions"
    paginate_by = 25

    def get_queryset(self):
        qs = TrainingSession.objects.select_related("course")
        course = self.request.GET.get("course")
        status = self.request.GET.get("status")
        if course:
            qs = qs.filter(course_id=course)
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-start_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["courses"] = TrainingCourse.objects.filter(is_active=True)
        return ctx


class SessionCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "training.manage"
    model = TrainingSession
    form_class = SessionForm
    template_name = "training/session_form.html"
    success_url = reverse_lazy("training:session_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("أُنشئت الجلسة"))
        return super().form_valid(form)


class SessionDetailView(PermissionRequiredMixin, DetailView):
    permission_code = "training.manage"
    model = TrainingSession
    template_name = "training/session_detail.html"
    context_object_name = "session"

    def get_queryset(self):
        return TrainingSession.objects.select_related("course").prefetch_related("enrollments__employee")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["enrollments"] = self.object.enrollments.select_related("employee").order_by("employee__employee_code")
        ctx["employees"] = employee_scope_queryset(self.request.user).exclude(
            id__in=self.object.enrollments.values_list("employee_id", flat=True)
        )
        return ctx


class SessionEnrollView(PermissionRequiredMixin, View):
    """تسجيل موظفين ضمن نطاق المستخدم في جلسة (BR-TRN-001)."""

    permission_code = "training.manage"

    def post(self, request, pk):
        session = get_object_or_404(TrainingSession, pk=pk)
        form = EnrollForm(request.POST, employees=employee_scope_queryset(request.user))
        if not form.is_valid():
            messages.error(request, _("اختر موظفًا واحدًا على الأقل"))
            return redirect("training:session_detail", pk=pk)
        enrolled = 0
        for employee in form.cleaned_data["employee_ids"]:
            try:
                enroll_employee(session, employee, user=request.user)
                enrolled += 1
            except TrainingError as exc:
                messages.error(request, str(exc))
        messages.success(request, _("سُجّل %(n)s موظفًا") % {"n": enrolled})
        return redirect("training:session_detail", pk=pk)


class EnrollmentApproveView(PermissionRequiredMixin, View):
    permission_code = "training.manage"

    def post(self, request, pk, enrollment_pk):
        enrollment = get_object_or_404(TrainingEnrollment, pk=enrollment_pk, session_id=pk)
        try:
            approve_enrollment(enrollment, user=request.user)
            messages.success(request, _("اعتُمد التسجيل"))
        except TrainingError as exc:
            messages.error(request, str(exc))
        return redirect("training:session_detail", pk=pk)


class EnrollmentRejectView(PermissionRequiredMixin, View):
    permission_code = "training.manage"

    def post(self, request, pk, enrollment_pk):
        enrollment = get_object_or_404(TrainingEnrollment, pk=enrollment_pk, session_id=pk)
        try:
            reject_enrollment(enrollment, user=request.user)
            messages.success(request, _("رُفض التسجيل"))
        except TrainingError as exc:
            messages.error(request, str(exc))
        return redirect("training:session_detail", pk=pk)


class SessionCompleteView(PermissionRequiredMixin, View):
    """إكمال الجلسة → تسجيلات مكتملة + شهادات (BR-TRN-003)."""

    permission_code = "training.manage"

    def post(self, request, pk):
        session = get_object_or_404(TrainingSession, pk=pk)
        try:
            count = complete_session(session, user=request.user)
            messages.success(request, _("أُكملت الجلسة — أُصدرت %(n)s شهادة") % {"n": count})
        except TrainingError as exc:
            messages.error(request, str(exc))
        return redirect("training:session_detail", pk=pk)


class SessionCancelView(PermissionRequiredMixin, View):
    permission_code = "training.manage"

    def post(self, request, pk):
        session = get_object_or_404(TrainingSession, pk=pk)
        try:
            cancel_session(session, user=request.user)
            messages.success(request, _("أُلغيت الجلسة"))
        except TrainingError as exc:
            messages.error(request, str(exc))
        return redirect("training:session_detail", pk=pk)


class CertificateListView(PermissionRequiredMixin, ListView):
    permission_code = "training.manage"
    model = TrainingCertificate
    template_name = "training/certificate_list.html"
    context_object_name = "certificates"
    paginate_by = 25

    def get_queryset(self):
        qs = TrainingCertificate.objects.select_related("enrollment__employee", "enrollment__session__course")
        employee = self.request.GET.get("employee")
        if employee:
            qs = qs.filter(enrollment__employee_id=employee)
        return qs.order_by("-issued_date")


class MyCertificatesView(PermissionRequiredMixin, ListView):
    """شهاداتي (الموظف الذي يستخدم الحساب)."""

    permission_code = "training.enroll"
    model = TrainingCertificate
    template_name = "training/my_certificates.html"
    context_object_name = "certificates"

    def get_queryset(self):
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is None:
            return TrainingCertificate.objects.none()
        return (
            TrainingCertificate.objects.filter(enrollment__employee=emp)
            .select_related("enrollment__session__course")
            .order_by("-issued_date")
        )
