from django.urls import re_path
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
import json

from accounts.middleware import JWTAuthMiddleware
from orders.consumers import ChatConsumer, NotificationConsumer
from orders.models import Order

User = get_user_model()


class ChatConsumerTests(TransactionTestCase):
    def setUp(self):
        self.sender = User.objects.create_user(
            email='ws_sender@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.SENDER,
        )
        self.dispatcher = User.objects.create_user(
            email='ws_dispatcher@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.DISPATCHER,
        )
        self.other_sender = User.objects.create_user(
            email='ws_other_sender@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.SENDER,
        )

        self.order = Order.objects.create(
            sender=self.sender,
            pickup_state="Kano",
            pickup_lga="Kano Municipal",
            delivery_state="Lagos",
            delivery_lga="Ikeja",
            cargo_weight=100,
            cargo_value=1000
        )
        
        self.application = JWTAuthMiddleware(
            URLRouter([
                re_path(r'ws/chat/orders/(?P<order_id>\w+)/$', ChatConsumer.as_asgi()),
            ])
        )

    async def test_unauthenticated_connection_rejected(self):
        communicator = WebsocketCommunicator(
            self.application, f"/ws/chat/orders/{self.order.id}/"
        )
        connected, subprotocol = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_authorized_sender_can_connect(self):
        token = str(AccessToken.for_user(self.sender))
        communicator = WebsocketCommunicator(
            self.application, f"/ws/chat/orders/{self.order.id}/?token={token}"
        )
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_unauthorized_sender_rejected(self):
        token = str(AccessToken.for_user(self.other_sender))
        communicator = WebsocketCommunicator(
            self.application, f"/ws/chat/orders/{self.order.id}/?token={token}"
        )
        connected, subprotocol = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()


class NotificationConsumerTests(TransactionTestCase):
    """
    Tests for the global notification WebSocket channel (ws/notifications/).
    """

    def setUp(self):
        self.dispatcher = User.objects.create_user(
            email='notif_dispatcher@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.DISPATCHER,
        )
        self.sender = User.objects.create_user(
            email='notif_sender@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.SENDER,
        )
        self.admin = User.objects.create_user(
            email='notif_admin@example.com', password='pass',
            is_active=True, is_verified=True, role=User.Role.ADMIN,
        )

        self.application = JWTAuthMiddleware(
            URLRouter([
                re_path(r'ws/chat/orders/(?P<order_id>\w+)/$', ChatConsumer.as_asgi()),
                re_path(r'ws/notifications/$', NotificationConsumer.as_asgi()),
            ])
        )

    async def test_unauthenticated_connection_rejected(self):
        """No token → rejected with 4001."""
        communicator = WebsocketCommunicator(self.application, '/ws/notifications/')
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_sender_connection_rejected(self):
        """Senders are not allowed on the notification channel (4003)."""
        token = str(AccessToken.for_user(self.sender))
        communicator = WebsocketCommunicator(
            self.application, f'/ws/notifications/?token={token}'
        )
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_dispatcher_can_connect_and_receives_initial_count(self):
        """Dispatcher connects and immediately gets an unread_count=0 event."""
        token = str(AccessToken.for_user(self.dispatcher))
        communicator = WebsocketCommunicator(
            self.application, f'/ws/notifications/?token={token}'
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Should receive an immediate snapshot on connect
        response = await communicator.receive_json_from(timeout=3)
        self.assertEqual(response['type'], 'notification.unread_update')
        self.assertEqual(response['data']['unread_count'], 0)

        await communicator.disconnect()

    async def test_admin_can_connect(self):
        """Admins are also permitted on the notification channel."""
        token = str(AccessToken.for_user(self.admin))
        communicator = WebsocketCommunicator(
            self.application, f'/ws/notifications/?token={token}'
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        response = await communicator.receive_json_from(timeout=3)
        self.assertEqual(response['type'], 'notification.unread_update')

        await communicator.disconnect()
