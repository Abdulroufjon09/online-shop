from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    BindTelegramView,
    LoginView,
    LogoutView,
    MeView,
    MyRoleApplicationsView,
    RegisterView,
    ResendCodeView,
    UnbindTelegramView,
    VerifyView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify/", VerifyView.as_view(), name="verify"),
    path("resend-code/", ResendCodeView.as_view(), name="resend-code"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("bind-telegram/", BindTelegramView.as_view(), name="bind-telegram"),
    path("telegram/", UnbindTelegramView.as_view(), name="unbind-telegram"),
    path("applications/", MyRoleApplicationsView.as_view(), name="my-applications"),
]
