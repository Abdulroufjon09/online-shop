# ============================================================
#  Chegirma kuponlari — ochiq ro'yxat va savatga qo'llash
# ============================================================
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.serializers import CartSerializer

from .models import Coupon
from .serializers import (
    CouponApplySerializer,
    CouponPublicSerializer,
)


class ActiveCouponListView(ListAPIView):
    """GET /api/discounts/ — hozir amal qilayotgan kuponlar (banner)."""

    permission_classes = [AllowAny]
    serializer_class = CouponPublicSerializer
    pagination_class = None

    def get_queryset(self):
        now = timezone.now()
        return Coupon.objects.filter(
            is_active=True, valid_from__lte=now, valid_to__gte=now
        ).order_by("-percent")


class CouponApplyView(APIView):
    """
    POST /api/discounts/apply/  {code}
    Kuponi o'z savatiga bog'laydi (faqat autentifikatsiyalangan foydalanuvchi).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CouponApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]

        coupon = Coupon.objects.filter(code=code).first()
        if coupon is None:
            return Response(
                {"detail": "Bunday chegirma kodi mavjud emas."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not coupon.is_valid_now:
            msg = "Kupon muddati tugagan yoki faol emas."
            if coupon.is_expired:
                msg = "Kuponning amal qilish muddati tugagan."
            return Response(
                {"detail": msg}, status=status.HTTP_400_BAD_REQUEST
            )

        from apps.cart.models import Cart

        cart, _ = Cart.objects.get_or_create(user=request.user)
        if not cart.items.exists():
            return Response(
                {"detail": "Avval savatga mahsulot qo'shing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart.coupon = coupon
        cart.save(update_fields=["coupon", "updated_at"])

        return Response(
            {
                "detail": f"{coupon.code} kupon qo'llandi — {coupon.percent}% chegirma.",
                "cart": CartSerializer(cart).data,
            }
        )


class CouponRemoveView(APIView):
    """DELETE /api/discounts/remove/ — kuponni savatdan olib tashlash."""

    permission_classes = [IsAuthenticated]

    def delete(self, request):
        from apps.cart.models import Cart

        cart = Cart.objects.filter(user=request.user).first()
        if cart is None or cart.coupon is None:
            return Response(
                {"detail": "Savatingizda chegirma kodi yo'q."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cart.coupon = None
        cart.save(update_fields=["coupon", "updated_at"])
        return Response(
            {
                "detail": "Chegirma kodi olib tashlandi.",
                "cart": CartSerializer(cart).data,
            }
        )
