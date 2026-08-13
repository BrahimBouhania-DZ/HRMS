"""عروض الذكاء الاصطناعي — لوحة تنبؤات المخاطر (قراءة فقط).

الصلاحية: ai.analytics.view. لا توجد أي عملية كتابة هنا إلا تحديث التنبؤات
يدويًا (POST مع مصادقة) — ولا تُتخذ قرارات إدارية آلية.
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView

from apps.ai import services
from apps.ai.models import AIPrediction
from apps.auth_app.mixins import PermissionRequiredMixin


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
