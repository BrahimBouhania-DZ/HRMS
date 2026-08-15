"""نماذج التوظيف — إعلان + مرشح + مقابلة."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Candidate, Interview, JobPosting


class PostingForm(forms.ModelForm):
    class Meta:
        model = JobPosting
        fields = [
            "code", "title_ar", "title_fr", "title_en",
            "department", "branch", "employment_type", "openings_count",
            "requirements", "description", "status", "publish_date", "close_date",
        ]
        widgets = {
            "requirements": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "publish_date": forms.DateInput(attrs={"type": "date"}),
            "close_date": forms.DateInput(attrs={"type": "date"}),
        }


class CandidateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = [
            "posting", "first_name_ar", "last_name_ar", "first_name_fr", "last_name_fr",
            "first_name_en", "last_name_en", "email", "phone", "source", "status", "resume", "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = ["interviewer", "scheduled_at", "mode", "score", "notes"]
        widgets = {
            "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["score"].required = False
