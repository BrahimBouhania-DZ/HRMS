"""خدمة النسخ الاحتياطي والاستعادة — لقطة متسقة + تشفير + احتفاظ.

المرجع: docs/09-security.md §7.
- SQLite: نسخة متسقة عبر وحدة sqlite3.backup().
- PostgreSQL: pg_dump عبر subprocess.
- النسخة: تُكتب في مجلد الوجهة، وتُشفَّر (AES-256-GCM) إن فُعِّلت، مع checksum.
- الاحتفاظ: عدد أقصى من النسخ (يُحذف الأقدم تلقائيًا).
- الإشعارات: نجاح/فشل للمستخدم المحدد في BackupSettings.
"""

import json
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone as tz
from django.utils.translation import gettext as _

from .crypto import constant_time_eq, decrypt_file, encrypt_file, sha256_hex
from .models import BackupJob, BackupSettings, RestoreJob


class BackupError(Exception):
    """فشل النسخ/الاستعادة."""


def _backup_dir() -> Path:
    cfg = BackupSettings.get_default()
    path = Path(cfg.backup_dir)
    if not path.is_absolute():
        path = settings.BASE_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _db_path() -> Path:
    """مسار قاعدة SQLite الفعلي — يتبع اتصال Django الحالي (يشمل قاعدة الاختبار)."""
    name = connection.settings_dict["NAME"]
    if name == ":memory:":
        raise BackupError("قاعدة بيانات في الذاكرة لا تدعم النسخ الاحتياطي بهذه الطريقة")
    return Path(name)


def _notify(user, title, body):
    from apps.notif.services import notify as _push

    if user is not None:
        _push(user, "system", title, body)


def run_backup(kind=BackupJob.Kind.MANUAL, user=None) -> BackupJob:
    """ينفّذ نسخة احتياطية ويعيد سجلها.

    يكتب ملفًا بصيغة .hrms في مجلد الوجهة (مشفّر إن فُعِّلت التشفير)،
    مع ملف .json يحوي checksum والحجم — ثم يطبّق سياسة الاحتفاظ.
    """
    from apps.core.services import record_audit

    cfg = BackupSettings.get_default()
    started = tz.now()
    job = BackupJob.objects.create(kind=kind, created_by=user)

    src = _db_path()
    out_dir = _backup_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = out_dir / f"hrms_{stamp}.hrms"

    t0 = time.monotonic()
    try:
        _snapshot_database(src, raw_file)
        checksum = sha256_hex(str(raw_file))

        final = raw_file
        encrypted = False
        if cfg.encrypt:
            encrypted_file = out_dir / f"hrms_{stamp}.enc"
            encrypt_file(str(raw_file), str(encrypted_file))
            raw_file.unlink(missing_ok=True)
            final = encrypted_file
            encrypted = True

        # ملف وصف بجانب النسخة: checksum + الحجم + النوع + التاريخ (للتحقق اليدوي)
        meta = {
            "created": started.isoformat(),
            "kind": kind,
            "checksum": checksum,
            "size": final.stat().st_size,
            "encrypted": encrypted,
        }
        meta_path = out_dir / f"hrms_{stamp}.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        job.status = BackupJob.Status.SUCCESS
        job.file_path = str(final)
        job.file_size = final.stat().st_size
        job.checksum = checksum
        job.encrypted = encrypted
        job.finished_at = tz.now()
        job.duration_seconds = time.monotonic() - t0
        job.save()

        _apply_retention(out_dir)
        record_audit("backup", "export", object_id=str(job.pk), detail=f"نسخة {kind} → {final.name}")
        _notify(cfg.notify_user, _("تم إنشاء نسخة احتياطية"), _("نسخة %(kind)s — %(file)s") % {"kind": kind, "file": final.name})
        return job

    except Exception as exc:  # noqa: BLE001 — يُسجَّل الفشل ليكون مرئيًا
        job.status = BackupJob.Status.FAILED
        job.error = str(exc)[:4000]
        job.finished_at = tz.now()
        job.save()
        raw_file.unlink(missing_ok=True)
        record_audit("backup", "export", object_id=str(job.pk), detail=f"فشل نسخة {kind}: {exc}")
        _notify(cfg.notify_user, _("فشلت النسخة الاحتياطية"), str(exc)[:400])
        raise BackupError(str(exc)) from exc


