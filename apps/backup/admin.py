"""إدارة النسخ الاحتياطي — سجلات للقراءة فقط + إعدادات (T-044/045/046)."""

from django.contrib import admin

from .models import BackupJob, BackupSettings, RestoreJob


@admin.register(BackupSettings)
class BackupSettingsAdmin(admin.ModelAdmin):
    list_display = ("enabled", "backup_dir", "retention_count", "encrypt", "updated_at")
    # سجل وحيد — يمنع إضافة أكثر من واحد
    def has_add_permission(self, request):
        return not BackupSettings.objects.exists()


@admin.register(BackupJob)
class BackupJobAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "file_path", "file_size", "encrypted", "started_at", "duration_seconds")
    list_filter = ("status", "kind", "encrypted")
    search_fields = ("file_path", "error")
    readonly_fields = ("kind", "status", "file_path", "file_size", "checksum", "encrypted", "error", "started_at", "finished_at", "duration_seconds", "created_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RestoreJob)
class RestoreJobAdmin(admin.ModelAdmin):
    list_display = ("source_file", "status", "checksum_verified", "restored_at", "restored_by")
    list_filter = ("status", "checksum_verified")
    readonly_fields = ("source_file", "checksum_verified", "status", "error", "restored_at", "restored_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
