# ============================================================
#  Katalog (ochiq) viewlari — autentifikatsiya talab qilinmaydi
# ============================================================
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Product, Review, WishlistItem
from apps.core.security import image_absolute_url

from .serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductPublicSerializer,
    ReviewSerializer,
)


def _visible_products():
    """Faqat faol kategoriyadagi faol mahsulotlar."""
    return Product.objects.filter(is_active=True, category__is_active=True).select_related(
        "category"
    )


def _annotate_ratings(qs):
    """O'rtacha yulduz va sharhlar sonini hisoblab qo'shadi."""
    return qs.annotate(
        average_rating=Avg("reviews__rating"),
        reviews_count=Count("reviews"),
    )


class CategoryListView(ListAPIView):
    """GET /api/products/categories/ — faol kategoriyalar."""

    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(is_active=True).order_by("name")
    pagination_class = None


class ProductListView(ListAPIView):
    """
    GET /api/products/?category=1&search=...&ordering=-price&page=2
    Faqat sotuvda bo'lgan mahsulotlar (filter + qidiruv + saralash + pagination).
    """

    permission_classes = [AllowAny]
    serializer_class = ProductPublicSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category"]
    search_fields = ["name", "description", "category__name"]
    ordering_fields = ["price", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = _visible_products()
        # 'aksiya' so'zi bilan qidirilsa — chegirmadagilarni ko'rsatish
        search = self.request.query_params.get("search", "").strip().lower()
        if search in {"aksiya", "chegirma", "sale", "discount"}:
            qs = qs.filter(discount_percent__gt=0)
        return _annotate_ratings(qs)


class FeaturedProductListView(ListAPIView):
    """GET /api/products/featured/ — tavsiya etilgan mahsulotlar (bosh sahifa)."""

    permission_classes = [AllowAny]
    serializer_class = ProductPublicSerializer
    pagination_class = None

    def get_queryset(self):
        return _annotate_ratings(_visible_products().filter(is_featured=True))[:12]


class ProductDetailView(RetrieveAPIView):
    """GET /api/products/<id>/ — mahsulot detali."""

    permission_classes = [AllowAny]
    serializer_class = ProductDetailSerializer
    lookup_field = "pk"

    def get_queryset(self):
        return _annotate_ratings(_visible_products())


# ============================================================
#  Sharhlar (5 yulduzli baho + izoh)
# ============================================================
class ProductReviewListView(ListAPIView):
    """
    GET  /api/products/<pk>/reviews/            — ochiq ro'yxat
    POST /api/products/<pk>/reviews/            — o'z sharhini yozish/yangilash
    """

    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = ReviewSerializer
    pagination_class = None

    def get_product(self):
        return get_object_or_404(_visible_products(), pk=self.kwargs["pk"])

    def get_queryset(self):
        product = self.get_product()
        return Review.objects.filter(product=product).select_related("user")

    def list(self, request, *args, **kwargs):
        product = self.get_product()
        queryset = Review.objects.filter(product=product).select_related("user")
        serializer = ReviewSerializer(
            queryset, many=True, context={"request": request}
        )
        data = {
            "product": product.pk,
            "average_rating": _average_for(product),
            "count": len(serializer.data),
            "results": serializer.data,
        }
        return Response(data)

    def post(self, request, *args, **kwargs):
        product = self.get_product()
        serializer = ReviewSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        rating = serializer.validated_data["rating"]
        comment = (serializer.validated_data.get("comment") or "").strip()
        if not comment and rating is None:
            return Response(
                {"detail": "Baho yoki sharh kiritilishi shart."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        review, created = Review.objects.update_or_create(
            product=product,
            user=request.user,
            defaults={"rating": rating, "comment": comment},
        )
        out = ReviewSerializer(review, context={"request": request}).data
        return Response(out, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class MyReviewsListView(ListAPIView):
    """
    GET /api/products/my-reviews/ — foydalanuvchining barcha sharhlari
    (mahsulot ma'lumoti bilan — profil "Sharhlarim" menyusi uchun).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ReviewSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Review.objects.filter(user=self.request.user)
            .select_related("product", "product__category", "user")
            .order_by("-updated_at")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        data = []
        for review, item in zip(queryset, serializer.data):
            product = review.product
            image = None
            if product.image:
                try:
                    image = image_absolute_url(request, product.image)
                except ValueError:
                    image = None
            data.append(
                {
                    **item,
                    "product": {
                        "id": product.pk,
                        "name": product.name,
                        "slug": product.slug,
                        "image": image,
                    },
                }
            )
        return Response({"count": len(data), "results": data})


class MyProductReviewView(APIView):
    """
    GET    /api/products/<pk>/reviews/mine/  — o'z sharhi (yoki null)
    DELETE /api/products/<pk>/reviews/mine/  — o'z sharhini o'chirish
    """

    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_product(self):
        return get_object_or_404(_visible_products(), pk=self.kwargs["pk"])

    def get(self, request, pk: int):
        product = self.get_product()
        if not request.user.is_authenticated:
            return Response({"review": None})
        review = Review.objects.filter(product=product, user=request.user).first()
        if review is None:
            return Response({"review": None})
        return Response(
            {"review": ReviewSerializer(review, context={"request": request}).data}
        )

    def delete(self, request, pk: int):
        product = self.get_product()
        Review.objects.filter(product=product, user=request.user).delete()
        return Response({"detail": "Sharh o'chirildi."})


def _average_for(product) -> float | None:
    agg = Review.objects.filter(product=product).aggregate(
        average_rating=Avg("rating")
    )
    value = agg["average_rating"]
    return round(float(value), 2) if value is not None else None


# ------------------------------------------------------------
#  Istaklar (wishlist)
# ------------------------------------------------------------
class WishlistView(APIView):
    """
    GET    /api/products/wishlist/          — istaklar ro'yxati
    POST   /api/products/wishlist/ {product_id} — istakka qo'shish (idempotent)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = (
            WishlistItem.objects.filter(user=request.user)
            .select_related("product", "product__category")
            .order_by("-created_at")
        )
        results = []
        for item in items:
            p = item.product
            image = None
            if p.image:
                try:
                    image = image_absolute_url(request, p.image)
                except ValueError:
                    image = None
            results.append(
                {
                    "id": item.pk,
                    "added_at": item.created_at,
                    "product": {
                        "id": p.pk,
                        "name": p.name,
                        "slug": p.slug,
                        "price": p.price,
                        "final_price": p.final_price,
                        "has_discount": p.has_discount,
                        "in_stock": p.in_stock,
                        "stock": p.stock,
                        "image": image,
                    },
                }
            )
        return Response({"count": len(results), "results": results})

    def post(self, request):
        product_id = request.data.get("product_id")
        if not product_id:
            return Response(
                {"detail": "product_id kerak."}, status=status.HTTP_400_BAD_REQUEST
            )
        product = get_object_or_404(_visible_products(), pk=product_id)
        item, created = WishlistItem.objects.get_or_create(
            user=request.user, product=product
        )
        return Response(
            {
                "detail": "Istaklarga qo'shildi." if created else "Allaqachon istaklarda.",
                "created": created,
                "in_wishlist": True,
                "count": WishlistItem.objects.filter(user=request.user).count(),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class WishlistDetailView(APIView):
    """DELETE /api/products/wishlist/<product_id>/ — istakdan olib tashlash."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, product_id: int):
        deleted, _ = WishlistItem.objects.filter(
            user=request.user, product_id=product_id
        ).delete()
        return Response(
            {
                "detail": "Istaklardan olib tashlandi.",
                "deleted": bool(deleted),
                "in_wishlist": False,
                "count": WishlistItem.objects.filter(user=request.user).count(),
            }
        )


class WishlistStatusView(APIView):
    """GET /api/products/wishlist/status/?ids=1,2,3 — qaysi mahsulotlar istakda."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get("ids", "")
        ids = {int(x) for x in raw.split(",") if x.strip().isdigit()}
        if not ids:
            return Response({"ids": []})
        in_wishlist = list(
            WishlistItem.objects.filter(user=request.user, product_id__in=ids)
            .values_list("product_id", flat=True)
        )
        return Response({"ids": in_wishlist})


class WishlistBulkOrderView(APIView):
    """
    POST /api/products/wishlist/order/ {product_ids: [..]}
    Tanlangan istak mahsulotlarini savatga qo'shadi (mavjud bo'lsagina).
    Qaytaradi: qo'shilganlar, stokda yo'q mahsulotlar.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.cart.models import Cart, CartItem
        from apps.cart.serializers import CartSerializer

        ids = request.data.get("product_ids") or []
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "product_ids ro'yxati kerak."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        products = {
            p.pk: p for p in _visible_products().filter(pk__in=ids)
        }
        cart, _ = Cart.objects.get_or_create(user=request.user)
        added, skipped = [], []
        for pid in ids:
            p = products.get(pid)
            if p is None or not p.in_stock:
                skipped.append(pid)
                continue
            item, created = CartItem.objects.get_or_create(
                cart=cart, product=p,
                defaults={"quantity": 1, "price": p.final_price},
            )
            if not created:
                item.quantity = min(item.quantity + 1, max(p.stock, 1))
                item.save(update_fields=["quantity"])
            added.append(pid)
        cart_data = CartSerializer(cart, context={"request": request}).data
        return Response(
            {
                "detail": f"{len(added)} ta mahsulot savatga qo'shildi.",
                "added": added,
                "skipped": skipped,
                "cart": cart_data,
            }
        )
