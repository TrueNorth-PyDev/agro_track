from django.urls import path
from .views import PublicPlatformStatsView, PublicTrackingView, PublicCostEstimateView

app_name = 'public_api'

urlpatterns = [
    path('stats/', PublicPlatformStatsView.as_view(), name='stats'),
    path('track/<str:tracking_number>/', PublicTrackingView.as_view(), name='track'),
    path('estimate/', PublicCostEstimateView.as_view(), name='estimate'),
]
