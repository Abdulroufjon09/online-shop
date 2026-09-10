from django.urls import path

from .views import (
    CategoryListView,
    FeaturedProductListView,
    MyProductReviewView,
    MyReviewsListView,
    ProductDetailView,
    ProductListView,
    ProductReviewListView,
    WishlistBulkOrderView,
    WishlistDetailView,
    WishlistStatusView,
    WishlistView,
)

urlpatterns = [
    path("", ProductListView.as_view(), name="product-list"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("featured/", FeaturedProductListView.as_view(), name="product-featured"),
    path("my-reviews/", MyReviewsListView.as_view(), name="my-reviews"),
    path("wishlist/", WishlistView.as_view(), name="wishlist"),
    path("wishlist/status/", WishlistStatusView.as_view(), name="wishlist-status"),
    path("wishlist/order/", WishlistBulkOrderView.as_view(), name="wishlist-order"),
    path("wishlist/<int:product_id>/", WishlistDetailView.as_view(), name="wishlist-detail"),
    path("<int:pk>/", ProductDetailView.as_view(), name="product-detail"),
    path("<int:pk>/reviews/", ProductReviewListView.as_view(), name="product-reviews"),
    path("<int:pk>/reviews/mine/", MyProductReviewView.as_view(), name="product-review-mine"),
]
