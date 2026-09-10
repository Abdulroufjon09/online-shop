from django.urls import path

from .admin_views import (
    AdminCategoryDetailView,
    AdminCategoryListCreateView,
    AdminProductDetailView,
    AdminProductImageDeleteView,
    AdminProductImagesAddView,
    AdminProductListCreateView,
)

urlpatterns = [
    path("products/", AdminProductListCreateView.as_view(), name="admin-product-list"),
    path(
        "products/<int:pk>/",
        AdminProductDetailView.as_view(),
        name="admin-product-detail",
    ),
    path(
        "products/<int:pk>/images/",
        AdminProductImagesAddView.as_view(),
        name="admin-product-images-add",
    ),
    path(
        "products/<int:pk>/images/<int:image_pk>/",
        AdminProductImageDeleteView.as_view(),
        name="admin-product-image-delete",
    ),
    path("categories/", AdminCategoryListCreateView.as_view(), name="admin-category-list"),
    path(
        "categories/<int:pk>/",
        AdminCategoryDetailView.as_view(),
        name="admin-category-detail",
    ),
]
