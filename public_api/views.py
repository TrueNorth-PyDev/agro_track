import logging

from django.http import Http404
from rest_framework import status, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView
from accounts.views import success_response, get_envelope_serializer
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer

from orders.models import Order, Review
from admin_api.models import PlatformSettings
from .serializers import PublicTrackingSerializer
from .geo import resolve_distance

logger = logging.getLogger(__name__)


class PublicCostEstimateView(APIView):
    """
    POST /api/v1/public/estimate/

    Calculates a shipping cost estimate from plain-text addresses.
    No authentication required.

    Flow:
        1. Validate pickup_address, delivery_address, cargo_priority.
        2. Geocode both addresses via Nominatim (OpenStreetMap).
        3. Calculate road distance via OSRM routing engine.
           Falls back to Haversine × 1.3 if OSRM is unreachable.
        4. Apply PlatformSettings pricing formula:
               estimated_cost = (base_rate + distance_km × per_km) × multiplier
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=['Public API'],
        summary="Estimate Shipping Cost",
        description=(
            "Calculates the estimated shipping cost from two plain-text addresses "
            "using real road distance (OSRM/OpenStreetMap). No API key or authentication required. "
            "Falls back to straight-line × 1.3 road correction if the routing service is unavailable."
        ),
        request=inline_serializer('CostEstimateRequest', {
            'pickup_state': serializers.CharField(help_text="e.g. 'Kano'"),
            'pickup_lga': serializers.CharField(help_text="e.g. 'Kano Municipal'"),
            'delivery_state': serializers.CharField(help_text="e.g. 'Lagos'"),
            'delivery_lga': serializers.CharField(help_text="e.g. 'Ikeja'"),
            'cargo_priority': serializers.ChoiceField(
                choices=['standard', 'express', 'same_day'],
                default='standard',
                help_text="Shipping priority tier (affects price multiplier)"
            ),
        }),
        responses={
            200: get_envelope_serializer('CostEstimateResponse', inline_serializer('CostEstimate', {
                'estimated_cost':      serializers.FloatField(),
                'base_rate':           serializers.FloatField(),
                'distance_charge':     serializers.FloatField(),
                'distance_km':         serializers.FloatField(),
                'priority_multiplier': serializers.FloatField(),
                'cargo_priority':      serializers.CharField(),
                'pickup_state':        serializers.CharField(),
                'pickup_lga':          serializers.CharField(),
                'delivery_state':      serializers.CharField(),
                'delivery_lga':        serializers.CharField(),
                'distance_method':     serializers.CharField(
                    help_text="'osrm' = actual road routing | 'haversine' = straight-line fallback"
                ),
            })),
            400: OpenApiResponse(description="Validation error or unresolvable address"),
            503: OpenApiResponse(description="Geocoding service temporarily unavailable"),
        }
    )
    def post(self, request, *args, **kwargs):
        # ── 1. Input validation ──────────────────────────────────────────────
        pickup_state   = (request.data.get('pickup_state')   or '').strip()
        pickup_lga     = (request.data.get('pickup_lga')     or '').strip()
        delivery_state = (request.data.get('delivery_state') or '').strip()
        delivery_lga   = (request.data.get('delivery_lga')   or '').strip()
        cargo_priority = (request.data.get('cargo_priority') or 'standard').strip()

        errors = {}

        if not pickup_state:
            errors['pickup_state'] = ['This field is required.']
        if not pickup_lga:
            errors['pickup_lga'] = ['This field is required.']
        if not delivery_state:
            errors['delivery_state'] = ['This field is required.']
        if not delivery_lga:
            errors['delivery_lga'] = ['This field is required.']

        # Validate against known states if provided
        import os
        import json
        from django.conf import settings
        path = os.path.join(settings.BASE_DIR, 'public_api', 'data', 'nigeria_states.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                states_data = json.load(f)
            states_map = {item['state'].lower(): [lga.lower() for lga in item['lgas']] for item in states_data}
            
            if pickup_state and pickup_lga:
                if pickup_state.lower() not in states_map:
                    errors['pickup_state'] = ['Invalid state.']
                elif pickup_lga.lower() not in states_map[pickup_state.lower()]:
                    errors['pickup_lga'] = [f'Invalid LGA for {pickup_state}.']
                    
            if delivery_state and delivery_lga:
                if delivery_state.lower() not in states_map:
                    errors['delivery_state'] = ['Invalid state.']
                elif delivery_lga.lower() not in states_map[delivery_state.lower()]:
                    errors['delivery_lga'] = [f'Invalid LGA for {delivery_state}.']
        except Exception:
            pass # Skip validation if data file is missing/broken

        valid_priorities = ['standard', 'express', 'same_day']
        if cargo_priority not in valid_priorities:
            errors['cargo_priority'] = [f"Must be one of: {', '.join(valid_priorities)}."]

        if errors:
            return Response(
                {'success': False, 'message': 'Validation error.', 'errors': errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pickup_address = f"{pickup_lga}, {pickup_state}"
        delivery_address = f"{delivery_lga}, {delivery_state}"

        # Catch the trivial same-address case before hitting external services.
        if pickup_address.lower() == delivery_address.lower():
            return Response(
                {
                    'success': False,
                    'message': 'Pickup and delivery addresses must be different.',
                    'errors': {'delivery_lga': ['Must differ from pickup address.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 2. Geocode + distance resolution ────────────────────────────────
        try:
            distance_km, distance_method = resolve_distance(pickup_address, delivery_address)
        except ValueError as exc:
            # Unresolvable address — surface the specific message to the client.
            return Response(
                {'success': False, 'message': str(exc), 'errors': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            # Unexpected failure (network completely down, etc.)
            logger.error("resolve_distance failed unexpectedly: %s", exc, exc_info=True)
            return Response(
                {
                    'success': False,
                    'message': (
                        'The geocoding service is temporarily unavailable. '
                        'Please try again in a moment.'
                    ),
                    'errors': {},
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # ── 3. Pricing calculation ───────────────────────────────────────────
        settings = PlatformSettings.get_settings()

        multiplier_map = {
            'standard': 1.0,
            'express':  float(settings.express_multiplier),
            'same_day': float(settings.same_day_multiplier),
        }

        base_rate       = float(settings.base_rate)
        per_km          = float(settings.distance_surcharge_per_km)
        multiplier      = multiplier_map[cargo_priority]
        distance_charge = distance_km * per_km
        estimated_cost  = (base_rate + distance_charge) * multiplier

        data = {
            'estimated_cost':      round(estimated_cost, 2),
            'base_rate':           base_rate,
            'distance_charge':     round(distance_charge, 2),
            'distance_km':         distance_km,
            'priority_multiplier': multiplier,
            'cargo_priority':      cargo_priority,
            'pickup_state':        pickup_state,
            'pickup_lga':          pickup_lga,
            'delivery_state':      delivery_state,
            'delivery_lga':        delivery_lga,
            'distance_method':     distance_method,
        }

        return success_response('Cost estimate calculated successfully.', data=data)


class PublicPlatformStatsView(APIView):
    """
    GET /api/v1/public/stats/

    Returns high-level platform statistics for the public marketing page.
    No authentication required.
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=['Public API'],
        summary="Get Public Platform Statistics",
        description=(
            "Retrieves high-level statistics shown on the public marketing site: "
            "deliveries completed, states served, and customer rating."
        ),
        responses={200: get_envelope_serializer('PublicStatsResponse', inline_serializer('PublicStats', {
            'deliveries_completed': serializers.CharField(),
            'states_served': serializers.CharField(),
            'customer_rating': serializers.CharField(),
        }))}
    )
    def get(self, request, *args, **kwargs):
        from django.db.models import Avg
        deliveries_completed = Order.objects.filter(status=Order.Status.COMPLETED).count()
        
        avg_rating = Review.objects.aggregate(Avg('rating'))['rating__avg']
        rating_str = f"{avg_rating:.1f} / 5" if avg_rating is not None else "5.0 / 5"

        data = {
            "deliveries_completed": deliveries_completed if deliveries_completed > 500 else "500+",
            "states_served": "32+",       # Updated periodically as coverage expands
            "customer_rating": rating_str,
        }

        return success_response('Platform stats retrieved.', data=data)


