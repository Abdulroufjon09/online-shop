from django.urls import path

from .seller_views import (
    SellerProductDetailView,
    SellerProductImageDeleteView,
    SellerProductImagesAddView,
    SellerProductListCreateView,
    SellerStatsView,
)

urlpatterns = [
    path("stats/", SellerStatsView.as_view(), name="seller-stats"),
    path("products/", SellerProductListCreateView.as_view(), name="seller-product-list"),
    path(
        "products/<int:pk>/",
        SellerProductDetailView.as_view(),
        name="seller-product-detail",
    ),
    path(
        "products/<int:pk>/images/",
        SellerProductImagesAddView.as_view(),
        name="seller-product-images-add",
    ),
    path(
        "products/<int:pk>/images/<int:image_pk>/",
        SellerProductImageDeleteView.as_view(),
        name="seller-product-image-delete",
    ),
]
