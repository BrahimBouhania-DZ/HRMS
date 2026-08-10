"""معالج سياق الإشعارات — عدّاد غير المقروء في الـ topbar."""

from apps.notif.services import unread_count


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_notifications": 0}
    return {"unread_notifications": unread_count(request.user)}
