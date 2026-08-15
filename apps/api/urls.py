"""مسارات واجهة API للموبايل (REST Framework)."""

from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="api_login"),
    path("auth/logout/", views.LogoutView.as_view(), name="api_logout"),
    path("scan/", views.ScanView.as_view(), name="api_scan"),
    path("me/", views.MeView.as_view(), name="api_me"),
    path("me/attendance/", views.MyAttendanceView.as_view(), name="api_my_attendance"),
    path("recruitment/postings/", views.PostingListAPIView.as_view(), name="api_recruitment_postings"),
    path("recruitment/postings/<int:pk>/", views.PostingDetailAPIView.as_view(), name="api_recruitment_posting_detail"),
    path("recruitment/candidates/", views.CandidateListAPIView.as_view(), name="api_recruitment_candidates"),
]
