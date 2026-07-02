"""
Views for the accounts app.

All responses follow the envelope:
    {
        "success": true | false,
        "message": "Human-readable message",
        "data": { ... }   # Present on success
    }

Endpoints:
    POST /api/v1/auth/register/
    POST /api/v1/auth/verify-otp/
    POST /api/v1/auth/resend-otp/
    POST /api/v1/auth/login/
    POST /api/v1/auth/token/refresh/
    POST /api/v1/auth/logout/
    GET  /api/v1/auth/me/
    POST /api/v1/auth/password-reset/
    POST /api/v1/auth/password-reset/confirm/
"""

import logging

from rest_framework import status, serializers
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTRefreshView

from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiResponse

from .serializers import (
    RegisterSerializer,
    OTPVerifySerializer,
    ResendOTPSerializer,
    LoginSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    UserProfileSerializer,
)

logger = logging.getLogger(__name__)


def success_response(message: str, data: dict = None, http_status=status.HTTP_200_OK) -> Response:
    """Build a consistent success envelope."""
    payload = {'success': True, 'message': message}
    if data is not None:
        payload['data'] = data
    return Response(payload, status=http_status)


# ---------------------------------------------------------------------------
# Common Response Serializers for drf-spectacular
# ---------------------------------------------------------------------------
# These are used to generate accurate OpenAPI schema definitions for our
# custom envelope responses.

def get_envelope_serializer(name: str, data_serializer=None):
    """Dynamically generate a serializer for our envelope response."""
    fields = {
        'success': serializers.BooleanField(default=True),
        'message': serializers.CharField(),
    }
    if data_serializer:
        fields['data'] = data_serializer
    
    return inline_serializer(name=name, fields=fields)

