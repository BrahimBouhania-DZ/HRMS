from django.contrib import admin

from .models import Branch, Department, Position, Shift


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "city", "country", "timezone")
    search_fields = ("code", "name_ar", "name_fr", "city")
    list_filter = ("country",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "branch", "parent", "manager")
    search_fields = ("code", "name_ar", "name_fr")
    list_filter = ("branch",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "department", "grade")
    search_fields = ("code", "name_ar", "name_fr")
    list_filter = ("department",)


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "start_time", "end_time", "is_flexible", "grace_minutes")
    search_fields = ("code", "name_ar")
