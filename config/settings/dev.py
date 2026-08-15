"""HRMS — إعدادات التطوير (Dev Settings).

تُستخدم عبر: DJANGO_SETTINGS_MODULE=config.settings.dev
- SQLite مؤقتًا (راجع D-02؛ PostgreSQL يُفعَّل في prod أو عبر env).
- DEBUG نشط + أدوات مريحة للتطوير.
"""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, _env

DEBUG = True

# dev فقط — يُقيَّد في prod.py عبر env
ALLOWED_HOSTS = ["*"]

# تحذير صارخ إذا كان المفتاح لا يزال الافتراضي في غير التطوير
if DEBUG and _env("DJANGO_SECRET_KEY") is None:
    import warnings

    warnings.warn(
        "DJANGO_SECRET_KEY غير مضبوط في .env — يُستخدم مفتاح dev ثابت. "
        "في الإنتاج (prod.py) يصبح المفتاح الافتراضي غير صالح.",
        stacklevel=2,
    )

# قاعدة بيانات التطوير (SQLite مؤقتًا؛ ويمكن التبديل لـ PostgreSQL عبر env)
if _env("DJANGO_DB_ENGINE", "sqlite") == "postgres":  # noqa: F405
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _env("DJANGO_DB_NAME", "hrms"),  # noqa: F405
            "USER": _env("DJANGO_DB_USER", "hrms"),  # noqa: F405
            "PASSWORD": _env("DJANGO_DB_PASSWORD", ""),  # noqa: F405
            "HOST": _env("DJANGO_DB_HOST", "localhost"),  # noqa: F405
            "PORT": _env("DJANGO_DB_PORT", "5432"),  # noqa: F405
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
