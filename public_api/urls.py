from django.urls import path
from .views import PublicPlatformStatsView, PublicTrackingView, PublicCostEstimateView, PublicLocationsView, PublicCompleteDeliveryView

app_name = 'public_api'

urlpatterns = [
    path('stats/', PublicPlatformStatsView.as_view(), name='stats'),
    path('track/<str:tracking_number>/', PublicTrackingView.as_view(), name='track'),
    path('track/<str:tracking_number>/complete/', PublicCompleteDeliveryView.as_view(), name='complete_delivery'),
    path('estimate/', PublicCostEstimateView.as_view(), name='estimate'),
    path('locations/', PublicLocationsView.as_view(), name='locations'),
]
