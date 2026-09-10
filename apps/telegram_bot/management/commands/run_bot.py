# ============================================================
#  python manage.py run_bot
#
#  Telegram botni long-polling rejimida ishga tushiradi.
#  Lokal dev uchun: ochiq (public) URL bo'lmasa webhook ishlamaydi,
#  polling esa bir xil handlerlardan foydalanadi.
#
#  Production'da (public URL mavjud) o'rniga:
#    python manage.py set_webhook
# ============================================================
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Telegram botni long-polling rejimida ishga tushiradi (lokal dev uchun)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--drop-pending",
            action="store_true",
            help="Ishga tushishdan oldin kutib turgan update'larni o'chirish.",
        )

    def handle(self, *args, **options):
        if not settings.BOT_TOKEN:
            raise CommandError("BOT_TOKEN sozlanmagan (.env da BOT_TOKEN ni kiriting).")

        from apps.telegram_bot.bot import get_application

        application = get_application()
        if application is None:
            raise CommandError("Bot Application yaratilmadi.")

        self.stdout.write(
            self.style.SUCCESS(
                "Bot polling rejimida ishga tushdi — to'xtatish uchun Ctrl+C bosing."
            )
        )
        # Python 3.12+ da asosiy ipda avtomatik event-loop yaratilmaydi —
        # run_polling get_event_loop() ni chaqiradi, shuning uchun
        # yangi loopni o'zimiz o'rnatib beramiz.
        import asyncio

        asyncio.set_event_loop(asyncio.new_event_loop())
        # run_polling o'zi delete_webhook() chaqiradi (webhook/polling ziddiyati bo'lmasin),
        # update'larni esa xuddi webhook'dagi kabi bir xil handlerlar qayta ishlaydi.
        application.run_polling(
            drop_pending_updates=bool(options["drop_pending"]),
        )
