# ============================================================
#  Admin (is_staff) — mahsulot va kategoriya CRUD
# ============================================================
from django.db.models import ProtectedError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.security import validate_image_upload

from .models import Category, Product, ProductImage
from .serializers import CategorySerializer, ProductAdminSerializer, MAX_PRODUCT_IMAGES, MIN_PRODUCT_IMAGES


class AdminProductListCreateView(ListCreateAPIView):
    """GET/POST /api/admin/products/ — ro'yxat va yangi mahsulot."""

    permission_classes = [IsAdminUser]
    serializer_class = ProductAdminSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "is_active", "is_featured"]
    search_fields = ["name", "slug"]
    ordering_fields = ["price", "created_at", "stock"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Product.objects.select_related("category").all()


class AdminProductDetailView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/admin/products/<pk>/."""

    permission_classes = [IsAdminUser]
    serializer_class = ProductAdminSerializer
    queryset = Product.objects.select_related("category").all()

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


class AdminProductImagesAddView(APIView):
    """POST /api/admin/products/<pk>/images/ — mavjud mahsulotga rasm qo'shish."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        product = Product.objects.filter(pk=pk).first()
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
        start = product.images.aggregate(m=models.Max("position"))["m"]
        start = (start + 1) if start is not None else 0
        for offset, upload in enumerate(files):
            ProductImage.objects.create(product=product, image=upload, position=start + offset)
        if not product.image:
            first = product.images.order_by("position").first()
            product.image = first.image
            product.save(update_fields=["image"])
        return Response({"detail": "Rasmlar qo'shildi.", "product": ProductAdminSerializer(product).data})


class AdminProductImageDeleteView(APIView):
    """DELETE /api/admin/products/<pk>/images/<image_pk>/ — rasmni o'chirish."""

    permission_classes = [IsAdminUser]

    def delete(self, request, pk: int, image_pk: int):
        product = Product.objects.filter(pk=pk).first()
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
        return Response({"detail": "Rasm o'chirildi.", "product": ProductAdminSerializer(product).data})


class AdminCategoryListCreateView(ListCreateAPIView):
    """GET/POST /api/admin/categories/."""

    permission_classes = [IsAdminUser]
    serializer_class = CategorySerializer
    pagination_class = None
    queryset = Category.objects.all().order_by("name")


class AdminCategoryDetailView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/admin/categories/<pk>/."""

    permission_classes = [IsAdminUser]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Kategoriyani o'chirib bo'lmaydi — ichida mahsulotlar bor. "
                        "Avval mahsulotlarni boshqa kategoriyaga o'tkazing."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
