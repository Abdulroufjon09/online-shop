# ============================================================
#  python manage.py seed_demo
#  Namuna ma'lumotlar: kategoriyalar, mahsulotlar (rasmlar bilan),
#  kupon, punkt, demo admin / xaridor / kuryer / punkt xodimi.
# ============================================================
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.core.validators import normalize_phone
from apps.discounts.models import Coupon
from apps.orders.models import PickupPoint
from apps.products.models import Category, Product, ProductImage

User = get_user_model()

CATEGORIES = [
    "Telefonlar",
    "Noutbuklar",
    "Elektronika",
    "Aksessuarlar",
    "Maishiy texnika",
    "Kiyim-kechak",
    "Go'zallik",
    "Sport",
]

PRODUCTS = [
    # (nomi, kategoriya, narx, chegirma %, zaxira, featured, tavsif)
    ("Samsung Galaxy A55 8/256", "Telefonlar", 4_290_000, 5, 15, True,
     "6.6\" AMOLED ekran, 50 MP kamera, 5000 mAh batareya."),
    ("iPhone 15 128GB", "Telefonlar", 9_990_000, 0, 8, True,
     "6.1\" Super Retina XDR, Dynamic Island, USB-C."),
    ("Redmi Note 13 Pro", "Telefonlar", 2_990_000, 10, 20, False,
     "200 MP kamera, 67W tez quvvatlash."),
    ("MacBook Air M2 13\"", "Noutbuklar", 12_900_000, 0, 6, True,
     "8/256, Midnight rangi, 18 soatgacha batareya."),
    ("Lenovo IdeaPad Slim 3", "Noutbuklar", 4_750_000, 7, 10, False,
     "Ryzen 5, 16/512 SSD, 15.6\" FHD."),
    ("Asus VivoBook 15", "Noutbuklar", 5_390_000, 0, 7, False,
     "Core i5, 8/512 SSD, ofis va o'qish uchun ideal."),
    ("AirPods Pro 2", "Elektronika", 1_890_000, 15, 25, True,
     "Faol shovqinni bostirish, MagSafe qutisi."),
    ("Samsung Galaxy Buds FE", "Elektronika", 690_000, 0, 18, False,
     "Qulay va sifatli simsiz quloqchinlar."),
    ("Smart Watch S8 Ultra", "Elektronika", 840_000, 20, 12, True,
     "GPS, yurak urishi nazorati, suv o'tkazmaydi."),
    ("JBL Go 4 (moviy)", "Elektronika", 390_000, 0, 30, False,
     "Yangi avlod JBL Go — kuchli ovoz, ixcham dizayn."),
    ("Robot changyutgich X10", "Maishiy texnika", 3_450_000, 12, 5, True,
     "Uyga robot yordamchisi — avtomatik tozalash."),
    ("Elektron choynak 1.7L", "Maishiy texnika", 245_000, 0, 40, False,
     "Zanglamaydigan po'lat, tez qaynatish."),
    ("Katta ekranli televizor 43\"", "Maishiy texnika", 3_890_000, 0, 9, False,
     "4K UHD, Smart TV, WiFi."),
    ("Classic futbolka (o'lcham S-XXL)", "Kiyim-kechak", 89_000, 0, 100, False,
     "100% paxta, bir necha rangda."),
    ("Sport krossovkalar", "Kiyim-kechak", 450_000, 25, 22, True,
     "Yengil, nafas oluvchi material — yugurish uchun."),
    ("Dermokosmetika to'plami", "Go'zallik", 320_000, 0, 15, False,
     "Terini parvarish qilish uchun tabiiy to'plam."),
    ("Fitnes sochiq + shisha", "Sport", 120_000, 0, 35, False,
     "Sport majmuasi — mashg'ulot uchun kerakli."),
    ("Yoga gilami (182x61)", "Sport", 190_000, 8, 28, False,
     "Qalin va sirpanmaydigan yoga gilami."),
]

# Rasm palitrasi (har bir mahsulot uchun 2-5 gradient)
IMAGE_PALETTES = [
    ("#4f46e5", "#7c3aed"),
    ("#0ea5e9", "#6366f1"),
    ("#ec4899", "#f43f5e"),
    ("#10b981", "#14b8a6"),
    ("#f59e0b", "#f97316"),
    ("#8b5cf6", "#d946ef"),
]


