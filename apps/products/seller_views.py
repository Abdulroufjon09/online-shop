# ============================================================
#  Sotuvchi (seller) paneli — faqat O'Z mahsulotlarini boshqaradi
# ============================================================
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.security import validate_image_upload

from .serializers import _prepared_image

from .models import Product, ProductImage
from .serializers import (
    MAX_PRODUCT_IMAGES,
    MIN_PRODUCT_IMAGES,
    ProductSellerSerializer,
)

User = get_user_model()


class IsSellerRole(BasePermission):
    message = "Bu bo'lim faqat sotuvchilar uchun."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated
            and user.is_active and user.has_role(User.Role.SELLER)
        )


class SellerStatsView(APIView):
    """GET /api/seller/stats/ — sotuvchi uchun qisqa statistika."""

    permission_classes = [IsAuthenticated, IsSellerRole]

    def get(self, request):
        mine = Product.objects.filter(seller=request.user)
        return Response(
            {
                "total": mine.count(),
                "active": mine.filter(is_active=True).count(),
                "inactive": mine.filter(is_active=False).count(),
                "stock_total": mine.aggregate(s=models.Sum("stock"))["s"] or 0,
            }
        )


class SellerProductListCreateView(ListCreateAPIView):
    """GET/POST /api/seller/products/ — o'z mahsulotlari."""

    permission_classes = [IsAuthenticated, IsSellerRole]
    serializer_class = ProductSellerSerializer

    def get_queryset(self):
        return Product.objects.filter(seller=self.request.user).select_related("category")

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user)


class SellerProductDetailView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/seller/products/<pk>/ — o'z mahsuloti."""

    permission_classes = [IsAuthenticated, IsSellerRole]
    serializer_class = ProductSellerSerializer

    def get_queryset(self):
        return Product.objects.filter(seller=self.request.user).select_related("category")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Mahsulotni o'chirib bo'lmaydi — u buyurtmalarda ishlatilgan. "
                        "O'rniga is_active=False qilib yashiring."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SellerProductImagesAddView(APIView):
    """POST /api/seller/products/<pk>/images/ — rasm qo'shish (2..5)."""

    permission_classes = [IsAuthenticated, IsSellerRole]

    def _product(self, request, pk: int):
        return Product.objects.filter(pk=pk, seller=request.user).first()

    def post(self, request, pk: int):
        product = self._product(request, pk)
        if product is None:
            return Response({"detail": "Mahsulot topilmadi."}, status=404)
        files = request.FILES.getlist("images")
        if not files:
            return Response(
                {"detail": "Rasm fayllari yuborilmadi ('images' kaliti)."},
                status=400,
            )
        current = product.images.count()
        if current + len(files) > MAX_PRODUCT_IMAGES:
            return Response(
                {"detail": f"Ko'pi bilan {MAX_PRODUCT_IMAGES} ta rasm bo'lishi mumkin (hozir {current})."},
                status=400,
            )
        for upload in files:
            validate_image_upload(upload)
        files = [_prepared_image(u) for u in files]
        start = product.images.aggregate(m=models.Max("position"))["m"]
        start = (start + 1) if start is not None else 0
        for offset, upload in enumerate(files):
            ProductImage.objects.create(product=product, image=upload, position=start + offset)
        if not product.image:
            first = product.images.order_by("position").first()
            product.image = first.image
            product.save(update_fields=["image"])
        return Response(
            {"detail": "Rasmlar qo'shildi.", "product": ProductSellerSerializer(product).data}
        )


class SellerProductImageDeleteView(APIView):
    """DELETE /api/seller/products/<pk>/images/<image_pk>/ — rasmni o'chirish."""

    permission_classes = [IsAuthenticated, IsSellerRole]

    def delete(self, request, pk: int, image_pk: int):
        product = Product.objects.filter(pk=pk, seller=request.user).first()
        if product is None:
            return Response({"detail": "Mahsulot topilmadi."}, status=404)
        image = ProductImage.objects.filter(pk=image_pk, product=product).first()
        if image is None:
            return Response({"detail": "Rasm topilmadi."}, status=404)
        if product.is_active and product.images.count() <= MIN_PRODUCT_IMAGES:
            return Response(
                {"detail": f"Faol mahsulotda kamida {MIN_PRODUCT_IMAGES} ta rasm qolishi shart."},
                status=400,
            )
        image.image.delete(save=False)
        image.delete()
        first = product.images.order_by("position").first()
        product.image = first.image if first else None
        product.save(update_fields=["image"])
        return Response(
            {"detail": "Rasm o'chirildi.", "product": ProductSellerSerializer(product).data}
        )
