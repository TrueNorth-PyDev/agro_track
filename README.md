# Agro Track — Backend API

> Logistics dispatch platform for agro commodities.  
> Connects **Senders/Receivers** and **Dispatchers** to manage orders from creation through delivery and proof of delivery (POD).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 5.2 + Django REST Framework 3.17 |
| Auth | SimpleJWT (stateless, rotating refresh tokens) |
| Database | PostgreSQL (Railway) / SQLite (local dev) |
| Static Files | WhiteNoise (compressed + fingerprinted) |
| Schema / Docs | drf-spectacular (OpenAPI 3) |
| Build | Railpack via Railway |
| Runtime | Python 3.12 |

---

## Project Structure

```
agrotrack/
├── accounts/               # Auth & user management app
│   ├── migrations/
│   ├── admin.py
│   ├── managers.py         # Custom UserManager (email-based auth)
│   ├── models.py           # User, OTPVerification
│   ├── permissions.py      # RBAC permission classes
│   ├── serializers.py      # All auth business logic
│   ├── tests.py            # 54 unit tests
│   ├── urls.py
│   ├── utils.py            # OTP utils, email helpers, exception handler
│   └── views.py            # API endpoints + OpenAPI schema annotations
├── agrotrack/
│   ├── settings.py         # Main settings
│   ├── settings_test.py    # Test overrides (no throttle, MD5 hasher)
│   ├── urls.py             # Root URL config + docs routes
│   └── wsgi.py
├── .env.example            # Environment variable reference
├── .gitignore
├── manage.py
├── railway.toml            # Railway deployment config (Railpack)
└── requirements.txt
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

# 6. Create a superuser (optional)
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
# Full test suite (54 tests, ~1s)
python manage.py test accounts --settings=agrotrack.settings_test

# Verbose output
python manage.py test accounts --settings=agrotrack.settings_test --verbosity=2
```

Test settings (`settings_test.py`) automatically:
- Disable all throttling (no 429s in the runner)
- Use MD5 password hasher (33× faster than PBKDF2)
- Force console email backend

---

## API Documentation

When the server is running, interactive docs are available at:

| URL | Description |
|---|---|
| `/api/docs/` | **ReDoc** — full reference UI |
| `/api/docs/swagger/` | **Swagger UI** — interactive testing |
| `/api/schema/` | Raw OpenAPI 3 YAML schema |

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

Available at `/admin/`. Requires a superuser — create one via Railway's shell:

```bash
python manage.py createsuperuser
```

---

## User Roles

| Role | Value | Description |
|---|---|---|
| Sender / Receiver | `sender` | Creates orders, tracks delivery, confirms POD |
| Dispatcher | `dispatcher` | Manages order queue, assigns drivers/vehicles |
| Admin | `admin` | Platform administration, user management |

Role is set at registration via the `role` field (defaults to `sender` if omitted).

---

## Security

- **Passwords**: Hashed with PBKDF2 + SHA-256; validated against Django's full validator suite including similarity checks
- **OTPs**: SHA-256 hashed, never stored in plaintext; compared with `hmac.compare_digest` (timing-safe)
- **JWT**: 15-min access tokens, 7-day rotating refresh tokens; blacklisted on logout
- **Throttling**: Anon `20/min`, user `100/min`, OTP resend `3/hour`, login `10/min`
- **HSTS**: 1-year max-age with preload (production only)
- **HTTPS**: SSL redirect enforced in production (`SECURE_SSL_REDIRECT=True`)
