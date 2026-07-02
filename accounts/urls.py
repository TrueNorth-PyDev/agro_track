"""
URL patterns for the accounts app.
Mounted at: /api/v1/auth/
"""

from django.urls import path
from .views import (
    RegisterView,
    VerifyOTPView,
    ResendOTPView,
    LoginView,
    TokenRefreshView,
    LogoutView,
    MeView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
)

app_name = 'accounts'

urlpatterns = [
    # Registration flow
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),

    # Authentication
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # Profile
    path('me/', MeView.as_view(), name='me'),

    # Password reset
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]
