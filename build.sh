#!/usr/bin/env bash
# ============================================================
#  Render build script — backend
#  1) Bog'liqliklarni o'rnatish
#  2) Statik fayllarni yig'ish (WhiteNoise)
#  3) Migratsiyalar
#  4) Admin yaratish (env: DEMO_ADMIN_PHONE/PASSWORD)
# ============================================================
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py create_admin
