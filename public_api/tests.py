from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock
from orders.models import Order
from admin_api.models import PlatformSettings

User = get_user_model()

ESTIMATE_URL = '/api/v1/public/estimate/'


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


# ---------------------------------------------------------------------------
# Geo module unit tests
# ---------------------------------------------------------------------------

class GeoModuleTests(APITestCase):
    """Unit tests for public_api.geo — all external HTTP calls are mocked."""

    def _make_nominatim_response(self, lat, lon):
        """Build a minimal Nominatim-style JSON response."""
        import json
        return json.dumps([{"lat": str(lat), "lon": str(lon)}]).encode("utf-8")

    def _make_osrm_response(self, distance_m):
        import json
        return json.dumps({
            "code": "Ok",
            "routes": [{"distance": distance_m, "duration": 3600}]
        }).encode("utf-8")

    def _mock_urlopen(self, responses):
        """
        Returns a context manager mock that yields successive byte responses
        for each call to urlopen.
        """
        mock_responses = []
        for raw_bytes in responses:
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read = MagicMock(return_value=raw_bytes)
            mock_responses.append(cm)
        return mock_responses

    @patch('urllib.request.urlopen')
    def test_geocode_success(self, mock_urlopen):
        from public_api.geo import geocode
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.read = MagicMock(return_value=self._make_nominatim_response(6.5244, 3.3792))
        mock_urlopen.return_value = cm

        result = geocode("Lagos Island")
        self.assertIsNotNone(result)
        lat, lon = result
        self.assertAlmostEqual(lat, 6.5244)
        self.assertAlmostEqual(lon, 3.3792)

    @patch('urllib.request.urlopen')
    def test_geocode_empty_result(self, mock_urlopen):
        """Nominatim returning [] should yield None, not crash."""
        from public_api.geo import geocode
        import json
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.read = MagicMock(return_value=json.dumps([]).encode("utf-8"))
        mock_urlopen.return_value = cm

        result = geocode("Nowhere Place XYZ123")
        self.assertIsNone(result)

    @patch('urllib.request.urlopen')
    def test_road_distance_osrm_success(self, mock_urlopen):
        from public_api.geo import road_distance_km
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.read = MagicMock(return_value=self._make_osrm_response(530_000))  # 530 km
        mock_urlopen.return_value = cm

        result = road_distance_km((9.0579, 7.4951), (6.5244, 3.3792))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 530.0)

    @patch('urllib.request.urlopen')
    def test_road_distance_osrm_non_ok(self, mock_urlopen):
        """OSRM 'NoRoute' code should return None, not crash."""
        from public_api.geo import road_distance_km
        import json
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.read = MagicMock(return_value=json.dumps({"code": "NoRoute", "routes": []}).encode())
        mock_urlopen.return_value = cm

        result = road_distance_km((9.0579, 7.4951), (6.5244, 3.3792))
        self.assertIsNone(result)

    def test_haversine_lagos_abuja(self):
        """Haversine Lagos→Abuja should be roughly 530 km road estimate."""
        from public_api.geo import haversine_km
        # Lagos ≈ (6.52, 3.38), Abuja ≈ (9.06, 7.50)
        result = haversine_km((6.52, 3.38), (9.06, 7.50))
        # Straight-line ≈ 411 km × 1.3 ≈ 534 km
        self.assertGreater(result, 400)
        self.assertLess(result, 700)

    def test_haversine_same_city(self):
        """Very small distances should still be positive."""
        from public_api.geo import haversine_km
        # Ikeja to Surulere — about 15 km apart
        result = haversine_km((6.604, 3.349), (6.505, 3.355))
        self.assertGreater(result, 0)
        self.assertLess(result, 50)


# ---------------------------------------------------------------------------
# Cost estimate endpoint integration tests (mocked geo calls)
# ---------------------------------------------------------------------------

