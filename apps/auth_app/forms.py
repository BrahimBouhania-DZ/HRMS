"""نماذج المصادقة (تسجيل الدخول مع فحص القفل)."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class LoginForm(AuthenticationForm):
    """نموذج الدخول — يمنع الدخول لحساب مقفل."""

    error_messages = {
        "invalid_login": _("اسم المستخدم أو كلمة المرور غير صحيحة"),
        "inactive": _("هذا الحساب غير نشط"),
        "locked": _("الحساب مقفل مؤقتًا، حاول لاحقًا"),
    }

    def confirm_login_allowed(self, user):
        if user.locked_until and user.locked_until > timezone.now():
            raise forms.ValidationError(
                self.error_messages["locked"],
                code="locked",
            )
        return super().confirm_login_allowed(user)
