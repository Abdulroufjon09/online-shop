from django.urls import path

from .views import telegram_webhook

urlpatterns = [
    path("webhook/<str:secret>/", telegram_webhook, name="telegram-webhook"),
]
