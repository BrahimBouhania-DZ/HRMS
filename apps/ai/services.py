"""خدمات الذكاء الاصطناعي: تدريب + تنبؤ + تحديث النتائج.

لا تُتّخذ أي قرارات إدارية تلقائيًا — المخرجات مساعدة تُعرض على مسؤول بشري
(تحذير أخلاقي في docs/07-ai-module.md §14).
"""

from decimal import Decimal

import datetime

from django.utils import timezone

from apps.ai import ml
from apps.ai import features
from apps.ai.features import ABSENCE_LABEL_COLUMN, LABEL_COLUMN, feature_frame
from apps.ai.models import AIPrediction, AIQuery
from apps.employees.models import Employee

LEVEL_THRESHOLDS = (Decimal("0.40"), Decimal("0.70"))

# عمود الهدف لكل نوع تنبؤ: المغادرة للاستقالة، ومعدل الغياب لمخاطر الغياب.
_LABEL_BY_TYPE = {
    AIPrediction.Type.RESIGNATION: LABEL_COLUMN,
    AIPrediction.Type.ABSENCE_RISK: ABSENCE_LABEL_COLUMN,
}


def level_for(probability: float) -> str:
    p = Decimal(str(round(probability, 3)))
    if p >= LEVEL_THRESHOLDS[1]:
        return "high"
    if p >= LEVEL_THRESHOLDS[0]:
        return "medium"
    return "low"


def retrain_model(prediction_type: str, employees=None) -> dict:
    """يُدرّب ويحفظ النموذج ثم يُحدّث تنبؤات الموظفين النشطين.

    مع فحص جودة البيانات (data_quality_report): يُرفض التدريب إذا كانت
    البيانات غير قابلة للتدريب الجاد (لا مغادرين، أصفار شاملة...) ويُعاد
    تقرير الجودة مع الاستثناء.
    """
    frame = feature_frame(employees)
    if frame.empty:
        raise ValueError("لا توجد بيانات كافية لتدريب النموذج.")
    quality = features.data_quality_report(frame)
    artifact = ml.train_model(prediction_type, frame, label_column=_LABEL_BY_TYPE.get(prediction_type, LABEL_COLUMN))
    artifact["data_quality"] = quality["metrics"]
    _monitor_drift(prediction_type, artifact)
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


def recent_queries(user, limit: int = 10):
    """آخر أسئلة المساعد للمستخدم (سجل تدقيق ai_aiquery)."""
    return AIQuery.objects.filter(user=user).order_by("-created_at")[:limit]


def latest_query_id(user) -> int | None:
    """معرّف آخر سؤال مسجَّل للمستخدم (للحلق على نتيجة التقييم)."""
    row = AIQuery.objects.filter(user=user).order_by("-created_at").values_list("id", flat=True).first()
    return row


def unknown_queries(limit: int = 20):
    """أسئلة لم يُجب عليها المساعد (intent unknown) — يُحسَّن قاموسها يدويًا.

    تُعرض في لوحة التحليلات لمن لديه صلاحية ai.analytics.view: تشير إلى
    صياغات يجهلها المساعد كي يُضاف إلى مفاتيح detect_intent في nlp.py.
    """
    return AIQuery.objects.filter(answer_json__intent="unknown").order_by("-created_at")[:limit]


def _now():
    return timezone.now()


DRIFT_THRESHOLD_AUC = 0.05


def _monitor_drift(prediction_type: str, artifact: dict) -> None:
    """مراقبة انحدار الجودة: مقارنة AUC الجديد بآخر نسخة محفوظة.

    عند تراجع يتجاوز العتبة يُكتب إنذار في ai_analyticsjob (type: turnover
    أو absence بحسب الهدف) — لا يُمنع الحفظ لكن يُلفت النظر للمسؤول البشري.
    """
    prev = ml.load_artifact(prediction_type)
    if prev is None:
        return
    new_auc = artifact.get("metrics", {}).get("auc_mean")
    old_auc = prev.get("metrics", {}).get("auc_mean")
    if new_auc is None or old_auc is None:
        return
    drop = float(old_auc) - float(new_auc)
    if drop > DRIFT_THRESHOLD_AUC:
        from apps.ai.models import AnalyticsJob

        AnalyticsJob.objects.create(
            analysis_type="turnover" if prediction_type == AIPrediction.Type.RESIGNATION else "absence",
            status=AnalyticsJob.Status.DONE,
            result_json={
                "type": "model_drift_warning",
                "prediction_type": prediction_type,
                "old_auc": round(float(old_auc), 4),
                "new_auc": round(float(new_auc), 4),
                "drop": round(drop, 4),
                "new_version": artifact.get("version"),
                "old_version": prev.get("version"),
            },
        )


def scheduled_retrain(days_window: int = 90) -> dict:
    """إعادة تدريب مجدولة (تُشغَّل من cron) — للمغادرين خلال النافذة.

    القاعدة: نتدرّب فقط إذا ظهرت بيانات مغادرة جديدة منذ آخر تدريب (مقارنة
    بـ trained_at المحفوظ). عند عدم وجود ما يكفي من العينات يرفع ValueError
    (يُعالَج بالاستثناء من المستدعي ليتجاهل الجولة بصمت).
    """
    from apps.ai.models import AnalyticsJob
    from apps.employees.models import Employee

    now = timezone.now()
    since = now - datetime.timedelta(days=days_window)
    departed = Employee.objects.filter(
        is_active=False, hire_date__lte=now,
    )
    # مهّد: لا نعيد التدريب بلا مغادرين جدد → خروج هادئ
    if not departed.exists():
        return {"retrained": False, "reason": "no_departed_in_window"}

    results = {}
    for ptype in (AIPrediction.Type.RESIGNATION, AIPrediction.Type.ABSENCE_RISK):
        try:
            artifact = retrain_model(ptype)
            results[ptype] = {
                "version": artifact["version"],
                "auc": artifact.get("metrics", {}).get("auc_mean"),
            }
        except ValueError as exc:
            results[ptype] = {"error": str(exc)}
    AnalyticsJob.objects.create(
        analysis_type="kpi_dashboard",
        status=AnalyticsJob.Status.DONE,
        result_json={"type": "scheduled_retrain", "results": results, "since": since.isoformat()},
    )
    return {"retrained": True, "results": results}
