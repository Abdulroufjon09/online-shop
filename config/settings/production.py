# ============================================================
#  Production sozlamalari — QAT'IY xavfsizlik
# ============================================================
import os

from .base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY.startswith("dev-") or "no-production-secret" in SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY production uchun kuchli qiymat bilan sozlanishi shart!")

# HTTPS
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 yil
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Hujjat rejasida ko'rsatilganidek, ALLOWED_HOSTS .env orqali beriladi
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["127.0.0.1", "localhost"]:
    raise RuntimeError("ALLOWED_HOSTS production uchun .env da ko'rsatilishi shart!")
