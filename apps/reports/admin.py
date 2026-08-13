"""إدارة التقارير المجدولة (T-REP-5) — T-049..T-051."""

from django.contrib import admin

from .models import ReportDefinition, ReportGeneratedFile, ReportJob


class ReportJobInline(admin.TabularInline):
    model = ReportJob
    extra = 0
    readonly_fields = ("status", "started_at", "finished_at", "error")


class ReportGeneratedFileInline(admin.TabularInline):
    model = ReportGeneratedFile
    extra = 0
    readonly_fields = ("file_path", "format", "size_bytes", "expires_at")


@admin.register(ReportDefinition)
class ReportDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "template_type", "schedule", "run_at", "is_active", "last_run_at")
    list_filter = ("schedule", "template_type", "is_active")
    search_fields = ("code", "name_ar")
    filter_horizontal = ("notify_users", "notify_roles")
    inlines = [ReportJobInline]
    readonly_fields = ("last_run_at",)


@admin.register(ReportJob)
class ReportJobAdmin(admin.ModelAdmin):
    list_display = ("report", "status", "started_at", "finished_at")
    list_filter = ("status",)
    readonly_fields = ("report", "requested_by", "status", "started_at", "finished_at", "error")
    inlines = [ReportGeneratedFileInline]
