"""إدارة الرواتب (v2)."""

from django.contrib import admin
from django.utils.translation import gettext as _

from .models import (
    EndOfService,
    PayElement,
    PayRun,
    PayrollLine,
    PayrollSettings,
    Payslip,
)


@admin.register(PayrollSettings)
class PayrollSettingsAdmin(admin.ModelAdmin):
    """إعدادات الحساب الآلي للخصم والغياب — للمدير أو موظف المالية المختص."""

    fieldsets = (
        (None, {"fields": ("salary_base_days", "eos_reward_factor")}),
        (
            _("خصم الغياب"),
            {"fields": ("absence_deduction_enabled", "absence_grace_days", "auto_mark_absent")},
        ),
    )


@admin.register(PayElement)
class PayElementAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "kind", "calculation", "amount", "percent", "is_active")
    list_filter = ("kind", "calculation", "is_active")


@admin.register(PayRun)
class PayRunAdmin(admin.ModelAdmin):
    list_display = ("period_code", "branch", "status", "total_net", "generated_by", "generated_at")
    list_filter = ("status", "period_code")


@admin.register(PayrollLine)
class PayrollLineAdmin(admin.ModelAdmin):
    list_display = ("pay_run", "employee", "element", "amount", "note")


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("employee", "pay_run", "net", "attended_days", "absent_days")
    list_filter = ("pay_run__period_code",)


@admin.register(EndOfService)
class EndOfServiceAdmin(admin.ModelAdmin):
    list_display = ("employee", "termination_date", "net", "status")
    list_filter = ("status",)