class CostEstimateTests(APITestCase):

    def setUp(self):
        # Ensure platform settings exist with known defaults
        PlatformSettings.objects.get_or_create(pk=1)

    def _patch_resolve(self, distance_km=530.0, method='osrm'):
        return patch('public_api.views.resolve_distance', return_value=(distance_km, method))

    def test_missing_pickup_address(self):
        response = self.client.post(ESTIMATE_URL, {
            'delivery_address': 'Abuja, FCT',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('pickup_address', response.data['errors'])

    def test_missing_delivery_address(self):
        response = self.client.post(ESTIMATE_URL, {
            'pickup_address': 'Lagos Island',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('delivery_address', response.data['errors'])

    def test_invalid_priority(self):
        with self._patch_resolve():
            response = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'Lagos Island',
                'delivery_address': 'Kano City',
                'cargo_priority':   'ultra_fast',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cargo_priority', response.data['errors'])

    def test_same_address_rejected(self):
        response = self.client.post(ESTIMATE_URL, {
            'pickup_address':   'Lagos Island',
            'delivery_address': 'Lagos Island',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('delivery_address', response.data['errors'])

    def test_successful_estimate_standard(self):
        with self._patch_resolve(530.0, 'osrm'):
            response = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'Lagos Island, Lagos',
                'delivery_address': 'Abuja, FCT',
                'cargo_priority':   'standard',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertIn('estimated_cost', data)
        self.assertIn('distance_km', data)
        self.assertEqual(data['distance_km'], 530.0)
        self.assertEqual(data['distance_method'], 'osrm')
        self.assertEqual(data['cargo_priority'], 'standard')
        self.assertEqual(data['priority_multiplier'], 1.0)
        self.assertGreater(data['estimated_cost'], 0)

    def test_successful_estimate_express_costs_more(self):
        with self._patch_resolve(530.0, 'osrm'):
            standard = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'Kano City, Kano',
                'delivery_address': 'Port Harcourt, Rivers',
                'cargo_priority':   'standard',
            }, format='json').data['data']['estimated_cost']

        with self._patch_resolve(530.0, 'osrm'):
            express = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'Kano City, Kano',
                'delivery_address': 'Port Harcourt, Rivers',
                'cargo_priority':   'express',
            }, format='json').data['data']['estimated_cost']

        self.assertGreater(express, standard)

    def test_haversine_fallback_still_returns_estimate(self):
        """If OSRM is down, haversine fallback should still return a valid estimate."""
        with self._patch_resolve(411.0, 'haversine'):
            response = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'Enugu, Enugu State',
                'delivery_address': 'Abuja, FCT',
                'cargo_priority':   'standard',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['distance_method'], 'haversine')
        self.assertGreater(response.data['data']['estimated_cost'], 0)

    def test_unresolvable_address_returns_400(self):
        with patch('public_api.views.resolve_distance', side_effect=ValueError("Could not locate pickup address")):
            response = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'XYZXYZ999 Nonexistent Place',
                'delivery_address': 'Abuja, FCT',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('locate', response.data['message'])

    def test_service_unavailable_returns_503(self):
        with patch('public_api.views.resolve_distance', side_effect=Exception("Connection refused")):
            response = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'Lagos Island',
                'delivery_address': 'Abuja, FCT',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_intrastate_trip_works(self):
        """Same-state trips (e.g. Ikeja to Surulere) should resolve fine."""
        with self._patch_resolve(22.0, 'osrm'):
            response = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'Ikeja, Lagos',
                'delivery_address': 'Surulere, Lagos',
                'cargo_priority':   'standard',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['distance_km'], 22.0)

    def test_response_contains_all_fields(self):
        with self._patch_resolve(300.0, 'osrm'):
            response = self.client.post(ESTIMATE_URL, {
                'pickup_address':   'Ibadan, Oyo State',
                'delivery_address': 'Benin City, Edo State',
            }, format='json')
        data = response.data['data']
        required_fields = [
            'estimated_cost', 'base_rate', 'distance_charge',
            'distance_km', 'priority_multiplier', 'cargo_priority',
            'pickup_address', 'delivery_address', 'distance_method',
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Missing field: {field}")
