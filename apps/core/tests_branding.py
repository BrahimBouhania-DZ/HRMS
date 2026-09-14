"""اختبارات صفحة الشعار والألوان السرية (المبرمج/المدير)."""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.core.models import CompanySettings

from .branding_utils import build_css_block
from .views_branding import MAX_ATTEMPTS

User = get_user_model()

_SECRET = settings.BRANDING_SECRET_PATH


def _u(name):
    return f"/{_SECRET}/{name}".rstrip("/") + "/"


class BrandingAuthTests(TestCase):
    username = os.environ.get("BRANDING_ADMIN_USERNAME", settings.BRANDING_ADMIN_USERNAME)
    password = os.environ.get("BRANDING_ADMIN_PASSWORD", "x") or "x"

    @classmethod
    def setUpTestData(cls):
        u = User.objects.create_user(
            username=cls.username, password=cls.password, is_staff=True
        )
        cls.user = u

    def test_secret_path_serves_login_page(self):
        r = self.client.get(_u(""))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "لوحة التحكم السرية")

    def test_wrong_path_is_404(self):
        r = self.client.get("/wrong-secret-path/")
        self.assertEqual(r.status_code, 404)

    def test_login_wrong_password_fails(self):
        r = self.client.post(_u(""), {"username": self.username, "password": "wrong"})
        self.assertContains(r, "بيانات الدخول غير صحيحة")

    def test_login_wrong_username_fails(self):
        r = self.client.post(_u(""), {"username": "hacker", "password": self.password})
        self.assertContains(r, "بيانات الدخول غير صحيحة")

    def test_login_success_redirects_dashboard(self):
        r = self.client.post(_u(""), {"username": self.username, "password": self.password})
        self.assertRedirects(r, _u("dashboard"))
        self.assertTrue(self.client.session.get("branding_admin"))

    def test_dashboard_requires_branding_account(self):
        other = User.objects.create_user(username="other", password="p", is_staff=True)
        self.client.force_login(other)
        r = self.client.get(_u("dashboard"))
        self.assertEqual(r.status_code, 404)

    def test_dashboard_without_login_redirects(self):
        r = self.client.get(_u("dashboard"))
        self.assertEqual(r.status_code, 302)

    def test_brute_force_lockout(self):
        for _ in range(MAX_ATTEMPTS):
            self.client.post(_u(""), {"username": self.username, "password": "x"})
        r = self.client.post(_u(""), {"username": self.username, "password": self.password},
                             follow=True)
        self.assertContains(r, "حظر الدخول مؤقتًا")

    def test_logout_clears_session(self):
        self.client.post(_u(""), {"username": self.username, "password": self.password})
        self.client.get(_u("logout"))
        self.assertFalse(self.client.session.get("branding_admin"))
        r = self.client.get(_u("dashboard"))
        self.assertEqual(r.status_code, 302)


class BrandingSaveTests(TestCase):
    username = os.environ.get("BRANDING_ADMIN_USERNAME", settings.BRANDING_ADMIN_USERNAME)
    password = os.environ.get("BRANDING_ADMIN_PASSWORD", "x") or "x"

    @classmethod
    def setUpTestData(cls):
        u = User.objects.create_user(
            username=cls.username, password=cls.password, is_staff=True
        )
        cls.user = u

    def setUp(self):
        CompanySettings.objects.get_or_create(company_name_ar="HRMS")
        self.client.post(_u(""), {"username": self.username, "password": self.password})

    def test_custom_colors_saved_and_block_injected(self):
        r = self.client.post(_u("save-colors"), {
            "action": "custom",
            "var_--brand": "#FF0000",
            "var_--surface": "#123456",
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        company = CompanySettings.get_default()
        self.assertEqual(company.css_overrides["--brand"], "#FF0000")
        self.assertEqual(company.css_overrides["--surface"], "#123456")

        home = self.client.get("/")
        self.assertContains(home, "--brand: #FF0000;")
        self.assertContains(home, "--surface: #123456;")

    def test_custom_colors_ignores_invalid(self):
        self.client.post(_u("save-colors"), {"action": "custom", "var_--brand": "notacolor"})
        company = CompanySettings.get_default()
        self.assertNotIn("--brand", company.css_overrides)

    def test_reset_colors(self):
        company = CompanySettings.get_default()
        company.css_overrides = {"--brand": "#FF0000"}
        company.save()
        self.client.post(_u("save-colors"), {"action": "reset"})
        company.refresh_from_db()
        self.assertEqual(company.css_overrides, {})

    def test_preset_applied(self):
        self.client.post(_u("save-colors"), {"action": "preset", "preset": "royal"})
        company = CompanySettings.get_default()
        self.assertEqual(company.css_overrides.get("--brand"), "#4338CA")

    def test_logo_upload(self):
        logo = SimpleUploadedFile("logo.png", b"fake-png-bytes", content_type="image/png")
        r = self.client.post(_u("save-logo"), {"logo": logo}, follow=True)
        self.assertEqual(r.status_code, 200)
        company = CompanySettings.get_default()
        self.assertTrue(company.logo)
        self.assertTrue(company.logo.name.startswith("branding/logo"))
        self.assertTrue(company.logo.name.endswith(".png"))

    def test_logo_delete(self):
        company = CompanySettings.get_default()
        company.logo = SimpleUploadedFile("logo.png", b"fake", content_type="image/png")
        company.save()
        self.client.post(_u("save-logo"), {"action": "delete"}, follow=True)
        company.refresh_from_db()
        self.assertFalse(company.logo)

    def test_identity_saved(self):
        r = self.client.post(_u("save-identity"), {
            "company_name_ar": "شركة الاختبار",
            "tagline": "شعارنا",
            "watermark_opacity": "42",
            "show_logo_watermark": "on",
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        company = CompanySettings.get_default()
        self.assertEqual(company.company_name_ar, "شركة الاختبار")
        self.assertEqual(company.tagline, "شعارنا")
        self.assertEqual(company.watermark_opacity, 42)
        self.assertTrue(company.show_logo_watermark)


class BrandingInjectionTests(TestCase):
    def test_no_overrides_means_empty_block(self):
        CompanySettings.objects.get_or_create(company_name_ar="HRMS")
        self.assertEqual(build_css_block({}), "")

    def test_branding_css_in_context_of_public_page(self):
        """صفحة الدخول العامة (auth/Login) ترث base.html — يجب أن تُحقن BRANDING_CSS."""
        r = self.client.get("/auth/login/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("BRANDING_CSS", r.context)
        self.assertEqual(r.context["BRANDING_CSS"], "")

    def test_branding_css_injected_when_overridden(self):
        company, _ = CompanySettings.objects.get_or_create(company_name_ar="HRMS")
        company.css_overrides = {"--brand": "#A1B2C3"}
        company.save()
        r = self.client.get("/auth/login/")
        self.assertIn("--brand: #A1B2C3;", r.context["BRANDING_CSS"])