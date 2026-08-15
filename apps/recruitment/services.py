"""خدمات التوظيف — حالات المرشح + مقابلات + توظيف مرشح (v4).

القواعد:
    BR-REC-001  توظيف المرشح يُنشئ ملف موظف فريدًا ويربطه مرة واحدة.
    BR-REC-002  لا يُعاد فتح إعلان مُغلق.
    BR-REC-003  إنهاء المرشح (رفض/تعيين/انسحاب) يغلق مقابلاته الجارية.
"""

import re
from datetime import date

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.notif.services import notify

from .models import Candidate, Interview, JobPosting


class RecruitmentError(Exception):
    """خطأ منطقي في التوظيف (يُعرض للمستخدم)."""


_TERMINAL = {Candidate.Status.HIRED, Candidate.Status.REJECTED, Candidate.Status.WITHDRAWN}


def publish_posting(posting, user=None) -> JobPosting:
    """ينشر الإعلان (تاريخ النشر = اليوم إن لم يُحدد)."""
    if posting.status == JobPosting.Status.CLOSED:
        raise RecruitmentError(_("لا يمكن إعادة نشر إعلان مغلق"))
    posting.status = JobPosting.Status.PUBLISHED
    if not posting.publish_date:
        posting.publish_date = date.today()
    posting.updated_by = user
    posting.save(update_fields=["status", "publish_date", "updated_at", "updated_by"])
    return posting


def close_posting(posting, user=None) -> JobPosting:
    """يغلق الإعلان (المرشحون الحاليون يبقون، لا يقبل إضافة مرشحين جدد)."""
    posting.status = JobPosting.Status.CLOSED
    posting.close_date = posting.close_date or date.today()
    posting.updated_by = user
    posting.save(update_fields=["status", "close_date", "updated_at", "updated_by"])
    return posting


def add_candidate(posting, *, email, first_name_ar, last_name_ar, user=None, **extra) -> Candidate:
    """يضيف مرشحًا لإعلان (يمنع ذلك للإعلان المغلق)."""
    if posting and posting.status == JobPosting.Status.CLOSED:
        raise RecruitmentError(_("الإعلان مغلق ولا يقبل مرشحين جدد"))
    candidate = Candidate.objects.create(
        posting=posting,
        email=email,
        first_name_ar=first_name_ar,
        last_name_ar=last_name_ar,
        applied_date=extra.pop("applied_date", date.today()),
        created_by=user,
        updated_by=user,
        **extra,
    )
    return candidate


def set_candidate_status(candidate, status, user=None, note="") -> Candidate:
    """يغيّر حالة مرشح (لا يقبل تغيير مرشح نهائي أو توظيف مرشح معيّن)."""
    if candidate.status in _TERMINAL:
        raise RecruitmentError(_("المرشح في حالة نهائية (%(s)s)") % {"s": candidate.get_status_display()})
    if status == Candidate.Status.HIRED:
        raise RecruitmentError(_("استخدم «توظيف المرشح» لإنشاء ملف الموظف"))
    candidate.status = status
    candidate.notes = (candidate.notes + "\n" + note).strip() if note else candidate.notes
    candidate.updated_by = user
    candidate.save(update_fields=["status", "notes", "updated_at", "updated_by"])
    if status in _TERMINAL:
        _cancel_open_interviews(candidate)
    return candidate


def schedule_interview(candidate, *, scheduled_at, user=None, interviewer=None, mode=Interview.Mode.IN_PERSON) -> Interview:
    """جدولة مقابلة لمرشح غير نهائي (ينقل المرشح الجديد إلى قيد الفرز)."""
    if candidate.status in _TERMINAL:
        raise RecruitmentError(_("لا يمكن جدولة مقابلة لمرشح نهائي"))
    if candidate.status == Candidate.Status.NEW:
        candidate.status = Candidate.Status.SCREENING
        candidate.updated_by = user
        candidate.save(update_fields=["status", "updated_at", "updated_by"])
    return Interview.objects.create(
        candidate=candidate,
        interviewer=interviewer,
        scheduled_at=scheduled_at,
        mode=mode,
        created_by=user,
        updated_by=user,
    )


