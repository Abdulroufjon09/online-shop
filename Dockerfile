# ============================================================
#  ONLINE SAVDO — Backend image (Django + Gunicorn)
#  Build: docker build -t online-savdo-backend ./backend
# ============================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pillow / psycopg uchun tizim kutubxonalari
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-production.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-production.txt

COPY . .

RUN mkdir -p /app/media /app/staticfiles

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
