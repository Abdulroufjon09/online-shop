# ============================================================
#  Telefon raqam normalizatsiyasi (O'zbekiston)
# ============================================================
import re

from django.core.exceptions import ValidationError

_PHONE_RE = re.compile(r"^\+998\d{9}$")


def normalize_phone(value: str) -> str:
    """
    Telefon raqamini kanonik shaklga keltiradi: +998XXXXXXXXX

    Qabul qilinadi:  +998901234567 | 998901234567 | 901234567 | 8 901234567
    """
    if value is None:
        raise ValidationError("Telefon raqami kiritilishi shart.")
    digits = re.sub(r"\D", "", str(value))

    # +998901234567 / 998901234567 (12 raqam, davlat kodi bilan)
    if len(digits) == 12 and digits.startswith("998"):
        digits = digits[3:]  # faqat lokal qism: 901234567
    # 8901234567 (boshi 8 bilan) -> lokal
    elif len(digits) == 10 and digits.startswith("8"):
        digits = digits[1:]
    # 901234567 lokal (9 raqam)
    elif len(digits) != 9:
        raise ValidationError(
            "Telefon raqam noto'g'ri. Namuna: +998901234567"
        )

    canonical = "+998" + digits
    if not _PHONE_RE.match(canonical):
        raise ValidationError("Telefon raqam noto'g'ri. Namuna: +998901234567")
    return canonical


def mask_phone(phone: str) -> str:
    """Telefonni qisman yashiradi: +998 90 **** 4567"""
    if not phone or len(phone) < 12:
        return phone
    return f"{phone[:4]} {phone[4:6]} **** {phone[-4:]}"
