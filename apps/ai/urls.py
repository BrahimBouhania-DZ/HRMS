"""مسارات الذكاء الاصطناعي (namespace: ai)."""

from django.urls import path

from apps.ai import views

app_name = "ai"

urlpatterns = [
    path("", views.PredictionListView.as_view(), name="predictions"),
    path("refresh/", views.RefreshPredictionsView.as_view(), name="refresh"),
    path("assistant/", views.AssistantView.as_view(), name="assistant"),
    path("assistant/feedback/", views.FeedbackView.as_view(), name="feedback"),
    path("analytics/", views.AnalyticsDashboardView.as_view(), name="analytics"),
]
