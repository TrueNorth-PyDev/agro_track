"""
Django admin configuration for the accounts app.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, OTPVerification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Admin panel for the custom User model.
    Replaces username with email as the primary identifier.
    """

    # List view
    list_display = ('email', 'full_name', 'role', 'is_active', 'is_verified', 'is_staff', 'date_joined')
    list_filter = ('role', 'is_active', 'is_verified', 'is_staff', 'date_joined')
    search_fields = ('email', 'full_name', 'phone_number')
    ordering = ('-date_joined',)
    readonly_fields = ('id', 'date_joined', 'updated_at')

    # Detail view fieldsets
    fieldsets = (
        (None, {
            'fields': ('id', 'email', 'password'),
        }),
        (_('Personal Info'), {
            'fields': ('full_name', 'phone_number', 'delivery_address'),
        }),
        (_('Role & Status'), {
            'fields': ('role', 'is_active', 'is_verified', 'is_staff', 'is_superuser'),
        }),
        (_('Permissions'), {
            'fields': ('groups', 'user_permissions'),
            'classes': ('collapse',),
        }),
        (_('Timestamps'), {
            'fields': ('date_joined', 'updated_at'),
        }),
    )

    # Add user form fieldsets
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'full_name', 'phone_number', 'delivery_address',
                'role', 'password1', 'password2',
                'is_active', 'is_verified', 'is_staff',
            ),
        }),
    )

    # Override to use email as the login field
    USERNAME_FIELD = 'email'


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    """
    Read-only admin view for OTP records (for debugging/support).
    OTP hashes are visible but the raw OTP is never stored.
    """
    list_display = ('user', 'purpose', 'created_at', 'expires_at', 'is_used', 'is_valid_display')
    list_filter = ('purpose', 'is_used')
    search_fields = ('user__email', 'user__full_name')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'user', 'otp_hash', 'purpose', 'created_at', 'expires_at', 'is_used')

    def is_valid_display(self, obj):
        return obj.is_valid()
    is_valid_display.boolean = True
    is_valid_display.short_description = 'Valid?'

    def has_add_permission(self, request):
        """OTPs should only be created via the API — not via admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """OTP records should be immutable via admin."""
        return False
