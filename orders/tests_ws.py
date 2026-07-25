from django.urls import re_path
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
import json

from accounts.middleware import JWTAuthMiddleware
from orders.consumers import ChatConsumer
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
            pickup_address="A",
            delivery_address="B",
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
