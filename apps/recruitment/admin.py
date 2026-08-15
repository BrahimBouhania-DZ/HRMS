"""إدارة التوظيف من لوحة الإدارة."""

from django.contrib import admin

from .models import Candidate, Interview, JobPosting


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ("code", "title_ar", "department", "branch", "employment_type", "status", "openings_count")
    list_filter = ("status", "employment_type", "department")
    search_fields = ("code", "title_ar")


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("first_name_ar", "last_name_ar", "posting", "email", "status", "applied_date")
    list_filter = ("status", "posting")
    search_fields = ("first_name_ar", "last_name_ar", "email")


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("candidate", "interviewer", "scheduled_at", "mode", "status", "score")
    list_filter = ("status", "mode")
    search_fields = ("candidate__first_name_ar", "candidate__last_name_ar")
