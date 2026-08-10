from django.contrib import admin

from .models import AttendanceDay, AttendanceException, AttendanceScan


@admin.register(AttendanceDay)
class AttendanceDayAdmin(admin.ModelAdmin):
    list_display = (
        "employee", "work_date", "state", "check_in", "check_out",
        "worked_minutes", "late_minutes", "is_corrected",
    )
    list_filter = ("state", "work_date", "is_corrected")
    search_fields = ("employee__employee_code", "employee__first_name_ar")
    date_hierarchy = "work_date"


@admin.register(AttendanceScan)
class AttendanceScanAdmin(admin.ModelAdmin):
    list_display = ("employee", "scanned_at", "source", "device", "decision", "result_detail")
    list_filter = ("decision", "source")
    search_fields = ("employee__employee_code",)
    date_hierarchy = "scanned_at"


@admin.register(AttendanceException)
class AttendanceExceptionAdmin(admin.ModelAdmin):
    list_display = ("employee", "type", "from_time", "to_time", "hours", "status")
    list_filter = ("type", "status")
    search_fields = ("employee__employee_code", "employee__first_name_ar")
