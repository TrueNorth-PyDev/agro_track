import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from .models import Order, OrderMessage

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_group_name = f'chat_{self.order_id}'
        self.user = self.scope['user']

        # Reject unauthenticated users
        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Check access to this specific order
        has_access = await self._check_order_access(self.user, self.order_id)
        if not has_access:
            await self.close(code=4003)
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from room group
    async def chat_message(self, event):
        """
        Handler for the 'chat_message' event.
        Triggered when a new message is saved and broadcasted.
        """
        payload = event['payload']
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'data': payload
        }))

    async def chat_read(self, event):
        """
        Handler for the 'chat_read' event.
        Triggered when messages are marked as read.
        """
        payload = event['payload']
        # Send read receipt to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_read',
            'data': payload
        }))

    @sync_to_async
    def _check_order_access(self, user, order_id):
        try:
            order = Order.objects.get(id=order_id)
            if user.is_admin_user:
                return True
            if user.is_dispatcher:
                # Dispatcher can access any order they are assigned to, or any unassigned order (to claim it)
                # Actually, standard logic in views allows dispatchers to see any order. Let's stick to that.
                return True
            if user.is_sender and order.sender_id == user.id:
                return True
            return False
        except Order.DoesNotExist:
            return False


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for the global notification channel.

    Route: ws/notifications/

    Authenticated dispatchers and admins connect here to receive real-time
    unread-count badge updates.  The channel is server → client push only;
    any message sent by the client is silently ignored.

    Each user joins their own per-user group: ``notifications_{user_id}``.
    This ensures each dispatcher only receives counts relevant to them.

    Events pushed to the client
    ---------------------------
    ``notification.unread_update``
        Fired whenever a new chat message is created in any order assigned
        to this dispatcher, or whenever messages are marked as read.

        Shape::

            {
                "type": "notification.unread_update",
                "data": { "unread_count": <int> }
            }
    """

    async def connect(self):
        self.user = self.scope['user']

        # Only authenticated dispatchers and admins may subscribe
        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        is_allowed = await sync_to_async(
            lambda: self.user.is_dispatcher or self.user.is_admin_user
        )()
        if not is_allowed:
            await self.close(code=4003)
            return

        # Per-user group so each dispatcher gets their own counts
        self.group_name = f'notifications_{self.user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Push current unread count immediately on connect so the frontend
        # badge is accurate as soon as the socket opens.
        count = await self._get_unread_count(self.user)
        await self.send(text_data=json.dumps({
            'type': 'notification.unread_update',
            'data': {'unread_count': count}
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Clients are not expected to send anything — silently ignore
    async def receive(self, text_data=None, bytes_data=None):
        pass

    # ------------------------------------------------------------------
    # Channel-layer event handlers
    # ------------------------------------------------------------------

    async def notification_unread_update(self, event):
        """
        Forwards a ``notification_unread_update`` channel-layer event to the
        connected WebSocket client.

        Expected event shape (from group_send call)::

            {
                "type":         "notification_unread_update",
                "unread_count": <int>
            }
        """
        await self.send(text_data=json.dumps({
            'type': 'notification.unread_update',
            'data': {'unread_count': event['unread_count']}
        }))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @sync_to_async
    def _get_unread_count(self, user):
        """Total unread messages from senders across all orders assigned to this user."""
        return (
            OrderMessage.objects
            .filter(order__dispatcher=user, is_read=False)
            .exclude(sender=user)
            .count()
        )
