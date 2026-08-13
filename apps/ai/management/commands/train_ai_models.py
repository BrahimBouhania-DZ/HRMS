"""أمر تدريب نماذج التنبؤ (train_ai_models).

الاستخدام:
    python manage.py train_ai_models                          # تدريب مخاطر الاستقالة
    python manage.py train_ai_models --type absence_risk      # نموذج غياب
    python manage.py train_ai_models --all                    # كلا النموذجين

يتطلب بيانات كافية (≥ 5 عينات إيجابية) — مولّد البيانات: seed_ai_data.
"""

from django.core.management.base import BaseCommand

from apps.ai import services
from apps.ai.models import AIPrediction


class Command(BaseCommand):
    help = "تدريب نماذج التنبؤ: تحقق متقاطع + حفظ + تحديث التنبؤات"

    def add_arguments(self, parser):
        parser.add_argument("--type", type=str, default=AIPrediction.Type.RESIGNATION,
                            choices=[AIPrediction.Type.RESIGNATION, AIPrediction.Type.ABSENCE_RISK])
        parser.add_argument("--all", action="store_true", help="درّب كلا النموذجين")

    def handle(self, *args, **options):
        types = [AIPrediction.Type.RESIGNATION, AIPrediction.Type.ABSENCE_RISK] if options["all"] else [options["type"]]
        for prediction_type in types:
            try:
                artifact = services.retrain_model(prediction_type)
            except ValueError as exc:
                self.stderr.write(self.style.ERROR(f"{prediction_type}: {exc}"))
                continue
            m = artifact["metrics"]
            self.stdout.write(self.style.SUCCESS(
                f"{prediction_type}: {artifact['version']} — عينات {artifact['n_samples']} "
                f"(إيجابية {artifact['n_positive']}) — AUC {m['auc_mean']}±{m['auc_std']} "
                f"| PRC {m['prc_max']} | Recall {m['recall_max']}"
            ))
