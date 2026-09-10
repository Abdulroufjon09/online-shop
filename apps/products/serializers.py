# ============================================================
#  Mahsulot / kategoriya serializers
# ============================================================
import uuid

from django.utils.text import slugify
from rest_framework import serializers

from apps.core.security import validate_image_upload

from .models import Category, Product, ProductImage, Review

MAX_PRODUCT_IMAGES = 5
MIN_PRODUCT_IMAGES = 2


class CategorySerializer(serializers.ModelSerializer):
    """Kategoriya (ochiq katalog va admin uchun)."""

    product_count = serializers.SerializerMethodField(read_only=True)
    # Slug majburiy emas — bo'sh bo'lsa nomdan avtomatik yaratiladi
    slug = serializers.SlugField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "product_count", "is_active"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        """Bir xil nomdagi kategoriya yaratilmasin (barcha holatlarda)."""
        qs = Category.objects.filter(name__iexact=value.strip())
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Bu nomdagi kategoriya allaqachon mavjud."
            )
        return value

    def validate(self, attrs):
        """Slug avtomatik generatsiya + unique kafolati."""
        name = attrs.get("name") or (self.instance.name if self.instance else "")
        slug = attrs.get("slug") or (self.instance.slug if self.instance else "") or slugify(name)
        if not slug:
            slug = f"kategoriya-{uuid.uuid4().hex[:8]}"
        # Unique emas bo'lsa qisqartma qo'shamiz
        base_slug, n = slug, 2
        qs = Category.objects.all()
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        while qs.filter(slug=slug).exists():
            slug = f"{base_slug}-{n}"
            n += 1
        attrs["slug"] = slug
        return attrs

    def get_product_count(self, obj) -> int:
        """Faqat faol (ko'rinadigan) mahsulotlar soni."""
        return obj.products.filter(is_active=True).count()


def _gallery_urls(obj) -> list:
    """Mahsulot rasmlari URL'lari (tartib bo'yicha)."""
    return [img.image.url for img in obj.images.all()]


class ProductPublicSerializer(serializers.ModelSerializer):
    """Katalogda ko'rinadigan mahsulot (narx doim serverdan)."""

    category_id = serializers.IntegerField(source="category.id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    final_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    has_discount = serializers.BooleanField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    average_rating = serializers.SerializerMethodField(read_only=True)
    reviews_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category_id",
            "category_name",
            "price",
            "discount_percent",
            "final_price",
            "has_discount",
            "in_stock",
            "stock",
            "image",
            "is_featured",
            "average_rating",
            "reviews_count",
        ]

    def get_average_rating(self, obj):
        value = getattr(obj, "average_rating", None)
        if value is None:
            return None
        return round(float(value), 2)

    def get_reviews_count(self, obj):
        value = getattr(obj, "reviews_count", None)
        return int(value) if value is not None else 0


class ProductDetailSerializer(ProductPublicSerializer):
    """Mahsulot detali — to'liqroq ma'lumot + galereya."""

    gallery = serializers.SerializerMethodField()

    class Meta(ProductPublicSerializer.Meta):
        fields = ProductPublicSerializer.Meta.fields + ["gallery", "description", "created_at"]

    def get_gallery(self, obj) -> list:
        return _gallery_urls(obj)


class ReviewSerializer(serializers.ModelSerializer):
    """Mahsulot sharhi — foydalanuvchi bir marta baholaydi (yangi yozuv = yangilash)."""

    user_name = serializers.SerializerMethodField(read_only=True)
    is_own = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Review
        fields = ["id", "product", "rating", "comment", "user_name", "is_own", "created_at", "updated_at"]
        read_only_fields = ["id", "product", "user_name", "is_own", "created_at", "updated_at"]

    def get_user_name(self, obj) -> str:
        if obj.user.full_name:
            return obj.user.full_name
        from apps.core.validators import mask_phone

        return mask_phone(obj.user.phone)

    def get_is_own(self, obj) -> bool:
        request = self.context.get("request")
        return bool(
            request and request.user and request.user.is_authenticated
            and request.user.pk == obj.user_id
        )


class ProductAdminSerializer(serializers.ModelSerializer):
    """
    Admin CRUD — to'liq boshqaruv.

    Rasm yuklash: multipart/form-data, `images` maydoni (2..5 fayl).
    - Yangi mahsulot: kamida 2 ta rasm majburiy.
    - Tahrirlash (PATCH): `images` jo'natilmasa mavjud rasmlar saqlanadi;
      jo'natilsa barchasi yangi rasmlar bilan almashtiriladi.
    """

    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=Category.objects.all(),
        write_only=True,
    )
    category = CategorySerializer(read_only=True)
    final_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    gallery = serializers.SerializerMethodField(read_only=True)
    images = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False),
        write_only=True,
        required=False,
        error_messages={"required": "Kamida 2 ta rasm yuklash shart."},
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category_id",
            "category",
            "description",
            "price",
            "discount_percent",
            "stock",
            "image",
            "gallery",
            "images",
            "is_active",
            "is_featured",
            "final_price",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "image", "created_at", "updated_at"]

    def get_gallery(self, obj) -> list:
        return _gallery_urls(obj)

    def validate_images(self, files):
        files = list(files or [])
        if not files:
            if self.instance is None:
                raise serializers.ValidationError(
                    {"images": "Kamida 2 ta rasm yuklash shart."}
                )
            return files
        if len(files) < MIN_PRODUCT_IMAGES:
            raise serializers.ValidationError(
                {"images": f"Kamida {MIN_PRODUCT_IMAGES} ta rasm yuklanishi shart."}
            )
        if len(files) > MAX_PRODUCT_IMAGES:
            raise serializers.ValidationError(
                {"images": f"Ko'pi bilan {MAX_PRODUCT_IMAGES} ta rasm yuklash mumkin."}
            )
        for upload in files:
            validate_image_upload(upload)
        return files

    def validate_discount_percent(self, value: int) -> int:
        if value and not (0 <= value <= 90):
            raise serializers.ValidationError("Chegirma 0–90% oralig'ida bo'lishi kerak.")
        return value

    # ------------------------------------------------------------
    #  Yaratish / yangilash — rasmlarni ProductImage sifatida saqlash
    # ------------------------------------------------------------
    @staticmethod
    def _replace_images(product: Product, files) -> None:
        product.images.all().delete()
        for index, upload in enumerate(files):
            ProductImage.objects.create(
                product=product, image=upload, position=index
            )
        first = files[0]
        product.image = first
        product.save(update_fields=["image"])

    def create(self, validated_data):
        files = validated_data.pop("images", [])
        product = super().create(validated_data)
        if files:
            self._replace_images(product, files)
        return product

    def update(self, instance, validated_data):
        files = validated_data.pop("images", None)
        product = super().update(instance, validated_data)
        if files is not None:
            if not files and product.is_active:
                raise serializers.ValidationError(
                    {"images": "Faol mahsulotda kamida 2 ta rasm bo'lishi kerak."}
                )
            if files:
                self._replace_images(product, files)
        return product


class ProductSellerSerializer(ProductAdminSerializer):
    """Sotuvchi o'z mahsulotlarini boshqaradi (is_featured faqat admin)."""

    image_items = serializers.SerializerMethodField(read_only=True)

    class Meta(ProductAdminSerializer.Meta):
        read_only_fields = ProductAdminSerializer.Meta.read_only_fields + ["is_featured"]
        fields = ProductAdminSerializer.Meta.fields + ["image_items"]

    def get_image_items(self, obj) -> list:
        return [
            {"id": img.pk, "url": img.image.url}
            for img in obj.images.all()
        ]
