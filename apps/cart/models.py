# ============================================================
#  Savat modellari — ma'lumotlar bazasida saqlanadi
# ============================================================
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Cart(models.Model):
    """Har bir foydalanuvchida bitta savat (DB saqlanadi)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
        verbose_name="Foydalanuvchi",
    )
    coupon = models.ForeignKey(
        "discounts.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Qo'llangan kupon",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Savat"
        verbose_name_plural = "Savatlar"

    def __str__(self):
        return f"Savat #{self.pk} ({self.user.phone})"

    # ------------------------------------------------------------
    #  Hisoblashlar — doim server tomonda (serializerlar chaqiradi)
    # ------------------------------------------------------------
    @property
    def active_coupon_percent(self) -> Decimal:
        """Amal qilayotgan kupon foizi (aks holda 0)."""
        if self.coupon and self.coupon.is_valid_now:
            return Decimal(self.coupon.percent)
        return Decimal("0")

    @property
    def subtotal(self) -> Decimal:
        """Barcha bandlar yig'indisi (narx x soni)."""
        total = Decimal("0")
        for item in self.items.select_related("product").all():
            total += item.price * item.quantity
        return total

    @property
    def discount_amount(self) -> Decimal:
        percent = self.active_coupon_percent
        if not percent:
            return Decimal("0")
        return (self.subtotal * percent / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def total(self) -> Decimal:
        return (self.subtotal - self.discount_amount).quantize(Decimal("0.01"))

    @property
    def items_count(self) -> int:
        """Savatdagi jami mahsulot soni (har bir nusxa sanaladi)."""
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    """Savatdagi bitta mahsulot qatori."""

    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", verbose_name="Savat"
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="Mahsulot",
    )
    quantity = models.PositiveSmallIntegerField(
        "Soni",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
    )
    # Qo'shilish paytidagi narx (snapshot) — keyinchalik o'zgarsa ham adolatli
    price = models.DecimalField(
        "Narx (qo'shilgandagi)", max_digits=12, decimal_places=2
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Savat bandi"
        verbose_name_plural = "Savat bandlari"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"], name="unique_cart_product"
            )
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def line_total(self) -> Decimal:
        return (self.price * self.quantity).quantize(Decimal("0.01"))
