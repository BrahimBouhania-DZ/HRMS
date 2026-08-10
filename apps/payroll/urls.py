"""روابط تطبيق الرواتب (namespace: payroll)."""

from django.urls import path

from .views import (
    BankExportView,
    EndOfServiceCreateView,
    EndOfServiceListView,
    MyPayslipsView,
    PayElementCreateView,
    PayElementListView,
    PayRunDetailView,
    PayRunGenerateView,
    PayRunListView,
    PayRunStatusView,
    PayslipListView,
    PayslipPdfView,
)

app_name = "payroll"

urlpatterns = [
    path("elements/", PayElementListView.as_view(), name="element_list"),
    path("elements/new/", PayElementCreateView.as_view(), name="element_create"),
    path("runs/", PayRunListView.as_view(), name="run_list"),
    path("runs/generate/", PayRunGenerateView.as_view(), name="run_generate"),
    path("runs/<int:pk>/", PayRunDetailView.as_view(), name="run_detail"),
    path("runs/<int:pk>/<str:action>/", PayRunStatusView.as_view(), name="run_status"),
    path("runs/<int:pk>/payslips/", PayslipListView.as_view(), name="run_payslips"),
    path("runs/<int:pk>/bank/<str:fmt>/", BankExportView.as_view(), name="bank_export"),
    path("payslips/<int:pk>/pdf/", PayslipPdfView.as_view(), name="payslip_pdf"),
    path("my-payslips/", MyPayslipsView.as_view(), name="my_payslips"),
    path("eos/", EndOfServiceListView.as_view(), name="eos_list"),
    path("eos/new/", EndOfServiceCreateView.as_view(), name="eos_create"),
]
