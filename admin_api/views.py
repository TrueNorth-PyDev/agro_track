from rest_framework import status
from rest_framework.response import Response
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveUpdateAPIView, CreateAPIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.contrib.auth import get_user_model
from django.db.models import Sum, Avg
from django.utils import timezone
from datetime import timedelta

from accounts.views import success_response
from accounts.permissions import IsAdminUser
from orders.models import Order, Vehicle, Driver
from .serializers import (
    AdminUserSerializer, AdminUserDetailSerializer, AdminDispatcherCreateSerializer,
    AdminDriverSerializer, AdminDriverDetailSerializer, AdminDriverCreateSerializer,
    AdminVehicleSerializer, PlatformSettingsSerializer
)
from .models import PlatformSettings

User = get_user_model()

class AdminDashboardView(GenericAPIView):
    """
    GET /api/v1/admin/dashboard/
    """
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Get Admin Overview Dashboard",
        responses={200: OpenApiResponse(description="Admin Dashboard data")}
    )
    def get(self, request, *args, **kwargs):
        registered_users = User.objects.filter(role=User.Role.SENDER).count()
        active_dispatchers = User.objects.filter(role=User.Role.DISPATCHER, is_active=True).count()
        verified_drivers = Driver.objects.filter(is_verified=True).count()
        fleet_size = Vehicle.objects.count()
        
        # Shipments
        now = timezone.now()
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        this_month_orders = Order.objects.filter(created_at__gte=start_date)
        total_shipments = this_month_orders.count()
        
        # Revenue
        platform_revenue = sum([float(o.total_cost) for o in this_month_orders])
        
        # Determine if we should use mock data for growth trend
        all_orders_count = Order.objects.count()
        if all_orders_count < 10:
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            current_month_idx = now.month - 1
            trend_months = []
            
            for i in range(5, -1, -1):
                idx = (current_month_idx - i) % 12
                trend_months.append(months[idx])
                
            growth_trend = [
                {'month': 'Jan', 'users': 10, 'shipments': 15},
                {'month': 'Feb', 'users': 15, 'shipments': 25},
                {'month': 'Mar', 'users': 22, 'shipments': 30},
                {'month': 'Apr', 'users': 28, 'shipments': 45},
                {'month': 'May', 'users': 35, 'shipments': 40},
                {'month': 'Jun', 'users': 42, 'shipments': 48},
            ]
            
            # Map dynamic months
            for i, item in enumerate(growth_trend):
                if i < len(trend_months):
                    item['month'] = trend_months[i]
        else:
            # Generate actual trend
            from collections import defaultdict
            users_by_month = defaultdict(int)
            shipments_by_month = defaultdict(int)
            
            # 6 months ago
            trend_start = (now.replace(day=1) - timedelta(days=5*32)).replace(day=1)
            
            for user in User.objects.filter(date_joined__gte=trend_start):
                m_name = user.date_joined.strftime('%b')
                users_by_month[m_name] += 1
                
            for order in Order.objects.filter(created_at__gte=trend_start):
                m_name = order.created_at.strftime('%b')
                shipments_by_month[m_name] += 1
                
            # cumulative sum approx
            months_order = []
            current = trend_start
            while current <= now:
                m_name = current.strftime('%b')
                if m_name not in months_order:
                    months_order.append(m_name)
                current += timedelta(days=32)
                current = current.replace(day=1)
                
            growth_trend = []
            cum_u = 0
            for m in months_order[-6:]:
                cum_u += users_by_month.get(m, 0)
                growth_trend.append({
                    'month': m,
                    'users': cum_u if cum_u > 0 else users_by_month.get(m, 0), # Simplified cumulative
                    'shipments': shipments_by_month.get(m, 0)
                })

        data = {
            'overview_metrics': {
                'registered_users': registered_users,
                'active_dispatchers': active_dispatchers,
                'verified_drivers': verified_drivers,
                'fleet_size': fleet_size,
                'total_shipments': total_shipments,
                'platform_revenue': f"₦{platform_revenue/1000:.0f}k" if platform_revenue >= 1000 else f"₦{platform_revenue}"
            },
            'growth_trend': growth_trend
        }
        
        return success_response('Admin dashboard retrieved', data=data)


