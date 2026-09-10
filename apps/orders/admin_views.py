# ============================================================
#  Admin — buyurtmalarni boshqarish
# ============================================================
from django.db.models import ProtectedError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, PickupPoint
from .serializers import AdminOrderSerializer, AdminPickupPointSerializer


class AdminOrderListView(ListAPIView):
    """GET /api/admin/orders/ — barcha buyurtmalar (filter + qidiruv)."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminOrderSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status"]
    search_fields = [
        "order_number",
        "full_name",
        "phone",
        "user__phone",
        "user__full_name",
    ]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Order.objects.select_related("user").prefetch_related("items").all()
        # ?from=YYYY-MM-DD&to=YYYY-MM-DD — sana oralig'i
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs


class AdminOrderDetailView(RetrieveAPIView):
    """GET /api/admin/orders/<pk>/ — bitta buyurtma to'liq."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminOrderSerializer

    def get_queryset(self):
        return Order.objects.select_related("user").prefetch_related("items").all()


class AdminOrderStatusView(APIView):
    """PATCH /api/admin/orders/<pk>/status/  {status: 'shipped'}"""

    permission_classes = [IsAdminUser]

    def patch(self, request, pk: int):
        order = Order.objects.select_related("user").prefetch_related("items").filter(pk=pk).first()
        if order is None:
            return Response(
                {"detail": "Buyurtma topilmadi."}, status=status.HTTP_404_NOT_FOUND
            )

        new_status = request.data.get("status")
        allowed = {c.value for c in Order.Status}
        if new_status not in allowed:
            return Response(
                {"detail": f"status quyidagilardan biri bo'lishi kerak: {', '.join(sorted(allowed))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.status == Order.Status.CANCELLED:
            return Response(
                {"detail": "Bekor qilingan buyurtma holatini o'zgartirib bo'lmaydi."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if new_status == Order.Status.CANCELLED and order.status not in {
            Order.Status.PENDING,
            Order.Status.PROCESSING,
        }:
            return Response(
                {"detail": "Faqat 'Kutilmoqda' yoki 'Qayta ishlanmoqda' buyurtmani bekor qilish mumkin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = new_status
        order.save(update_fields=["status", "updated_at"])

        # Holat o'zgargani haqida foydalanuvchiga Telegram xabar
        from django.db import transaction

        transaction.on_commit(lambda: self._notify(order.pk))

        return Response(
            {
                "detail": "Buyurtma holati yangilandi.",
                "order": AdminOrderSerializer(order).data,
            }
        )

    def _notify(self, order_pk: int) -> None:
        from apps.telegram_bot.services import notify_order_status_changed

        notify_order_status_changed(order_pk)


class AdminPickupPointListCreateView(ListCreateAPIView):
    """GET/POST /api/admin/points/ — punktlar ro'yxati va yaratish."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminPickupPointSerializer
    pagination_class = None
    queryset = PickupPoint.objects.all()


class AdminPickupPointDetailView(RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/admin/points/<pk>/."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminPickupPointSerializer
    queryset = PickupPoint.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {
                    "detail": "Punktni o'chirib bo'lmaydi — unga bog'langan buyurtmalar bor. O'rniga is_active=False qiling."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
