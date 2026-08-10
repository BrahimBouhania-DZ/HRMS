"""HRMS — إعدادات الاختبار على PostgreSQL (Tests over PostgreSQL).

الاستعمال:
    python manage.py test --settings=config.settings.test

تُشغّل مجموعة الاختبارات كاملةً ضد PostgreSQL مع تخفيف قيود أمان
الكوكيز (CSRF/Session/Secure) التي تتعارض مع عميل الاختبار عبر HTTP
(راجع: الاختبارات مصممة لبيئة dev). قاعدة الاختبار: <DJANGO_DB_NAME>_test.
"""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, _env

DEBUG = True
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _env("DJANGO_DB_NAME", "hrms_test"),  # noqa: F405
        "USER": _env("DJANGO_DB_USER", "hrms"),  # noqa: F405
        "PASSWORD": _env("DJANGO_DB_PASSWORD", ""),  # noqa: F405
        "HOST": _env("DJANGO_DB_HOST", "localhost"),  # noqa: F405
        "PORT": _env("DJANGO_DB_PORT", "5432"),  # noqa: F405
        "TEST": {"NAME": f"{_env('DJANGO_DB_NAME', 'hrms')}_test"},
    }
}

# تخفيف قيود الكوكيز لعميل الاختبار HTTP (لا يُستعمل في الإنتاج)
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
