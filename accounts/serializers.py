"""
Serializers for the accounts app.

Covers:
  - User registration
  - OTP verification
  - OTP resend
  - Login (returns JWT pair + profile)
  - Password reset request
  - Password reset confirmation
  - User profile (read-only)
"""

import logging

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema_field

from .models import OTPVerification
from .utils import generate_otp, hash_otp, verify_otp, send_otp_email, get_otp_expiry

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _create_and_send_otp(user: User, purpose: str) -> None:
    """
    Invalidate any existing active OTPs for this user + purpose,
    generate a new OTP, store its hash, and email it to the user.

    Raises:
        serializers.ValidationError: if the email could not be sent,
            so the caller can surface the failure and the user is not
            silently left without an OTP.
    """
    # Invalidate all prior OTPs of the same purpose for this user atomically
    OTPVerification.objects.filter(
        user=user,
        purpose=purpose,
        is_used=False,
    ).update(is_used=True)

    raw_otp = generate_otp()
    OTPVerification.objects.create(
        user=user,
        otp_hash=hash_otp(raw_otp),
        purpose=purpose,
        expires_at=get_otp_expiry(),
    )

    email_sent = send_otp_email(user, raw_otp, purpose=purpose)
    if not email_sent:
        # Log already happened inside send_otp_email; raise so the view can
        # return a 500-level error rather than silently succeeding.
        raise serializers.ValidationError(
            'We were unable to send the verification email. Please try again shortly.'
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterSerializer(serializers.ModelSerializer):
    """
    Handles the 'Create an account' screen.

    Fields: full_name, email, phone_number, delivery_address, password
    On success: creates an inactive, unverified user and sends an OTP email.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text='Minimum 8 characters. Cannot be entirely numeric or too common.',
    )

    class Meta:
        model = User
        fields = ('full_name', 'email', 'phone_number', 'delivery_address', 'password')
        extra_kwargs = {
            'full_name': {'required': True},
            'email': {'required': True},
            'phone_number': {'required': True},
            'delivery_address': {'required': True},
        }

    def validate_email(self, value):
        """Normalize and check uniqueness (case-insensitive)."""
        normalized = value.lower().strip()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError(
                'An account with this email address already exists.'
            )
        return normalized

    def validate_phone_number(self, value):
        """Accept 7–15 digit phone numbers; strip formatting characters."""
        digits = ''.join(filter(str.isdigit, value))
        if len(digits) < 7 or len(digits) > 15:
            raise serializers.ValidationError(
                'Enter a valid phone number (7–15 digits).'
            )
        return value.strip()

    def validate_password(self, value):
        """
        Run Django's built-in password validators with user context if available.
        Field-level validate_ hooks run before the cross-field validate(), so we
        store the value and re-validate with the user object in validate().
        """
        # Basic validation without user context at field level
        validate_password(value)
        return value

    def validate(self, attrs):
        """
        Re-run password validation with full user context so
        UserAttributeSimilarityValidator can compare against email/name.
        """
        # Build a temporary user object for similarity checks (not saved)
        temp_user = User(
            email=attrs.get('email', ''),
            full_name=attrs.get('full_name', ''),
        )
        try:
            validate_password(attrs['password'], user=temp_user)
        except Exception as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        return attrs

    def create(self, validated_data):
        """Create active user directly, bypassing OTP for now."""
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            full_name=validated_data['full_name'],
            phone_number=validated_data.get('phone_number', ''),
            delivery_address=validated_data.get('delivery_address', ''),
            is_active=True,
            is_verified=True,
        )
        # OTP bypass: no email sent for now.
        return user


# ---------------------------------------------------------------------------
# OTP Verification
# ---------------------------------------------------------------------------

class OTPVerifySerializer(serializers.Serializer):
    """
    Handles the 'Verify registration' screen.

    Accepts: email + otp
    On success: activates user, returns JWT pair + profile.
    """
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, min_length=6, max_length=6)

    def validate(self, attrs):
        email = attrs['email'].lower().strip()
        raw_otp = attrs['otp'].strip()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {'email': 'No account found with this email address.'}
            )

        if user.is_verified:
            raise serializers.ValidationError(
                {'otp': 'This account is already verified. Please log in.'}
            )

        # Fetch the latest unused OTP for this user + purpose
        otp_record = (
            OTPVerification.objects
            .filter(user=user, purpose=OTPVerification.Purpose.REGISTRATION, is_used=False)
            .order_by('-created_at')
            .first()
        )

        if not otp_record:
            raise serializers.ValidationError(
                {'otp': 'No active OTP found. Please request a new one.'}
            )

        if not otp_record.is_valid():
            raise serializers.ValidationError(
                {'otp': 'This OTP has expired. Please request a new one.'}
            )

        if not verify_otp(raw_otp, otp_record.otp_hash):
            raise serializers.ValidationError(
                {'otp': 'Invalid OTP. Please try again.'}
            )

        attrs['user'] = user
        attrs['otp_record'] = otp_record
        return attrs

    def save(self, **kwargs):
        """Activate user and consume the OTP. Returns JWT pair + profile."""
        user = self.validated_data['user']
        otp_record = self.validated_data['otp_record']

        user.is_active = True
        user.is_verified = True
        user.save(update_fields=['is_active', 'is_verified'])

        otp_record.mark_used()

        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserProfileSerializer(user).data,
        }


# ---------------------------------------------------------------------------
# OTP Resend
# ---------------------------------------------------------------------------

class ResendOTPSerializer(serializers.Serializer):
    """
    Allows an unverified user to request a fresh registration OTP.
    Invalidates any prior active OTPs before issuing a new one.
    """
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        email = value.lower().strip()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                'No account found with this email address.'
            )
        if user.is_verified:
            raise serializers.ValidationError(
                'This account is already verified. Please log in.'
            )
        # Store on the serializer instance (not in context — context is DRF-owned)
        self._user = user
        return email

    def save(self, **kwargs):
        _create_and_send_otp(self._user, purpose=OTPVerification.Purpose.REGISTRATION)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginSerializer(serializers.Serializer):
    """
    Handles the 'Log in to your account' screen.

    Accepts: email + password
    Returns: JWT pair + user profile on success.

    Error messages are intentionally specific per field so the UI can
    highlight the correct input. Since we use email-based auth (not username),
    the mild enumeration risk is acceptable and expected by users.
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'},
    )

    def validate(self, attrs):
        email = attrs['email'].lower().strip()
        password = attrs['password']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {'email': 'No account found with this email address.'}
            )

        if not user.is_verified:
            raise serializers.ValidationError(
                {'email': 'Please verify your email address before logging in.'}
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {'email': 'This account has been deactivated. Please contact support.'}
            )

        # authenticate() uses Django's AUTHENTICATION_BACKENDS; verifies hashed password
        authenticated_user = authenticate(
            request=self.context.get('request'),
            username=email,
            password=password,
        )

        if authenticated_user is None:
            raise serializers.ValidationError(
                {'password': 'Incorrect password. Please try again.'}
            )

        attrs['user'] = authenticated_user
        return attrs

    def get_tokens(self) -> dict:
        """Issue JWT pair for the validated user. Call only after is_valid()."""
        user = self.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserProfileSerializer(user).data,
        }


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------

