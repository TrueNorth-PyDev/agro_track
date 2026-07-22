from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.models import User
from .models import Order, Driver, Vehicle, OrderStatusHistory, OrderMessage, Review


def make_user(email='test@example.com', verified=True):
    return User.objects.create_user(
        email=email,
        password='TestPass99!',
        full_name='Test User',
        is_active=verified,
        is_verified=verified,
    )


class OrderTests(APITestCase):
    def setUp(self):
        self.user = make_user(email='sender@example.com')
        self.other_user = make_user(email='other@example.com')

        self.client.force_authenticate(user=self.user)

        self.valid_payload = {
            'pickup_address': 'Plot 204, Nitel Industrial Avenue',
            'pickup_contact_name': 'John Doe',
            'pickup_phone': '+2348000000000',
            'pickup_date': '2026-07-10',
            'pickup_notes': 'Gate code is 1234',

            'delivery_address': 'Plot 204, Waterline Zone Estate',
            'delivery_name': 'Jane Smith',
            'delivery_phone': '+2348000000001',
            'delivery_email': 'jane@example.com',

            'cargo_type': 'Grains & Cereals',
            'cargo_weight': '500.00',
            'cargo_value': '250000.00',
            'cargo_priority': 'standard',

            'base_rate': '15000.00',
            'distance_surcharge': '4500.00',
            'total_cost': '19500.00'
        }

    def test_create_order(self):
        url = reverse('orders:order-list')
        response = self.client.post(url, self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])

        order_data = response.data['data']
        self.assertIn('tracking_number', order_data)
        self.assertEqual(order_data['cargo_type'], 'Grains & Cereals')
        self.assertEqual(order_data['status'], Order.Status.NEW_REQUEST)

        # Verify in DB
        order = Order.objects.get(id=order_data['id'])
        self.assertEqual(order.sender, self.user)

    def test_create_order_generates_timeline_entry(self):
        """Creating an order should auto-generate a 'Order Placed' timeline entry."""
        url = reverse('orders:order-list')
        response = self.client.post(url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        order = Order.objects.get(id=response.data['data']['id'])
        timeline = order.timeline.all()

        self.assertEqual(timeline.count(), 1)
        entry = timeline.first()
        self.assertEqual(entry.display_name, 'Order Placed')
        self.assertIn(self.user.full_name, entry.description)

    def test_list_orders(self):
        # Create one order for self
        Order.objects.create(sender=self.user, cargo_type='My Cargo', cargo_weight=10, cargo_value=100)
        # Create one order for other user
        Order.objects.create(sender=self.other_user, cargo_type='Other Cargo', cargo_weight=10, cargo_value=100)

        url = reverse('orders:order-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)

    def test_get_order_detail(self):
        order = Order.objects.create(sender=self.user, cargo_type='My Cargo', cargo_weight=10, cargo_value=100)
        url = reverse('orders:order-detail', kwargs={'pk': order.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['cargo_type'], 'My Cargo')

    def test_cannot_get_other_users_order(self):
        order = Order.objects.create(sender=self.other_user, cargo_type='Other Cargo', cargo_weight=10, cargo_value=100)
        url = reverse('orders:order-detail', kwargs={'pk': order.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TimelineDisplayNameTests(APITestCase):
    """
    Tests for the timeline display_name feature.
    Verifies that each status transition produces the correct human-readable title
    and contextual description in the shipment timeline.
    """

    def setUp(self):
        self.sender = make_user(email='sender_dn@example.com')
        self.sender.full_name = 'Ludwig Agro Farm'
        self.sender.save(update_fields=['full_name'])

        self.dispatcher = User.objects.create_user(
            email='dispatcher_dn@example.com',
            password='TestPass99!',
            role=User.Role.DISPATCHER,
            full_name='Vivi Akomolafe',
        )

        self.driver = Driver.objects.create(name='Eze Chukwudi', phone='+2341234567890')
        self.vehicle = Vehicle.objects.create(registration_number='ABC-123-KJ')

    def _create_order(self):
        return Order.objects.create(
            sender=self.sender,
            pickup_address='Enugu Agro Partners, Independence Layout, Enugu',
            pickup_contact_name='Contact Name',
            pickup_phone='+2340000000000',
            delivery_address='Alaba Farm Market, Trade Fair Complex, Lagos',
            delivery_name='Recipient Name',
            delivery_phone='+2340000000001',
            cargo_type='Grains',
            cargo_weight=100,
            cargo_value=500000,
        )

    def test_order_placed_display_name(self):
        order = self._create_order()
        entry = order.timeline.first()
        self.assertEqual(entry.display_name, 'Order Placed')
        self.assertIn('Ludwig Agro Farm', entry.description)

    def test_driver_vehicle_assigned_display_name(self):
        order = self._create_order()
        order.status = Order.Status.ASSIGNED
        order.driver = self.driver
        order.vehicle = self.vehicle
        order.save()

        entry = order.timeline.filter(display_name='Driver & Vehicle Assigned').first()
        self.assertIsNotNone(entry)
        self.assertIn('Eze Chukwudi', entry.description)
        self.assertIn('ABC-123-KJ', entry.description)

    def test_dispatcher_assigned_display_name(self):
        order = self._create_order()
        order.status = Order.Status.ASSIGNED
        order.dispatcher = self.dispatcher
        order.save()

        entry = order.timeline.filter(display_name='Dispatcher Assigned').first()
        self.assertIsNotNone(entry)
        self.assertIn('Vivi Akomolafe', entry.description)

    def test_pickup_confirmed_display_name(self):
        order = self._create_order()
        order.status = Order.Status.ASSIGNED
        order.save()

        order.status = Order.Status.PENDING_PICKUP
        order.save()

        entry = order.timeline.filter(display_name='Pickup Confirmed').first()
        self.assertIsNotNone(entry)
        # Description should reference the first segment of pickup_address
        self.assertIn('Enugu Agro Partners', entry.description)

    def test_in_transit_display_name(self):
        order = self._create_order()
        order.status = Order.Status.IN_TRANSIT
        order.current_location = 'Benin City'
        order.save()

        entry = order.timeline.filter(display_name='In Transit').first()
        self.assertIsNotNone(entry)
        self.assertIn('Benin City', entry.description)

    def test_location_update_display_name(self):
        order = self._create_order()
        order.status = Order.Status.IN_TRANSIT
        order.current_location = 'Benin City'
        order.save()

        # Simulate a location update while still in transit
        order.current_location = 'Ibadan'
        order.save()

        update_entry = order.timeline.filter(display_name='Location Update').first()
        self.assertIsNotNone(update_entry)
        self.assertIn('Ibadan', update_entry.description)

    def test_delivered_display_name(self):
        order = self._create_order()
        order.status = Order.Status.DELIVERED
        order.save()

        entry = order.timeline.filter(display_name='Delivered').first()
        self.assertIsNotNone(entry)
        self.assertIn('Recipient Name', entry.description)

    def test_completed_display_name(self):
        order = self._create_order()
        order.status = Order.Status.COMPLETED
        order.save()

        entry = order.timeline.filter(display_name='Completed').first()
        self.assertIsNotNone(entry)

    def test_timeline_serializer_includes_display_name(self):
        """Verify the API response includes display_name in each timeline event."""
        self.client.force_authenticate(user=self.sender)
        order = self._create_order()
        url = reverse('orders:order-detail', kwargs={'pk': order.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        timeline = response.data['data']['timeline']
        self.assertGreater(len(timeline), 0)
        first_event = timeline[0]
        self.assertIn('display_name', first_event)
        self.assertEqual(first_event['display_name'], 'Order Placed')

    def test_old_rows_fallback_to_status_display(self):
        """Rows with blank display_name fall back gracefully to the status label."""
        order = self._create_order()
        # Manually create a legacy-style entry with no display_name
        legacy = OrderStatusHistory.objects.create(
            order=order,
            status=Order.Status.IN_TRANSIT,
            display_name='',  # simulates pre-migration row
            description='Shipment is in transit',
        )
        from orders.serializers import OrderStatusHistorySerializer
        data = OrderStatusHistorySerializer(legacy).data
        self.assertEqual(data['display_name'], 'In Transit')  # falls back to get_status_display()


class DashboardTests(APITestCase):
    def setUp(self):
        self.user = make_user(email='dashboard@example.com')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('orders:dashboard')

    def test_dashboard_no_orders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['data']['active_shipment'])
        self.assertEqual(response.data['data']['recent_shipments'], [])

    def test_dashboard_with_active_shipment(self):
        active = Order.objects.create(sender=self.user, status=Order.Status.IN_TRANSIT, cargo_weight=10, cargo_value=10)
        Order.objects.create(sender=self.user, status=Order.Status.COMPLETED, cargo_weight=10, cargo_value=10)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Active shipment should be the IN_TRANSIT one
        self.assertEqual(response.data['data']['active_shipment']['id'], active.id)

        # Both should be in recent_shipments since recent is just latest 5
        self.assertEqual(len(response.data['data']['recent_shipments']), 2)


class FleetOverviewTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            email='dispatcher@example.com', password='TestPass99!', role=User.Role.DISPATCHER
        )
        self.sender = make_user(email='sender2@example.com')
        self.client.force_authenticate(user=self.dispatcher)

        self.driver1 = Driver.objects.create(name='Saliu', trips_completed=10, rating=4.5)
        self.driver2 = Driver.objects.create(name='Eze', trips_completed=20, rating=4.9)

        self.vehicle1 = Vehicle.objects.create(registration_number='ABC-123', assigned_driver=self.driver1)
        self.vehicle2 = Vehicle.objects.create(registration_number='XYZ-456', assigned_driver=self.driver2)

    def test_fleet_overview(self):
        url = reverse('orders:fleet-overview')

        # Initially, all are available
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['total_on_duty'], 0)
        self.assertEqual(response.data['data']['total_available'], 2)
        self.assertEqual(len(response.data['data']['vehicles']), 2)

        # Create an order and assign vehicle1 to it (On Duty)
        Order.objects.create(
            sender=self.sender,
            status=Order.Status.IN_TRANSIT,
            vehicle=self.vehicle1,
            driver=self.driver1,
            cargo_weight=10, cargo_value=10
        )

        response = self.client.get(url)
        self.assertEqual(response.data['data']['total_on_duty'], 1)
        self.assertEqual(response.data['data']['total_available'], 1)

    def test_driver_list_status(self):
        url = reverse('orders:driver-list')

        # Initially available
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        drivers = response.data['data']
        for d in drivers:
            self.assertEqual(d['current_status'], 'Available')

        # Assign driver1 to an active order
        Order.objects.create(
            sender=self.sender,
            status=Order.Status.IN_TRANSIT,
            driver=self.driver1,
            cargo_weight=10, cargo_value=10
        )

        response = self.client.get(url)
        drivers = response.data['data']
        # One driver should be On Trip, the other Available
        statuses = [d['current_status'] for d in drivers]
        self.assertIn('On Trip', statuses)
        self.assertIn('Available', statuses)


class ReportsTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            email='dispatcher3@example.com', password='TestPass99!', role=User.Role.DISPATCHER
        )
        self.sender = make_user(email='sender3@example.com')
        self.client.force_authenticate(user=self.dispatcher)

    def test_reports_view_mock_data(self):
        url = reverse('orders:reports')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

        data = response.data['data']
        self.assertIn('summary_metrics', data)
        self.assertIn('delivery_trend', data)
        self.assertIn('fleet_utilisation_chart', data)
        self.assertIn('revenue_insights', data)

        # We expect mock data since we have 0 deliveries
        self.assertEqual(data['summary_metrics']['total_deliveries']['value'], 35)
        self.assertEqual(len(data['delivery_trend']), 6)


class ChatSystemTests(APITestCase):
    """
    Tests for the order chat system:
      - GET /api/v1/orders/{id}/messages/  (chat_info, messages, unread_count)
      - POST /api/v1/orders/{id}/messages/ (send message)
      - POST /api/v1/orders/{id}/messages/read/ (mark as read)
    """

    def setUp(self):
        self.sender = make_user(email='chat_sender@example.com')
        self.sender.full_name = 'Ephraim Okon'
        self.sender.save(update_fields=['full_name'])

        self.dispatcher = User.objects.create_user(
            email='chat_dispatcher@example.com',
            password='TestPass99!',
            role=User.Role.DISPATCHER,
            full_name='Lade Akomolafe',
            is_active=True,
            is_verified=True,
        )

        self.other_dispatcher = User.objects.create_user(
            email='other_dispatcher@example.com',
            password='TestPass99!',
            role=User.Role.DISPATCHER,
            full_name='Other Person',
        )

        # Order with dispatcher assigned
        self.order = Order.objects.create(
            sender=self.sender,
            dispatcher=self.dispatcher,
            status=Order.Status.IN_TRANSIT,
            cargo_type='Rice',
            cargo_weight=50,
            cargo_value=100000,
        )

        self.messages_url = reverse('orders:order-messages', kwargs={'pk': self.order.id})
        self.mark_read_url = reverse('orders:order-messages-mark-read', kwargs={'pk': self.order.id})

    # ── GET messages ──────────────────────────────────────────────────────────

    def test_sender_can_get_chat_messages(self):
        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.messages_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertIn('chat_info', data)
        self.assertIn('messages', data)
        self.assertIn('unread_count', data)

    def test_dispatcher_can_get_chat_messages(self):
        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(self.messages_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unrelated_dispatcher_cannot_access_chat(self):
        """A dispatcher not assigned to this order should be denied."""
        self.client.force_authenticate(user=self.other_dispatcher)
        response = self.client.get(self.messages_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_chat_info_other_party_for_sender(self):
        """When sender views chat, other_party should be the dispatcher."""
        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.messages_url)
        other_party = response.data['data']['chat_info']['other_party']
        self.assertEqual(other_party['name'], 'Lade Akomolafe')
        self.assertEqual(other_party['initials'], 'L')
        self.assertEqual(other_party['role'], 'dispatcher')

    def test_chat_info_other_party_for_dispatcher(self):
        """When dispatcher views chat, other_party should be the sender."""
        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(self.messages_url)
        other_party = response.data['data']['chat_info']['other_party']
        self.assertEqual(other_party['name'], 'Ephraim Okon')
        self.assertEqual(other_party['initials'], 'E')
        self.assertEqual(other_party['role'], 'sender')

    # ── Message fields ────────────────────────────────────────────────────────

    def test_message_has_sender_initials_and_is_own_message(self):
        """Messages include sender_initials and correct is_own_message."""
        # Dispatcher sends a message
        OrderMessage.objects.create(
            order=self.order,
            sender=self.dispatcher,
            content='Thank you for reaching out. How may we help you today?',
        )

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.messages_url)
        messages = response.data['data']['messages']
        self.assertEqual(len(messages), 1)

        msg = messages[0]
        self.assertIn('sender_initials', msg)
        self.assertIn('is_own_message', msg)
        self.assertEqual(msg['sender_initials'], 'L')   # Lade
        self.assertFalse(msg['is_own_message'])          # sender is viewing, not the dispatcher

    def test_is_own_message_true_for_own_messages(self):
        OrderMessage.objects.create(
            order=self.order,
            sender=self.sender,
            content='I need to log a complaint.',
        )
        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.messages_url)
        msg = response.data['data']['messages'][0]
        self.assertTrue(msg['is_own_message'])
        self.assertEqual(msg['sender_initials'], 'E')   # Ephraim

    # ── POST message ──────────────────────────────────────────────────────────

    def test_sender_can_post_message(self):
        self.client.force_authenticate(user=self.sender)
        payload = {'content': 'I need to log a complaint regarding a shipment.'}
        response = self.client.post(self.messages_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(OrderMessage.objects.filter(order=self.order).count(), 1)

    def test_dispatcher_can_post_message(self):
        self.client.force_authenticate(user=self.dispatcher)
        payload = {'content': 'Thank you for reaching out. How may we help you today?'}
        response = self.client.post(self.messages_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unrelated_dispatcher_cannot_post_message(self):
        self.client.force_authenticate(user=self.other_dispatcher)
        payload = {'content': 'I should not be able to send this.'}
        response = self.client.post(self.messages_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Unread count ──────────────────────────────────────────────────────────

    def test_unread_count_reflects_unread_messages(self):
        # Dispatcher sends 2 messages (sender hasn't read them)
        OrderMessage.objects.create(order=self.order, sender=self.dispatcher, content='Message 1')
        OrderMessage.objects.create(order=self.order, sender=self.dispatcher, content='Message 2')

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.messages_url)
        self.assertEqual(response.data['data']['unread_count'], 2)

    def test_unread_count_ignores_own_messages(self):
        """Your own sent messages don't count as unread."""
        OrderMessage.objects.create(order=self.order, sender=self.sender, content='My own message')

        self.client.force_authenticate(user=self.sender)
        response = self.client.get(self.messages_url)
        self.assertEqual(response.data['data']['unread_count'], 0)

    # ── Mark read ─────────────────────────────────────────────────────────────

    def test_mark_read_bulk_updates_messages(self):
        """POST /messages/read/ marks the other party's messages as read."""
        OrderMessage.objects.create(order=self.order, sender=self.dispatcher, content='Hey 1')
        OrderMessage.objects.create(order=self.order, sender=self.dispatcher, content='Hey 2')
        OrderMessage.objects.create(order=self.order, sender=self.sender, content='My reply')  # own — should not be touched

        self.client.force_authenticate(user=self.sender)
        response = self.client.post(self.mark_read_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['marked_read'], 2)

        # Verify DB
        self.assertEqual(OrderMessage.objects.filter(is_read=True).count(), 2)
        self.assertEqual(OrderMessage.objects.filter(is_read=False).count(), 1)  # sender's own message

    def test_mark_read_after_read_returns_zero(self):
        """Calling mark-read twice returns 0 the second time."""
        OrderMessage.objects.create(order=self.order, sender=self.dispatcher, content='Hey')

        self.client.force_authenticate(user=self.sender)
        self.client.post(self.mark_read_url)   # first call
        response = self.client.post(self.mark_read_url)  # second call
        self.assertEqual(response.data['data']['marked_read'], 0)

    def test_unrelated_dispatcher_cannot_mark_read(self):
        self.client.force_authenticate(user=self.other_dispatcher)
        response = self.client.post(self.mark_read_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Dispatcher Inbox Tests
# ---------------------------------------------------------------------------

INBOX_URL = '/api/v1/orders/messages/'


def _make_order(sender, dispatcher=None, **kwargs):
    defaults = dict(
        pickup_address='Farm A, Kano',
        pickup_contact_name='Dan',
        pickup_phone='0800000001',
        delivery_address='Mile 12, Lagos',
        delivery_name='Ola',
        delivery_phone='0800000002',
        cargo_type='Tomatoes',
        cargo_weight=200,
        cargo_value=50000,
    )
    defaults.update(kwargs)
    order = Order.objects.create(sender=sender, dispatcher=dispatcher, **defaults)
    return order


class DispatcherInboxTests(APITestCase):

    def setUp(self):
        # Users
        self.sender = User.objects.create_user(
            email='inbox_sender@example.com', password='pass', full_name='Inbox Sender',
            is_active=True, is_verified=True, role=User.Role.SENDER,
        )
        self.dispatcher = User.objects.create_user(
            email='inbox_dispatcher@example.com', password='pass', full_name='Inbox Dispatcher',
            is_active=True, is_verified=True, role=User.Role.DISPATCHER,
        )
        self.other_dispatcher = User.objects.create_user(
            email='other_inbox_dispatcher@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.DISPATCHER,
        )
        self.admin = User.objects.create_user(
            email='inbox_admin@example.com', password='pass', full_name='Admin',
            is_active=True, is_verified=True, role=User.Role.ADMIN,
        )

        # One order assigned to our dispatcher
        self.order1 = _make_order(self.sender, dispatcher=self.dispatcher)
        # A second order also assigned to our dispatcher
        self.order2 = _make_order(
            self.sender, dispatcher=self.dispatcher,
            pickup_address='Kaduna City', delivery_address='Abuja, FCT'
        )
        # An order assigned to a different dispatcher (should NOT appear)
        self.order_other = _make_order(self.sender, dispatcher=self.other_dispatcher)

    # ── Access control ────────────────────────────────────────────────────

    def test_sender_cannot_access_inbox(self):
        self.client.force_authenticate(user=self.sender)
        response = self.client.get(INBOX_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access_inbox(self):
        response = self.client.get(INBOX_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dispatcher_can_access_inbox(self):
        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_access_inbox(self):
        # Admin should see all messages across all orders they're assigned to
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(INBOX_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── Empty inbox ───────────────────────────────────────────────────────

    def test_empty_inbox_returns_zero_counts(self):
        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        data = response.data['data']
        self.assertEqual(data['total_count'], 0)
        self.assertEqual(data['unread_count'], 0)
        self.assertEqual(data['messages'], [])

    # ── Message counts ────────────────────────────────────────────────────

    def test_total_count_includes_all_assigned_orders(self):
        # 2 messages on order1, 1 message on order2
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Hello from order 1')
        OrderMessage.objects.create(order=self.order1, sender=self.dispatcher, content='Got it')
        OrderMessage.objects.create(order=self.order2, sender=self.sender, content='Hello from order 2')

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        data = response.data['data']
        self.assertEqual(data['total_count'], 3)

    def test_unread_count_excludes_own_messages(self):
        # 2 unread from sender, 1 from dispatcher (own — should NOT count)
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Msg 1', is_read=False)
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Msg 2', is_read=False)
        OrderMessage.objects.create(order=self.order1, sender=self.dispatcher, content='My reply', is_read=False)

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        self.assertEqual(response.data['data']['unread_count'], 2)

    def test_read_messages_not_counted_as_unread(self):
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Msg', is_read=True)

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        self.assertEqual(response.data['data']['unread_count'], 0)
        self.assertEqual(response.data['data']['total_count'], 1)

    def test_messages_from_other_dispatcher_orders_not_included(self):
        # Message on order assigned to other_dispatcher — should NOT appear
        OrderMessage.objects.create(order=self.order_other, sender=self.sender, content='Private')
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Mine')

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        self.assertEqual(response.data['data']['total_count'], 1)

    # ── Response shape ────────────────────────────────────────────────────

    def test_message_has_all_required_fields(self):
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Test message')

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        msg = response.data['data']['messages'][0]

        required = [
            'id', 'order_id', 'tracking_number', 'pickup_address',
            'delivery_address', 'sender_id', 'sender_name',
            'sender_initials', 'is_own_message', 'content', 'is_read', 'timestamp',
        ]
        for field in required:
            self.assertIn(field, msg, f"Missing field: {field}")

    def test_is_own_message_true_for_dispatcher_messages(self):
        OrderMessage.objects.create(order=self.order1, sender=self.dispatcher, content='I sent this')

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        msg = response.data['data']['messages'][0]
        self.assertTrue(msg['is_own_message'])

    def test_is_own_message_false_for_sender_messages(self):
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Sender sent this')

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        msg = response.data['data']['messages'][0]
        self.assertFalse(msg['is_own_message'])

    def test_messages_ordered_newest_first(self):
        m1 = OrderMessage.objects.create(order=self.order1, sender=self.sender, content='First')
        m2 = OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Second')

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        messages = response.data['data']['messages']
        self.assertEqual(messages[0]['id'], m2.id)
        self.assertEqual(messages[1]['id'], m1.id)

    def test_tracking_number_included_in_message(self):
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Hi')

        self.client.force_authenticate(user=self.dispatcher)
        response = self.client.get(INBOX_URL)
        msg = response.data['data']['messages'][0]
        self.assertEqual(msg['tracking_number'], self.order1.tracking_number)


UNREAD_URL = reverse('orders:dispatcher-unread')


class DispatcherUnreadTests(APITestCase):
    def setUp(self):
        self.sender = User.objects.create_user(
            email='unread_sender@example.com', password='pass', full_name='Sender One',
            is_active=True, is_verified=True, role=User.Role.SENDER,
        )
        self.dispatcher = User.objects.create_user(
            email='unread_disp@example.com', password='pass', full_name='Dispatcher One',
            is_active=True, is_verified=True, role=User.Role.DISPATCHER,
        )

        self.order1 = _make_order(self.sender, dispatcher=self.dispatcher)
        self.order2 = _make_order(
            self.sender, dispatcher=self.dispatcher,
            pickup_address='Kaduna', delivery_address='Abuja',
        )

    # ── Access control ────────────────────────────────────────────────────

    def test_sender_cannot_access_unread(self):
        self.client.force_authenticate(user=self.sender)
        res = self.client.get(UNREAD_URL)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access_unread(self):
        res = self.client.get(UNREAD_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── Empty state ───────────────────────────────────────────────────────

    def test_empty_returns_zero_total_and_empty_threads(self):
        self.client.force_authenticate(user=self.dispatcher)
        res = self.client.get(UNREAD_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['data']['total_unread'], 0)
        self.assertEqual(res.data['data']['threads'], [])

    # ── Unread grouping ───────────────────────────────────────────────────

    def test_unread_messages_grouped_by_order(self):
        # 2 unread on order1, 1 unread on order2
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Msg A')
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Msg B')
        OrderMessage.objects.create(order=self.order2, sender=self.sender, content='Msg C')

        self.client.force_authenticate(user=self.dispatcher)
        res = self.client.get(UNREAD_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data['data']
        self.assertEqual(data['total_unread'], 3)
        self.assertEqual(len(data['threads']), 2)

        # Find the thread for order1
        thread1 = next(t for t in data['threads'] if t['order_id'] == self.order1.id)
        self.assertEqual(thread1['unread_count'], 2)
        self.assertEqual(len(thread1['messages']), 2)

    def test_own_messages_not_included_in_unread(self):
        # Dispatcher sends a message — should NOT appear in unread
        OrderMessage.objects.create(order=self.order1, sender=self.dispatcher, content='I replied')
        # Sender sends one — SHOULD appear
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Hi')

        self.client.force_authenticate(user=self.dispatcher)
        res = self.client.get(UNREAD_URL)
        self.assertEqual(res.data['data']['total_unread'], 1)

    def test_already_read_messages_not_included(self):
        msg = OrderMessage.objects.create(
            order=self.order1, sender=self.sender, content='Already read', is_read=True
        )
        self.client.force_authenticate(user=self.dispatcher)
        res = self.client.get(UNREAD_URL)
        self.assertEqual(res.data['data']['total_unread'], 0)

    # ── Mark specific chat as read ─────────────────────────────────────────

    def test_mark_specific_order_chat_as_read(self):
        OrderMessage.objects.create(order=self.order1, sender=self.sender, content='Chat 1')
        OrderMessage.objects.create(order=self.order2, sender=self.sender, content='Chat 2')

        # Mark only order1's chat as read
        mark_url = reverse('orders:order-messages-mark-read', kwargs={'pk': self.order1.pk})
        self.client.force_authenticate(user=self.dispatcher)
        res = self.client.post(mark_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['data']['marked_read'], 1)

        # Now unread should only contain order2
        res2 = self.client.get(UNREAD_URL)
        data = res2.data['data']
        self.assertEqual(data['total_unread'], 1)
        self.assertEqual(len(data['threads']), 1)
        self.assertEqual(data['threads'][0]['order_id'], self.order2.id)


class ReviewTests(APITestCase):
    def setUp(self):
        self.sender = User.objects.create_user(
            email='sender@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.SENDER
        )
        self.other_sender = User.objects.create_user(
            email='other@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.SENDER
        )
        self.driver = Driver.objects.create(name="Driver Bob", rating=0.0)
        self.order = _make_order(self.sender)
        self.order.driver = self.driver
        self.order.status = Order.Status.COMPLETED
        self.order.save()
        
        self.url = reverse('orders:order-rate', kwargs={'pk': self.order.pk})

    def test_rate_completed_order_success(self):
        self.client.force_authenticate(user=self.sender)
        data = {'rating': 5, 'comment': 'Great driver!'}
        res = self.client.post(self.url, data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Review.objects.count(), 1)
        
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.rating, 5.0)

    def test_rate_updates_driver_average(self):
        self.client.force_authenticate(user=self.sender)
        self.client.post(self.url, {'rating': 5})
        
        # Another order for the same driver, rated 3
        order2 = _make_order(self.sender)
        order2.driver = self.driver
        order2.status = Order.Status.COMPLETED
        order2.save()
        
        url2 = reverse('orders:order-rate', kwargs={'pk': order2.pk})
        self.client.post(url2, {'rating': 3})
        
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.rating, 4.0)

    def test_cannot_rate_uncompleted_order(self):
        self.order.status = Order.Status.IN_TRANSIT
        self.order.save()
        self.client.force_authenticate(user=self.sender)
        res = self.client.post(self.url, {'rating': 4})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("only rate completed orders", str(res.data))

    def test_cannot_rate_other_peoples_order(self):
        self.client.force_authenticate(user=self.other_sender)
        res = self.client.post(self.url, {'rating': 4})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_rate_twice(self):
        self.client.force_authenticate(user=self.sender)
        self.client.post(self.url, {'rating': 4})
        res = self.client.post(self.url, {'rating': 5})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already rated", str(res.data))

    def test_review_embedded_in_order_detail(self):
        # Submit a rating first
        self.client.force_authenticate(user=self.sender)
        self.client.post(self.url, {'rating': 4, 'comment': 'Good job'})

        # Fetch the order detail — review should be embedded
        detail_url = reverse('orders:order-detail', kwargs={'pk': self.order.pk})
        res = self.client.get(detail_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        review = res.data['data']['review']
        self.assertIsNotNone(review)
        self.assertEqual(review['rating'], 4)
        self.assertEqual(review['comment'], 'Good job')

    def test_review_embedded_in_order_list(self):
        # Submit a rating first
        self.client.force_authenticate(user=self.sender)
        self.client.post(self.url, {'rating': 5, 'comment': 'Excellent'})

        # Fetch the order list — review should be embedded on the matching order
        list_url = reverse('orders:order-list')
        res = self.client.get(list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order_data = next(o for o in res.data['data'] if o['id'] == self.order.id)
        self.assertIsNotNone(order_data['review'])
        self.assertEqual(order_data['review']['rating'], 5)

    def test_unrated_order_has_null_review(self):
        # No rating submitted — review field should be null
        detail_url = reverse('orders:order-detail', kwargs={'pk': self.order.pk})
        self.client.force_authenticate(user=self.sender)
        res = self.client.get(detail_url)
        self.assertIsNone(res.data['data']['review'])


class DoubleBookingTests(APITestCase):
    def setUp(self):
        self.sender = User.objects.create_user(
            email='sender@example.com', password='pass', role=User.Role.SENDER, is_active=True, is_verified=True
        )
        self.dispatcher = User.objects.create_user(
            email='disp@example.com', password='pass', role=User.Role.DISPATCHER, is_active=True, is_verified=True
        )
        
        self.driver = Driver.objects.create(name="Driver 1")
        self.vehicle = Vehicle.objects.create(registration_number="V1")
        
        # Order 1 is in progress
        self.order1 = _make_order(self.sender, dispatcher=self.dispatcher)
        self.order1.driver = self.driver
        self.order1.vehicle = self.vehicle
        self.order1.status = Order.Status.IN_TRANSIT
        self.order1.save()
        
        # Order 2 is a new request
        self.order2 = _make_order(self.sender, dispatcher=self.dispatcher)
        
        self.url = reverse('orders:order-detail', kwargs={'pk': self.order2.pk})

    def test_cannot_assign_busy_driver(self):
        self.client.force_authenticate(user=self.dispatcher)
        data = {'driver_id': self.driver.id}
        res = self.client.patch(self.url, data)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('driver_id', res.data['errors'])

    def test_cannot_assign_busy_vehicle(self):
        self.client.force_authenticate(user=self.dispatcher)
        data = {'vehicle_id': self.vehicle.id}
        res = self.client.patch(self.url, data)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('vehicle_id', res.data['errors'])

    def test_can_assign_if_driver_finished_previous_order(self):
        self.order1.status = Order.Status.COMPLETED
        self.order1.save()
        
        self.client.force_authenticate(user=self.dispatcher)
        data = {'driver_id': self.driver.id, 'vehicle_id': self.vehicle.id}
        res = self.client.patch(self.url, data)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

