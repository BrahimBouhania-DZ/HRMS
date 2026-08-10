"""نماذج الإجازات (S4)."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import LeaveRequest, LeaveType, PublicHoliday


class LeaveRequestForm(forms.ModelForm):
    """طلب إجازة — الحقل أيام يظهر فقط (قراءة) بعد الحساب."""

    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "from_date", "to_date", "reason"]
        widgets = {
            "from_date": forms.DateInput(attrs={"type": "date"}),
            "to_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["leave_type"].queryset = LeaveType.objects.filter(is_active=True)
        self.fields["leave_type"].label = _("نوع الإجازة")

    def clean(self):
        cleaned = super().clean()
        frm, to = cleaned.get("from_date"), cleaned.get("to_date")
        if frm and to and to < frm:
            self.add_error("to_date", _("نهاية الإجازة يجب أن تكون بعد بدايتها"))
        return cleaned


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = [
            "code", "name_ar", "name_fr", "name_en", "days_per_year",
            "carryover_allowed", "max_carryover_days", "is_unpaid",
            "requires_approval_levels", "applicable_to", "is_active",
        ]


class PublicHolidayForm(forms.ModelForm):
    class Meta:
        model = PublicHoliday
        fields = ["branch", "date", "name_ar", "name_fr", "name_en", "is_recurring"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


class BalanceAdjustForm(forms.Form):
    """تسوية رصيد (leave.balance.adjust)."""

    amount = forms.DecimalField(
        label=_("مقدار التسوية (+/-)"),
        max_digits=5,
        decimal_places=1,
    )
    reason = forms.CharField(label=_("السبب"), widget=forms.Textarea, required=False)
