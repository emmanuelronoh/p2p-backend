from rest_framework import serializers
from .models import Notification, NotificationSettings


class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for Notification model.
    """
    class Meta:
        model = Notification
        fields = [
            'id', 
            'title', 
            'message', 
            'is_read', 
            'notification_type', 
            'created_at', 
            'metadata'
        ]
        read_only_fields = ['created_at']


class NotificationSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationSettings model.
    Handles user notification preferences.
    """
    class Meta:
        model = NotificationSettings
        fields = [
            'email_enabled',
            'push_enabled', 
            'in_app_enabled',
            'transaction_notifications',
            'marketing_notifications',
            'last_updated'
        ]
        read_only_fields = ['last_updated']

    # Optional: Format last_updated date if needed
    last_updated = serializers.DateTimeField(read_only=True, format="%Y-%m-%d %H:%M:%S")
