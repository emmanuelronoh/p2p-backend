import os
from pathlib import Path
from datetime import timedelta
import environ
import json
import base64
from cryptography.fernet import Fernet
from decouple import config
from corsheaders.defaults import default_headers
from decimal import Decimal
from rest_framework.settings import api_settings
from dotenv import load_dotenv


USDT_ADDR = config('USDT_ADDR')

WEB3_RPC_URL = config('WEB3_RPC_URL')


# Generate or use existing key for security questions
SECURITY_QUESTION_ENCRYPTION_KEY = Fernet.generate_key().decode()
BASE_DIR = Path(__file__).resolve().parent.parent 

load_dotenv(BASE_DIR / '.env')

# Initialize environment variables
env = environ.Env()
environ.Env.read_env()
env.read_env(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('DJANGO_SECRET_KEY')
print(f"ENCRYPTION_KEY loaded: {os.getenv('ENCRYPTION_KEY') is not None}")

INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'django_extensions',
    'rest_framework',
    'rest_framework_simplejwt',  # Required for JWT
    'corsheaders',
    'channels',  # For WebSockets
    
    # Local apps
    'apps.core',
    'apps.escrow',
    'apps.p2p',
    'apps.disputes',
    'apps.wallet',
    'apps.swap',
    'apps.bridge',
    'apps.notifications',
]

ASGI_APPLICATION = 'config.asgi.application'



FIELD_ENCRYPTION_KEY = os.getenv('FIELD_ENCRYPTION_KEY')

# Channel layer configuration (development)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}


# For production, use Redis:
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {
#             "hosts": [("redis://localhost:6379/0")],
#         },
#     },
# }

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # <-- must be at the top!
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

CORS_ALLOW_HEADERS = list(default_headers) + ['x-client', 'x-client-token']


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}

XUSDT_SETTINGS = {
    'USER_TOKEN_HMAC_KEY': 'your-secret-key-here',
    'LISTING_EXPIRY_DAYS': 7,
    'ESCROW_FEE_PERCENT': 0.25,  # 0.25%
    'ESCROW_MIN_FEE': 1.00,  # $1.00 minimum fee
}

# Add to settings.py
SECURITY_SETTINGS = {
    'MAX_TRANSACTION_VALUE': Decimal('5000'),  # $5k max per tx
    'DAILY_USER_LIMIT': Decimal('20000'),  # $20k daily/user
    'RATE_LIMITS': {
        'fund_escrow': '5/hour',
        'release_escrow': '10/hour',
    }
}

WEB3_RPC_URL = "https://mainnet.infura.io/v3/9e98c23f60ab491eab2cd5a82eece1fd"  # Or your node URL
USDT_ADDR = "0xdAC17F958D2ee523a2206206994597C13D831ec7"  # Mainnet USDT

# Load environment
env = environ.Env()
environ.Env.read_env()
env.read_env(os.path.join(BASE_DIR, '.env'))
SECURITY_QUESTION_ENCRYPTION_KEY = Fernet.generate_key().decode()
# Define DEBUG here immediately after reading environment
DEBUG = env.bool('DJANGO_DEBUG', default=False)

SECURITY_EVENT_HMAC_KEY = os.getenv('SECURITY_EVENT_HMAC_KEY', 'default-insecure-key-for-dev-only')

if DEBUG:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
else:
    SECURE_SSL_REDIRECT = env.bool('DJANGO_SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = env.bool('DJANGO_SESSION_COOKIE_SECURE', default=True)
    CSRF_COOKIE_SECURE = env.bool('DJANGO_CSRF_COOKIE_SECURE', default=True)
    SECURE_HSTS_SECONDS = env.int('DJANGO_SECURE_HSTS_SECONDS', default=31536000)

# Now printing will work
print("DEBUG:", DEBUG)
print("SECURE_SSL_REDIRECT:", SECURE_SSL_REDIRECT)


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'core.AnonymousUser'

CORS_ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "https://preview--anon-cash-tether-trade.lovable.app",
    "https://anon-cash-tether-trade.vercel.app",
    'https://exusdt-backend.onrender.com',
]

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'exusdt-backend.onrender.com',
    "anon-cash-tether-trade.vercel.app"
]

CORS_ALLOW_ALL_ORIGINS = True

# Optional - allow credentials (e.g., cookies, Authorization headers)
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.core.authentication.ClientTokenAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'registration': '10/hour',
        'login': '20/hour',
        'security_questions': '5/hour',
        'verify_questions': '10/hour',
        'recovery': '5/hour',
        'password_reset': '5/hour',
        'profile': '100/day',
        'password_change': '5/hour',
    },
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler'
}

# Argon2 password hashing
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Application-specific settings
XUSDT_SETTINGS = {
    'EXCHANGE_CODE_PREFIX': 'EX-',
    'EXCHANGE_CODE_LENGTH': 8,
    'CLIENT_TOKEN_SALT': env('CLIENT_TOKEN_SALT'),
    'USER_TOKEN_HMAC_KEY': env('USER_TOKEN_HMAC_KEY'),
    'ESCROW_FEE_PERCENT': 0.25,  # 0.25%
    'ESCROW_MIN_FEE': 1.0,  # 1 USDT
    'LISTING_EXPIRY_DAYS': 7,
    'TRADE_TIMEOUT_HOURS': 24,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'wallet': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}