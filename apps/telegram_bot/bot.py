# ============================================================
#  Telegram bot — handlerlar va Application
#
#  Buyruqlar:
#    /start          — salomlashish
#    /help           — yordam
#    /link <telefon> — Telegram chatni hisobingizga bog'lash
#                      (kod profil sahifasida tasdiqlanadi)
#
#  Oddiy matn (telefon raqam) — ro'yxatdan o'tishda tasdiqlash
#  kodi shu chatga yuboriladi (kanal: via_bot).
# ============================================================
import asyncio
import logging
import threading

from asgiref.sync import sync_to_async
from django.conf import settings

logger = logging.getLogger("apps.telegram_bot")

_application = None
_bot_loop = None
_bot_loop_lock = threading.Lock()


def get_application():
    """Bot Application obyektini yaratadi (BOT_TOKEN sozlangan bo'lsa)."""
    global _application
    if not settings.BOT_TOKEN:
        return None
    if _application is None:
        from telegram.ext import (
            Application,
            CommandHandler,
            MessageHandler,
            filters,
        )

        from telegram.ext import CallbackQueryHandler

        _application = Application.builder().token(settings.BOT_TOKEN).build()
        _application.add_handler(CommandHandler("start", _cmd_start))
        _application.add_handler(CommandHandler("help", _cmd_help))
        _application.add_handler(CommandHandler("link", _cmd_link))
        _application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text_message)
        )
        _application.add_handler(
            CallbackQueryHandler(_on_callback_query, pattern=r"^ra:")
        )
        _application.add_error_handler(_on_error)
        logger.info("Telegram bot handlerlari ro'yxatdan o'tkazildi.")
    return _application


# ------------------------------------------------------------
#  Doimiy event-loop (fon ipida)
#
#  Har bir yuboruv uchun yangi asyncio.run() ochilsa, Application'ning
#  httpx klienti birinchi loopga bog'lanib qoladi va keyingi
#  chaqiruvlarda "RuntimeError: Event loop is closed" beradi.
#  Shuning uchun bitta doimiy loop ishlatiladi — barcha yuboruvlar
#  va webhook update'lari shu loopda bajariladi.
# ------------------------------------------------------------
def get_bot_loop() -> asyncio.AbstractEventLoop:
    """Bot uchun maxsus, doimiy ishlaydigan event-loop qaytaradi."""
    global _bot_loop
    with _bot_loop_lock:
        if _bot_loop is None or _bot_loop.is_closed():
            _bot_loop = asyncio.new_event_loop()
            threading.Thread(
                target=_bot_loop.run_forever,
                name="telegram-bot-loop",
                daemon=True,
            ).start()
    return _bot_loop


def run_on_bot_loop(coro, timeout: float = 30.0):
    """Korutinani doimiy bot loopida bajaradi va natijasini kutadi."""
    future = asyncio.run_coroutine_threadsafe(coro, get_bot_loop())
    return future.result(timeout=timeout)


# ------------------------------------------------------------
#  Yordamchi (sync) xabar yuborish
# ------------------------------------------------------------
def send_message_sync(
    chat_id: int, text: str, reply_markup=None, parse_mode: str = "HTML"
) -> bool:
    """Synchronous xabar yuborish (doimiy fon loopida)."""
    app = get_application()
    if app is None or not chat_id:
        return False

    async def _go():
        # initialize() idempotent — birinchi chaqiruvda ishlaydi,
        # keyingilarida darhol qaytadi (webhook'siz ham shart).
        await app.initialize()
        await app.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

    try:
        run_on_bot_loop(_go())
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram xabar yuborilmadi (chat=%s): %s", chat_id, exc)
        return False


# ------------------------------------------------------------
#  Matnlar
# ------------------------------------------------------------
HELP_TEXT = (
    "Assalomu alaykum! 🤖\n\n"
    "Men Online Savdo do'konining yordamchi botiman.\n\n"
    "Buyruqlar:\n"
    "/start — boshlash\n"
    "/link <telefon> — Telegram hisobingizni sayt profiliga bog'lash\n\n"
    "Ro'yxatdan o'tishda tasdiqlash kodi: saytda telefon raqamingizni "
    "kiritib ro'yxatdan o'ting, so'ng shu chatga raqamingizni yozing — "
    "kod shu yerga keladi."
)

START_TEXT = (
    "Assalomu alaykum! Online Savdo do'konining botiga xush kelibsiz. 🛒\n\n"
    "Telefon raqamingizni yuboring — tasdiqlash kodi shu chatga keladi.\n"
    "Yordam: /help"
)

