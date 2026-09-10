from django.urls import path

from .roles_views import (
    CourierClaimView,
    CourierOrderHistoryView,
    CourierOrderListView,
    CourierOrderStatusView,
)

urlpatterns = [
    path("orders/", CourierOrderListView.as_view(), name="courier-orders"),
    path("orders/history/", CourierOrderHistoryView.as_view(), name="courier-history"),
    path("orders/<int:pk>/claim/", CourierClaimView.as_view(), name="courier-claim"),
    path("orders/<int:pk>/status/", CourierOrderStatusView.as_view(), name="courier-status"),
]
