"""عروض الإشعارات — مركز الإشعارات + القراءة (S4).

المرجع: docs/03 §3.9 + docs/04 §4.12 (مركز الإشعارات).
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView

from .models import Notification
from .services import mark_all_as_read, mark_as_read


class NotificationListView(LoginRequiredMixin, ListView):
    """مركز الإشعارات — كل مستخدم يرى إشعاراته فقط."""

    model = Notification
    template_name = "notif/list.html"
    context_object_name = "notifications"
    paginate_by = 30

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["unread_total"] = self.get_queryset().filter(is_read=False).count()
        return ctx


class NotificationMarkReadView(LoginRequiredMixin, View):
    """تعليم إشعار كمقروء (POST)."""

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        next_url = request.POST.get("next") or reverse_lazy("notif:list")
        return redirect(next_url)


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    """تعليم كل الإشعارات كمقروءة (POST)."""

    def post(self, request):
        mark_all_as_read(request.user)
        messages.success(request, _("عُلمت جميع الإشعارات كمقروءة"))
        return redirect(reverse_lazy("notif:list"))