BIND_OK_PREFIX = "🔗 Telegram hisobingiz bog'lanmoqda."
BIND_CODE_FORMAT = (
    "\n\nProfil sahifasida 'Telegram ulash' bo'limiga ushbu kodni kiriting:\n"
    "<code>{code}</code>\n\nKod {ttl} daqiqa amal qiladi."
)


# ------------------------------------------------------------
#  Handlerlar (async — python-telegram-bot)
# ------------------------------------------------------------
async def _on_callback_query(update, context):
    """Ariza tugmalari: ✅ qabul / ⏳ kutish / ❌ rad etish."""
    from django.conf import settings as dj_settings

    query = update.callback_query
    chat_id = getattr(query.message, "chat", None)
    chat_id = chat_id.id if chat_id else query.from_user.id

    admin_chats = {str(c) for c in dj_settings.ADMIN_TELEGRAM_CHAT_IDS}
    if str(chat_id) not in admin_chats:
        await query.answer("Sizda ruxsat yo'q.", show_alert=True)
        return

    parts = (query.data or "").split(":")
    if len(parts) != 3 or parts[0] != "ra":
        await query.answer()
        return

    try:
        application_pk = int(parts[1])
    except ValueError:
        await query.answer("Noto'g'ri ariza.")
        return

    from apps.accounts.models import RoleApplication
    from apps.accounts.services import review_role_application

    action_map = {
        "ok": RoleApplication.Status.APPROVED,
        "no": RoleApplication.Status.REJECTED,
        "hold": RoleApplication.Status.PENDING,
    }
    new_status = action_map.get(parts[2])
    if new_status is None:
        await query.answer()
        return

    try:
        app = await sync_to_async(review_role_application)(
            application_pk, new_status
        )
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    status_text = {
        RoleApplication.Status.APPROVED: "Ariza QABUL QILINDI ✅",
        RoleApplication.Status.REJECTED: "Ariza RAD ETILDI ❌",
        RoleApplication.Status.PENDING: "Ariza kutishda qoldi ⏳",
    }[app.status]

    # Tugmalarni olib tashlab, natijani xabarga yozamiz
    if query.message:
        base = query.message.text or ""
        await query.edit_message_text(
            f"{base}\n\n━━━━━━━━━━━━\n<b>{status_text}</b>",
            parse_mode="HTML",
            reply_markup=None,
        )
    await query.answer(status_text)

    # Arizachiga natijani to'g'ridan-to'g'ri yuboramiz (eager navbat
    # asyncio loop ichida asyncio.run chaqira olmaydi)
    if app.user.telegram_chat_id and app.status != RoleApplication.Status.PENDING:
        try:
            role_name = app.get_role_display()
            if app.status == RoleApplication.Status.APPROVED:
                text = (
                    "🎉 <b>Arizangiz QABUL QILINDI!</b>\n\n"
                    f"Rol: {role_name}\n\n"
                    "Endi saytdagi tegishli panelda ishlashingiz mumkin "
                    "(profil sahifangizni yangilang)."
                )
            else:
                text = "❌ <b>Arizangiz rad etildi.</b>\n\n"
                if app.note:
                    text += f"Izoh: {app.note}\n"
                text += "Savollar bo'lsa operator bilan bog'laning."
            await context.bot.send_message(
                chat_id=app.user.telegram_chat_id, text=text, parse_mode="HTML"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Natija xabari yuborilmadi (#%s): %s", app.pk, exc)


async def _on_error(update, context):
    """Handler ichida yuzaga kelgan xatolarni jurnallash (bot o'lishi emas)."""
    logger.error("Bot handler xatosi: %s", context.error, exc_info=context.error)


async def _cmd_start(update, _context):
    await update.message.reply_text(START_TEXT)


async def _cmd_help(update, _context):
    await update.message.reply_text(HELP_TEXT)


async def _cmd_link(update, _context):
    """Telegram chatni tasdiqlangan hisobga bog'lash (/link <telefon>)."""
    parts = (update.message.text or "").split()
    if len(parts) < 2:
        await update.message.reply_text(
            "Namuna: /link 998901234567  (telefon raqamini kiriting)"
        )
        return

    phone = _normalize_phone_for_bot(parts[1])
    if phone is None:
        await update.message.reply_text(
            "Telefon raqam formati noto'g'ri. Namuna: +998901234567"
        )
        return

    user = await sync_to_async(_find_user)(phone)
    if user is None:
        await update.message.reply_text(
            "Bu raqam tizimda topilmadi. Avval saytda ro'yxatdan o'ting."
        )
        return
    if not user.is_verified or not user.is_active:
        await update.message.reply_text(
            "Hisob hali tasdiqlanmagan. Avval ro'yxatdan o'tishni yakunlang."
        )
        return

    chat_id = update.effective_chat.id
    if user.telegram_chat_id == chat_id:
        await update.message.reply_text(
            "Bu chat allaqachon hisobingizga bog'langan. ✅"
        )
        return
    if user.telegram_chat_id and user.telegram_chat_id != chat_id:
        await update.message.reply_text(
            "Bu raqam boshqa Telegram hisobga bog'langan. "
            "Avval sayt profilida eski bog'lanishni olib tashlang."
        )
        return

    # Chat boshqa foydalanuvchiga bog'langanligini tekshirish
    taken = await sync_to_async(_chat_id_taken)(chat_id, user.pk)
    if taken:
        await update.message.reply_text(
            "Bu chat boshqa foydalanuvchiga bog'langan. Avval o'sha hisobni uzib qo'ying."
        )
        return

    code = await sync_to_async(user.prepare_telegram_bind)(chat_id)
    from django.conf import settings as dj_settings

    await update.message.reply_text(
        BIND_OK_PREFIX
        + BIND_CODE_FORMAT.format(
            code=code, ttl=dj_settings.PHONE_VERIFY_CODE_TTL_MINUTES
        )
    )


async def _on_text_message(update, _context):
    """Oddiy matn — telefon raqam bo'lsa tasdiqlash kodini yuboradi."""
    raw = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    phone = _normalize_phone_for_bot(raw)
    if phone is None:
        # Raqam emas — yo'riqnoma
        await update.message.reply_text(HELP_TEXT)
        return

    user = await sync_to_async(_find_user)(phone)
    if user is None:
        await update.message.reply_text(
            "Bu raqam tizimda ro'yxatdan o'tmagan. "
            "Avval saytda ro'yxatdan o'ting, so'ng raqamingizni shu yerga yozing."
        )
        return

    # Chat boshqa foydalanuvchiga tegishli bo'lmasin
    other = await sync_to_async(_chat_id_taken)(chat_id, user.pk)
    if other:
        await update.message.reply_text(
            "Bu chat boshqa foydalanuvchiga bog'langan. Avval o'sha hisobni uzib qo'ying."
        )
        return

    # Tasdiqlanmagan ro'yxatdan o'tish uchun kod yetkazish (kanal: via_bot)
    if not user.is_verified or not user.is_active:
        if user.telegram_chat_id and user.telegram_chat_id != chat_id:
            await update.message.reply_text(
                "Bu raqam boshqa Telegram hisobga bog'langan. "
                "Bog'lanishni sayt profilidan boshqaring."
            )
            return
        if not user.verification_code or user.verification_code_expired:
            await update.message.reply_text(
                "Ro'yxatdan o'tish kodi topilmadi yoki muddati o'tgan. "
                "Saytda 'Kodni qayta yuborish' tugmasini bosing."
            )
            return

        # Chatni hisobga bog'lab, kodni yuboramiz
        if not user.telegram_chat_id:
            await sync_to_async(_bind_chat_to_user)(user, chat_id)
        from apps.telegram_bot.services import build_registration_code_text

        await update.message.reply_text(build_registration_code_text(user.verification_code))
        return

    # Tasdiqlangan foydalanuvchi
    if user.telegram_chat_id == chat_id:
        await update.message.reply_text(
            "Siz allaqachon ro'yxatdan o'tgansiz va bu chat hisobingizga bog'langan. ✅"
        )
    else:
        await update.message.reply_text(
            "Siz allaqachon ro'yxatdan o'tgansiz. Ushbu chatni bog'lash uchun: "
            "/link <telefon>\nMasalan: /link 998901234567"
        )


# ------------------------------------------------------------
#  Yordamchi funksiyalar
# ------------------------------------------------------------
def _normalize_phone_for_bot(raw: str):
    """Bot matnidan telefon raqamni normalizatsiya qiladi (None — noto'g'ri)."""
    try:
        from apps.core.validators import normalize_phone

        return normalize_phone(raw)
    except Exception:  # noqa: BLE001
        return None


def _find_user(phone: str):
    from apps.accounts.models import User

    return User.objects.filter(phone=phone).first()


def _chat_id_taken(chat_id: int, exclude_pk: int) -> bool:
    """Chat boshqa foydalanuvchiga bog'langanmi (DB so'rovi — sync)."""
    from apps.accounts.models import User

    return (
        User.objects.filter(telegram_chat_id=chat_id)
        .exclude(pk=exclude_pk)
        .exists()
    )


def _bind_chat_to_user(user, chat_id: int) -> None:
    """Chat ID'ni foydalanuvchiga yozadi (DB yozuvi — sync)."""
    user.telegram_chat_id = chat_id
    user.save(update_fields=["telegram_chat_id"])
