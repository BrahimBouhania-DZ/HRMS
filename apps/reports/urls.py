"""مسارات التقارير (S5)."""

from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportIndexView.as_view(), name="index"),
    path("employees/", views.Rep01View.as_view(), name="rep01"),
    path("attendance/", views.Rep10View.as_view(), name="rep10"),
    path("absence/", views.Rep12View.as_view(), name="rep12"),
    path("lateness/", views.Rep13View.as_view(), name="rep13"),
    path("leave-balances/", views.Rep20View.as_view(), name="rep20"),
    path("leave-requests/", views.Rep21View.as_view(), name="rep21"),
    path("scans/", views.Rep16View.as_view(), name="rep16"),
    path("rejected-scans/", views.Rep17View.as_view(), name="rep17"),
    path("salary/", views.Rep30View.as_view(), name="rep30"),
    path("export/<str:report_code>/<str:fmt>/", views.export, name="export"),
]
