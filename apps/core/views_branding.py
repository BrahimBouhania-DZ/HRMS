"""عرض صفحة الشعار والألوان السرية للمبرمج/المدير.

الدخول يتطلب:
  1. المسار السري (BRANDING_SECRET_PATH) فقط — لا يوجد رابط في أي مكان.
  2. حساب مميز (BRANDING_ADMIN_USERNAME من .env).
  3. حماية من التخمين المتكرر (حد أقصى 8 محاولات لكل جلسة).
"""

from __future__ import annotations

import json
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import AuditLog, CompanySettings

from .branding_utils import COLOR_VARS, DEFAULTS, build_css_block, build_full_palette, validate_hex

MAX_ATTEMPTS = 8
LOCKOUT_SECONDS = 900  # 15 دقيقة

_GROUP_PREFIX = {
    "brand_vars": ("--sky", "--brand", "--accent", "--gold"),
    "sand_vars": ("--sand", "--accent"),
    "gold_vars": ("--gold",),
    "green_vars": ("--green", "--success"),
    "red_vars": ("--red", "--danger"),
    "neutral_vars": ("--bg", "--surface", "--text", "--muted", "--border"),
}

PRESETS = [
    ("classic", "الأصلية"),
    ("royal", "ملكي بنفسجي"),
    ("emerald", "زمردي"),
    ("warm", "دافئ ترابي"),
]


def _grouped_vars() -> dict[str, list[str]]:
    groups = {k: [] for k in _GROUP_PREFIX}
    for var in COLOR_VARS:
        for group, prefixes in _GROUP_PREFIX.items():
            if any(var.startswith(p) for p in prefixes):
                groups[group].append(var)
    seen = set()
    for g in groups.values():
        g[:] = [v for v in g if not (v in seen or seen.add(v))]
    return groups


def _attempt_key() -> str:
    return "branding_attempts"


def _is_locked(request: HttpRequest) -> bool:
    """هل المستخدم محظور مؤقتًا بعد محاولات فاشلة؟"""
    attempts = request.session.get(_attempt_key(), {})
    if not attempts:
        return False
    ts = attempts.get("locked_at")
    if ts and (time.time() - ts) < LOCKOUT_SECONDS:
        return True
    if ts:
        request.session.pop(_attempt_key(), None)
    return False


def _record_fail(request: HttpRequest) -> int:
    d = request.session.setdefault(_attempt_key(), {"count": 0})
    d["count"] = d.get("count", 0) + 1
    if d["count"] >= MAX_ATTEMPTS:
        d["locked_at"] = time.time()
    request.session.modified = True
    return d["count"]


def _clear_attempts(request: HttpRequest) -> None:
    request.session.pop(_attempt_key(), None)


# --------------------------------------------------------------------------
# صفحة الدخول
# --------------------------------------------------------------------------
def branding_login(request: HttpRequest) -> HttpResponse:
    if not getattr(settings, "BRANDING_SECRET_PATH", ""):
        return HttpResponse(status=404)

    if request.user.is_authenticated and getattr(request.user, "is_branding_admin", False):
        return redirect("core:branding_dashboard")

    error = None
    if request.method == "POST":
        if _is_locked(request):
            error = "تم حظر الدخول مؤقتًا بعد محاولات كثيرة. حاول بعد 15 دقيقة."
        else:
            username = (request.POST.get("username") or "").strip()
            password = request.POST.get("password") or ""
            if username != getattr(settings, "BRANDING_ADMIN_USERNAME", ""):
                error = "بيانات الدخول غير صحيحة"
                _record_fail(request)
            else:
                user = authenticate(request, username=username, password=password)
                if user is not None and user.username == getattr(settings, "BRANDING_ADMIN_USERNAME", ""):
                    login(request, user)
                    request.session["branding_admin"] = True
                    _clear_attempts(request)
                    AuditLog.objects.create(
                        user=user, action=AuditLog.Action.LOGIN,
                        model_name="branding", detail="دخول لوحة التحكم السرية",
                        ip=_client_ip(request),
                    )
                    return redirect("core:branding_dashboard")
                error = "بيانات الدخول غير صحيحة"
                _record_fail(request)

    return render(request, "core/branding_login.html", {"error": error})


