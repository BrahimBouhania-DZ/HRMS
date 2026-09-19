"""نماذج إدخال الموظفين."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Contract, Document, Employee


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "employee_code", "first_name_ar", "last_name_ar",
            "first_name_fr", "last_name_fr",
            "first_name_en", "last_name_en",
            "gender", "birth_date", "phone", "email", "address",
            "national_id", "hire_date", "employment_status",
            "branch", "department", "position", "shift",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
        }


class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = [
            "contract_number", "employee", "contract_type",
            "start_date", "end_date", "gross_salary", "base_salary",
            "allowance", "currency", "previous_contract",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["allowance"].required = False
        self.fields["currency"].required = False
        self.fields["previous_contract"].required = False


class DocumentForm(forms.ModelForm):
    MAX_FILE_MB = 10

    class Meta:
        model = Document
        fields = ["employee", "document_type", "title", "file", "issued_date", "expiry_date"]
        widgets = {
            "issued_date": forms.DateInput(attrs={"type": "date"}),
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if f and f.size > self.MAX_FILE_MB * 1024 * 1024:
            raise forms.ValidationError(
                _("حجم الملف يتجاوز الحد المسموح (%(mb)s ميغابايت)."),
                code="file_too_large",
                params={"mb": self.MAX_FILE_MB},
            )
        return f
