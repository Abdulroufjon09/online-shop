# ============================================================
#  ONLINE SAVDO — Umumiy (base) sozlamalar
#  development.py / production.py shu fayldan meros oladi.
# ============================================================
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# .env faylini yuklash (agar mavjud bo'lsa)
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    """Vergul bilan ajratilgan .env qiymatini ro'yxatga aylantiradi."""
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def database_config() -> dict:
    """DATABASE_URL bo'lsa PostgreSQL, bo'lmasa SQLite (dev)."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        # postgresql://user:password@host:port/name
        body = url.split("://", 1)[1]
        cred, _, rest = body.partition("@")
        host_port, _, db = rest.rpartition("/")
        host, _, port = host_port.partition(":")
        user, _, password = cred.partition(":")
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db,
            "USER": user,
            "PASSWORD": password,
            "HOST": host or "db",
            "PORT": port or "5432",
        }
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }


# ------------------------------------------------------------
#  Asosiy Django
# ------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "no-production-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "django.contrib.messages",
    # Uchinchi tomon
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    # Loyiha app'lari
    "apps.core",
    "apps.accounts",
    "apps.products",
    "apps.cart",
    "apps.orders",
    "apps.discounts",
    "apps.telegram_bot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise: statik fayllarni WSGI sun'iy orqali xizmat ko'rsatish (Render/Vercel/PythonAnywhere)
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Xavfsizlik sarlavhalari (qo'shimcha qatlam)
    "config.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": database_config()}

AUTH_USER_MODEL = "accounts.User"

# ------------------------------------------------------------
#  Parol hashlash — Argon2 birinchi o'rinda
# ------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------------------------------
#  DRF — API sozlamalari
# ------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Browsable API o'chirilgan — faqat JSON (attack sirtini kamaytiradi)
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 12,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_RATES": {
        # Umumiy (tizimga kirmaganlar)
        "anon": "100/min",
        # Tizimga kirganlar
        "user": "300/min",
        # Auth endpointlari — brute-force himoyasi
        "auth_login": "10/min",
        "auth_register": "6/hour",
        # Kod tekshirish — brute-force himoyasi
        "code_verify": "10/min",
        "resend_code": "3/hour",
        "bind_telegram": "5/hour",
    },
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    # JWT yaroqsiz / muddati o'tgan bo'lsa oddiy 401 (WWW-Authenticate'siz)
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
}

# ------------------------------------------------------------
#  JWT (djangorestframework-simplejwt)
# ------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
}

# ------------------------------------------------------------
#  CORS — faqat ruxsat etilgan manzillarga ochiq
# ------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["authorization", "content-type", "accept", "origin", "x-requested-with"]

# ------------------------------------------------------------
#  Statik / media
# ------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Static fayllarni inline (CSS/JS) ko'p vaqt tsizishgan fayllar uchun cheklangan
# va cache-busting sozlangan holda WhiteNoise yonida xizmat qiladi.
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
WHITENOISE_USE_FINDERS = True

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------
#  Vaqt mintaqasi
# ------------------------------------------------------------
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------
#  Transport xavfsizligi (production qat'iyroq — prod settings)
# ------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

# ------------------------------------------------------------
#  Ilova mantig'i uchun konstantalar
# ------------------------------------------------------------
SITE_NAME = "Online Savdo"
PHONE_VERIFY_CODE_TTL_MINUTES = 10
MAX_VERIFY_ATTEMPTS = 5
MAX_IMAGE_SIZE_MB = 5

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").strip()
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").strip().rstrip("/")
ADMIN_TELEGRAM_CHAT_IDS = env_list("ADMIN_TELEGRAM_CHAT_IDS")
# Webhook maxfiy yo'li (SECRET_KEY dan barqaror hosila)
WEBHOOK_PATH_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "") or ""
if not WEBHOOK_PATH_SECRET:
    import hashlib

    WEBHOOK_PATH_SECRET = hashlib.sha256(("webhook:" + SECRET_KEY).encode()).hexdigest()[:32]

# Background tasklar
USE_CELERY = env_bool("USE_CELERY", False)
CELERY_BROKER_URL = os.getenv("BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_TASK_ALWAYS_EAGER = not USE_CELERY

# Demo
DEMO_ADMIN_PHONE = os.getenv("DEMO_ADMIN_PHONE", "998901234567")
DEMO_ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "Admin@123456")
ADMIN_FULL_NAME = os.getenv("ADMIN_FULL_NAME", "Abdulroufjon")
DEMO_USER_PHONE = os.getenv("DEMO_USER_PHONE", "998901234568")
DEMO_USER_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "User@123456")

# ------------------------------------------------------------
#  Loglash
# ------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "apps.telegram_bot": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
