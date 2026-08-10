from django.contrib import admin

from .models import LeaveApproval, LeaveBalance, LeaveRequest, LeaveType, PublicHoliday


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "days_per_year", "is_unpaid", "requires_approval_levels", "is_active")
    list_filter = ("is_active", "is_unpaid")
    search_fields = ("code", "name_ar")


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "year", "granted", "used", "carried_from", "adjusted", "remaining")
    list_filter = ("year", "leave_type")
    search_fields = ("employee__employee_code", "employee__first_name_ar")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "from_date", "to_date", "days", "status", "current_level", "submitted_at")
    list_filter = ("status", "leave_type")
    date_hierarchy = "from_date"


@admin.register(LeaveApproval)
class LeaveApprovalAdmin(admin.ModelAdmin):
    list_display = ("leave_request", "level", "approver", "action", "at")
    list_filter = ("action",)


@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name_ar", "branch", "is_recurring")
    list_filter = ("is_recurring", "branch")
    date_hierarchy = "date"
