"""مسارات الوحدة الأساسية (توجيه الصفحة الرئيسية بعد تسجيل الدخول).

يُسجَّل المسار السري للشعار والألوان فقط إن كان BRANDING_SECRET_PATH مضبوطًا في .env.
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views
from .views_branding import branding_dashboard, branding_login, branding_logout, branding_save_colors, branding_save_identity, branding_save_logo

app_name = "core"

urlpatterns = [
    path("", login_required(views.home), name="home"),
    path("search/", views.search, name="search"),
    path("audit/", views.AuditLogView.as_view(), name="audit_log"),
]

# ---- صفحة التحكم السرية (شعار + ألوان) — المسار يُقرأ من .env فقط ----
_secret = getattr(settings, "BRANDING_SECRET_PATH", "")
if _secret:
    urlpatterns += [
        path(f"{_secret}/", branding_login, name="branding_login"),
        path(f"{_secret}/dashboard/", branding_dashboard, name="branding_dashboard"),
        path(f"{_secret}/save-logo/", branding_save_logo, name="branding_save_logo"),
        path(f"{_secret}/save-colors/", branding_save_colors, name="branding_save_colors"),
        path(f"{_secret}/save-identity/", branding_save_identity, name="branding_save_identity"),
        path(f"{_secret}/logout/", branding_logout, name="branding_logout"),
    ]
