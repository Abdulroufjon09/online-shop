# ============================================================
#  Telegram webhook view
#
#  Manzil: /telegram/webhook/<secret>/
#  Secret yo'l — har kim botga soxta update yuborolmasligi uchun
#  (WEBHOOK_PATH_SECRET SECRET_KEY dan hosil qilinadi).
# ============================================================
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.security import constant_time_equal

from .bot import get_application, run_on_bot_loop

logger = logging.getLogger("apps.telegram_bot")


@csrf_exempt
@require_POST
def telegram_webhook(request, secret: str):
    """Telegram serveri update'larini shu yerga yuboradi."""
    from django.conf import settings

    # Maxfiy yo'lni tekshirish — faqat Telegram o'zi yubora oladi
    if not secret or not constant_time_equal(secret, settings.WEBHOOK_PATH_SECRET):
        return JsonResponse({"ok": False, "error": "invalid secret"}, status=403)

    # Telegram tomonidan yuborilgan X-Telegram-Bot-Api-Secret-Token sarlavhasi —
    # setWebhook'da secret_token sifatida berilgan qiymatga teng bo'lishi shart.
    header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not constant_time_equal(header_token, settings.WEBHOOK_PATH_SECRET):
        logger.warning("Webhook: noto'g'ri secret-token sarlavhasi — so'rov rad etildi.")
        return JsonResponse({"ok": False, "error": "invalid token"}, status=403)

    application = get_application()
    if application is None:
        logger.warning("BOT_TOKEN sozlanmagan — webhook ishlay olmaydi.")
        return JsonResponse({"ok": False, "error": "bot not configured"}, status=503)

    try:
        from telegram import Update

        payload = json.loads(request.body.decode("utf-8"))
        update = Update.de_json(payload, application.bot)

        async def _process():
            # initialize() idempotent — birinchi update'da bir marta ishlaydi
            await application.initialize()
            await application.process_update(update)

        # Doimiy bot loopida bajarish — har safar yangi asyncio.run
        # ochilsa httpx klient eski loopga bog'lanib qoladi
        run_on_bot_loop(_process())
    except Exception as exc:  # noqa: BLE001
        # Xatolikni yutib yubormaymiz — log qilamiz (Telegram qayta yuboradi)
        logger.exception("Webhook update'ni qayta ishlashda xato: %s", exc)

    return JsonResponse({"ok": True})
