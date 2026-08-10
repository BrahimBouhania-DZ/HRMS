from django.contrib import admin

from .models import Contract, Document, Employee, EmployeeQR, EmploymentHistory


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_code", "first_name_ar", "last_name_ar", "branch", "department", "position", "employment_status", "is_active")
    list_filter = ("employment_status", "is_active", "branch", "department")
    search_fields = ("employee_code", "first_name_ar", "last_name_ar", "first_name_fr")


@admin.register(EmploymentHistory)
class EmploymentHistoryAdmin(admin.ModelAdmin):
    list_display = ("employee", "position", "branch", "department", "effective_from", "is_current")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("contract_number", "employee", "contract_type", "start_date", "end_date", "gross_salary")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("employee", "title", "document_type", "issued_date", "expiry_date")


@admin.register(EmployeeQR)
class EmployeeQRAdmin(admin.ModelAdmin):
    list_display = ("employee", "version", "status", "activated_at", "expires_at", "revoked_at")
    list_filter = ("status",)
    search_fields = ("employee__employee_code", "employee__first_name_ar")
    readonly_fields = ("secret",)
