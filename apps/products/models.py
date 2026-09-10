# ============================================================
#  Kategoriya va mahsulot modellari
# ============================================================
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.security import product_image_path


class Category(models.Model):
    name = models.CharField("Nomi", max_length=100)
    slug = models.SlugField("Slug", max_length=120, unique=True)
    is_active = models.BooleanField("Faol", default=True)

    class Meta:
        verbose_name = "Kategoriya"
        verbose_name_plural = "Kategoriyalar"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    name = models.CharField("Nomi", max_length=255)
    slug = models.SlugField("Slug", max_length=280, unique=True, blank=True)
    description = models.TextField("Tavsif", blank=True)
    price = models.DecimalField(
        "Narx (so'm)", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    discount_percent = models.PositiveSmallIntegerField(
        "Chegirma %", default=0,
        validators=[MaxValueValidator(90)],
        help_text="0 bo'lsa chegirma yo'q. Max 90%.",
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products",
        verbose_name="Kategoriya",
    )
    stock = models.PositiveIntegerField("Zaxiradagi soni", default=0)
    image = models.ImageField(
        "Rasm", upload_to=product_image_path, blank=True, null=True
    )
    is_active = models.BooleanField("Ko'rinadigan", default=True)
    is_featured = models.BooleanField("Tavsiya etilgan", default=False)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products_sold",
        verbose_name="Sotuvchi (seller)",
        help_text="Bo'sh bo'lsa — do'konning o'z mahsuloti.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["seller", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "mahsulot"
            self.slug = base
            counter = 1
            while Product.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    # ------------------------------------------------------------
    #  Narx hisoblash — doim server tomonda
    # ------------------------------------------------------------
    @property
    def final_price(self) -> Decimal:
        """Chegirma hisobga olingan yakuniy narx."""
        if self.discount_percent:
            return (self.price * (100 - self.discount_percent) / 100).quantize(Decimal("0.01"))
        return self.price

    @property
    def has_discount(self) -> bool:
        return self.discount_percent > 0

    @property
    def in_stock(self) -> bool:
        return self.stock > 0


class Review(models.Model):
    """
    Mahsulot sharhi — 1..5 yulduzli baho + izoh.
    Har bir foydalanuvchi bitta mahsulotga faqat bitta sharh yozishi mumkin
    (qayta yozish — yangilash hisoblanadi).
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews",
        verbose_name="Mahsulot",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
        verbose_name="Foydalanuvchi",
    )
    rating = models.PositiveSmallIntegerField(
        "Baho (yulduz)",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField("Sharh", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mahsulot sharhi"
        verbose_name_plural = "Mahsulot sharhlari"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="one_review_per_user_product"
            ),
        ]
        indexes = [models.Index(fields=["product", "-created_at"])]

    def __str__(self):
        return f"{self.product.name} — {self.rating}★ ({self.user_id})"


class ProductImage(models.Model):
    """
    Mahsulot galereyasi — bitta mahsulotda 2..5 ta rasm.
    Birinchi (position=0) rasm Product.image da asosiy sifatida saqlanadi.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images",
        verbose_name="Mahsulot",
    )
    image = models.ImageField("Rasm", upload_to=product_image_path)
    position = models.PositiveSmallIntegerField("Tartib", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mahsulot rasmi"
        verbose_name_plural = "Mahsulot rasmlari"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.name} — rasm #{self.position}"


class WishlistItem(models.Model):
    """
    Istaklar — foydalanuvchi keyinroq sotib olishi mumkin bo'lgan mahsulotlar.
    Bir foydalanuvchi bir mahsulotni bir marta qo'shadi (takroriy qo'shish zararsiz).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist",
        verbose_name="Foydalanuvchi",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wished_by",
        verbose_name="Mahsulot",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Istak"
        verbose_name_plural = "Istaklar"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="one_wish_per_user_product"
            ),
        ]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.user_id} → {self.product.name}"
