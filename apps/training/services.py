"""خدمات التدريب — تسجيل + اعتماد + إكمال جلسة + شهادات (v3).

المرجع: docs/03 §3.7 + docs/10-roadmap.md v3 (Training).
القواعد:
    BR-TRN-001  التسجيل وحيد لكل (جلسة، موظف) — لا تكرار.
    BR-TRN-002  الاعتماد لا يتجاوز سعة الجلسة.
    BR-TRN-003  شهادة واحدة لكل تسجيل مكتمل، تُصدر عند إكمال الجلسة.
    BR-TRN-004  الجلسات الملغاة تُحوّل تسجيلاتها إلى "فاشل" بدون شهادة.
"""

from datetime import date

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.notif.services import notify

from .models import TrainingEnrollment, TrainingSession


class TrainingError(Exception):
    """خطأ منطقي في التدريب (يُعرض للمستخدم)."""


def _session_closed(session) -> bool:
    """الجلسة مكتملة/ملغاة؟ — لا مزيد من التعديلات عليها."""
    return session.status in (TrainingSession.Status.COMPLETED, TrainingSession.Status.CANCELLED)


def enroll_employee(session, employee, user=None) -> TrainingEnrollment:
    """BR-TRN-001 — تسجيل موظف في جلسة (idempotent عبر unique)."""
    if _session_closed(session):
        raise TrainingError(_("لا يمكن التسجيل في جلسة مكتملة أو ملغاة"))
    enrollment, created = TrainingEnrollment.objects.get_or_create(
        session=session,
        employee=employee,
        defaults={"status": TrainingEnrollment.Status.PENDING, "created_by": user},
    )
    if created:
        emp = employee
        if emp.user:
            notify(
                emp.user,
                "training_enrollment",
                _("تم تسجيلك في الجلسة %(s)s") % {"s": str(session)},
                _("بانتظار الاعتماد على %(c)s") % {"c": str(session.course)},
                related=session,
            )
    return enrollment


def approve_enrollment(enrollment, user=None):
    """BR-TRN-002 — اعتماد تسجيل قيد الانتظار ضمن السعة."""
    if enrollment.status != TrainingEnrollment.Status.PENDING:
        raise TrainingError(_("التسجيل ليس قيد الانتظار"))
    session = enrollment.session
    if _session_closed(session):
        raise TrainingError(_("لا يمكن الاعتماد في جلسة مكتملة أو ملغاة"))
    if session.seats_left < 1:
        raise TrainingError(_("الجلسة ممتلئة (%(cap)s مقعدًا)") % {"cap": session.capacity})
    enrollment.status = TrainingEnrollment.Status.APPROVED
    enrollment.approved_by = user
    enrollment.approved_at = timezone.now()
    enrollment.updated_by = user
    enrollment.save(update_fields=["status", "approved_by", "approved_at", "updated_by"])
    emp = enrollment.employee
    if emp.user:
        notify(
            emp.user,
            "training_enrollment",
            _("اعتُمد تسجيلك في %(s)s") % {"s": str(session)},
            related=enrollment,
        )
    return enrollment


def reject_enrollment(enrollment, user=None):
    """رفض تسجيل قيد الانتظار (حالة فاشل)."""
    if enrollment.status != TrainingEnrollment.Status.PENDING:
        raise TrainingError(_("التسجيل ليس قيد الانتظار"))
    enrollment.status = TrainingEnrollment.Status.FAILED
    enrollment.approved_by = user
    enrollment.updated_by = user
    enrollment.save(update_fields=["status", "approved_by", "updated_by"])
    emp = enrollment.employee
    if emp.user:
        notify(
            emp.user,
            "training_enrollment",
            _("رُفض تسجيلك في %(s)s") % {"s": str(enrollment.session)},
            related=enrollment,
        )
    return enrollment


def complete_session(session, user=None) -> int:
    """BR-TRN-003 — إكمال الجلسة: تحويل التسجيلات المعتمدة إلى مكتملة وإصدار الشهادات."""
    if session.status == TrainingSession.Status.CANCELLED:
        raise TrainingError(_("الجلسة ملغاة"))
    if session.status == TrainingSession.Status.COMPLETED:
        raise TrainingError(_("الجلسة مكتملة بالفعل"))
    certificates = 0
    for enrollment in session.enrollments.filter(status=TrainingEnrollment.Status.APPROVED):
        enrollment.status = TrainingEnrollment.Status.COMPLETED
        enrollment.updated_by = user
        enrollment.save(update_fields=["status", "updated_by"])
        _issue_certificate(enrollment, user=user)
        certificates += 1
    session.status = TrainingSession.Status.COMPLETED
    session.updated_by = user
    session.save(update_fields=["status", "updated_by"])
    return certificates


def cancel_session(session, user=None):
    """BR-TRN-004 — إلغاء الجلسة: التسجيلات غير المكتملة تصبح فاشل (بدون شهادة)."""
    if session.status in (TrainingSession.Status.COMPLETED, TrainingSession.Status.CANCELLED):
        raise TrainingError(_("الجلسة مكتملة أو ملغاة بالفعل"))
    updated = session.enrollments.exclude(status=TrainingEnrollment.Status.FAILED).update(
        status=TrainingEnrollment.Status.FAILED, updated_by=user
    )
    session.status = TrainingSession.Status.CANCELLED
    session.updated_by = user
    session.save(update_fields=["status", "updated_by"])
    return updated


def _issue_certificate(enrollment, user=None):
    """ينشئ شهادة إتمام لتسجيل مكتمل (idempotent عبر OneToOne)."""
    from .models import TrainingCertificate

    if hasattr(enrollment, "certificate"):
        return enrollment.certificate
    session = enrollment.session
    title = _("شهادة إتمام: %(c)s — %(s)s") % {
        "c": session.course.title_ar,
        "s": session.start_date.strftime("%Y-%m-%d"),
    }
    certificate = TrainingCertificate.objects.create(
        enrollment=enrollment,
        title=title,
        issued_date=date.today(),
        created_by=user,
    )
    emp = enrollment.employee
    if emp.user:
        notify(
            emp.user,
            "training_certificate",
            _("حصلت على شهادة %(c)s") % {"c": session.course.title_ar},
            related=certificate,
        )
    return certificate
