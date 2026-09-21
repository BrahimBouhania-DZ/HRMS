"""اختبارات الذكاء الاصطناعي — خط التدريب + حفظ/تحميل + تنبؤات + عروض.

يغطي: قوة خط التدريب على عيّنة تركيبية، دورة الحفظ/التحميل، إنشاء تنبوهات
الموظفين النشطين، والصلاحيات على صفحة اللوحة.
"""

import datetime
import tempfile
from unittest import mock

import numpy as np
import pandas as pd
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.ai import ml
from apps.ai.features import CATEGORICAL_FEATURES, LABEL_COLUMN, NUMERIC_FEATURES, feature_frame
from apps.ai.models import AIPrediction, AIQuery
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

    def test_absence_label_trains_distinct_model_no_leakage(self):
        frame = _synthetic_frame()
        frame["label_absence"] = np.where(frame["absent_days"] >= 10, 1, 0)
        artifact = ml.train_model("absence_risk", frame, label_column="label_absence")
        self.assertNotIn("label", artifact["input_columns"])
        self.assertNotIn("label_absence", artifact["input_columns"])
        self.assertEqual(artifact["n_positive"], int(frame["label_absence"].sum()))
        self.assertGreaterEqual(artifact["metrics"]["auc_mean"], 0.6)


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


class PredictionViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._patcher = mock.patch("apps.ai.ml.model_dir", return_value=tempfile.mkdtemp(prefix="ai-test-view-"))
        cls._patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()
        super().tearDownClass()
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
        self.assertIn("label_absence", frame.columns)
        self.assertEqual(int(frame.loc[emp.id, "label_absence"]), 0)


class NlpIntentTests(TestCase):
    """دقة فهم الهدف ≥ 90% لكل لغة."""

    CASES = {
        "ar": [
            ("كم موظفًا في الشركة؟", "headcount"),
            ("عدد الموظفين النشطين؟", "headcount"),
            ("كم موظفًا غائبًا اليوم؟", "absent_today"),
            ("كم عدد الحاضرين اليوم؟", "present_today"),
            ("ما هي الأقسام الأعلى تأخرًا هذا الشهر؟", "late_top"),
            ("كم طلب إجازة معلق؟", "leave_pending"),
            ("كم يوم إجازة معتمد هذا العام؟", "leave_days"),
            ("ما هي كتلة الأجور لهذا الشهر؟", "payroll_month"),
            ("ما هو متوسط الراتب؟", "avg_salary"),
            ("ما هو متوسط التقييم؟", "perf_avg"),
            ("أفضل 5 موظفين أداءً؟", "perf_top"),
            ("من هم الموظفون الأكثر عرضة للاستقالة؟", "turnover_risk"),
            ("معلومات عن الموظف 1001؟", "employee_info"),
            ("ماذا يمكنك أن تفعل؟", "help"),
        ],
        "fr": [
            ("Combien d'employés dans l'entreprise ?", "headcount"),
            ("Combien d'absents aujourd'hui ?", "absent_today"),
            ("Combien de présents aujourd'hui ?", "present_today"),
            ("Quels services sont en retard ce mois-ci ?", "late_top"),
            ("Combien de congés en attente ?", "leave_pending"),
            ("Combien de jours de congé approuvés cette année ?", "leave_days"),
            ("Quelle est la masse salariale de ce mois ?", "payroll_month"),
            ("Quel est le salaire moyen ?", "avg_salary"),
            ("Quel est le score moyen d'évaluation ?", "perf_avg"),
            ("Les 5 meilleurs employés ?", "perf_top"),
            ("Quels employés sont à risque de départ ?", "turnover_risk"),
            ("Que peux-tu faire ?", "help"),
        ],
        "en": [
            ("How many employees in the company?", "headcount"),
            ("How many employees are active?", "headcount"),
            ("How many employees are absent today?", "absent_today"),
            ("How many present today?", "present_today"),
            ("Which departments are most late this month?", "late_top"),
            ("How many pending leave requests?", "leave_pending"),
            ("How many approved leave days this year?", "leave_days"),
            ("What is this month's payroll total?", "payroll_month"),
            ("What is the average salary?", "avg_salary"),
            ("What is the average review score?", "perf_avg"),
            ("Who are the top 5 performers?", "perf_top"),
            ("Which employees are at turnover risk?", "turnover_risk"),
            ("What can you do?", "help"),
        ],
    }

    def test_intent_accuracy_per_language(self):
        from apps.ai import nlp

        for lang, cases in self.CASES.items():
            correct = sum(
                1 for q, expected in cases
                if nlp.detect_intent(nlp.normalize(q), lang)[0] == expected
            )
            accuracy = correct / len(cases)
            self.assertGreaterEqual(
                accuracy, 0.90,
                f"{lang}: {correct}/{len(cases)} = {accuracy:.0%}",
            )

    def test_entity_extraction_code_and_limit(self):
        from apps.ai import nlp

        norm = nlp.normalize("أفضل 5 موظفين أداءً")
        entities = nlp.extract_entities(norm, "ar")
        self.assertEqual(entities["limit"], 5)
        norm = nlp.normalize("معلومات عن الموظف EMP-1234")
        entities = nlp.extract_entities(norm, "ar")
        self.assertEqual(entities["employee_code"], "1234")

    def test_language_detection(self):
        from apps.ai import nlp

        self.assertEqual(nlp.detect_language("كم موظفًا غائبًا اليوم؟"), "ar")
        self.assertEqual(nlp.detect_language("Combien d'absents aujourd'hui ?"), "fr")
        self.assertEqual(nlp.detect_language("How many absent today?"), "en")


