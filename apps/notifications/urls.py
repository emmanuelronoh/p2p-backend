# notifications/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
    path('mark-all-read/', NotificationViewSet.as_view({'post': 'mark_all_as_read'}), name='mark-all-read'),
    path('settings/', NotificationViewSet.as_view({'get': 'settings', 'put': 'settings'}), name='notification-settings'),
]