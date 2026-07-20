from django.urls import path
from .views import (
    DashboardView, OrderListView, OrderDetailView,
    OrderTimelineView, OrderTimelineEventUpdateView,
    OrderMessageListCreateView, OrderMessageMarkReadView,
    DispatcherInboxView,
    FleetOverviewView, DriverListView, VehicleListView,
    ReportsView
)

app_name = 'orders'

urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('reports/', ReportsView.as_view(), name='reports'),
    path('fleet/', FleetOverviewView.as_view(), name='fleet-overview'),
    path('drivers/', DriverListView.as_view(), name='driver-list'),
    path('vehicles/', VehicleListView.as_view(), name='vehicle-list'),
    path('timeline/<int:event_id>/', OrderTimelineEventUpdateView.as_view(), name='timeline-event-update'),
    path('', OrderListView.as_view(), name='order-list'),
    path('<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('<int:pk>/timeline/', OrderTimelineView.as_view(), name='order-timeline'),
    path('messages/', DispatcherInboxView.as_view(), name='dispatcher-inbox'),
    path('<int:pk>/messages/', OrderMessageListCreateView.as_view(), name='order-messages'),
    path('<int:pk>/messages/read/', OrderMessageMarkReadView.as_view(), name='order-messages-mark-read'),
]