# --------------------------------------------------------------------------
# لوحة التحكم
# --------------------------------------------------------------------------
@login_required
def branding_dashboard(request: HttpRequest) -> HttpResponse:
    if not getattr(settings, "BRANDING_SECRET_PATH", "") or not _is_branding(request):
        return HttpResponse(status=404)

    company = CompanySettings.get_default()
    if company is None:
        company = CompanySettings.objects.create(company_name_ar="HRMS")

    current_overrides = company.css_overrides or {}
    css_block = build_css_block(current_overrides)

    groups = _grouped_vars()

    return render(request, "core/branding_dashboard.html", {
        "company": company,
        "overrides": current_overrides,
        "css_block": css_block,
        "defaults": DEFAULTS,
        "defaults_json": json.dumps(DEFAULTS),
        "presets": PRESETS,
        **groups,
    })


# --------------------------------------------------------------------------
# حفظ: الشعار
# --------------------------------------------------------------------------
@login_required
@require_POST
def branding_save_logo(request: HttpRequest) -> HttpResponse:
    if not _is_branding(request):
        return HttpResponse(status=404)
    company = CompanySettings.get_default()
    action = request.POST.get("action", "save")

    if action == "delete" and company.logo:
        company.logo.delete(save=False)
        company.logo = None
        company.save(update_fields=["logo"])
        messages.success(request, "✅ تم مسح الشعار.")
    elif "logo" in request.FILES:
        company.logo = request.FILES["logo"]
        company.save(update_fields=["logo"])
        messages.success(request, "✅ تم حفظ الشعار الجديد.")
    else:
        messages.warning(request, "لم يتم اختيار ملف.")

    _log(request, "logo", f"شعار: {action}")
    return redirect("core:branding_dashboard")


# --------------------------------------------------------------------------
# حفظ: الألوان (مجاني / مقاييس جاهزة)
# --------------------------------------------------------------------------
@login_required
@require_POST
def branding_save_colors(request: HttpRequest) -> HttpResponse:
    if not _is_branding(request):
        return HttpResponse(status=404)

    company = CompanySettings.get_default()
    action = request.POST.get("action", "custom")

    if action == "reset":
        company.css_overrides = {}
        company.save(update_fields=["css_overrides"])
        messages.success(request, "✅ تمت استعادة الألوان الافتراضية.")
        _log(request, "colors_reset", "استعادة الافتراضي")
        return redirect("core:branding_dashboard")

    if action == "preset":
        preset = request.POST.get("preset", "default")
        company.css_overrides = _apply_preset(preset)
        company.save(update_fields=["css_overrides"])
        messages.success(request, f"✅ تم تطبيق النموذج: {preset}")
        _log(request, "colors_preset", f"نموذج: {preset}")
        return redirect("core:branding_dashboard")

    # custom: تجميع القيم من حقول النموذج
    overrides: dict[str, str] = {}
    for var in COLOR_VARS:
        val = (request.POST.get(f"var_{var}") or "").strip()
        if val and val != DEFAULTS.get(var, ""):
            if validate_hex(val):
                overrides[var] = val
            else:
                messages.warning(request, f"قيمة غير صالحة تم تجاهلها: {var} = {val}")

    company.css_overrides = overrides
    company.save(update_fields=["css_overrides"])
    messages.success(request, "✅ تم حفظ الألوان.")
    _log(request, "colors_custom", f"متغيرات: {len(overrides)}")
    return redirect("core:branding_dashboard")


