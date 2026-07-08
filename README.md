# AgroTrack — Backend API

> A production-ready logistics dispatch platform for agro commodities.  
> Connects **Senders/Receivers**, **Dispatchers**, and **Admins** to manage shipments from creation through proof-of-delivery (POD), with fleet management, analytics, and public tracking.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 5.2 + Django REST Framework 3.17 |
| Auth | SimpleJWT (stateless, rotating refresh tokens + blacklist) |
| Database | PostgreSQL (Railway) / SQLite (local dev) |
| Static Files | WhiteNoise (compressed + fingerprinted) |
| Schema / Docs | drf-spectacular (OpenAPI 3 — ReDoc + Swagger) |
| Deployment | Railpack via Railway |
| Runtime | Python 3.14 |

---

## Project Structure

```
agrotrack/
├── accounts/               # Auth & user management
│   ├── admin.py            # User model registered in Django Admin
│   ├── managers.py         # Custom UserManager (email-based auth)
│   ├── models.py           # User, OTPVerification
│   ├── permissions.py      # RBAC permission classes (IsSender, IsDispatcher, IsAdminUser…)
│   ├── serializers.py      # All auth business logic + UserProfile
│   ├── tests.py            # Auth test suite
│   ├── urls.py             # Mounted at /api/v1/auth/
│   ├── utils.py            # OTP utils, email helpers, custom exception handler
│   └── views.py            # API views + OpenAPI annotations
│
├── orders/                 # Order lifecycle, fleet, drivers, reports
│   ├── admin.py            # Order, Driver, Vehicle registered in Django Admin
│   ├── models.py           # Order, Driver, Vehicle, OrderStatusHistory, OrderMessage
│   ├── serializers.py      # OrderCreate, OrderList, OrderDetail, Driver, Vehicle…
│   ├── tests.py            # Orders & fleet test suite
│   ├── urls.py             # Mounted at /api/v1/orders/
│   └── views.py            # API views + OpenAPI annotations
│
├── admin_api/              # Admin-only portal endpoints
│   ├── admin.py            # PlatformSettings registered in Django Admin
│   ├── models.py           # PlatformSettings (singleton)
│   ├── serializers.py      # Admin-scoped serializers for users, drivers, vehicles, settings
│   ├── tests.py            # Admin API test suite
│   ├── urls.py             # Mounted at /api/v1/admin/
│   └── views.py            # Admin views + OpenAPI annotations
│
├── public_api/             # Unauthenticated public endpoints
│   ├── serializers.py      # PublicTrackingSerializer
│   ├── tests.py            # Public API test suite
│   ├── urls.py             # Mounted at /api/v1/public/
│   └── views.py            # PublicPlatformStatsView, PublicTrackingView
│
├── agrotrack/
│   ├── settings.py         # Main settings
│   ├── settings_test.py    # Test overrides (no throttle, MD5 hasher)
│   ├── urls.py             # Root URL config + docs routes
│   └── wsgi.py
│
├── .env.example            # Environment variable reference
├── railway.toml            # Railway deployment config (Railpack)
├── requirements.txt
└── schema.yml              # Generated OpenAPI 3 schema
```

---

## Local Development

### Prerequisites
- Python 3.12+
- pip

### Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd agrotrack

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your local environment file
cp .env.example .env
# Edit .env and fill in SECRET_KEY at minimum

# 5. Apply migrations
python manage.py migrate

# 6. Create a superuser (for /admin/ access)
python manage.py createsuperuser

# 7. Start the dev server
python manage.py runserver
```

The API is now available at `http://localhost:8000`.

### Generating a SECRET_KEY

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Running Tests

```bash
# Full test suite (79 tests)
python manage.py test --settings=agrotrack.settings_test

# Single app
python manage.py test accounts --settings=agrotrack.settings_test
python manage.py test orders --settings=agrotrack.settings_test
python manage.py test admin_api --settings=agrotrack.settings_test
python manage.py test public_api --settings=agrotrack.settings_test

# Verbose output
python manage.py test --settings=agrotrack.settings_test --verbosity=2
```

Test settings (`settings_test.py`) automatically:
- Disable all throttling (no 429s in the test runner)
- Use MD5 password hasher (significantly faster than PBKDF2)
- Force console email backend (OTPs printed to stdout)

---

## API Documentation

When the server is running, interactive docs are available at:

| URL | Description |
|---|---|
| `/api/docs/` | **ReDoc** — full reference UI |
| `/api/docs/swagger/` | **Swagger UI** — interactive testing |
| `/api/schema/` | Raw OpenAPI 3 YAML schema |

---

## API Overview

### Authentication (`/api/v1/auth/`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/register/` | None | Register a new sender account |
| POST | `/verify-otp/` | None | Verify email OTP |
| POST | `/resend-otp/` | None | Resend registration OTP |
| POST | `/login/` | None | Login and obtain JWT pair |
| POST | `/token/refresh/` | None | Refresh access token |
| POST | `/logout/` | JWT | Blacklist refresh token |
| GET / PATCH | `/me/` | JWT | Get or update user profile |
| POST | `/password-reset/` | None | Request password reset OTP |
| POST | `/password-reset/confirm/` | None | Confirm reset with OTP |

