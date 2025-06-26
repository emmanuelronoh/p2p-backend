# apps/notifications/consumers.py
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            # Get user from scope (set by your middleware)
            self.user = self.scope["user"]
            
            # Reject connection if user is not authenticated
            if self.user.is_anonymous:
                logger.warning("Anonymous user attempted WebSocket connection")
                await self.close(code=4001)
                return
            
            logger.info(f"User {self.user.id} attempting to connect to notifications")
            
            # Create a unique group name for this user's notifications
            self.group_name = f'user_{self.user.id}_notifications'
            
            # Add this channel to the user's notification group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            # Accept the connection
            await self.accept()
            logger.info(f"WebSocket connection established for user {self.user.id}")
            
            # Optionally send a welcome message
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'You are now connected to notifications',
                'user_id': self.user.id
            }))
            
        except Exception as e:
            logger.error(f"Error during WebSocket connection: {str(e)}")
            await self.close(code=4002)

    async def disconnect(self, close_code):
        try:
            # Only try to remove from group if we successfully added earlier
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(
                    self.group_name,
                    self.channel_name
                )
                logger.info(f"User {self.user.id} disconnected from notifications")
        except Exception as e:
            logger.error(f"Error during WebSocket disconnection: {str(e)}")

    async def send_notification(self, event):
        """
        Handler for sending actual notifications to the client.
        Called when something is sent to the user's notification group.
        """
        try:
            await self.send(text_data=json.dumps({
                'type': event.get('type', 'notification'),
                'data': event['data'],
                'timestamp': event.get('timestamp'),
                # Add any other relevant fields
            }))
        except Exception as e:
            logger.error(f"Error sending notification to user {self.user.id}: {str(e)}")
            await self.close(code=4003)

    # Add additional handlers for different message types if needed
    async def receive(self, text_data):
        """
        Handle messages received from the client
        """
        try:
            data = json.loads(text_data)
            logger.info(f"Received message from user {self.user.id}: {data}")
            
            # Example: Handle different message types
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'message': 'pong'
                }))
                
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON received from user {self.user.id}")
        except Exception as e:
            logger.error(f"Error processing message from user {self.user.id}: {str(e)}")