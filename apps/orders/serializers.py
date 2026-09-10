# ============================================================
#  Buyurtma serializers
# ============================================================
from rest_framework import serializers

from .models import Order, OrderItem, PickupPoint


class OrderProductBriefSerializer(serializers.Serializer):
    """Buyurtmadagi mahsulotga havola (detali uchun)."""

    id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField(read_only=True)
    image = serializers.ImageField(read_only=True)


class OrderItemSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "unit_price",
            "discount_percent",
            "quantity",
            "line_total",
        ]
        read_only_fields = fields

    def get_product(self, obj):
        return {
            "id": obj.product_id,
            "slug": obj.product.slug,
            "image": obj.product.image.url if obj.product.image else None,
        }


class OrderListSerializer(serializers.ModelSerializer):
    """Foydalanuvchi buyurtmalari ro'yxati (engil ko'rinish)."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    delivery_type = serializers.CharField(read_only=True)
    products_count = serializers.SerializerMethodField()
    items_preview = serializers.SerializerMethodField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "status_display",
            "delivery_type",
            "total",
            "products_count",
            "items_preview",
            "created_at",
        ]
        read_only_fields = fields

    def get_products_count(self, obj) -> int:
        return obj.products_count

    def get_items_preview(self, obj) -> list:
        """Ro'yxatda ko'rsatish uchun kichik rasmlar (mahsulot sahifasiga havola bilan)."""
        preview = []
        for item in obj.items.all():
            image = None
            product = item.product
            if product is not None and product.image:
                try:
                    image = product.image.url
                except ValueError:
                    image = None
            preview.append(
                {
                    "product_id": item.product_id,
                    "name": item.product_name,
                    "image": image,
                    "quantity": item.quantity,
                }
            )
        return preview


class PickupPointSerializer(serializers.ModelSerializer):
    """Punkt (ochiq ro'yxat va buyurtma ichida)."""

    class Meta:
        model = PickupPoint
        fields = [
            "id",
            "name",
            "address",
            "phone",
            "latitude",
            "longitude",
        ]
        read_only_fields = fields


class OrderDeliveryInfoSerializer(serializers.Serializer):
    """Yetkazib berish / olish joyi haqida qulay ko'rinish."""

    delivery_type = serializers.CharField(read_only=True)
    delivery_type_display = serializers.CharField(read_only=True)
    pickup_point = PickupPointSerializer(read_only=True)
    address = serializers.CharField(read_only=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, read_only=True, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, read_only=True, allow_null=True
    )

    class Meta:
        fields = "__all__"


class OrderDetailSerializer(serializers.ModelSerializer):
    """Buyurtma detali (egasi ko'radi)."""

    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    delivery_type_display = serializers.CharField(
        source="get_delivery_type_display", read_only=True
    )
    pickup_point = PickupPointSerializer(read_only=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True, allow_null=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "status_display",
            "delivery_type",
            "delivery_type_display",
            "pickup_point",
            "full_name",
            "phone",
            "address",
            "note",
            "latitude",
            "longitude",
            "items",
            "subtotal",
            "discount_amount",
            "coupon_code",
            "total",
            "products_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OrderCreateSerializer(serializers.Serializer):
    """
    Buyurtma yaratish so'rovi (narxlar serverda hisoblanadi).

    delivery_type='delivery'  -> address (va ixtiyoriy lat/lng)
    delivery_type='pickup'    -> pickup_point (punkt id)
    """

    address = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    delivery_type = serializers.ChoiceField(
        choices=Order.DeliveryType.choices, default=Order.DeliveryType.DELIVERY
    )
    pickup_point = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True,
        min_value=-90, max_value=90,
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True,
        min_value=-180, max_value=180,
    )

    def validate(self, attrs):
        delivery_type = attrs.get("delivery_type", Order.DeliveryType.DELIVERY)
        address = (attrs.get("address") or "").strip()
        point = attrs.get("pickup_point")

        if delivery_type == Order.DeliveryType.PICKUP:
            if point is None:
                raise serializers.ValidationError(
                    {"detail": "Punkt tanlanishi shart (punktdan olish uchun)."}
                )
            if not address:
                attrs["address"] = point.address
        else:
            if not address:
                raise serializers.ValidationError(
                    {"detail": "Yetkazib berish manzili kiritilishi shart."}
                )
            attrs["pickup_point"] = None
        attrs["address"] = address

        lat = attrs.get("latitude")
        lng = attrs.get("longitude")
        if (lat is None) != (lng is None):
            raise serializers.ValidationError(
                {"detail": "Kenglik va uzunlik birgalikda kiritilishi kerak."}
            )
        if delivery_type == Order.DeliveryType.PICKUP and point is not None:
            attrs["latitude"] = point.latitude
            attrs["longitude"] = point.longitude
        return attrs

    def validate_phone(self, value: str) -> str:
        if not value:
            return value
        from apps.core.validators import normalize_phone

        return normalize_phone(value)


class AdminOrderSerializer(OrderDetailSerializer):
    """Admin uchun — foydalanuvchi va kuryer ma'lumoti bilan."""

    user = serializers.SerializerMethodField()
    courier = serializers.SerializerMethodField()

    class Meta(OrderDetailSerializer.Meta):
        fields = OrderDetailSerializer.Meta.fields + ["user", "courier"]

    def get_user(self, obj):
        return {
            "id": obj.user_id,
            "phone": obj.user.phone,
            "full_name": obj.user.full_name,
            "is_verified": obj.user.is_verified,
        }

    def get_courier(self, obj):
        if obj.courier_id is None:
            return None
        return {
            "id": obj.courier_id,
            "full_name": obj.courier.full_name,
            "phone": obj.courier.phone,
        }


class AdminPickupPointSerializer(serializers.ModelSerializer):
    """Admin punkt CRUD."""

    orders_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PickupPoint
        fields = [
            "id",
            "name",
            "address",
            "phone",
            "latitude",
            "longitude",
            "is_active",
            "orders_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_orders_count(self, obj) -> int:
        return obj.orders.filter(status__in=[
            Order.Status.PENDING, Order.Status.PROCESSING, Order.Status.READY
        ]).count()