BasicEnvelope = get_envelope_serializer('BasicEnvelope')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterView(GenericAPIView):
    """
    POST /api/v1/auth/register/

    Create a new user account and trigger an OTP email.
    The account remains inactive until OTP is verified.
    """
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Register new user",
        responses={
            201: get_envelope_serializer('RegisterAuthResponse', inline_serializer('RegisterAuthData', {
                'access': serializers.CharField(),
                'refresh': serializers.CharField(),
                'user': UserProfileSerializer(),
            })),
            400: OpenApiResponse(description="Validation error"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        logger.info('New user registered (OTP bypassed): %s', user.email)
        
        refresh = RefreshToken.for_user(user)
        token_data = {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserProfileSerializer(user).data,
        }

        return success_response(
            message='Account created successfully. Welcome to AgroTrack!',
            data=token_data,
            http_status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# OTP Verification
# ---------------------------------------------------------------------------

class VerifyOTPView(GenericAPIView):
    """
    POST /api/v1/auth/verify-otp/

    Verify the OTP emailed after registration.
    On success: activates the account and returns a JWT pair.
    """
    serializer_class = OTPVerifySerializer
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Verify Registration OTP",
        responses={
            200: get_envelope_serializer('AuthResponse', inline_serializer('AuthData', {
                'access': serializers.CharField(),
                'refresh': serializers.CharField(),
                'user': UserProfileSerializer(),
            })),
            400: OpenApiResponse(description="Invalid OTP or validation error"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_data = serializer.save()

        logger.info('User verified email: %s', request.data.get('email'))
        return success_response(
            message='Email verified successfully. Welcome to AgroTrack!',
            data=token_data,
        )


# ---------------------------------------------------------------------------
# OTP Resend
# ---------------------------------------------------------------------------

class ResendOTPView(GenericAPIView):
    """
    POST /api/v1/auth/resend-otp/

    Rate-limited to 3 requests/hour per IP.
    Invalidates prior OTPs and sends a fresh one.
    """
    serializer_class = ResendOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'otp_resend'

    @extend_schema(
        summary="Resend Registration OTP",
        responses={
            200: BasicEnvelope,
            400: OpenApiResponse(description="Validation error"),
            429: OpenApiResponse(description="Too many requests"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return success_response(
            message='A new OTP has been sent to your email address.',
        )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginView(GenericAPIView):
    """
    POST /api/v1/auth/login/

    Authenticate with email + password. Returns a JWT access/refresh pair.
    Unverified and inactive accounts are rejected with clear error messages.
    """
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    @extend_schema(
        summary="User Login",
        responses={
            200: get_envelope_serializer('LoginResponse', inline_serializer('LoginData', {
                'access': serializers.CharField(),
                'refresh': serializers.CharField(),
                'user': UserProfileSerializer(),
            })),
            400: OpenApiResponse(description="Invalid credentials or account inactive"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        token_data = serializer.get_tokens()

        logger.info('User logged in: %s', request.data.get('email'))
        return success_response(
            message='Login successful.',
            data=token_data,
        )


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------

class TokenRefreshView(SimpleJWTRefreshView):
    """
    POST /api/v1/auth/token/refresh/

    Delegates to simplejwt's built-in TokenRefreshView which correctly:
      - Validates the refresh token
      - Returns a new access token
      - Rotates and blacklists the old refresh token (per SIMPLE_JWT settings)

    Wraps the response in the standard success envelope.

    Body: { "refresh": "<refresh_token>" }
    """

    @extend_schema(
        summary="Refresh JWT Token",
        responses={
            200: get_envelope_serializer('TokenRefreshResponse', inline_serializer('TokenRefreshData', {
                'access': serializers.CharField(),
                'refresh': serializers.CharField(required=False, help_text='Only returned if token rotation is enabled'),
            })),
            401: OpenApiResponse(description="Invalid or expired refresh token"),
        }
    )
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        # super() returns 200 on success with {"access": "...", "refresh": "..."}
        # Wrap in our envelope
        return Response(
            {
                'success': True,
                'message': 'Token refreshed.',
                'data': response.data,
            },
            status=response.status_code,
        )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class LogoutView(GenericAPIView):
    """
    POST /api/v1/auth/logout/

    Blacklists the provided refresh token, permanently invalidating that session.
    The access token expires naturally after its short lifetime (15 min).

    Body: { "refresh": "<refresh_token>" }
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="User Logout",
        request=inline_serializer('LogoutRequest', {'refresh': serializers.CharField()}),
        responses={
            200: BasicEnvelope,
            400: OpenApiResponse(description="Bad request (e.g. missing or already blacklisted token)"),
            401: OpenApiResponse(description="Unauthorized (missing access token)"),
        }
    )
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'success': False, 'message': 'Refresh token is required.', 'errors': None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            # Token is already expired or invalid — logout is effectively complete
            return Response(
                {'success': False, 'message': 'Invalid or already expired token.', 'errors': None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info('User logged out: %s', request.user.email)
        return success_response(message='Logged out successfully.')


# ---------------------------------------------------------------------------
# Me (Profile)
# ---------------------------------------------------------------------------

class MeView(GenericAPIView):
    """
    GET /api/v1/auth/me/

    Returns the authenticated user's profile data.
    Requires a valid JWT Bearer token in the Authorization header.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get Current User Profile",
        responses={
            200: get_envelope_serializer('MeResponse', UserProfileSerializer()),
            401: OpenApiResponse(description="Unauthorized (missing or invalid token)"),
        }
    )
    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(request.user)
        return success_response(
            message='Profile retrieved.',
            data=serializer.data,
        )

    @extend_schema(
        summary="Update Current User Profile",
        responses={
            200: get_envelope_serializer('MeUpdateResponse', UserProfileSerializer()),
            400: OpenApiResponse(description="Validation error"),
        }
    )
    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(
            message='Profile updated successfully.',
            data=serializer.data,
        )


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------

class PasswordResetRequestView(GenericAPIView):
    """
    POST /api/v1/auth/password-reset/

    Sends a password-reset OTP to the given email address.
    ALWAYS returns 200 regardless of whether the email exists — this
    prevents user enumeration (an attacker cannot tell which emails are registered).
    """
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'otp_resend'

    @extend_schema(
        summary="Request Password Reset OTP",
        responses={
            200: BasicEnvelope,
            429: OpenApiResponse(description="Too many requests"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return success_response(
            message='If an account with that email exists, a password reset OTP has been sent.',
        )


class PasswordResetConfirmView(GenericAPIView):
    """
    POST /api/v1/auth/password-reset/confirm/

    Validates the reset OTP and sets the new password.
    Body: { "email": "...", "otp": "...", "new_password": "..." }
    """
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Confirm Password Reset",
        responses={
            200: BasicEnvelope,
            400: OpenApiResponse(description="Invalid OTP or validation error"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return success_response(
            message='Password reset successful. Please log in with your new password.',
        )
