"""معالج سياق عام — معلومات المنصة لكل القوالب + حقن ألوان الهوية المخصصة."""

from django.conf import settings
from django.utils import translation

from .branding_utils import build_css_block
from .models import CompanySettings


def app_info(request):
    lang = translation.get_language()
    return {
        "APP_NAME": "HRMS",
        "APP_VERSION": "0.1.0",
        "LANGUAGES": settings.LANGUAGES,
        "LANGUAGE_CODE": lang,
        "LANGUAGE_DIR": "rtl" if lang == "ar" else "ltr",
    }


def company_info(request):
    """هوية الشركة (الاسم + الشعار) لكل القوالب — يُستخدم في رأس الموقع وخلفية طباعة البطاقات."""
    company = CompanySettings.get_default()
    overrides = company.css_overrides if company else {}
    css_block = build_css_block(overrides)
    branding_css = f"<style>{css_block}</style>" if css_block else ""
    return {
        "COMPANY": company,
        "BRANDING_CSS": branding_css,
    }
