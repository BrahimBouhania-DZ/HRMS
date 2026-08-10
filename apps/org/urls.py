"""مسارات الهيكل التنظيمي (org)."""

from django.urls import path

from . import views

app_name = "org"

urlpatterns = [
    path("branches/", views.BranchListView.as_view(), name="branch_list"),
    path("branches/new/", views.BranchCreateView.as_view(), name="branch_create"),
    path("branches/<int:pk>/edit/", views.BranchUpdateView.as_view(), name="branch_edit"),
    path("branches/<int:pk>/delete/", views.BranchDeleteView.as_view(), name="branch_delete"),
    path("departments/", views.DepartmentListView.as_view(), name="department_list"),
    path("departments/new/", views.DepartmentCreateView.as_view(), name="department_create"),
    path("departments/<int:pk>/edit/", views.DepartmentUpdateView.as_view(), name="department_edit"),
    path("departments/<int:pk>/delete/", views.DepartmentDeleteView.as_view(), name="department_delete"),
    path("positions/", views.PositionListView.as_view(), name="position_list"),
    path("positions/new/", views.PositionCreateView.as_view(), name="position_create"),
    path("positions/<int:pk>/edit/", views.PositionUpdateView.as_view(), name="position_edit"),
    path("shifts/", views.ShiftListView.as_view(), name="shift_list"),
    path("shifts/new/", views.ShiftCreateView.as_view(), name="shift_create"),
    path("shifts/<int:pk>/edit/", views.ShiftUpdateView.as_view(), name="shift_edit"),
]
