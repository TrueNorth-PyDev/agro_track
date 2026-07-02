from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from orders.models import Order

User = get_user_model()

class PublicAPITests(APITestCase):
    def setUp(self):
        # Create a sender user to associate with the order
        self.sender = User.objects.create_user(
            email='sender@test.com',
            password='password123',
            full_name='Test Sender',
            role='sender'
        )
        
        self.order = Order.objects.create(
            sender=self.sender,
            pickup_address='Lagos',
            pickup_contact_name='John',
            pickup_phone='08011112222',
            delivery_address='Abuja',
            delivery_name='Jane',
            delivery_phone='08033334444',
            cargo_type='Produce',
            cargo_weight=500.0,
            cargo_value=10000.0
        )
        
        # Complete a few orders to test stats
        Order.objects.create(
            sender=self.sender,
            status=Order.Status.COMPLETED,
            pickup_address='Kano', pickup_contact_name='Dan', pickup_phone='123',
            delivery_address='Kaduna', delivery_name='Joe', delivery_phone='123',
            cargo_type='Grain', cargo_weight=10, cargo_value=100
        )

    def test_get_platform_stats(self):
        url = reverse('public_api:stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('deliveries_completed', response.data['data'])
        self.assertEqual(response.data['data']['deliveries_completed'], '500+')
        self.assertEqual(response.data['data']['states_served'], '32+')
        
    def test_get_public_tracking(self):
        url = reverse('public_api:track', kwargs={'tracking_number': self.order.tracking_number})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['tracking_number'], self.order.tracking_number)
        self.assertIn('timeline', response.data['data'])
        
    def test_get_public_tracking_not_found(self):
        url = reverse('public_api:track', kwargs={'tracking_number': 'AGT-INVALID'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
