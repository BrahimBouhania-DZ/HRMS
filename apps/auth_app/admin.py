"""تسجيل النماذج في لوحة الإدارة."""

from django.contrib import admin

from .models import Permission, Role, RoleMember, RolePermission, User, UserPermission


class RoleMemberInline(admin.TabularInline):
    """تعيين المستخدم لأدوار (مع نطاق الفرع) — مباشرة داخل صفحة المستخدم."""

    model = RoleMember
    fk_name = "user"
    extra = 0
    verbose_name = "تعيين دور"
    verbose_name_plural = "أدوار المستخدم"
    autocomplete_fields = ["role", "branch_scope"]


class UserPermissionInline(admin.TabularInline):
    """استثناءات مباشرة (منح/منع) تتجاوز الدور — داخل صفحة المستخدم."""

    model = UserPermission
    fk_name = "user"
    extra = 0
    verbose_name = "استثناء صلاحية"
    verbose_name_plural = "استثناءات الصلاحيات (تتجاوز الدور)"
    autocomplete_fields = ["permission"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "roles_display", "is_staff", "is_active", "language", "mfa_enabled")
    list_filter = ("is_staff", "is_active", "language", "mfa_enabled")
    search_fields = ("username", "email", "first_name", "last_name")
    inlines = [RoleMemberInline, UserPermissionInline]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("معلومات شخصية", {"fields": ("first_name", "last_name", "email", "language", "timezone")}),
        ("الصلاحيات", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("أمان", {"fields": ("mfa_enabled", "mfa_secret", "failed_attempts", "locked_until", "password_changed_at")}),
        ("تواريخ مهمة", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("mfa_secret", "failed_attempts", "locked_until", "password_changed_at")

    @admin.display(description="الأدوار")
    def roles_display(self, obj):
        return ", ".join(m.role.name_ar for m in obj.role_memberships.select_related("role")[:5]) or "—"


class RolePermissionInline(admin.TabularInline):
    """صلاحيات الدور — تُدار داخل صفحة الدور مباشرة."""

    model = RolePermission
    extra = 0
    verbose_name = "صلاحية"
    verbose_name_plural = "صلاحيات هذا الدور"
    autocomplete_fields = ["permission"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name_ar", "members_count", "permissions_count", "is_system", "parent")
    search_fields = ("code", "name_ar")
    list_filter = ("is_system",)
    inlines = [RolePermissionInline]

    @admin.display(description="عدد الأعضاء")
    def members_count(self, obj):
        return obj.members.count()

    @admin.display(description="عدد الصلاحيات")
    def permissions_count(self, obj):
        return obj.permission_links.count()


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "module", "name_ar")
    list_filter = ("module",)
    search_fields = ("code", "module", "name_ar")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")
    autocomplete_fields = ["role", "permission"]


@admin.register(RoleMember)
class RoleMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "branch_scope", "effective_from", "effective_to")
    autocomplete_fields = ["user", "role", "branch_scope"]


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "permission", "action")
    autocomplete_fields = ["user", "permission"]
