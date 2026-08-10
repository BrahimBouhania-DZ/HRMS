"""عروض الحضور — API المسح + سجلات الحضور + الاستثناءات + بطاقة QR.

المرجع: docs/06-qr-system.md §7 (API) + docs/10-roadmap.md S3.
"""

import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView, ListView, UpdateView

import qrcode

from apps.auth_app.mixins import PermissionRequiredMixin
from apps.auth_app.scopes import employee_scope_queryset
from apps.employees.qr_service import get_active_qr, get_qr_payload
from apps.employees.qr_engine import verify_payload

from .forms import AttendanceDayForm, AttendanceExceptionForm, ScanQrForm
from .models import AttendanceDay, AttendanceException, AttendanceScan
from .services import decide_and_record_scan, verify_qr_token


# ---------------------------------------------------------------------------
# 1) واجهة المسح (API) — T-QR-6
# ---------------------------------------------------------------------------

class ScanApiView(View):
    """POST /api/v1/scan/ — قبول QR وتسجيل دخول/خروج (JSON).

    السماح: مستخدم مسجّل بصلاحية attendance.scan، أو جهاز مُعرَّف
    (X-Device-Code + X-API-Key) يعمل كقارئ ثابت.

    أمان CSRF: الطلبات المعتمدة على الجلسة تُخضع للفحص؛ الأجهزة
    تستوثق بمفتاح API ولا تحمل كوكيز لذلك يُعفى المسار كليًا ثم
    يُفحص يدويًا للجلسات (الأنسب لقارئ ثابت خارجي).
    """

    @method_decorator(csrf_exempt, name="dispatch")
    def dispatch(self, request, *args, **kwargs):
        # الأجهزة (بلا جلسة/كوكيز) لا تخضع لـ CSRF — تستوثق بمفتاح API.
        # جلسات المتصفح تُفحص يدويًا هنا لأن csrf_exempt يعطّل الفحص التلقائي.
        if request.user.is_authenticated:
            from django.middleware.csrf import (
                InvalidTokenFormat,
                _check_token_format,
                _does_token_match,
            )

            token = request.headers.get("X-CSRFToken") or request.POST.get("csrfmiddlewaretoken")
            cookie = request.META.get("CSRF_COOKIE")
            if not token or not cookie:
                return JsonResponse(
                    {"ok": False, "error": _("رمز CSRF مفقود")}, status=403
                )
            try:
                _check_token_format(token)
            except InvalidTokenFormat:
                return JsonResponse(
                    {"ok": False, "error": _("رمز CSRF غير صالح")}, status=403
                )
            if not _does_token_match(token, cookie):
                return JsonResponse(
                    {"ok": False, "error": _("رمز CSRF غير متطابق")}, status=403
                )
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        form = ScanQrForm(request.POST or request.GET or {})
        if not form.is_valid():
            return JsonResponse({"ok": False, "error": _("payload مطلوب")}, status=400)

        device = None
        if not request.user.is_authenticated:
            device = self._authenticate_device(request)
            if device is None:
                return JsonResponse(
                    {"ok": False, "error": _("مصادقة الجهاز أو المستخدم مطلوبة")}, status=401
                )
        else:
            from apps.auth_app.services import has_perm
            if not has_perm(request.user, "attendance.scan"):
                return JsonResponse({"ok": False, "error": _("لا تملك صلاحية المسح")}, status=403)

        employee, qr, error = self._resolve_employee(request, form.cleaned_data["payload"])
        if error or employee is None or qr is None:
            if employee is not None:
                self._log_rejected(request, employee, device, error)
            return JsonResponse({"ok": False, "error": error or _("QR مرفوض")}, status=422)

        scan = decide_and_record_scan(
            employee,
            qr,
            source=AttendanceScan.Source.FIXED_READER if device else AttendanceScan.Source.PHONE,
            device=device,
            ip_address=self._client_ip(request),
        )
        return JsonResponse(
            {
                "ok": scan.decision != AttendanceScan.Decision.REJECTED,
                "decision": scan.decision,
                "detail": scan.result_detail,
                "employee": str(employee),
                "time": scan.scanned_at.isoformat(),
            }
        )

    def _authenticate_device(self, request):
        import hashlib
        import hmac

        from apps.devices.models import QrDevice

        code = request.headers.get("X-Device-Code")
        key = request.headers.get("X-API-Key")
        if not code or not key:
            return None
        device = QrDevice.objects.filter(device_code=code, status=QrDevice.Status.ACTIVE).first()
        if not device:
            return None
        digest = hashlib.sha256(key.encode()).hexdigest()
        if not hmac.compare_digest(digest, device.api_key_hash):
            return None
        device.last_seen = timezone.now()
        device.save(update_fields=["last_seen"])
        return device

    def _resolve_employee(self, request, payload):
        """تحقق مزدوج: التوقيع/النسخة، ثم تطابق الرمز مع الحساب (للموظف)."""
        employee, qr, error = verify_qr_token(payload)
        if employee is None:
            return None, None, error
        if request.user.is_authenticated:
            emp_profile = getattr(request.user, "employee_profile", None)
            if emp_profile is None or emp_profile.id != employee.id:
                return None, None, _("هذا الرمز لا يخص حسابك")
        return employee, qr, None

    def _log_rejected(self, request, employee, device, error):
        AttendanceScan.objects.create(
            employee=employee,
            source=AttendanceScan.Source.FIXED_READER if device else AttendanceScan.Source.PHONE,
            device=device,
            ip_address=self._client_ip(request),
            decision=AttendanceScan.Decision.REJECTED,
            qr_version=0,
            result_detail=(error or _("مرفوض"))[:200],
        )

    @staticmethod
    def _client_ip(request):
        return request.META.get("REMOTE_ADDR")


