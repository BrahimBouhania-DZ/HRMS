"""مسارات التقارير (S5)."""

from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportIndexView.as_view(), name="index"),
    path("employees/", views.Rep01View.as_view(), name="rep01"),
    path("operational/", views.Rep11View.as_view(), name="rep11"),
    path("attendance/", views.Rep10View.as_view(), name="rep10"),
    path("absence/", views.Rep12View.as_view(), name="rep12"),
    path("lateness/", views.Rep13View.as_view(), name="rep13"),
    path("leave-balances/", views.Rep20View.as_view(), name="rep20"),
    path("leave-requests/", views.Rep21View.as_view(), name="rep21"),
    path("scans/", views.Rep16View.as_view(), name="rep16"),
    path("rejected-scans/", views.Rep17View.as_view(), name="rep17"),
    path("salary/", views.Rep30View.as_view(), name="rep30"),
    path("contracts-expiring/", views.Rep04View.as_view(), name="rep04"),
    path("salary-detail/", views.Rep31View.as_view(), name="rep31"),
    path("salary-cost/", views.Rep33View.as_view(), name="rep33"),
    path("bonuses-deductions/", views.Rep34View.as_view(), name="rep34"),
    path("end-of-service/", views.Rep35View.as_view(), name="rep35"),
    path("perf-results/", views.Rep42View.as_view(), name="rep42"),
    path("pip-plans/", views.Rep43View.as_view(), name="rep43"),
    path("audit/", views.Rep50View.as_view(), name="rep50"),
    path("users-roles/", views.Rep51View.as_view(), name="rep51"),
    path("backup-status/", views.Rep53View.as_view(), name="rep53"),
    path("daily-activity/", views.Rep52View.as_view(), name="rep52"),
    path("device-status/", views.Rep54View.as_view(), name="rep54"),
    path("generated/", views.GeneratedReportsView.as_view(), name="generated"),
    path("generated/<int:pk>/download/", views.generated_download, name="generated_download"),
    path("export/<str:report_code>/<str:fmt>/", views.export, name="export"),
]
