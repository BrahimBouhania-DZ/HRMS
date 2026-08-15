"""خدمة المساعد الذكي (AI Assistant) — T-AI-2/T-AI-3.

المرجع: docs/07-ai-module.md §4 (فهم السؤال) + §10 (دورة المعالجة) + §11 (الأمان).

- **قراءة فقط**: لا توجد أي عملية كتابة هنا إلا سجل التدقيق ai_aiquery.
- **استعلامات معلمة**: تُبنى عبر ORM فقط (لا يُبنى SQL من النص) — ممنوع الحقن.
- **النطاق**: كل استعلام عن الموظفين يمر عبر employee_scope_queryset(user).
- **التدقيق**: كل سؤال/إجابة يُسجَّل في AIQuery (من سأل، ماذا، متى، النتيجة).
"""

import datetime

from django.db.models import Avg, Count, OuterRef, Subquery, Sum
from django.utils import timezone

from apps.ai import nlp, services
from apps.ai.models import AIQuery, AIPrediction
from apps.attendance.models import AttendanceDay
from apps.auth_app.scopes import employee_scope_queryset
from apps.employees.models import Contract
from apps.leave.models import LeaveRequest
from apps.org.models import Branch, Department
from apps.perf.models import PerfReview
from apps.payroll.models import PayRun, Payslip

# --------------------------------------------------------------------- صياغة


def _num(lang: str, n) -> str:
    """تنسيق عدد مع فواصل آلاف حسب اللغة."""
    n = int(round(n))
    s = f"{n:,}"
    if lang == "fr":
        s = s.replace(",", "\u202f")
    return s


def _money(lang: str, amount) -> str:
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
    unit = {"ar": " دج", "fr": " DA", "en": " DZD"}[lang]
    return f"{_num(lang, amount)}{unit}"


def _fmt_date(lang: str, d) -> str:
    if not d:
        return "—"
    return d.strftime("%Y-%m-%d")


def _employee_name(emp, lang: str) -> str:
    if lang == "ar":
        return f"{emp.first_name_ar} {emp.last_name_ar}"
    return f"{emp.first_name_fr or emp.first_name_en} {emp.last_name_fr or emp.last_name_en}"


def _dept_name(dep, lang: str) -> str:
    if dep is None:
        return "—"
    if lang == "ar":
        return dep.name_ar
    return dep.name_fr or dep.name_en or dep.name_ar


def _src(lang: str, key: str) -> str:
    return _SOURCES[lang].get(key) or _SOURCES["ar"].get(key) or key


_SOURCES = {
    "ar": {
        "employees": "سجلات الموظفين",
        "attendance": "سجل الحضور",
        "leave": "طلبات الإجازة",
        "payroll": "دورات الرواتب",
        "perf": "سجلات التقييم",
        "prediction": "نماذج التنبؤ",
        "assistant": "المساعد الذكي",
    },
    "fr": {
        "employees": "Registre des employés",
        "attendance": "Registre de présence",
        "leave": "Demandes de congé",
        "payroll": "Cycles de paie",
        "perf": "Registre des évaluations",
        "prediction": "Modèles de prédiction",
        "assistant": "Assistant IA",
    },
    "en": {
        "employees": "Employee records",
        "attendance": "Attendance records",
        "leave": "Leave requests",
        "payroll": "Payroll cycles",
        "perf": "Review records",
        "prediction": "Prediction models",
        "assistant": "AI assistant",
    },
}

