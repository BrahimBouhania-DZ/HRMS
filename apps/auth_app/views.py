"""عروض المصادقة (T-001..T-008 منطق الدخول/الخروج/الاستعادة)."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.forms import (
    PasswordResetForm,
    SetPasswordForm,
)
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.utils import timezone
from django.utils.translation import gettext as _
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import LoginForm

User = get_user_model()

LOGIN_THROTTLE_MAX_ATTEMPTS = 5
LOGIN_THROTTLE_LOCK_MINUTES = 15


@never_cache
def login_view(request):
    """تسجيل الدخول مع قفل الحساب بعد 5 محاولات فاشلة (D-05)."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        user.failed_attempts = 0
        user.save(update_fields=["failed_attempts"])
        messages.success(request, _("تم تسجيل الدخول بنجاح"))
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == "POST":
        username = request.POST.get("username", "")
        user = User.objects.filter(username=username).first()
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= LOGIN_THROTTLE_MAX_ATTEMPTS:
                user.locked_until = timezone.now() + timezone.timedelta(minutes=LOGIN_THROTTLE_LOCK_MINUTES)
                user.failed_attempts = 0
                messages.error(request, _("تم قفل الحساب مؤقتًا لعدة محاولات فاشلة"))
            user.save(update_fields=["failed_attempts", "locked_until"])

    return render(request, "auth_app/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, _("تم تسجيل الخروج"))
    return redirect("auth_app:login")


password_reset = PasswordResetView
