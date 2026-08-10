"""نماذج إدخال الموظفين."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Employee


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "employee_code", "first_name_ar", "last_name_ar",
            "first_name_fr", "last_name_fr",
            "first_name_en", "last_name_en",
            "gender", "birth_date", "phone", "email", "address",
            "hire_date", "employment_status",
            "branch", "department", "position", "shift",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
        }
