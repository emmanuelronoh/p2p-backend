import logging
from rest_framework import authentication, exceptions
from django.conf import settings
from django.utils import timezone
from .models import AnonymousUser

# Get an instance of a logger
logger = logging.getLogger(__name__)

class ClientTokenAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication for anonymous users using client tokens.
    Handles cases where username might be null and ensures all required user attributes exist.
    """
    
    def authenticate(self, request):
        client_token = request.headers.get('X-Client-Token')
        
        # Return None if no token provided (let other auth classes try)
        if not client_token:
            logger.debug("No client token provided in headers")
            return None

        try:
            # Get user and update last active timestamp
            user = AnonymousUser.objects.get(client_token=client_token)
            user.last_active = timezone.now()
            
            # Ensure user has a username (set default if missing)
            if not user.username:
                default_username = f"anon_{user.exchange_code or user.id}"
                logger.debug(f"Setting default username: {default_username}")
                user.username = default_username
                user.save(update_fields=['username', 'last_active'])
            else:
                user.save(update_fields=['last_active'])
                
            logger.debug(f"Authenticated user: {user.username} ({user.exchange_code})")
            return (user, None)
            
        except AnonymousUser.DoesNotExist:
            logger.warning(f"Invalid client token provided: {client_token}")
            raise exceptions.AuthenticationFailed('Invalid client token')
        except Exception as e:
            logger.error(f"Authentication error for token {client_token}: {str(e)}", 
                        exc_info=True)
            raise exceptions.AuthenticationFailed('Authentication service unavailable')