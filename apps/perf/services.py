"""خدمات تقييم الأداء — دورات + مراجعات + أهداف + خطط تحسين (v2).

المرجع: docs/03 §3.8 + docs/10-roadmap.md v2 (Performance).
القواعد:
    BR-PERF-001  المراجعة وحيدة لكل (موظف، دورة) — لا تكرار.
    BR-PERF-002  التقييم الذاتي قبل تقييم المدير (تسلسل الحالة).
    BR-PERF-003  الدرجة النهائية = متوسط مرجّح للأهداف إن وُجدت، وإلا متوسط الدرجتين.
    BR-PERF-004  لا تُعدَّل المراجعة بعد إغلاق الدورة.
    BR-PERF-005  PIP تُفتح لمراجعات مكتملة فقط ولا تُغلق قبل نهاية تاريخها.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from .models import PerfReview, PipPlan


def _cycle_closed(review) -> bool:
    """الدورة مغلقة؟ (استيراد محلي لتجنب الدورات الدائرية)."""
    from .models import PerfCycle

    return review.cycle.status == PerfCycle.Status.CLOSED


class PerfError(Exception):
    """خطأ منطقي في تقييم الأداء (يُعرض للمستخدم)."""


def generate_reviews(cycle, template, employees, user=None):
    """ينشئ مراجعات لموظفين في دورة بقالب (idempotent عبر unique)."""
    created = 0
    for emp in employees:
        _, was_created = PerfReview.objects.get_or_create(
            employee=emp,
            cycle=cycle,
            defaults={
                "template": template,
                "status": PerfReview.Status.PENDING_SELF,
                "created_by": user,
            },
        )
        created += int(was_created)
    return created


def weighted_final_score(review) -> Decimal:
    """BR-PERF-003 — متوسط مرجّح للأهداف إن وُجدت، وإلا متوسط الدرجتين."""
    objectives = list(review.objectives.filter(score__isnull=False))
    if objectives:
        total_weight = sum((o.weight or 0) for o in objectives)
        if total_weight:
            total = sum(((o.score or 0) * o.weight) for o in objectives)
            return (total / total_weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    scores = [s for s in (review.self_score, review.manager_score) if s is not None]
    if not scores:
        return Decimal("0.00")
    return (sum(scores) / len(scores)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def submit_self_review(review, score, comment="", user=None):
    """BR-PERF-002 — تسجيل التقييم الذاتي (لا يُعاد بعد بدء تقييم المدير)."""
    if _cycle_closed(review):
        raise PerfError(_("الدورة مغلقة — لا يمكن التعديل"))
    if review.status == PerfReview.Status.CLOSED:
        raise PerfError(_("المراجعة مغلقة — لا يمكن التعديل"))
    if score is None:
        raise PerfError(_("الدرجة مطلوبة"))
    review.self_score = score
    review.self_comment = comment
    review.updated_by = user
    if review.status == PerfReview.Status.PENDING_SELF:
        review.status = PerfReview.Status.PENDING_MANAGER
    review.save(update_fields=["self_score", "self_comment", "status", "updated_by"])
    return review


def submit_manager_review(review, score, comment="", user=None):
    """تقييم المدير + احتساب الدرجة النهائية (BR-PERF-003)."""
    if _cycle_closed(review):
        raise PerfError(_("الدورة مغلقة — لا يمكن التعديل"))
    if review.status == PerfReview.Status.CLOSED:
        raise PerfError(_("المراجعة مغلقة — لا يمكن التعديل"))
    if review.status == PerfReview.Status.PENDING_SELF:
        raise PerfError(_("التقييم الذاتي لم يُستكمل بعد"))
    if score is None:
        raise PerfError(_("درجة المدير مطلوبة"))
    review.manager_score = score
    review.manager_comment = comment
    review.final_score = weighted_final_score(review)
    review.status = PerfReview.Status.DONE
    review.updated_by = user
    review.save(update_fields=[
        "manager_score", "manager_comment", "final_score", "status", "updated_by",
    ])
    return review


def save_objectives(review, objectives_data, user=None):
    """يحفظ أهداف المراجعة من بيانات (kpi_title, weight, target, achieved, score).

    objectives_data: قائمة dicts — سجلات حاليّة تُحدَّث بالتسلسل، والجديدة تُنشأ.
    """
    existing = list(review.objectives.order_by("id"))
    for i, item in enumerate(objectives_data):
        title = (item.get("kpi_title") or "").strip()
        if not title:
            continue
        data = {
            "kpi_title": title,
            "weight": item.get("weight"),
            "target": item.get("target"),
            "achieved": item.get("achieved"),
            "score": item.get("score"),
        }
        if i < len(existing):
            obj = existing[i]
            for field, value in data.items():
                setattr(obj, field, value)
            obj.updated_by = user
            obj.save()
        else:
            review.objectives.create(updated_by=user, **data)
    # حذف الزوائد
    for obj in existing[len(objectives_data):]:
        obj.delete()
    return review.objectives.count()


def close_cycle(cycle, user=None):
    """BR-PERF-004 — إغلاق الدورة وثبات كل مراجعاتها النهائية."""
    open_reviews = cycle.reviews.exclude(status=PerfReview.Status.DONE)
    if open_reviews.exists():
        raise PerfError(_("لا يمكن الإغلاق: %(n)s مراجعة غير مكتملة") % {"n": open_reviews.count()})
    cycle.status = "closed"
    cycle.updated_by = user
    cycle.save(update_fields=["status", "updated_by"])
    cycle.reviews.filter(status=PerfReview.Status.DONE).update(status=PerfReview.Status.CLOSED)
    return cycle


def open_pip(review, start_date, end_date, action_items, supervisor_note="", user=None):
    """BR-PERF-005 — فتح خطة تحسين لمراجعة مكتملة."""
    if review.status != PerfReview.Status.DONE and review.status != PerfReview.Status.CLOSED:
        raise PerfError(_("الخطة تُفتح لمراجعة مكتملة فقط"))
    if end_date < start_date:
        raise PerfError(_("نهاية الخطة يجب أن تكون بعد بدايتها"))
    return PipPlan.objects.create(
        review=review,
        start_date=start_date,
        end_date=end_date,
        action_items=action_items,
        supervisor_note=supervisor_note,
        created_by=user,
    )


def close_pip(pip, user=None):
    """إغلاق خطة تحسين (لا تُغلق قبل تاريخ نهايتها)."""
    if pip.end_date > timezone.localdate():
        raise PerfError(_("لا يمكن الإغلاق قبل تاريخ الانتهاء (%(date)s)") % {"date": pip.end_date})
    pip.status = PipPlan.Status.CLOSED
    pip.updated_by = user
    pip.save(update_fields=["status", "updated_by"])
    return pip
