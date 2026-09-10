# ============================================================
#  Foydalanuvchi modeli — telefon raqam orqali auth
# ============================================================
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.security import constant_time_equal, random_numeric_code
from apps.core.validators import mask_phone, normalize_phone

from .managers import UserManager


class User(AbstractUser):
    """Ro'yxatdan o'tish: telefon + parol, Telegram orqali kod tasdiqlash."""

    username = None  # username ishlatilmaydi — faqat telefon

    phone = models.CharField(
        "Telefon",
        max_length=20,
        unique=True,
        help_text="Kanonik shakl: +998XXXXXXXXX",
    )
    full_name = models.CharField("To'liq ism", max_length=150, blank=True)
    address = models.TextField("Manzil", blank=True)
    avatar = models.ImageField(
        "Avatar",
        upload_to="avatars/",
        null=True,
        blank=True,
    )

    is_verified = models.BooleanField(
        "Tasdiqlangan",
        default=False,
        help_text="Telefon raqami kod orqali tasdiqlangani",
    )

    # --- Telegram bog'lash ---
    telegram_chat_id = models.BigIntegerField(
        "Telegram chat ID", null=True, blank=True, unique=True
    )
    telegram_linked_at = models.DateTimeField(null=True, blank=True)

    # --- Ro'yxatdan o'tish kodini tasdiqlash (vremenny) ---
    verification_code = models.CharField(max_length=6, null=True, blank=True)
    code_created_at = models.DateTimeField(null=True, blank=True)
    code_attempts = models.PositiveSmallIntegerField(default=0)

    # --- Profil orqali Telegram chatni bog'lash (bot /link) ---
    bind_code = models.CharField(max_length=6, null=True, blank=True)
    bind_code_created_at = models.DateTimeField(null=True, blank=True)
    pending_chat_id = models.BigIntegerField(null=True, blank=True)

    # --- Rol: xaridor / sotuvchi / kuryer / punkt xodimi / admin ---
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Xaridor"
        SELLER = "seller", "Sotuvchi"
        COURIER = "courier", "Kuryer"
        PICKUP = "pickup", "Punkt xodimi"
        ADMIN = "admin", "Admin"

    # Ariza orqali olinadigan rol kodlari (nested enum ichida o'z a'zolarini
    # nom bilan chaqirib bo'lmaydi — shuning uchun kodlar ko'rinishida)
    APPLICABLE_ROLES = ("courier", "pickup", "seller")

    role = models.CharField(
        "Rol", max_length=10, choices=Role.choices, default=Role.CUSTOMER
    )
    # Ko'p rol: foydalanuvchi bir vaqtda bir nechta rolga ega bo'lishi mumkin
    # (masalan, sotuvchi + kuryer). "customer" barchaga implicit berilgan.
    roles = models.JSONField(
        "Qo'shimcha rollar",
        default=list,
        blank=True,
        help_text="Rol kodlari ro'yxati: [\"seller\", \"courier\"]",
    )
    pickup_point = models.ForeignKey(
        "orders.PickupPoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
        verbose_name="Punkt",
    )

    objects = UserManager()

    @property
    def is_courier(self) -> bool:
        return self.role == self.Role.COURIER or self.has_role("courier")

    @property
    def is_pickup_staff(self) -> bool:
        return self.role == self.Role.PICKUP or self.has_role("pickup")

    def has_role(self, role_code: str) -> bool:
        """Foydalanuvchida ko'rsatilgan rol bormi (ko'p rol hisobga olingan)."""
        if self.is_staff or self.role == self.Role.ADMIN:
            return True
        if self.role == role_code:
            return True
        return role_code in (self.roles or [])

    def add_role(self, role_code: str) -> None:
        """Yangi rol qo'shadi (takrorlanmaydi)."""
        current = list(self.roles or [])
        if role_code not in current:
            current.append(role_code)
            self.roles = current

    def remove_role(self, role_code: str) -> None:
        """Rolni olib tashlaydi."""
        current = list(self.roles or [])
        if role_code in current:
            current.remove(role_code)
            self.roles = current

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"
        ordering = ["-date_joined"]

    def __str__(self):
        name = self.full_name or self.phone
        return f"{name} ({mask_phone(self.phone)})"

    # ------------------------------------------------------------
    #  Ro'yxatdan o'tish kodini tasdiqlash
    # ------------------------------------------------------------
    @property
    def verification_code_expired(self) -> bool:
        if not self.code_created_at:
            return True
        ttl = timedelta(minutes=settings.PHONE_VERIFY_CODE_TTL_MINUTES)
        return timezone.now() > self.code_created_at + ttl

    def regenerate_verification_code(self) -> str:
        code = random_numeric_code(6)
        self.verification_code = code
        self.code_created_at = timezone.now()
        self.code_attempts = 0
        return code

    def check_verification_code(self, code: str) -> bool:
        """Kodni tekshiradi — muvaffaqiyatda kod o'chiriladi."""
        if (
            not self.verification_code
            or not code
            or self.verification_code_expired
            or self.code_attempts >= settings.MAX_VERIFY_ATTEMPTS
        ):
            return False
        if not constant_time_equal(self.verification_code, code):
            self.code_attempts += 1
            if self.code_attempts >= settings.MAX_VERIFY_ATTEMPTS:
                # 5 ta noto'g'ri urinish — kod bekor qilinadi
                self.verification_code = None
            self.save(update_fields=["code_attempts", "verification_code"])
            return False
        # Muvaffaqiyat — kodni darhol o'chirish (qayta ishlatib bo'lmasin)
        self.verification_code = None
        self.code_created_at = None
        self.code_attempts = 0
        self.save(update_fields=["verification_code", "code_created_at", "code_attempts"])
        return True

    def mark_verified(self) -> None:
        self.is_verified = True
        self.is_active = True
        self.verification_code = None
        self.code_created_at = None
        self.code_attempts = 0
        self.save(
            update_fields=[
                "is_verified",
                "is_active",
                "verification_code",
                "code_created_at",
                "code_attempts",
            ]
        )

    # ------------------------------------------------------------
    #  Telegram chat bog'lash (bot /link -> profilga kod kiritish)
    # ------------------------------------------------------------
    @property
    def telegram_linked(self) -> bool:
        return self.telegram_chat_id is not None

    @property
    def bind_code_expired(self) -> bool:
        if not self.bind_code_created_at:
            return True
        ttl = timedelta(minutes=settings.PHONE_VERIFY_CODE_TTL_MINUTES)
        return timezone.now() > self.bind_code_created_at + ttl

    def prepare_telegram_bind(self, chat_id: int) -> str:
        """Bot /link buyrug'i: chat_id ni bog'lash uchun kod yaratadi."""
        code = random_numeric_code(6)
        self.bind_code = code
        self.bind_code_created_at = timezone.now()
        self.pending_chat_id = chat_id
        self.save(
            update_fields=["bind_code", "bind_code_created_at", "pending_chat_id"]
        )
        return code

    def confirm_telegram_bind(self, code: str) -> bool:
        """Profil sahifasidagi kod bilan chat bog'lashni yakunlaydi."""
        if (
            not self.pending_chat_id
            or not self.bind_code
            or self.bind_code_expired
            or not constant_time_equal(self.bind_code, code)
        ):
            return False
        self.telegram_chat_id = self.pending_chat_id
        self.telegram_linked_at = timezone.now()
        self.pending_chat_id = None
        self.bind_code = None
        self.bind_code_created_at = None
        self.save(
            update_fields=[
                "telegram_chat_id",
                "telegram_linked_at",
                "pending_chat_id",
                "bind_code",
                "bind_code_created_at",
            ]
        )
        return True

    def clean(self):
        try:
            self.phone = normalize_phone(self.phone)
        except ValidationError:
            raise


