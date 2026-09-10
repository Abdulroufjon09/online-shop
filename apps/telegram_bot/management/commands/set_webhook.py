# ============================================================
#  python manage.py set_webhook
#  Telegram bot uchun webhook manzilini o'rnatadi.
#  Kerakli: BOT_TOKEN va WEBHOOK_BASE_URL (production).
# ============================================================
import json
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Telegram bot webhook manzilini o'rnatadi."

    def handle(self, *args, **options):
        if not settings.BOT_TOKEN:
            raise CommandError(
                "BOT_TOKEN sozlanmagan (.env da BOT_TOKEN ni kiriting)."
            )
        if not settings.WEBHOOK_BASE_URL:
            raise CommandError(
                "WEBHOOK_BASE_URL sozlanmagan (.env da https://domeningiz.com ni kiriting)."
            )

        webhook_url = (
            f"{settings.WEBHOOK_BASE_URL}/telegram/webhook/{settings.WEBHOOK_PATH_SECRET}/"
        )

        # 1) Bot ma'lumotini tekshirish
        try:
            with urllib.request.urlopen(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getMe", timeout=15
            ) as resp:
                me = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Telegram bilan bog'lanib bo'lmadi: {exc}") from exc
        if not me.get("ok"):
            raise CommandError("BOT_TOKEN noto'g'ri — getMe xato qaytardi.")

        bot_user = me["result"].get("username", "?")
        self.stdout.write(self.style.SUCCESS(f"Bot: @{bot_user}"))

        # 2) Webhook o'rnatish
        #    secret_token — Telegram har bir so'rovga shu sarlavhani qo'shadi;
        #    view tomonida tekshirish soxta so'rovlardan himoya qiladi.
        params = urllib.parse.urlencode(
            {
                "url": webhook_url,
                "drop_pending_updates": "true",
                "secret_token": settings.WEBHOOK_PATH_SECRET,
            }
        )
        try:
            with urllib.request.urlopen(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/setWebhook?{params}",
                timeout=15,
            ) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"setWebhook so'rovi bajarilmadi: {exc}") from exc

        if result.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"✓ Webhook o'rnatildi: {webhook_url}"))
        else:
            raise CommandError(f"setWebhook xato: {result}")
