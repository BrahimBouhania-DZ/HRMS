"""روابط تقييم الأداء (namespace: perf)."""

from django.urls import path

from .views import (
    CycleCloseView,
    CycleCreateView,
    CycleListView,
    CycleOpenView,
    MyReviewListView,
    MyReviewSelfView,
    PipCloseView,
    PipCreateView,
    ReviewDetailView,
    ReviewListView,
    ReviewManagerSubmitView,
    TemplateCreateView,
    TemplateListView,
)

app_name = "perf"

urlpatterns = [
    path("", CycleListView.as_view(), name="cycle_list"),
    path("cycles/new/", CycleCreateView.as_view(), name="cycle_create"),
    path("cycles/<int:pk>/open/", CycleOpenView.as_view(), name="cycle_open"),
    path("cycles/<int:pk>/close/", CycleCloseView.as_view(), name="cycle_close"),
    path("reviews/", ReviewListView.as_view(), name="review_list"),
    path("reviews/<int:pk>/", ReviewDetailView.as_view(), name="review_detail"),
    path("reviews/<int:pk>/submit/", ReviewManagerSubmitView.as_view(), name="review_submit"),
    path("my/", MyReviewListView.as_view(), name="my_reviews"),
    path("my/<int:pk>/self/", MyReviewSelfView.as_view(), name="self_review"),
    path("templates/", TemplateListView.as_view(), name="template_list"),
    path("templates/new/", TemplateCreateView.as_view(), name="template_create"),
    path("pip/<int:pk>/create/", PipCreateView.as_view(), name="pip_create"),
    path("pip/<int:pk>/close/", PipCloseView.as_view(), name="pip_close"),
]
