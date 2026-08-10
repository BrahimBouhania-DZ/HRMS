"""نماذج الحضور — API مسح QR + سجلات الحضور.

المرجع: docs/06-qr-system.md §7 (API) — القرارات والتحقق هنا.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.employees.models import Employee

from .models import AttendanceDay, AttendanceException


class ScanQrForm(forms.Form):
    """جسم طلب POST /api/v1/scan/."""

    payload = forms.CharField(label=_("نص QR"), max_length=512)

    def clean_payload(self):
        payload = (self.cleaned_data.get("payload") or "").strip()
        if not payload:
            raise forms.ValidationError(_("حقل payload مطلوب"))
        return payload


class AttendanceDayForm(forms.ModelForm):
    """تصحيح يوم حضور (T-019) — صلاحية attendance.correct."""

    class Meta:
        model = AttendanceDay
        fields = [
            "work_date", "shift", "branch", "state",
            "check_in", "check_out",
            "worked_minutes", "late_minutes", "early_minutes", "overtime_minutes",
        ]
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date"}),
            "check_in": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "check_out": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["state"].disabled = self.instance.is_corrected

    def save(self, commit=True):
        day = super().save(commit=False)
        day.is_corrected = True
        if commit:
            day.save()
        return day


class AttendanceExceptionForm(forms.ModelForm):
    """طلب استثناء (إذن/مأمورية/تعويض) — docs §5."""

    class Meta:
        model = AttendanceException
        fields = ["type", "from_time", "to_time", "hours", "reason"]
        widgets = {
            "from_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "to_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean(self):
        cleaned = super().clean()
        frm, to = cleaned.get("from_time"), cleaned.get("to_time")
        if frm and to and to <= frm:
            self.add_error("to_time", _("نهاية الفترة يجب أن تكون بعد بدايتها"))
        return cleaned

    def save(self, commit=True):
        exc = super().save(commit=False)
        exc.status = AttendanceException.Status.PENDING
        if commit:
            exc.save()
        return exc
