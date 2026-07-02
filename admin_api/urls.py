from django.urls import path
from .views import (
    AdminDashboardView,
    AdminUserListView,
    AdminUserDetailView,
    AdminDispatcherListView,
    AdminDispatcherDetailView,
    AdminDriverListView,
    AdminDriverDetailView,
    AdminVehicleListView,
    AdminVehicleDetailView,
    PlatformSettingsView,
    PlatformAnalyticsView
)

app_name = 'admin_api'

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='dashboard'),
    path('users/', AdminUserListView.as_view(), name='user-list'),
    path('users/<uuid:pk>/', AdminUserDetailView.as_view(), name='user-detail'),
    path('dispatchers/', AdminDispatcherListView.as_view(), name='dispatcher-list'),
    path('dispatchers/<uuid:pk>/', AdminDispatcherDetailView.as_view(), name='dispatcher-detail'),
    path('drivers/', AdminDriverListView.as_view(), name='driver-list'),
    path('drivers/<int:pk>/', AdminDriverDetailView.as_view(), name='driver-detail'),
    path('vehicles/', AdminVehicleListView.as_view(), name='vehicle-list'),
    path('vehicles/<int:pk>/', AdminVehicleDetailView.as_view(), name='vehicle-detail'),
    path('settings/', PlatformSettingsView.as_view(), name='platform-settings'),
    path('analytics/', PlatformAnalyticsView.as_view(), name='platform-analytics'),
]
