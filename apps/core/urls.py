"""مسارات الوحدة الأساسية (توجيه الصفحة الرئيسية بعد تسجيل الدخول)."""

from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", login_required(views.home), name="home"),
    path("search/", views.search, name="search"),
]