class AdminUserListView(ListAPIView):
    """
    GET /api/v1/admin/users/
    """
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer
    
    def get_queryset(self):
        return User.objects.filter(role=User.Role.SENDER).order_by('-date_joined')
        
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response('Users retrieved', data=serializer.data)


class AdminUserDetailView(RetrieveUpdateAPIView):
    """
    GET /api/v1/admin/users/{id}/
    PATCH /api/v1/admin/users/{id}/
    """
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()
    serializer_class = AdminUserDetailSerializer
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response('User details retrieved', data=serializer.data)
        
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if 'is_active' in request.data:
            instance.is_active = request.data['is_active']
            instance.save(update_fields=['is_active'])
            return success_response(f"Account {'activated' if instance.is_active else 'suspended'}")
        
        return super().update(request, *args, **kwargs)


class AdminDispatcherListView(ListAPIView, CreateAPIView):
    """
    GET /api/v1/admin/dispatchers/
    POST /api/v1/admin/dispatchers/
    """
    permission_classes = [IsAdminUser]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminDispatcherCreateSerializer
        return AdminUserSerializer
    
    def get_queryset(self):
        return User.objects.filter(role=User.Role.DISPATCHER).order_by('-date_joined')
        
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response('Dispatchers retrieved', data=serializer.data)
        
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return success_response('Dispatcher created successfully', data=AdminUserDetailSerializer(user).data, http_status=status.HTTP_201_CREATED)


class AdminDispatcherDetailView(RetrieveUpdateAPIView):
    """
    GET /api/v1/admin/dispatchers/{id}/
    PATCH /api/v1/admin/dispatchers/{id}/
    """
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        return User.objects.filter(role=User.Role.DISPATCHER)
        
    def get_serializer_class(self):
        return AdminUserDetailSerializer
        
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response('Dispatcher details retrieved', data=serializer.data)
        
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        updated = False
        
        if 'is_active' in request.data:
            instance.is_active = request.data['is_active']
            updated = True
        
        if 'territory' in request.data:
            instance.territory = request.data['territory']
            updated = True
            
        if updated:
            instance.save(update_fields=['is_active', 'territory'] if 'is_active' in request.data and 'territory' in request.data else ['is_active'] if 'is_active' in request.data else ['territory'])
            return success_response("Dispatcher updated successfully", data=self.get_serializer(instance).data)
            
        return super().update(request, *args, **kwargs)


class AdminDriverListView(ListAPIView, CreateAPIView):
    """
    GET /api/v1/admin/drivers/
    POST /api/v1/admin/drivers/
    """
    permission_classes = [IsAdminUser]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AdminDriverCreateSerializer
        return AdminDriverSerializer
        
    def get_queryset(self):
        return Driver.objects.all().order_by('-created_at')
        
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response('Drivers retrieved', data=serializer.data)
        
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        driver = serializer.save()
        return success_response('Driver created successfully', data=AdminDriverDetailSerializer(driver).data, http_status=status.HTTP_201_CREATED)

class AdminDriverDetailView(RetrieveUpdateAPIView):
    """
    GET /api/v1/admin/drivers/{id}/
    PATCH /api/v1/admin/drivers/{id}/
    """
    permission_classes = [IsAdminUser]
    serializer_class = AdminDriverDetailSerializer
    
    def get_queryset(self):
        from orders.models import Driver
        return Driver.objects.all()
        
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response('Driver details retrieved', data=serializer.data)
        
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        updated = False
        
        if 'is_verified' in request.data:
            instance.is_verified = request.data['is_verified']
            updated = True
            
        if 'is_active' in request.data:
            instance.is_active = request.data['is_active']
            updated = True
            
        if updated:
            fields = []
            if 'is_verified' in request.data: fields.append('is_verified')
            if 'is_active' in request.data: fields.append('is_active')
            instance.save(update_fields=fields)
            return success_response("Driver updated successfully", data=self.get_serializer(instance).data)
            
        return super().update(request, *args, **kwargs)

