"""
Utility functions for the accounts app.

Provides:
  - OTP generation (cryptographically secure)
  - OTP hashing (SHA-256, never stored in plaintext)
  - Constant-time OTP comparison (prevents timing attacks)
  - Email dispatch helpers
  - Custom DRF exception handler for consistent error envelopes
"""

import hashlib
import hmac
import secrets
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from rest_framework.views import exception_handler
from rest_framework.response import Response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OTP Utilities
# ---------------------------------------------------------------------------

def generate_otp(length: int = 6) -> str:
    """
    Generate a cryptographically secure numeric OTP.

    Uses secrets.randbelow(10**length) to produce a uniformly distributed
    integer, then zero-pads to the requested length.
    This is simpler and equally secure to the list-comprehension approach.
    """
    upper = 10 ** length
    return str(secrets.randbelow(upper)).zfill(length)


def hash_otp(raw_otp: str) -> str:
    """
    Return the SHA-256 hex digest of the raw OTP string.
    This is what gets stored in the database — the raw value is never persisted.
    """
    return hashlib.sha256(raw_otp.encode('utf-8')).hexdigest()


def verify_otp(raw_otp: str, stored_hash: str) -> bool:
    """
    Compare a submitted OTP against its stored hash in constant time.

    Uses hmac.compare_digest to prevent timing-based side-channel attacks
    that could allow an attacker to infer digits of the OTP one at a time.
    """
    computed = hash_otp(raw_otp)
    return hmac.compare_digest(computed, stored_hash)


def get_otp_expiry() -> timezone.datetime:
    """
    Return the absolute expiry datetime for a newly generated OTP.
    Driven by the OTP_EXPIRY_MINUTES setting (default: 10 minutes).
    """
    minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
    return timezone.now() + timedelta(minutes=minutes)


# ---------------------------------------------------------------------------
# Email Utilities
# ---------------------------------------------------------------------------

def send_otp_email(user, raw_otp: str, purpose: str = 'registration') -> bool:
    """
    Dispatch an OTP email to the user.

    Args:
        user:     The User model instance (must have .email and .get_short_name())
        raw_otp:  The plain-text OTP to embed in the email body
        purpose:  'registration' | 'password_reset'

    Returns:
        True on successful dispatch, False on any error.
        Errors are logged but not re-raised — callers decide whether to surface them.
    """
    expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
    name = user.get_short_name()

    templates = {
        'registration': (
            'Verify your AgroTrack account',
            (
                f'Hello {name},\n\n'
                f'Welcome to AgroTrack! Use the OTP below to verify your email address:\n\n'
                f'    {raw_otp}\n\n'
                f'This code is valid for {expiry_minutes} minutes.\n\n'
                f'If you did not create an AgroTrack account, please ignore this email.\n\n'
                f'— The AgroTrack Team'
            ),
        ),
        'password_reset': (
            'Reset your AgroTrack password',
            (
                f'Hello {name},\n\n'
                f'We received a request to reset your AgroTrack password.\n\n'
                f'Use this OTP to proceed:\n\n'
                f'    {raw_otp}\n\n'
                f'This code is valid for {expiry_minutes} minutes.\n\n'
                f'If you did not request a password reset, you can safely ignore this email.\n\n'
                f'— The AgroTrack Team'
            ),
        ),
    }

    if purpose not in templates:
        logger.error('send_otp_email: unknown purpose "%s" for user %s', purpose, user.email)
        return False

    subject, message = templates[purpose]

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info('OTP email dispatched to %s [purpose=%s]', user.email, purpose)
        return True
    except Exception as exc:
        logger.error(
            'Failed to send OTP email to %s [purpose=%s]: %s',
            user.email, purpose, exc, exc_info=True
        )
        return False


# ---------------------------------------------------------------------------
# Custom DRF Exception Handler
# ---------------------------------------------------------------------------

def custom_exception_handler(exc, context):
    """
    Wraps all DRF error responses in a consistent envelope:

        {
            "success": false,
            "message": "Human-readable summary of the error",
            "errors": { "field": ["detail"] } | null
        }

    Handles:
      - Dict responses (field-level and non-field errors)
      - List responses (non-field error lists)
      - Scalar responses (plain string detail)
      - Empty dict edge case (returns generic message instead of crashing)
    """
    response = exception_handler(exc, context)

    if response is None:
        return None

    data = response.data
    errors = None
    message = 'An error occurred.'

    if isinstance(data, dict):
        if not data:
            # Empty dict — shouldn't happen in practice but guard against it
            message = 'An unexpected error occurred.'
        else:
            # Check for non-field errors first (highest priority for message)
            non_field = data.get('non_field_errors') or data.get('detail')
            if non_field:
                message = str(non_field[0]) if isinstance(non_field, list) else str(non_field)
                remaining = {k: v for k, v in data.items() if k not in ('non_field_errors', 'detail')}
                errors = remaining if remaining else None
            else:
                # Field-level errors — pick the first field's first message as the summary
                first_key = next(iter(data))
                first_val = data[first_key]
                if isinstance(first_val, list) and first_val:
                    message = f'{first_key}: {first_val[0]}'
                elif isinstance(first_val, dict):
                    # Nested field errors (e.g., from nested serializers)
                    message = f'{first_key}: validation error'
                else:
                    message = str(first_val)
                errors = data

    elif isinstance(data, list):
        if data:
            message = str(data[0])
        errors = None

    else:
        message = str(data)

    response.data = {
        'success': False,
        'message': message,
        'errors': errors,
    }

    return response