_T = {
    "ar": {
        "no_scope": "ليست لديك صلاحية رؤية بيانات الموظفين.",
        "unknown": "لم أفهم السؤال بدقة. جرّب من الأسئلة السريعة، أو صُغ السؤال بشكل أوضح.",
        "help": "يمكنني الإجابة عن: عدد الموظفين، الغياب اليومي، التأخر، الإجازات، الرواتب، التقييمات، ومخاطر الاستقالة — بلغات متعددة وضمن نطاق صلاحياتك.",
        "headcount": "عدد الموظفين النشطين: {count}.",
        "headcount_dept": "عدد موظفي قسم {dept}: {count}.",
        "absent_today": "عدد الغائبين اليوم: {count} موظفًا.",
        "present_today": "عدد الحاضرين اليوم: {count} موظفًا.",
        "late_top": "الأقسام الأعلى تأخرًا هذا الشهر:",
        "late_top_dept": "عدد حالات التأخر المسجلة في قسم {dept} هذا الشهر: {count}.",
        "late_empty": "لا توجد تأخيرات مسجلة في هذه الفترة.",
        "leave_pending": "طلبات الإجازة المعلقة (قيد الموافقة): {count}.",
        "leave_days": "أيام الإجازة المعتمدة (سنة {year}): {count} يومًا.",
        "payroll_month": "كتلة الأجور لفترة {period}: {total} ({count} قسيمة).",
        "payroll_none": "لا توجد دورة رواتب منشورة للفترة {period}.",
        "avg_salary": "متوسط الأجر الإجمالي: {avg}.",
        "perf_avg": "متوسط درجات التقييم: {avg} (من {count} تقييمًا).",
        "perf_top": "أفضل {limit} موظفًا أداءً:",
        "perf_empty": "لا توجد تقييمات منجزة بعد.",
        "turnover": "موظفون بمخاطر استقالة مرتفعة/متوسطة: {count}.",
        "turnover_dept": "موظفون بمخاطر استقالة في قسم {dept}: {count}.",
        "turnover_untrained": "نموذج التنبؤ غير مدرب بعد — شغّل seed_ai_data ثم train_ai_models.",
        "turnover_empty": "لا توجد تنبؤات مخاطر حالية.",
        "employee_info": "الموظف {code}: {name} — القسم: {dept} — المسمى: {position} — تاريخ التوظيف: {hired} — الحالة: {status}.",
        "employee_not_found": "لم أجد موظفًا بهذا الرمز/الاسم ضمن نطاقك.",
        "rows_header": "النتائج:",
    },
    "fr": {
        "no_scope": "Vous n'avez pas le droit de consulter les données des employés.",
        "unknown": "Je n'ai pas bien compris la question. Essayez les questions rapides ou reformulez.",
        "help": "Je peux répondre : effectif, absences du jour, retards, congés, salaires, évaluations et risque de départ — en plusieurs langues et dans votre périmètre.",
        "headcount": "Effectif des employés actifs : {count}.",
        "headcount_dept": "Employés du service {dept} : {count}.",
        "absent_today": "Absents aujourd'hui : {count} employé(s).",
        "present_today": "Présents aujourd'hui : {count} employé(s).",
        "late_top": "Services les plus en retard ce mois-ci :",
        "late_top_dept": "Retards enregistrés au service {dept} ce mois-ci : {count}.",
        "late_empty": "Aucun retard enregistré sur cette période.",
        "leave_pending": "Demandes de congé en attente d'approbation : {count}.",
        "leave_days": "Jours de congé approuvés (année {year}) : {count}.",
        "payroll_month": "Masse salariale de {period} : {total} ({count} bulletin(s)).",
        "payroll_none": "Aucune paie publiée pour {period}.",
        "avg_salary": "Salaire brut moyen : {avg}.",
        "perf_avg": "Score moyen d'évaluation : {avg} ({count} évaluation(s)).",
        "perf_top": "Les {limit} meilleurs employés :",
        "perf_empty": "Aucune évaluation terminée pour l'instant.",
        "turnover": "Employés à risque de départ élevé/moyen : {count}.",
        "turnover_dept": "Employés à risque de départ au service {dept} : {count}.",
        "turnover_untrained": "Le modèle de prédiction n'est pas encore entraîné — lancez seed_ai_data puis train_ai_models.",
        "turnover_empty": "Aucune prédiction de risque actuelle.",
        "employee_info": "Employé {code} : {name} — Service : {dept} — Poste : {position} — Date d'embauche : {hired} — Statut : {status}.",
        "employee_not_found": "Aucun employé trouvé avec ce code/nom dans votre périmètre.",
        "rows_header": "Résultats :",
    },
    "en": {
        "no_scope": "You are not allowed to view employee data.",
        "unknown": "I did not understand the question. Try the quick questions or rephrase.",
        "help": "I can answer: headcount, today's absences, lateness, leave, payroll, reviews and turnover risk — in several languages within your scope.",
        "headcount": "Active employees: {count}.",
        "headcount_dept": "Employees in {dept} department: {count}.",
        "absent_today": "Absent today: {count} employee(s).",
        "present_today": "Present today: {count} employee(s).",
        "late_top": "Departments with most lateness this month:",
        "late_top_dept": "Lateness records in {dept} department this month: {count}.",
        "late_empty": "No lateness recorded in this period.",
        "leave_pending": "Pending leave requests (awaiting approval): {count}.",
        "leave_days": "Approved leave days (year {year}): {count}.",
        "payroll_month": "Payroll total for {period}: {total} ({count} slip(s)).",
        "payroll_none": "No published payroll for {period}.",
        "avg_salary": "Average gross salary: {avg}.",
        "perf_avg": "Average review score: {avg} ({count} review(s)).",
        "perf_top": "Top {limit} performers:",
        "perf_empty": "No completed reviews yet.",
        "turnover": "Employees at high/medium turnover risk: {count}.",
        "turnover_dept": "Employees at turnover risk in {dept}: {count}.",
        "turnover_untrained": "The prediction model is not trained yet — run seed_ai_data then train_ai_models.",
        "turnover_empty": "No current risk predictions.",
        "employee_info": "Employee {code}: {name} — Department: {dept} — Position: {position} — Hire date: {hired} — Status: {status}.",
        "employee_not_found": "No employee found with this code/name in your scope.",
        "rows_header": "Results:",
    },
}

