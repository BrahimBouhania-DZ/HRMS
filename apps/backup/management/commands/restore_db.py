"""أمر استعادة النسخة الاحتياطية — للاختبار الشهري الإلزامي أو الطوارئ.

الاستعمال:
    python manage.py restore_db backups/hrms_*.enc            # استعادة فعلية
    python manage.py restore_db backups/hrms_*.enc --dry-run  # اختبار (فك تشفير + تحقق فقط)
"""

from django.core.management.base import BaseCommand, CommandError

from apps.backup.services import restore_backup


class Command(BaseCommand):
    help = "يستعيد قاعدة البيانات من نسخة مشفرة (مع التحقق من checksum)."

    def add_arguments(self, parser):
        parser.add_argument("file", help="مسار ملف النسخة المشفرة (.enc)")
        parser.add_argument("--dry-run", action="store_true", help="اختبار استعادة: فك تشفير وتحقق دون تعديل")

    def handle(self, *args, **options):
        try:
            job = restore_backup(options["file"], dry_run=options["dry_run"])
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc
        verb = "اختبار استعادة (تحقق فقط)" if options["dry_run"] else "استعادة"
        self.stdout.write(self.style.SUCCESS(f"{verb} ناجح — {job.source_file}"))
