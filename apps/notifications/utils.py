# notifications/utils.py
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification

def send_notification(user, title, message, notification_type='info', metadata=None):
    # Create database notification
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        metadata=metadata or {}
    )
    
    # Send real-time notification
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'notifications_{user.id}',
        {
            'type': 'send_notification',
            'data': {
                'id': notification.id,
                'title': title,
                'message': message,
                'type': notification_type,
                'created_at': notification.created_at.isoformat(),
                'metadata': metadata or {}
            }
        }
    )
    
    return notification