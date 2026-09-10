# ============================================================
#  Telegram xabar xizmatlari
#
#  Kanallar:
#    console  — BOT_TOKEN yo'q (kod faqat server logida, DEBUG ko'rinadi)
#    telegram — foydalanuvchi chatini bog'lagan (to'g'ridan-to'g'ri)
#    via_bot  — chat bog'lanmagan: botga raqam yozilsa kod shu yerga keladi
# ============================================================
import logging
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger("apps.telegram_bot")


# ------------------------------------------------------------
#  Formatlash yordamchilari
# ------------------------------------------------------------
def format_money(value) -> str:
    """1000000 -> '1 000 000 so'm'"""
    try:
        amount = int(Decimal(value))
    except (TypeError, ValueError):
        amount = int(Decimal("0"))
    return f"{amount:,}".replace(",", " ") + " so'm"


def build_registration_code_text(code: str) -> str:
    return (
        "✅ Online Savdo — ro'yxatdan o'tish kodi\n\n"
        f"<b>Kodingiz: {code}</b>\n\n"
        "Kodni saytga kiriting. Kod 10 daqiqa amal qiladi.\n"
        "Agar bu siz bo'lmasangiz, xabarni e'tiborsiz qoldiring."
    )


# ------------------------------------------------------------
#  Yetkazish
# ------------------------------------------------------------
def _enqueue_message(chat_id, text: str) -> bool:
    """Xabarni navbatga qo'shadi (celery) yoki sinxron yuboradi.

    Celery eager rejimida ham `.delay()` natija-backendiga ulanadi —
    redis o'rnatilmagan muhitda bu import xatosi bilan yiqiladi.
    Shuning uchun eager rejimda to'g'ridan-to'g'ri yuboramiz.
    """
    if not settings.BOT_TOKEN or not chat_id:
        return False

    from django.conf import settings as _s

    if getattr(_s, "CELERY_TASK_ALWAYS_EAGER", False):
        # Navbatga tushirmay, shu zahoti yuborish (dev rejimi)
        from .bot import send_message_sync

        try:
            return send_message_sync(int(chat_id), text)
        except Exception:
            logger.exception("Telegram xabarni yuborishda xato (chat=%s)", chat_id)
            return False

    from .tasks import task_send_message

    task_send_message.delay(int(chat_id), text)
    return True


def send_registration_code(user_pk: int, dry_run: bool = False) -> str:
    """
    Ro'yxatdan o'tish kodini yetkazish kanalini aniqlaydi va yuboradi.

    dry_run=True — aslida yubormaydi, faqat kanal nomini qaytaradi
    (javobda 'channel' ko'rsatish uchun).
    """
    from apps.accounts.models import User

    user = User.objects.filter(pk=user_pk).first()
    if user is None:
        return "error"

    code = user.verification_code or ""
    text = build_registration_code_text(code)

    # 1) BOT_TOKEN yo'q — faqat konsol (dev rejimi)
    if not settings.BOT_TOKEN:
        if not dry_run:
            logger.info("Tasdiqlash kodi (%s uchun): %s", user.phone, code)
        return "console"

    # 2) Chat bog'langan — to'g'ridan-to'g'ri yuborish
    if user.telegram_chat_id:
        if not dry_run:
            _enqueue_message(user.telegram_chat_id, text)
        return "telegram"

    # 3) Chat bog'lanmagan — foydalanuvchi botga raqamini yozadi
    return "via_bot"


def notify_new_order(order_pk: int) -> int:
    """
    Yangi buyurtma: adminlarga xabar + buyurtma egasiga tasdiq.
    Qaytadi: yuborilgan admin xabarlari soni.
    """
    from apps.orders.models import Order

    order = (
        Order.objects.select_related("user")
        .prefetch_related("items")
        .filter(pk=order_pk)
        .first()
    )
    if order is None:
        return 0

    lines = "\n".join(
        f"• {item.product_name} — {item.quantity} dona ({format_money(item.line_total)})"
        for item in order.items.all()
    )
    text = (
        "🛒 <b>YANGI BUYURTMA!</b>\n\n"
        f"👤 Foydalanuvchi: {order.full_name} (ID: {order.user_id})\n"
        f"📞 Telefon: {order.phone}\n"
        f"📍 Manzil: {order.address}\n"
        f"📦 Mahsulotlar:\n{lines}\n"
        f"💰 Summa: {format_money(order.subtotal)}\n"
    )
    if order.discount_amount:
        text += f"🏷 Chegirma: -{format_money(order.discount_amount)}\n"
    text += f"✅ Jami: <b>{format_money(order.total)}</b>\n"
    text += f"📅 Vaqt: {order.created_at:%Y-%m-%d %H:%M}"

    sent = 0
    for chat_id in settings.ADMIN_TELEGRAM_CHAT_IDS:
        if _enqueue_message(chat_id, text):
            sent += 1

    # Foydalanuvchiga tasdiq (chat bog'langan bo'lsa)
    if order.user.telegram_chat_id:
        confirm = (
            "📦 Buyurtmangiz qabul qilindi!\n\n"
            f"Raqam: {order.order_number}\n"
            f"Summa: {format_money(order.total)}\n"
            "Operator tez orada siz bilan bog'lanadi. Rahmat! 🙌"
        )
        _enqueue_message(order.user.telegram_chat_id, confirm)

    return sent


