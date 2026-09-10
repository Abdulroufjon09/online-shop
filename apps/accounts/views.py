# ============================================================
#  Auth API viewlari
# ============================================================
from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.throttles import (
    BindTelegramThrottle,
    LoginRateThrottle,
    RegisterRateThrottle,
    ResendCodeThrottle,
    VerifyCodeThrottle,
)

from .serializers import (
    BindTelegramSerializer,
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    ResendCodeSerializer,
    UserProfileSerializer,
    VerifySerializer,
)

# Kodni yetkazish yo'li (telegram_bot.services dan)
CHANNEL_TELEGRAM = "telegram"
CHANNEL_VIA_BOT = "via_bot"
CHANNEL_CONSOLE = "console"

REGISTER_NEW_MSG = "Ro'yxatdan o'tish muvaffaqiyatli. Tasdiqlash kodi yuborildi."
REGISTER_RETRY_MSG = "Kod qayta yuborildi. Ro'yxatdan o'tishni yakunlang."


class RegisterView(APIView):
    """POST /api/auth/register/ — telefon + parol, kod yuboriladi."""

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, RegisterRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, created = serializer.create(serializer.validated_data)

        transaction.on_commit(lambda: self._deliver_code(user.pk))

        channel = self._deliver_code(user.pk, dry_run=True)
        data = {
            "phone": user.phone,
            "detail": REGISTER_NEW_MSG if created else REGISTER_RETRY_MSG,
            "channel": channel,
        }
        if settings.DEBUG:
            # Faqat mahalliy ishlab chiqishda — kodni ko'rsatish uchun
            data["dev_code"] = user.verification_code
        return Response(data, status=status.HTTP_201_CREATED)

    def _deliver_code(self, user_pk: int, dry_run: bool = False) -> str:
        from apps.telegram_bot.services import send_registration_code

        return send_registration_code(user_pk, dry_run=dry_run)


class ResendCodeView(APIView):
    """POST /api/auth/resend-code/ — yangi kod so'rash."""

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, ResendCodeThrottle]

    def post(self, request):
        serializer = ResendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.create(serializer.validated_data)

        transaction.on_commit(lambda: self._deliver_code(user.pk))
        channel = self._deliver_code(user.pk, dry_run=True)

        data = {
            "phone": user.phone,
            "detail": "Yangi tasdiqlash kodi yuborildi.",
            "channel": channel,
        }
        if settings.DEBUG:
            data["dev_code"] = user.verification_code
        return Response(data, status=status.HTTP_200_OK)

    def _deliver_code(self, user_pk: int, dry_run: bool = False) -> str:
        from apps.telegram_bot.services import send_registration_code

        return send_registration_code(user_pk, dry_run=dry_run)


class VerifyView(APIView):
    """POST /api/auth/verify/ — kodni tekshirish, JWT tokenlar qaytariladi."""

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, VerifyCodeThrottle]

    def post(self, request):
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.create(serializer.validated_data)

        data = {
            "detail": "Hisob tasdiqlandi. Xush kelibsiz!",
            **result["tokens"],
            "user": UserProfileSerializer(
                result["user"], context={"request": request}
            ).data,
        }
        return Response(data, status=status.HTTP_200_OK)


class LoginView(APIView):
    """POST /api/auth/login/ — telefon + parol -> JWT tokenlar."""

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.create(serializer.validated_data)

        data = {
            "detail": "Tizimga muvaffaqiyatli kirdingiz.",
            **result["tokens"],
            "user": UserProfileSerializer(
                result["user"], context={"request": request}
            ).data,
        }
        return Response(data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """POST /api/auth/logout/ — refresh tokenni qora ro'yxatga olish."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except Exception:  # noqa: BLE001 — token allaqachon bekor qilingan
            pass
        return Response({"detail": "Tizimdan chiqdingiz."}, status=status.HTTP_200_OK)


class MyRoleApplicationsView(APIView):
    """
    GET  /api/auth/applications/  — o'z arizalari ro'yxati
    POST /api/auth/applications/  — yangi ariza (sotuvchi/kuryer/punkt)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import RoleApplication
        from .serializers import RoleApplicationSerializer

        apps = RoleApplication.objects.filter(user=request.user)[:20]
        return Response(RoleApplicationSerializer(apps, many=True).data)

    def post(self, request):
        from .serializers import RoleApplicationCreateSerializer, RoleApplicationSerializer

        serializer = RoleApplicationCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        app = serializer.create(serializer.validated_data)
        data = RoleApplicationSerializer(app).data
        return Response(data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    """GET/PATCH /api/auth/me/ — o'z profilini ko'rish va tahrirlash."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user, context=self.get_serializer_context()).data)

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def get_serializer_context(self):
        return {"request": self.request}


class BindTelegramView(APIView):
    """POST /api/auth/bind-telegram/ — bot /link da olingan kodni tasdiqlash."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [BindTelegramThrottle]

    def post(self, request):
        serializer = BindTelegramSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        ok = serializer.create(serializer.validated_data)
        if not ok:
            return Response(
                {"detail": "Kod noto'g'ri yoki muddati o'tgan."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"detail": "Telegram hisob muvaffaqiyatli bog'landi.", "telegram_linked": True}
        )


class UnbindTelegramView(APIView):
    """DELETE /api/auth/telegram/ — Telegram bog'lanishni olib tashlash."""

    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.telegram_chat_id = None
        user.telegram_linked_at = None
        user.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
        return Response(
            {"detail": "Telegram bog'lanish olib tashlandi.", "telegram_linked": False}
        )
