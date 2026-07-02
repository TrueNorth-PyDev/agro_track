"""
Test suite for the accounts app.

Covers:
  - User registration (success, duplicate email, weak password, missing fields, OTP created)
  - OTP verification (success, wrong OTP, expired OTP, already verified, unknown email)
  - OTP resend (success, already verified, unknown email)
  - Login (success, wrong password, unverified account, inactive account, unknown email)
  - Token refresh (success, bad token)
  - Logout (success, no auth, missing token)
  - Me / profile (authenticated, unauthenticated)
  - Password reset request (known email, unknown email — both 200)
  - Password reset confirm (success, wrong OTP, expired OTP)
  - Utils: generate_otp, hash_otp, verify_otp
"""

import unittest.mock
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTPVerification
from .utils import generate_otp, hash_otp, verify_otp, get_otp_expiry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(
    email='test@example.com',
    password='StrongPass1!',
    verified=True,
    role=User.Role.SENDER,
    **kwargs,
) -> User:
    """Create and return a test User."""
    return User.objects.create_user(
        email=email,
        password=password,
        full_name=kwargs.get('full_name', 'Test User'),
        phone_number=kwargs.get('phone_number', '08012345678'),
        delivery_address=kwargs.get('delivery_address', '12 Test Street, Lagos'),
        role=role,
        is_active=verified,
        is_verified=verified,
    )


def make_otp(
    user: User,
    purpose=OTPVerification.Purpose.REGISTRATION,
    raw_otp: str = '123456',
    expired: bool = False,
) -> OTPVerification:
    """Create and return a test OTPVerification record."""
    expires_at = (
        timezone.now() - timedelta(minutes=1) if expired else get_otp_expiry()
    )
    return OTPVerification.objects.create(
        user=user,
        otp_hash=hash_otp(raw_otp),
        purpose=purpose,
        expires_at=expires_at,
    )


def auth_header(user: User) -> str:
    """Return a Bearer Authorization header string for the given user."""
    return f'Bearer {str(RefreshToken.for_user(user).access_token)}'


# ---------------------------------------------------------------------------
# Utility Unit Tests
# ---------------------------------------------------------------------------

class UtilsTests(APITestCase):

    def test_generate_otp_length(self):
        for _ in range(20):
            otp = generate_otp()
            self.assertEqual(len(otp), 6)
            self.assertTrue(otp.isdigit())

    def test_generate_otp_zero_padding(self):
        """OTP must be zero-padded so length is always exactly 6."""
        # Force a value that would be < 100000 without zfill
        with unittest.mock.patch('accounts.utils.secrets.randbelow', return_value=42):
            otp = generate_otp()
        self.assertEqual(otp, '000042')
        self.assertEqual(len(otp), 6)

    def test_hash_otp_deterministic(self):
        self.assertEqual(hash_otp('123456'), hash_otp('123456'))

    def test_hash_otp_different_values(self):
        self.assertNotEqual(hash_otp('123456'), hash_otp('654321'))

    def test_verify_otp_correct(self):
        raw = '987654'
        stored = hash_otp(raw)
        self.assertTrue(verify_otp(raw, stored))

    def test_verify_otp_incorrect(self):
        self.assertFalse(verify_otp('000000', hash_otp('111111')))


# ---------------------------------------------------------------------------
# Registration Tests
# ---------------------------------------------------------------------------

class RegisterTests(APITestCase):

    def setUp(self):
        self.url = reverse('accounts:register')
        self.valid_payload = {
            'full_name': 'John Doe',
            'email': 'john@example.com',
            'phone_number': '08012345678',
            'delivery_address': '15 Farm Road, Abuja',
            'password': 'SecurePass1!',
        }

    def test_register_success(self):
        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertIn('email', response.data['data'])

        user = User.objects.get(email='john@example.com')
        self.assertFalse(user.is_active, 'User must be inactive before OTP verification')
        self.assertFalse(user.is_verified)

    def test_register_creates_one_otp_record(self):
        self.client.post(self.url, self.valid_payload, format='json')
        user = User.objects.get(email='john@example.com')
        count = OTPVerification.objects.filter(
            user=user, purpose=OTPVerification.Purpose.REGISTRATION, is_used=False
        ).count()
        self.assertEqual(count, 1)

    def test_register_duplicate_email(self):
        make_user(email='john@example.com')
        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_register_duplicate_email_case_insensitive(self):
        make_user(email='john@example.com')
        payload = {**self.valid_payload, 'email': 'JOHN@EXAMPLE.COM'}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_email_format(self):
        payload = {**self.valid_payload, 'email': 'not-an-email'}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password(self):
        payload = {**self.valid_payload, 'password': '1234'}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_numeric_only_password(self):
        payload = {**self.valid_payload, 'password': '12345678'}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_full_name(self):
        payload = {**self.valid_payload}
        del payload['full_name']
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_phone_number(self):
        payload = {**self.valid_payload}
        del payload['phone_number']
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_phone_too_short(self):
        payload = {**self.valid_payload, 'phone_number': '123'}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_email_normalized_to_lowercase(self):
        payload = {**self.valid_payload, 'email': 'UPPER@Example.COM'}
        self.client.post(self.url, payload, format='json')
        self.assertTrue(User.objects.filter(email='upper@example.com').exists())


