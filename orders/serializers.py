from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Order, Driver, Vehicle, OrderStatusHistory, OrderMessage, Review


ACTIVE_ORDER_STATUSES = [
    Order.Status.ASSIGNED,
    Order.Status.PENDING_PICKUP,
    Order.Status.IN_TRANSIT,
]


class DriverSerializer(serializers.ModelSerializer):
    """Compact driver representation for embedding in order responses."""
    current_status = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = (
            'id', 'driver_id', 'name', 'phone', 'rating',
            'trips_completed', 'is_verified', 'current_status',
        )

    @extend_schema_field(serializers.ChoiceField(choices=['On Trip', 'Available']))
    def get_current_status(self, obj):
        """Returns 'On Trip' if driver has an active order, else 'Available'."""
        return 'On Trip' if obj.orders.filter(status__in=ACTIVE_ORDER_STATUSES).exists() else 'Available'


class VehicleSerializer(serializers.ModelSerializer):
    """Compact vehicle representation for embedding in order responses."""
    current_status = serializers.SerializerMethodField()
    assigned_driver = DriverSerializer(read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            'id', 'registration_number', 'vehicle_type', 'make_model',
            'capacity_tonnes', 'status', 'current_status', 'assigned_driver',
        )

    @extend_schema_field(serializers.ChoiceField(choices=['On Duty', 'Available']))
    def get_current_status(self, obj):
        """Returns 'On Duty' if vehicle has an active order, else 'Available'."""
        return 'On Duty' if obj.orders.filter(status__in=ACTIVE_ORDER_STATUSES).exists() else 'Available'


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for individual shipment timeline events.

    `display_name` is the bold event title shown in the UI
    (e.g. "Driver & Vehicle Assigned").  For any rows created before this
    field was added, we fall back to the human-readable status label.
    """
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderStatusHistory
        fields = ('id', 'status', 'display_name', 'description', 'timestamp')

    @extend_schema_field(serializers.CharField())
    def get_display_name(self, obj):
        return obj.display_name or obj.get_status_display()


class TimelineEventUpdateSerializer(serializers.ModelSerializer):
    """
    Write-only serializer for patching a single timeline event.

    Only `display_name` and `description` are editable — the status and
    timestamp are append-only and must not be mutated after creation.
    """
    class Meta:
        model = OrderStatusHistory
        fields = ('display_name', 'description')


class OrderMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for a single chat message in an order's conversation thread.

    Includes:
      - sender_name:    Full name of the sender (for display)
      - sender_initials: First letter of full_name, used for the avatar circle in the UI
      - is_own_message: True if the requesting user sent this message (drives left/right bubble placement)
      - is_read:        Whether the other party has read this message
    """
    sender_name = serializers.CharField(source='sender.full_name', read_only=True)
    sender_initials = serializers.SerializerMethodField()
    is_own_message = serializers.SerializerMethodField()

    class Meta:
        model = OrderMessage
        fields = (
            'id', 'sender', 'sender_name', 'sender_initials',
            'is_own_message', 'content', 'is_read', 'timestamp',
        )
        read_only_fields = ('sender', 'is_read')

    @extend_schema_field(serializers.CharField())
    def get_sender_initials(self, obj):
        """Returns the first letter of the sender's full_name, uppercased."""
        name = obj.sender.full_name or obj.sender.email
        return name[0].upper() if name else '?'

    @extend_schema_field(serializers.BooleanField())
    def get_is_own_message(self, obj):
        """Returns True if the requesting user is the sender of this message."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return obj.sender_id == request.user.id
        return False


class OrderListSerializer(serializers.ModelSerializer):
    """
    Serializer for lists of shipments (e.g., 'My Shipments' dashboard widget).
    Only includes high-level info needed for the UI.
    """
    driver = DriverSerializer(read_only=True)

    class Meta:
        model = Order
        fields = (
            'id',
            'tracking_number',
            'pickup_address',
            'delivery_address',
            'status',
            'created_at',
            'estimated_delivery_date',
            'driver',
        )


class OrderDetailSerializer(serializers.ModelSerializer):
    """
    Detailed view of a shipment request.
    Includes all information submitted in the 4-step wizard.
    """
    driver = DriverSerializer(read_only=True)
    vehicle = VehicleSerializer(read_only=True)
    timeline = OrderStatusHistorySerializer(many=True, read_only=True)

    driver_id = serializers.PrimaryKeyRelatedField(
        queryset=Driver.objects.all(), source='driver', write_only=True, required=False, allow_null=True
    )
    vehicle_id = serializers.PrimaryKeyRelatedField(
        queryset=Vehicle.objects.all(), source='vehicle', write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ('tracking_number', 'sender', 'dispatcher', 'progress_percentage')

    def validate(self, attrs):
        current_status = attrs.get('status', getattr(self.instance, 'status', None))
        pod = attrs.get('proof_of_delivery', getattr(self.instance, 'proof_of_delivery', None))

        if current_status == Order.Status.COMPLETED and not pod:
            raise serializers.ValidationError({
                'proof_of_delivery': 'Proof of delivery image is required when completing a shipment.'
            })

        return attrs


class OrderCreateSerializer(serializers.ModelSerializer):
    """
    Handles the 'New Shipment Request' 4-step submission.
    """
    class Meta:
        model = Order
        fields = (
            # Step 1 — Pickup
            'pickup_address', 'pickup_contact_name', 'pickup_phone', 'pickup_date', 'pickup_notes',
            # Step 2 — Delivery
            'delivery_address', 'delivery_name', 'delivery_phone', 'delivery_email',
            # Step 3 — Cargo & Pricing
            'cargo_type', 'cargo_weight', 'cargo_value', 'cargo_priority',
            'base_rate', 'distance_surcharge', 'total_cost',
        )

    def create(self, validated_data):
        """Automatically assign the logged-in user as the sender."""
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)


class ReviewSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a review on a completed order.
    """
    class Meta:
        model = Review
        fields = ('id', 'rating', 'comment', 'timestamp')
        read_only_fields = ('id', 'timestamp')

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value