def _snapshot_database(src: Path, dst: Path) -> None:
    """لقطة متسقة للقاعدة الحالية — SQLite عبر backup() أو pg_dump لـ Postgres."""
    engine = settings.DATABASES["default"]["ENGINE"]
    if "sqlite3" in engine:
        src_con = sqlite3.connect(src)
        try:
            dst_con = sqlite3.connect(dst)
            try:
                src_con.backup(dst_con)
            finally:
                dst_con.close()
        finally:
            src_con.close()
    elif "postgresql" in engine:
        cfg = settings.DATABASES["default"]
        env = dict(
            PGPASSWORD=cfg.get("PASSWORD", ""),
            PATH="/usr/bin:/bin:/usr/local/bin",
        )
        cmd = [
            "pg_dump",
            "-h", cfg.get("HOST", "127.0.0.1"),
            "-p", str(cfg.get("PORT", "5432")),
            "-U", cfg.get("USER", ""),
            "-d", cfg.get("NAME", ""),
            "-Fc",  # تنسيق مخصص (قابل للاستعادة عبر pg_restore)
        ]
        with open(dst, "wb") as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env)
        if result.returncode != 0:
            dst.unlink(missing_ok=True)
            raise BackupError(f"pg_dump فشل: {result.stderr[:500]}")
    else:
        raise BackupError(f"محرك قاعدة بيانات غير مدعوم: {engine}")


def _apply_retention(out_dir: Path) -> None:
    """يبقي آخر retention_count نسخًا (بالملفات *.enc) ويحذف ما قبلها مع الوصف."""
    cfg = BackupSettings.get_default()
    files = sorted(out_dir.glob("hrms_*.enc"), reverse=True)
    for old in files[cfg.retention_count:]:
        old.unlink(missing_ok=True)
        old.with_suffix(".json").unlink(missing_ok=True)


def list_backups() -> list[dict]:
    """قائمة نسخ جاهزة للعرض (مع checksum والحالة من السجلات إن وُجدت)."""
    out_dir = _backup_dir()
    entries = []
    for enc in sorted(out_dir.glob("hrms_*.enc"), reverse=True):
        meta = {"size": enc.stat().st_size}
        meta_path = enc.with_suffix(".json")
        if meta_path.exists():
            try:
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                pass
        entries.append(
            {
                "name": enc.name,
                "path": str(enc),
                "size": meta.get("size", enc.stat().st_size),
                "created": meta.get("created", ""),
                "checksum": meta.get("checksum", ""),
                "kind": meta.get("kind", ""),
            }
        )
    return entries


def restore_backup(enc_path: str, user=None, dry_run=False) -> RestoreJob:
    """يستعيد قاعدة البيانات من نسخة مشفرة — مع التحقق من checksum.

    dry_run=True: يفك التشفير والتحقق فقط دون لمس القاعدة (اختبار استعادة).
    """
    from apps.core.services import record_audit

    path = Path(enc_path)
    if not path.exists():
        raise BackupError(_("الملف غير موجود: %(path)s") % {"path": enc_path})

    job = RestoreJob.objects.create(source_file=enc_path, restored_by=user)
    raw = path.with_suffix(".restore.tmp")

    try:
        decrypt_file(str(path), str(raw))

        # التحقق من checksum من ملف الوصف
        meta_path = path.with_suffix(".json")
        verified = False
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                expected = meta.get("checksum", "")
                if expected and constant_time_eq(sha256_hex(str(raw)), expected):
                    verified = True
            except Exception:  # noqa: BLE001
                pass

        if dry_run:
            job.status = RestoreJob.Status.SUCCESS
            job.checksum_verified = verified
            job.save()
            raw.unlink(missing_ok=True)
            record_audit("backup", "import", object_id=str(job.pk), detail="اختبار استعادة (تحقق فقط)")
            return job

        _restore_database(raw)
        job.status = RestoreJob.Status.SUCCESS
        job.checksum_verified = verified
        job.save()
        record_audit("backup", "import", object_id=str(job.pk), detail="استعادة ناجحة")
        return job

    except Exception as exc:  # noqa: BLE001
        job.status = RestoreJob.Status.FAILED
        job.error = str(exc)[:4000]
        job.save()
        record_audit("backup", "import", object_id=str(job.pk), detail=f"فشل استعادة: {exc}")
        raise BackupError(str(exc)) from exc
    finally:
        raw.unlink(missing_ok=True)


def _restore_database(raw: Path) -> None:
    engine = settings.DATABASES["default"]["ENGINE"]
    if "sqlite3" in engine:
        dst_con = sqlite3.connect(_db_path())
        try:
            src_con = sqlite3.connect(raw)
            try:
                src_con.backup(dst_con)
            finally:
                src_con.close()
        finally:
            dst_con.close()
    elif "postgresql" in engine:
        cfg = settings.DATABASES["default"]
        env = dict(
            PGPASSWORD=cfg.get("PASSWORD", ""),
            PATH="/usr/bin:/bin:/usr/local/bin",
        )
        cmd = [
            "pg_restore",
            "-h", cfg.get("HOST", "127.0.0.1"),
            "-p", str(cfg.get("PORT", "5432")),
            "-U", cfg.get("USER", ""),
            "-d", cfg.get("NAME", ""),
            "--clean", "--if-exists",
            str(raw),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            raise BackupError(f"pg_restore فشل: {result.stderr[:500]}")
    else:
        raise BackupError(f"محرك قاعدة بيانات غير مدعوم: {engine}")
