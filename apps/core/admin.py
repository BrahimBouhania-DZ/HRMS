from django.contrib import admin
from django.utils.html import format_html

from .models import AuditLog, CompanySettings


@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    """إعدادات هوية الشركة — سجل وحيد يُعدَّل من قسم «هوية الشركة»."""

    list_display = ("company_name_ar", "tagline", "show_logo_watermark", "watermark_opacity", "logo_preview")

    def has_add_permission(self, request):
        # سجل واحد فقط — لا يُضاف ثانٍ بعد وجوده.
        return CompanySettings.objects.count() == 0

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="الشعار")
    def logo_preview(self, obj):
        if obj and obj.logo:
            return format_html('<img src="{}" style="max-height:42px;border-radius:6px;" alt="logo">', obj.logo.url)
        return "—"


# هوية لوحة الإدارة (يُظهرها base_site.html)
admin.site.site_header = "HRMS — نظام إدارة الموارد البشرية"
admin.site.site_title = "HRMS"
admin.site.index_title = "لوحة تحكم الموارد البشرية"
admin.site.index_template = "admin/index.html"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """سجل تدقيق — للقراءة فقط (append-only)."""

    list_display = ("created_at", "user", "action", "model_name", "object_repr", "ip")
    list_filter = ("action", "model_name", "created_at")
    search_fields = ("object_repr", "user__username", "detail")
    list_select_related = ("user",)
    readonly_fields = ("created_at", "user", "action", "model_name", "object_id", "object_repr", "detail", "ip")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
