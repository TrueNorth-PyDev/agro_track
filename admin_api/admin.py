from django.contrib import admin
from .models import PlatformSettings


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    """
    Admin for the singleton PlatformSettings model.
    Prevents creation of additional instances and blocks deletion.
    """
    fieldsets = (
        ('Pricing Configuration', {
            'fields': (
                'base_rate', 'distance_surcharge_per_km', 'express_multiplier',
                'same_day_multiplier', 'max_cargo_weight',
            )
        }),
        ('Notification Flags', {
            'fields': (
                'notify_shipment_assigned', 'notify_status_update',
                'notify_delivery_confirmed', 'notify_new_request',
            )
        }),
    )

    def has_add_permission(self, request):
        """Only allow one settings object to exist."""
        if self.model.objects.count() >= 1:
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        """Prevent accidental deletion of global settings."""
        return False
