# ============================================================
#  Xavfsizlik yordamchilari
# ============================================================
import hmac
import secrets
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from urllib.parse import urlsplit

# Rasm uchun ruxsat etilgan kengaytmalar
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}


# ------------------------------------------------------------
#  Open-redirect himoyasi
#  Maqsad: "url yozib hech qayerga o'tib bo'lmasin" — ya'ni
#  foydalanuvchi/attacker bergan URL faqat shu sayt ichidagi
#  xavfsiz yo'lga yo'naltira oladi, tashqi saytga hech qachon emas.
# ------------------------------------------------------------
def is_safe_internal_path(value) -> bool:
    """
    URL faqat ichki (same-site) yo'l bo'lsa True qaytaradi.

    Xavfsiz deb hisoblanadi:  /products/12
    Xavfsiz EMAS:            //evil.com, https://evil.com, javascript:...
    """
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value.startswith("/"):
        return False
    parts = urlsplit(value)
    # netloc bo'lsa demak //evil.com ko'rinishi (protocol-relative) — taqiqlanadi
    if parts.netloc or parts.scheme:
        return False
    return True


def safe_next_url(value, default: str = "/") -> str:
    """
    'next' / 'redirect' parametrini tekshirib qaytaradi.
    Xavfsiz ichki yo'l bo'lmasa default qiymat ishlatiladi.
    """
    if is_safe_internal_path(value):
        return value
    return default


def constant_time_equal(left: str, right: str) -> bool:
    """Ikkita matnni vaqt jihatidan xavfsiz (constant-time) solishtirish."""
    return hmac.compare_digest(str(left), str(right))


def random_numeric_code(length: int = 6) -> str:
    """Xavfsiz tasodifiy raqamli kod (secrets moduli)."""
    if length < 4:
        raise ValueError("Kod uzunligi kamida 4 bo'lishi kerak")
    return "".join(secrets.choice("0123456789") for _ in range(length))


def random_token_hex(length: int = 24) -> str:
    """Xavfsiz tasodifiy hex token."""
    return secrets.token_hex(length // 2)


# ------------------------------------------------------------
#  Rasm yuklash xavfsizligi
# ------------------------------------------------------------
import io

from django.core.files.base import ContentFile


def optimize_image(upload):
    """
    Katta rasmlarni avtomatik siqish (JPEG, maks 1920px).

    Telefon kameralari 8–12 MB rasm beradi — xotirada qayta kodlaymiz:
    maksimal 1920px + JPEG sifat 82 (natija odatda 150–500 KB).
    EXIF aylanishi ham to'g'rilanadi. Buzilgan faylda None qaytaradi.
    """
    try:
        from PIL import Image, ImageOps

        upload.seek(0)
        img = Image.open(upload)
        img.load()
        img = ImageOps.exif_transpose(img)  # EXIF aylanishini to'g'rilash
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((1920, 1920), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True, progressive=True)
        buf.seek(0)
        return ContentFile(buf.getvalue())
    except Exception:
        return None


def product_image_path(instance, filename: str) -> str:
    """
    Yuklangan rasm nomi hech qachon foydalanuvchi nomi bilan
    saqlanmaydi — tasodifiy UUID ishlatiladi (path traversal / 
    nom to'qnashuvining oldini oladi).
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = ".jpg"
    return f"products/{secrets.token_hex(16)}{ext}"


def validate_image_upload(upload) -> None:
    """
    Rasm faylini tekshiradi:
      - ruxsat etilgan kengaytma
      - hajm chegarasi (settings.MAX_IMAGE_SIZE_MB)
      - ruxsat etilgan MIME (Pillow orqali tekshiriladi)
    """
    if upload is None:
        return
    name = getattr(upload, "name", "") or ""
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError("Faqat JPG, PNG yoki WEBP rasmlar yuklash mumkin.")

    size = getattr(upload, "size", 0) or 0
    max_bytes = getattr(settings, "MAX_IMAGE_SIZE_MB", 5) * 1024 * 1024
    if size > max_bytes:
        raise ValidationError(
            f"Rasm hajmi {settings.MAX_IMAGE_SIZE_MB} MB dan oshmasligi kerak."
        )

    # MIME ni Pillow bilan haqiqatan tekshirish (kengaytma aldovidan himoya)
    try:
        from PIL import Image

        upload.seek(0)
        img = Image.open(upload)
        img.verify()
        upload.seek(0)
        if img.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("Rasm formati qo'llab-quvvatlanmaydi.")
    except ValidationError:
        raise
    except Exception as exc:  # buzilgan fayl
        raise ValidationError("Fayl haqiqiy rasm emas.") from exc
