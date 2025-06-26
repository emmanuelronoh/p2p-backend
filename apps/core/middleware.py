# apps.core/middleware.py

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs

User = get_user_model()

class ClientTokenAuthMiddleware:
    """
    Custom WebSocket middleware that authenticates users based on an
    'x-client-token' header or query string parameter.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Extract headers as a dict with lowercase keys for convenience
        headers = dict((k.lower(), v) for k, v in scope.get('headers', []))

        token = None

        # Try to get token from 'x-client-token' header
        token_header = headers.get(b'x-client-token')
        if token_header:
            token = token_header.decode('utf-8')

        # Fallback: check query string if no token found in headers
        if not token and scope.get('query_string'):
            qs = parse_qs(scope['query_string'].decode('utf-8'))
            token_list = qs.get('x-client-token')
            if token_list:
                token = token_list[0]

        # Validate token and assign user to scope
        if token:
            try:
                user = await self.get_user_for_token(token)
                scope['user'] = user
            except Exception:
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()

        # Continue to the next ASGI app with the modified scope
        return await self.app(scope, receive, send)

    @database_sync_to_async
    def get_user_for_token(self, token):
        """
        Replace this with your actual token validation logic.
        Should return a User instance or raise an exception.
        """
        try:
            # Example: assume you have a token stored on the User model or a related model
            return User.objects.get(auth_token=token)
        except User.DoesNotExist:
            return AnonymousUser()

def ClientTokenAuthMiddlewareStack(inner):
    # Wrap your middleware around the default AuthMiddlewareStack
    return ClientTokenAuthMiddleware(AuthMiddlewareStack(inner))
