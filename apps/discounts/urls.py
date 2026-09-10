from django.urls import path

from .views import ActiveCouponListView, CouponApplyView, CouponRemoveView

urlpatterns = [
    path("", ActiveCouponListView.as_view(), name="coupon-list"),
    path("apply/", CouponApplyView.as_view(), name="coupon-apply"),
    path("remove/", CouponRemoveView.as_view(), name="coupon-remove"),
]
