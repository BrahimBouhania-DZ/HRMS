"""تاج قالب — فحص الصلاحيات في الواجهة (يخفي الأزرار فقط؛ التحقق الأمني يبقى في الخادم).

الاستخدام في القوالب:
    {% load perms_tags %}
    {% perm_check user "employee.create" as can_create %}
    {% if can_create %}<a class="btn" href="...">إضافة موظف</a>{% endif %}
"""

from django import template

from apps.auth_app.services import has_perm

register = template.Library()


@register.simple_tag
def perm_check(user, permission_code):
    return has_perm(user, permission_code)
