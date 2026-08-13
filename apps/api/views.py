"""واجهة API للموبايل والأجهزة (REST Framework) — مسارات JSON.

النطاق /api/v1/:
  POST auth/login/          → رمز (Token) + ملف الموظف
  POST auth/logout/         → إبطال الرمز
  POST scan/                → مسح QR (موظف برمز Token أو جهاز بمفتاح API)
  GET  me/                  → ملفي + رمز QR النشط + حالة اليوم
  GET  me/attendance/       → أيام حضوري (نطاق from/to اختياري)

المصادقة: Token للموظفين، أو DeviceKey (X-Device-Code + X-API-Key) للأجهزة.
"""

from datetime import datetime

from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.authentication import DeviceKeyAuth, DeviceKeyAuthentication
from apps.attendance.forms import ScanQrForm
from apps.attendance.models import AttendanceScan
from apps.attendance.services import decide_and_record_scan, verify_qr_token
from apps.auth_app.services import has_perm

from .serializers import (
    AttendanceDaySerializer,
    EmployeeProfileSerializer,
    LoginSerializer,
    ScanResponseSerializer,
)


def _employee_profile(user):
    return getattr(user, "employee_profile", None)


class LoginView(ObtainAuthToken):
    """POST /api/v1/auth/login/ — {username, password} → {token, profile}."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.validated_data["employee"]
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "employee": EmployeeProfileSerializer(employee, context={"request": request}).data,
            }
        )


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — يبطل رمز المصادقة الحالي."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"ok": True})


class ScanView(APIView):
    """POST /api/v1/scan/ — {payload} → قرار الدخول/الخروج.

    المصادقة: جهاز نشط (ترويسات) أو موظف مسجّل بصلاحية attendance.scan.
    الموظف يمسح رمز نفسه فقط (حماية من استعمال رموز الآخرين).
    """

    authentication_classes = [DeviceKeyAuthentication, TokenAuthentication, SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        form = ScanQrForm(request.data or {})
        if not form.is_valid():
            return Response({"ok": False, "error": _("payload مطلوب")}, status=status.HTTP_400_BAD_REQUEST)

        device = None
        if isinstance(request.auth, DeviceKeyAuth):
            device = request.auth.device
        elif request.user.is_authenticated:
            if not has_perm(request.user, "attendance.scan"):
                return Response(
                    {"ok": False, "error": _("لا تملك صلاحية المسح")},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if _employee_profile(request.user) is None:
                return Response(
                    {"ok": False, "error": _("لا يملك الحساب ملف موظف")},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            return Response(
                {"ok": False, "error": _("مصادقة الجهاز أو المستخدم مطلوبة")},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        employee, qr, error = self._resolve_employee(request, form.cleaned_data["payload"], device)
        if employee is None or qr is None:
            return Response(
                {"ok": False, "error": error or _("QR مرفوض")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        scan = decide_and_record_scan(
            employee,
            qr,
            source=AttendanceScan.Source.FIXED_READER if device else AttendanceScan.Source.PHONE,
            device=device,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(
            ScanResponseSerializer(
                {
                    "ok": scan.decision != AttendanceScan.Decision.REJECTED,
                    "decision": scan.decision,
                    "detail": scan.result_detail,
                    "employee": str(employee),
                    "time": scan.scanned_at,
                }
            ).data
        )

    def _resolve_employee(self, request, payload, device):
        """تحقق مزدوج: توقيع/نسخة الرمز ثم (للموظف) تطابقه مع حساب المسامح."""
        employee, qr, error = verify_qr_token(payload)
        if employee is None or qr is None:
            return None, None, error
        if device is None and request.user.is_authenticated:
            me = _employee_profile(request.user)
            if me is None or me.id != employee.id:
                return None, None, _("هذا الرمز لا يخص حسابك")
        return employee, qr, None


class MeView(APIView):
    """GET /api/v1/me/ — ملف الموظف + رمز QR النشط + حالة اليوم."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee = _employee_profile(request.user)
        if employee is None:
            return Response(
                {"error": _("لا يملك الحساب ملف موظف")}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(EmployeeProfileSerializer(employee, context={"request": request}).data)


class MyAttendanceView(APIView):
    """GET /api/v1/me/attendance/?from=YYYY-MM-DD&to=YYYY-MM-DD — أيام حضوري."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee = _employee_profile(request.user)
        if employee is None:
            return Response(
                {"error": _("لا يملك الحساب ملف موظف")}, status=status.HTTP_404_NOT_FOUND
            )
        qs = employee.attendance_days.all()
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")
        try:
            if date_from:
                qs = qs.filter(work_date__gte=datetime.strptime(date_from, "%Y-%m-%d").date())
            if date_to:
                qs = qs.filter(work_date__lte=datetime.strptime(date_to, "%Y-%m-%d").date())
        except ValueError:
            return Response(
                {"error": _("صيغة التاريخ YYYY-MM-DD")}, status=status.HTTP_400_BAD_REQUEST
            )
        qs = qs.order_by("-work_date")[:90]
        return Response(AttendanceDaySerializer(qs, many=True).data)