def _make_gradient_png(color_a: str, color_b: str, seed_offset: int = 0):
    """Oddiy gradient PNG yaratadi (placeholder rasm)."""
    width, height = 600, 450
    top = int(color_a.lstrip("#"), 16)
    bottom = int(color_b.lstrip("#"), 16)
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    r1, g1, b1 = (top >> 16) & 255, (top >> 8) & 255, top & 255
    r2, g2, b2 = (bottom >> 16) & 255, (bottom >> 8) & 255, bottom & 255
    for y in range(height):
        t = y / height
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    # chap burchakda och rangli tasma — "rasm" ko'rinishi uchun
    for x in range(0, width, 40):
        draw.ellipse(
            [x + seed_offset % 160, height * 0.25, x + 70 + seed_offset % 160, height * 0.85],
            fill=(255, 255, 255),
        )
    buf = BytesIO()
    img.save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name=f"placeholder_{color_a[1:]}_{seed_offset}.png")


class Command(BaseCommand):
    help = "Namuna (demo) ma'lumotlar bilan to'ldiradi."

    def handle(self, *args, **options):
        now = timezone.now()

        # ---- Kategoriyalar ----
        cats = {}
        for name in CATEGORIES:
            cat, _ = Category.objects.get_or_create(name=name)
            cat.is_active = True
            cat.save()
            cats[name] = cat
        self.stdout.write(self.style.SUCCESS(f"[OK] {len(cats)} ta kategoriya"))

        # ---- Mahsulotlar (2..5 rasm bilan) ----
        for index, (name, cat_name, price, disc, stock, feat, desc) in enumerate(PRODUCTS):
            obj, _ = Product.objects.get_or_create(
                name=name,
                defaults={
                    "category": cats[cat_name],
                    "price": price,
                    "discount_percent": disc,
                    "stock": stock,
                    "is_featured": feat,
                    "description": desc,
                    "is_active": True,
                },
            )
            obj.category = cats[cat_name]
            obj.is_active = True
            obj.is_featured = feat
            obj.save()

            # Rasmlar yo'q bo'lsa — 2 ta gradient yaratamiz
            if not obj.images.exists():
                pal = IMAGE_PALETTES[index % len(IMAGE_PALETTES)]
                first = _make_gradient_png(pal[0], pal[1], index)
                second = _make_gradient_png(pal[1], pal[0], index + 5)
                ProductImage.objects.create(product=obj, image=first, position=0)
                ProductImage.objects.create(product=obj, image=second, position=1)
                obj.image = first
                obj.save(update_fields=["image"])
        self.stdout.write(
            self.style.SUCCESS(f"[OK] {len(PRODUCTS)} ta mahsulot (har biri 2+ rasm bilan)")
        )

        # ---- Kuponlar ----
        coupon, _ = Coupon.objects.get_or_create(
            code="BAHOR20",
            defaults={
                "percent": 20,
                "description": "Barcha mahsulotlarga 20% chegirma",
                "valid_from": now,
                "valid_to": now + timedelta(days=30),
                "is_active": True,
            },
        )
        coupon.valid_to = now + timedelta(days=30)
        coupon.is_active = True
        coupon.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] Kupon: {coupon.code} ({coupon.percent}%)"))

        # ---- Punkt (yetkazib berish / olish nuqtasi) ----
        point, _ = PickupPoint.objects.get_or_create(
            name="Chilonzor punkti",
            defaults={
                "address": "Toshkent, Chilonzor tumani, Bunyodkor ko'chasi 12",
                "phone": "+998712000100",
                "latitude": 41.276,
                "longitude": 69.239,
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"[OK] Punkt: {point.name}"))

        # ---- Demo admin ----
        admin_phone = normalize_phone(settings.DEMO_ADMIN_PHONE)
        admin, _ = User.objects.get_or_create(
            phone=admin_phone,
            defaults={"is_staff": True, "is_superuser": True},
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_active = True
        admin.is_verified = True
        admin.role = User.Role.ADMIN
        admin.full_name = "Admin"
        admin.set_password(settings.DEMO_ADMIN_PASSWORD)
        admin.save()
        self.stdout.write(
            self.style.SUCCESS(f"[OK] Admin: {admin.phone} / {settings.DEMO_ADMIN_PASSWORD}")
        )

        # ---- Demo xaridor ----
        demo_phone = normalize_phone(settings.DEMO_USER_PHONE)
        demo_user, _ = User.objects.get_or_create(
            phone=demo_phone,
            defaults={"full_name": "Demo Foydalanuvchi"},
        )
        demo_user.is_active = True
        demo_user.is_verified = True
        demo_user.role = User.Role.CUSTOMER
        demo_user.full_name = demo_user.full_name or "Demo Foydalanuvchi"
        demo_user.set_password(settings.DEMO_USER_PASSWORD)
        demo_user.save()
        self.stdout.write(
            self.style.SUCCESS(f"[OK] Xaridor: {demo_user.phone} / {settings.DEMO_USER_PASSWORD}")
        )

        # ---- Demo kuryer ----
        courier, _ = User.objects.get_or_create(
            phone="+998901234561", defaults={"full_name": "Demo Kuryer"}
        )
        courier.is_active = True
        courier.is_verified = True
        courier.role = User.Role.COURIER
        courier.full_name = "Demo Kuryer"
        courier.set_password("Courier@123")
        courier.save()
        self.stdout.write(
            self.style.SUCCESS(f"[OK] Kuryer: {courier.phone} / Courier@123")
        )

        # ---- Demo punkt xodimi ----
        staff, _ = User.objects.get_or_create(
            phone="+998901234562", defaults={"full_name": "Punkt Xodimi"}
        )
        staff.is_active = True
        staff.is_verified = True
        staff.role = User.Role.PICKUP
        staff.pickup_point = point
        staff.full_name = "Punkt Xodimi"
        staff.set_password("Punkt@123")
        staff.save()
        self.stdout.write(
            self.style.SUCCESS(f"[OK] Punkt xodimi: {staff.phone} / Punkt@123")
        )

        # ---- Demo sotuvchi (seller) va uning mahsulotlari ----
        seller, _ = User.objects.get_or_create(
            phone="+998901234563", defaults={"full_name": "Demo Sotuvchi"}
        )
        seller.is_active = True
        seller.is_verified = True
        seller.role = User.Role.SELLER
        seller.full_name = "Demo Sotuvchi"
        seller.set_password("Seller@123456")
        seller.save()
        self.stdout.write(
            self.style.SUCCESS(f"[OK] Sotuvchi: {seller.phone} / Seller@123456")
        )

        # Bir nechta mahsulotni sotuvchiga biriktiramiz (qolgani — do'konniki)
        seller_names = ["Redmi Note 13 Pro", "Lenovo IdeaPad Slim 3", "Yoga gilami (182x61)"]
        assigned = Product.objects.filter(name__in=seller_names).update(seller=seller)
        self.stdout.write(self.style.SUCCESS(f"[OK] Sotuvchiga {assigned} ta mahsulot biriktirildi"))

        # ---- AirPods Pro 2 ga demo sharhlar (o'rtacha yulduz ko'rinishi uchun) ----
        flagship = Product.objects.filter(name="AirPods Pro 2").first()
        if flagship is not None:
            reviewers = [
                (demo_user, 5, "Ajoyib quloqchinlar! Shovqinni bostirishi zo'r."),
                (courier, 4, "Sifati yaxshi, lekin narxi biroz baland."),
                (staff, 5, "Tavsiya qilaman — batareyasi uzoq turadi."),
            ]
            from apps.products.models import Review

            for r_user, rating, comment in reviewers:
                Review.objects.update_or_create(
                    product=flagship,
                    user=r_user,
                    defaults={"rating": rating, "comment": comment},
                )
            self.stdout.write(self.style.SUCCESS(f"[OK] AirPods Pro 2 ga {len(reviewers)} ta sharh"))

        self.stdout.write(self.style.SUCCESS("Demo ma'lumotlar tayyor!"))