_DEP_STATUS = {
    "ar": {"active": "نشط", "resigned": "استقال", "terminated": "منتهي الخدمة", "retired": "متقاعد"},
    "fr": {"active": "actif", "resigned": "démissionné", "terminated": "licencié", "retired": "retraité"},
    "en": {"active": "active", "resigned": "resigned", "terminated": "terminated", "retired": "retired"},
}


def _t(lang: str, key: str, **kw) -> str:
    template = _T.get(lang, _T["ar"]).get(key) or _T["ar"][key]
    return template.format(**kw)


# --------------------------------------------------------------------- تنفيذ


def answer_question(user, prompt: str, language: str = nlp.DEFAULT_LANG) -> dict:
    """يُعالج سؤالًا ويعيد إجابة منظمة، مع تسجيل تدقيقي في AIQuery."""
    norm = nlp.normalize(prompt)
    lang = nlp.detect_language(prompt, language)
    intent, score = nlp.detect_intent(norm, lang)
    entities = nlp.extract_entities(
        norm, lang,
        departments=list(Department.objects.all()),
        branches=list(Branch.objects.all()),
    )
    entities["_norm"] = norm
    scope = employee_scope_queryset(user)
    result = _run(intent, user, lang, entities, scope, score)
    answer = {
        "intent": result["intent"],
        "confidence": score,
        "language": lang,
        "text": result["text"],
        "rows": result.get("rows", []),
        "source": result.get("source", ""),
    }
    AIQuery.objects.create(user=user, prompt=prompt, answer_json=answer, language=lang)
    return answer


def _run(intent, user, lang, entities, scope, score: int) -> dict:
    handler = _HANDLERS.get(intent, _HANDLERS["unknown"])
    return handler(user, lang, entities, scope)


# --------------------------------------------------------------------- معالجات


def _h_unknown(user, lang, e, scope):
    return {"intent": "unknown", "text": _t(lang, "unknown"), "rows": [], "source": _src(lang, "assistant")}


def _h_help(user, lang, e, scope):
    return {"intent": "help", "text": _t(lang, "help"), "rows": [], "source": _src(lang, "assistant")}


def _h_headcount(user, lang, e, scope):
    if scope.query.is_empty():
        return {"intent": "headcount", "text": _t(lang, "no_scope"), "rows": [], "source": _src(lang, "employees")}
    qs = scope
    dept = e["department"]
    if dept is not None:
        qs = qs.filter(department=dept)
    count = qs.count()
    if dept is not None:
        text = _t(lang, "headcount_dept", dept=_dept_name(dept, lang), count=_num(lang, count))
    else:
        text = _t(lang, "headcount", count=_num(lang, count))
    return {"intent": "headcount", "text": text, "rows": [], "source": _src(lang, "employees")}


def _h_absent_today(user, lang, e, scope):
    today = timezone.localdate()
    count = AttendanceDay.objects.filter(
        employee__in=scope, work_date=today, state=AttendanceDay.State.ABSENT
    ).count()
    return {"intent": "absent_today", "text": _t(lang, "absent_today", count=_num(lang, count)),
            "rows": [], "source": _src(lang, "attendance")}


