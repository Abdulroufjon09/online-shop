# ============================================================
#  Savat serializers
# ============================================================
from rest_framework import serializers

from apps.products.serializers import ProductPublicSerializer

from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    """Savatdagi mahsulot qatori."""

    product = ProductPublicSerializer(read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "quantity", "price", "line_total"]
        read_only_fields = fields

    def get_line_total(self, obj) -> str:
        return f"{obj.line_total:.2f}"


class CartCouponSerializer(serializers.Serializer):
    """Savatingizdagi kupon (xavfsiz ko'rinish)."""

    code = serializers.CharField(read_only=True)
    percent = serializers.IntegerField(read_only=True)
    valid_to = serializers.DateTimeField(read_only=True)


class CartSerializer(serializers.ModelSerializer):
    """
    To'liq savat holati:
    items, subtotal, coupon, discount_amount, total — hammasi serverda hisoblanadi.
    """

    items = CartItemSerializer(many=True, read_only=True)
    coupon = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "items",
            "items_count",
            "subtotal",
            "coupon",
            "discount_amount",
            "total",
        ]
        read_only_fields = fields

    def _coupon_data(self, obj):
        if obj.coupon is None:
            return None
        return {
            "code": obj.coupon.code,
            "percent": obj.coupon.percent,
            "valid_to": obj.coupon.valid_to,
            "is_valid_now": obj.coupon.is_valid_now,
        }

    def get_coupon(self, obj):
        return self._coupon_data(obj)

    def get_subtotal(self, obj) -> str:
        return f"{obj.subtotal:.2f}"

    def get_discount_amount(self, obj) -> str:
        return f"{obj.discount_amount:.2f}"

    def get_total(self, obj) -> str:
        return f"{obj.total:.2f}"

    def get_items_count(self, obj) -> int:
        return obj.items_count


class ActiveProductField(serializers.PrimaryKeyRelatedField):
    """Faqat sotuvda bo'lgan (faol) mahsulotlarni qabul qiladi."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.error_messages["does_not_exist"] = "Mahsulot topilmadi."
        self.error_messages["incorrect_type"] = "Mahsulot identifikatori noto'g'ri."

    def get_queryset(self):
        from apps.products.models import Product

        return Product.objects.filter(is_active=True, category__is_active=True)


class CartAddItemSerializer(serializers.Serializer):
    """Savatga qo'shish so'rovi."""

    product = ActiveProductField()
    quantity = serializers.IntegerField(min_value=1, max_value=99, default=1)

    def validate(self, attrs):
        product = attrs["product"]
        if product.stock <= 0:
            raise serializers.ValidationError(
                {"product": "Bu mahsulot hozircha zaxirada yo'q."}
            )
        return attrs


class CartUpdateItemSerializer(serializers.Serializer):
    """Savatdagi band sonini o'zgartirish."""

    quantity = serializers.IntegerField(min_value=1, max_value=99)

    def __init__(self, *args, item=None, **kwargs):
        self._item = item
        super().__init__(*args, **kwargs)

    def validate_quantity(self, value: int) -> int:
        if self._item is not None:
            max_qty = min(99, self._item.product.stock)
            if value > max_qty:
                raise serializers.ValidationError(
                    f"Zaxirada atigi {max_qty} dona bor."
                )
        return value
