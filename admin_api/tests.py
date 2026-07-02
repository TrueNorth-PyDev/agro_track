from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class AdminAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@agrotrack.ng', password='AdminPass99!', role=User.Role.ADMIN
        )
        self.sender = User.objects.create_user(
            email='sender@test.com', password='TestPass1!', role=User.Role.SENDER, full_name='Test Sender'
        )
        self.dispatcher = User.objects.create_user(
            email='disp@test.com', password='TestPass2!', role=User.Role.DISPATCHER, full_name='Test Disp', territory='South'
        )
        self.client.force_authenticate(user=self.admin)
        
    def test_dashboard_access(self):
        url = reverse('admin_api:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('overview_metrics', response.data['data'])
        self.assertIn('growth_trend', response.data['data'])
        
    def test_user_list(self):
        url = reverse('admin_api:user-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only list SENDER roles
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['email'], 'sender@test.com')
        
    def test_suspend_user(self):
        url = reverse('admin_api:user-detail', kwargs={'pk': self.sender.id})
        response = self.client.patch(url, {'is_active': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.sender.refresh_from_db()
        self.assertFalse(self.sender.is_active)
        
    def test_dispatcher_list(self):
        url = reverse('admin_api:dispatcher-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['territory'], 'South')
        
    def test_create_dispatcher(self):
        url = reverse('admin_api:dispatcher-list')
        response = self.client.post(url, {
            'full_name': 'New Dispatcher',
            'email': 'newdisp@test.com',
            'territory': 'North',
            'phone_number': '1234567890'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='newdisp@test.com').exists())
        
    def test_update_dispatcher_territory(self):
        url = reverse('admin_api:dispatcher-detail', kwargs={'pk': self.dispatcher.id})
        response = self.client.patch(url, {'territory': 'East'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.dispatcher.refresh_from_db()
        self.assertEqual(self.dispatcher.territory, 'East')

    def test_list_drivers(self):
        from orders.models import Driver
        Driver.objects.create(name="Eze Chukwudi", phone="08031112222", is_verified=True)
        url = reverse('admin_api:driver-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertTrue(response.data['data'][0]['is_verified'])

    def test_create_driver(self):
        url = reverse('admin_api:driver-list')
        response = self.client.post(url, {
            'first_name': 'Austin',
            'last_name': 'Power',
            'phone': '08123456789',
            'email': 'austin@test.com'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['name'], 'Austin Power')
        self.assertFalse(response.data['data']['is_verified'])

    def test_update_driver_verification(self):
        from orders.models import Driver
        driver = Driver.objects.create(name="Pending Driver", is_verified=False)
        url = reverse('admin_api:driver-detail', kwargs={'pk': driver.pk})
        response = self.client.patch(url, {'is_verified': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver.refresh_from_db()
        self.assertTrue(driver.is_verified)

    def test_list_vehicles(self):
        from orders.models import Vehicle
        Vehicle.objects.create(registration_number="XYZ-123", capacity_tonnes=10.0)
        url = reverse('admin_api:vehicle-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)

    def test_create_vehicle(self):
        url = reverse('admin_api:vehicle-list')
        response = self.client.post(url, {
            'registration_number': 'ABC-456',
            'make_model': 'Toyota Hilux',
            'capacity_tonnes': 5.0,
            'status': 'available'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['registration_number'], 'ABC-456')

    def test_update_platform_settings(self):
        url = reverse('admin_api:platform-settings')
        response = self.client.patch(url, {'base_rate': '20000.00', 'notify_new_request': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data['data']['base_rate']), 20000.00)
        self.assertFalse(response.data['data']['notify_new_request'])

    def test_platform_analytics(self):
        url = reverse('admin_api:platform-analytics')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('kpis', response.data['data'])
        self.assertIn('revenue_trend', response.data['data'])
