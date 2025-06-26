from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from .models import Notification, NotificationSettings
from .serializers import NotificationSerializer, NotificationSettingsSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for handling notifications and notification settings.
    Includes standard CRUD operations for notifications plus:
    - Mark all as read
    - Notification settings management
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    queryset = Notification.objects.none()  # Default empty queryset

    def get_queryset(self):
        """Return notifications for the current authenticated user"""
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request, *args, **kwargs):
        """
        Mark all unread notifications as read for the current user
        """
        updated_count = Notification.objects.filter(
            user=request.user, 
            is_read=False
        ).update(is_read=True)

        return Response({
            'status': 'success',
            'updated_count': updated_count
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='settings')
    def notification_settings(self, request):
        """
        Handle notification settings for the current user
        GET: Retrieve current settings
        PUT/PATCH: Update settings
        """
        settings_obj, created = NotificationSettings.objects.get_or_create(user=request.user)

        if request.method == 'GET':
            serializer = NotificationSettingsSerializer(settings_obj)
            return Response(serializer.data)

        # Handle PUT/PATCH requests
        serializer = NotificationSettingsSerializer(
            settings_obj,
            data=request.data,
            partial=request.method == 'PATCH'
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def get_serializer_class(self):
        """
        Use different serializers for different actions
        """
        if self.action == 'notification_settings':
            return NotificationSettingsSerializer
        return super().get_serializer_class()
