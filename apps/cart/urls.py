from django.urls import path

from .views import (
    CartAddItemView,
    CartClearView,
    CartDetailView,
    CartItemDetailView,
)

urlpatterns = [
    path("", CartDetailView.as_view(), name="cart-detail"),
    path("add/", CartAddItemView.as_view(), name="cart-add"),
    path("items/<int:pk>/", CartItemDetailView.as_view(), name="cart-item"),
    path("clear/", CartClearView.as_view(), name="cart-clear"),
]
