"""
Serializers for the admin_api app.

These serializers power the Admin Portal endpoints for managing Users,
Dispatchers, Drivers, Vehicles and Platform Settings.
"""

import secrets
import string

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.contrib.auth import get_user_model

from orders.models import Order, Driver, Vehicle
from orders.serializers import OrderListSerializer
from .models import PlatformSettings

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    """Compact user listing for admin dashboards."""
    shipments = serializers.SerializerMethodField()
    account_status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'business_name', 'email', 'phone_number',
            'shipments', 'date_joined', 'account_status', 'is_active', 'role', 'territory'
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_shipments(self, obj):
        if obj.role == User.Role.SENDER:
            return obj.sent_orders.count()
        elif obj.role == User.Role.DISPATCHER:
            return Order.objects.filter(
                status__in=[Order.Status.IN_TRANSIT, Order.Status.PENDING_PICKUP, Order.Status.ASSIGNED],
                dispatcher=obj
            ).count()
        return 0

    @extend_schema_field(serializers.ChoiceField(choices=['Active', 'Inactive']))
    def get_account_status(self, obj):
        return "Active" if obj.is_active else "Inactive"


class AdminUserDetailSerializer(AdminUserSerializer):
    """Detailed user view with recent activity."""
    recent_shipments = serializers.SerializerMethodField()

    class Meta(AdminUserSerializer.Meta):
        fields = AdminUserSerializer.Meta.fields + ['recent_shipments']

    @extend_schema_field(OrderListSerializer(many=True))
    def get_recent_shipments(self, obj):
        if obj.role == User.Role.SENDER:
            orders = obj.sent_orders.all()[:5]
        elif obj.role == User.Role.DISPATCHER:
            orders = obj.dispatched_orders.all()[:5]
        else:
            orders = []
        return OrderListSerializer(orders, many=True).data


class AdminDispatcherCreateSerializer(serializers.ModelSerializer):
    """Creates a new Dispatcher account with a randomly-generated initial password."""

    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone_number', 'territory']

    def create(self, validated_data):
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(12))

        user = User.objects.create_user(
            email=validated_data['email'],
            password=password,
            role=User.Role.DISPATCHER,
            full_name=validated_data.get('full_name', ''),
            phone_number=validated_data.get('phone_number', ''),
            territory=validated_data.get('territory', ''),
            is_active=True,
            is_verified=True,
        )
        return user


class AdminDriverSerializer(serializers.ModelSerializer):
    """Compact driver listing for the admin drivers panel."""

    class Meta:
        model = Driver
        fields = [
            'id', 'driver_id', 'name', 'trips_completed',
            'rating', 'violations', 'is_verified', 'is_active',
            'created_at', 'license_number', 'license_expiry',
        ]


class AdminDriverDetailSerializer(AdminDriverSerializer):
    """Detailed driver view including contact info and assigned vehicle."""
    assigned_vehicle = serializers.SerializerMethodField()

    class Meta(AdminDriverSerializer.Meta):
        fields = AdminDriverSerializer.Meta.fields + ['phone', 'email', 'assigned_vehicle']

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_assigned_vehicle(self, obj):
        vehicle = obj.assigned_vehicles.first()
        if vehicle:
            return {
                'id': vehicle.id,
                'registration_number': vehicle.registration_number,
                'vehicle_type': vehicle.vehicle_type,
                'make_model': vehicle.make_model,
            }
        return None


class AdminDriverCreateSerializer(serializers.ModelSerializer):
    """Handles new driver registration from the Admin portal."""
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    assigned_vehicle = serializers.PrimaryKeyRelatedField(
        queryset=Vehicle.objects.all(), required=False, write_only=True, allow_null=True
    )

    class Meta:
        model = Driver
        fields = ['first_name', 'last_name', 'phone', 'email', 'assigned_vehicle']

    def create(self, validated_data):
        first_name = validated_data.pop('first_name', '')
        last_name = validated_data.pop('last_name', '')
        assigned_vehicle = validated_data.pop('assigned_vehicle', None)

        validated_data['name'] = f"{first_name} {last_name}".strip()
        driver = Driver.objects.create(**validated_data)

        if assigned_vehicle:
            assigned_vehicle.assigned_driver = driver
            assigned_vehicle.save(update_fields=['assigned_driver'])

        return driver


class AdminVehicleSerializer(serializers.ModelSerializer):
    """Vehicle serializer for Admin Fleet Registry."""
    driver_name = serializers.CharField(source='assigned_driver.name', read_only=True, allow_null=True)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'registration_number', 'vehicle_type', 'make_model',
            'capacity_tonnes', 'insurance_expiry', 'roadworthy_expiry',
            'status', 'assigned_driver', 'driver_name', 'last_service_date',
            'health_percentage',
        ]


class PlatformSettingsSerializer(serializers.ModelSerializer):
    """Serializer for managing singleton PlatformSettings."""

    class Meta:
        model = PlatformSettings
        fields = '__all__'
