# ============================================================
#  Xavfsizlik sarlavhalari (Security Headers) middleware
#  Har bir javobga qo'shimcha himoya sarlavhalarini qo'shadi.
# ============================================================
from django.conf import settings


class SecurityHeadersMiddleware:
    """Brauzer darajasidagi himoya sarlavhalarini har bir response'ga qo'shadi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Kontent turlarini taxmin qilishni taqiqlash (MIME sniffing)
        response["X-Content-Type-Options"] = "nosniff"

        # Frame ichida ochilishni taqiqlash (clickjacking)
        response["X-Frame-Options"] = "DENY"

        # Referrer ma'lumotlarini cheklash
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Keraksiz brauzer imkoniyatlarini o'chirish
        response["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )

        # CSP — admin sozlamasida ko'rsatilgan bo'lsa
        csp = getattr(settings, "CONTENT_SECURITY_POLICY", "")
        if csp:
            response["Content-Security-Policy"] = csp

        # HSTS faqat HTTPS (production) da
        if getattr(settings, "SECURE_HSTS_SECONDS", 0) and request.is_secure():
            response["Strict-Transport-Security"] = (
                f"max-age={settings.SECURE_HSTS_SECONDS}; includeSubDomains"
            )
        return response
