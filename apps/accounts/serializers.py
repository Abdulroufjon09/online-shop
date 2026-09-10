# ============================================================
#  Auth serializers
# ============================================================
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.validators import normalize_phone

from .models import ROLE_APPLICATION_CHOICES, RoleApplication, User

User = get_user_model()


def issue_token_pair(user) -> dict:
    """Foydalanuvchi uchun JWT access+refresh juftligini yaratadi."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class _PhoneMixin:
    def validate_phone(self, value: str) -> str:
        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


def validate_avatar_upload(upload) -> None:
    """Avatar rasm tekshiruvi (kengaytma, hajm, MIME)."""
    from apps.core.security import validate_image_upload

    try:
        validate_image_upload(upload)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc


class UserProfileSerializer(serializers.ModelSerializer):
    """Ommaviy profil ma'lumotlari (telegram_chat_id hech qachon ko'rsatilmaydi)."""

    telegram_linked = serializers.BooleanField(read_only=True)
    phone_display = serializers.SerializerMethodField()
    role = serializers.CharField(read_only=True)
    role_display = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    pickup_point = serializers.SerializerMethodField()
    avatar = serializers.ImageField(
        required=False,
        allow_null=True,
        allow_empty_file=True,
        use_url=True,
        validators=[validate_avatar_upload],
    )

    def validate_avatar(self, value):
        """Bo'sh satr (yoki null) — avatarni o'chirish talqini."""
        if value in (None, "", b""):
            return None
        return value

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "phone_display",
            "full_name",
            "address",
            "is_verified",
            "is_staff",
            "role",
            "role_display",
            "roles",
            "pickup_point",
            "avatar",
            "telegram_linked",
            "date_joined",
        ]
        read_only_fields = ["id", "phone", "is_verified", "is_staff", "role", "date_joined"]

    def get_phone_display(self, obj) -> str:
        from apps.core.validators import mask_phone

        return mask_phone(obj.phone)

    def get_roles(self, obj) -> list:
        """Barcha rollar: asosiy + qo'shimchalar (customer implicit)."""
        all_roles = {obj.role}
        all_roles.update(obj.roles or [])
        if obj.is_staff or obj.role == obj.Role.ADMIN:
            all_roles.add("admin")
        return sorted(all_roles)

    def get_role_display(self, obj) -> str:
        return obj.get_role_display()

    def get_pickup_point(self, obj):
        if obj.pickup_point_id is None:
            return None
        return {"id": obj.pickup_point_id, "name": obj.pickup_point.name}


class RegisterSerializer(_PhoneMixin, serializers.Serializer):
    """
    Ro'yxatdan o'tish: telefon + parol.
    Foydalanuvchi NOFAOL yaratiladi; kod tasdiqlangach faollashadi.
    """

    phone = serializers.CharField(max_length=20)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)

    def validate_password(self, value: str) -> str:
        from django.contrib.auth.password_validation import validate_password

        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def validate(self, attrs):
        phone = attrs["phone"]
        existing = User.objects.filter(phone=phone).first()
        if existing and existing.is_verified and existing.is_active:
            raise serializers.ValidationError(
                {"phone": "Bu telefon raqam allaqachon ro'yxatdan o'tgan. Tizimga kiring."}
            )
        return attrs

    def create(self, validated_data) -> tuple:
        """
        Yangi (yoki tasdiqlanmagan qayta) foydalanuvchi yaratadi.
        Qaytaradi: (user, yangimi)
        """
        phone = validated_data["phone"]
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={
                "is_active": False,
                "is_verified": False,
            },
        )
        user.full_name = validated_data.get("full_name", "") or user.full_name
        user.set_password(validated_data["password"])
        user.is_active = False
        user.is_verified = False
        user.regenerate_verification_code()
        user.save()
        return user, created


class VerifySerializer(_PhoneMixin, serializers.Serializer):
    """
    Ro'yxatdan o'tish kodini tekshirish.
    Muvaffaqiyatda foydalanuvchi faollashadi va JWT tokenlar qaytariladi.
    """

    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(min_length=6, max_length=6)

    def validate(self, attrs):
        user = User.objects.filter(phone=attrs["phone"]).first()
        if user is None or user.is_verified:
            raise serializers.ValidationError(
                {"detail": "Tasdiqlanadigan ro'yxatdan o'tish topilmadi."}
            )
        if not user.check_verification_code(attrs["code"]):
            if user.code_attempts >= settings.MAX_VERIFY_ATTEMPTS:
                raise serializers.ValidationError(
                    {"detail": "Juda ko'p urinish. Iltimos, yangi kod so'rang."}
                )
            raise serializers.ValidationError(
                {"detail": "Kod noto'g'ri yoki muddati o'tgan."}
            )
        attrs["user"] = user
        return attrs

    def create(self, validated_data) -> dict:
        user = validated_data["user"]
        user.mark_verified()
        return {"tokens": issue_token_pair(user), "user": user}


