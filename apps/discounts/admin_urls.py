from django.urls import path

from .admin_views import (
    AdminCouponBroadcastView,
    AdminCouponDetailView,
    AdminCouponListCreateView,
)

urlpatterns = [
    path(
        "discounts/coupons/",
        AdminCouponListCreateView.as_view(),
        name="admin-coupon-list",
    ),
    path(
        "discounts/coupons/<int:pk>/",
        AdminCouponDetailView.as_view(),
        name="admin-coupon-detail",
    ),
    path(
        "discounts/coupons/<int:pk>/broadcast/",
        AdminCouponBroadcastView.as_view(),
        name="admin-coupon-broadcast",
    ),
]
