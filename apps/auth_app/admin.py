"""تسجيل النماذج في لوحة الإدارة."""

from django.contrib import admin

from .models import Permission, Role, RoleMember, RolePermission, User, UserPermission


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "is_staff", "is_active", "language", "mfa_enabled")
    list_filter = ("is_staff", "is_active", "language", "mfa_enabled")
    search_fields = ("username", "email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("معلومات شخصية", {"fields": ("first_name", "last_name", "email", "language", "timezone")}),
        ("الصلاحيات", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("أمان", {"fields": ("mfa_enabled", "mfa_secret", "failed_attempts", "locked_until", "password_changed_at")}),
        ("تواريخ مهمة", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("mfa_secret", "failed_attempts", "locked_until", "password_changed_at")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "is_system", "parent")
    search_fields = ("code", "name_ar")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "module", "name_ar")
    list_filter = ("module",)
    search_fields = ("code", "module", "name_ar")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")


@admin.register(RoleMember)
class RoleMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "branch_scope", "effective_from", "effective_to")


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "permission", "action")
