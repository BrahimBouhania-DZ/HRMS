"""أمر إعادة تدريب مجدول (retrain_ai_models_scheduled).

للاستخدام مع cron: إعادة تدريب دورية دون إزعاج — يخرج بصمت إذا لم تظهر
بيانات مغادرة جديدة منذ آخر تدريب، ويسجّل نتيجة كل جولة في ai_analyticsjob
للمراقبة (انحدار AUC → إنذار انحراف تلقائي).

الاستخدام:
    python manage.py retrain_ai_models_scheduled [--window 90]
"""

import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ai import services
from apps.ai.models import AnalyticsJob


class Command(BaseCommand):
    help = "إعادة تدريب مجدولة مع مراقبة جودة (AUC drift) وتسجيل في ai_analyticsjob"

    def add_arguments(self, parser):
        parser.add_argument("--window", type=int, default=90, help="نافذة أيام المغادرين")

    def handle(self, *args, **options):
        window = options["window"]
        result = services.scheduled_retrain(days_window=window)
        if not result["retrained"]:
            self.stdout.write(f"لا بيانات مغادرة جديدة خلال {window} يومًا — تخطي.")
            return
        for ptype, res in result["results"].items():
            if "error" in res:
                self.stderr.write(self.style.WARNING(f"{ptype}: {res['error']}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"{ptype}: {res['version']} (AUC {res['auc']})"))