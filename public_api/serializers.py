from rest_framework import serializers
from orders.models import Order, OrderStatusHistory

class PublicOrderHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ['status', 'description', 'timestamp']

class PublicTrackingSerializer(serializers.ModelSerializer):
    timeline = PublicOrderHistorySerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'tracking_number', 'status', 'status_display', 'current_location', 
            'estimated_delivery_date', 'pickup_address', 'delivery_address', 
            'pickup_contact_name', 'delivery_name', 'created_at', 'timeline'
        ]
