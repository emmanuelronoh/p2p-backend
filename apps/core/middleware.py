# apps/core/middleware.py
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class ClientTokenAuthMiddleware:
    """
    Enhanced WebSocket middleware with detailed debugging for X-Client-Token auth
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            scope['user'] = AnonymousUser()
            
            # Debug all headers and query params
            logger.debug(f"Incoming connection headers: {dict((k.lower(), v.decode()) for k, v in scope.get('headers', []))}")
            if scope.get('query_string'):
                logger.debug(f"Query params: {parse_qs(scope['query_string'].decode('utf-8'))}")
            
            token = self._extract_client_token(scope)
            logger.debug(f"Extracted token: {token}")
            
            if token:
                logger.debug("Attempting token validation...")
                user = await self._validate_client_token(token)
                if user:
                    scope['user'] = user
                    logger.info(f"Authenticated user {user.id}")
                else:
                    logger.warning("Token validation failed")
            else:
                logger.warning("No token found in request")
            
            return await self.app(scope, receive, send)
            
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}", exc_info=True)
            scope['user'] = AnonymousUser()
            return await self.app(scope, receive, send)

    def _extract_client_token(self, scope):
        """Extract token from all possible locations"""
        # Check query params
        if scope.get('query_string'):
            try:
                qs = parse_qs(scope['query_string'].decode('utf-8'))
                for param in ['token', 'x-client-token', 'access_token']:
                    if qs.get(param):
                        return qs[param][0]
            except Exception as e:
                logger.warning(f"Query parsing error: {str(e)}")
        
        # Check headers
        if scope.get('headers'):
            try:
                headers = dict((k.lower(), v) for k, v in scope['headers'])
                for header in [b'x-client-token', b'authorization']:
                    if header in headers:
                        value = headers[header].decode()
                        if header == b'authorization' and value.startswith('Bearer '):
                            return value[7:]
                        return value
            except Exception as e:
                logger.warning(f"Header parsing error: {str(e)}")
        
        return None

    @database_sync_to_async
    def _validate_client_token(self, token):
        """Validate token with detailed debugging"""
        try:
            logger.debug(f"Validating token: {token}")
            
            # Option 1: DRF Token Authentication
            from rest_framework.authtoken.models import Token
            token_obj = Token.objects.select_related('user').filter(key=token).first()
            if token_obj:
                logger.debug(f"Found matching DRF token for user {token_obj.user.id}")
                return token_obj.user if token_obj.user.is_active else None
            
            # Option 2: Custom token field
            user = User.objects.filter(auth_token=token).first()
            if user:
                logger.debug(f"Found matching user with auth_token: {user.id}")
                return user if user.is_active else None
            
            logger.warning("No matching user found for token")
            return None
            
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return None

def ClientTokenAuthMiddlewareStack(inner):
    return ClientTokenAuthMiddleware(AuthMiddlewareStack(inner))