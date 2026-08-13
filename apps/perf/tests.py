"""اختبارات تقييم الأداء (T-036..T-040, v2).

يغطي: توليد المراجعات (idempotent)، تسلسل التقييم الذاتي→المدير (BR-PERF-002)،
الدرجة النهائية المرجّحة (BR-PERF-003)، إغلاق الدورة (BR-PERF-004)،
خطط التحسين PIP (BR-PERF-005)، والصلاحيات عبر العروض.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.auth_app.models import Permission, Role, RoleMember
from apps.employees.models import Employee
from apps.perf.models import PerfCycle, PerfObjective, PerfReview, PerfTemplate, PipPlan
from apps.perf.services import (
    PerfError,
    close_cycle,
    close_pip,
    generate_reviews,
    open_pip,
    save_objectives,
    submit_manager_review,
    submit_self_review,
    weighted_final_score,
)

User = get_user_model()


def _employee(code="PF-001", **kw):
    defaults = {
        "employee_code": code,
        "first_name_ar": "أداء",
        "last_name_ar": code,
        "hire_date": datetime.date(2024, 1, 1),
    }
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def _cycle(**kw):
    defaults = {
        "name_ar": "دورة 2026",
        "period_start": datetime.date(2026, 1, 1),
        "period_end": datetime.date(2026, 6, 30),
        "self_review_deadline": datetime.date(2026, 7, 15),
        "manager_review_deadline": datetime.date(2026, 8, 15),
    }
    defaults.update(kw)
    return PerfCycle.objects.create(**defaults)


def _template(**kw):
    defaults = {
        "name_ar": "قالب عام",
        "criteria_json": [{"title": "الدقة", "weight": 50}, {"title": "الالتزام", "weight": 50}],
    }
    defaults.update(kw)
    return PerfTemplate.objects.create(**defaults)


def _permission(code):
    return Permission.objects.get_or_create(code=code, defaults={"module": "perf", "name_ar": code})[0]


def _user_with_role(username, role_code, *permission_codes):
    role = Role.objects.create(code=role_code, name_ar=role_code, is_system=True)
    for code in permission_codes:
        role.permission_links.create(permission=_permission(code))
    user = User.objects.create_user(username=username, password="pass")
    RoleMember.objects.create(user=user, role=role)
    return user


class PerfServiceTests(TestCase):
    def setUp(self):
        self.cycle = _cycle()
        self.template = _template()
        self.emp = _employee()
        self.user = User.objects.create_user(username="mgr", password="pass")

    def test_generate_reviews_creates_pending_self(self):
        n = generate_reviews(self.cycle, self.template, [self.emp])
        self.assertEqual(n, 1)
        review = PerfReview.objects.get()
        self.assertEqual(review.status, PerfReview.Status.PENDING_SELF)
        self.assertEqual(review.template, self.template)

    def test_generate_reviews_is_idempotent(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        n = generate_reviews(self.cycle, self.template, [self.emp])
        self.assertEqual(n, 0)
        self.assertEqual(PerfReview.objects.count(), 1)

    def test_self_review_moves_to_pending_manager(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("80"), "جيد", user=self.user)
        review.refresh_from_db()
        self.assertEqual(review.status, PerfReview.Status.PENDING_MANAGER)
        self.assertEqual(review.self_score, Decimal("80.00"))

    def test_manager_review_blocked_before_self(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        with self.assertRaises(PerfError):
            submit_manager_review(review, Decimal("90"))

    def test_full_flow_with_weighted_objectives(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("80"))
        save_objectives(
            review,
            [
                {"kpi_title": "المبيعات", "weight": 60, "score": 90},
                {"kpi_title": "الالتزام", "weight": 40, "score": 70},
            ],
        )
        submit_manager_review(review, Decimal("75"))
        review.refresh_from_db()
        # النهائي = (90*60 + 70*40)/100 = 82
        self.assertEqual(review.final_score, Decimal("82.00"))
        self.assertEqual(review.status, PerfReview.Status.DONE)

    def test_weighted_final_score_averages_when_no_objectives(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("80"))
        submit_manager_review(review, Decimal("90"))
        review.refresh_from_db()
        self.assertEqual(review.final_score, Decimal("85.00"))

    def test_close_cycle_requires_all_done(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        with self.assertRaises(PerfError):
            close_cycle(self.cycle)
        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, PerfCycle.Status.DRAFT)

    def test_close_cycle_closes_reviews(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("80"))
        submit_manager_review(review, Decimal("90"))
        close_cycle(self.cycle, user=self.user)
        self.cycle.refresh_from_db()
        review.refresh_from_db()
        self.assertEqual(self.cycle.status, PerfCycle.Status.CLOSED)
        self.assertEqual(review.status, PerfReview.Status.CLOSED)

    def test_review_locked_after_cycle_closed(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("80"))
        submit_manager_review(review, Decimal("90"))
        close_cycle(self.cycle)
        review.refresh_from_db()
        with self.assertRaises(PerfError):
            submit_self_review(review, Decimal("10"))

    def test_open_pip_requires_done_review(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        with self.assertRaises(PerfError):
            open_pip(review, datetime.date(2026, 7, 1), datetime.date(2026, 8, 1), "تدريب")
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("50"))
        submit_manager_review(review, Decimal("45"))
        pip = open_pip(review, datetime.date(2026, 7, 1), datetime.date(2026, 8, 1), "تدريب")
        self.assertEqual(pip.status, PipPlan.Status.OPEN)

    def test_open_pip_rejects_inverted_dates(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("50"))
        submit_manager_review(review, Decimal("45"))
        with self.assertRaises(PerfError):
            open_pip(review, datetime.date(2026, 8, 1), datetime.date(2026, 7, 1), "تدريب")

    def test_close_pip_blocked_before_end_date(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("50"))
        submit_manager_review(review, Decimal("45"))
        pip = open_pip(review, datetime.date(2026, 7, 1), datetime.date(2099, 1, 1), "تدريب")
        with self.assertRaises(PerfError):
            close_pip(pip)

    def test_save_objectives_removes_extra(self):
        generate_reviews(self.cycle, self.template, [self.emp])
        review = PerfReview.objects.get()
        save_objectives(review, [{"kpi_title": "أ", "weight": 100}])
        save_objectives(review, [{"kpi_title": "أ", "weight": 100}, {"kpi_title": "ب", "weight": 100}])
        self.assertEqual(review.objectives.count(), 2)
        save_objectives(review, [{"kpi_title": "أ", "weight": 100}])
        self.assertEqual(review.objectives.count(), 1)


class PerfViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hr = _user_with_role("perf_hr", "hr_manager",
                                 "perf.manage", "perf.review", "perf.self", "perf.pip.manage")
        cls.supervisor = _user_with_role("perf_sup", "supervisor",
                                         "perf.review", "perf.self")
        cls.emp_user = User.objects.create_user(username="perf_emp", password="pass")
        emp_role = Role.objects.create(code="employee", name_ar="موظف", is_system=True)
        emp_role.permission_links.create(permission=_permission("perf.self"))
        RoleMember.objects.create(user=cls.emp_user, role=emp_role)
        cls.employee = _employee()
        cls.employee.user = cls.emp_user
        cls.employee.save()
        cls.cycle = _cycle()
        cls.template = _template()

    def test_hr_can_view_cycle_list(self):
        self.client.force_login(self.hr)
        resp = self.client.get(reverse("perf:cycle_list"))
        self.assertEqual(resp.status_code, 200)

    def test_cycle_list_requires_permission(self):
        self.client.force_login(self.emp_user)
        resp = self.client.get(reverse("perf:cycle_list"))
        self.assertEqual(resp.status_code, 403)

    def test_open_cycle_generates_reviews(self):
        self.client.force_login(self.hr)
        resp = self.client.post(reverse("perf:cycle_open", args=[self.cycle.pk]),
                                {"template": self.template.pk})
        self.assertEqual(resp.status_code, 302)
        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, PerfCycle.Status.OPEN)
        self.assertEqual(PerfReview.objects.filter(cycle=self.cycle).count(), 1)

    def test_open_cycle_requires_template(self):
        self.client.force_login(self.hr)
        resp = self.client.post(reverse("perf:cycle_open", args=[self.cycle.pk]), {"template": ""})
        self.assertEqual(resp.status_code, 302)
        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, PerfCycle.Status.DRAFT)

    def test_employee_sees_only_own_reviews(self):
        generate_reviews(self.cycle, self.template, [self.employee])
        self.client.force_login(self.emp_user)
        resp = self.client.get(reverse("perf:my_reviews"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "دورة 2026")

    def test_employee_self_review_submission(self):
        generate_reviews(self.cycle, self.template, [self.employee])
        review = PerfReview.objects.get()
        self.client.force_login(self.emp_user)
        resp = self.client.post(reverse("perf:self_review", args=[review.pk]),
                                {"self_score": "85", "self_comment": "التزام جيد"})
        self.assertEqual(resp.status_code, 302)
        review.refresh_from_db()
        self.assertEqual(review.status, PerfReview.Status.PENDING_MANAGER)

    def test_manager_submits_review_and_objectives(self):
        generate_reviews(self.cycle, self.template, [self.employee])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("80"))
        self.client.force_login(self.hr)
        resp = self.client.post(
            reverse("perf:review_submit", args=[review.pk]),
            {
                "manager_score": "76",
                "manager_comment": "جيد",
                "objectives-TOTAL_FORMS": "1",
                "objectives-INITIAL_FORMS": "0",
                "objectives-MIN_NUM_FORMS": "0",
                "objectives-MAX_NUM_FORMS": "1000",
                "objectives-0-kpi_title": "الالتزام",
                "objectives-0-weight": "100",
                "objectives-0-score": "76",
            },
        )
        self.assertEqual(resp.status_code, 302)
        review.refresh_from_db()
        self.assertEqual(review.status, PerfReview.Status.DONE)
        self.assertEqual(review.final_score, Decimal("76.00"))

    def test_pip_created_from_view(self):
        generate_reviews(self.cycle, self.template, [self.employee])
        review = PerfReview.objects.get()
        submit_self_review(review, Decimal("50"))
        submit_manager_review(review, Decimal("45"))
        self.client.force_login(self.hr)
        resp = self.client.post(
            reverse("perf:pip_create", args=[review.pk]),
            {
                "start_date": "2026-07-01",
                "end_date": "2026-08-01",
                "action_items": "تدريب مكثف",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PipPlan.objects.filter(review=review).count(), 1)

    def test_template_form_validates_weights(self):
        self.client.force_login(self.hr)
        resp = self.client.post(
            reverse("perf:template_create"),
            {"name_ar": "ق", "criteria": '[{"title": "أ", "weight": 40}]'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "100")
        resp = self.client.post(
            reverse("perf:template_create"),
            {"name_ar": "ق", "criteria": '[{"title": "أ", "weight": 40}, {"title": "ب", "weight": 60}]'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(PerfTemplate.objects.filter(name_ar="ق").exists())
