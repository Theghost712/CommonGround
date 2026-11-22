import os
from pathlib import Path
from datetime import timedelta

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path):
    """Load KEY=VALUE lines from a local .env file without overriding real env vars.

    Keeps machine-specific values (LAN IPs, secrets) out of the code. Blank lines
    and # comments are ignored; values may be wrapped in single or double quotes.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


# backend/.env wins over the project-root .env; both lose to real environment variables.
load_env_file(BASE_DIR / ".env")
load_env_file(BASE_DIR.parent / ".env")

# On Render, the public hostname is known only at runtime: use it as the default for
# hosts, origins and email links (explicit environment variables still win).
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME:
    for key, value in {
        "DJANGO_ALLOWED_HOSTS": RENDER_EXTERNAL_HOSTNAME,
        "CORS_ALLOWED_ORIGINS": f"https://{RENDER_EXTERNAL_HOSTNAME}",
        "CSRF_TRUSTED_ORIGINS": f"https://{RENDER_EXTERNAL_HOSTNAME}",
        "FRONTEND_URL": f"https://{RENDER_EXTERNAL_HOSTNAME}",
    }.items():
        os.environ.setdefault(key, value)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-this-secret-key-before-production")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"


def env_list(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost",
)

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "corsheaders", "rest_framework", "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist", "channels",
    "apps.accounts",
    "apps.communities",
    "apps.discussions",
    "apps.messaging",
    "apps.notifications",
    "apps.events",
    "apps.social",
    "apps.moderation",
    "apps.calls",
    "apps.stories",
    "apps.safety",
]
MIDDLEWARE = [
    "apps.common.health.HealthCheckMiddleware",  # first: probes use internal IPs/plain HTTP
    "django.middleware.security.SecurityMiddleware", "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if not DEBUG:
    # Serves collected static files and the built React app (single-service hosting).
    # In development Vite serves the app, so it's left out (it would warn about a
    # missing STATIC_ROOT on every request).
    MIDDLEWARE.insert(MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages", "config.admin_context.admin_dashboard_stats"]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # The app runs under ASGI, where Django's persistent connections (CONN_MAX_AGE)
    # are not reused across request threads and can pile up until PostgreSQL refuses
    # new ones. PostgreSQL therefore uses psycopg's connection pool (Django 5.1+):
    # each worker process keeps up to DB_POOL_MAX_SIZE connections and shares them.
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=0)}
    if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql" and os.getenv("DB_POOL", "True").lower() == "true":
        DATABASES["default"].setdefault("OPTIONS", {})["pool"] = {
            "min_size": int(os.getenv("DB_POOL_MIN_SIZE", "2")),
            "max_size": int(os.getenv("DB_POOL_MAX_SIZE", "10")),
            "timeout": int(os.getenv("DB_POOL_TIMEOUT", "10")),
        }
else:
    # timeout: wait up to 20s for a write lock instead of failing with "database is locked"
    # when chat sockets and HTTP requests write at the same moment.
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3", "OPTIONS": {"timeout": 20}}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Dar_es_Salaam"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles"))
# When set (e.g. "/protected-media/"), media responses hand the file to nginx via
# X-Accel-Redirect after Django checks permission; nginx then streams it (with Range).
MEDIA_ACCEL_REDIRECT_PREFIX = os.getenv("MEDIA_ACCEL_REDIRECT_PREFIX", "")
# Single-service hosting (e.g. Render): Django also serves the built React app.
# FRONTEND_DIST points at frontend/dist; WhiteNoise serves its files (hashed assets
# cached for a year) and every other non-API path returns index.html.
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.is_dir() else None
WHITENOISE_IMMUTABLE_FILE_TEST = r"^/assets/.+-[A-Za-z0-9_-]{8,}\.(js|css|woff2?|svg|png|jpe?g|webp)$"
# Content-Security-Policy for the app shell when Django serves it (nginx sets its own).
# Extra media origins (e.g. https://<project>.supabase.co for uploaded files) are added.
CSP_MEDIA_ORIGINS = env_list("CSP_MEDIA_ORIGINS", "")

# Uploaded files: local disk by default; S3-compatible object storage (AWS S3,
# Cloudflare R2, Supabase Storage…) when S3_BUCKET is set. Hosts like Render's free
# tier wipe the local disk on every restart, so they need object storage.
S3_BUCKET = os.getenv("S3_BUCKET", "")
if S3_BUCKET:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": S3_BUCKET,
                "endpoint_url": os.getenv("S3_ENDPOINT_URL") or None,
                "region_name": os.getenv("S3_REGION") or None,
                "access_key": os.getenv("S3_ACCESS_KEY_ID", ""),
                "secret_key": os.getenv("S3_SECRET_ACCESS_KEY", ""),
                "default_acl": None,
                "file_overwrite": False,
                "querystring_auth": True,
                "querystring_expire": int(os.getenv("S3_URL_EXPIRE", "3600")),
                "addressing_style": "path",
                "signature_version": "s3v4",
            },
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    # After Django checks permission, media responses redirect to a short-lived
    # signed URL so the bytes (and video Range requests) go straight from storage.
    MEDIA_REDIRECT_TO_STORAGE = os.getenv("MEDIA_REDIRECT_TO_STORAGE", "True").lower() == "true"
else:
    MEDIA_REDIRECT_TO_STORAGE = False
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TEST_RUNNER = "config.test_runner.TempMediaTestRunner"

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
REST_FRAMEWORK = {
    # Plain JWT auth plus a check that the session wasn't revoked (password change, sign out everywhere).
    "DEFAULT_AUTHENTICATION_CLASSES": ("apps.accounts.security.RevocableJWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticatedOrReadOnly",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ("rest_framework.filters.SearchFilter", "rest_framework.filters.OrderingFilter"),
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        # Each page load spends ~2 anonymous requests (CSRF + session refresh).
        "anon": os.getenv("THROTTLE_ANON_RATE", "1000/hour"),
        "user": os.getenv("THROTTLE_USER_RATE", "5000/hour"),
        # Login and registration: strict per-IP limit against password guessing.
        "auth": os.getenv("THROTTLE_AUTH_RATE", "10/minute"),
        # Contact matching: limits how fast anyone can probe which numbers belong to members.
        "contacts": os.getenv("THROTTLE_CONTACTS_RATE", "20/hour"),
        # Photo/video uploads (stories, posts) per user.
        "uploads": os.getenv("THROTTLE_UPLOADS_RATE", "60/hour"),
        # Abuse reports per user (stops report-bombing).
        "reports": os.getenv("THROTTLE_REPORTS_RATE", "20/hour"),
        # Requests that send email (password reset, verification resend, email change).
        "account_email": os.getenv("THROTTLE_ACCOUNT_EMAIL_RATE", "5/hour"),
        # Starting voice/video calls (stops ring-spamming someone).
        "calls": os.getenv("THROTTLE_CALLS_RATE", "30/hour"),
    },
    # How many reverse proxies sit in front of Django. 0 = trust only REMOTE_ADDR.
    # Must be explicit: DRF's default (None) trusts the raw X-Forwarded-For header,
    # which lets any client dodge rate limits. Set 1 behind the Vite dev proxy or nginx.
    "NUM_PROXIES": int(os.getenv("NUM_PROXIES", "0")),
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "commonground",
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "commonground-development",
            "KEY_PREFIX": "commonground",
        }
    }

# Links in account emails (reset password, confirm email) point at the frontend.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "CommonGround <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Development default: each email is written as a file in backend/sent_emails/
# so you can open the links. Production uses SMTP (set EMAIL_HOST etc.).
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.filebased.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_FILE_PATH = os.getenv("EMAIL_FILE_PATH", str(BASE_DIR / "sent_emails"))
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() == "true"
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
# Password-reset links work for 1 hour and only once; email links for 3 days.
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "3600"))
EMAIL_LINK_MAX_AGE_SECONDS = int(os.getenv("EMAIL_LINK_MAX_AGE_SECONDS", str(3 * 24 * 3600)))

# Voice/video calls (WebRTC). STUN finds each side's public address; TURN relays media
# when a direct connection is impossible (strict NAT, mobile networks). TURN is needed
# for reliable calls on the internet: run coturn with use-auth-secret and set
# TURN_URLS (comma-separated, e.g. turn:turn.example.org:3478,turns:turn.example.org:5349)
# and TURN_SECRET (coturn's static-auth-secret).
WEBRTC_STUN_URLS = env_list("WEBRTC_STUN_URLS", "stun:stun.l.google.com:19302")
TURN_URLS = env_list("TURN_URLS", "")
TURN_SECRET = os.getenv("TURN_SECRET", "")
TURN_CREDENTIAL_TTL = int(os.getenv("TURN_CREDENTIAL_TTL", str(6 * 3600)))

# Country code assumed for local phone numbers ("0712…") when matching contacts.
DEFAULT_PHONE_COUNTRY_CODE = os.getenv("DEFAULT_PHONE_COUNTRY_CODE", "255")

WEBSOCKET_TICKET_TTL_SECONDS = int(os.getenv("WEBSOCKET_TICKET_TTL_SECONDS", "15"))
if not 1 <= WEBSOCKET_TICKET_TTL_SECONDS <= 60:
    raise ImproperlyConfigured("WEBSOCKET_TICKET_TTL_SECONDS must be between 1 and 60")

# Refresh credentials are sent only to the authentication endpoints.
# Set REFRESH_COOKIE_SECURE=True in production (HTTPS required).
REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "cg_refresh")
REFRESH_COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "False").strip().lower() == "true"
REFRESH_COOKIE_SAMESITE = os.getenv("REFRESH_COOKIE_SAMESITE", "Lax")
REFRESH_COOKIE_PATH = os.getenv("REFRESH_COOKIE_PATH", "/api/v1/auth/")
 

# Logs go to stdout/stderr (collected by systemd/journald or the container runtime).
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # 4xx noise (bad tokens, throttled requests) is normal; keep server errors.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

# Fail fast instead of silently running production on development defaults
# (dev secret key, DEBUG=True, SQLite, per-process cache for WebSocket tickets).
DJANGO_ENV = os.getenv("DJANGO_ENV", "development").strip().lower()
PRODUCTION_REQUIRED_SETTINGS = (
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "CORS_ALLOWED_ORIGINS",
    "CSRF_TRUSTED_ORIGINS",
    "DATABASE_URL",
    "REDIS_URL",
)
if DJANGO_ENV == "production":
    missing = [name for name in PRODUCTION_REQUIRED_SETTINGS if not os.getenv(name, "").strip()]
    if missing:
        raise ImproperlyConfigured(f"DJANGO_ENV=production requires: {', '.join(missing)}")
    if DEBUG:
        raise ImproperlyConfigured("DJANGO_ENV=production requires DJANGO_DEBUG=False")
    if not os.getenv("FRONTEND_URL", "").startswith("https://"):
        raise ImproperlyConfigured("DJANGO_ENV=production requires FRONTEND_URL=https://… (used in email links)")
    if EMAIL_BACKEND.endswith("smtp.EmailBackend") and not EMAIL_HOST:
        raise ImproperlyConfigured("DJANGO_ENV=production requires EMAIL_HOST (or another EMAIL_BACKEND) to send account emails")

if DJANGO_ENV == "production":
    # Behind a TLS-terminating proxy (nginx / load balancer).
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"
    # Load-balancer health probes often arrive over plain HTTP inside the platform.
    SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    REFRESH_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # Preloading is hard to undo (browsers ship the list), so it's an explicit opt-in.
    SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False").lower() == "true"
    if not SECURE_HSTS_PRELOAD:
        SILENCED_SYSTEM_CHECKS = ["security.W021"]
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
