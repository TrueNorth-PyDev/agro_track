"""
Django settings for agrotrack project.
"""

from pathlib import Path
from datetime import timedelta
import dj_database_url
from decouple import config, Csv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',

    # Local apps
    'accounts',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',             # Must be before CommonMiddleware
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',        # Serve static files efficiently
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'agrotrack.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'agrotrack.wsgi.application'


# ---------------------------------------------------------------------------
# Custom User Model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.User'


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# On Railway, DATABASE_URL is automatically injected by the Postgres plugin.
# Locally, falls back to SQLite when DATABASE_URL is not set.
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,       # Keep DB connections alive for 10 min (pooling)
        conn_health_checks=True,
    )
}


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',   # For POD photo uploads (future)
        'rest_framework.parsers.FormParser',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',
        'user': '100/minute',
        'otp_resend': '3/hour',     # Resend OTP + password reset request
        'login': '10/minute',       # Brute-force protection on login endpoint
    },
    'EXCEPTION_HANDLER': 'accounts.utils.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}


# ---------------------------------------------------------------------------
# drf-spectacular (OpenAPI 3 / ReDoc)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'Agro Track API',
    'DESCRIPTION': 'API documentation for Agro Track logistics dispatch platform.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'ENUM_NAME_OVERRIDES': {
        'RoleEnum': 'accounts.models.User.Role',
    },
}


# ---------------------------------------------------------------------------
# SimpleJWT
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'TOKEN_OBTAIN_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenObtainPairSerializer',
    'TOKEN_REFRESH_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenRefreshSerializer',
}


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://localhost:5173',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True


# ---------------------------------------------------------------------------
# CSRF Trusted Origins
# ---------------------------------------------------------------------------
# Required when running behind Railway's HTTPS reverse proxy.
# Set CSRF_TRUSTED_ORIGINS in Railway env vars to your public domain(s),
# e.g.: https://agrotrack-production.up.railway.app
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:3000,http://localhost:8000',
    cast=Csv(),
)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='AgroTrack <noreply@agrotrack.com>')


# ---------------------------------------------------------------------------
# OTP Configuration
# ---------------------------------------------------------------------------
OTP_EXPIRY_MINUTES = config('OTP_EXPIRY_MINUTES', default=10, cast=int)


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'    # WAT — matches Nigeria (client location)
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static & Media files
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise: serve compressed, fingerprinted static files with long cache TTLs
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media (uploaded files) — ephemeral on Railway's filesystem.
# TODO: switch to django-storages + S3/R2 when POD photo upload feature lands.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ---------------------------------------------------------------------------
# Default primary key
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Security headers (enforced in production)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO' if DEBUG else 'WARNING',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}
