"""HRMS — الإعدادات الافتراضية (Default Settings).

يستورد إعدادات التطوير (config.settings.dev) افتراضيًا.
التبديل: DJANGO_SETTINGS_MODULE=config.settings.prod (إنتاج) أو .test (اختبار).
"""

from .dev import *  # noqa: F401,F403