class PublicLocationsView(APIView):
    """
    GET /api/v1/public/locations/

    Returns the list of Nigerian states and their LGAs from a static JSON file.
    Optional query param: `?state=Lagos` to filter by state.
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=['Public API'],
        summary="Get Nigerian States and LGAs",
        description="Returns a list of Nigerian states and their Local Government Areas. Used for populating frontend location pickers.",
        responses={
            200: OpenApiResponse(description="Returns a list of state objects or a single state object if filtered.")
        }
    )
    def get(self, request, *args, **kwargs):
        import os, json
        from django.conf import settings

        file_path = os.path.join(settings.BASE_DIR, 'public_api', 'data', 'nigeria_states.json')
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return Response(
                {'success': False, 'message': 'Location data not found.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        state_query = request.query_params.get('state', '').strip().lower()

        if state_query:
            # Filter by state name (case-insensitive)
            filtered = [s for s in data if s.get('state', '').lower() == state_query]
            if filtered:
                return success_response('Locations retrieved successfully.', data=filtered[0])
            else:
                return Response(
                    {'success': False, 'message': 'State not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )

        return success_response('Locations retrieved successfully.', data=data)


class PublicTrackingView(RetrieveAPIView):
    """
    GET /api/v1/public/track/{tracking_number}/

    Retrieves order status and timeline using a tracking number.
    No authentication required.
    """
    permission_classes = []
    authentication_classes = []
    serializer_class = PublicTrackingSerializer
    lookup_field = 'tracking_number'

    @extend_schema(
        tags=['Public API'],
        summary="Track a Shipment",
        description=(
            "Look up the current status, origin, destination, and full timeline of a "
            "shipment using its tracking number (e.g. AGT12345678). "
            "No authentication is required."
        ),
        responses={
            200: get_envelope_serializer('PublicTrackingResponse', PublicTrackingSerializer()),
            404: OpenApiResponse(description="Tracking number not found"),
        }
    )
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def get_queryset(self):
        return Order.objects.prefetch_related('timeline').all()

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            return Response(
                {'success': False, 'message': 'Shipment not found. Please check your tracking number.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(instance)
        return success_response('Shipment found.', data=serializer.data)


class PublicCompleteDeliveryView(APIView):
    """
    POST /api/v1/public/track/{tracking_number}/complete/

    Completes a delivery via the public API using a Delivery PIN and a photo.
    This acts as a secure Proof of Delivery for drivers using the public web app.
    """
    permission_classes = []
    authentication_classes = []

    @extend_schema(
        tags=['Public API'],
        summary="Secure Proof of Delivery",
        description="Allows a driver to mark an order as completed by submitting the receiver's secret Delivery PIN along with a proof-of-delivery photo. No authentication required. Note: The order must be in the 'delivered' status first.",
        request=inline_serializer('PublicPODRequest', {
            'delivery_pin': serializers.CharField(required=True, help_text="The 4-digit PIN given to the receiver"),
            'proof_of_delivery': serializers.ImageField(required=True)
        }),
        responses={
            200: OpenApiResponse(description="Delivery completed successfully"),
            400: OpenApiResponse(description="Invalid PIN, invalid state, or missing fields"),
            404: OpenApiResponse(description="Tracking number not found")
        }
    )
    def post(self, request, tracking_number, *args, **kwargs):
        try:
            order = Order.objects.get(tracking_number=tracking_number)
        except Order.DoesNotExist:
            return Response(
                {'success': False, 'message': 'Shipment not found. Please check your tracking number.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if order.status != Order.Status.DELIVERED:
            return Response(
                {'success': False, 'message': f"Order must be marked as DELIVERED before it can be completed with a PIN. Current status: {order.get_status_display()}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        pin = request.data.get('delivery_pin')
        image = request.FILES.get('proof_of_delivery')

        if not pin or not image:
            return Response(
                {'success': False, 'message': 'Both delivery_pin and proof_of_delivery (image) are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if str(pin).strip() != order.delivery_pin:
            return Response(
                {'success': False, 'message': 'Invalid Delivery PIN.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the order
        order.proof_of_delivery = image
        order.status = Order.Status.COMPLETED
        order.save()

        return success_response('Proof of delivery submitted. Order completed successfully.')
