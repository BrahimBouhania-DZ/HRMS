"""مسارات إدارة قارئات QR (S6)."""

from django.urls import path

from . import views

app_name = "devices"

urlpatterns = [
    path("", views.DeviceListView.as_view(), name="list"),
    path("new/", views.DeviceCreateView.as_view(), name="create"),
    path("<int:pk>/", views.DeviceDetailView.as_view(), name="detail"),
    path("<int:pk>/status/<str:status>/", views.DeviceStatusView.as_view(), name="status"),
]
