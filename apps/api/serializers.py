"""محوِّلات بيانات واجهة API للموبايل (serializers)."""

from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.attendance.models import AttendanceDay
from apps.employees.models import Employee


class LoginSerializer(serializers.Serializer):
    """اسم مستخدم + كلمة مرور → موظف (يمنع تسجيل دخول غير الموظفين)."""

    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            username=attrs.get("username"),
            password=attrs.get("password"),
        )
        if user is None:
            raise serializers.ValidationError(_("بيانات الدخول غير صحيحة"))
        if not user.is_active:
            raise serializers.ValidationError(_("الحساب معطّل"))
        employee = getattr(user, "employee_profile", None)
        if employee is None:
            raise serializers.ValidationError(
                _("لا يملك هذا الحساب ملف موظف (واجهة الموبايل للموظفين)")
            )
        attrs["user"] = user
        attrs["employee"] = employee
        return attrs


class EmployeeProfileSerializer(serializers.ModelSerializer):
    """ملف الموظف + الرمز النشط + حالة اليوم."""

    full_name_ar = serializers.SerializerMethodField()
    qr_payload = serializers.SerializerMethodField()
    branch = serializers.StringRelatedField()
    department = serializers.StringRelatedField()
    position = serializers.StringRelatedField()
    today = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id",
            "employee_code",
            "full_name_ar",
            "first_name_ar",
            "last_name_ar",
            "first_name_fr",
            "last_name_fr",
            "first_name_en",
            "last_name_en",
            "phone",
            "email",
            "photo",
            "employment_status",
            "branch",
            "department",
            "position",
            "qr_payload",
            "today",
        ]

    def get_full_name_ar(self, obj):
        return f"{obj.first_name_ar} {obj.last_name_ar}"

    def get_qr_payload(self, obj):
        from apps.employees.qr_service import get_qr_payload

        return get_qr_payload(obj)

    def get_today(self, obj):
        from django.utils import timezone

        from apps.attendance.models import AttendanceDay

        today = timezone.localdate()
        day = AttendanceDay.objects.filter(employee=obj, work_date=today).first()
        if day is None:
            return None
        return {
            "work_date": day.work_date,
            "state": day.state,
            "check_in": day.check_in,
            "check_out": day.check_out,
            "worked_minutes": day.worked_minutes,
            "late_minutes": day.late_minutes,
        }


class AttendanceDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceDay
        fields = [
            "work_date",
            "state",
            "check_in",
            "check_out",
            "worked_minutes",
            "late_minutes",
            "early_minutes",
            "overtime_minutes",
            "is_corrected",
        ]


class ScanResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    decision = serializers.CharField()
    detail = serializers.CharField()
    employee = serializers.CharField()
    time = serializers.DateTimeField()
