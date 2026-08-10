"""أمر تجهيز النشر (راجع docs/14-deployment.md §4).

الاستخدام:
    python manage.py deploy_prepare   # بيئة prod إلزامية (config.settings.prod)

ينفّذ التحقق الكامل قبل التشغيل على خادم LAN:
    check  →  makemigrations --check  →  migrate  →  collectstatic

يفشل (exit 1) عند أي انحراف (نماذج بلا هجرات، إعدادات خاطئة، ...).
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "تجهيز النشر: check + تحقق الهجرات + migrate + collectstatic (بيئة prod)"

    def handle(self, *args, **options):
        module = settings.SETTINGS_MODULE
        if not module.endswith("prod"):
            self.stderr.write(self.style.ERROR(
                f"deploy_prepare يتطلب config.settings.prod — الجاري: {module}"
            ))
            raise SystemExit(1)

        self.stdout.write("1/4 فحص النظام (check) ...")
        call_command("check", deploy=True)

        self.stdout.write("2/4 تحقق عدم وجود هجرات معلقة (makemigrations --check) ...")
        call_command("makemigrations", check=True, dry_run=True)

        self.stdout.write("3/4 تطبيق الهجرات (migrate) ...")
        call_command("migrate")

        self.stdout.write("4/4 جمع الملفات الثابتة (collectstatic) ...")
        call_command("collectstatic", interactive=False, verbosity=1)

        self.stdout.write(self.style.SUCCESS(
            "جاهز للنشر — تأكد من ملف .env (DJANGO_ALLOWED_HOSTS, DJANGO_DB_*, DJANGO_SECRET_KEY)."
        ))
