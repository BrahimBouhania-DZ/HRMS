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
]
