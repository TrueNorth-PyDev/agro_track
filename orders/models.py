import string
import random
from django.db import models
from django.conf import settings


def generate_tracking_number():
    """Generates a unique tracking number like AGT30349900"""
    from django.apps import apps
    Order = apps.get_model('orders', 'Order')
    while True:
        num = ''.join(random.choices(string.digits, k=8))
        tracking_number = f"AGT{num}"
        if not Order.objects.filter(tracking_number=tracking_number).exists():
            return tracking_number


def generate_driver_id():
    """Generates a sequential driver ID like D001, D002, etc."""
    from django.apps import apps
    from django.db import transaction
    from django.db.utils import OperationalError, ProgrammingError
    Driver = apps.get_model('orders', 'Driver')
    try:
        with transaction.atomic():
            last_driver = Driver.objects.order_by('id').last()
            if last_driver and getattr(last_driver, 'driver_id', None) and last_driver.driver_id.startswith('D'):
                try:
                    num = int(last_driver.driver_id[1:])
                    return f"D{num + 1:03d}"
                except ValueError:
                    pass
    except (OperationalError, ProgrammingError):
        pass
    rand_suffix = ''.join(random.choices(string.digits, k=4))
    return f"D{rand_suffix}"


class Driver(models.Model):
    driver_id = models.CharField(max_length=10, unique=True, default=generate_driver_id, editable=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    license_number = models.CharField(max_length=50, blank=True)
    license_expiry = models.DateField(null=True, blank=True)
    trips_completed = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    violations = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.driver_id} - {self.name}"


