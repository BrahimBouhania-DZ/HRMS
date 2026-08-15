"""عروض التوظيف — إعلانات + مرشحون + مقابلات (v4).

المرجع: docs/10-roadmap.md v4 (Recruitment).
الصلاحيات: recruitment.posting.* (إعلانات)، recruitment.candidate.* (مرشحون ومقابلات).
"""

import csv
import json

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.auth_app.mixins import PermissionRequiredMixin

from . import imports
from .forms import CandidateForm, InterviewForm, PostingForm
from .models import Candidate, Interview, JobPosting
from .services import (
    RecruitmentError,
    add_candidate,
    close_posting,
    complete_interview,
    hire_candidate,
    publish_posting,
    schedule_interview,
    set_candidate_status,
)


class PostingListView(PermissionRequiredMixin, ListView):
    permission_code = "recruitment.posting.view"
    model = JobPosting
    template_name = "recruitment/posting_list.html"
    context_object_name = "postings"
    paginate_by = 25

    def get_queryset(self):
        qs = JobPosting.objects.select_related("department", "branch")
        status = self.request.GET.get("status")
        q = self.request.GET.get("q")
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(title_ar__icontains=q)
        return qs


class PostingCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "recruitment.posting.create"
    model = JobPosting
    form_class = PostingForm
    template_name = "recruitment/posting_form.html"
    success_url = reverse_lazy("recruitment:posting_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("أُنشئ الإعلان"))
        return super().form_valid(form)


class PostingUpdateView(PermissionRequiredMixin, UpdateView):
    permission_code = "recruitment.posting.edit"
    model = JobPosting
    form_class = PostingForm
    template_name = "recruitment/posting_form.html"
    success_url = reverse_lazy("recruitment:posting_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("حُدّث الإعلان"))
        return super().form_valid(form)


class PostingPublishView(PermissionRequiredMixin, View):
    permission_code = "recruitment.posting.edit"

    def post(self, request, pk):
        posting = get_object_or_404(JobPosting, pk=pk)
        try:
            publish_posting(posting, user=request.user)
            messages.success(self.request, _("نُشر الإعلان"))
        except RecruitmentError as exc:
            messages.error(self.request, str(exc))
        return redirect("recruitment:posting_list")


class PostingCloseView(PermissionRequiredMixin, View):
    permission_code = "recruitment.posting.edit"

    def post(self, request, pk):
        posting = get_object_or_404(JobPosting, pk=pk)
        close_posting(posting, user=request.user)
        messages.success(self.request, _("أُغلق الإعلان"))
        return redirect("recruitment:posting_list")


class PostingDetailView(PermissionRequiredMixin, DetailView):
    permission_code = "recruitment.posting.view"
    model = JobPosting
    template_name = "recruitment/posting_detail.html"
    context_object_name = "posting"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["candidates"] = self.object.candidates.select_related("hired_employee").order_by("-applied_date")
        return ctx


class CandidateListView(PermissionRequiredMixin, ListView):
    permission_code = "recruitment.candidate.view"
    model = Candidate
    template_name = "recruitment/candidate_list.html"
    context_object_name = "candidates"
    paginate_by = 25

    def get_queryset(self):
        qs = Candidate.objects.select_related("posting", "hired_employee")
        status = self.request.GET.get("status")
        posting = self.request.GET.get("posting")
        q = self.request.GET.get("q")
        if status:
            qs = qs.filter(status=status)
        if posting:
            qs = qs.filter(posting_id=posting)
        if q:
            qs = qs.filter(first_name_ar__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["postings"] = JobPosting.objects.filter(status__in=[JobPosting.Status.PUBLISHED, JobPosting.Status.DRAFT])
        return ctx


class CandidateCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "recruitment.candidate.manage"
    model = Candidate
    form_class = CandidateForm
    template_name = "recruitment/candidate_form.html"
    success_url = reverse_lazy("recruitment:candidate_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ("POST",):
            return kwargs
        posting = self.request.GET.get("posting")
        if posting:
            kwargs["initial"] = {"posting": posting}
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("أُضيف المرشح"))
        return super().form_valid(form)


class CandidateDetailView(PermissionRequiredMixin, DetailView):
    permission_code = "recruitment.candidate.view"
    model = Candidate
    template_name = "recruitment/candidate_detail.html"
    context_object_name = "candidate"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["interviews"] = self.object.interviews.select_related("interviewer").order_by("scheduled_at")
        return ctx


class CandidateStatusView(PermissionRequiredMixin, View):
    """تغيير حالة مرشح (فرز/مقابلة/عرض/رفض/انسحاب)."""

    permission_code = "recruitment.candidate.manage"

    def post(self, request, pk, status):
        candidate = get_object_or_404(Candidate, pk=pk)
        try:
            set_candidate_status(candidate, status, user=request.user)
            messages.success(self.request, _("حُدّثت حالة المرشح"))
        except RecruitmentError as exc:
            messages.error(self.request, str(exc))
        return redirect("recruitment:candidate_detail", pk=pk)


class InterviewScheduleView(PermissionRequiredMixin, CreateView):
    permission_code = "recruitment.candidate.manage"
    form_class = InterviewForm
    template_name = "recruitment/interview_form.html"

    def form_valid(self, form):
        candidate = get_object_or_404(Candidate, pk=self.kwargs["pk"])
        try:
            interview = schedule_interview(
                candidate,
                scheduled_at=form.cleaned_data["scheduled_at"],
                interviewer=form.cleaned_data.get("interviewer"),
                mode=form.cleaned_data.get("mode", Interview.Mode.IN_PERSON),
                user=self.request.user,
            )
            messages.success(self.request, _("جُدولت المقابلة"))
            return redirect("recruitment:candidate_detail", pk=candidate.pk)
        except RecruitmentError as exc:
            messages.error(self.request, str(exc))
            return redirect("recruitment:candidate_detail", pk=candidate.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["candidate"] = get_object_or_404(Candidate, pk=self.kwargs["pk"])
        return ctx


class InterviewCompleteView(PermissionRequiredMixin, View):
    permission_code = "recruitment.candidate.manage"

    def post(self, request, pk, interview_pk):
        interview = get_object_or_404(Interview, pk=interview_pk, candidate_id=pk)
        try:
            complete_interview(
                interview,
                score=int(request.POST.get("score", 0) or 0),
                notes=request.POST.get("notes", ""),
                user=request.user,
            )
            messages.success(self.request, _("حُدّثت المقابلة"))
        except RecruitmentError as exc:
            messages.error(self.request, str(exc))
        return redirect("recruitment:candidate_detail", pk=pk)


class CandidateHireView(PermissionRequiredMixin, View):
    permission_code = "recruitment.candidate.manage"

    def post(self, request, pk):
        candidate = get_object_or_404(Candidate, pk=pk)
        try:
            hire_candidate(candidate, user=request.user)
            messages.success(
                self.request,
                _("تم التوظيف — أُنشئ الموظف %(code)s") % {"code": candidate.hired_employee.employee_code},
            )
        except RecruitmentError as exc:
            messages.error(self.request, str(exc))
        return redirect("recruitment:candidate_detail", pk=pk)


class ImportView(PermissionRequiredMixin, TemplateView):
    """استيراد جماعي من CSV / Excel — إعلانات أو مرشحون.

    الصلاحية تتغير حسب الكيان: الإعلانات ← recruitment.posting.create،
    المرشحون ← recruitment.candidate.manage.
    """

    template_name = "recruitment/import.html"
    permission_code = "recruitment.posting.create"

    def dispatch(self, request, *args, **kwargs):
        entity = request.POST.get("entity") or request.GET.get("entity") or "postings"
        self.permission_code = (
            "recruitment.candidate.manage" if entity == "candidates" else "recruitment.posting.create"
        )
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        entity = request.POST.get("entity", "")
        file = request.FILES.get("file")
        if not file:
            messages.error(request, _("اختر ملفًا أولًا"))
            return redirect("recruitment:import")
        try:
            if file.name.lower().endswith(".sql"):
                table_map = imports.read_sql_tables(file)
                created, errors = {}, []
                for table_entity, records in table_map.items():
                    if not records:
                        continue
                    if table_entity == "candidates":
                        count, row_errors = imports.import_candidates(records, user=request.user)
                    else:
                        count, row_errors = imports.import_postings(records, user=request.user)
                    created[table_entity] = count
                    errors.extend(row_errors)
            else:
                entity = entity or "postings"
                if entity not in ("postings", "candidates"):
                    entity = "postings"
                records = imports.read_table(file)
                if entity == "candidates":
                    count, errors = imports.import_candidates(records, user=request.user)
                else:
                    count, errors = imports.import_postings(records, user=request.user)
                created = {entity: count}
        except imports.ImportFileError as exc:
            messages.error(request, str(exc))
            return redirect("recruitment:import")
        return self.render_to_response(
            self.get_context_data(entity=entity, created=created, errors=errors)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["entity"] = kwargs.get("entity", self.request.GET.get("entity", "postings"))
        if kwargs.get("created") is not None:
            ctx["created"] = kwargs["created"]
            ctx["errors"] = kwargs.get("errors", [])
        return ctx


class ImportTemplateView(PermissionRequiredMixin, View):
    """تنزيل نموذج جاهز للتعبئة — CSV/JSON/SQL (إعلانات أو مرشحون).

    الصيغة عبر ?fmt=csv|json|sql (الافتراضي csv).
    """

    permission_code = "recruitment.posting.create"

    def dispatch(self, request, *args, **kwargs):
        self.permission_code = (
            "recruitment.candidate.manage"
            if kwargs.get("entity") == "candidates"
            else "recruitment.posting.create"
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, entity):
        fmt = request.GET.get("fmt", "csv")
        if entity == "candidates":
            table, headers, sample = "recruitment_candidate", [
                "first_name_ar", "last_name_ar", "email", "phone", "source",
                "posting_code", "status", "first_name_fr", "last_name_fr",
                "first_name_en", "last_name_en", "applied_date", "notes",
            ], [
                "ليلى", "بن عمر", "lila@example.com", "0661", "موقع الوظائف",
                "JOB-003", "new", "Lila", "Ben Omar", "Lila", "Ben Omar",
                "2026-08-01", "",
            ]
        else:
            table, headers, sample = "recruitment_jobposting", [
                "code", "title_ar", "title_fr", "title_en", "department_code",
                "branch_code", "employment_type", "openings_count", "status",
                "publish_date", "close_date", "requirements", "description",
            ], [
                "JOB-101", "مطور برمجيات", "Développeur logiciel", "Software Developer",
                "DP-IT", "BR-01", "full_time", "2", "published",
                "2026-08-01", "2026-09-30", "", "",
            ]
        response = HttpResponse()
        if fmt == "json":
            response["Content-Type"] = "application/json; charset=utf-8"
            response["Content-Disposition"] = f'attachment; filename="hrms_{entity}_template.json"'
            payload = [dict(zip(headers, [value if value != "" else None for value in sample]))]
            response.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return response
        if fmt == "sql":
            response["Content-Type"] = "text/sql; charset=utf-8"
            response["Content-Disposition"] = f'attachment; filename="hrms_{entity}_template.sql"'
            values = ", ".join(_sql_literal(value) for value in sample)
            columns = ", ".join(headers)
            response.write(f"INSERT INTO {table} ({columns}) VALUES ({values});")
            return response
        response["Content-Type"] = "text/csv; charset=utf-8"
        response["Content-Disposition"] = f'attachment; filename="hrms_{entity}_template.csv"'
        writer = csv.writer(response)
        writer.writerow(headers)
        writer.writerow(sample)
        return response


def _sql_literal(value):
    if value in ("", None):
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"
