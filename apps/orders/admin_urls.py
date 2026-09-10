from django.urls import path

from .admin_views import (
    AdminOrderDetailView,
    AdminOrderListView,
    AdminOrderStatusView,
    AdminPickupPointDetailView,
    AdminPickupPointListCreateView,
)

urlpatterns = [
    path("orders/", AdminOrderListView.as_view(), name="admin-order-list"),
    path("orders/<int:pk>/", AdminOrderDetailView.as_view(), name="admin-order-detail"),
    path(
        "orders/<int:pk>/status/",
        AdminOrderStatusView.as_view(),
        name="admin-order-status",
    ),
    path("points/", AdminPickupPointListCreateView.as_view(), name="admin-point-list"),
    path(
        "points/<int:pk>/",
        AdminPickupPointDetailView.as_view(),
        name="admin-point-detail",
    ),
]
