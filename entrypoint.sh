#!/bin/sh
# ============================================================
#  Container ishga tushganda: migratsiya + statik + (ixtiyoriy) seed
# ============================================================
set -e

echo "[entrypoint] Migratsiyalar..."
python manage.py migrate --noinput

echo "[entrypoint] Statik fayllar..."
python manage.py collectstatic --noinput 2>/dev/null || true

# CREATE_ADMIN=true bo'lsa demo ma'lumotlar yaratiladi
if [ "${CREATE_ADMIN:-false}" = "true" ]; then
  echo "[entrypoint] Demo ma'lumotlar..."
  python manage.py seed_demo || echo "[entrypoint] seed_demo o'tkazib yuborildi"
fi

echo "[entrypoint] Server ishga tushmoqda: $*"
exec "$@"