class AdminVehicleListView(ListAPIView, CreateAPIView):
    """
    GET /api/v1/admin/vehicles/
    POST /api/v1/admin/vehicles/
    """
    permission_classes = [IsAdminUser]
    serializer_class = AdminVehicleSerializer
    
    def get_queryset(self):
        return Vehicle.objects.select_related('assigned_driver').all().order_by('-id')
        
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return success_response('Vehicles retrieved', data=serializer.data)
        
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        return success_response('Vehicle registered successfully', data=serializer.data, http_status=status.HTTP_201_CREATED)

class AdminVehicleDetailView(RetrieveUpdateAPIView):
    """
    GET /api/v1/admin/vehicles/{id}/
    PATCH /api/v1/admin/vehicles/{id}/
    """
    permission_classes = [IsAdminUser]
    serializer_class = AdminVehicleSerializer
    
    def get_queryset(self):
        return Vehicle.objects.select_related('assigned_driver').all()
        
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response('Vehicle details retrieved', data=serializer.data)
        
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response("Vehicle updated successfully", data=serializer.data)

class PlatformSettingsView(GenericAPIView):
    """
    GET /api/v1/admin/settings/
    PATCH /api/v1/admin/settings/
    """
    permission_classes = [IsAdminUser]
    serializer_class = PlatformSettingsSerializer
    
    def get(self, request):
        settings = PlatformSettings.get_settings()
        serializer = self.get_serializer(settings)
        return success_response('Platform settings retrieved', data=serializer.data)
        
    def patch(self, request):
        settings = PlatformSettings.get_settings()
        serializer = self.get_serializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response('Platform settings updated successfully', data=serializer.data)

class PlatformAnalyticsView(GenericAPIView):
    """
    GET /api/v1/admin/analytics/
    """
    permission_classes = [IsAdminUser]
    
    @extend_schema(
        tags=['Admin Analytics'],
        summary="Get Platform Analytics",
        description="Retrieves aggregate analytics like revenue, uptime, and trend charts.",
        responses={200: OpenApiResponse(description="Analytics JSON payload")}
    )
    def get(self, request):
        orders = Order.objects.filter(status__in=[Order.Status.DELIVERED, Order.Status.COMPLETED])
        stats = orders.aggregate(
            total_revenue=Sum('total_cost'),
            avg_revenue=Avg('total_cost')
        )
        
        total_rev = stats['total_revenue'] or 0
        avg_rev = stats['avg_revenue'] or 0
        
        # Mocking complex analytics for UI rendering
        data = {
            "kpis": {
                "total_revenue": total_rev,
                "total_revenue_growth_percentage": 24, # Mocked vs last month
                "avg_revenue_per_shipment": avg_rev,
                "platform_uptime_percentage": 99.8,
                "avg_delivery_time_days": 2.4,
                "avg_delivery_time_growth": -0.3 # Mocked
            },
            "revenue_trend": [
                {"month": "Jan", "revenue": 380000},
                {"month": "Feb", "revenue": 520000},
                {"month": "Mar", "revenue": 600000},
                {"month": "Apr", "revenue": 850000},
                {"month": "May", "revenue": 750000},
                {"month": "Jun", "revenue": total_rev if total_rev > 0 else 920000}
            ],
            "shipments_by_region": [
                {"region": "South-West", "shipments": 18},
                {"region": "North-Central", "shipments": 9},
                {"region": "South-East", "shipments": 7},
                {"region": "North-West", "shipments": 5},
                {"region": "South-South", "shipments": 6}
            ],
            "user_acquisition": [
                {"month": "Jan", "users": 10},
                {"month": "Feb", "users": 15},
                {"month": "Mar", "users": 20},
                {"month": "Apr", "users": 25},
                {"month": "May", "users": 35},
                {"month": "Jun", "users": 42}
            ]
        }
        
        return success_response('Platform analytics retrieved', data=data)
