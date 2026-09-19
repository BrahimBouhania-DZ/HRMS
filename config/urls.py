"""HRMS — المسارات الجذرية."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("sec-admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("apps.core.urls", namespace="core")),
    path("auth/", include("apps.auth_app.urls", namespace="auth_app")),
    path("org/", include("apps.org.urls")),
    path("employees/", include("apps.employees.urls")),
    path("attendance/", include("apps.attendance.urls", namespace="attendance")),
    path("leave/", include("apps.leave.urls", namespace="leave")),
    path("notifications/", include("apps.notif.urls", namespace="notif")),
    path("reports/", include("apps.reports.urls", namespace="reports")),
    path("devices/", include("apps.devices.urls", namespace="devices")),
    path("payroll/", include("apps.payroll.urls", namespace="payroll")),
    path("backup/", include("apps.backup.urls", namespace="backup")),
    path("perf/", include("apps.perf.urls", namespace="perf")),
    path("training/", include("apps.training.urls", namespace="training")),
    path("recruitment/", include("apps.recruitment.urls", namespace="recruitment")),
    path("ai/", include("apps.ai.urls", namespace="ai")),
    path("api/v1/", include("apps.api.urls", namespace="api")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
