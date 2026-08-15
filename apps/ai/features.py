"""استخراج خصائص (Features) كل موظف من قاعدة البيانات للتنبؤ.

نافذة الحساب: آخر 365 يومًا لكل موظف — النهاية = تاريخ انتهاء العقد (للمغادرين)
أو تاريخ اليوم (للنشطين). كل خاصية قابلة للتدقيق ومبنية على بيانات حقيقية.
المرجع: docs/07-ai-module.md §5.1 (ميزات مخاطر الاستقالة).
"""

import datetime

from django.utils import timezone

from apps.attendance.models import AttendanceDay
from apps.leave.models import LeaveRequest

# الخصائص الرقمية (مرتبة، تُدخل النموذج كما هي بعد التوحيد القياسي)
NUMERIC_FEATURES = [
    "attendance_rate",      # حاضر / أيام متوقعة
    "absent_days",          # أيام غياب (آخر 365 يومًا)
    "avg_late_minutes",     # متوسط دقائق التأخير في أيام الحضور
    "late_ratio",           # نسبة أيام التأخير إلى أيام الحضور
    "overtime_minutes",     # إجمالي الدقائق الإضافية
    "sick_leave_days",      # أيام الإجازة المرضية (معتمدة)
    "leave_days_total",     # إجمالي أيام الإجازات المعتمدة
    "perf_score_latest",    # آخر درجة تقييم (final_score / manager_score)
    "perf_trend",           # الفرق بين آخر تقييم والذي قبله
    "perf_count",           # عدد مرات التقييم
    "tenure_days",          # مدة الخدمة
    "salary_growth_12m",    # نمو الأجر آخر 365 يومًا (0..1)
    "num_contracts",        # عدد العقود
    "gross_salary",         # آخر أجر إجمالي
]

# الخصائص الفئوية (تُرمَّز one-hot)
CATEGORICAL_FEATURES = ["department", "position_grade"]

FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

LABEL_COLUMN = "label"  # 1 = مغادر (استقالة/إنهاء/تقاعد)، 0 = باقٍ

# تسمية مخاطر الغياب: 1 = موظف غاب ≥ ABSENCE_RISK_RATIO من الأيام المتوقعة
# (خلال نافذة 365 يومًا) — معيار تدقيقي صريح، لا يختلط مع تسمية المغادرة.
ABSENCE_LABEL_COLUMN = "label_absence"
ABSENCE_RISK_RATIO = 0.15

_DEPARTED_STATUSES = ("resigned", "terminated", "retired")


def _is_departed(employee) -> bool:
    return (not employee.is_active) or (employee.employment_status in _DEPARTED_STATUSES)


def _reference_date(employee) -> datetime.date:
    """نهاية نافذة القياس: آخر عقد للمغادر، واليوم للنشط."""
    if _is_departed(employee):
        contracts = employee.contracts.order_by("-start_date")
        if contracts.exists():
            end = contracts.first().end_date
            if end:
                return end
    return timezone.localdate()


