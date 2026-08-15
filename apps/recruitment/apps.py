from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RecruitmentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recruitment"
    verbose_name = _("التوظيف")
