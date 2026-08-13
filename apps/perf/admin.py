"""إدارة قوالب/دورات التقييم من لوحة الإدارة."""

from django.contrib import admin

from .models import PerfCycle, PerfObjective, PerfReview, PerfTemplate, PipPlan


@admin.register(PerfCycle)
class PerfCycleAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "period_start", "period_end", "status")
    list_filter = ("status",)


@admin.register(PerfTemplate)
class PerfTemplateAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "is_active")
    list_filter = ("is_active",)


@admin.register(PerfReview)
class PerfReviewAdmin(admin.ModelAdmin):
    list_display = ("employee", "cycle", "self_score", "manager_score", "final_score", "status")
    list_filter = ("status", "cycle")


@admin.register(PerfObjective)
class PerfObjectiveAdmin(admin.ModelAdmin):
    list_display = ("review", "kpi_title", "weight", "score")


@admin.register(PipPlan)
class PipPlanAdmin(admin.ModelAdmin):
    list_display = ("review", "start_date", "end_date", "status")
    list_filter = ("status",)
