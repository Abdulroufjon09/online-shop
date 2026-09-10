# ============================================================
#  Kuryer va Punkt panellari API
#
#  Kuryer:  o'ziga tayinlangan / olinadigan buyurtmalar
#           claim -> out_for_delivery -> delivered
#  Punkt:   o'z punktiga yo'naltirilgan buyurtmalarni
#           ready (tayyor) / delivered (berildi) qiladi
# ============================================================
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import AdminOrderSerializer

User = get_user_model()


class IsCourierRole(BasePermission):
    message = "Bu bo'lim faqat kuryerlar uchun."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated
            and user.is_active and user.has_role(User.Role.COURIER)
        )


class IsPickupRole(BasePermission):
    message = "Bu bo'lim faqat punkt xodimlari uchun."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated
            and user.is_active and user.has_role(User.Role.PICKUP)
            and user.pickup_point_id is not None
        )


def _full_queryset():
    return Order.objects.select_related(
        "user", "courier", "pickup_point"
    ).prefetch_related("items")


# ============================================================
#  KURYER
# ============================================================
class CourierOrderListView(ListAPIView):
    """
    GET /api/courier/orders/?scope=my|available
    my         — o'zimga tayinlangan faol buyurtmalar
    available  — olish mumkin bo'lgan yetkazish buyurtmalari (courier=null)
    """

    permission_classes = [IsAuthenticated, IsCourierRole]
    serializer_class = AdminOrderSerializer

    def get_queryset(self):
        user = self.request.user
        scope = self.request.query_params.get("scope", "my")
        active = [
            Order.Status.PENDING,
            Order.Status.PROCESSING,
            Order.Status.READY,
            Order.Status.OUT_FOR_DELIVERY,
        ]
        qs = _full_queryset()
        if scope == "available":
            return qs.filter(
                delivery_type=Order.DeliveryType.DELIVERY,
                courier__isnull=True,
                status__in=[
                    Order.Status.PENDING,
                    Order.Status.PROCESSING,
                    Order.Status.READY,
                ],
            )
        return qs.filter(courier=user, status__in=active)


class CourierOrderHistoryView(ListAPIView):
    """GET /api/courier/orders/history/ — yetkazib berilganlar."""

    permission_classes = [IsAuthenticated, IsCourierRole]
    serializer_class = AdminOrderSerializer
    pagination_class = None

    def get_queryset(self):
        return _full_queryset().filter(
            courier=self.request.user, status=Order.Status.DELIVERED
        ).order_by("-created_at")[:50]


