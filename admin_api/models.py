from django.db import models


class PlatformSettings(models.Model):
    """
    Singleton model for global platform configuration.
    Only one row should ever exist — use get_settings() to access it.
    """
    # Pricing Configuration
    base_rate = models.DecimalField(max_digits=15, decimal_places=2, default=15000.00)
    distance_surcharge_per_km = models.DecimalField(max_digits=10, decimal_places=2, default=45.00)
    express_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1.5)
    same_day_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)
    max_cargo_weight = models.DecimalField(max_digits=10, decimal_places=2, default=15000.00)

    # Notification Feature Flags
    notify_shipment_assigned = models.BooleanField(default=True)
    notify_status_update = models.BooleanField(default=True)
    notify_delivery_confirmed = models.BooleanField(default=True)
    notify_new_request = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Platform Settings"
        verbose_name_plural = "Platform Settings"

    def __str__(self):
        return "Global Platform Settings"

    def save(self, *args, **kwargs):
        """Enforce singleton: only allow saves if pk=1 or no instance exists."""
        if not self.pk and PlatformSettings.objects.exists():
            # Rather than raise, silently prevent a second instance
            return
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Return the singleton instance, creating it with defaults if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance
