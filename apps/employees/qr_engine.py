"""QR Engine — توليد/توقيع/تحقق رمز QR (T-QR-2).

المرجع: docs/06-qr-system.md §3.

البنية: payload = base64(header) + "." + base64(signature)
- header: {"eid": <معرف موظف مشفّر>, "v": version, "ts": issued_at}
- signature: HMAC-SHA256(marker + "." + encoded_payload, SECRET_KEY)
السر لا يغادر الخادم — أي QR خارجي مرفوض.
"""

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time

from django.conf import settings

# أوبسكود: عكس 64 بت (Obfuscate)
_OBFUSCATE_KEY = 0x5DEECE66D  # ثابت داخلي لا يُكشف خارج الخادم
_MAGIC = b"HRMS::QR"

SECRET_KEY = settings.SECRET_KEY.encode()


def _obfuscate(employee_id: int) -> str:
    """يشفر معرف الموظف: XOR مع مفتاح ثابت + تدوير البتات."""
    x = (employee_id ^ _OBFUSCATE_KEY) & 0xFFFFFFFFFFFFFFFF
    return struct.pack(">Q", x).hex()


def _deobfuscate(token: str) -> int:
    x = struct.unpack(">Q", bytes.fromhex(token))[0]
    return (x ^ _OBFUSCATE_KEY) & 0xFFFFFFFFFFFFFFFF


def _encode(obj: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).decode()


def _decode(token: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(token.encode()))


def _sign(marker: bytes, payload_b64: str) -> str:
    return hmac.new(SECRET_KEY, marker + b"." + payload_b64.encode(), hashlib.sha256).hexdigest()


def generate_payload(employee_id: int, version: int, issued_at: float | None = None) -> str:
    """ينشئ نص QR موقّعًا (payload) لموظف وإصدار محدد."""
    issued_at = issued_at or time.time()
    header = {
        "eid": _obfuscate(employee_id),
        "v": version,
        "ts": int(issued_at),
    }
    payload_b64 = _encode(header)
    sig = _sign(_MAGIC, payload_b64)
    return f"{payload_b64}.{sig}"


def verify_payload(payload: str) -> dict | None:
    """يتحقق من التوقيع ويعيد الـ header، أو None عند التزوير/التلف."""
    try:
        payload_b64, sig = payload.split(".", 1)
        expected = _sign(_MAGIC, payload_b64)
        if not hmac.compare_digest(sig, expected):
            return None
        header = _decode(payload_b64)
        header["employee_id"] = _deobfuscate(header["eid"])
        return header
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def new_secret() -> str:
    """سر عشوائي 32 حرفًا سداسيًا."""
    return secrets.token_hex(16)


def is_payload_valid(payload: str) -> bool:
    return verify_payload(payload) is not None
