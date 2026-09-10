# ============================================================
#  Buyurtmalar — foydalanuvchi API
# ============================================================
from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.models import Cart, CartItem
from apps.products.models import Product

from .models import Order, OrderItem, PickupPoint
from .serializers import (
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    PickupPointSerializer,
)

MONEY = Decimal("0.01")


class PickupPointListView(ListAPIView):
    """GET /api/orders/points/ — faol punktlar (yetkazib olish uchun)."""

    permission_classes = [AllowAny]
    serializer_class = PickupPointSerializer
    pagination_class = None
    queryset = PickupPoint.objects.filter(is_active=True)


class OrderCreateView(APIView):
    """
    POST /api/orders/
    Savatdagi mahsulotlardan buyurtma yaratadi:
      - zaxira tekshiriladi va kamaytiriladi (select_for_update — race yo'q)
      - narxlar serverda qayta hisoblanadi (mijozga ishonilmaydi)
      - kupon amalda bo'lsa chegirma qo'llanadi
      - delivery_type: 'delivery' (xarita koordinatalari bilan) yoki 'pickup' (punkt)
      - buyurtma yaratilgach admin + foydalanuvchiga xabar boradi
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        full_name = (data.get("full_name") or user.full_name or "").strip()
        if not full_name:
            raise ValidationError(
                {"full_name": "Qabul qiluvchining ismi kiritilishi shart."}
            )
        phone = data.get("phone") or user.phone

        order = self._build_order(user, full_name, phone, data)
        # Xabarlar faqat muvaffaqiyatli saqlangandan keyin (commit dan so'ng)
        transaction.on_commit(lambda pk=order.pk: self._notify(pk))
        return Response(
            {
                "detail": "Buyurtma qabul qilindi! Tez orada operator siz bilan bog'lanadi.",
                "order": OrderDetailSerializer(order).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def _build_order(self, user, full_name: str, phone: str, data: dict) -> Order:
        with transaction.atomic():
            cart = (
                Cart.objects.select_related("coupon")
                .filter(user=user)
                .first()
            )
            if cart is None or not cart.items.exists():
                raise ValidationError({"detail": "Savatingiz bo'sh. Avval mahsulot qo'shing."})

            cart_items = list(cart.items.select_related("product").all())
            # Zaxira qatorlarini bloklash — parallel buyurtmalar xavfsiz
            locked = {
                p.id: p
                for p in Product.objects.select_for_update().filter(
                    id__in=[ci.product_id for ci in cart_items]
                )
            }

            coupon = cart.coupon
            percent = Decimal("0")
            if coupon is not None:
                if not coupon.is_valid_now:
                    raise ValidationError(
                        {"detail": "Chegirma kodi muddati tugagan. Kodni olib tashlang va qayta urinib ko'ring."}
                    )
                percent = Decimal(coupon.percent)

            order = Order(
                user=user,
                full_name=full_name,
                phone=phone,
                address=data["address"],
                note=data.get("note", ""),
                coupon=coupon,
                coupon_code=coupon.code if coupon else "",
                delivery_type=data["delivery_type"],
                pickup_point=data.get("pickup_point"),
                latitude=data.get("latitude"),
                longitude=data.get("longitude"),
            )
            order.save()  # order_number avtomatik beriladi

            subtotal = Decimal("0")
            for ci in cart_items:
                product = locked[ci.product_id]
                if not product.is_active:
                    raise ValidationError(
                        {"detail": f"'{product.name}' endi sotuvda yo'q. Savatni yangilang."}
                    )
                if product.stock < ci.quantity:
                    raise ValidationError(
                        {
                            "detail": f"'{product.name}' uchun zaxirada yetarli mahsulot yo'q "
                            f"(qolgani: {product.stock})."
                        }
                    )
                product.stock -= ci.quantity
                product.save(update_fields=["stock"])

                unit = product.final_price
                line = (unit * ci.quantity).quantize(MONEY)
                subtotal += unit * ci.quantity
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name,
                    unit_price=unit,
                    discount_percent=product.discount_percent,
                    quantity=ci.quantity,
                    line_total=line,
                )

            discount = (subtotal * percent / Decimal("100")).quantize(MONEY)
            total = (subtotal - discount).quantize(MONEY)
            Order.objects.filter(pk=order.pk).update(
                subtotal=subtotal.quantize(MONEY),
                discount_amount=discount,
                total=total,
            )
            if coupon is not None:
                coupon.increment_use()

            # Savat tozalanadi — buyurtma snapshoti allaqachon saqlangan
            cart.items.all().delete()
            cart.coupon = None
            cart.save(update_fields=["coupon", "updated_at"])

            order.refresh_from_db()
            return order

    def _notify(self, order_pk: int) -> None:
        from apps.telegram_bot.services import notify_new_order

        notify_new_order(order_pk)


class MyOrderListView(ListAPIView):
    """GET /api/orders/mine/ — faqat o'z buyurtmalari."""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderListSerializer

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items__product")
            .order_by("-created_at")
        )


class MyOrderDetailView(RetrieveAPIView):
    """GET /api/orders/<pk>/ — o'z buyurtmasi detali."""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderDetailSerializer

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")


class OrderCancelView(APIView):
    """POST /api/orders/<pk>/cancel/ — kutilayotgan buyurtmani bekor qilish."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        order = Order.objects.filter(pk=pk, user=request.user).first()
        if order is None:
            return Response(
                {"detail": "Buyurtma topilmadi."}, status=status.HTTP_404_NOT_FOUND
            )
        if order.status != Order.Status.PENDING:
            return Response(
                {"detail": "Faqat 'Kutilmoqda' holatidagi buyurtmani bekor qilish mumkin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            items = list(order.items.select_related("product").all())
            product_ids = [i.product_id for i in items]
            locked = {
                p.id: p
                for p in Product.objects.select_for_update().filter(id__in=product_ids)
            }
            for item in items:
                product = locked.get(item.product_id)
                if product is not None:
                    product.stock += item.quantity
                    product.save(update_fields=["stock"])
            Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)

        return Response(
            {
                "detail": "Buyurtma bekor qilindi. Zaxiradagi mahsulotlar qaytarildi.",
                "order": OrderDetailSerializer(order).data,
            }
        )
