"""روابط تطبيق الحضور (namespace: attendance)."""

from django.urls import path

from .views import (
    AttendanceDayCorrectionView,
    AttendanceDayDetailView,
    AttendanceDayListView,
    ExceptionApproveView,
    ExceptionCreateView,
    ExceptionListView,
    MyAttendanceView,
    MyQrCardView,
    QrImageForPayload,
    ScanApiView,
)

app_name = "attendance"

urlpatterns = [
    path("api/v1/scan/", ScanApiView.as_view(), name="api_scan"),
    path("my-card/", MyQrCardView.as_view(), name="my_qr_card"),
    path("qr-image/<str:payload>/", QrImageForPayload.as_view(), name="qr_image"),
    path("my/", MyAttendanceView.as_view(), name="my_attendance"),
    path("days/", AttendanceDayListView.as_view(), name="attendance_day_list"),
    path("days/<int:pk>/", AttendanceDayDetailView.as_view(), name="attendance_day_detail"),
    path("days/<int:pk>/correct/", AttendanceDayCorrectionView.as_view(), name="attendance_day_correct"),
    path("exceptions/", ExceptionListView.as_view(), name="exception_list"),
    path("exceptions/new/", ExceptionCreateView.as_view(), name="exception_create"),
    path("exceptions/<int:pk>/<str:action>/", ExceptionApproveView.as_view(), name="exception_approve"),
]
