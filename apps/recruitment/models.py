"""نماذج التوظيف (T-REC-1..T-REC-3).

المرجع: docs/10-roadmap.md v4 (Recruitment) + docs/03 §3 (نمط النماذج).
القواعد:
    BR-REC-001  توظيف المرشح يُنشئ ملف موظف فريدًا ويربطه بالمرشح مرة واحدة.
    BR-REC-002  لا يُعاد فتح إعلان مُغلق؛ يفتح إعلان جديد بنسخة محدثة.
    BR-REC-003  إنهاء المرشح (رفض/تعيين/انسحاب) لا يسمح بأكثر من مقابلة جارية.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class JobPosting(BaseModel):
    """T-REC-1 — إعلان وظيفة (عنوان ثلاثي اللغات + قسم + حالة)."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("مسودة")
        PUBLISHED = "published", _("منشور")
        CLOSED = "closed", _("مغلق")

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", _("دوام كامل")
        PART_TIME = "part_time", _("دوام جزئي")
        CONTRACT = "contract", _("عقد محدد")
        INTERNSHIP = "internship", _("تدريب مهني")

    code = models.CharField(_("رمز الإعلان"), max_length=30, unique=True)
    title_ar = models.CharField(_("العنوان (عربي)"), max_length=200)
    title_fr = models.CharField(_("العنوان (فرنسي)"), max_length=200, blank=True)
    title_en = models.CharField(_("العنوان (إنجليزي)"), max_length=200, blank=True)
    department = models.ForeignKey(
        "org.Department",
        verbose_name=_("القسم"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="job_postings",
    )
    branch = models.ForeignKey(
        "org.Branch",
        verbose_name=_("الفرع"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="job_postings",
    )
    employment_type = models.CharField(
        _("نوع التوظيف"), max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    openings_count = models.PositiveSmallIntegerField(_("عدد الشواغر"), default=1)
    requirements = models.TextField(_("المتطلبات"), blank=True)
    description = models.TextField(_("الوصف"), blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.DRAFT)
    publish_date = models.DateField(_("تاريخ النشر"), null=True, blank=True)
    close_date = models.DateField(_("تاريخ الإغلاق"), null=True, blank=True)

    class Meta:
        verbose_name = _("إعلان وظيفة")
        verbose_name_plural = _("إعلانات الوظائف")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.code} — {self.title_ar}"

    @property
    def candidate_count(self):
        return self.candidates.count()


class Candidate(BaseModel):
    """T-REC-2 — مرشح (بيانات + حالة + مسار التوظيف)."""

    class Status(models.TextChoices):
        NEW = "new", _("جديد")
        SCREENING = "screening", _("قيد الفرز")
        INTERVIEWED = "interviewed", _("تمت المقابلة")
        OFFER = "offer", _("عرض وظيفي")
        HIRED = "hired", _("تم التوظيف")
        REJECTED = "rejected", _("مرفوض")
        WITHDRAWN = "withdrawn", _("انسحب")

    first_name_ar = models.CharField(_("الاسم (عربي)"), max_length=100)
    last_name_ar = models.CharField(_("اللقب (عربي)"), max_length=100)
    first_name_fr = models.CharField(_("الاسم (فرنسي)"), max_length=100, blank=True)
    last_name_fr = models.CharField(_("اللقب (فرنسي)"), max_length=100, blank=True)
    first_name_en = models.CharField(_("الاسم (إنجليزي)"), max_length=100, blank=True)
    last_name_en = models.CharField(_("اللقب (إنجليزي)"), max_length=100, blank=True)
    email = models.EmailField(_("البريد الإلكتروني"))
    phone = models.CharField(_("الهاتف"), max_length=30, blank=True)
    posting = models.ForeignKey(
        JobPosting,
        verbose_name=_("الإعلان"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidates",
    )
    source = models.CharField(_("المصدر"), max_length=30, blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.NEW)
    resume = models.FileField(_("السيرة الذاتية"), upload_to="recruitment/resumes/", null=True, blank=True)
    notes = models.TextField(_("ملاحظات"), blank=True)
    applied_date = models.DateField(_("تاريخ التقديم"), null=True, blank=True)
    hired_employee = models.OneToOneField(
        "employees.Employee",
        verbose_name=_("الموظف المعيّن"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = _("مرشح")
        verbose_name_plural = _("المرشحون")
        ordering = ("-applied_date", "-created_at")

    def __str__(self):
        return f"{self.first_name_ar} {self.last_name_ar}"

    @property
    def full_name(self):
        return f"{self.first_name_ar} {self.last_name_ar}"


class Interview(BaseModel):
    """T-REC-3 — مقابلة مرشح (موعد + محاور + درجة + نتيجة)."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("مجدولة")
        COMPLETED = "completed", _("مكتملة")
        CANCELLED = "cancelled", _("ملغاة")

    class Mode(models.TextChoices):
        IN_PERSON = "in_person", _("حضوري")
        PHONE = "phone", _("هاتف")
        VIDEO = "video", _("فيديو")

    candidate = models.ForeignKey(
        Candidate,
        verbose_name=_("المرشح"),
        on_delete=models.CASCADE,
        related_name="interviews",
    )
    interviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("المحاور"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="interviews",
    )
    scheduled_at = models.DateTimeField(_("موعد المقابلة"))
    mode = models.CharField(_("الطريقة"), max_length=20, choices=Mode.choices, default=Mode.IN_PERSON)
    status = models.CharField(_("الحالة"), max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    score = models.PositiveSmallIntegerField(_("الدرجة (0-100)"), null=True, blank=True)
    notes = models.TextField(_("الملاحظات"), blank=True)

    class Meta:
        verbose_name = _("مقابلة")
        verbose_name_plural = _("المقابلات")
        ordering = ("scheduled_at",)

    def __str__(self):
        return f"{self.candidate} — {self.scheduled_at:%Y-%m-%d %H:%M}"
