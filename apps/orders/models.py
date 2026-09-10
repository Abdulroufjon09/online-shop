# ============================================================
#  Buyurtma, yetkazib berish punktlari va buyurtma bandlari
# ============================================================
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class PickupPoint(models.Model):
    """Punkt — buyurtmalar tayyorlanadigan / olinadigan joy."""

    name = models.CharField("Nomi", max_length=120)
    address = models.CharField("Manzil", max_length=255)
    phone = models.CharField("Telefon", max_length=20, blank=True)
    latitude = models.DecimalField(
        "Kenglik", max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        "Uzunlik", max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    is_active = models.BooleanField("Faol", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Punkt"
        verbose_name_plural = "Punktlar"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Order(models.Model):
    """Buyurtma — narxlar va holatlar doim serverda himoyalangan."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Kutilmoqda")
        PROCESSING = "processing", _("Qayta ishlanmoqda")
        READY = "ready", _("Tayyor")
        OUT_FOR_DELIVERY = "out_for_delivery", _("Kuryerda")
        DELIVERED = "delivered", _("Yetkazilgan")
        CANCELLED = "cancelled", _("Bekor qilingan")

    class DeliveryType(models.TextChoices):
        DELIVERY = "delivery", _("Yetkazib berish")
        PICKUP = "pickup", _("Punktdan olish")

    delivery_type = models.CharField(
        "Yetkazish turi", max_length=10, choices=DeliveryType.choices,
        default=DeliveryType.DELIVERY,
    )
    pickup_point = models.ForeignKey(
        PickupPoint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Punkt",
    )
    # Xaritadagi manzil (buyurtma paytidagi nuqta)
    latitude = models.DecimalField(
        "Kenglik", max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        "Uzunlik", max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courier_orders",
        verbose_name="Kuryer",
    )

    order_number = models.CharField(
        "Buyurtma raqami", max_length=20, unique=True, blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Foydalanuvchi",
    )
    # Yetkazib berish ma'lumotlari (buyurtma paytidagi snapshot)
    full_name = models.CharField("Qabul qiluvchi", max_length=150)
    phone = models.CharField("Telefon", max_length=20)
    address = models.TextField("Manzil")
    note = models.TextField("Izoh", blank=True)

    status = models.CharField(
        "Holat", max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Moliyaviy snapshotlar — keyinchalik o'zgartirilmaydi
    subtotal = models.DecimalField(
        "Summa", max_digits=14, decimal_places=2, default=Decimal("0")
    )
    discount_amount = models.DecimalField(
        "Chegirma", max_digits=14, decimal_places=2, default=Decimal("0")
    )
    total = models.DecimalField(
        "Jami", max_digits=14, decimal_places=2, default=Decimal("0")
    )
    coupon = models.ForeignKey(
        "discounts.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Kupon",
    )
    coupon_code = models.CharField("Kupon kodi", max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Buyurtma #{self.order_number or self.pk} ({self.status})"

    @property
    def products_count(self) -> int:
        return sum(item.quantity for item in self.items.all())

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.order_number:
            self.order_number = f"OS-{self.pk:06d}"
            # qo'shimcha saqlashni cheklash uchun update_fields bilan yozamiz
            Order.objects.filter(pk=self.pk).update(order_number=self.order_number)

    @property
    def delivery_point(self) -> str:
        """Yetkaziladigan nuqta tavsifi (kuryer/punkt uchun)."""
        if self.delivery_type == self.DeliveryType.PICKUP:
            return self.pickup_point.address if self.pickup_point else self.address
        return self.address


class OrderItem(models.Model):
    """Buyurtmadagi bitta mahsulot qatori (to'liq snapshot)."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name="Buyurtma"
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="Mahsulot",
    )
    # Snapshotlar: mahsulot o'chirilsa/ozgarsa ham buyurtma tarixi buzilmaydi
    product_name = models.CharField("Mahsulot nomi", max_length=255)
    unit_price = models.DecimalField("Narx", max_digits=12, decimal_places=2)
    discount_percent = models.PositiveSmallIntegerField("Chegirma %", default=0)
    quantity = models.PositiveSmallIntegerField("Soni", default=1)
    line_total = models.DecimalField(
        "Jami", max_digits=14, decimal_places=2, default=Decimal("0")
    )

    class Meta:
        verbose_name = "Buyurtma bandi"
        verbose_name_plural = "Buyurtma bandlari"

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
