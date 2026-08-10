"""معالج سياق عام — معلومات المنصة لكل القوالب."""

from django.conf import settings
from django.utils import translation


def app_info(request):
    lang = translation.get_language()
    return {
        "APP_NAME": "HRMS",
        "APP_VERSION": "0.1.0",
        "LANGUAGES": settings.LANGUAGES,
        "LANGUAGE_CODE": lang,
        "LANGUAGE_DIR": "rtl" if lang == "ar" else "ltr",
    }
