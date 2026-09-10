# ============================================================
#  Savat API viewlari — faqat o'z savatiga kirish mumkin
# ============================================================
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cart, CartItem
from .serializers import (
    CartAddItemSerializer,
    CartSerializer,
    CartUpdateItemSerializer,
)


def get_user_cart(user) -> Cart:
    """Foydalanuvchining savatini oladi (yo'q bo'lsa yaratadi)."""
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def _own_cart_item(user, item_pk: int):
    """Foydalanuvchining o'z savatidagi bandni qidiradi."""
    return (
        CartItem.objects.select_related("product")
        .filter(cart__user=user, pk=item_pk)
        .first()
    )


class CartDetailView(APIView):
    """GET /api/cart/ — savatning to'liq holati (narxlar serverda)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = get_user_cart(request.user)
        return Response(CartSerializer(cart).data)


class CartAddItemView(APIView):
    """
    POST /api/cart/add/  {product: <id>, quantity: 2}
    Mahsulotni savatga qo'shadi (allaqachon bor bo'lsa sonini oshiradi).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CartAddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]

        cart = get_user_cart(request.user)
        item = CartItem.objects.select_for_update().filter(
            cart=cart, product=product
        ).first()

        max_qty = min(99, product.stock)
        new_qty = quantity if item is None else item.quantity + quantity
        if new_qty > max_qty:
            return Response(
                {"detail": f"Zaxirada atigi {max_qty} dona bor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if item is None:
            CartItem.objects.create(
                cart=cart, product=product, quantity=quantity, price=product.final_price
            )
        else:
            item.quantity = new_qty
            item.save(update_fields=["quantity"])

        return Response(
            {
                "detail": "Mahsulot savatga qo'shildi.",
                "cart": CartSerializer(cart).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CartItemDetailView(APIView):
    """PATCH/DELETE /api/cart/items/<pk>/ — sonni o'zgartirish yoki o'chirish."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int):
        item = _own_cart_item(request.user, pk)
        if item is None:
            return Response(
                {"detail": "Savat bandi topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CartUpdateItemSerializer(
            data=request.data, item=item
        )
        serializer.is_valid(raise_exception=True)
        item.quantity = serializer.validated_data["quantity"]
        item.save(update_fields=["quantity"])
        return Response(CartSerializer(item.cart).data)

    def delete(self, request, pk: int):
        item = _own_cart_item(request.user, pk)
        if item is None:
            return Response(
                {"detail": "Savat bandi topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )
        cart = item.cart
        item.delete()
        return Response(
            {"detail": "Mahsulot savatdan olib tashlandi.", "cart": CartSerializer(cart).data}
        )


class CartClearView(APIView):
    """DELETE /api/cart/ — savatni tozalash."""

    permission_classes = [IsAuthenticated]

    def delete(self, request):
        cart = Cart.objects.filter(user=request.user).first()
        if cart is not None:
            cart.items.all().delete()
            cart.coupon = None
            cart.save(update_fields=["coupon", "updated_at"])
        return Response(
            {"detail": "Savat tozalandi.", "cart": CartSerializer(get_user_cart(request.user)).data}
        )
