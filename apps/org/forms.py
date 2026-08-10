"""نماذج إدخال الهيكل التنظيمي."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Branch, Department, Position, Shift


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ["code", "name_ar", "name_fr", "name_en", "country", "city", "address", "timezone"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
        }


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["code", "branch", "parent", "name_ar", "name_fr", "name_en"]
        widgets = {"parent": forms.Select(attrs={"class": "form-select"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Department.objects.none()
        if self.instance and self.instance.pk:
            self.fields["parent"].queryset = Department.objects.exclude(pk=self.instance.pk)
        elif "branch" in self.data:
            self.fields["parent"].queryset = Department.objects.filter(
                branch_id=self.data.get("branch")
            )


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ["code", "name_ar", "name_fr", "name_en", "department", "grade"]


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = ["code", "name_ar", "name_fr", "name_en", "start_time", "end_time", "is_flexible", "grace_minutes"]