class AssistantServiceTests(TestCase):
    """خدمة المساعد: قراءة فقط + نطاق + تدقيق."""

    def test_answer_is_audited_readonly(self):
        from apps.ai import assistant
        from apps.ai.models import AIQuery

        user = _user_with_role("boss", "ai.assistant.use")
        _employee("EMP-1001", is_active=True)
        before_emp = Employee.objects.count()
        answer = assistant.answer_question(user, "كم موظفًا في الشركة؟")
        self.assertEqual(answer["intent"], "headcount")
        self.assertEqual(Employee.objects.count(), before_emp)
        self.assertTrue(AIQuery.objects.filter(user=user, prompt="كم موظفًا في الشركة؟").exists())

    def test_answer_respects_scope(self):
        from apps.ai import assistant

        user = _user_with_role("noscope")
        answer = assistant.answer_question(user, "كم موظفًا في الشركة؟")
        self.assertEqual(answer["intent"], "headcount")
        self.assertNotIn("125", answer["text"])

    def test_sql_injection_attempts_are_safe(self):
        from apps.ai import assistant

        user = _user_with_role("boss", "ai.assistant.use")
        payloads = [
            "SELECT * FROM employees; DROP TABLE employees",
            "'; DELETE FROM employees; --",
            "كم موظفًا؟ UNION SELECT password FROM auth_user",
        ]
        for payload in payloads:
            answer = assistant.answer_question(user, payload)
            self.assertIn(answer["intent"], ("unknown", "headcount"))
            self.assertNotIn("password", answer["text"].lower())

    def test_department_filter_in_headcount(self):
        from apps.ai import assistant
        from apps.org.models import Branch, Department

        branch = Branch.objects.create(code="BR-X", name_ar="فرع الاختبار")
        dept = Department.objects.create(code="DP-X", name_ar="المشتريات", branch=branch)
        _employee("EMP-9001", department=dept, is_active=True)
        user = _user_with_role("hr9", "ai.assistant.use")
        role = user.role_memberships.first().role
        role.code = "hr_manager"
        role.save()
        answer = assistant.answer_question(user, "كم موظفًا في قسم المشتريات؟")
        self.assertEqual(answer["intent"], "headcount")
        self.assertIn("1", answer["text"])

    def test_employee_info_by_code(self):
        from apps.ai import assistant

        _employee("EMP-1001", is_active=True)
        user = _user_with_role("hr8", "ai.assistant.use")
        role = user.role_memberships.first().role
        role.code = "hr_manager"
        role.save()
        answer = assistant.answer_question(user, "معلومات عن الموظف EMP-1001؟")
        self.assertEqual(answer["intent"], "employee_info")
        self.assertIn("EMP-1001", answer["text"])


