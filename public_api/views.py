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
            'pickup_address': serializers.CharField(
                help_text="Full pickup address, e.g. 'Kano City, Kano State'"
            ),
            'delivery_address': serializers.CharField(
                help_text="Full delivery address, e.g. 'Mile 12 Market, Lagos'"
            ),
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
                'pickup_address':      serializers.CharField(),
                'delivery_address':    serializers.CharField(),
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
        pickup_address   = (request.data.get('pickup_address')   or '').strip()
        delivery_address = (request.data.get('delivery_address') or '').strip()
        cargo_priority   = (request.data.get('cargo_priority')   or 'standard').strip()

        errors = {}

        if not pickup_address:
            errors['pickup_address'] = ['This field is required.']
        elif len(pickup_address) < 3:
            errors['pickup_address'] = ['Please provide a more specific address.']

        if not delivery_address:
            errors['delivery_address'] = ['This field is required.']
        elif len(delivery_address) < 3:
            errors['delivery_address'] = ['Please provide a more specific address.']

        valid_priorities = ['standard', 'express', 'same_day']
        if cargo_priority not in valid_priorities:
            errors['cargo_priority'] = [f"Must be one of: {', '.join(valid_priorities)}."]

        if errors:
            return Response(
                {'success': False, 'message': 'Validation error.', 'errors': errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Catch the trivial same-address case before hitting external services.
        if pickup_address.lower() == delivery_address.lower():
            return Response(
                {
                    'success': False,
                    'message': 'Pickup and delivery addresses must be different.',
                    'errors': {'delivery_address': ['Must differ from pickup address.']},
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
            'pickup_address':      pickup_address,
            'delivery_address':    delivery_address,
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
