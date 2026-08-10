from django.contrib import admin

from .models import Notification, NotificationPref, ScheduledAlert


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "title", "is_read", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("title", "body", "user__username")
    list_select_related = ("user",)


@admin.register(NotificationPref)
class NotificationPrefAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "channel", "enabled")
    list_filter = ("channel", "enabled")


@admin.register(ScheduledAlert)
class ScheduledAlertAdmin(admin.ModelAdmin):
    list_display = ("alert_type", "target_date", "fired_at")
    list_filter = ("alert_type", "fired_at")
