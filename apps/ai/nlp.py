"""طبقة فهم اللغة الطبيعية للمساعد الذكي (NL Pipeline) — T-AI-2.

المرجع: docs/07-ai-module.md §4.2 (قبل §4.3: استعلامات معلمة).
محرك قواعد/قالب (Template NL) — بدون LLM وبدون إنترنت وبدون بناء SQL من النص:
    normalize() → detect_language() → detect_intent() → extract_entities()

كل نص يُوحَّد أولًا (عربي/فرنسي/إنجليزي + أرقام)، ثم يُصنَّف الهدف (Intent)
بالكلمات المفتاحية للغة المكتشفة، ثم تُستخرج الكيانات (قسم/فرع/موظف/فترة/كمية).
"""

import re
import unicodedata

from django.utils import timezone

LANGS = ("ar", "fr", "en")
DEFAULT_LANG = "ar"

_AR_SCRIPT = re.compile(r"[\u0600-\u06FF]")
_DIACRITICS = re.compile(r"[\u064B-\u0652\u0640]")
_AR_TRANS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})
_FR_ACCENTS = {
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "à": "a", "â": "a", "ä": "a",
    "ô": "o", "ö": "o", "î": "i", "ï": "i",
    "û": "u", "ü": "u", "ù": "u", "ç": "c",
}

MONTHS = {
    1: ["janvier", "january", "jan", "يناير", "جانفي"],
    2: ["fevrier", "february", "fev", "فبراير", "فيفري"],
    3: ["mars", "march", "مارس"],
    4: ["avril", "april", "أفريل", "افريل", "ابريل"],
    5: ["mai", "may", "ماي", "مايو"],
    6: ["juin", "june", "يونيو", "جوان"],
    7: ["juillet", "july", "يوليو", "جويلية"],
    8: ["aout", "august", "أوت", "اوت", "أغسطس", "اغسطس"],
    9: ["septembre", "september", "سبتمبر"],
    10: ["octobre", "october", "اكتوبر"],
    11: ["novembre", "november", "نوفمبر"],
    12: ["decembre", "december", "ديسمبر", "ديسمب"],
}

# --------------------------------------------------------------------- توحيد


def normalize(text: str) -> str:
    """توحيد النص: حروف عربية/فرنسية + تشكيل + مسافات → نص صغير موحّد."""
    s = unicodedata.normalize("NFKC", text or "").strip().lower()
    s = _DIACRITICS.sub("", s)
    s = s.translate(_AR_TRANS)
    for ch, rep in _FR_ACCENTS.items():
        s = s.replace(ch, rep)
    s = s.replace("’", "'").replace("`", "'")
    s = re.sub(r"\s+", " ", s)
    return s


# --------------------------------------------------------------------- لغة


_LANG_MARKERS = {
    "ar": [
        "كم", "كيف", "هل", "ماذا", "ما", "الموظف", "موظف", "غائب", "حاضر",
        "غياب", "حضور", "إجازة", "اجازة", "رواتب", "راتب", "قسم", "فرع",
        "تقييم", "اليوم", "هذا الشهر", "أعلى", "اكثر", "الشركة", "تنبؤ",
    ],
    "fr": [
        "combien", "comment", "quel", "quelle", "aujourd", "mois", "employe",
        "employes", "absent", "present", "absence", "presence", "conge",
        "salaire", "service", "evaluation", "meilleurs", "top", "risque",
    ],
    "en": [
        "how", "many", "what", "which", "employee", "employees", "absent",
        "present", "absence", "attendance", "leave", "salary", "department",
        "review", "today", "month", "top", "best", "turnover", "risk",
    ],
}