def _h_present_today(user, lang, e, scope):
    today = timezone.localdate()
    count = AttendanceDay.objects.filter(
        employee__in=scope, work_date=today, state=AttendanceDay.State.PRESENT
    ).count()
    return {"intent": "present_today", "text": _t(lang, "present_today", count=_num(lang, count)),
            "rows": [], "source": _src(lang, "attendance")}


def _h_late_top(user, lang, e, scope):
    today = timezone.localdate()
    month, year = e["month"] or today.month, e["year"] or today.year
    start = today.replace(year=year, month=month, day=1)
    nxt = (start + datetime.timedelta(days=32)).replace(day=1)
    base = AttendanceDay.objects.filter(
        employee__in=scope, work_date__gte=start, work_date__lt=nxt, late_minutes__gt=0
    )
    dept = e["department"]
    if dept is not None:
        count = base.filter(employee__department=dept).count()
        text = _t(lang, "late_top_dept", dept=_dept_name(dept, lang), count=_num(lang, count))
        return {"intent": "late_top", "text": text, "rows": [], "source": _src(lang, "attendance")}
    rows = list(
        base.values("employee__department__name_ar", "employee__department__name_fr", "employee__department__name_en")
        .annotate(n=Count("id")).order_by("-n")[: e["limit"] or 5]
    )
    if not rows:
        return {"intent": "late_top", "text": _t(lang, "late_empty"), "rows": [], "source": _src(lang, "attendance")}
    return {
        "intent": "late_top",
        "text": _t(lang, "late_top"),
        "rows": [{"name": r["employee__department__name_ar"], "count": r["n"]} for r in rows],
        "source": _src(lang, "attendance"),
    }


def _h_leave_pending(user, lang, e, scope):
    count = LeaveRequest.objects.filter(
        employee__in=scope, status=LeaveRequest.Status.PENDING
    ).count()
    return {"intent": "leave_pending", "text": _t(lang, "leave_pending", count=_num(lang, count)),
            "rows": [], "source": _src(lang, "leave")}


def _h_leave_days(user, lang, e, scope):
    year = e["year"] or timezone.localdate().year
    total = LeaveRequest.objects.filter(
        employee__in=scope, status=LeaveRequest.Status.APPROVED, from_date__year=year
    ).aggregate(s=Sum("days"))["s"] or 0
    return {"intent": "leave_days", "text": _t(lang, "leave_days", year=year, count=_num(lang, float(total))),
            "rows": [], "source": _src(lang, "leave")}


def _h_payroll_month(user, lang, e, scope):
    today = timezone.localdate()
    month, year = e["month"] or today.month, e["year"] or today.year
    period = f"{year:04d}-{month:02d}"
    runs = PayRun.objects.filter(period_code=period, status__in=[PayRun.Status.APPROVED, PayRun.Status.FROZEN])
    slips = Payslip.objects.filter(pay_run__in=runs, employee__in=scope)
    total = slips.aggregate(s=Sum("net"))["s"]
    count = slips.count()
    if total is None:
        return {"intent": "payroll_month", "text": _t(lang, "payroll_none", period=period),
                "rows": [], "source": _src(lang, "payroll")}
    return {"intent": "payroll_month",
            "text": _t(lang, "payroll_month", period=period, total=_money(lang, total), count=_num(lang, count)),
            "rows": [], "source": _src(lang, "payroll")}


def _h_avg_salary(user, lang, e, scope):
    latest = Contract.objects.filter(employee=OuterRef("pk")).order_by("-start_date").values("gross_salary")[:1]
    values = [v for v in scope.annotate(gross=Subquery(latest)).values_list("gross", flat=True) if v is not None]
    avg = (sum(values) / len(values)) if values else 0
    return {"intent": "avg_salary", "text": _t(lang, "avg_salary", avg=_money(lang, avg)),
            "rows": [], "source": _src(lang, "employees")}


def _h_perf_avg(user, lang, e, scope):
    agg = PerfReview.objects.filter(employee__in=scope, status__in=[PerfReview.Status.DONE, PerfReview.Status.CLOSED]) \
        .aggregate(avg=Avg("final_score"), n=Count("id"))
    avg = float(agg["avg"] or 0)
    count = agg["n"] or 0
    return {"intent": "perf_avg", "text": _t(lang, "perf_avg", avg=f"{avg:.1f}", count=_num(lang, count)),
            "rows": [], "source": _src(lang, "perf")}


