import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)
User = get_user_model()  # This will return your AnonymousUser class

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            # Extract token from WebSocket URL query string
            query_string = self.scope.get('query_string', b'').decode()
            query_params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            token = query_params.get('token')

            if not token:
                logger.warning("Missing token in query params")
                await self.close(code=4001)
                return

            # Authenticate user using client_token
            self.user = await self.get_user_from_token(token)

            if not self.user or isinstance(self.user, AnonymousUser):
                logger.warning("Invalid token - rejecting connection")
                await self.close(code=4001)
                return

            logger.info(f"WebSocket connection accepted for user {self.user.exchange_code}")

            self.group_name = f'user_{self.user.id}_notifications'

            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

            # Convert UUID to string for JSON serialization
            await self.send(text_data=json.dumps({
                'type': 'connection.established',
                'message': 'WebSocket connection established',
                'user_id': str(self.user.id),       # <-- fix here
                'exchange_code': self.user.exchange_code
            }))

        except Exception as e:
            logger.exception(f"WebSocket connection error: {e}")
            await self.close(code=4002)

    @database_sync_to_async
    def get_user_from_token(self, token):
        """Authenticate using client_token field in AnonymousUser"""
        try:
            return User.objects.get(client_token=token)
        except User.DoesNotExist:
            return AnonymousUser()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"User {getattr(self.user, 'exchange_code', 'unknown')} disconnected")

    async def send_notification(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'data': event['data'],
                'timestamp': event.get('timestamp')
            }))
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
            await self.close(code=4003)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            logger.debug(f"Message from user {self.user.exchange_code}: {data}")

            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received from client")
        except Exception as e:
            logger.error(f"Error handling message from client: {str(e)}")
