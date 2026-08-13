"""مسارات التقارير (S5)."""

from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportIndexView.as_view(), name="index"),
    path("employees/", views.Rep01View.as_view(), name="rep01"),
    path("org-structure/", views.Rep02View.as_view(), name="rep02"),
    path("new-employees/", views.Rep03View.as_view(), name="rep03"),
    path("operational/", views.Rep11View.as_view(), name="rep11"),
    path("attendance/", views.Rep10View.as_view(), name="rep10"),
    path("absence/", views.Rep12View.as_view(), name="rep12"),
    path("lateness/", views.Rep13View.as_view(), name="rep13"),
    path("early-departure/", views.Rep14View.as_view(), name="rep14"),
    path("overtime/", views.Rep15View.as_view(), name="rep15"),
    path("attendance-exceptions/", views.Rep18View.as_view(), name="rep18"),
    path("ongoing-leaves/", views.Rep22View.as_view(), name="rep22"),
    path("public-holidays/", views.Rep23View.as_view(), name="rep23"),
    path("leave-balances/", views.Rep20View.as_view(), name="rep20"),
    path("leave-requests/", views.Rep21View.as_view(), name="rep21"),
    path("scans/", views.Rep16View.as_view(), name="rep16"),
    path("rejected-scans/", views.Rep17View.as_view(), name="rep17"),
    path("salary/", views.Rep30View.as_view(), name="rep30"),
    path("contracts-expiring/", views.Rep04View.as_view(), name="rep04"),
    path("retirement/", views.Rep05View.as_view(), name="rep05"),
    path("job-changes/", views.Rep06View.as_view(), name="rep06"),
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
    path("executive-summary/", views.Rep60View.as_view(), name="rep60"),
    path("kpi/", views.Rep61View.as_view(), name="rep61"),
    path("turnover/", views.Rep62View.as_view(), name="rep62"),
    path("generated/", views.GeneratedReportsView.as_view(), name="generated"),
    path("generated/<int:pk>/download/", views.generated_download, name="generated_download"),
    path("export/<str:report_code>/<str:fmt>/", views.export, name="export"),
]
