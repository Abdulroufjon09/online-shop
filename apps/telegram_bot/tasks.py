# ============================================================
#  Celery background tasklar
#  USE_CELERY=False (dev): eager rejimda sinxron ishlaydi
#  USE_CELERY=True  (prod): Redis orqali navbatga tushadi
# ============================================================
from celery import shared_task


@shared_task(name="telegram_bot.send_message")
def task_send_message(chat_id: int, text: str) -> bool:
    """Bitta chatga matnli xabar yuborish."""
    from .bot import send_message_sync

    return send_message_sync(chat_id, text)


@shared_task(name="telegram_bot.deliver_registration_code")
def task_deliver_registration_code(user_pk: int) -> str:
    """Ro'yxatdan o'tish tasdiqlash kodini yetkazish (kanal aniqlab)."""
    from .services import send_registration_code

    return send_registration_code(user_pk)


@shared_task(name="telegram_bot.notify_new_order")
def task_notify_new_order(order_pk: int) -> int:
    """Yangi buyurtma haqida adminlarga xabar."""
    from .services import notify_new_order

    return notify_new_order(order_pk)


@shared_task(name="telegram_bot.notify_order_status_changed")
def task_notify_order_status_changed(order_pk: int) -> bool:
    """Buyurtma holati o'zgargani haqida foydalanuvchiga xabar."""
    from .services import notify_order_status_changed

    return notify_order_status_changed(order_pk)


@shared_task(name="telegram_bot.broadcast_coupon")
def task_broadcast_coupon(coupon_pk: int) -> int:
    """Chegirma kuponini barcha bog'langan foydalanuvchilarga yuborish."""
    from .services import broadcast_discount_coupon

    return broadcast_discount_coupon(coupon_pk)