class CourierClaimView(APIView):
    """POST /api/courier/orders/<pk>/claim/ — buyurtmani o'ziga olish."""

    permission_classes = [IsAuthenticated, IsCourierRole]

    # select_for_update faqat tranzaksiya ichida amal qiladi —
    # ikki kuryer bir buyurtmani bir vaqtda ola olmasligi uchun atomic kerak
    @transaction.atomic
    def post(self, request, pk: int):
        order = Order.objects.select_for_update().filter(pk=pk).first()
        if order is None:
            return Response(
                {"detail": "Buyurtma topilmadi."}, status=status.HTTP_404_NOT_FOUND
            )
        if order.delivery_type != Order.DeliveryType.DELIVERY:
            return Response(
                {"detail": "Bu buyurtma yetkazish emas — punktdan olinadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if order.courier_id is not None:
            return Response(
                {
                    "detail": "Bu buyurtma allaqachon boshqa kuryerga tayinlangan.",
                    "claimed_by": order.courier.full_name if order.courier else None,
                },
                status=status.HTTP_409_CONFLICT,
            )
        if order.status not in (
            Order.Status.PENDING,
            Order.Status.PROCESSING,
            Order.Status.READY,
        ):
            return Response(
                {"detail": "Hozircha bu buyurtmani olish mumkin emas."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.courier = request.user
        order.save(update_fields=["courier", "updated_at"])
        return Response(
            {
                "detail": "Buyurtma qabul qilindi. Endi yetkazishni boshlashingiz mumkin.",
                "order": AdminOrderSerializer(order).data,
            }
        )


class CourierOrderStatusView(APIView):
    """
    POST /api/courier/orders/<pk>/status/  {status}
    processing/ready -> out_for_delivery -> delivered
    """

    permission_classes = [IsAuthenticated, IsCourierRole]
    # joriy holat -> ruxsat etilgan keyingi holatlar
    ALLOWED = {
        Order.Status.PENDING: {Order.Status.OUT_FOR_DELIVERY},
        Order.Status.PROCESSING: {Order.Status.OUT_FOR_DELIVERY},
        Order.Status.READY: {Order.Status.OUT_FOR_DELIVERY},
        Order.Status.OUT_FOR_DELIVERY: {Order.Status.DELIVERED},
    }

    @transaction.atomic
    def post(self, request, pk: int):
        order = Order.objects.select_for_update().filter(pk=pk, courier=request.user).first()
        if order is None:
            return Response(
                {"detail": "Sizga tayinlangan buyurtma topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )
        new_status = request.data.get("status")
        if order.status not in self.ALLOWED or new_status not in self.ALLOWED[order.status]:
            return Response(
                {"detail": "Bu holatga o'tkazib bo'lmaydi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        self._notify(order.pk)
        return Response(
            {
                "detail": "Holat yangilandi.",
                "order": AdminOrderSerializer(order).data,
            }
        )

    def _notify(self, order_pk: int) -> None:
        from apps.telegram_bot.services import notify_order_status_changed

        notify_order_status_changed(order_pk)


# ============================================================
#  PUNKT
# ============================================================
class PickupOrderListView(ListAPIView):
    """GET /api/pickup/orders/ — o'z punktidagi faol buyurtmalar."""

    permission_classes = [IsAuthenticated, IsPickupRole]
    serializer_class = AdminOrderSerializer
    pagination_class = None

    def get_queryset(self):
        return _full_queryset().filter(
            pickup_point_id=self.request.user.pickup_point_id,
            delivery_type=Order.DeliveryType.PICKUP,
            status__in=[
                Order.Status.PENDING,
                Order.Status.PROCESSING,
                Order.Status.READY,
                Order.Status.OUT_FOR_DELIVERY,
            ],
        ).order_by("created_at")


class PickupOrderActionView(APIView):
    """
    POST /api/pickup/orders/<pk>/ready/   — buyurtma tayyor
    POST /api/pickup/orders/<pk>/handed/  — xaridorga berildi
    """

    permission_classes = [IsAuthenticated, IsPickupRole]

    def _get_order(self, request, pk: int):
        return Order.objects.filter(
            pk=pk,
            pickup_point_id=request.user.pickup_point_id,
            delivery_type=Order.DeliveryType.PICKUP,
        ).select_for_update().first()

    @transaction.atomic
    def _act(self, request, pk: int, target: str):
        order = self._get_order(request, pk)
        if order is None:
            return Response(
                {"detail": "Punktingizdagi buyurtma topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if target == "ready":
            if order.status not in (Order.Status.PENDING, Order.Status.PROCESSING):
                return Response(
                    {"detail": "Faqat 'Kutilmoqda'/'Qayta ishlanmoqda' buyurtmani tayyor qilish mumkin."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.status = Order.Status.READY
        else:  # handed -> delivered
            if order.status != Order.Status.READY:
                return Response(
                    {"detail": "Buyurtma hali tayyor emas."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.status = Order.Status.DELIVERED

        order.save(update_fields=["status", "updated_at"])
        self._notify(order.pk)
        return Response(
            {
                "detail": "Holat yangilandi.",
                "order": AdminOrderSerializer(order).data,
            }
        )

    def _notify(self, order_pk: int) -> None:
        from apps.telegram_bot.services import notify_order_status_changed

        notify_order_status_changed(order_pk)


class PickupReadyView(PickupOrderActionView):
    def post(self, request, pk: int):
        return self._act(request, pk, "ready")


class PickupHandedView(PickupOrderActionView):
    def post(self, request, pk: int):
        return self._act(request, pk, "handed")
