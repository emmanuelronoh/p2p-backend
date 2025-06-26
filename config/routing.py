# config/routing.py
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from apps.notifications import routing
from apps.core.middleware import ClientTokenAuthMiddlewareStack  

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": ClientTokenAuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    ),
})
