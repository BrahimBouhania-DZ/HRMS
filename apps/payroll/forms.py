"""نماذج الرواتب (v2)."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import PayElement, PayRun


class PayElementForm(forms.ModelForm):
    class Meta:
        model = PayElement
        fields = ["code", "name_ar", "name_fr", "name_en", "kind", "calculation", "amount", "percent", "applies_to_all", "is_active"]
        labels = {
            "code": _("الرمز"), "name_ar": _("الاسم (عربي)"), "name_fr": _("الاسم (فرنسي)"),
            "name_en": _("الاسم (إنجليزي)"), "kind": _("النوع"), "calculation": _("طريقة الحساب"),
            "amount": _("المبلغ"), "percent": _("النسبة %"), "applies_to_all": _("يطبق على الجميع"),
            "is_active": _("نشط"),
        }


class PayRunGenerateForm(forms.Form):
    """توليد دورة رواتب لفترة وفرع."""

    period_code = forms.CharField(
        label=_("فترة الرواتب (مثال: 2026-08)"),
        max_length=10,
        widget=forms.TextInput(attrs={"placeholder": "2026-08"}),
    )
    branch = forms.ModelChoiceField(label=_("الفرع"), queryset=None)

    def __init__(self, *args, **kwargs):
        branches = kwargs.pop("branches", None)
        super().__init__(*args, **kwargs)
        if branches is not None:
            self.fields["branch"].queryset = branches

    def clean_period_code(self):
        value = (self.cleaned_data.get("period_code") or "").strip()
        try:
            year, month = (int(x) for x in value.split("-"))
            if not (1 <= month <= 12 and year >= 2000):
                raise ValueError
        except (ValueError, AttributeError):
            raise forms.ValidationError(_("صيغة الفترة غير صالحة — مثال: 2026-08"))
        return value