def _features_for(employee) -> dict:
    ref = _reference_date(employee)
    start = ref - datetime.timedelta(days=365)

    days = list(
        AttendanceDay.objects.filter(employee=employee, work_date__gte=start, work_date__lte=ref)
        .values_list("state", "late_minutes", "overtime_minutes")
    )
    expected = len(days)
    present = sum(1 for d in days if d[0] == AttendanceDay.State.PRESENT)
    absent = sum(1 for d in days if d[0] == AttendanceDay.State.ABSENT)
    late_days = [d[1] for d in days if d[0] == AttendanceDay.State.PRESENT and d[1] > 0]
    overtime = sum(d[2] for d in days)

    leave = list(
        LeaveRequest.objects.filter(
            employee=employee,
            status=LeaveRequest.Status.APPROVED,
            from_date__lte=ref,
            to_date__gte=start,
        ).select_related("leave_type")
    )
    sick_days = 0
    leave_total = 0
    for req in leave:
        f = max(req.from_date, start)
        t = min(req.to_date, ref)
        total = max(0, (t - f).days + 1)
        leave_total += total
        if req.leave_type.code == "sick":
            sick_days += total

    reviews = list(
        employee.perf_reviews.filter(status__in=("done", "closed")).order_by("-cycle__period_start")
    )
    scores = []
    for r in reviews:
        score = r.final_score
        if score is None:
            score = r.manager_score
        if score is not None:
            scores.append(float(score))
    latest = scores[0] if scores else None
    trend = (scores[0] - scores[1]) if len(scores) >= 2 else 0.0

    contracts = list(employee.contracts.order_by("start_date"))
    num_contracts = len(contracts)
    gross = float(contracts[-1].gross_salary) if contracts else 0.0
    growth = 0.0
    for c in contracts:
        if c.start_date and start <= c.start_date <= ref and c.previous_contract_id:
            prev = c.previous_contract.gross_salary or 0
            if prev > 0:
                growth = max(growth, float(c.gross_salary - prev) / float(prev))
    if num_contracts >= 1 and not growth:
        # تقدير بسيط: لا عقد حديث بارز ⇒ نمو صفري (يُحسب من عقد واحد فقط)
        pass

    tenure = (ref - employee.hire_date).days if employee.hire_date else 0

    return {
        "attendance_rate": round(present / expected, 4) if expected else 0.0,
        "absent_days": absent,
        "avg_late_minutes": round(sum(d[1] for d in days if d[0] == AttendanceDay.State.PRESENT) / present, 2) if present else 0.0,
        "late_ratio": round(len(late_days) / present, 4) if present else 0.0,
        "overtime_minutes": overtime,
        "sick_leave_days": sick_days,
        "leave_days_total": leave_total,
        "perf_score_latest": latest if latest is not None else 0.0,
        "perf_trend": round(trend, 2),
        "perf_count": len(scores),
        "tenure_days": tenure,
        "salary_growth_12m": round(growth, 4),
        "num_contracts": num_contracts,
        "gross_salary": gross,
        "department": getattr(employee.department, "name_ar", "") or "",
        "position_grade": getattr(employee.position, "grade", "") or "",
        LABEL_COLUMN: 1 if _is_departed(employee) else 0,
        ABSENCE_LABEL_COLUMN: 1 if expected and (absent / expected) >= ABSENCE_RISK_RATIO else 0,
    }


def feature_frame(employees=None):
    """DataFrame بخصائص كل الموظفين (أو قائمة محددة) — مفهرس برقم الموظف."""
    import pandas as pd

    from apps.employees.models import Employee

    if employees is None:
        employees = Employee.objects.select_related("department", "position").all()
    else:
        employees = [e for e in employees]

    rows = []
    for emp in employees:
        row = _features_for(emp)
        row["employee_id"] = emp.id
        rows.append(row)
    if not rows:
        return pd.DataFrame({"employee_id": pd.Series(dtype="int64")}).set_index("employee_id")
    return pd.DataFrame(rows).set_index("employee_id")


def data_quality_report(frame) -> dict:
    """3.3 تدقيق جودة البيانات قبل التدريب — يعيد تقريرًا قياسيًا.

    الغاية: منع تدريب نموذج على بيانات متسخة (نقص/تكرار/أصفار شاملة).
    المرجع: docs/07-ai-module.md §14.3 (جودة البيانات قبل التنبؤ).
    """
    import numpy as np

    report = {"ok": True, "issues": [], "metrics": {}}
    if frame is None or frame.empty:
        return {"ok": False, "issues": ["إطار البيانات فارغ"], "metrics": {}}

    n = len(frame)
    report["metrics"]["rows"] = int(n)
    report["metrics"]["columns"] = int(frame.shape[1])

    # اكتمال: أعمدة رقمية بلا قيم مفقودة
    missing = int(frame.isna().sum().sum())
    report["metrics"]["missing_cells"] = missing
    if missing:
        report["issues"].append(f"{missing} خلية مفقودة")

    # تكرار: مؤشر مكرر (employee_id)
    if frame.index.duplicated().any():
        dup = int(frame.index.duplicated().sum())
        report["issues"].append(f"{dup} صفوف مكررة")
        report["metrics"]["duplicates"] = dup

    # إشارة: هل يوجد صف إيجابي واحد على الأقل
    if LABEL_COLUMN in frame.columns:
        n_pos = int(frame[LABEL_COLUMN].sum())
        report["metrics"]["n_positive"] = n_pos
        if n_pos == 0:
            report["issues"].append("لا توجد عينات إيجابية (لا مغادرين)")

    # أصفار شاملة في أعمدة جوهرية (معدل الحضور والأجر) قد تعني بيانات ناقصة
    for col in ("attendance_rate", "gross_salary"):
        if col in frame.columns:
            zeros = int((frame[col].fillna(0) == 0).sum())
            report["metrics"].setdefault("zeros", {})[col] = zeros
            if zeros > n * 0.9 and n > 5:
                report["issues"].append(f"العمود {col} أغلب قيمه صفر ({zeros}/{n})")

    report["ok"] = not report["issues"]
    return report
