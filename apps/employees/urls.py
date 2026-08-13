"""مسارات الموظفين."""

from django.urls import path

from . import views

app_name = "employees"

urlpatterns = [
    path("", views.EmployeeListView.as_view(), name="employee_list"),
    path("new/", views.EmployeeCreateView.as_view(), name="employee_create"),
    path("<int:pk>/", views.EmployeeDetailView.as_view(), name="employee_detail"),
    path("<int:pk>/edit/", views.EmployeeUpdateView.as_view(), name="employee_edit"),
    path("<int:pk>/card/", views.EmployeeQrCardView.as_view(), name="employee_card"),
    path("<int:pk>/card/print/", views.EmployeeCardPrintView.as_view(), name="employee_card_print"),
    path("cards/print/", views.EmployeeCardsPrintView.as_view(), name="employee_cards_print"),
    path("contracts/", views.ContractListView.as_view(), name="contract_list"),
    path("contracts/new/", views.ContractCreateView.as_view(), name="contract_create"),
    path("contracts/<int:pk>/edit/", views.ContractUpdateView.as_view(), name="contract_edit"),
    path("documents/", views.DocumentListView.as_view(), name="document_list"),
    path("documents/upload/", views.DocumentUploadView.as_view(), name="document_upload"),
    path("documents/<int:pk>/edit/", views.DocumentUpdateView.as_view(), name="document_edit"),
    path("documents/<int:pk>/download/", views.DocumentDownloadView.as_view(), name="document_download"),
]