def _h_perf_top(user, lang, e, scope):
    limit = e["limit"] or 5
    qs = PerfReview.objects.filter(
        employee__in=scope, status__in=[PerfReview.Status.DONE, PerfReview.Status.CLOSED]
    ).select_related("employee__department").order_by("-final_score", "-id")
    rows, seen = [], set()
    for r in qs:
        if r.employee_id in seen:
            continue
        seen.add(r.employee_id)
        rows.append({"code": r.employee.employee_code,
                     "name": _employee_name(r.employee, lang),
                     "score": float(r.final_score or 0)})
        if len(rows) >= limit:
            break
    if not rows:
        return {"intent": "perf_top", "text": _t(lang, "perf_empty"), "rows": [], "source": _src(lang, "perf")}
    return {"intent": "perf_top", "text": _t(lang, "perf_top", limit=limit),
            "rows": rows, "source": _src(lang, "perf")}


def _h_turnover(user, lang, e, scope):
    if services.model_status(AIPrediction.Type.RESIGNATION) is None:
        return {"intent": "turnover_risk", "text": _t(lang, "turnover_untrained"),
                "rows": [], "source": _src(lang, "prediction")}
    preds = AIPrediction.objects.filter(
        employee__in=scope, prediction_type=AIPrediction.Type.RESIGNATION,
        level__in=["high", "medium"],
    )
    dept = e["department"]
    if dept is not None:
        preds = preds.filter(employee__department=dept)
    count = preds.count()
    if count == 0:
        return {"intent": "turnover_risk", "text": _t(lang, "turnover_empty"),
                "rows": [], "source": _src(lang, "prediction")}
    if dept is not None:
        text = _t(lang, "turnover_dept", dept=_dept_name(dept, lang), count=_num(lang, count))
    else:
        text = _t(lang, "turnover", count=_num(lang, count))
    return {"intent": "turnover_risk", "text": text, "rows": [], "source": _src(lang, "prediction")}


def _h_employee_info(user, lang, e, scope):
    emp = None
    code = e["employee_code"]
    if code:
        emp = (
            scope.filter(employee_code__iexact=code).first()
            or scope.filter(employee_code__iexact=f"EMP-{code}").first()
            or scope.filter(employee_code__iexact=f"EMP{code}").first()
        )
    if emp is None:
        emp = _find_by_name(scope, e, lang)
    if emp is None:
        return {"intent": "employee_info", "text": _t(lang, "employee_not_found"),
                "rows": [], "source": _src(lang, "employees")}
    status = _DEP_STATUS[lang].get(emp.employment_status, str(emp.employment_status))
    text = _t(
        lang, "employee_info",
        code=emp.employee_code,
        name=_employee_name(emp, lang),
        dept=_dept_name(getattr(emp, "department", None), lang),
        position=getattr(emp.position, "name_ar", "") or "—",
        hired=_fmt_date(lang, emp.hire_date),
        status=status,
    )
    return {"intent": "employee_info", "text": text, "rows": [], "source": _src(lang, "employees")}


def _find_by_name(scope, e, lang):
    """يبحث عن موظف بالاسم (عربي/فرنسي/إنجليزي) ضمن النطاق — عملية أفضلية للرمز."""
    names = list(scope.select_related("department", "position")[:500])
    for emp in names:
        if _name_in(e, emp):
            return emp
    return None


def _name_in(e, emp) -> bool:
    code = e["employee_code"]
    if code and code.lower() in str(emp.employee_code).lower():
        return True
    for field in ("first_name_ar", "last_name_ar", "first_name_fr", "last_name_fr", "first_name_en", "last_name_en"):
        value = getattr(emp, field, "") or ""
        if value and nlp.normalize(value) in e.get("_norm", ""):
            return True
    return False


_HANDLERS = {
    "help": _h_help,
    "headcount": _h_headcount,
    "absent_today": _h_absent_today,
    "present_today": _h_present_today,
    "late_top": _h_late_top,
    "leave_pending": _h_leave_pending,
    "leave_days": _h_leave_days,
    "payroll_month": _h_payroll_month,
    "avg_salary": _h_avg_salary,
    "perf_avg": _h_perf_avg,
    "perf_top": _h_perf_top,
    "turnover_risk": _h_turnover,
    "employee_info": _h_employee_info,
    "unknown": _h_unknown,
}
