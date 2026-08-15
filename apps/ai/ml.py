"""نواة التعلّم الآلي: خط تدريب + تحقق متقاطع + حفظ/تحميل النموذج + تنبؤ.

قرارات التصميم (docs/07-ai-module.md §2/§5):
- انحدار لوجستي (LogisticRegression) — دقيق وقابل للتفسير على بيانات صغيرة.
- تحقق متقاطع Stratified K-Fold → AUC / Precision / Recall.
- غابة عشوائية إضافية للاحتفاظ بـ"أهمية الخصائص" (تفسير العوامل المساهمة).
- النموذج يُحفظ عبر joblib في MEDIA_ROOT/ai/models مع ملف بيانات تعريف (metadata).
- لا يُستخدم لأي قرار آلي — مجرد مساعدة إدارية (تحذير أخلاقي).
"""

import datetime
import json
import os

import joblib
import numpy as np
from django.conf import settings
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import auc as sk_auc
from sklearn.metrics import precision_recall_curve, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from apps.ai.features import ABSENCE_LABEL_COLUMN, CATEGORICAL_FEATURES, LABEL_COLUMN, NUMERIC_FEATURES

MODEL_SUBDIR = os.path.join("ai", "models")
RANDOM_STATE = 42
CV_FOLDS = 5
MIN_POSITIVE_SAMPLES = 5

_LABEL_COLUMNS = (LABEL_COLUMN, ABSENCE_LABEL_COLUMN)


def model_dir(prediction_type: str) -> str:
    base = getattr(settings, "MEDIA_ROOT", None)
    if not base:
        base = os.path.join(settings.BASE_DIR, "media")
    directory = os.path.join(base, MODEL_SUBDIR, prediction_type)
    os.makedirs(directory, exist_ok=True)
    return directory


def _next_version(prediction_type: str) -> str:
    directory = model_dir(prediction_type)
    existing = [d for d in os.listdir(directory) if d.startswith("v") and os.path.isdir(os.path.join(directory, d))]
    nums = [int(d[1:]) for d in existing if d[1:].isdigit()]
    return f"v{max(nums, default=0) + 1}"


def _pipeline() -> Pipeline:
    numeric = StandardScaler()
    categorical = OneHotEncoder(handle_unknown="ignore")
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric, NUMERIC_FEATURES),
            ("cat", categorical, CATEGORICAL_FEATURES),
        ]
    )
    return Pipeline(
        steps=[
            ("pre", preprocessor),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_STATE)),
        ]
    )


def _explainer(X, y) -> RandomForestClassifier:
    """نموذج تفسير مستقل (أهمية الخصائص على الميزات الخام)."""
    rf = RandomForestClassifier(n_estimators=150, random_state=RANDOM_STATE, n_jobs=-1)
    rf.fit(X[NUMERIC_FEATURES], y)
    return rf