class Vehicle(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        ON_DUTY = 'on_duty', 'On Duty'
        MAINTENANCE = 'maintenance', 'Maintenance'

    registration_number = models.CharField(max_length=100, unique=True)
    vehicle_type = models.CharField(max_length=100, blank=True)
    make_model = models.CharField(max_length=100, blank=True)
    capacity_tonnes = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    health_percentage = models.IntegerField(default=100)
    last_service_date = models.DateField(null=True, blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    roadworthy_expiry = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    assigned_driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_vehicles',
        help_text="Long-term assigned driver for fleet overview."
    )

    class Meta:
        ordering = ['registration_number']

    def __str__(self):
        return f"{self.registration_number} ({self.get_status_display()})"


class Order(models.Model):
    class Status(models.TextChoices):
        NEW_REQUEST = 'new_request', 'New Request'
        ASSIGNED = 'assigned', 'Assigned'
        PENDING_PICKUP = 'pending_pickup', 'Pending Pickup'
        IN_TRANSIT = 'in_transit', 'In Transit'
        DELIVERED = 'delivered', 'Delivered'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    class Priority(models.TextChoices):
        STANDARD = 'standard', 'Standard'
        EXPRESS = 'express', 'Express'

    tracking_number = models.CharField(max_length=20, unique=True, default=generate_tracking_number, editable=False)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_orders')
    dispatcher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='dispatched_orders'
    )

    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW_REQUEST, db_index=True)

    # Live Tracking
    estimated_delivery_date = models.DateField(null=True, blank=True)
    current_location = models.CharField(max_length=255, blank=True, default='')
    progress_percentage = models.IntegerField(default=0)
    proof_of_delivery = models.ImageField(upload_to='pod/', null=True, blank=True)

    # Pickup Info
    pickup_address = models.CharField(max_length=255)
    pickup_contact_name = models.CharField(max_length=255)
    pickup_phone = models.CharField(max_length=20)
    pickup_date = models.DateField(null=True, blank=True)
    pickup_notes = models.TextField(blank=True, default='')

    # Delivery Info
    delivery_address = models.CharField(max_length=255)
    delivery_name = models.CharField(max_length=255)
    delivery_phone = models.CharField(max_length=20)
    delivery_email = models.EmailField(blank=True, default='')

    # Cargo Details
    cargo_type = models.CharField(max_length=100)
    cargo_weight = models.DecimalField(max_digits=10, decimal_places=2, help_text="Weight in kg")
    cargo_value = models.DecimalField(max_digits=15, decimal_places=2, help_text="Estimated value in Naira")
    cargo_priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.STANDARD)

    # Pricing
    base_rate = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    distance_surcharge = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tracking_number} - {self.get_status_display()}"

    # ------------------------------------------------------------------
    # Timeline Helpers
    # ------------------------------------------------------------------

    def _get_sender_name(self):
        """Safely retrieve the sender's display name."""
        try:
            return self.sender.full_name or self.sender.email
        except Exception:
            return "Unknown sender"

    def _get_timeline_event(
        self,
        is_new,
        old_status,
        old_driver_id,
        old_vehicle_id,
        old_dispatcher_id,
    ):
        """
        Returns a (display_name, description) tuple for a new timeline entry.

        Derives the human-readable title and contextual subtitle from what
        actually changed on this save, so each event is specific and meaningful
        in the shipment UI (e.g. "Driver & Vehicle Assigned" vs "Dispatcher Assigned").
        """
        status = self.status

        # ── Brand new order ─────────────────────────────────────────────────
        if is_new:
            sender_name = self._get_sender_name()
            return "Order Placed", f"Received from {sender_name}"

        # ── ASSIGNED ────────────────────────────────────────────────────────
        if status == self.Status.ASSIGNED:
            driver_changed = self.driver_id and self.driver_id != old_driver_id
            vehicle_changed = self.vehicle_id and self.vehicle_id != old_vehicle_id
            dispatcher_changed = self.dispatcher_id and self.dispatcher_id != old_dispatcher_id

            if driver_changed or vehicle_changed:
                # Build "Eze Chukwudi · Truck ABC-123-KJ"
                parts = []
                if driver_changed and self.driver_id:
                    try:
                        driver = Driver.objects.get(pk=self.driver_id)
                        parts.append(driver.name)
                    except Driver.DoesNotExist:
                        parts.append("Assigned Driver")
                if vehicle_changed and self.vehicle_id:
                    try:
                        vehicle = Vehicle.objects.get(pk=self.vehicle_id)
                        parts.append(f"Truck {vehicle.registration_number}")
                    except Vehicle.DoesNotExist:
                        pass
                return "Driver & Vehicle Assigned", " · ".join(parts) if parts else "Driver and vehicle assigned"

            if dispatcher_changed:
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    dispatcher = User.objects.get(pk=self.dispatcher_id)
                    desc = f"{dispatcher.full_name} — Dispatcher"
                except Exception:
                    desc = "Dispatcher assigned"
                return "Dispatcher Assigned", desc

            # Generic fallback for assigned without specific actor
            return "Dispatcher Assigned", "Order accepted and being processed"

        # ── PENDING PICKUP ───────────────────────────────────────────────────
        if status == self.Status.PENDING_PICKUP:
            # Extract the first meaningful segment of the pickup address as a location hint
            location_hint = (self.pickup_address or '').split(',')[0].strip()
            desc = f"Cargo loaded at {location_hint}" if location_hint else "Pickup confirmed"
            return "Pickup Confirmed", desc

        # ── IN TRANSIT ──────────────────────────────────────────────────────
        if status == self.Status.IN_TRANSIT:
            desc = f"Currently in {self.current_location}" if self.current_location else "Shipment is now in transit"
            return "In Transit", desc

        # ── DELIVERED ───────────────────────────────────────────────────────
        if status == self.Status.DELIVERED:
            recipient = self.delivery_name or "recipient"
            desc = f"Delivered to {recipient} at {self.delivery_address.split(',')[0].strip()}"
            return "Delivered", desc

        # ── COMPLETED ───────────────────────────────────────────────────────
        if status == self.Status.COMPLETED:
            return "Completed", "Delivery confirmed with proof of delivery"

        # ── CANCELLED ───────────────────────────────────────────────────────
        if status == self.Status.CANCELLED:
            return "Cancelled", "Order was cancelled"

        # ── Generic fallback ────────────────────────────────────────────────
        return self.get_status_display(), f"Status updated to {self.get_status_display()}"

    # ------------------------------------------------------------------
    # Save Override
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        # Auto-calculate progress percentage from status
        progress_map = {
            self.Status.NEW_REQUEST: 0,
            self.Status.ASSIGNED: 10,
            self.Status.PENDING_PICKUP: 20,
            self.Status.IN_TRANSIT: 50,
            self.Status.DELIVERED: 80,
            self.Status.COMPLETED: 100,
            self.Status.CANCELLED: 0,
        }
        self.progress_percentage = progress_map.get(self.status, 0)

        is_new = self.pk is None
        old_status = None
        old_location = None
        old_driver_id = None
        old_vehicle_id = None
        old_dispatcher_id = None

        if not is_new:
            try:
                old = Order.objects.get(pk=self.pk)
                old_status = old.status
                old_location = old.current_location
                old_driver_id = old.driver_id
                old_vehicle_id = old.vehicle_id
                old_dispatcher_id = old.dispatcher_id
            except Order.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        status_changed = is_new or (old_status is not None and old_status != self.status)
        location_changed = (
            not is_new
            and self.status == self.Status.IN_TRANSIT
            and old_location != self.current_location
            and self.current_location
        )

        if status_changed:
            display_name, description = self._get_timeline_event(
                is_new=is_new,
                old_status=old_status,
                old_driver_id=old_driver_id,
                old_vehicle_id=old_vehicle_id,
                old_dispatcher_id=old_dispatcher_id,
            )
            OrderStatusHistory.objects.create(
                order=self,
                status=self.status,
                display_name=display_name,
                description=description,
            )
        elif location_changed:
            OrderStatusHistory.objects.create(
                order=self,
                status=self.status,
                display_name="Location Update",
                description=f"Currently in {self.current_location}",
            )


class OrderStatusHistory(models.Model):
    """
    Append-only log of meaningful events in an order's lifecycle.

    Each row represents one event — a status transition, a location update,
    or any other significant change. The `display_name` field carries the
    human-readable event title shown in the shipment timeline UI.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='timeline')
    status = models.CharField(max_length=20, choices=Order.Status.choices)
    display_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Human-readable event title shown in the shipment timeline UI, "
                  "e.g. 'Driver & Vehicle Assigned', 'Pickup Confirmed'."
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Contextual subtitle for the event, e.g. actor name, location, or note."
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        title = self.display_name or self.get_status_display()
        return f"{self.order.tracking_number} — {title} at {self.timestamp}"


class OrderMessage(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    is_read = models.BooleanField(
        default=False,
        help_text="True once the recipient (the other party in the 2-person chat) has read this message."
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Message on {self.order.tracking_number} by {self.sender}"
