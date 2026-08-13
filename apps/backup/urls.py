"""مسارات النسخ الاحتياطي والاستعادة (v2)."""

from django.urls import path

from . import views

app_name = "backup"

urlpatterns = [
    path("", views.BackupView.as_view(), name="page"),
    path("download/", views.BackupDownloadView.as_view(), name="download"),
]
