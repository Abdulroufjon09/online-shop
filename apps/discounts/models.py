# ============================================================
#  Chegirma kuponi modeli
# ============================================================
from django.conf import settings
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

code_validator = RegexValidator(
    regex=r"^[A-Z0-9_-]{4,50}$",
    message="Kod faqat lotin harflari (A-Z), raqamlar, tire va pastki chiziqdan iborat bo'lishi kerak (4–50 belgi).",
)


class Coupon(models.Model):
    """Bir martalik emas — muddatli foizli chegirma kodi."""

    code = models.CharField(
        "Kod", max_length=50, unique=True, validators=[code_validator]
    )
    percent = models.PositiveSmallIntegerField(
        "Chegirma %",
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        help_text="1–90% oralig'ida.",
    )
    description = models.CharField(
        "Tavsif (xabar matni)", max_length=255, blank=True
    )
    valid_from = models.DateTimeField("Boshlanish vaqti", default=timezone.now)
    valid_to = models.DateTimeField("Tugash vaqti")
    is_active = models.BooleanField("Faol", default=True)
    max_uses = models.PositiveIntegerField(
        "Maksimal foydalanish soni", null=True, blank=True,
        help_text="Bo'sh bo'lsa — cheklanmagan.",
    )
    used_count = models.PositiveIntegerField("Ishlatilgan soni", default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Yaratgan admin",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Chegirma kupon"
        verbose_name_plural = "Chegirma kuponlari"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["valid_to", "is_active"]),
        ]

    def __str__(self):
        return f"{self.code} ({self.percent}%)"

    @property
    def is_valid_now(self) -> bool:
        """Hozirgi vaqtda qo'llash mumkinmi?"""
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.valid_to

    def increment_use(self) -> None:
        self.used_count = models.F("used_count") + 1
        self.save(update_fields=["used_count"])
        self.refresh_from_db(fields=["used_count"])

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.valid_to and self.valid_from and self.valid_to <= self.valid_from:
            raise ValidationError({"valid_to": "Tugash vaqti boshlanish vaqtidan keyin bo'lishi kerak."})
        self.code = (self.code or "").upper().strip()
