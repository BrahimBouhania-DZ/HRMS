"""مسارات الإشعارات (S4)."""

from django.urls import path

from . import views

app_name = "notif"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("<int:pk>/read/", views.NotificationMarkReadView.as_view(), name="mark_read"),
    path("mark-all-read/", views.NotificationMarkAllReadView.as_view(), name="mark_all_read"),
    path("prefs/", views.NotificationPrefsView.as_view(), name="prefs"),
]