# ---------------------------------------------------------------------------
# OTP Verification Tests
# ---------------------------------------------------------------------------

class VerifyOTPTests(APITestCase):

    def setUp(self):
        self.url = reverse('accounts:verify-otp')
        self.user = make_user(email='otp@example.com', verified=False)
        self.raw_otp = '654321'
        self.otp_record = make_otp(self.user, raw_otp=self.raw_otp)

    def test_verify_success_returns_jwt(self):
        response = self.client.post(self.url, {
            'email': 'otp@example.com',
            'otp': self.raw_otp,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('access', response.data['data'])
        self.assertIn('refresh', response.data['data'])
        self.assertIn('user', response.data['data'])

    def test_verify_activates_user(self):
        self.client.post(self.url, {'email': 'otp@example.com', 'otp': self.raw_otp}, format='json')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.is_verified)

    def test_verify_consumes_otp_record(self):
        self.client.post(self.url, {'email': 'otp@example.com', 'otp': self.raw_otp}, format='json')
        self.otp_record.refresh_from_db()
        self.assertTrue(self.otp_record.is_used)

    def test_verify_wrong_otp(self):
        response = self.client.post(self.url, {
            'email': 'otp@example.com', 'otp': '000000',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_expired_otp(self):
        make_otp(self.user, raw_otp='999999', expired=True)
        self.otp_record.is_used = True
        self.otp_record.save()
        response = self.client.post(self.url, {
            'email': 'otp@example.com', 'otp': '999999',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_already_verified_account(self):
        make_user(email='done@example.com', verified=True)
        response = self.client.post(self.url, {
            'email': 'done@example.com', 'otp': '123456',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_unknown_email(self):
        response = self.client.post(self.url, {
            'email': 'ghost@example.com', 'otp': '123456',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_otp_cannot_be_reused(self):
        """After one successful verification, the same OTP must not work again."""
        payload = {'email': 'otp@example.com', 'otp': self.raw_otp}
        self.client.post(self.url, payload, format='json')
        # Second attempt
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Resend OTP Tests
# ---------------------------------------------------------------------------

class ResendOTPTests(APITestCase):
    """
    Throttle is patched per-test to prevent 429s in the test runner.
    In production the ScopedRateThrottle (3/hour per IP) applies normally.
    """

    def setUp(self):
        self.url = reverse('accounts:resend-otp')
        self.user = make_user(email='resend@example.com', verified=False)
        self.throttle_patcher = unittest.mock.patch(
            'accounts.views.ResendOTPView.throttle_classes', new=[]
        )
        self.throttle_patcher.start()

    def tearDown(self):
        self.throttle_patcher.stop()

    def test_resend_success(self):
        response = self.client.post(self.url, {'email': 'resend@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    def test_resend_invalidates_old_otp(self):
        """Resending must invalidate any prior active OTPs."""
        old_otp = make_otp(self.user, raw_otp='111111')
        self.client.post(self.url, {'email': 'resend@example.com'}, format='json')
        old_otp.refresh_from_db()
        self.assertTrue(old_otp.is_used)

    def test_resend_creates_new_otp(self):
        initial_count = OTPVerification.objects.filter(
            user=self.user, is_used=False
        ).count()
        self.client.post(self.url, {'email': 'resend@example.com'}, format='json')
        new_count = OTPVerification.objects.filter(
            user=self.user, is_used=False
        ).count()
        # Still exactly one active OTP after resend
        self.assertEqual(new_count, 1)

    def test_resend_already_verified(self):
        verified = make_user(email='alreadydone@example.com', verified=True)
        response = self.client.post(self.url, {'email': 'alreadydone@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resend_unknown_email(self):
        response = self.client.post(self.url, {'email': 'nobody@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Login Tests
# ---------------------------------------------------------------------------

class LoginTests(APITestCase):

    def setUp(self):
        self.url = reverse('accounts:login')
        self.user = make_user(email='login@example.com', password='TestPass99!', verified=True)

    def test_login_success(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'TestPass99!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('access', response.data['data'])
        self.assertIn('refresh', response.data['data'])
        self.assertIn('user', response.data['data'])

    def test_login_returns_correct_user_data(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com', 'password': 'TestPass99!',
        }, format='json')
        self.assertEqual(response.data['data']['user']['email'], 'login@example.com')

    def test_login_wrong_password(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'WrongPassword!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_login_unverified_account(self):
        make_user(email='unverified@example.com', password='TestPass99!', verified=False)
        response = self.client.post(self.url, {
            'email': 'unverified@example.com', 'password': 'TestPass99!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_inactive_account(self):
        """An admin-deactivated account (is_active=False, is_verified=True) must be rejected."""
        user = make_user(email='inactive@example.com', password='TestPass99!', verified=True)
        user.is_active = False
        user.save(update_fields=['is_active'])
        response = self.client.post(self.url, {
            'email': 'inactive@example.com', 'password': 'TestPass99!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_unknown_email(self):
        response = self.client.post(self.url, {
            'email': 'ghost@example.com', 'password': 'TestPass99!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_email_case_insensitive(self):
        """Login should succeed regardless of email case."""
        response = self.client.post(self.url, {
            'email': 'LOGIN@EXAMPLE.COM', 'password': 'TestPass99!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Token Refresh Tests
# ---------------------------------------------------------------------------

class TokenRefreshTests(APITestCase):

    def setUp(self):
        self.url = reverse('accounts:token-refresh')
        self.user = make_user(email='refresh@example.com', password='TestPass99!', verified=True)
        self.refresh_token = RefreshToken.for_user(self.user)

    def test_refresh_success(self):
        response = self.client.post(self.url, {
            'refresh': str(self.refresh_token),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('access', response.data['data'])

    def test_refresh_invalid_token(self):
        response = self.client.post(self.url, {
            'refresh': 'this.is.not.a.valid.token',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_missing_token(self):
        response = self.client.post(self.url, {}, format='json')
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
        ])


# ---------------------------------------------------------------------------
# Logout Tests
# ---------------------------------------------------------------------------

class LogoutTests(APITestCase):

    def setUp(self):
        self.url = reverse('accounts:logout')
        self.user = make_user(email='logout@example.com', password='TestPass99!', verified=True)
        self.refresh = RefreshToken.for_user(self.user)

    def test_logout_success(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(self.refresh.access_token)}')
        response = self.client.post(self.url, {'refresh': str(self.refresh)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    def test_logout_without_auth_header(self):
        response = self.client.post(self.url, {'refresh': str(self.refresh)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_missing_refresh_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(self.refresh.access_token)}')
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_blacklisted_token_cannot_be_reused(self):
        """After logout, the same refresh token must be rejected."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(self.refresh.access_token)}')
        self.client.post(self.url, {'refresh': str(self.refresh)}, format='json')
        # Try to use the same refresh token again
        response = self.client.post(self.url, {'refresh': str(self.refresh)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Me (Profile) Tests
# ---------------------------------------------------------------------------

class MeTests(APITestCase):

    def setUp(self):
        self.url = reverse('accounts:me')
        self.user = make_user(email='me@example.com', password='TestPass99!', verified=True)

    def test_me_authenticated(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['email'], 'me@example.com')

    def test_me_returns_no_password(self):
        self.client.credentials(HTTP_AUTHORIZATION=auth_header(self.user))
        response = self.client.get(self.url)
        self.assertNotIn('password', response.data['data'])

    def test_me_unauthenticated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Password Reset Tests
# ---------------------------------------------------------------------------

class PasswordResetTests(APITestCase):

    def setUp(self):
        self.request_url = reverse('accounts:password-reset')
        self.confirm_url = reverse('accounts:password-reset-confirm')
        self.user = make_user(email='reset@example.com', password='OldPass99!', verified=True)

    def test_reset_request_known_email_returns_200(self):
        """Always 200 — anti-enumeration."""
        response = self.client.post(self.request_url, {'email': 'reset@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    def test_reset_request_unknown_email_still_returns_200(self):
        """Must not reveal whether email exists."""
        response = self.client.post(self.request_url, {'email': 'ghost@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reset_confirm_success(self):
        raw_otp = '777777'
        make_otp(self.user, purpose=OTPVerification.Purpose.PASSWORD_RESET, raw_otp=raw_otp)
        response = self.client.post(self.confirm_url, {
            'email': 'reset@example.com',
            'otp': raw_otp,
            'new_password': 'NewStrongPass2!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass2!'))

    def test_reset_confirm_otp_consumed_after_success(self):
        raw_otp = '888888'
        otp_record = make_otp(self.user, purpose=OTPVerification.Purpose.PASSWORD_RESET, raw_otp=raw_otp)
        self.client.post(self.confirm_url, {
            'email': 'reset@example.com',
            'otp': raw_otp,
            'new_password': 'NewStrongPass2!',
        }, format='json')
        otp_record.refresh_from_db()
        self.assertTrue(otp_record.is_used)

    def test_reset_confirm_wrong_otp(self):
        make_otp(self.user, purpose=OTPVerification.Purpose.PASSWORD_RESET, raw_otp='111111')
        response = self.client.post(self.confirm_url, {
            'email': 'reset@example.com',
            'otp': '000000',
            'new_password': 'NewStrongPass2!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_confirm_expired_otp(self):
        make_otp(self.user, purpose=OTPVerification.Purpose.PASSWORD_RESET, raw_otp='222222', expired=True)
        response = self.client.post(self.confirm_url, {
            'email': 'reset@example.com',
            'otp': '222222',
            'new_password': 'NewStrongPass2!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_confirm_weak_new_password(self):
        raw_otp = '333333'
        make_otp(self.user, purpose=OTPVerification.Purpose.PASSWORD_RESET, raw_otp=raw_otp)
        response = self.client.post(self.confirm_url, {
            'email': 'reset@example.com',
            'otp': raw_otp,
            'new_password': '1234',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
