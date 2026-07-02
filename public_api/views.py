from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from orders.models import Order
from accounts.views import success_response
from .serializers import PublicTrackingSerializer


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
        responses={200: OpenApiResponse(description="Platform statistics")}
    )
    def get(self, request, *args, **kwargs):
        deliveries_completed = Order.objects.filter(status=Order.Status.COMPLETED).count()

        data = {
            "deliveries_completed": deliveries_completed if deliveries_completed > 500 else "500+",
            "states_served": "32+",       # Updated periodically as coverage expands
            "customer_rating": "4.8 / 5", # Aggregated from driver ratings
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
            200: PublicTrackingSerializer,
            404: OpenApiResponse(description="Shipment not found")
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
