# ============================================================
#  Production admin yaratish (demo ma'lumotlarsiz)
#  Misol:  python manage.py create_admin
#  Env:    DEMO_ADMIN_PHONE, DEMO_ADMIN_PASSWORD, ADMIN_FULL_NAME
# ============================================================
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.core.validators import normalize_phone


class Command(BaseCommand):
    help = "Admin foydalanuvchini yaratadi/yangilaydi (env dan sozlanadi)."

    def handle(self, *args, **options) -> None:
        phone = normalize_phone(settings.DEMO_ADMIN_PHONE)
        full_name = getattr(settings, "ADMIN_FULL_NAME", "Abdulroufjon")
        password = settings.DEMO_ADMIN_PASSWORD

        admin, created = User.objects.get_or_create(
            phone=phone,
            defaults={"full_name": full_name},
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_active = True
        admin.is_verified = True
        admin.role = User.Role.ADMIN
        admin.full_name = full_name
        admin.set_password(password)
        admin.save()

        action = "yaratildi" if created else "yangilandi"
        self.stdout.write(
            self.style.SUCCESS(f"[OK] Admin {action}: {phone}")
        )
