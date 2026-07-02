"""
Models for the accounts app.

Defines:
  - User          : Custom user model with email as login field and role-based access
  - OTPVerification: Stores hashed OTP tokens for email verification and password reset
"""

import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for AgroTrack.

    Authentication is via email + password.
    All platform roles are encoded in the `role` field and enforced
    via DRF permission classes (see permissions.py).
    """

    class Role(models.TextChoices):
        SENDER = 'sender', _('Sender / Receiver')
        DISPATCHER = 'dispatcher', _('Logistics Dispatcher')
        ADMIN = 'admin', _('Platform Admin')

    # Primary key — UUID for security (no sequential ID leakage)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Authentication fields
    email = models.EmailField(_('email address'), unique=True, db_index=True)

    # Profile fields (from registration screen)
    full_name = models.CharField(_('full name'), max_length=255)
    phone_number = models.CharField(_('phone number'), max_length=20, blank=True)
    delivery_address = models.TextField(_('delivery address'), blank=True)

    # Role
    role = models.CharField(
        _('role'),
        max_length=20,
        choices=Role.choices,
        default=Role.SENDER,
        db_index=True,   # Indexed for fast RBAC permission queries
    )

    # Account state
    is_active = models.BooleanField(
        _('active'),
        default=False,      # Set True only after OTP verification
        help_text=_('Designates whether this user should be treated as active. '
                    'Unselect this instead of deleting accounts.'),
    )
    is_verified = models.BooleanField(
        _('email verified'),
        default=False,
        help_text=_('Designates whether this user has verified their email address.'),
    )
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into the admin site.'),
    )

    # Profile & Contact Info
    business_name = models.CharField(_('business name'), max_length=255, blank=True)
    
    # Notification Preferences
    notify_status_updates = models.BooleanField(default=True)
    notify_delivery_confirmation = models.BooleanField(default=True)
    notify_promotions = models.BooleanField(default=False)
    
    # Stats placeholders
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0)
    on_time_percentage = models.IntegerField(default=100)
    
    # Dispatcher Specific
    territory = models.CharField(_('territory'), max_length=255, blank=True)

    # Timestamps
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    updated_at = models.DateTimeField(_('last updated'), auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.full_name} <{self.email}>'

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.email

    @property
    def is_sender(self):
        return self.role == self.Role.SENDER

    @property
    def is_dispatcher(self):
        return self.role == self.Role.DISPATCHER

    @property
    def is_admin_user(self):
        return self.role == self.Role.ADMIN


class OTPVerification(models.Model):
    """
    Stores a hashed OTP for a user. Used for:
      - Email verification after registration
      - Password reset flow

    The raw OTP is never stored — only a SHA-256 hash.
    Each OTP is single-use and expires after OTP_EXPIRY_MINUTES.
    """

    class Purpose(models.TextChoices):
        REGISTRATION = 'registration', _('Email Verification')
        PASSWORD_RESET = 'password_reset', _('Password Reset')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='otp_verifications',
    )
    otp_hash = models.CharField(_('OTP hash'), max_length=64)  # SHA-256 hex digest
    purpose = models.CharField(
        _('purpose'),
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.REGISTRATION,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('OTP verification')
        verbose_name_plural = _('OTP verifications')
        ordering = ['-created_at']
        indexes = [
            # Covers the most common query pattern:
            # WHERE user_id=? AND purpose=? AND is_used=false AND expires_at > now()
            models.Index(fields=['user', 'purpose', 'is_used', 'expires_at']),
        ]

    def __str__(self):
        return f'OTP for {self.user.email} [{self.purpose}] — expires {self.expires_at}'

    def is_valid(self):
        """
        Returns True if the OTP has not been used and has not expired.
        """
        return not self.is_used and timezone.now() < self.expires_at

    def mark_used(self):
        """
        Mark this OTP as consumed so it cannot be reused.
        """
        self.is_used = True
        self.save(update_fields=['is_used'])
