"""تشفير النسخ الاحتياطية (AES-256-GCM) + اشتقاق المفتاح + checksum.

المرجع: docs/09-security.md §7/§8 — ملفات النسخ مشفرة قبل مغادرتها الخادم.
- المفتاح يُشتق من HRMS_BACKUP_KEY (env) عبر HKDF-SHA256، ويقع في .env (600).
- التشفير: AES-256-GCM (AEAD: سري + سلامة ضد العبث) مع random nonce.
- صيغة الملف: [ماجيك 4 بايت][nonce 12][tag 16][ciphertext].
"""

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from django.conf import settings

MAGIC = b"HRMS1"
NONCE_SIZE = 12
TAG_SIZE = 16


def _passphrase():
    """المفتاح من البيئة HRMS_BACKUP_KEY (إن وُجد) وإلا SECRET_KEY.

    في الإنتاج يُفرض HRMS_BACKUP_KEY (انظر docs/09-security.md §8 إدارة المفاتيح).
    """
    key = getattr(settings, "HRMS_BACKUP_KEY", "")
    if key:
        return key.encode()
    return settings.SECRET_KEY.encode()


def derive_key() -> bytes:
    """32 بايت لمفتاح AES-256 — من عبارة المرور عبر HKDF-SHA256."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"hrms-backup-v1",
    ).derive(_passphrase())


def sha256_hex(path: str) -> str:
    """SHA-256 للملف — للتحقق من سلامة النسخة."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def encrypt_file(src_path: str, dst_path: str) -> None:
    """تشفير src_path → dst_path (AES-256-GCM)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = derive_key()
    nonce = os.urandom(NONCE_SIZE)
    with open(src_path, "rb") as f:
        plaintext = f.read()
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    with open(dst_path, "wb") as f:
        f.write(MAGIC + nonce + ciphertext)  # ciphertext يبدأ بـ tag (16)


def decrypt_file(src_path: str, dst_path: str) -> None:
    """فك تشفير src_path → dst_path. يرفع InvalidTag عند العبث أو مفتاح خاطئ."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    with open(src_path, "rb") as f:
        blob = f.read()
    if blob[: len(MAGIC)] != MAGIC:
        raise ValueError("ملف غير صالح (مفتقد للترويسة) — ليس نسخة مشفرة HRMS")
    nonce = blob[len(MAGIC): len(MAGIC) + NONCE_SIZE]
    ciphertext = blob[len(MAGIC) + NONCE_SIZE:]
    key = derive_key()
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    with open(dst_path, "wb") as f:
        f.write(plaintext)


def constant_time_eq(a: str, b: str) -> bool:
    """مقارنة checksum آمنة ضد هجمات التوقيت."""
    return hmac.compare_digest(a.encode(), b.encode())
