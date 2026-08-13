"""إدارة التدريب من لوحة الإدارة."""

from django.contrib import admin

from .models import TrainingCertificate, TrainingCourse, TrainingEnrollment, TrainingSession


@admin.register(TrainingCourse)
class TrainingCourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title_ar", "category", "provider", "cost", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("code", "title_ar")


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ("course", "start_date", "end_date", "trainer", "capacity", "status")
    list_filter = ("status",)


@admin.register(TrainingEnrollment)
class TrainingEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("employee", "session", "status", "approved_by")
    list_filter = ("status", "session")


@admin.register(TrainingCertificate)
class TrainingCertificateAdmin(admin.ModelAdmin):
    list_display = ("title", "enrollment", "issued_date")
    list_filter = ("issued_date",)
