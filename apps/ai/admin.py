"""تسجيل نماذج الذكاء الاصطناعي في لوحة الإدارة (قراءة فقط للتنبؤات)."""

from django.contrib import admin

from apps.ai.models import AIPrediction, AIQuery, AnalyticsJob


@admin.register(AIPrediction)
class AIPredictionAdmin(admin.ModelAdmin):
    list_display = ("employee", "prediction_type", "probability", "level", "model_version", "created_at")
    list_filter = ("prediction_type", "level", "model_version")
    search_fields = ("employee__employee_code", "employee__first_name_ar", "employee__last_name_ar")
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        return False


@admin.register(AIQuery)
class AIQueryAdmin(admin.ModelAdmin):
    list_display = ("user", "prompt", "language", "created_at")
    search_fields = ("prompt", "user__username")
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        return False


@admin.register(AnalyticsJob)
class AnalyticsJobAdmin(admin.ModelAdmin):
    list_display = ("analysis_type", "status", "period_start", "period_end", "created_at")
    list_filter = ("analysis_type", "status")
    readonly_fields = ("created_at",)
