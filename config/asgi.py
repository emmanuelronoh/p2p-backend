import os
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Set default settings module first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Initialize Django before any imports that might need models
django.setup()

# Now import routing after Django is initialized
import apps.notifications.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            apps.notifications.routing.websocket_urlpatterns
        )
    ),
})