def detect_language(text: str, hint: str = DEFAULT_LANG) -> str:
    """يكتشف لغة السؤال. الحروف العربية علامة حاسمة؛ وإلا يعتمد على الكلمات."""
    if _AR_SCRIPT.search(text):
        return "ar"
    norm = normalize(text)
    scores = {
        lang: sum(1 for marker in markers if marker in norm)
        for lang, markers in _LANG_MARKERS.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return hint if hint in LANGS else DEFAULT_LANG
    return best


# --------------------------------------------------------------------- هدف


INTENTS = {
    "help": {
        "ar": ["ماذا يمكنك", "ماذا تستطيع", "ساعدني", "تساعدني", "قدراتك", "مساعدة"],
        "fr": ["que peux", "que fais", "tu peux", "aides-moi", "aide moi"],
        "en": ["what can you", "what do you do", "help me", "your abilities", "assistant"],
    },
    "headcount": {
        "ar": ["كم موظف", "عدد الموظفين", "عدد العمال", "عدد العاملين"],
        "fr": ["combien d'employes", "nombre d'employes", "effectif"],
        "en": ["how many employees", "number of employees", "headcount", "total employees", "total staff"],
    },
    "absent_today": {
        "ar": ["غائب اليوم", "الغائبون اليوم", "كم غائب", "عدد الغائبين", "كم غائبا اليوم", "عدد الغائبين اليوم"],
        "fr": ["absent aujourd", "absents aujourd", "combien d'absents", "absence aujourd"],
        "en": ["absent today", "absentees today", "how many absent", "absent now"],
    },
    "present_today": {
        "ar": ["حاضر اليوم", "الحاضرون اليوم", "كم حاضر", "عدد الحاضرين"],
        "fr": ["present aujourd", "presents aujourd", "combien de presents"],
        "en": ["present today", "how many present", "in attendance today"],
    },
    "late_top": {
        "ar": ["اكثر الاقسام تاخرا", "أكثر الأقسام تأخرا", "تاخر هذا الشهر", "اكثر الموظفين تاخرا", "اكثر المتاخرين", "اعلى تاخر"],
        "fr": ["plus de retard", "plus tardifs", "les retards", "en retard ce mois", "retards du mois"],
        "en": ["most late", "most tardy", "lateness", "tardiness", "late this month", "most delays"],
    },
    "leave_pending": {
        "ar": ["طلبات الاجازة", "اجازة معلقة", "اجازات معلقة", "طلبات قيد الموافقة", "انتظار الموافقة"],
        "fr": ["conge en attente", "conges en attente", "demandes de conge", "en attente d'approbation"],
        "en": ["pending leave", "leave requests pending", "requests awaiting approval", "pending requests"],
    },
    "leave_days": {
        "ar": ["ايام الاجازة", "عدد ايام الاجازة", "رصيد الاجازة", "اجازة معتمدة", "الاجازات المعتمدة"],
        "fr": ["jours de conge", "soldes de conge", "conge approuve", "conges approuves"],
        "en": ["leave days", "vacation days", "leave balance", "approved leave"],
    },
    "payroll_month": {
        "ar": ["كتلة الاجور", "اجمالي الرواتب", "مجموع الرواتب", "رواتب الشهر", "قسائم الرواتب", "اجمالي الاجور"],
        "fr": ["masse salariale", "total des salaires", "bulletins de paie", "paie du mois", "salaires du mois"],
        "en": ["payroll", "total salary", "total salaries", "wages", "payslips", "salary total", "salary bill"],
    },
    "avg_salary": {
        "ar": ["متوسط الراتب", "متوسط الاجور", "متوسط الاجر", "متوسط الرواتب"],
        "fr": ["salaire moyen", "moyenne des salaires", "salaire moyen des employes"],
        "en": ["average salary", "average wage", "avg salary", "average pay"],
    },
    "perf_avg": {
        "ar": ["متوسط التقييم", "متوسط الدرجات", "متوسط درجات التقييم", "مستوى الاداء", "متوسط الاداء"],
        "fr": ["evaluation moyenne", "score moyen", "moyenne des evaluations", "performance moyenne"],
        "en": ["average review", "average score", "average rating", "average performance"],
    },
    "perf_top": {
        "ar": ["افضل الموظفين", "اعلى التقييمات", "افضل الاداء", "الافضل اداء", "افضل الاداء", "متميزين"],
        "fr": ["meilleurs employes", "meilleures evaluations", "meilleurs resultats", "meilleurs scores"],
        "en": ["top performers", "best employees", "highest rated", "best performers", "top scores"],
    },
    "turnover_risk": {
        "ar": ["احتمال استقالة", "مخاطر الاستقالة", "خطر استقالة", "سيستقيل", "تنبؤ بالاستقالة", "مخاطر المغادرة", "دوران الموظفين", "عرضة للاستقالة", "عرضة للمغادرة", "خطر المغادرة"],
        "fr": ["risque de depart", "risque de demission", "probabilite de depart", "depart probable", "turnover"],
        "en": ["turnover", "resignation risk", "risk of leaving", "attrition", "likelihood of leaving"],
    },
    "employee_info": {
        "ar": ["معلومات عن", "بيانات الموظف", "متى تعين", "من هو الموظف", "رقم الموظف"],
        "fr": ["informations sur", "infos sur", "donnees de l'employe", "qui est"],
        "en": ["information about", "info about", "details about", "who is"],
    },
}

# ترتيب الأفضلية عند تساوي الدرجات — الأهداف المحددة أولًا.
_INTENT_ORDER = [
    "turnover_risk", "employee_info", "perf_top", "perf_avg", "avg_salary",
    "payroll_month", "leave_days", "leave_pending", "absent_today", "present_today",
    "late_top", "headcount", "help",
]


def detect_intent(norm: str, lang: str) -> tuple[str, int]:
    """يرجع (intent, score). score=0 تعني هدفًا غير معروف → يطلب توضيحًا.

    المطابقة بالكلمات (word-set) بدل السلسلة الحرفية: تغطّي تنوين النصب
    (غائبًا→غائب)، وتصريفات خفيفة، وأداة التعريف، واختلاف ترتيب الكلمات.
    """
    nwords = _word_variants(norm)
    scores = {}
    for intent, keywords in INTENTS.items():
        scores[intent] = sum(1 for kw in keywords.get(lang, []) if _kw_matches(kw, nwords))
    best_score = max(scores.values())
    if best_score == 0:
        return "unknown", 0
    best = [i for i in _INTENT_ORDER if scores[i] == best_score]
    return (best[0] if best else "unknown"), best_score


def _kw_matches(kw: str, nwords: set[str]) -> bool:
    """هل كل كلمة من الكلمة المفتاحية (بعد التوحيد) حاضرة في كلمات النص؟

    "الموظفين" ∈ nwords إذا وُجد "الموظفين" أو "موظفين" (أو "الموظفين").
    """
    words = [w for w in re.findall(r"[\w']+", normalize(kw)) if len(w) >= 2]
    if not words:
        return False
    return all(bool(_word_variants(w) & nwords) for w in words)


def _word_variants(text: str) -> set[str]:
    """تنويعات كلمة/نص: الكلمة + تجريد التنوين (ا/ه) + أداة التعريف (ال).

    مثلًا: "غائبًا" → {غائبًا, غائب}؛ "الموظفين" → {الموظفين, موظفين}؛
    "peux-tu" → {peux, tu}.
    """
    out = set()
    for token in re.findall(r"[\w']+", text or ""):
        for word in token.split("-"):
            if len(word) < 2:
                continue
            out.add(word)
            if word.endswith("ا") and len(word) > 3:
                out.add(word[:-1])
            if word.endswith("ه") and len(word) > 3:
                out.add(word[:-1])
            if word.startswith("ال") and len(word) > 4:
                out.add(word[2:])
    return out


# --------------------------------------------------------------------- كيانات


def _find_month(norm: str) -> int | None:
    for month, names in MONTHS.items():
        if any(name in norm for name in names):
            return month
    return None


def _find_year(norm: str) -> int | None:
    for token in re.findall(r"(?:19|20)\d{2}", norm):
        return int(token)
    return None


def extract_entities(norm: str, lang: str, departments=None, branches=None) -> dict:
    """استخراج كيانات: قسم/فرع/موظف (رمز) / فترة (اليوم، شهر، سنة) / حدّ أعلى N.

    departments/branches: قوائم (obj) مقيدة بنطاق المستخدم — لا يُبحث خارجها.
    """
    entities = {"department": None, "branch": None, "employee_code": None,
                "period": None, "month": None, "year": None, "limit": None}

    today = timezone.localdate()
    for marker in ["اليوم", "aujourd", "today"]:
        if marker in norm:
            entities["period"] = "today"
            break
    for marker in ["هذا الشهر", "الشهر الحالي", "ce mois", "le mois en cours", "this month", "current month"]:
        if marker in norm:
            entities["period"] = "month"
            break

    month = _find_month(norm)
    year = _find_year(norm)
    if month:
        entities["month"] = month
        entities["period"] = entities["period"] or "month"
    if year:
        entities["year"] = year

    limit = None
    for marker in ["اعلى", "أعلى", "افضل", "أفضل", "اكثر", "أكثر", "meilleurs", "top", "best", "most"]:
        m = re.search(rf"{marker}\s+(\d+)", norm)
        if m:
            limit = int(m.group(1))
            break
    if limit is None:
        m = re.search(r"(\d+)\s+(اعلى|أعلى|افضل|أفضل)", norm)
        if m:
            limit = int(m.group(1))
    entities["limit"] = limit

    for dep in departments or []:
        for name in (dep.name_ar, dep.name_fr, dep.name_en):
            if name and normalize(name) and normalize(name) in norm:
                entities["department"] = dep
                break
        if entities["department"]:
            break

    for br in branches or []:
        for name in (br.name_ar, br.name_fr, br.name_en):
            if name and normalize(name) and normalize(name) in norm:
                entities["branch"] = br
                break
        if entities["branch"]:
            break

    code = re.search(r"\b(?:emp[- ]?)?(\d{3,})\b", norm)
    if code:
        entities["employee_code"] = code.group(1)

    return entities
