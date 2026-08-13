"""اختبارات النسخ الاحتياطي والاستعادة — التشفير، التشغيل، الاحتفاظ، الاستعادة، الواجهة."""

import os
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.auth_app.models import Role, RoleMember

from .crypto import constant_time_eq, decrypt_file, encrypt_file, sha256_hex
from .models import BackupJob, BackupSettings, RestoreJob
from .services import BackupError, run_backup, restore_backup

User = get_user_model()


class CryptoTests(TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "plain.bin")
            enc = os.path.join(tmp, "enc.hrms")
            dec = os.path.join(tmp, "dec.bin")
            data = b"\x00\x01\x02 secret \xe2\x82\xac data" * 1000
            with open(src, "wb") as f:
                f.write(data)
            encrypt_file(src, enc)
            self.assertNotEqual(open(enc, "rb").read(), data)
            decrypt_file(enc, dec)
            self.assertEqual(open(dec, "rb").read(), data)

    def test_decrypt_tampered_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "plain.bin")
            enc = os.path.join(tmp, "enc.hrms")
            with open(src, "wb") as f:
                f.write(b"hello")
            encrypt_file(src, enc)
            with open(enc, "r+b") as f:
                f.seek(-5, 2)
                f.write(b"XXXXX")
            with self.assertRaises(Exception):
                decrypt_file(enc, os.path.join(tmp, "out.bin"))

    def test_decrypt_non_hrms_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            junk = os.path.join(tmp, "junk.hrms")
            with open(junk, "wb") as f:
                f.write(b"NOT A BACKUP FILE CONTENT" * 10)
            with self.assertRaises(ValueError):
                decrypt_file(junk, os.path.join(tmp, "out.bin"))

    def test_checksum_and_constant_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "f.bin")
            with open(p, "wb") as f:
                f.write(b"data")
            self.assertEqual(len(sha256_hex(p)), 64)
            self.assertTrue(constant_time_eq(sha256_hex(p), sha256_hex(p)))
            self.assertFalse(constant_time_eq("a" * 64, "b" * 64))

class BackupServiceTests(TransactionTestCase):
    """TransactionTestCase: لأن sqlite3.backup() يتطلب التحرر من معاملة الاختبار."""

    def setUp(self):
        self.admin = User.objects.create_superuser(username="bk_admin", password="pass")

    def test_run_backup_creates_encrypted_file_and_job(self):
        job = run_backup(kind=BackupJob.Kind.MANUAL, user=self.admin)
        self.assertEqual(job.status, BackupJob.Status.SUCCESS)
        self.assertTrue(job.encrypted)
        self.assertTrue(os.path.exists(job.file_path))
        self.assertEqual(len(job.checksum), 64)
        self.assertGreater(job.file_size, 0)
        # الحجم الحقيقي يجب أن يطابق الملف
        self.assertEqual(job.file_size, os.path.getsize(job.file_path))

    def test_restore_dry_run_verifies_checksum(self):
        job = run_backup(kind=BackupJob.Kind.DAILY, user=self.admin)
        rjob = restore_backup(job.file_path, dry_run=True)
        self.assertEqual(rjob.status, RestoreJob.Status.SUCCESS)
        self.assertTrue(rjob.checksum_verified)

    def test_restore_missing_file_raises(self):
        with self.assertRaises(BackupError):
            restore_backup("/nonexistent/backup.enc", dry_run=True)

    def test_retention_keeps_last_n(self):
        cfg = BackupSettings.get_default()
        cfg.retention_count = 2
        cfg.save()
        for _ in range(4):
            run_backup(kind=BackupJob.Kind.MANUAL)
        import glob

        from .services import _backup_dir

        files = glob.glob(str(_backup_dir() / "hrms_*.enc"))
        self.assertEqual(len(files), 2)

    def test_backup_not_encrypted_when_disabled(self):
        cfg = BackupSettings.get_default()
        cfg.encrypt = False
        cfg.save()
        job = run_backup(kind=BackupJob.Kind.WEEKLY)
        self.assertFalse(job.encrypted)


class BackupViewTests(TransactionTestCase):
    """TransactionTestCase: إنشاء نسخة عبر الواجهة يتطلب التحرر من معاملة الاختبار."""

    def setUp(self):
        from apps.auth_app.models import Permission

        Permission.objects.get_or_create(
            code="system.backup.manage", defaults={"module": "core", "name_ar": "النسخ الاحتياطي"}
        )
        self.admin = User.objects.create_superuser(username="bk_view_admin", password="pass")
        self.client.force_login(self.admin)

    def test_page_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("backup:page"))
        self.assertEqual(resp.status_code, 302)

    def test_page_renders(self):
        resp = self.client.get(reverse("backup:page"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "النسخ الاحتياطي")

    def test_create_backup_from_page(self):
        resp = self.client.post(reverse("backup:page"), {"action": "backup"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(BackupJob.objects.filter(status=BackupJob.Status.SUCCESS).exists())

    def test_download_requires_permission(self):
        job = run_backup(kind=BackupJob.Kind.MANUAL, user=self.admin)
        name = os.path.basename(job.file_path)
        resp = self.client.get(reverse("backup:download"), {"name": name})
        self.assertEqual(resp.status_code, 200)

    def test_download_path_traversal_blocked(self):
        resp = self.client.get(reverse("backup:download"), {"name": "../../etc/passwd"})
        self.assertEqual(resp.status_code, 404)

    def test_plain_user_forbidden(self):
        plain = User.objects.create_user(username="bk_plain", password="pass")
        self.client.force_login(plain)
        self.assertEqual(self.client.get(reverse("backup:page")).status_code, 403)