# --------------------------------------------------------------------------
# حفظ: معلومات الهوية (اسم + تاغلاين)
# --------------------------------------------------------------------------
@login_required
@require_POST
def branding_save_identity(request: HttpRequest) -> HttpResponse:
    if not _is_branding(request):
        return HttpResponse(status=404)

    company = CompanySettings.get_default()
    company.company_name_ar = (request.POST.get("company_name_ar") or "").strip() or company.company_name_ar
    company.company_name_fr = (request.POST.get("company_name_fr") or "").strip()
    company.company_name_en = (request.POST.get("company_name_en") or "").strip()
    company.tagline = (request.POST.get("tagline") or "").strip()
    company.show_logo_watermark = "show_logo_watermark" in request.POST

    try:
        op = int(request.POST.get("watermark_opacity", company.watermark_opacity))
        company.watermark_opacity = max(0, min(100, op))
    except (ValueError, TypeError):
        pass

    company.save()
    messages.success(request, "✅ تم حفظ معلومات الهوية.")
    _log(request, "identity_saved", f"اسم: {company.company_name_ar}")
    return redirect("core:branding_dashboard")


# --------------------------------------------------------------------------
# الخروج
# --------------------------------------------------------------------------
@login_required
def branding_logout(request: HttpRequest) -> HttpResponse:
    if _is_branding(request):
        AuditLog.objects.create(
            user=request.user, action=AuditLog.Action.LOGOUT,
            model_name="branding", detail="خروج لوحة التحكم السرية",
            ip=_client_ip(request),
        )
        request.session.pop("branding_admin", None)
        logout(request)
    return redirect("core:branding_login")


# --------------------------------------------------------------------------
# مساعدات
# --------------------------------------------------------------------------
def _is_branding(request: HttpRequest) -> bool:
    return (
        request.user.is_authenticated
        and request.user.username == getattr(settings, "BRANDING_ADMIN_USERNAME", "")
        and request.session.get("branding_admin") is True
    )


def _client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")) or ""


def _log(request: HttpRequest, action_type: str, detail: str) -> None:
    AuditLog.objects.create(
        user=request.user, action=AuditLog.Action.UPDATE,
        model_name="CompanySettings", object_id="1",
        object_repr="هوية الشركة", detail=detail, ip=_client_ip(request),
    )


def _apply_preset(name: str) -> dict[str, str]:
    """نماذج لونية جاهزة — تولّد لوحة كاملة من الألوان الأساسية عبر build_full_palette."""
    presets: dict[str, dict[str, str]] = {
        "classic": {"brand": "#2E96C8", "sand": "#C29247", "gold": "#D4AF37",
                    "green": "#3E9466", "red": "#C0392B",
                    "surface": "#FFFFFF", "bg": "#F1F6FA", "text": "#20303C", "border": "#DEE8F0"},
        "royal":   {"brand": "#4338CA", "sand": "#D97706", "gold": "#B45309",
                    "green": "#059669", "red": "#DC2626",
                    "surface": "#FFFFFF", "bg": "#F5F5FF", "text": "#1E1B4B", "border": "#DDD6FE"},
        "emerald": {"brand": "#059669", "sand": "#D97706", "gold": "#B45309",
                    "green": "#16A34A", "red": "#DC2626",
                    "surface": "#FFFFFF", "bg": "#F0FDFA", "text": "#064E3B", "border": "#A7F3D0"},
        "warm":    {"brand": "#C2410C", "sand": "#0E7490", "gold": "#B45309",
                    "green": "#16A34A", "red": "#E11D48",
                    "surface": "#FFFFFF", "bg": "#FFFBEB", "text": "#451A03", "border": "#FED7AA"},
    }
    p = presets.get(name, presets["classic"])
    return build_full_palette(
        brand=p["brand"], sand=p.get("sand"), gold_color=p.get("gold"),
        green=p.get("green"), red=p.get("red"),
        surface=p.get("surface"), bg=p.get("bg"),
        text_color=p.get("text"), border_color=p.get("border"),
    )
