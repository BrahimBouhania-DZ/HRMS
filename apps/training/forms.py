"""نماذج التدريب — دورة + جلسة + تسجيل جماعي."""

from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import TrainingCourse, TrainingSession


class CourseForm(forms.ModelForm):
    cost = forms.DecimalField(required=False, max_digits=15, decimal_places=2, initial=0)

    class Meta:
        model = TrainingCourse
        fields = ["code", "title_ar", "title_fr", "title_en", "description", "category", "provider", "cost", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_cost(self):
        return self.cleaned_data.get("cost") or Decimal("0")


class SessionForm(forms.ModelForm):
    class Meta:
        model = TrainingSession
        fields = ["course", "start_date", "end_date", "trainer", "location", "capacity", "status"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("نهاية الجلسة يجب أن تكون بعد بدايتها"))
        return cleaned


class EnrollForm(forms.Form):
    """تسجيل جماعي لموظفين ضمن نطاق المستخدم في جلسة."""

    employee_ids = forms.ModelMultipleChoiceField(
        queryset=None,
        label=_("الموظفون"),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, employees=None, **kwargs):
        super().__init__(*args, **kwargs)
        if employees is not None:
            self.fields["employee_ids"].queryset = employees
