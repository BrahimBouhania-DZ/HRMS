"""خدمة دورة حياة QR (T-QR-1, T-QR-7).

القاعدة (docs/06 §4): صف واحد لكل موظف (OneToOne) — النسخة النشطة واحدة فقط.
إعادة التوليد تُحدّث الصف نفسه: سر جديد + v+1 + إعادة تنشيط.
"""

from django.utils import timezone

from .models import Employee, EmployeeQR
from .qr_engine import generate_payload, new_secret


def issue_qr(employee: Employee, issued_by=None) -> EmployeeQR:
    """يُنشئ أو يعيد توليد QR نشطًا لموظف (نسخة واحدة فقط)."""
    qr = EmployeeQR.objects.filter(employee=employee).first()
    now = timezone.now()

    if qr is None:
        qr = EmployeeQR.objects.create(
            employee=employee,
            secret=new_secret(),
            version=1,
            status=EmployeeQR.Status.ACTIVE,
            activated_at=now,
            created_by=issued_by,
        )
        return qr

    qr.secret = new_secret()
    qr.version = qr.version + 1
    qr.status = EmployeeQR.Status.ACTIVE
    qr.activated_at = now
    qr.expires_at = None
    qr.revoked_at = None
    qr.revoked_by = None
    qr.updated_by = issued_by
    qr.save()
    return qr


def regenerate_qr(employee: Employee, issued_by=None) -> EmployeeQR:
    """إعادة توليد: تحديث الصف (سر جديد + v+1)."""
    return issue_qr(employee, issued_by)


def revoke_qr(employee: Employee, issued_by=None) -> None:
    """إلغاء فوري للنسخة النشطة (إنهاء خدمة / فقدان / انكشاف السر)."""
    qr = EmployeeQR.objects.filter(employee=employee, status=EmployeeQR.Status.ACTIVE).first()
    if qr:
        qr.status = EmployeeQR.Status.REVOKED
        qr.revoked_at = timezone.now()
        qr.revoked_by = issued_by
        qr.updated_by = issued_by
        qr.save()


def get_active_qr(employee: Employee) -> EmployeeQR | None:
    return EmployeeQR.objects.filter(
        employee=employee, status=EmployeeQR.Status.ACTIVE
    ).first()


def get_qr_payload(employee: Employee) -> str | None:
    """نص QR الجاهز للعرض/الطباعة (أو None إن لم يوجد QR نشط)."""
    qr = get_active_qr(employee)
    if not qr:
        return None
    return generate_payload(employee.id, qr.version, qr.activated_at.timestamp())
