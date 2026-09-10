# ============================================================
#  Admin (is_staff) — foydalanuvchilar boshqaruvi
# ============================================================
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.generics import ListAPIView, UpdateAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.products.models import Product
from apps.discounts.models import Coupon

from .serializers import AdminUserSerializer

User = get_user_model()


class AdminStatsView(APIView):
    """GET /api/admin/stats/ — admin panel uchun umumiy statistika."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(
            {
                "users": User.objects.count(),
                "verified_users": User.objects.filter(is_verified=True).count(),
                "products": Product.objects.count(),
                "active_products": Product.objects.filter(is_active=True).count(),
                "categories": Product.objects.values("category_id").distinct().count(),
                "orders": Order.objects.count(),
                "pending_orders": Order.objects.filter(status=Order.Status.PENDING).count(),
                "coupons": Coupon.objects.filter(is_active=True).count(),
            }
        )


class AdminUserListView(ListAPIView):
    """GET /api/admin/users/ — barcha foydalanuvchilar (filtr + qidiruv)."""

    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer
    queryset = User.objects.all()
    filterset_fields = ["is_verified", "is_active", "is_staff"]
    search_fields = ["phone", "full_name"]
    ordering = ["-date_joined"]
    pagination_class = None


class AdminUserStatusView(UpdateAPIView):
    """
    PATCH /api/admin/users/{id}/status/ — hisobni boshqarish.
    {is_active, role, pickup_point} qabul qiladi (rol berish uchun).
    """

    permission_classes = [IsAdminUser]
    queryset = User.objects.select_related("pickup_point").all()

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        update_fields = []

        if "is_active" in request.data:
            is_active = request.data.get("is_active")
            if not isinstance(is_active, bool):
                return Response(
                    {"detail": "is_active maydoni boolean bo'lishi kerak."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user == request.user and not is_active:
                return Response(
                    {"detail": "O'z hisobingizni o'chira olmaysiz."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.is_active = is_active
            update_fields.append("is_active")

        if "role" in request.data:
            role = request.data.get("role")
            allowed = {c.value for c in User.Role}
            if role not in allowed:
                return Response(
                    {"detail": f"role quyidagilardan biri bo'lishi kerak: {', '.join(sorted(allowed))}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user == request.user and role != User.Role.ADMIN:
                return Response(
                    {"detail": "O'z rolingizni o'zgartira olmaysiz."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.role = role
            update_fields.append("role")
            # Ko'p rol modeli: asosiy roldan olib tashlanganda qo'shimcha
            # rollardan ham tozalaymiz (admin to'liq nazoratda).
            user.roles = []
            update_fields.append("roles")
            if role != User.Role.PICKUP:
                user.pickup_point = None
                update_fields.append("pickup_point")

        if "pickup_point" in request.data:
            if user.role != User.Role.PICKUP:
                return Response(
                    {"detail": "Avval rol'ni 'pickup' qilib belgilang."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            value = request.data.get("pickup_point")
            if value in (None, "", 0):
                user.pickup_point = None
            else:
                from apps.orders.models import PickupPoint

                point = PickupPoint.objects.filter(pk=value, is_active=True).first()
                if point is None:
                    return Response(
                        {"detail": "Punkt topilmadi."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                user.pickup_point = point
            update_fields.append("pickup_point")

        if update_fields:
            user.save(update_fields=update_fields)
        from .serializers import AdminUserSerializer

        return Response(AdminUserSerializer(user).data)


class AdminRoleApplicationListView(APIView):
    """GET /api/admin/applications/?status=pending — barcha rol arizalari."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        from .models import RoleApplication
        from .serializers import RoleApplicationSerializer

        qs = RoleApplication.objects.select_related("user", "reviewer").all()
        status_filter = request.query_params.get("status", "").strip()
        if status_filter in RoleApplication.Status.values:
            qs = qs.filter(status=status_filter)
        role_filter = request.query_params.get("role", "").strip()
        if role_filter:
            qs = qs.filter(role=role_filter)
        qs = qs[:100]
        return Response(RoleApplicationSerializer(qs, many=True).data)


class AdminRoleApplicationDecideView(APIView):
    """
    POST /api/admin/applications/<pk>/decide/
    {status: 'approved'|'rejected'|'pending', note?}
    Qabul qilinsa rol beriladi (kuryer/sotuvchi) yoki punkt ochiladi.
    """

    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        from .models import RoleApplication
        from .serializers import RoleApplicationSerializer
        from .services import notify_role_application_result, review_role_application

        new_status = request.data.get("status", "").strip()
        if new_status not in RoleApplication.Status.values:
            return Response(
                {"detail": f"status quyidagilardan biri bo'lishi kerak: {', '.join(RoleApplication.Status.values)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        note = (request.data.get("note") or "").strip()
        try:
            app = review_role_application(
                pk, new_status, reviewer=request.user, note=note
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Qaror qabul qilindi — arizachiga Telegram xabar
        if app.status in (RoleApplication.Status.APPROVED, RoleApplication.Status.REJECTED):
            notify_role_application_result(app.pk)

        return Response(RoleApplicationSerializer(app).data)
