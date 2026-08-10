"""HRMS — إعدادات الإنتاج (Prod Settings).

تُستخدم عبر: DJANGO_SETTINGS_MODULE=config.settings.prod
- PostgreSQL (D-02) — يتطلب psycopg + خادم LAN.
- كل إعدادات الأمان من docs/09-security.md.
"""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, _env

DEBUG = False

# لا نسمح بالجوكر في الإنتاج — عناوين LAN صريحة
ALLOWED_HOSTS = _env("DJANGO_ALLOWED_HOSTS", "").split(",")  # noqa: F405
ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h]

if not ALLOWED_HOSTS:
    raise ValueError("DJANGO_ALLOWED_HOSTS إلزامي في الإنتاج")

# قاعدة البيانات: PostgreSQL فقط (D-01/D-02)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _env("DJANGO_DB_NAME", "hrms"),  # noqa: F405
        "USER": _env("DJANGO_DB_USER", "hrms"),  # noqa: F405
        "PASSWORD": _env("DJANGO_DB_PASSWORD", ""),  # noqa: F405
        "HOST": _env("DJANGO_DB_HOST", "localhost"),  # noqa: F405
        "PORT": _env("DJANGO_DB_PORT", "5432"),  # noqa: F405
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
}

# ---- أمان الإنتاج (راجع 09-security.md) --------------------------------
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ---- الملفات الثابتة ----------------------------------------------------
STATIC_ROOT = BASE_DIR / "staticfiles"