class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Accepts an email address and sends a password-reset OTP.

    ALWAYS returns successfully regardless of whether the email exists —
    this prevents user enumeration (attackers cannot probe for registered emails).
    """
    email = serializers.EmailField(required=True)

    def save(self, **kwargs):
        email = self.validated_data['email'].lower().strip()
        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            # Silently do nothing
            logger.debug('Password reset requested for unknown/inactive email: %s', email)
            return
        try:
            _create_and_send_otp(user, purpose=OTPVerification.Purpose.PASSWORD_RESET)
        except serializers.ValidationError:
            # Log already happened; don't surface the error to prevent enumeration
            logger.warning('Failed to send password reset OTP to %s', email)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Validates the reset OTP and sets the new password.

    Body: { "email": "...", "otp": "...", "new_password": "..." }
    """
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, min_length=6, max_length=6)
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'},
    )

    def validate(self, attrs):
        email = attrs['email'].lower().strip()
        raw_otp = attrs['otp'].strip()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {'email': 'No account found with this email address.'}
            )

        otp_record = (
            OTPVerification.objects
            .filter(user=user, purpose=OTPVerification.Purpose.PASSWORD_RESET, is_used=False)
            .order_by('-created_at')
            .first()
        )

        if not otp_record or not otp_record.is_valid():
            raise serializers.ValidationError({'otp': 'Invalid or expired OTP.'})

        if not verify_otp(raw_otp, otp_record.otp_hash):
            raise serializers.ValidationError({'otp': 'Invalid OTP. Please try again.'})

        # Validate new password with user context so similarity checks work
        try:
            validate_password(attrs['new_password'], user=user)
        except Exception as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})

        attrs['user'] = user
        attrs['otp_record'] = otp_record
        return attrs

    def save(self, **kwargs):
        user = self.validated_data['user']
        otp_record = self.validated_data['otp_record']
        new_password = self.validated_data['new_password']

        user.set_password(new_password)
        user.save(update_fields=['password'])
        otp_record.mark_used()

        logger.info('Password reset completed for user: %s', user.email)


# ---------------------------------------------------------------------------
# User Profile (read-only)
# ---------------------------------------------------------------------------

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Safe, read-only representation of a User returned after
    login, OTP verification, or direct profile fetches,
    and supports updating profile contact & preferences.
    """
    total_shipments = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'full_name',
            'phone_number',
            'business_name',
            'delivery_address',
            'role',
            'is_verified',
            'date_joined',
            'notify_status_updates',
            'notify_delivery_confirmation',
            'notify_promotions',
            'rating',
            'on_time_percentage',
            'total_shipments'
        )
        read_only_fields = (
            'id', 'email', 'role', 'is_verified', 'date_joined', 
            'rating', 'on_time_percentage', 'total_shipments'
        )
        
    @extend_schema_field(serializers.IntegerField())
    def get_total_shipments(self, obj):
        if obj.is_sender:
            return obj.sent_orders.count()
        elif obj.is_dispatcher:
            return obj.dispatched_orders.count()
        return 0