def complete_interview(interview, *, score, notes="", user=None) -> Interview:
    """استكمال مقابلة وتسجيل درجتها (BR-REC-003)."""
    if interview.status == Interview.Status.CANCELLED:
        raise RecruitmentError(_("المقابلة ملغاة"))
    interview.status = Interview.Status.COMPLETED
    interview.score = max(0, min(100, score))
    interview.notes = (interview.notes + "\n" + notes).strip() if notes else interview.notes
    interview.updated_by = user
    interview.save(update_fields=["status", "score", "notes", "updated_at", "updated_by"])
    candidate = interview.candidate
    if candidate.status == Candidate.Status.NEW:
        candidate.status = Candidate.Status.INTERVIEWED
        candidate.updated_by = user
        candidate.save(update_fields=["status", "updated_at", "updated_by"])
    return interview


def _cancel_open_interviews(candidate):
    candidate.interviews.filter(status=Interview.Status.SCHEDULED).update(status=Interview.Status.CANCELLED)


def _next_employee_code() -> str:
    """ينشئ رمز موظف فريدًا: EMP-<أكبر رقمي موجود + 1>."""
    from apps.employees.models import Employee

    max_num = 0
    for code in Employee.objects.values_list("employee_code", flat=True):
        match = re.fullmatch(r"EMP-(\d+)", code)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"EMP-{max_num + 1:04d}"


def hire_candidate(candidate, *, user=None, branch=None, department=None, position=None, hire_date=None) -> Candidate:
    """BR-REC-001 — توظيف مرشح: ينشئ موظفًا ويربطه ويحوله لحالة HIRED.

    يشترط: قبول المرشح للعرض الوظيفي (حالة OFFER) وإعلانًا مفعّلًا (منشورًا).
    يُحال المحاورون/المرشحون بإشعار داخلي.
    """
    if candidate.status in _TERMINAL:
        raise RecruitmentError(_("المرشح في حالة نهائية (%(s)s)") % {"s": candidate.get_status_display()})
    if candidate.hired_employee_id:
        raise RecruitmentError(_("هذا المرشح معيّن بالفعل"))
    if candidate.status != Candidate.Status.OFFER:
        raise RecruitmentError(_("لا يمكن توظيف مرشح لم يقبل العرض الوظيفي بعد"))
    if candidate.posting and candidate.posting.status != JobPosting.Status.PUBLISHED:
        raise RecruitmentError(_("الإعلان غير مفعّل — لا يمكن التوظيف"))

    from apps.employees.models import Employee

    employee = Employee.objects.create(
        employee_code=_next_employee_code(),
        first_name_ar=candidate.first_name_ar,
        last_name_ar=candidate.last_name_ar,
        first_name_fr=candidate.first_name_fr,
        last_name_fr=candidate.last_name_fr,
        first_name_en=candidate.first_name_en,
        last_name_en=candidate.last_name_en,
        email=candidate.email,
        phone=candidate.phone,
        hire_date=hire_date or date.today(),
        branch=branch or (candidate.posting.branch if candidate.posting else None),
        department=department or (candidate.posting.department if candidate.posting else None),
        created_by=user,
        updated_by=user,
    )
    candidate.hired_employee = employee
    candidate.status = Candidate.Status.HIRED
    candidate.updated_by = user
    candidate.save(update_fields=["hired_employee", "status", "updated_at", "updated_by"])
    _cancel_open_interviews(candidate)

    posting = candidate.posting
    if posting and posting.candidates.filter(status=Candidate.Status.HIRED).count() >= posting.openings_count:
        close_posting(posting, user=user)

    for interview in candidate.interviews.filter(interviewer__isnull=False):
        interviewer = interview.interviewer
        if interviewer != user:
            notify(
                interviewer,
                "recruitment_hired",
                _("تم توظيف المرشح %(c)s") % {"c": str(candidate)},
                _("أُنشئ ملف الموظف %(code)s") % {"code": employee.employee_code},
                related=employee,
            )
    return candidate