def notify_order_status_changed(order_pk: int) -> bool:
    """Buyurtma holati o'zgarganini foydalanuvchiga bildiradi."""
    from apps.orders.models import Order

    order = Order.objects.select_related("user").filter(pk=order_pk).first()
    if order is None or not order.user.telegram_chat_id:
        return False

    emoji = {
        Order.Status.PENDING: "⏳",
        Order.Status.PROCESSING: "🛠",
        Order.Status.READY: "📦",
        Order.Status.OUT_FOR_DELIVERY: "🚚",
        Order.Status.DELIVERED: "✅",
        Order.Status.CANCELLED: "❌",
    }.get(order.status, "📋")
    text = (
        f"{emoji} Buyurtma #{order.order_number} holati yangilandi:\n\n"
        f"<b>{order.get_status_display()}</b>"
    )
    return _enqueue_message(order.user.telegram_chat_id, text)


# ------------------------------------------------------------
#  Rol arizalari (sotuvchi / kuryer / punkt) xabarlari
# ------------------------------------------------------------
def _role_application_text(app, *, with_buttons: bool = False) -> str:
    """Ariza haqida matn (admin inline tugmalar uchun)."""
    from apps.accounts.models import RoleApplication

    text = "📩 <b>YANGI ARIZA!</b>\n\n"
    text += f"🎯 Rol: <b>{app.get_role_display()}</b>\n"
    text += f"👤 Ism: {app.full_name}\n"
    text += f"📞 Telefon: {app.phone}\n"
    text += f"📍 Manzil: {app.address}\n"
    if app.address_latitude is not None and app.address_longitude is not None:
        text += f"   🗺 Xarita: https://www.openstreetmap.org/?mlat={app.address_latitude}&mlon={app.address_longitude}#map=16/{app.address_latitude}/{app.address_longitude}\n"
    text += f"🛂 Passport: {app.passport or '—'}\n"
    text += f"💳 Karta: {app.card_number_masked}\n"
    if app.role == "pickup":
        text += f"\n🏬 <b>Punkt ochish:</b>\n"
        text += f"   Nomi: {app.point_name or '—'}\n"
        text += f"   Manzil: {app.point_address or '—'}\n"
        if app.point_latitude is not None and app.point_longitude is not None:
            text += f"   Xarita: https://www.openstreetmap.org/?mlat={app.point_latitude}&mlon={app.point_longitude}#map=16/{app.point_latitude}/{app.point_longitude}\n"
    text += f"\n⏰ {app.created_at:%Y-%m-%d %H:%M}"
    return text


def notify_new_role_application(application_pk: int) -> int:
    """Yangi rol arizasi haqida adminlarga inline tugmalar bilan xabar."""
    from apps.accounts.models import RoleApplication

    app = (
        RoleApplication.objects.select_related("user")
        .filter(pk=application_pk)
        .first()
    )
    if app is None or not settings.BOT_TOKEN:
        return 0

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Qabul qilish", callback_data=f"ra:{app.pk}:ok"
                ),
                InlineKeyboardButton(
                    "⏳ Kutish", callback_data=f"ra:{app.pk}:hold"
                ),
                InlineKeyboardButton(
                    "❌ Rad etish", callback_data=f"ra:{app.pk}:no"
                ),
            ]
        ]
    )
    text = _role_application_text(app)

    sent = 0
    for chat_id in settings.ADMIN_TELEGRAM_CHAT_IDS:
        from .bot import send_message_sync

        if send_message_sync(chat_id, text, reply_markup=keyboard):
            sent += 1
    return sent


def notify_role_application_result(application_pk: int) -> bool:
    """Ariza egasiga qaror haqida xabar (Telegram bog'langan bo'lsa)."""
    from apps.accounts.models import RoleApplication

    app = (
        RoleApplication.objects.select_related("user")
        .filter(pk=application_pk)
        .first()
    )
    if app is None or not settings.BOT_TOKEN or not app.user.telegram_chat_id:
        return False

    if app.status == RoleApplication.Status.APPROVED:
        text = (
            "🎉 <b>Arizangiz QABUL QILINDI!</b>\n\n"
            f"Rol: {app.get_role_display()}\n"
        )
        if app.role == "pickup" and app.status == RoleApplication.Status.APPROVED:
            text += "Endi punkt panelidan buyurtmalarni boshqarishingiz mumkin.\n"
        else:
            text += (
                "Endi saytdagi tegishli panelda ishlashingiz mumkin "
                "(profil sahifangizni yangilang).\n"
            )
    elif app.status == RoleApplication.Status.REJECTED:
        text = (
            "❌ <b>Arizangiz rad etildi.</b>\n\n"
        )
        if app.note:
            text += f"Izoh: {app.note}\n"
        text += "Savollar bo'lsa operator bilan bog'laning."
    else:
        return False  # kutish — xabar yuborilmaydi

    from .bot import send_message_sync

    return send_message_sync(app.user.telegram_chat_id, text)


def broadcast_discount_coupon(coupon_pk: int) -> int:
    """
    Chegirma kuponini barcha Telegram bog'lagan foydalanuvchilarga yuboradi.
    Qaytadi: navbatga qo'shilgan chatlar soni.
    """
    from apps.accounts.models import User
    from apps.discounts.models import Coupon

    coupon = Coupon.objects.filter(pk=coupon_pk).first()
    if coupon is None:
        return 0

    valid_until = (
        f"{coupon.valid_to:%Y-%m-%d %H:%M}" if coupon.valid_to else "cheksiz"
    )
    text = (
        "🎉 <b>CHEGIRMA!</b>\n\n"
        f"<b>{coupon.percent}%</b> chegirma — kodi: <b>{coupon.code}</b>\n"
    )
    if coupon.description:
        text += f"{coupon.description}\n"
    text += f"⏳ Amal qilish muddati: {valid_until} gacha\n\nKodni kassada kiriting!"

    chats = list(
        User.objects.filter(telegram_chat_id__isnull=False)
        .values_list("telegram_chat_id", flat=True)
    )
    sent = 0
    for chat_id in chats:
        if _enqueue_message(chat_id, text):
            sent += 1
    return sent
