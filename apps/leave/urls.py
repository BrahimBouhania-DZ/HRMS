"""روابط تطبيق الإجازات (namespace: leave)."""

from django.urls import path

from .views import (
    BalanceAdjustView,
    BalanceListView,
    LeaveRequestApproveView,
    LeaveRequestCancelView,
    LeaveRequestCreateView,
    LeaveRequestDetailView,
    LeaveRequestListView,
    LeaveTypeCreateView,
    LeaveTypeListView,
    LeaveTypeUpdateView,
    MyLeaveView,
    PublicHolidayCreateView,
    PublicHolidayDeleteView,
    PublicHolidayListView,
)

app_name = "leave"

urlpatterns = [
    path("my/", MyLeaveView.as_view(), name="my_leave"),
    path("my/new/", LeaveRequestCreateView.as_view(), name="request_create"),
    path("my/<int:pk>/", LeaveRequestDetailView.as_view(), name="request_detail"),
    path("my/<int:pk>/cancel/", LeaveRequestCancelView.as_view(), name="request_cancel"),
    path("queue/", LeaveRequestListView.as_view(), name="request_list"),
    path("queue/<int:pk>/<str:action>/", LeaveRequestApproveView.as_view(), name="request_approve"),
    path("balances/", BalanceListView.as_view(), name="balance_list"),
    path("balances/<int:pk>/adjust/", BalanceAdjustView.as_view(), name="balance_adjust"),
    path("types/", LeaveTypeListView.as_view(), name="leave_type_list"),
    path("types/new/", LeaveTypeCreateView.as_view(), name="leave_type_create"),
    path("types/<int:pk>/edit/", LeaveTypeUpdateView.as_view(), name="leave_type_edit"),
    path("holidays/", PublicHolidayListView.as_view(), name="public_holiday_list"),
    path("holidays/new/", PublicHolidayCreateView.as_view(), name="public_holiday_create"),
    path("holidays/<int:pk>/delete/", PublicHolidayDeleteView.as_view(), name="public_holiday_delete"),
]
