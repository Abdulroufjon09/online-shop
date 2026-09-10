# ============================================================
#  Development sozlamalari (localhost / mahalliy ishlab chiqish)
# ============================================================
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

# Kod maxfiy bo'lmagan holatda ko'rsatilmasin — lekin dev qulayligi uchun
# DEBUG rejimida API javobiga dev_code qo'shiladi (accounts/serializers.py).
# Bu FAQAT mahalliy ishlab chiqish uchun!

# Rasm xavfsizligi — devda ham bir xil qoidalar
# (upload cheklovlari kodda, ular DEBUG ga bog'liq emas)

# Konsol loglarini batafsil ko'rsatish
import logging  # noqa: E402

logging.getLogger("django.server").setLevel(logging.WARNING)
