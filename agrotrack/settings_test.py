"""
Test settings for AgroTrack.

Inherits all production settings and overrides only what needs to change
during automated testing:
  - Throttling fully disabled (prevents 429s in the test runner)
  - Faster password hasher (speeds up tests significantly — MD5 is fine for tests)
  - Console email backend (no accidental SMTP calls)
"""

from .settings import *   # noqa: F401, F403

# ---------------------------------------------------------------------------
# Disable ALL DRF throttling during tests.
# Views with explicit throttle_classes (ResendOTPView, PasswordResetRequestView)
# are additionally patched in their respective test class setUp methods.
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    **REST_FRAMEWORK,   # noqa: F405
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {
        # Keep scope keys present so ScopedRateThrottle doesn't raise
        # ImproperlyConfigured on views that still declare throttle_classes.
        # The per-test mock in setUp patches those view throttle_classes to []
        # before any request fires, so these values are never evaluated.
        'anon': None,
        'user': None,
        'otp_resend': None,
        'login': None,
    },
}

# ---------------------------------------------------------------------------
# Use MD5 instead of PBKDF2/bcrypt — much faster for the test suite.
# Never use MD5PasswordHasher in production.
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# ---------------------------------------------------------------------------
# Email — always console in tests (no accidental SMTP calls)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# ---------------------------------------------------------------------------
# Static files — disable WhiteNoise's manifest storage during tests.
# collectstatic is never run in the test runner so the staticfiles/ dir
# doesn't exist, causing WhiteNoise to emit a spurious warning.
# ---------------------------------------------------------------------------
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
