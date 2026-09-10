# ============================================================
#  Brute-force himoyasi uchun maxsus throttles
#
#  Stollar "DEFAULT_THROTTLE_RATES" da belgilanadi (base.py).
#  auth_login: 10/min, auth_register: 6/hour, code_verify: 10/min,
#  resend_code: 3/hour, bind_telegram: 5/hour
# ============================================================
from rest_framework.throttling import SimpleRateThrottle


class _IpBaseThrottle(SimpleRateThrottle):
    """IP-manzil asosidagi umumiy throttle."""

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginRateThrottle(_IpBaseThrottle):
    """Login urinishlarini cheklash (parol brute-force)."""
    scope = "auth_login"


class RegisterRateThrottle(_IpBaseThrottle):
    """Registratsiya urinishlarini cheklash."""
    scope = "auth_register"


class VerifyCodeThrottle(_IpBaseThrottle):
    """Kod tekshirish urinishlarini cheklash (kod brute-force)."""
    scope = "code_verify"


class BindTelegramThrottle(_IpBaseThrottle):
    """Telegram bog'lash urinishlarini cheklash."""
    scope = "bind_telegram"


class ResendCodeThrottle(SimpleRateThrottle):
    """Telefon raqam bo'yicha kod qayta yuborishni cheklash."""
    scope = "resend_code"

    def get_cache_key(self, request, view):
        phone = str(getattr(request.data, "get", lambda *a: None)("phone", "") or "")
        if not phone:
            return None  # tekshirish o'tkazib yuborilmaydi — validatorda ushlanadi
        return self.cache_format % {"scope": self.scope, "ident": phone}
