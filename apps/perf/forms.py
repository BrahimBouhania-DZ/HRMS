"""نماذج تقييم الأداء (v2)."""

from django import forms
from django.forms.models import BaseModelFormSet
from django.utils.translation import gettext_lazy as _

from .models import PerfCycle, PerfObjective, PerfReview, PerfTemplate, PipPlan


class PerfCycleForm(forms.ModelForm):
    class Meta:
        model = PerfCycle
        fields = ["name_ar", "name_fr", "name_en", "period_start", "period_end",
                  "self_review_deadline", "manager_review_deadline"]
        widgets = {
            "period_start": forms.DateInput(attrs={"type": "date"}),
            "period_end": forms.DateInput(attrs={"type": "date"}),
            "self_review_deadline": forms.DateInput(attrs={"type": "date"}),
            "manager_review_deadline": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("period_start"), cleaned.get("period_end")
        if start and end and end < start:
            self.add_error("period_end", _("نهاية الفترة يجب أن تكون بعد بدايتها"))
        return cleaned


class PerfTemplateForm(forms.ModelForm):
    criteria = forms.CharField(
        label=_("المعايير"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 5, "dir": "ltr",
                                     "placeholder": '[{"title": "الدقة", "weight": 50}, {"title": "الالتزام", "weight": 50}]'}),
        help_text=_("قائمة JSON من المعايير بأوزانها: [{\"title\": \"...\", \"weight\": 50}]"),
    )

    class Meta:
        model = PerfTemplate
        fields = ["name_ar", "name_fr", "name_en", "criteria", "is_active"]

    def clean_criteria(self):
        import json

        raw = self.cleaned_data.get("criteria") or ""
        raw = raw.strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise forms.ValidationError(_("صيغة JSON غير صالحة"))
        if not isinstance(data, list):
            raise forms.ValidationError(_("يجب أن تكون المعايير قائمة"))
        total = 0
        for item in data:
            if "title" not in item:
                raise forms.ValidationError(_("كل معيار يتطلب عنوانًا (title)"))
            weight = item.get("weight", 0)
            try:
                total += float(weight)
            except (TypeError, ValueError):
                raise forms.ValidationError(_("الوزن يجب أن يكون رقمًا"))
        if total != 100:
            raise forms.ValidationError(_("مجموع الأوزان يجب أن يساوي 100 (الآن: %(n)s)") % {"n": total})
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.criteria_json = self.cleaned_data["criteria"]
        if commit:
            instance.save()
        return instance


class SelfReviewForm(forms.ModelForm):
    class Meta:
        model = PerfReview
        fields = ["self_score", "self_comment"]
        labels = {"self_score": _("درجة التقييم الذاتي"), "self_comment": _("تعليقك")}


class ManagerReviewForm(forms.ModelForm):
    class Meta:
        model = PerfReview
        fields = ["manager_score", "manager_comment"]
        labels = {"manager_score": _("درجة المدير"), "manager_comment": _("تعليق المدير")}


class ObjectiveForm(forms.ModelForm):
    class Meta:
        model = PerfObjective
        fields = ["kpi_title", "weight", "target", "achieved", "score"]
        labels = {
            "kpi_title": _("عنوان الهدف/KPI"),
            "weight": _("الوزن (٪)"),
            "target": _("الهدف"),
            "achieved": _("المحقق"),
            "score": _("الدرجة (من 100)"),
        }


class _ObjectiveFormSet(BaseModelFormSet):
    """Formset بأسماء حقول ثابتة (prefix: objectives) مطابقة للقالب والطلبات."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("prefix", "objectives")
        super().__init__(*args, **kwargs)


ObjectiveFormSet = forms.modelformset_factory(
    PerfObjective,
    form=ObjectiveForm,
    formset=_ObjectiveFormSet,
    extra=3,
    can_delete=False,
)


class PipPlanForm(forms.ModelForm):
    class Meta:
        model = PipPlan
        fields = ["start_date", "end_date", "action_items", "supervisor_note"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("نهاية الخطة يجب أن تكون بعد بدايتها"))
        return cleaned