### Orders (`/api/v1/orders/`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/dashboard/` | JWT | Dashboard stats (role-aware) |
| GET | `/` | JWT | List shipments |
| POST | `/` | JWT (Sender) | Create new shipment request |
| GET / PATCH | `/{id}/` | JWT | Get or update shipment details |
| GET | `/{id}/timeline/` | JWT | Auto-generated status timeline |
| PATCH | `/timeline/{event_id}/` | JWT (Dispatcher/Admin) | Edit timeline event description |
| GET / POST | `/{id}/messages/` | JWT | Context-aware chat thread |
| POST | `/{id}/messages/read/` | JWT | Mark incoming messages as read |
| GET | `/fleet/` | JWT (Dispatcher) | Fleet overview |
| GET | `/drivers/` | JWT (Dispatcher) | Active drivers for assignment |
| GET | `/vehicles/` | JWT (Dispatcher) | Vehicles for assignment |
| GET | `/reports/` | JWT (Dispatcher/Admin) | Delivery & revenue analytics |

### Admin Portal (`/api/v1/admin/`)

> All endpoints require a JWT from an account with `role = admin`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/dashboard/` | Platform-wide KPI overview |
| GET | `/users/` | List all sender accounts |
| GET / PATCH | `/users/{id}/` | View or suspend a user |
| GET / POST | `/dispatchers/` | List dispatchers or create one |
| GET / PATCH | `/dispatchers/{id}/` | View or update a dispatcher |
| GET / POST | `/drivers/` | List drivers or register one |
| GET / PATCH | `/drivers/{id}/` | View or verify a driver |
| GET / POST | `/vehicles/` | Fleet registry list or add vehicle |
| GET / PATCH | `/vehicles/{id}/` | View or update a vehicle |
| GET / PATCH | `/settings/` | View or update platform settings |
| GET | `/analytics/` | Revenue, region, and user acquisition charts |

### Public API (`/api/v1/public/`)

> No authentication required.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/stats/` | Platform statistics for marketing page |
| GET | `/track/{tracking_number}/` | Track a shipment by its tracking number |

---

## User Roles

| Role | Value | Description |
|---|---|---|
| Sender / Receiver | `sender` | Creates orders, tracks delivery, confirms POD |
| Dispatcher | `dispatcher` | Manages order queue, assigns drivers/vehicles |
| Admin | `admin` | Platform administration, user and fleet management |

Role is set at registration via the `role` field (defaults to `sender` if omitted).

---

## Deployment (Railway)

### Required Environment Variables

Set these in your Railway service's **Variables** tab:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key — generate with `get_random_secret_key()` |
| `DEBUG` | ✅ | Must be `False` in production |
| `ALLOWED_HOSTS` | ✅ | Comma-separated — include your `*.railway.app` domain |
| `CSRF_TRUSTED_ORIGINS` | ✅ | Include `https://<your-app>.up.railway.app` |
| `DATABASE_URL` | ✅ | Auto-injected by Railway Postgres plugin |
| `CORS_ALLOWED_ORIGINS` | ✅ | Comma-separated frontend origin(s) |
| `EMAIL_BACKEND` | ✅ | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | ✅ | SMTP host (e.g. `smtp.gmail.com`) |
| `EMAIL_HOST_USER` | ✅ | SMTP username |
| `EMAIL_HOST_PASSWORD` | ✅ | SMTP password / app password |
| `DEFAULT_FROM_EMAIL` | ❌ | Defaults to `AgroTrack <noreply@agrotrack.com>` |
| `OTP_EXPIRY_MINUTES` | ❌ | Defaults to `10` |
| `AWS_STORAGE_BUCKET_NAME` | ❌ | S3 bucket name (REQUIRED for POD image uploads) |
| `AWS_ACCESS_KEY_ID` | ❌ | AWS Access Key (REQUIRED if bucket name is set) |
| `AWS_SECRET_ACCESS_KEY` | ❌ | AWS Secret Key (REQUIRED if bucket name is set) |
| `AWS_S3_REGION_NAME` | ❌ | e.g. `eu-west-1` (Defaults to `us-east-1`) |

### Deploy Flow

Railway runs these steps automatically on every push:

```
1. RAILPACK build     → pip install -r requirements.txt
                      → python manage.py collectstatic --noinput
2. Pre-deploy         → python manage.py migrate --noinput
3. Start              → gunicorn agrotrack.wsgi:application \
                          --bind 0.0.0.0:$PORT \
                          --workers 2 --threads 2
4. Health check       → GET /api/schema/ must return 200
```

### Django Admin

Available at `/admin/`. Create a superuser via Railway's shell:

```bash
python manage.py createsuperuser
```

All models are registered: **User**, **OTPVerification**, **Order**, **Driver**, **Vehicle**, **OrderStatusHistory**, **PlatformSettings**.

---

## Security

- **Passwords**: PBKDF2 + SHA-256; full Django validator suite including similarity checks
- **OTPs**: SHA-256 hashed, never stored in plaintext; constant-time comparison via `hmac.compare_digest`
- **JWT**: 15-min access tokens, 7-day rotating refresh tokens; blacklisted on logout
- **Throttling**: Anon `20/min`, user `100/min`, OTP resend `3/hour`, login `10/min`
- **HSTS**: 1-year max-age with subdomains + preload (production only)
- **HTTPS**: SSL redirect enforced in production (`SECURE_SSL_REDIRECT=True`)
- **UUIDs**: User primary keys are UUIDs — no sequential ID leakage
- **CORS**: Strict origin whitelist via `CORS_ALLOWED_ORIGINS`
