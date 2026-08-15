"""روابط التوظيف (namespace: recruitment)."""

from django.urls import path

from .views import (
    CandidateCreateView,
    CandidateDetailView,
    CandidateHireView,
    CandidateListView,
    CandidateStatusView,
    ImportTemplateView,
    ImportView,
    InterviewCompleteView,
    InterviewScheduleView,
    PostingCloseView,
    PostingCreateView,
    PostingDetailView,
    PostingListView,
    PostingPublishView,
    PostingUpdateView,
)

app_name = "recruitment"

urlpatterns = [
    path("", PostingListView.as_view(), name="posting_list"),
    path("postings/new/", PostingCreateView.as_view(), name="posting_create"),
    path("postings/<int:pk>/", PostingDetailView.as_view(), name="posting_detail"),
    path("postings/<int:pk>/edit/", PostingUpdateView.as_view(), name="posting_edit"),
    path("postings/<int:pk>/publish/", PostingPublishView.as_view(), name="posting_publish"),
    path("postings/<int:pk>/close/", PostingCloseView.as_view(), name="posting_close"),
    path("candidates/", CandidateListView.as_view(), name="candidate_list"),
    path("candidates/new/", CandidateCreateView.as_view(), name="candidate_create"),
    path("candidates/<int:pk>/", CandidateDetailView.as_view(), name="candidate_detail"),
    path("candidates/<int:pk>/status/<str:status>/", CandidateStatusView.as_view(), name="candidate_status"),
    path("candidates/<int:pk>/hire/", CandidateHireView.as_view(), name="candidate_hire"),
    path("candidates/<int:pk>/interviews/new/", InterviewScheduleView.as_view(), name="interview_create"),
    path("candidates/<int:pk>/interviews/<int:interview_pk>/complete/", InterviewCompleteView.as_view(), name="interview_complete"),
    path("import/", ImportView.as_view(), name="import"),
    path("import/template/<str:entity>/", ImportTemplateView.as_view(), name="import_template"),
]
