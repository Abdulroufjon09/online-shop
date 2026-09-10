from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Telefon raqam asosidagi foydalanuvchi menejeri (username'siz)."""

    use_in_migrations = True

    def _create_user(self, phone, password, **extra_fields):
        if not phone:
            raise ValueError("Telefon raqami kiritilishi shart.")
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        # Yangi foydalanuvchi kodni tasdiqlaguncha faol emas
        extra_fields.setdefault("is_active", False)
        extra_fields.setdefault("is_verified", False)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser is_staff=True bo'lishi kerak.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser is_superuser=True bo'lishi kerak.")
        return self._create_user(phone, password, **extra_fields)