def train_model(prediction_type: str, frame, label_column: str = LABEL_COLUMN) -> dict:
    """يُدرّب نموذجًا من DataFrame خصائص + عمود label ويعيد كائنًا جاهزًا.

    label_column يحدد عمود الهدف (مغادرة أو غياب). تُستبعد كل أعمدة التسمية
    من الخصائص دائمًا لمنع تسريب الهدف (data leakage).
    يرفع ValueError إذا كان عدد العينات الإيجابية غير كافٍ للتدريب الجاد.
    """
    X = frame.drop(columns=[c for c in _LABEL_COLUMNS if c in frame.columns], errors="ignore")
    y = frame[label_column].astype(int).values
    n_positive = int(y.sum())
    if n_positive < MIN_POSITIVE_SAMPLES:
        raise ValueError(
            f"عدد العينات الإيجابية {n_positive} أقل من الحد الأدنى {MIN_POSITIVE_SAMPLES} — "
            "أدرج بيانات موظفين مغادرين أولًا (seed_ai_data)."
        )

    pipeline = _pipeline()
    aucs, precs, recs = [], [], []
    skf = StratifiedKFold(n_splits=min(CV_FOLDS, min(np.bincount(y).min(), 2 * n_positive)), shuffle=True, random_state=RANDOM_STATE)
    for train_idx, test_idx in skf.split(X, y):
        fold = _pipeline()
        fold.fit(X.iloc[train_idx], y[train_idx])
        proba = fold.predict_proba(X.iloc[test_idx])[:, 1]
        aucs.append(roc_auc_score(y[test_idx], proba))
        precision, recall, _ = precision_recall_curve(y[test_idx], proba)
        precs.append(precision[np.argmax(precision * recall)])
        recs.append(recall[np.argmax(precision * recall)])

    pipeline.fit(X, y)
    explainer = _explainer(X, y)
    importances = dict(zip(NUMERIC_FEATURES, explainer.feature_importances_))

    artifact = {
        "prediction_type": prediction_type,
        "version": _next_version(prediction_type),
        "model": pipeline,
        "explainer": explainer,
        "input_columns": [c for c in frame.columns if c not in _LABEL_COLUMNS],
        "n_samples": int(len(frame)),
        "n_positive": int(n_positive),
        "metrics": {
            "auc_mean": round(float(np.mean(aucs)), 4),
            "auc_std": round(float(np.std(aucs)), 4),
            "prc_max": round(float(np.mean(precs)), 4),
            "recall_max": round(float(np.mean(recs)), 4),
        },
        "feature_importances": {k: round(float(v), 4) for k, v in importances.items()},
        "trained_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    return artifact


def save_artifact(artifact: dict) -> None:
    directory = model_dir(artifact["prediction_type"])
    version_dir = os.path.join(directory, artifact["version"])
    os.makedirs(version_dir, exist_ok=True)
    model_path = os.path.join(version_dir, "model.joblib")
    joblib.dump(artifact["model"], model_path)
    joblib.dump(artifact["explainer"], os.path.join(version_dir, "explainer.joblib"))
    meta = {k: v for k, v in artifact.items() if k not in ("model", "explainer")}
    with open(os.path.join(version_dir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    _write_latest_link(directory, artifact["version"])


def _write_latest_link(directory: str, version: str) -> None:
    with open(os.path.join(directory, "LATEST"), "w", encoding="utf-8") as fh:
        fh.write(version)


def load_artifact(prediction_type: str) -> dict | None:
    directory = model_dir(prediction_type)
    latest_file = os.path.join(directory, "LATEST")
    if not os.path.exists(latest_file):
        return None
    with open(latest_file, encoding="utf-8") as fh:
        version = fh.read().strip()
    version_dir = os.path.join(directory, version)
    if not os.path.isdir(version_dir):
        return None
    try:
        with open(os.path.join(version_dir, "metadata.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    meta["model"] = joblib.load(os.path.join(version_dir, "model.joblib"))
    meta["explainer"] = joblib.load(os.path.join(version_dir, "explainer.joblib"))
    meta["version"] = version
    return meta


def predict_frame(artifact: dict, frame) -> np.ndarray:
    cols = artifact["input_columns"]
    X = frame[cols]
    return artifact["model"].predict_proba(X)[:, 1]


def top_factors(row, importances: dict, top_n: int = 3) -> list[dict]:
    """أبرز العوامل المساهمة لموظف واحد: انحراف عن المتوسط × أهمية الخاصية."""
    numeric = {k: row.get(k, 0) for k in NUMERIC_FEATURES}
    mean = float(np.mean([v for v in numeric.values()])) if numeric else 0.0
    std = float(np.std([v for v in numeric.values()])) or 1.0
    scored = []
    for key, value in numeric.items():
        if isinstance(value, (int, float)):
            z = (value - mean) / std
            scored.append((abs(z) * importances.get(key, 0.0), key, float(value), z))
    scored.sort(reverse=True)
    return [
        {"feature": key, "value": round(value, 2), "zscore": round(z, 2)}
        for _, key, value, z in scored[:top_n]
    ]