# Ariza orqali olinadigan rollar (label bilan) — RoleApplication.role uchun
ROLE_APPLICATION_CHOICES = [
    (User.Role.SELLER.value, User.Role.SELLER.label),
    (User.Role.COURIER.value, User.Role.COURIER.label),
    (User.Role.PICKUP.value, User.Role.PICKUP.label),
]


class RoleApplication(models.Model):
    """
    Sotuvchi / kuryer / punkt ochish arizasi.
    Admin (yoki Telegram inline tugmalari) qabul qilganda rol beriladi.

    Xavfsizlik: karta raqami to'liq saqlanmaydi — faqat maskalangan ko'rinish
    va oxirgi 4 ta raqam (PCI-DSS kabi to'liq himoya talab qilinadi).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        APPROVED = "approved", "Qabul qilingan"
        REJECTED = "rejected", "Rad etilgan"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="role_applications",
        verbose_name="Arizachi",
    )
    role = models.CharField(
        "So'ralgan rol",
        max_length=10,
        choices=ROLE_APPLICATION_CHOICES,
    )

    # Shaxs ma'lumotlari (ariza paytidagi snapshot)
    full_name = models.CharField("To'liq ism", max_length=150)
    phone = models.CharField("Telefon", max_length=20)
    address = models.TextField("Aniq manzil")
    # Manzilning xaritadagi nuqtasi (aniq manzil uchun)
    address_latitude = models.DecimalField(
        "Manzil kengligi", max_digits=9, decimal_places=6, null=True, blank=True
    )
    address_longitude = models.DecimalField(
        "Manzil uzunligi", max_digits=9, decimal_places=6, null=True, blank=True
    )
    passport = models.CharField(
        "Passport (seriya + raqam)", max_length=30, blank=True
    )
    # Karta — to'liq raqam YO'Q, faqat maskalangan + oxirgi 4 xona
    card_number_masked = models.CharField("Karta (maskalangan)", max_length=24)
    card_last4 = models.CharField("Karta oxirgi 4", max_length=4)

    # Punkt ochish so'rovi uchun
    point_name = models.CharField("Punkt nomi", max_length=150, blank=True)
    point_address = models.TextField("Punkt manzili", blank=True)
    point_latitude = models.DecimalField(
        "Punkt kengligi", max_digits=9, decimal_places=6, null=True, blank=True
    )
    point_longitude = models.DecimalField(
        "Punkt uzunligi", max_digits=9, decimal_places=6, null=True, blank=True
    )

    status = models.CharField(
        "Holat", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    note = models.TextField("Admin izohi", blank=True)
    reviewer = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
        verbose_name="Ko'rib chiqqan",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rol arizasi"
        verbose_name_plural = "Rol arizalari"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["role", "status"]),
        ]

    def __str__(self):
        return f"{self.get_role_display()} arizasi #{self.pk} ({self.user_id})"

    @property
    def card_display(self) -> str:
        return self.card_number_masked
