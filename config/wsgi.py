import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
