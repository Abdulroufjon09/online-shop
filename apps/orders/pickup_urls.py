from django.urls import path

from .roles_views import (
    PickupHandedView,
    PickupOrderListView,
    PickupReadyView,
)

urlpatterns = [
    path("orders/", PickupOrderListView.as_view(), name="pickup-orders"),
    path("orders/<int:pk>/ready/", PickupReadyView.as_view(), name="pickup-ready"),
    path("orders/<int:pk>/handed/", PickupHandedView.as_view(), name="pickup-handed"),
]
