"""نماذج الموظفين (T-013..T-018)."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Employee(BaseModel):
    """T-013 — سجل الموظف (حالة وظيفية، بيانات تعريفية)."""

    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", _("نشط")
        PROBATION = "probation", _("تحت التجربة")
        SUSPENDED = "suspended", _("موقوف")
        TERMINATED = "terminated", _("منتهي")
        RESIGNED = "resigned", _("مستقيل")
        RETIRED = "retired", _("متقاعد")

    employee_code = models.CharField(_("رقم الموظف"), max_length=30, unique=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("حساب المستخدم"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee_profile",
    )
    first_name_ar = models.CharField(_("الاسم (عربي)"), max_length=100)
    last_name_ar = models.CharField(_("اللقب (عربي)"), max_length=100)
    first_name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=100, blank=True)
    last_name_fr = models.CharField(_("اللقب (فرنسي)"), max_length=100, blank=True)
    first_name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=100, blank=True)
    last_name_en = models.CharField(_("اللقب (إنجليزي)"), max_length=100, blank=True)
    gender = models.CharField(_("الجنس"), max_length=1, choices=[("M", _("ذكر")), ("F", _("أنثى"))], blank=True)
    birth_date = models.DateField(_("تاريخ الميلاد"), null=True, blank=True)
    hire_date = models.DateField(_("تاريخ التوظيف"), null=True, blank=True)
    phone = models.CharField(_("الهاتف"), max_length=30, blank=True)
    email = models.EmailField(_("البريد الإلكتروني"), blank=True)
    address = models.TextField(_("العنوان"), blank=True)
    bank_account = models.CharField(_("الحساب البنكي"), max_length=50, blank=True, help_text=_("لتصدير البنك (FR-PAY-008)"))
    photo = models.ImageField(_("الصورة"), upload_to="employees/photos/", null=True, blank=True)
    employment_status = models.CharField(
        _("الحالة الوظيفية"),
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    branch = models.ForeignKey(
        "org.Branch",
        verbose_name=_("الفرع"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    department = models.ForeignKey(
        "org.Department",
        verbose_name=_("القسم"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    position = models.ForeignKey(
        "org.Position",
        verbose_name=_("المنصب"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    shift = models.ForeignKey(
        "org.Shift",
        verbose_name=_("جدول الدوام"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )

    class Meta:
        verbose_name = _("موظف")
        verbose_name_plural = _("الموظفون")

    def __str__(self):
        return f"{self.employee_code} — {self.first_name_ar} {self.last_name_ar}"


class EmploymentHistory(BaseModel):
    """T-014 — سجل توظيفي (تغيير قسم/منصب/حالة)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="history")
    branch = models.ForeignKey("org.Branch", verbose_name=_("الفرع"), on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey("org.Department", verbose_name=_("القسم"), on_delete=models.PROTECT, related_name="+")
    position = models.ForeignKey("org.Position", verbose_name=_("المنصب"), on_delete=models.PROTECT, related_name="+")
    effective_from = models.DateField(_("ساري من"))
    effective_to = models.DateField(_("ساري حتى"), null=True, blank=True)
    is_current = models.BooleanField(_("الحالي"), default=True)

    class Meta:
        verbose_name = _("سجل توظيفي")
        verbose_name_plural = _("السجل الوظيفي")

    def __str__(self):
        return f"{self.employee} → {self.position}"


class Contract(BaseModel):
    """T-015 — عقد العمل."""

    class ContractType(models.TextChoices):
        CDI = "cdi", _("عقد دائم")
        CDD = "cdd", _("عقد محدد المدة")
        STAGE = "stage", _("تدريب")

    contract_number = models.CharField(_("رقم العقد"), max_length=50, unique=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="contracts")
    contract_type = models.CharField(_("نوع العقد"), max_length=10, choices=ContractType.choices, default=ContractType.CDI)
    start_date = models.DateField(_("بداية العقد"))
    end_date = models.DateField(_("نهاية العقد"), null=True, blank=True)
    gross_salary = models.DecimalField(_("الأجر الإجمالي"), max_digits=15, decimal_places=2)
    base_salary = models.DecimalField(_("الأجر الأساسي"), max_digits=15, decimal_places=2)
    allowance = models.DecimalField(_("العلاوات"), max_digits=15, decimal_places=2, default=0)
    currency = models.CharField(_("العملة"), max_length=3, default="DZD")

    class Meta:
        verbose_name = _("عقد")
        verbose_name_plural = _("العقود")

    def __str__(self):
        return f"{self.contract_number} — {self.employee}"


class Document(BaseModel):
    """T-016 — مستند (هوية، شهادة، عقد…)."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(_("نوع المستند"), max_length=50)
    title = models.CharField(_("العنوان"), max_length=200)
    file = models.FileField(_("الملف"), upload_to="employees/documents/")
    issued_date = models.DateField(_("تاريخ الإصدار"), null=True, blank=True)
    expiry_date = models.DateField(_("تاريخ الانتهاء"), null=True, blank=True)

    class Meta:
        verbose_name = _("مستند")
        verbose_name_plural = _("المستندات")

    def __str__(self):
        return self.title


class EmployeeQR(BaseModel):
    """T-018 — سجل QR للموظف (نسخة نشطة واحدة فقط لكل موظف).

    المرجع: docs/06-qr-system.md §4 (دورة الحياة) + docs/03 §3.3.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", _("نشط")
        REVOKED = "revoked", _("مُلغى")
        EXPIRED = "expired", _("منتهي")

    employee = models.OneToOneField(
        Employee,
        verbose_name=_("الموظف"),
        on_delete=models.CASCADE,
        related_name="qr_record",
    )
    secret = models.CharField(_("السر"), max_length=32, unique=True)
    version = models.PositiveSmallIntegerField(_("الإصدار"), default=1)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.ACTIVE)
    activated_at = models.DateTimeField(_("فُعّل في"), auto_now_add=True)
    expires_at = models.DateTimeField(_("ينتهي في"), null=True, blank=True)
    revoked_at = models.DateTimeField(_("أُلغي في"), null=True, blank=True)
    revoked_by = models.ForeignKey(
        "auth_app.User",
        verbose_name=_("ألغاه"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revoked_qrs",
    )

    class Meta:
        verbose_name = _("رمز QR")
        verbose_name_plural = _("رموز QR")

    def __str__(self):
        return f"QR {self.employee} v{self.version}"
