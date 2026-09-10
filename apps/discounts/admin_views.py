# ============================================================
#  Admin — chegirma kuponlari CRUD + Telegram broadcast
# ============================================================
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Coupon
from .serializers import CouponAdminSerializer


class AdminCouponListCreateView(ListCreateAPIView):
    """GET/POST /api/admin/discounts/coupons/."""

    permission_classes = [IsAdminUser]
    serializer_class = CouponAdminSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["code", "description"]
    ordering = ["-created_at"]
    queryset = Coupon.objects.select_related("created_by").all()

    def perform_create(self, serializer):
        coupon = serializer.save(created_by=self.request.user)
        # Faol kupon yaratilganda — barcha bog'langan foydalanuvchilarga xabar
        if coupon.is_active and coupon.is_valid_now:
            transaction.on_commit(
                lambda: self._broadcast(coupon.pk)
            )

    def _broadcast(self, coupon_pk: int) -> None:
        from apps.telegram_bot.services import broadcast_discount_coupon

        broadcast_discount_coupon(coupon_pk)


class AdminCouponDetailView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/admin/discounts/coupons/<pk>/."""

    permission_classes = [IsAdminUser]
    serializer_class = CouponAdminSerializer
    queryset = Coupon.objects.select_related("created_by").all()

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        coupon = serializer.save()
        # Yangi faollashtirilgan / tahrirlangan faol kupon uchun ham xabar
        if not was_active and coupon.is_active and coupon.is_valid_now:
            transaction.on_commit(
                lambda: self._broadcast(coupon.pk)
            )

    def _broadcast(self, coupon_pk: int) -> None:
        from apps.telegram_bot.services import broadcast_discount_coupon

        broadcast_discount_coupon(coupon_pk)


class AdminCouponBroadcastView(APIView):
    """POST /api/admin/discounts/coupons/<pk>/broadcast/ — qo'lda qayta yuborish."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        coupon = Coupon.objects.filter(pk=pk).first()
        if coupon is None:
            return Response({"detail": "Kupon topilmadi."}, status=404)
        from apps.telegram_bot.services import broadcast_discount_coupon

        count = broadcast_discount_coupon(coupon.pk)
        return Response(
            {"detail": f"Xabar {count} ta foydalanuvchiga yuborish uchun navbatga qo'shildi."}
        )
