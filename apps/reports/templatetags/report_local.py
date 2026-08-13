"""وسوم لغة التقارير: فلتر triname (اسم كيان حسب اللغة النشطة)."""

from django import template
from django.utils import translation

register = template.Library()


@register.filter
def triname(obj):
    """اسم كيان محلي (name_ar/name_fr/name_en) حسب اللغة النشطة."""
    if obj is None:
        return ""
    lang = translation.get_language()
    if lang == "fr" and getattr(obj, "name_fr", ""):
        return obj.name_fr
    if lang == "en" and getattr(obj, "name_en", ""):
        return obj.name_en
    return getattr(obj, "name_ar", "") or ""
