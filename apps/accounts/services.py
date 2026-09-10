# ============================================================
#  Rol arizalari — biznes mantiq (admin REST va Telegram bot
#  inline tugmalari umumiy shu yerdan ishlatadi)
# ============================================================
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("apps.accounts")


# ------------------------------------------------------------
#  Karta raqami — Luhn tekshiruvi + maskalash
#  To'liq raqam hech qayerda saqlanmaydi (faqat tekshiriladi).
# ------------------------------------------------------------
def validate_card_number(raw: str) -> str:
    """Karta raqamini tekshiradi (Luhn). Qaytaradi: toza 16 xonali raqam."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) != 16:
        raise ValueError("Karta raqami 16 xonali bo'lishi kerak.")
    # Luhn algoritmi
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = int(ch)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    if total % 10 != 0:
        raise ValueError("Karta raqami yaroqsiz (tekshiruvdan o'tmadi).")
    return digits


def mask_card_number(raw: str) -> str:
    """Toza raqamdan maskalangan ko'rinish yasaydi: '•••• •••• •••• 1234'."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) < 4:
        return digits
    return "**** **** **** " + digits[-4:]


# ------------------------------------------------------------
#  Ariza ko'rib chiqish
# ------------------------------------------------------------
def review_role_application(
    application_pk: int,
    new_status: str,
    reviewer=None,
    note: str = "",
) -> "RoleApplication":
    """
    Arizani qabul qilish / kutish / rad etish.

    Qabul qilinganda rol beriladi:
      - courier -> foydalanuvchi rol = courier
      - seller  -> foydalanuvchi rol = seller
      - pickup  -> yangi PickupPoint ochiladi va foydalanuvchi
                   shu punkt xodimi qilib biriktiriladi
    """
    from .models import RoleApplication

    with transaction.atomic():
        app = (
            RoleApplication.objects.select_for_update()
            .select_related("user")
            .filter(pk=application_pk)
            .first()
        )
        if app is None:
            raise ValueError("Ariza topilmadi.")
        if app.status != RoleApplication.Status.PENDING:
            raise ValueError("Bu ariza allaqachon ko'rib chiqilgan.")

        if new_status == RoleApplication.Status.PENDING:
            # "Kutish" — holat o'zgarmaydi, faqat izoh qo'shiladi
            if note:
                app.note = note
                app.save(update_fields=["note", "updated_at"])
            return app

        app.status = new_status
        app.note = note or app.note
        app.reviewer = reviewer
        app.decided_at = timezone.now()
        app.save(
            update_fields=["status", "note", "reviewer", "decided_at", "updated_at"]
        )

        if new_status == RoleApplication.Status.APPROVED:
            _apply_approved(app)
    return app


def _apply_approved(app) -> None:
    """Ariza qabul qilindi — rol berish / punkt ochish (ko'p rol modeli).

    Foydalanuvchi bir nechta rolega ega bo'lishi mumkin. Birlamchi `role`
    maydoni "asosiy" rol sifatida qoladi (mavjud asosiy rol buzilmaydi).
    """
    from .models import RoleApplication, User

    user = app.user
    role = app.role

    if role == User.Role.PICKUP.value:
        from apps.orders.models import PickupPoint

        PickupPoint.objects.get_or_create(
            name=app.point_name or f"{app.full_name} punkti",
            defaults={
                "address": app.point_address or app.address,
                "phone": app.phone,
                "latitude": app.point_latitude,
                "longitude": app.point_longitude,
                "is_active": True,
            },
        )

    # Rol berish: asosiy rol "customer" (yoki bo'sh) bo'lsa uni yangilaymiz,
    # aks holda qo'shimcha rollar ro'yxatiga qo'shamiz.
    if user.role in (User.Role.CUSTOMER, ""):
        user.role = role
    else:
        user.add_role(role)

    update_fields = ["role", "roles"]
    if role == User.Role.PICKUP.value:
        from apps.orders.models import PickupPoint

        point = PickupPoint.objects.filter(
            name=app.point_name or f"{app.full_name} punkti"
        ).order_by("-id").first()
        if point is not None:
            user.pickup_point = point
            update_fields.append("pickup_point")
    user.save(update_fields=update_fields)


def notify_new_role_application(application_pk: int) -> int:
    """Yangi ariza: admin Telegram chatlariga inline tugmalar bilan xabar."""
    try:
        from apps.telegram_bot.services import notify_new_role_application as tg_notify

        return tg_notify(application_pk)
    except Exception as exc:  # noqa: BLE001 — bot sozlanmagan bo'lishi mumkin
        logger.warning("Ariza xabari yuborilmadi (#%s): %s", application_pk, exc)
        return 0


def notify_role_application_result(application_pk: int) -> bool:
    """Ariza egasiga natijani bildiradi (Telegram bog'langan bo'lsa)."""
    try:
        from apps.telegram_bot.services import notify_role_application_result as tg_result

        return tg_result(application_pk)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ariza natijasi yuborilmadi (#%s): %s", application_pk, exc)
        return False
