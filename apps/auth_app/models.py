"""إدارة المستخدمين المخصصة (T-001..T-008)."""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class UserManager(BaseUserManager):
    """مدير المستخدمين — يُنشئ المستخدم العادي والمشرف."""

    use_in_migrations = True

    def _create_user(self, username, email, password, **extra):
        if not username:
            raise ValueError(_("اسم المستخدم إلزامي"))
        email = self.normalize_email(email) if email else None
        user = self.model(username=username, email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra)

    def create_superuser(self, username, email=None, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create_user(username, email, password, **extra)


class User(AbstractUser, TimeStampedModel):
    """T-001 — مستخدم النظام (يرتبط 0..1 بملف موظف)."""

    LANGUAGE_CHOICES = [
        ("ar", _("العربية")),
        ("fr", _("Français")),
        ("en", _("English")),
    ]

    email = models.EmailField(_("البريد الإلكتروني"), unique=True, null=True, blank=True)
    mfa_enabled = models.BooleanField(_("MFA مفعّل"), default=False)
    mfa_secret = models.CharField(_("سر MFA"), max_length=64, null=True, blank=True, editable=False)
    language = models.CharField(_("اللغة"), max_length=5, choices=LANGUAGE_CHOICES, default="ar")
    timezone = models.CharField(_("المنطقة الزمنية"), max_length=64, default="Africa/Algiers")
    failed_attempts = models.PositiveSmallIntegerField(_("محاولات فاشلة"), default=0)
    locked_until = models.DateTimeField(_("مقفل حتى"), null=True, blank=True)
    password_changed_at = models.DateTimeField(_("آخر تغيير لكلمة المرور"), null=True, blank=True)

    objects = UserManager()

    class Meta:
        verbose_name = _("مستخدم")
        verbose_name_plural = _("المستخدمون")

    def __str__(self):
        return self.get_full_name() or self.username


class Role(TimeStampedModel):
    """T-002 — دور (is_system: الأدوار المدمجة لا تُحذف)."""

    code = models.CharField(_("الرمز"), max_length=50, unique=True)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    description = models.TextField(_("الوصف"), blank=True)
    is_system = models.BooleanField(_("دور مدمج"), default=False)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("دور أب (ميراث)"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    class Meta:
        verbose_name = _("دور")
        verbose_name_plural = _("الأدوار")

    def __str__(self):
        return self.name_ar


class Permission(TimeStampedModel):
    """T-003 — مفردة صلاحية بصيغة module.object.action."""

    code = models.CharField(_("الكود"), max_length=100, unique=True)
    module = models.CharField(_("الوحدة"), max_length=50)
    name_ar = models.CharField(_("الاسم (عربي)"), max_length=150)
    name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=150, blank=True)
    name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=150, blank=True)
    description = models.TextField(_("الوصف"), blank=True)

    class Meta:
        verbose_name = _("صلاحية")
        verbose_name_plural = _("الصلاحيات")

    def __str__(self):
        return self.code


class RolePermission(models.Model):
    """T-005 — ربط دور بصلاحيات."""

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permission_links")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_links")

    class Meta:
        unique_together = ("role", "permission")
        verbose_name = _("صلاحية دور")
        verbose_name_plural = _("صلاحيات الأدوار")

    def __str__(self):
        return f"{self.role} → {self.permission}"


class RoleMember(TimeStampedModel):
    """T-004 — تعيين مستخدم لدور (مع نطاق فرع وتواريخ سريان)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_memberships")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="members")
    branch_scope = models.ForeignKey(
        "org.Branch",
        verbose_name=_("نطاق الفرع"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="role_members",
    )
    effective_from = models.DateField(_("ساري من"), null=True, blank=True)
    effective_to = models.DateField(_("ساري حتى"), null=True, blank=True)

    class Meta:
        unique_together = ("user", "role", "branch_scope")
        verbose_name = _("تعيين دور")
        verbose_name_plural = _("تعيينات الأدوار")

    def __str__(self):
        return f"{self.user} ← {self.role}"


class UserPermission(models.Model):
    """T-006 — استثناء مباشر لمستخدم (grant/deny يتجاوز الدور)."""

    GRANT = "grant"
    DENY = "deny"
    ACTION_CHOICES = [(GRANT, _("منح")), (DENY, _("منع"))]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="permission_exceptions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="user_exceptions")
    action = models.CharField(_("الإجراء"), max_length=5, choices=ACTION_CHOICES, default=GRANT)

    class Meta:
        unique_together = ("user", "permission")
        verbose_name = _("استثناء صلاحية")
        verbose_name_plural = _("استثناءات الصلاحيات")

    def __str__(self):
        return f"{self.user} {self.action} {self.permission}"