class ResendCodeSerializer(_PhoneMixin, serializers.Serializer):
    """Yangi tasdiqlash kodi yuborish."""

    phone = serializers.CharField(max_length=20)

    def validate(self, attrs):
        user = User.objects.filter(phone=attrs["phone"]).first()
        if user is None or user.is_verified:
            raise serializers.ValidationError(
                {"detail": "Bu raqam uchun tasdiqlanmagan ro'yxatdan o'tish topilmadi."}
            )
        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        user = validated_data["user"]
        user.regenerate_verification_code()
        user.save()
        return user


class LoginSerializer(_PhoneMixin, serializers.Serializer):
    """Telefon + parol bilan kirish."""

    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        user = User.objects.filter(phone=attrs["phone"]).first()

        # Xuddi shu xato — foydalanuvchi mavjudligini bilinmasin (enumeration)
        generic = "Telefon raqam yoki parol noto'g'ri."

        if user is None or not user.check_password(attrs["password"]):
            raise serializers.ValidationError({"detail": generic})

        if not user.is_verified or not user.is_active:
            raise serializers.ValidationError(
                {"detail": "Hisob tasdiqlanmagan. Ro'yxatdan o'tishni yakunlang."}
            )
        attrs["user"] = user
        return attrs

    def create(self, validated_data) -> dict:
        user = validated_data["user"]
        return {"tokens": issue_token_pair(user), "user": user}


class LogoutSerializer(serializers.Serializer):
    """Refresh tokenni qora ro'yxatga olish (chiqish)."""

    refresh = serializers.CharField()

    def validate_refresh(self, value: str) -> str:
        try:
            RefreshToken(value)
        except Exception as exc:  # noqa: BLE001
            raise serializers.ValidationError("Refresh token yaroqsiz.") from exc
        return value


class BindTelegramSerializer(serializers.Serializer):
    """
    Bot /link orqali boshlangan chat bog'lashni yakunlash.
    Foydalanuvchi profil sahifasida botga yuborilgan kodni kiritadi.
    """

    code = serializers.CharField(min_length=6, max_length=6)

    def validate_code(self, value: str) -> str:
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            raise serializers.ValidationError("Avval tizimga kiring.")
        if request.user.pending_chat_id is None or request.user.bind_code_expired:
            raise serializers.ValidationError(
                "Faol bog'lash so'rovi topilmadi. Botda /link buyrug'ini yuboring."
            )
        return value

    def create(self, validated_data) -> bool:
        return self.context["request"].user.confirm_telegram_bind(validated_data["code"])


class AdminUserSerializer(serializers.ModelSerializer):
    """Admin panel uchun foydalanuvchi ro'yxati (rol bilan)."""

    telegram_linked = serializers.BooleanField(read_only=True)
    role_display = serializers.SerializerMethodField(read_only=True)
    pickup_point = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "full_name",
            "role",
            "role_display",
            "pickup_point",
            "is_verified",
            "is_active",
            "is_staff",
            "telegram_linked",
            "date_joined",
        ]
        read_only_fields = fields

    def get_role_display(self, obj) -> str:
        return obj.get_role_display()

    def get_pickup_point(self, obj):
        if obj.pickup_point_id is None:
            return None
        return {"id": obj.pickup_point_id, "name": obj.pickup_point.name}


