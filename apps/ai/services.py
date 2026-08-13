"""خدمات الذكاء الاصطناعي: تدريب + تنبؤ + تحديث النتائج.

لا تُتّخذ أي قرارات إدارية تلقائيًا — المخرجات مساعدة تُعرض على مسؤول بشري
(تحذير أخلاقي في docs/07-ai-module.md §14).
"""

from decimal import Decimal

from django.utils import timezone

from apps.ai import ml
from apps.ai.features import feature_frame
from apps.ai.models import AIPrediction
from apps.employees.models import Employee

LEVEL_THRESHOLDS = (Decimal("0.40"), Decimal("0.70"))


def level_for(probability: float) -> str:
    p = Decimal(str(round(probability, 3)))
    if p >= LEVEL_THRESHOLDS[1]:
        return "high"
    if p >= LEVEL_THRESHOLDS[0]:
        return "medium"
    return "low"


def retrain_model(prediction_type: str, employees=None) -> dict:
    """يُدرّب ويحفظ النموذج ثم يُحدّث تنبؤات الموظفين النشطين."""
    frame = feature_frame(employees)
    if frame.empty:
        raise ValueError("لا توجد بيانات كافية لتدريب النموذج.")
    artifact = ml.train_model(prediction_type, frame)
    ml.save_artifact(artifact)
    refresh_predictions(prediction_type, frame)
    return artifact


def refresh_predictions(prediction_type: str, frame=None) -> int:
    """يحسب احتمالات الموظفين النشطين ويحفظ/يحدّث سجلات AIPrediction."""
    artifact = ml.load_artifact(prediction_type)
    if artifact is None:
        raise ValueError("لا يوجد نموذج مدرَّب — شغّل أمر train_ai_models أولًا.")
    active = list(Employee.objects.filter(is_active=True))
    if not active:
        return 0
    if frame is None:
        frame = feature_frame(active)
    probs = ml.predict_frame(artifact, frame)
    updated = 0
    for emp, prob in zip(active, probs):
        p = Decimal(str(round(float(prob), 3)))
        factors = ml.top_factors(frame.loc[emp.id], artifact["feature_importances"])
        obj, _ = AIPrediction.objects.update_or_create(
            employee=emp,
            prediction_type=prediction_type,
            defaults={
                "probability": p,
                "level": level_for(float(prob)),
                "features_json": {f["feature"]: f["value"] for f in factors},
                "model_version": artifact["version"],
            },
        )
        updated += 1
    return updated


def predict_employee(employee) -> dict | None:
    """تنبؤ لموظف واحد من آخر نموذج محفوظ (بدون إعادة تدريب)."""
    artifact = ml.load_artifact(AIPrediction.Type.RESIGNATION)
    if artifact is None:
        return None
    frame = feature_frame([employee])
    prob = float(ml.predict_frame(artifact, frame)[0])
    return {
        "probability": prob,
        "level": level_for(prob),
        "factors": ml.top_factors(frame.loc[employee.id], artifact["feature_importances"]),
        "model_version": artifact["version"],
        "trained_at": artifact.get("trained_at", ""),
    }


def model_status(prediction_type: str) -> dict | None:
    artifact = ml.load_artifact(prediction_type)
    if artifact is None:
        return None
    return {
        "version": artifact["version"],
        "n_samples": artifact["n_samples"],
        "n_positive": artifact["n_positive"],
        "metrics": artifact["metrics"],
        "trained_at": artifact["trained_at"],
    }


def latest_predictions(prediction_type: str, employee=None):
    qs = AIPrediction.objects.filter(prediction_type=prediction_type).select_related("employee__department", "employee__position")
    if employee is not None:
        qs = qs.filter(employee=employee)
    return qs.order_by("-created_at")


def _now():
    return timezone.now()