# ---------------------------------------------------------------------------
# 2) بطاقة QR (بطاقتي)
# ---------------------------------------------------------------------------

class MyQrCardView(PermissionRequiredMixin, View):
    """بطاقة الموظف: رمز QR حيّ + زر إعادة التوليد (بصلاحية employee.qr.manage)."""

    permission_code = "attendance.view"

    def get(self, request):
        emp = getattr(request.user, "employee_profile", None)
        if emp is None:
            messages.error(request, _("حسابك غير مرتبط بملف موظف"))
            return redirect("attendance:my_attendance")
        qr = get_active_qr(emp)
        payload = get_qr_payload(emp)
        can_manage = self._has_perm(request.user, "employee.qr.manage")
        return render(
            request,
            "attendance/my_qr_card.html",
            {"employee": emp, "qr": qr, "payload": payload, "can_manage": can_manage},
        )

    def post(self, request):
        if not self._has_perm(request.user, "employee.qr.manage"):
            messages.error(request, _("لا تملك صلاحية إدارة QR"))
        else:
            from apps.employees.qr_service import issue_qr
            emp = getattr(request.user, "employee_profile", None)
            if emp is None:
                messages.error(request, _("حسابك غير مرتبط بملف موظف"))
                return redirect("attendance:my_qr_card")
            issue_qr(emp, issued_by=request.user)
            messages.success(request, _("تم توليد رمز QR جديد (نسخة محدثة)"))
        return redirect("attendance:my_qr_card")

    @staticmethod
    def _has_perm(user, code):
        from apps.auth_app.services import has_perm
        return has_perm(user, code)


class QrImageForPayload(View):
    """يعرض QR كصورة PNG من نص payload (يستخدمه القالب)."""

    def get(self, request, payload):
        if verify_payload(payload) is None:
            return HttpResponse(status=404)
        img = qrcode.make(payload)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return HttpResponse(buf.getvalue(), content_type="image/png")


# ---------------------------------------------------------------------------
# 3) سجلات الحضور
# ---------------------------------------------------------------------------

class AttendanceDayListView(PermissionRequiredMixin, ListView):
    permission_code = "attendance.view"
    model = AttendanceDay
    template_name = "attendance/attendance_day_list.html"
    context_object_name = "days"
    paginate_by = 25

    def get_queryset(self):
        qs = AttendanceDay.objects.select_related("employee", "shift", "branch")
        emp_qs = employee_scope_queryset(self.request.user)
        qs = qs.filter(employee__in=emp_qs)

        date = self.request.GET.get("date")
        state = self.request.GET.get("state")
        q = self.request.GET.get("q")
        if date:
            qs = qs.filter(work_date=date)
        if state:
            qs = qs.filter(state=state)
        if q:
            qs = qs.filter(
                Q(employee__employee_code__icontains=q)
                | Q(employee__first_name_ar__icontains=q)
                | Q(employee__last_name_ar__icontains=q)
            )
        return qs.order_by("-work_date", "employee__employee_code")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["date"] = self.request.GET.get("date", "")
        ctx["state"] = self.request.GET.get("state", "")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["today"] = timezone.localdate()
        ctx["states"] = AttendanceDay.State.choices
        return ctx


