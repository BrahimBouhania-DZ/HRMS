"""اختبارات الذكاء الاصطناعي — خط التدريب + حفظ/تحميل + تنبؤات + عروض.

يغطي: قوة خط التدريب على عيّنة تركيبية، دورة الحفظ/التحميل، إنشاء تنبوهات
الموظفين النشطين، والصلاحيات على صفحة اللوحة.
"""

import datetime
import tempfile

import numpy as np
import pandas as pd
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.ai import ml
from apps.ai.features import CATEGORICAL_FEATURES, LABEL_COLUMN, NUMERIC_FEATURES, feature_frame
from apps.ai.models import AIPrediction
from apps.ai import services
from apps.auth_app.models import Permission, Role, RoleMember
from apps.employees.models import Employee

User = get_user_model()


def _synthetic_frame(n=40, positive=0.3):
    """عيّنة تركيبية بإشارة واضحة: معدل الحضور يتنبأ بالرحيل."""
    rng = np.random.RandomState(7)
    n_pos = int(n * positive)
    y = np.array([1] * n_pos + [0] * (n - n_pos))
    rng.shuffle(y)
    attendance = np.where(y == 1, rng.uniform(0.55, 0.78, n), rng.uniform(0.88, 0.99, n))
    depts = np.array(["مالية"] * n)
    grades = np.array(["B1"] * n)
    data = {
        "attendance_rate": attendance,
        "absent_days": np.where(y == 1, rng.randint(8, 40, n), rng.randint(0, 6, n)),
        "avg_late_minutes": np.where(y == 1, rng.uniform(10, 40, n), rng.uniform(0, 4, n)),
        "late_ratio": np.full(n, 0.1),
        "overtime_minutes": np.zeros(n),
        "sick_leave_days": np.where(y == 1, rng.randint(3, 12, n), 0),
        "leave_days_total": np.full(n, 10),
        "perf_score_latest": np.where(y == 1, rng.uniform(45, 65, n), rng.uniform(75, 95, n)),
        "perf_trend": np.zeros(n),
        "perf_count": np.ones(n),
        "tenure_days": np.full(n, 1000),
        "salary_growth_12m": np.where(y == 1, 0.0, 0.05),
        "num_contracts": np.ones(n),
        "gross_salary": np.where(y == 1, rng.uniform(30000, 50000, n), rng.uniform(50000, 90000, n)),
        "department": depts,
        "position_grade": grades,
        LABEL_COLUMN: y,
    }
    return pd.DataFrame(data)


def _permission(code):
    return Permission.objects.get_or_create(code=code, defaults={"module": "ai", "name_ar": code})[0]


def _user_with_role(username, *codes):
    role = Role.objects.create(code=f"role-{username}", name_ar=username, is_system=True)
    for code in codes:
        role.permission_links.create(permission=_permission(code))
    user = User.objects.create_user(username=username, password="pass")
    RoleMember.objects.create(user=user, role=role)
    return user


def _employee(code, **kw):
    defaults = {
        "employee_code": code,
        "first_name_ar": "ذكاء",
        "last_name_ar": code,
        "hire_date": datetime.date(2022, 1, 1),
    }
    defaults.update(kw)
    return Employee.objects.create(**defaults)


class MlPipelineTests(TestCase):
    def test_train_model_reports_metrics_and_versions(self):
        frame = _synthetic_frame()
        artifact = ml.train_model("resignation", frame)
        self.assertEqual(artifact["n_samples"], len(frame))
        self.assertEqual(artifact["n_positive"], 12)
        self.assertGreaterEqual(artifact["metrics"]["auc_mean"], 0.7)
        self.assertTrue(artifact["version"].startswith("v"))
        self.assertIn("attendance_rate", artifact["feature_importances"])

    def test_train_raises_when_positive_samples_insufficient(self):
        frame = _synthetic_frame(n=20, positive=0.1)
        with self.assertRaises(ValueError):
            ml.train_model("resignation", frame)

    def test_predict_proba_within_range(self):
        frame = _synthetic_frame()
        artifact = ml.train_model("resignation", frame)
        probs = ml.predict_frame(artifact, frame)
        self.assertTrue(((probs >= 0) & (probs <= 1)).all())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="ai-test-media-"))
class SaveLoadRefreshTests(TestCase):
    def setUp(self):
        self.artifact = ml.train_model("resignation", _synthetic_frame())
        ml.save_artifact(self.artifact)
        self.emp = _employee("AI-001", is_active=True)
        self.departed = _employee("AI-002", is_active=False, employment_status="resigned")

    def test_save_load_roundtrip(self):
        loaded = ml.load_artifact("resignation")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["version"], self.artifact["version"])
        self.assertIn("model", loaded)

    def test_refresh_creates_predictions_for_active_only(self):
        count = services.refresh_predictions("resignation")
        self.assertEqual(count, 1)
        pred = AIPrediction.objects.get()
        self.assertEqual(pred.employee, self.emp)
        self.assertIn(pred.level, ("low", "medium", "high"))
        self.assertTrue(0 <= float(pred.probability) <= 1)

    def test_predict_employee_returns_result(self):
        services.refresh_predictions("resignation")
        result = services.predict_employee(self.emp)
        self.assertIsNotNone(result)
        self.assertIn("probability", result)
        self.assertTrue(result["factors"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="ai-test-view-media-"))
class PredictionViewTests(TestCase):
    def test_page_requires_permission(self):
        user = _user_with_role("plain")
        self.client.force_login(user)
        response = self.client.get(reverse("ai:predictions"))
        self.assertEqual(response.status_code, 403)

    def test_page_renders_untrained_message(self):
        user = _user_with_role("analyst", "ai.analytics.view")
        self.client.force_login(user)
        response = self.client.get(reverse("ai:predictions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "seed_ai_data")

    def test_page_renders_predictions(self):
        emp = _employee("AI-003", is_active=True)
        AIPrediction.objects.create(
            employee=emp, prediction_type=AIPrediction.Type.RESIGNATION,
            probability=0.85, level="high",
            features_json={"attendance_rate": 0.8}, model_version="v1",
        )
        user = _user_with_role("analyst2", "ai.analytics.view")
        self.client.force_login(user)
        response = self.client.get(reverse("ai:predictions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI-003")


class FeatureExtractionTests(TestCase):
    def test_feature_frame_columns(self):
        emp = _employee("AI-004", is_active=True)
        frame = feature_frame([emp])
        expected = set(NUMERIC_FEATURES + CATEGORICAL_FEATURES + [LABEL_COLUMN])
        self.assertTrue(expected.issubset(set(frame.columns)))
        self.assertEqual(int(frame.loc[emp.id, LABEL_COLUMN]), 0)
