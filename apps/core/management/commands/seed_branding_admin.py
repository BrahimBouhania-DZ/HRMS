"""إنشاء/تحديث حساب المبرمج/المدير لصفحة الشعار والألوان السرية.

الاستخدام:
    python manage.py seed_branding_admin

يقرأ من: BRANDING_ADMIN_USERNAME، BRANDING_ADMIN_PASSWORD، BRANDING_ADMIN_EMAIL
(مفاتيح .env عبر config.settings.base).
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "إنشاء حساب المبرمج/المدير لصفحة الشعار السرية (is_staff فقط)"

    def handle(self, *args, **options):
        username = settings.BRANDING_ADMIN_USERNAME
        # كلمة المرور تُقرأ من متغير البيئة مباشرة (لا تمر عبر settings حفاظًا عليها)
        password = os.environ.get("BRANDING_ADMIN_PASSWORD")
        email = getattr(settings, "BRANDING_ADMIN_EMAIL", "branding@hrms.local")

        if not password:
            raise CommandError(
                "BRANDING_ADMIN_PASSWORD غير مضبوط في .env — "
                "أضفه إلى ملف .env ثم أعد التشغيل."
            )

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": "Branding",
                "last_name": "Admin",
                "is_staff": True,
                "is_superuser": False,
                "is_active": True,
            },
        )
        if not created:
            changed = False
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if changed:
                user.save()
                self.stdout.write(self.style.WARNING(f"✅ تم تحديث حساب «{username}» (is_staff={user.is_staff})"))
            else:
                self.stdout.write(self.style.NOTICE(f"ℹ️  الحساب «{username}» موجود مسبقًا且معطياته صحيحة."))

        # تعيين كلمة المرور دائمًا (تشفير bcrypt)
        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ تم {'إنشاء' if created else 'تحديث'} حساب المبرمج/المدير:\n"
            f"   اسم المستخدم : {username}\n"
            f"   البريد       : {email}\n"
            f"   is_staff     : {user.is_staff}\n"
            f"   is_superuser : {user.is_superuser}\n"
            f"\n   🔗 افتح المسار السري في المتصفح مباشرةً.\n"
        ))