# ------------------------------------------------------------
#  Rol arizalari (sotuvchi / kuryer / punkt ochish)
# ------------------------------------------------------------
class RoleApplicationCreateSerializer(serializers.Serializer):
    """
    POST /api/auth/applications/ — yangi ariza.

    Karta raqami faqat tekshiriladi va MASKALANIB saqlanadi
    (to'liq raqam bazaga yozilmaydi).
    """

    role = serializers.ChoiceField(choices=ROLE_APPLICATION_CHOICES)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    address = serializers.CharField(max_length=2000)
    address_latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True,
        min_value=-90, max_value=90,
    )
    address_longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True,
        min_value=-180, max_value=180,
    )
    passport = serializers.CharField(max_length=30, required=False, allow_blank=True)
    card_number = serializers.CharField(max_length=24, write_only=True)

    # Punkt ochish so'rovi
    point_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    point_address = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    point_latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True,
        min_value=-90, max_value=90,
    )
    point_longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True,
        min_value=-180, max_value=180,
    )

    def _request(self):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            raise serializers.ValidationError("Avval tizimga kiring.")
        return request

    def validate_role(self, value: str) -> str:
        user = self._request().user
        if not user.is_verified or not user.is_active:
            raise serializers.ValidationError(
                "Ariza berish uchun hisob tasdiqlangan bo'lishi kerak."
            )
        allowed = set(User.APPLICABLE_ROLES)
        if value not in allowed:
            raise serializers.ValidationError("Bu rol uchun ariza berib bo'lmaydi.")
        # Ko'p rol: asosiy rol yoki qo'shimcha rollarda bo'lsa ham ariza berilmaydi
        if user.has_role(value) and value != "customer":
            raise serializers.ValidationError("Siz allaqachon shu rolga egasiz.")
        return value

    def validate(self, attrs):
        from apps.accounts.models import RoleApplication

        request = self._request()
        user = request.user
        role = attrs["role"]

        # Bitta rol uchun faqat bitta kutilayotgan ariza
        has_pending = RoleApplication.objects.filter(
            user=user, role=role, status=RoleApplication.Status.PENDING
        ).exists()
        if has_pending:
            raise serializers.ValidationError(
                {"detail": "Bu rol uchun arizangiz allaqachon ko'rib chiqilmoqda."}
            )

        # Telefon normalizatsiya
        try:
            attrs["phone"] = normalize_phone(attrs["phone"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"phone": exc.messages}) from exc

        # Karta raqami — Luhn tekshiruvi
        try:
            from apps.accounts.services import mask_card_number, validate_card_number

            digits = validate_card_number(attrs["card_number"])
        except ValueError as exc:
            raise serializers.ValidationError({"card_number": str(exc)}) from exc
        attrs["_card_masked"] = mask_card_number(digits)
        attrs["_card_last4"] = digits[-4:]

        # Manzil koordinatalari juft bo'lishi shart
        a_lat = attrs.get("address_latitude")
        a_lng = attrs.get("address_longitude")
        if (a_lat is None) != (a_lng is None):
            raise serializers.ValidationError(
                {"address_longitude": "Kenglik va uzunlik birgalikda kiritilishi kerak."}
            )

        # Punkt ochish uchun joy majburiy
        if role == User.Role.PICKUP:
            if not (attrs.get("point_name") or "").strip():
                raise serializers.ValidationError(
                    {"point_name": "Punkt nomini kiriting."}
                )
            if not (attrs.get("point_address") or "").strip():
                raise serializers.ValidationError(
                    {"point_address": "Punkt ochiladigan joy manzilini kiriting."}
                )
        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        from apps.accounts.models import RoleApplication

        app = RoleApplication.objects.create(
            user=validated_data["user"],
            role=validated_data["role"],
            full_name=validated_data["full_name"].strip(),
            phone=validated_data["phone"],
            address=validated_data["address"].strip(),
            address_latitude=validated_data.get("address_latitude"),
            address_longitude=validated_data.get("address_longitude"),
            passport=(validated_data.get("passport") or "").strip(),
            card_number_masked=validated_data["_card_masked"],
            card_last4=validated_data["_card_last4"],
            point_name=(validated_data.get("point_name") or "").strip(),
            point_address=(validated_data.get("point_address") or "").strip(),
            point_latitude=validated_data.get("point_latitude"),
            point_longitude=validated_data.get("point_longitude"),
        )
        # Adminlarga Telegram xabar (inline tugmalar bilan)
        try:
            from apps.accounts.services import notify_new_role_application

            notify_new_role_application(app.pk)
        except Exception:  # noqa: BLE001 — xabar muhim emas, ariza saqlandi
            pass
        return app


class RoleApplicationSerializer(serializers.ModelSerializer):
    """Ariza ko'rinishi (egasi va admin uchun)."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    user = serializers.SerializerMethodField(read_only=True)
    reviewer_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RoleApplication
        fields = [
            "id",
            "role",
            "role_display",
            "status",
            "status_display",
            "full_name",
            "phone",
            "address",
            "address_latitude",
            "address_longitude",
            "passport",
            "card_number_masked",
            "point_name",
            "point_address",
            "point_latitude",
            "point_longitude",
            "note",
            "user",
            "reviewer_name",
            "created_at",
            "decided_at",
        ]
        read_only_fields = fields

    def get_user(self, obj):
        return {
            "id": obj.user_id,
            "full_name": obj.user.full_name,
            "phone": obj.user.phone,
        }

    def get_reviewer_name(self, obj):
        if obj.reviewer_id is None:
            return None
        return obj.reviewer.full_name or obj.reviewer.phone

