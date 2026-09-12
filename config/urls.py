# ============================================================
#  ONLINE SAVDO — Asosiy URL marshrutlari
#
#  Tuzilishi:
#    /api/auth/...        — ro'yxatdan o'tish, login, profil
#    /api/products/...    — katalog (ochiq)
#    /api/cart/...        — savat (faqat o'z foydalanuvchisi)
#    /api/orders/...      — buyurtmalar (faqat o'z foydalanuvchisi)
#    /api/discounts/...   — chegirma kodlari
#    /api/admin/...       — faqat is_staff (admin panel)
#    /telegram/webhook/   — Telegram webhook
# ============================================================
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve as media_serve

from apps.accounts.admin_urls import urlpatterns as accounts_admin_urls
from apps.discounts.admin_urls import urlpatterns as discounts_admin_urls
from apps.orders.admin_urls import urlpatterns as orders_admin_urls
from apps.products.admin_urls import urlpatterns as products_admin_urls


def health_check(_request):
    """Server holatini tekshirish endpoint'i (monitoring uchun)."""
    return JsonResponse({"status": "ok", "service": "online-savdo-api"})


# Barcha admin (is_staff) marshrutlari bitta namespace ostida
_admin_urls = (
    accounts_admin_urls
    + products_admin_urls
    + orders_admin_urls
    + discounts_admin_urls
)

urlpatterns = [
    path("api/health/", health_check, name="health"),
    # --- Auth (foydalanuvchi) ---
    path("api/auth/", include("apps.accounts.urls")),
    # --- Katalog (ochiq) ---
    path("api/products/", include("apps.products.urls")),
    # --- Savat va buyurtmalar (autentifikatsiya talab) ---
    path("api/cart/", include("apps.cart.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/discounts/", include("apps.discounts.urls")),
    # --- Kuryer, punkt va sotuvchi panellari (rolga qarab) ---
    path("api/courier/", include("apps.orders.courier_urls")),
    path("api/pickup/", include("apps.orders.pickup_urls")),
    path("api/seller/", include("apps.products.seller_urls")),
    # --- Telegram bot webhook ---
    path("telegram/", include("apps.telegram_bot.urls")),
    # --- Admin (faqat is_staff) ---
    path("api/admin/", include((_admin_urls, "admin-api"))),
]

if settings.DEBUG:
    # Dev rejimida media/static fayllarni xizmat ko'rsatish
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Yuklangan rasmlar (/media/) — production'da (DEBUG=False) ham ko'rinishi
# shart. `static()` helper'i DEBUG=False da bo'sh ro'yxat qaytaradi, shuning
# uchun bevosita `serve` view ishlatiladi: u faqat MEDIA_ROOT ichidan o'qiydi
# (path traversal himoyasi o'rnatilgan) va proxy/W bunda WhiteNoise'ga xalaqit bermaydi.
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", media_serve, {"document_root": settings.MEDIA_ROOT}),
]
