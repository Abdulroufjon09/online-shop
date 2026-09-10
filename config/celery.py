# ============================================================
#  Celery app — background tasklar uchun (ixtiyoriy)
#  Devda USE_CELERY=False bo'lsa ishlatilmaydi.
# ============================================================
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("online_savdo")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
