"""عروض إدارة قارئات QR — قائمة + تسجيل + حالة + تفاصيل (S6)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from apps.auth_app.mixins import PermissionRequiredMixin

from .models import QrDevice
from .services import register_device, set_device_status


class DeviceListView(PermissionRequiredMixin, ListView):
    permission_code = "device.manage"
    template_name = "devices/device_list.html"
    context_object_name = "devices"

    def get_queryset(self):
        return QrDevice.objects.select_related("branch").order_by("device_code")


class DeviceCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "device.manage"
    template_name = "devices/device_form.html"
    model = QrDevice
    fields = ["device_code", "branch", "location"]
    success_url = reverse_lazy("devices:list")

    def form_valid(self, form):
        device, api_key = register_device(
            device_code=form.cleaned_data["device_code"],
            branch=form.cleaned_data["branch"],
            user=self.request.user,
            location=form.cleaned_data.get("location", ""),
        )
        messages.success(
            self.request,
            _("تم تسجيل الجهاز %(code)s.") % {"code": device.device_code},
        )
        self.request.session[f"device_key_{device.pk}"] = api_key
        return redirect(reverse_lazy("devices:detail", args=[device.pk]))


class DeviceDetailView(PermissionRequiredMixin, DetailView):
    permission_code = "device.manage"
    template_name = "devices/device_detail.html"
    context_object_name = "device"
    model = QrDevice

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["audit_logs"] = self.object.audit_logs.select_related("created_by").order_by("-created_at")[:20]
        ctx["shown_api_key"] = self.request.session.pop(f"device_key_{self.object.pk}", None)
        return ctx


class DeviceStatusView(PermissionRequiredMixin, View):
    permission_code = "device.manage"

    def post(self, request, pk, status):
        device = get_object_or_404(QrDevice, pk=pk)
        if status not in ("active", "inactive", "maintenance"):
            messages.error(request, _("حالة غير صالحة"))
            return redirect(reverse_lazy("devices:list"))
        set_device_status(device, status, request.user)
        messages.success(
            request,
            _("أصبح الجهاز %(status)s.") % {"status": device.get_status_display()},
        )
        return redirect(reverse_lazy("devices:detail", args=[pk]))
