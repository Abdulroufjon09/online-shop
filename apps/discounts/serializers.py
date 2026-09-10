# ============================================================
#  Chegirma kupon serializers
# ============================================================
from django.utils import timezone
from rest_framework import serializers

from .models import Coupon


class CouponPublicSerializer(serializers.ModelSerializer):
    """Do'konda ko'rsatiladigan faol kupon (banner uchun)."""

    class Meta:
        model = Coupon
        fields = ["id", "code", "percent", "description", "valid_to"]
        read_only_fields = fields


class CouponBriefSerializer(serializers.ModelSerializer):
    """Savat ichida ko'rsatiladigan kupon."""

    class Meta:
        model = Coupon
        fields = ["code", "percent"]
        read_only_fields = fields


class CouponAdminSerializer(serializers.ModelSerializer):
    """Admin CRUD uchun to'liq serializer."""

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "percent",
            "description",
            "valid_from",
            "valid_to",
            "is_active",
            "max_uses",
            "used_count",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "used_count", "created_by", "created_at"]

    def validate_code(self, value: str) -> str:
        return (value or "").upper().strip()

    def validate(self, attrs):
        # Yangilashda mavjud qiymatlarni ham hisobga olish
        valid_to = attrs.get("valid_to", getattr(self.instance, "valid_to", None))
        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        if valid_to and valid_from and valid_to <= valid_from:
            raise serializers.ValidationError(
                {"valid_to": "Tugash vaqti boshlanish vaqtidan keyin bo'lishi kerak."}
            )
        return attrs


class CouponApplySerializer(serializers.Serializer):
    """Savatga kupon qo'llash."""

    code = serializers.CharField(max_length=50)

    def validate_code(self, value: str) -> str:
        return (value or "").upper().strip()
