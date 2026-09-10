from django.urls import path

from .views import (
    MyOrderDetailView,
    MyOrderListView,
    OrderCancelView,
    OrderCreateView,
    PickupPointListView,
)

urlpatterns = [
    path("points/", PickupPointListView.as_view(), name="pickup-point-list"),
    path("", OrderCreateView.as_view(), name="order-create"),
    path("mine/", MyOrderListView.as_view(), name="order-list"),
    path("<int:pk>/", MyOrderDetailView.as_view(), name="order-detail"),
    path("<int:pk>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
]