class AssistantViewTests(TestCase):
    """صفحة المساعد تتطلب صلاحية ai.assistant.use."""

    def test_page_requires_permission(self):
        user = _user_with_role("nosmurf")
        self.client.force_login(user)
        response = self.client.get(reverse("ai:assistant"))
        self.assertEqual(response.status_code, 403)

    def test_page_renders_for_authorized(self):
        user = _user_with_role("boss2", "ai.assistant.use")
        self.client.force_login(user)
        response = self.client.get(reverse("ai:assistant"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "المساعد الذكي")

    def test_page_answers_question(self):
        user = _user_with_role("boss3", "ai.assistant.use")
        self.client.force_login(user)
        response = self.client.get(reverse("ai:assistant"), {"q": "كم موظفًا في الشركة؟"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "headcount")

    def test_page_exposes_query_id_for_feedback(self):
        user = _user_with_role("boss4", "ai.assistant.use")
        self.client.force_login(user)
        response = self.client.get(reverse("ai:assistant"), {"q": "كم موظفًا في الشركة؟"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-feedback")
        self.assertContains(response, reverse("ai:feedback"))


class FeedbackTests(TestCase):
    """حلقة تعلم المساعد: تقييم المستخدم لسؤاله الخاص فقط."""

    def _ask_and_feedback(self, value):
        user = _user_with_role("fb1", "ai.assistant.use")
        self.client.force_login(user)
        assistant = __import__("apps.ai.assistant", fromlist=["answer_question"])
        assistant.answer_question(user, "كم موظفًا في الشركة؟")
        query = AIQuery.objects.get(user=user)
        response = self.client.post(
            reverse("ai:feedback"),
            {"query_id": query.id, "value": value},
        )
        self.assertEqual(response.status_code, 200)
        query.refresh_from_db()
        return query

    def test_requires_permission(self):
        user = _user_with_role("fb2")
        self.client.force_login(user)
        response = self.client.post(reverse("ai:feedback"), {"query_id": 1, "value": "1"})
        self.assertEqual(response.status_code, 403)

    def test_marks_helpful(self):
        query = self._ask_and_feedback("1")
        self.assertIs(query.was_helpful, True)

    def test_marks_not_helpful(self):
        query = self._ask_and_feedback("0")
        self.assertIs(query.was_helpful, False)

    def test_cannot_evaluate_others_query(self):
        owner = _user_with_role("fb3", "ai.assistant.use")
        intruder = _user_with_role("fb4", "ai.assistant.use")
        AIQuery.objects.create(user=owner, prompt="سر", answer_json={})
        query = AIQuery.objects.get(user=owner)
        self.client.force_login(intruder)
        response = self.client.post(reverse("ai:feedback"), {"query_id": query.id, "value": "1"})
        self.assertEqual(response.status_code, 404)
        query.refresh_from_db()
        self.assertIsNone(query.was_helpful)

    def test_unknown_queries_listed_only_for_analytics_permission(self):
        from apps.ai import services

        user = _user_with_role("fb5", "ai.assistant.use")
        self.client.force_login(user)
        assistant = __import__("apps.ai.assistant", fromlist=["answer_question"])
        assistant.answer_question(user, "ما لون السماء؟")
        unknown = list(services.unknown_queries())
        self.assertTrue(unknown)
        self.assertNotEqual(unknown[0].answer_json["intent"], "headcount")
        self.assertIn("ما لون السماء", unknown[0].prompt)

        response = self.client.get(reverse("ai:assistant"))
        self.assertContains(response, "ما لون السماء")

        other = _user_with_role("fb6", "ai.assistant.use")
        self.client.force_login(other)
        response = self.client.get(reverse("ai:assistant"))
        self.assertNotContains(response, "ما لون السماء")

        admin = _user_with_role("fb7", "ai.analytics.view")
        self.client.force_login(admin)
        response = self.client.get(reverse("ai:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ما لون السماء")


class DataQualityTests(TestCase):
    """فحص جودة البيانات قبل التدريب (3.3)."""

    def test_report_ok_on_clean_frame(self):
        from apps.ai.features import data_quality_report

        frame = _synthetic_frame(n=20, positive=0.4)
        report = data_quality_report(frame)
        self.assertTrue(report["ok"])
        self.assertEqual(report["metrics"]["rows"], 20)
        self.assertIn("n_positive", report["metrics"])

    def test_report_flags_missing_and_no_positive(self):
        from apps.ai.features import data_quality_report

        frame = _synthetic_frame(n=20, positive=0.4)
        frame.iloc[0, frame.columns.get_loc("attendance_rate")] = np.nan
        frame[LABEL_COLUMN] = 0
        report = data_quality_report(frame)
        self.assertFalse(report["ok"])
        self.assertGreaterEqual(report["metrics"]["missing_cells"], 1)
        self.assertEqual(report["metrics"]["n_positive"], 0)

    def test_report_empty_frame_rejected(self):
        from apps.ai.features import data_quality_report

        report = data_quality_report(None)
        self.assertFalse(report["ok"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="ai-test-media-"))
class ScheduledRetrainTests(TestCase):
    """إعادة التدريب المجدولة + مراقبة AUC drift (3.4)."""

    def test_quiet_skip_without_departed(self):
        _employee("R-001", is_active=True)
        result = services.scheduled_retrain(days_window=90)
        self.assertFalse(result["retrained"])
        self.assertEqual(result["reason"], "no_departed_in_window")

    def test_retrain_logs_value_error_not_crash(self):
        _employee("R-002", is_active=False, hire_date=datetime.date(2019, 1, 1))
        result = services.scheduled_retrain(days_window=3650)
        self.assertTrue(result["retrained"])
        self.assertIn("error", result["results"][AIPrediction.Type.RESIGNATION])

    def test_no_drift_warning_without_previous_model(self):
        _employee("R-003", is_active=False, hire_date=datetime.date(2019, 1, 1))
        with self.assertRaises(ValueError):
            services.retrain_model(AIPrediction.Type.RESIGNATION, employees=[])
