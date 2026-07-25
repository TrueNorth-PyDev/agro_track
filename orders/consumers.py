import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from .models import Order

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
