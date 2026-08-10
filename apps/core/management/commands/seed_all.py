"""أمر التهيئة الموحّد (Seed Policy) — بوليصة فرش بيانات كاملة.

الاستخدام:
    python manage.py seed_all                          # RBAC + أنواع إجازات (سنة جارية)
    python manage.py seed_all --year 2027              # + أرصدة سنة محددة
    python manage.py seed_all --no-admin               # بدون إنشاء مشرف افتراضي

يجمع أمرَي التهيئة السابقين (seed_rbac + seed_leave) في أمر واحد
يعمل في بيئة التطوير والإنتاج على حد سواء (راجع docs/15 §10).
"""

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Adm1n@2026!")
DEFAULT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@hrms.local")


class Command(BaseCommand):
    help = "التهيئة الموحّدة: الأدوار/الصلاحيات + أنواع/أرصدة الإجازات + مشرف افتراضي"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=None, help="سنة أرصدة الإجازات")
        parser.add_argument("--no-admin", action="store_true", help="لا تُنشئ مشرفًا افتراضيًا")

    def handle(self, *args, **options):
        year = options["year"] or timezone.localdate().year
        no_admin = options["no_admin"]

        call_command("seed_rbac")
        call_command("seed_leave", year=year)
        call_command("seed_branding")

        if not no_admin:
            self._ensure_admin()
        self.stdout.write(self.style.SUCCESS("اكتملت التهيئة الموحّدة (seed_all)."))

    def _ensure_admin(self):
        User = get_user_model()
        username = DEFAULT_ADMIN_USERNAME
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"المشرف '{username}' موجود مسبقًا — تخطي.")
            return
        User.objects.create_superuser(
            username=username,
            email=DEFAULT_ADMIN_EMAIL,
            password=DEFAULT_ADMIN_PASSWORD,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"مشرف افتراضي: {username} — غيّر كلمة المرور عند أول دخول (هذه بوليصة أمان)."
            )
        )
