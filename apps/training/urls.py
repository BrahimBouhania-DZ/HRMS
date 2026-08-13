"""روابط التدريب (namespace: training)."""

from django.urls import path

from .views import (
    CertificateListView,
    CourseCreateView,
    CourseListView,
    CourseUpdateView,
    EnrollmentApproveView,
    EnrollmentRejectView,
    MyCertificatesView,
    SessionCancelView,
    SessionCompleteView,
    SessionCreateView,
    SessionDetailView,
    SessionEnrollView,
    SessionListView,
)

app_name = "training"

urlpatterns = [
    path("", CourseListView.as_view(), name="course_list"),
    path("courses/new/", CourseCreateView.as_view(), name="course_create"),
    path("courses/<int:pk>/edit/", CourseUpdateView.as_view(), name="course_edit"),
    path("sessions/", SessionListView.as_view(), name="session_list"),
    path("sessions/new/", SessionCreateView.as_view(), name="session_create"),
    path("sessions/<int:pk>/", SessionDetailView.as_view(), name="session_detail"),
    path("sessions/<int:pk>/enroll/", SessionEnrollView.as_view(), name="session_enroll"),
    path("sessions/<int:pk>/complete/", SessionCompleteView.as_view(), name="session_complete"),
    path("sessions/<int:pk>/cancel/", SessionCancelView.as_view(), name="session_cancel"),
    path("sessions/<int:pk>/approve/<int:enrollment_pk>/", EnrollmentApproveView.as_view(), name="enroll_approve"),
    path("sessions/<int:pk>/reject/<int:enrollment_pk>/", EnrollmentRejectView.as_view(), name="enroll_reject"),
    path("certificates/", CertificateListView.as_view(), name="certificate_list"),
    path("my/certificates/", MyCertificatesView.as_view(), name="my_certificates"),
]
