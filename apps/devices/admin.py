from django.contrib import admin

from .models import QrDevice, QrDeviceAudit


@admin.register(QrDevice)
class QrDeviceAdmin(admin.ModelAdmin):
    list_display = ("device_code", "branch", "status", "location", "last_seen")
    list_filter = ("status", "branch")
    search_fields = ("device_code", "location")


@admin.register(QrDeviceAudit)
class QrDeviceAuditAdmin(admin.ModelAdmin):
    list_display = ("device", "action", "created_at")
    list_filter = ("action",)
    readonly_fields = ("device", "action", "detail", "created_by", "created_at")
