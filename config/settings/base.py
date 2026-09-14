"""HRMS — الإعدادات الأساسية المشتركة (Base Settings).

ملاحظة القرارات (راجع docs/11-decisions.md):
- بيئة الإنتاج (prod.py): PostgreSQL — وفق D-01/D-02.
- بيئة التطوير (dev.py): SQLite مؤقتًا حتى توفير PostgreSQL على خادم LAN.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_dotenv():
    """يقرأ ملف .env في جذر المشروع إن وُجد (لا يتجاوز متغيرات البيئة الحالية)."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _env(name: str, default=None):
    return os.environ.get(name, default)


# ---- الأمان الأساسي (يُكمَّل في prod.py) --------------------------------
SECRET_KEY = _env("DJANGO_SECRET_KEY", "django-insecure-change-me-in-production")
DEBUG = _env("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = _env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# ---- التطبيقات ----------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
]

LOCAL_APPS = [
    "apps.core",
    "apps.auth_app",
    "apps.org",
    "apps.employees",
    "apps.attendance",
    "apps.leave",
    "apps.payroll",
    "apps.notif",
    "apps.devices",
    "apps.reports",
    "apps.backup",
    "apps.perf",
    "apps.training",
    "apps.recruitment",
    "apps.ai",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---- النسخ الاحتياطي ------------------------------------------------------
# عبارة مرور اشتقاق مفتاح AES-256 لتشفير النسخ — تُضبط في .env في الإنتاج.
HRMS_BACKUP_KEY = _env("HRMS_BACKUP_KEY", "")

# ---- هوية الشركة: صفحة سرية (شعار + ألوان) للمبرمج/المدير ------------
# المسار السري يُسجَّل في urls فقط إن كان مضبوطًا؛ غيابه = لا يوجد مسار إطلاقًا.
# الحساب المميز يُنشأ بأمر: python manage.py seed_branding_admin
BRANDING_SECRET_PATH = _env("BRANDING_SECRET_PATH", "").strip("/")
BRANDING_ADMIN_USERNAME = _env("BRANDING_ADMIN_USERNAME", "branding-admin")
BRANDING_ADMIN_EMAIL = _env("BRANDING_ADMIN_EMAIL", "branding@hrms.local")

# ---- البريد (LAN Email) ---------------------------------------------------
# بريد إشعارات داخل الشبكة — خادم SMTP محلي/LAN تُضبط معطياته في .env.
# HRMS_EMAIL_ENABLED=False ⇒ تُسجَّل الرسائل على وحدة التحكم (dev) ولا تُرسل.
HRMS_EMAIL_ENABLED = _env("HRMS_EMAIL_ENABLED", "False") == "True"
EMAIL_BACKEND = _env("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = _env("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(_env("DJANGO_EMAIL_PORT", "25"))
EMAIL_HOST_USER = _env("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _env("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env("DJANGO_EMAIL_USE_TLS", "False") == "True"
EMAIL_USE_SSL = _env("DJANGO_EMAIL_USE_SSL", "False") == "True"
EMAIL_TIMEOUT = int(_env("DJANGO_EMAIL_TIMEOUT", "15"))
DEFAULT_FROM_EMAIL = _env("DJANGO_DEFAULT_FROM_EMAIL", "HRMS <hrms@lan.local>")

# ---- الوسيطات -----------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"

# ---- القوالب ------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app_info",
                "apps.core.context_processors.company_info",
                "apps.notif.context_processors.unread_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---- التحقق من كلمات المرور --------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "auth_app.User"

# ---- التدويل (i18n) — ثلاث لغات + RTL -----------------------------------
LANGUAGE_CODE = _env("DJANGO_LANGUAGE_CODE", "ar")
LANGUAGES = [
    ("ar", "العربية"),
    ("fr", "Français"),
    ("en", "English"),
]
LANGUAGE_COOKIE_NAME = "hrms_language"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = "Lax"

TIME_ZONE = _env("DJANGO_TIME_ZONE", "Africa/Algiers")
USE_I18N = True
USE_TZ = True

LOCALE_PATHS = [BASE_DIR / "locale"]

# ---- الملفات الثابتة والوسائط -------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---- الجلسات ------------------------------------------------------------
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "hrms_session"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

LOGIN_URL = "auth_app:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "auth_app:login"

# ---- واجهة API (DRF) ------------------------------------------------------
_DRF_RENDERERS = ["rest_framework.renderers.JSONRenderer"]
if DEBUG:
    _DRF_RENDERERS.append("rest_framework.renderers.BrowsableAPIRenderer")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": _DRF_RENDERERS,
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