class MyAttendanceView(PermissionRequiredMixin, ListView):
    """سجل الموظف الشخصي (نطاق SELF)."""

    permission_code = "attendance.view"
    template_name = "attendance/my_attendance.html"
    context_object_name = "days"
    paginate_by = 30

    def get_queryset(self):
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is None:
            return AttendanceDay.objects.none()
        return (
            AttendanceDay.objects.filter(employee=emp)
            .select_related("shift")
            .order_by("-work_date")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is not None:
            days = AttendanceDay.objects.filter(employee=emp)
            ctx["month_worked"] = sum(d.worked_minutes for d in days)
            ctx["month_late"] = sum(d.late_minutes for d in days)
            ctx["month_days"] = days.filter(state=AttendanceDay.State.PRESENT).count()
        return ctx


class AttendanceDayDetailView(PermissionRequiredMixin, DetailView):
    permission_code = "attendance.view"
    model = AttendanceDay
    template_name = "attendance/attendance_day_detail.html"
    context_object_name = "day"

    def get_queryset(self):
        emp_qs = employee_scope_queryset(self.request.user)
        return AttendanceDay.objects.filter(employee__in=emp_qs).select_related("employee", "shift")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["scans"] = self.object.scans.order_by("scanned_at")
        ctx["exceptions"] = self.object.exceptions.order_by("-from_time")
        return ctx


class AttendanceDayCorrectionView(PermissionRequiredMixin, UpdateView):
    permission_code = "attendance.correct"
    model = AttendanceDay
    form_class = AttendanceDayForm
    template_name = "attendance/attendance_day_form.html"
    context_object_name = "day"
    success_url = reverse_lazy("attendance:attendance_day_list")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, _("تم تصحيح يوم الحضور"))
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# 4) الاستثناءات
# ---------------------------------------------------------------------------

class ExceptionListView(PermissionRequiredMixin, ListView):
    """قائمة الاستثناءات ضمن النطاق (الموافقة/الرفض بصلاحية منفصلة)."""

    permission_code = "attendance.view"
    model = AttendanceException
    template_name = "attendance/exception_list.html"
    context_object_name = "exceptions"
    paginate_by = 25

    def get_queryset(self):
        qs = AttendanceException.objects.select_related(
            "employee", "attendanceday", "requested_by"
        )
        emp_qs = employee_scope_queryset(self.request.user)
        return qs.filter(employee__in=emp_qs).order_by("-from_time")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuses"] = AttendanceException.Status.choices
        return ctx


class ExceptionCreateView(PermissionRequiredMixin, CreateView):
    permission_code = "attendance.scan"
    model = AttendanceException
    form_class = AttendanceExceptionForm
    template_name = "attendance/exception_form.html"
    success_url = reverse_lazy("attendance:exception_list")

    def get_initial(self):
        initial = super().get_initial()
        now = timezone.now()
        initial.setdefault("from_time", now)
        initial.setdefault("to_time", now)
        return initial

    def form_valid(self, form):
        emp = getattr(self.request.user, "employee_profile", None)
        if emp is None:
            messages.error(self.request, _("حسابك غير مرتبط بملف موظف"))
            return redirect("attendance:exception_list")
        form.instance.employee = emp
        form.instance.requested_by = self.request.user
        messages.success(self.request, _("أُرسل طلب الاستثناء للمراجعة"))
        return super().form_valid(form)


class ExceptionApproveView(PermissionRequiredMixin, View):
    permission_code = "attendance.exception.manage"

    def post(self, request, pk, action):
        exception = get_object_or_404(AttendanceException, pk=pk)
        if action == "approve":
            exception.status = AttendanceException.Status.APPROVED
            exception.approved_by = request.user
            messages.success(request, _("تم اعتماد الاستثناء"))
        elif action == "reject":
            exception.status = AttendanceException.Status.REJECTED
            exception.approved_by = request.user
            messages.warning(request, _("تم رفض الاستثناء"))
        else:
            messages.error(request, _("إجراء غير معروف"))
            return redirect("attendance:exception_list")
        exception.updated_by = request.user
        exception.save()
        return redirect("attendance:exception_list")
