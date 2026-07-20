from django.contrib import admin
from .models import Order, OrderStatusHistory, Driver, Vehicle, Review


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'status', 'sender', 'delivery_address', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('tracking_number', 'pickup_contact_name', 'delivery_name')
    readonly_fields = ('tracking_number', 'created_at', 'updated_at')
    inlines = [OrderStatusHistoryInline]


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('driver_id', 'name', 'phone', 'is_verified', 'is_active', 'created_at')
    list_filter = ('is_verified', 'is_active')
    search_fields = ('driver_id', 'name', 'phone', 'email')


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('registration_number', 'vehicle_type', 'make_model', 'status', 'assigned_driver')
    list_filter = ('vehicle_type', 'status')
    search_fields = ('registration_number', 'make_model')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('order', 'driver', 'rating', 'sender', 'timestamp')
    list_filter = ('rating', 'timestamp')
    search_fields = ('order__tracking_number', 'driver__name', 'sender__email')
    readonly_fields = ('timestamp',)
