"""عروض الذكاء الاصطناعي — لوحة تنبؤات المخاطر + المساعد الذكي + تحليلات (قراءة فقط).

الصلاحيات: ai.analytics.view (التنبؤات/التحليلات) و ai.assistant.use (المساعد).
- المساعد: كل إجابة تُسجَّل في ai_aiquery؛ التقييم (نعم/لا) يحسّن حلقة التعلم.
- لا تُتخذ قرارات إدارية آلية؛ كل مخرجات تحليلية تُعرض على مسؤول بشري.
"""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.ai import assistant, services
from apps.ai.models import AIPrediction, AIQuery
from apps.auth_app.mixins import PermissionRequiredMixin

QUICK_QUESTIONS = {
    "ar": [
        "كم موظفًا في الشركة؟",
        "كم موظفًا غائبًا اليوم؟",
        "ما هي الأقسام الأكثر تأخرًا هذا الشهر؟",
        "كم طلب إجازة معلق؟",
        "كم تبلغ كتلة أجور هذا الشهر؟",
        "ما متوسط درجات التقييم؟",
        "من هم أفضل 5 موظفين أداءً؟",
        "كم عدد الموظفين بمخاطر استقالة مرتفعة؟",
    ],
    "fr": [
        "Combien d'employés dans l'entreprise ?",
        "Combien d'absents aujourd'hui ?",
        "Quels services sont les plus en retard ce mois-ci ?",
        "Combien de congés en attente ?",
        "Quelle est la masse salariale de ce mois ?",
        "Quel est le score moyen d'évaluation ?",
        "Qui sont les 5 meilleurs employés ?",
        "Combien d'employés à risque de départ élevé ?",
    ],
    "en": [
        "How many employees in the company?",
        "How many employees are absent today?",
        "Which departments are most late this month?",
        "How many pending leave requests?",
        "What is this month's payroll total?",
        "What is the average review score?",
        "Who are the top 5 performers?",
        "How many employees at high turnover risk?",
    ],
}


class PredictionListView(PermissionRequiredMixin, ListView):
    permission_code = "ai.analytics.view"
    template_name = "ai/prediction_list.html"
    context_object_name = "predictions"

    def get_queryset(self):
        qs = services.latest_predictions(AIPrediction.Type.RESIGNATION)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                employee__employee_code__icontains=q
            ) | qs.filter(employee__first_name_ar__icontains=q) | qs.filter(employee__last_name_ar__icontains=q)
        level = self.request.GET.get("level", "").strip()
        if level in ("low", "medium", "high"):
            qs = qs.filter(level=level)
        return qs.order_by("-probability")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["model"] = services.model_status(AIPrediction.Type.RESIGNATION)
        context["trained"] = context["model"] is not None
        return context


class RefreshPredictionsView(PermissionRequiredMixin, View):
    permission_code = "ai.analytics.view"

    def post(self, request):
        try:
            updated = services.refresh_predictions(AIPrediction.Type.RESIGNATION)
            messages.success(request, _("حُدّثت التنبؤات (%(n)s موظفًا)") % {"n": updated})
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect(reverse("ai:predictions"))


class AssistantView(PermissionRequiredMixin, TemplateView):
    permission_code = "ai.assistant.use"
    template_name = "ai/assistant.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        prompt = self.request.GET.get("q", "").strip()
        if prompt:
            answer = assistant.answer_question(self.request.user, prompt)
            context["answer"] = answer
            context["query_id"] = services.latest_query_id(self.request.user)
        context["quick_questions"] = QUICK_QUESTIONS
        context["recent"] = services.recent_queries(self.request.user)[:10]
        return context


class AnalyticsDashboardView(PermissionRequiredMixin, TemplateView):
    """لوحة تحليلات KPI — حضرة/غياب/رواتب/أداء/إجازات/مخاطر (قراءة فقط).

    يختار المحلل الفترة، تُحسب النتائج لحظيًا عبر analytics.run_all (مقيدة
    بالنطاق) وتُسجَّل في ai_analyticsjob للتدقيق.
    """

    permission_code = "ai.analytics.view"
    template_name = "ai/analytics.html"

    PERIODS = ("month", "year")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = self.request.GET.get("period", "month")
        if period not in self.PERIODS:
            period = "month"
        context["period"] = period
        context["periods"] = self.PERIODS
        from apps.ai import analytics

        results = analytics.run_all(self.request.user, period)
        context["results"] = results
        context["analytics_job_id"] = analytics.save_analytics_job(
            self.request.user, "kpi_dashboard", {
                k: {"kpis": v["kpis"]} for k, v in results.items()
            }, period=period,
        )
        context["unknown_queries"] = services.unknown_queries(limit=20)
        return context


class FeedbackView(PermissionRequiredMixin, View):
    """حلقة تعلم المساعد: تقييم إجابة (مفيدة/غير مفيدة) — قراءة النتيجة وتحديث الحقل.

    القواعد:
    - المستخدم يقيم سؤالًا **خاصًا به فقط** (لا يقيم أسئلة غيره).
    - القيمة المنطقية تُخزَّن في ai_aiquery.was_helpful → تُحلَّل لاحقًا لتحسين
      القاموس والنتائج (أنماط "unknown" تُجمع عبر استعلام منفصل).
    """

    permission_code = "ai.assistant.use"

    def post(self, request):
        query_id = request.POST.get("query_id")
        value = request.POST.get("value")
        try:
            query = AIQuery.objects.get(id=query_id, user=request.user)
        except (AIQuery.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"ok": False, "error": "not_found"}, status=404)
        query.was_helpful = True if value in ("1", "true", "yes") else False
        query.save(update_fields=["was_helpful"])
        return JsonResponse({"ok": True})
