from django.urls import path

from .admin_views import (
    AdminRoleApplicationDecideView,
    AdminRoleApplicationListView,
    AdminStatsView,
    AdminUserListView,
    AdminUserStatusView,
)

urlpatterns = [
    path("stats/", AdminStatsView.as_view(), name="admin-stats"),
    path("users/", AdminUserListView.as_view(), name="admin-user-list"),
    path("users/<int:pk>/status/", AdminUserStatusView.as_view(), name="admin-user-status"),
    path("applications/", AdminRoleApplicationListView.as_view(), name="admin-applications"),
    path(
        "applications/<int:pk>/decide/",
        AdminRoleApplicationDecideView.as_view(),
        name="admin-application-decide",
    ),
]
