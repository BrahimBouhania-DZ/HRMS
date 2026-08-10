"""أمر تهيئة هوية الشركة — سجل وحيد + شعار افتراضي قابل للتعديل.

الاستخدام:
    python manage.py seed_branding                 # إنشاء السجل والشعار إن لم يوجد
    python manage.py seed_branding --force         # إعادة إنشاء الشعار الافتراضي

يُنشئ CompanySettings واحدًا مع شعار مبدئي (مونوغرام) مولّد بواسطة Pillow،
ويمكن استبداله لاحقًا من لوحة الإدارة → «هوية الشركة».
"""

import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from apps.core.models import CompanySettings


class Command(BaseCommand):
    help = "تهيئة هوية الشركة (الاسم + الشعار الافتراضي) — T-020"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="إعادة إنشاء الشعار الافتراضي")

    def handle(self, *args, **options):
        force = options["force"]
        obj, created = CompanySettings.objects.get_or_create(
            id=1,
            defaults={
                "company_name_ar": "HRMS",
                "company_name_fr": "HRMS",
                "company_name_en": "HRMS",
                "tagline": "نظام إدارة الموارد البشرية",
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("سجل هوية الشركة أُنشئ."))

        if not obj.logo or force:
            obj.logo.save("logo-default.png", self._render_logo(), save=True)
            self.stdout.write(self.style.SUCCESS("الشعار الافتراضي أُنشئ (media/branding/logo-default.png)."))
        else:
            self.stdout.write("الشعار موجود مسبقًا — تخطي (استخدم --force لإعادة إنشائه).")

    def _render_logo(self):
        """شعار مبدئي 512×512: خلفية متدرجة (كحلي→سماوي→ذهبي) + مونوغرام 'HR'."""
        size = 512
        img = Image.new("RGB", (size, size), "#0E354C")
        draw = ImageDraw.Draw(img)

        # تدرج رأسي ثلاثي الألوان
        stops = [
            (0, 14, 53, 76),    # كحلي
            (100, 46, 150, 200),  # سماوي
            (220, 212, 175, 55),  # ذهبي
        ]
        for y in range(size):
            ratio = y / size * 220
            if ratio <= 100:
                t = ratio / 100
                c1, c2 = stops[0], stops[1]
            else:
                t = (ratio - 100) / 120
                c1, c2 = stops[1], stops[2]
            r = int(c1[1] + (c2[1] - c1[1]) * t)
            g = int(c1[2] + (c2[2] - c1[2]) * t)
            b = int(c1[3] + (c2[3] - c1[3]) * t)
            draw.line([(0, y), (size, y)], fill=(r, g, b))

        # إطار داخلي مضيء
        draw.rounded_rectangle([14, 14, size - 14, size - 14], radius=56, outline=(255, 255, 255), width=6)

        # مونوغرام
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 190)
        except OSError:
            font = ImageFont.load_default(size=190)
        text = "HR"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - 40), text, font=font, fill=(255, 255, 255))

        # سطر شعار نصي أسفل المونوغرام
        try:
            small = ImageFont.truetype("DejaVuSans.ttf", 40)
        except OSError:
            small = ImageFont.load_default(size=40)
        tag = "HRMS"
        tb = draw.textbbox((0, 0), tag, font=small)
        draw.text(((size - (tb[2] - tb[0])) / 2 - tb[0], size - 110), tag, font=small, fill=(255, 244, 214))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return ContentFile(buf.getvalue())
