# ============================================================
#  Savat + kupon + buyurtma + admin oqimlari testlari
# ============================================================
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.discounts.models import Coupon
from apps.orders.models import PickupPoint
from apps.products.models import Category, Product

User = get_user_model()

PHONE = "+998907778899"
PASSWORD = "KuchliParol#123"


def _png_bytes(hex_color: str = "#4f46e5") -> bytes:
    """Haqiqiy (Pillow bilan tekshiriladigan) PNG fayl yaratadi."""
    buf = BytesIO()
    Image.new("RGB", (24, 18), hex_color).save(buf, format="PNG")
    return buf.getvalue()


def _upload(name: str, color: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, _png_bytes(color), content_type="image/png")


class NoThrottleMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Testlarda ham dev rejimidagi kabi dev_code ko'rinishi uchun
        settings.DEBUG = True
        for scope in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]:
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][scope] = "100000/min"


class ShopFlowTests(NoThrottleMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Telefonlar", slug="telefonlar")
        cls.product = Product.objects.create(
            name="Test Telefon",
            category=cls.category,
            price="1000.00",
            discount_percent=10,  # final = 900
            stock=5,
            is_featured=True,
        )
        cls.product2 = Product.objects.create(
            name="Test Noutbuk",
            category=cls.category,
            price="2000.00",
            stock=3,
        )
        cls.coupon = Coupon.objects.create(
            code="TEST20",
            percent=20,
            valid_from=timezone.now() - timedelta(days=1),
            valid_to=timezone.now() + timedelta(days=7),
        )

    def setUp(self):
        self._register_and_verify()
        tokens = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_public_catalog(self):
        # autentifikatsiyasiz ham katalog ochiq
        self.client.credentials()
        resp = self.client.get("/api/products/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)

        detail = self.client.get(f"/api/products/{self.product.id}/")
        self.assertEqual(detail.status_code, 200)
        # narx serverda hisoblanadi
        self.assertEqual(detail.data["price"], "1000.00")
        self.assertEqual(detail.data["final_price"], "900.00")
        self.assertTrue(detail.data["has_discount"])

        featured = self.client.get("/api/products/featured/")
        self.assertEqual(featured.status_code, 200)
        self.assertEqual(len(featured.data), 1)

    def test_inactive_product_hidden(self):
        self.client.credentials()
        self.product.is_active = False
        self.product.save()
        resp = self.client.get(f"/api/products/{self.product.id}/")
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get("/api/products/")
        self.assertEqual(resp.data["count"], 1)

    def test_cart_add_update_total(self):
        add = self.client.post(
            "/api/cart/add/", {"product": self.product.id, "quantity": 2}, format="json"
        )
        self.assertEqual(add.status_code, 201)
        cart = add.data["cart"]
        self.assertEqual(cart["items_count"], 2)
        self.assertEqual(cart["subtotal"], "1800.00")
        self.assertEqual(cart["total"], "1800.00")

        # yana qo'shish — son oshadi
        add2 = self.client.post(
            "/api/cart/add/", {"product": self.product.id, "quantity": 1}, format="json"
        )
        self.assertEqual(add2.data["cart"]["items_count"], 3)

        # o'zgartirish
        item_id = add2.data["cart"]["items"][0]["id"]
        upd = self.client.patch(
            f"/api/cart/items/{item_id}/", {"quantity": 1}, format="json"
        )
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.data["items_count"], 1)

    def test_add_more_than_stock_rejected(self):
        resp = self.client.post(
            "/api/cart/add/",
            {"product": self.product.id, "quantity": 99},
            format="json",
        )
        # 99 > stock 5 va max qty 99; product.stock=5 yetmaydi -> 400
        self.assertEqual(resp.status_code, 400)

    def test_coupon_apply_and_remove(self):
        self.client.post(
            "/api/cart/add/", {"product": self.product.id, "quantity": 2}, format="json"
        )
        apply = self.client.post("/api/discounts/apply/", {"code": "test20"}, format="json")
        self.assertEqual(apply.status_code, 200)
        cart = apply.data["cart"]
        self.assertEqual(cart["coupon"]["code"], "TEST20")
        self.assertEqual(cart["discount_amount"], "360.00")  # 1800 * 20%
        self.assertEqual(cart["total"], "1440.00")

        rm = self.client.delete("/api/discounts/remove/")
        self.assertEqual(rm.status_code, 200)
        self.assertIsNone(rm.data["cart"]["coupon"])

    def test_coupon_invalid_code(self):
        resp = self.client.post("/api/discounts/apply/", {"code": "YOQ"}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_order_creation_full_flow(self):
        # savat: 2x Test Telefon (900) + 1x Test Noutbuk (2000) = 3800
        self.client.post(
            "/api/cart/add/", {"product": self.product.id, "quantity": 2}, format="json"
        )
        self.client.post(
            "/api/cart/add/", {"product": self.product2.id, "quantity": 1}, format="json"
        )
        self.client.post("/api/discounts/apply/", {"code": "TEST20"}, format="json")

        resp = self.client.post(
            "/api/orders/",
            {"address": "Toshkent sh., Chilonzor 12-uy", "full_name": "Ali"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        order = resp.data["order"]
        self.assertEqual(order["subtotal"], "3800.00")
        self.assertEqual(order["discount_amount"], "760.00")  # 20%
        self.assertEqual(order["total"], "3040.00")
        self.assertEqual(order["coupon_code"], "TEST20")
        self.assertEqual(order["phone"], PHONE)
        self.assertIn("OS-", order["order_number"])
        self.assertEqual(len(order["items"]), 2)

        # zaxira kamaydi
        self.product.refresh_from_db()
        self.product2.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(self.product2.stock, 2)

        # kupon ishlatildi
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 1)

        # savat tozalandi
        cart = self.client.get("/api/cart/").data
        self.assertEqual(cart["items_count"], 0)
        self.assertIsNone(cart["coupon"])

        # buyurtma ro'yxati va detali
        mine = self.client.get("/api/orders/mine/")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.data["count"], 1)

    def test_order_without_stock_rejected(self):
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        self.client.post(
            "/api/cart/add/", {"product": self.product.id, "quantity": 1}, format="json"
        )
        resp = self.client.post(
            "/api/orders/",
            {"address": "Manzil 1", "full_name": "Ali"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_order_cancel_restores_stock(self):
        self.client.post(
            "/api/cart/add/", {"product": self.product.id, "quantity": 2}, format="json"
        )
        resp = self.client.post(
            "/api/orders/",
            {"address": "Manzil 2", "full_name": "Ali"},
            format="json",
        )
        order_id = resp.data["order"]["id"]
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

        cancel = self.client.post(f"/api/orders/{order_id}/cancel/")
        self.assertEqual(cancel.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    def test_order_requires_auth(self):
        self.client.credentials()
        resp = self.client.post("/api/orders/", {"address": "x"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def _register_and_verify(self):
        reg = self.client.post(
            "/api/auth/register/", {"phone": PHONE, "password": PASSWORD}, format="json"
        )
        self.assertEqual(reg.status_code, 201)
        verify = self.client.post(
            "/api/auth/verify/",
            {"phone": PHONE, "code": reg.data["dev_code"]},
            format="json",
        )
        self.assertEqual(verify.status_code, 200)

    def _login(self):
        resp = self.client.post(
            "/api/auth/login/", {"phone": PHONE, "password": PASSWORD}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data


class AdminAPITests(NoThrottleMixin, APITestCase):
    def setUp(self):
        admin = User.objects.create_superuser(
            phone="+998900000001", password="AdminParol#123"
        )
        login = self.client.post(
            "/api/auth/login/",
            {"phone": "+998900000001", "password": "AdminParol#123"},
            format="json",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.data['access']}"
        )

    def test_admin_product_crud_with_images(self):
        cat = Category.objects.create(name="Aksessuarlar", slug="aksessuarlar")
        # Kamida 2 rasm talab qilinadi
        bad = self.client.post(
            "/api/admin/products/",
            {
                "name": "Yagona rasm",
                "category_id": cat.id,
                "price": "500.00",
                "stock": 10,
                "images": [_upload("only.png", "#000000")],
            },
            format="multipart",
        )
        self.assertEqual(bad.status_code, 400)

        create = self.client.post(
            "/api/admin/products/",
            {
                "name": "Admin Mahsulot",
                "category_id": cat.id,
                "price": "500.00",
                "stock": 10,
                "images": [
                    _upload("one.png", "#4f46e5"),
                    _upload("two.png", "#7c3aed"),
                    _upload("three.png", "#ec4899"),
                ],
            },
            format="multipart",
        )
        self.assertEqual(create.status_code, 201, create.data)
        pid = create.data["id"]
        self.assertEqual(len(create.data["gallery"]), 3)

        # Rasmsiz PATCH (JSON) — mavjud rasmlar saqlanadi
        upd = self.client.patch(
            f"/api/admin/products/{pid}/", {"price": "450.00"}, format="json"
        )
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.data["price"], "450.00")

        lst = self.client.get("/api/admin/products/")
        self.assertEqual(lst.status_code, 200)

        dele = self.client.delete(f"/api/admin/products/{pid}/")
        self.assertEqual(dele.status_code, 204)

    def test_normal_user_cannot_access_admin(self):
        user = User.objects.create_user(phone="+998900000002", password="Foydalanuvchi#1")
        user.is_verified = True
        user.is_active = True
        user.save()
        login = self.client.post(
            "/api/auth/login/",
            {"phone": "+998900000002", "password": "Foydalanuvchi#1"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = self.client.get("/api/admin/products/")
        self.assertEqual(resp.status_code, 403)

    def test_admin_order_status_change(self):
        cat = Category.objects.create(name="Kiyim", slug="kiyim")
        product = Product.objects.create(
            name="Kurtka", category=cat, price="800.00", stock=4
        )
        user = User.objects.create_user(phone="+998900000003", password="Xaridor#123")
        user.is_verified = True
        user.is_active = True
        user.save()
        login = self.client.post(
            "/api/auth/login/",
            {"phone": "+998900000003", "password": "Xaridor#123"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.client.post("/api/cart/add/", {"product": product.id, "quantity": 1}, format="json")
        order =        self.client.post(
            "/api/orders/",
            {"address": "Manzil", "full_name": "Ali"},
            format="json",
        ).data["order"]

        # admin sifatida status o'zgartirish
        admin_login = User.objects.get(phone="+998900000001")
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(admin_login)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        change = self.client.patch(
            f"/api/admin/orders/{order['id']}/status/",
            {"status": "processing"},
            format="json",
        )
        self.assertEqual(change.status_code, 200)
        self.assertEqual(change.data["order"]["status"], "processing")


class CourierPanelTests(NoThrottleMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Category.objects.create(name="Elektronika", slug="elektronika")
        cls.product = Product.objects.create(
            name="Router", category=cat, price="500.00", stock=20
        )
        cls.admin = User.objects.create_superuser(
            phone="+998900000010", password="AdminParol#123"
        )
        cls.courier = User.objects.create_user(
            phone="+998900000011", password="Courier#1234", full_name="Kuryer Ali"
        )
        cls.courier.role = User.Role.COURIER
        cls.courier.is_active = True
        cls.courier.is_verified = True
        cls.courier.save()
        cls.customer = User.objects.create_user(
            phone="+998900000012", password="Xaridor#1234", full_name="Xaridor"
        )
        cls.customer.is_active = True
        cls.customer.is_verified = True
        cls.customer.save()

    def _login(self, phone, password):
        resp = self.client.post(
            "/api/auth/login/", {"phone": phone, "password": password}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data["access"]

    def _create_delivery_order(self):
        token = self._login("+998900000012", "Xaridor#1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.client.post(
            "/api/cart/add/", {"product": self.product.id, "quantity": 1}, format="json"
        )
        resp = self.client.post(
            "/api/orders/",
            {"address": "Manzil 10", "full_name": "Xaridor", "delivery_type": "delivery"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data["order"]

    def test_courier_full_delivery_flow(self):
        order = self._create_delivery_order()

        # Admin buyurtmani ishlovga oladi
        token = self._login("+998900000010", "AdminParol#123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.client.patch(
            f"/api/admin/orders/{order['id']}/status/",
            {"status": "processing"},
            format="json",
        )

        # Kuryer kirishi
        token = self._login("+998900000011", "Courier#1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Olinadiganlar ro'yxatida bor
        available = self.client.get("/api/courier/orders/?scope=available")
        self.assertEqual(available.status_code, 200)
        self.assertTrue(
            any(o["id"] == order["id"] for o in available.data["results"])
        )

        claim = self.client.post(f"/api/courier/orders/{order['id']}/claim/")
        self.assertEqual(claim.status_code, 200, claim.data)
        self.assertEqual(claim.data["order"]["courier"]["id"], self.courier.id)

        # Endi 'my' ro'yxatida va available'da yo'q
        my = self.client.get("/api/courier/orders/")
        self.assertTrue(any(o["id"] == order["id"] for o in my.data["results"]))
        available2 = self.client.get("/api/courier/orders/?scope=available")
        self.assertFalse(
            any(o["id"] == order["id"] for o in available2.data["results"])
        )

        step = self.client.post(
            f"/api/courier/orders/{order['id']}/status/",
            {"status": "out_for_delivery"},
            format="json",
        )
        self.assertEqual(step.status_code, 200)
        done = self.client.post(
            f"/api/courier/orders/{order['id']}/status/",
            {"status": "delivered"},
            format="json",
        )
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.data["order"]["status"], "delivered")

    def test_normal_user_cannot_access_courier_panel(self):
        token = self._login("+998900000012", "Xaridor#1234")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/courier/orders/")
        self.assertEqual(resp.status_code, 403)


class PickupPanelTests(NoThrottleMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Category.objects.create(name="Kitoblar", slug="kitoblar")
        cls.product = Product.objects.create(
            name="Kitob", category=cat, price="150.00", stock=10
        )
        cls.point = PickupPoint.objects.create(
            name="Yunusobod punkti",
            address="Toshkent, Yunusobod 12",
            is_active=True,
            latitude=41.35,
            longitude=69.28,
        )
        cls.pickup_user = User.objects.create_user(
            phone="+998900000021", password="Punkt#12345", full_name="Punkt Hodimi"
        )
        cls.pickup_user.role = User.Role.PICKUP
        cls.pickup_user.pickup_point = cls.point
        cls.pickup_user.is_active = True
        cls.pickup_user.is_verified = True
        cls.pickup_user.save()
        cls.customer = User.objects.create_user(
            phone="+998900000022", password="Xaridor#12345", full_name="Mijoz"
        )
        cls.customer.is_active = True
        cls.customer.is_verified = True
        cls.customer.save()

    def _login(self, phone, password):
        resp = self.client.post(
            "/api/auth/login/", {"phone": phone, "password": password}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data["access"]

    def test_pickup_point_ready_and_handed_flow(self):
        token = self._login("+998900000022", "Xaridor#12345")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.client.post(
            "/api/cart/add/", {"product": self.product.id, "quantity": 1}, format="json"
        )
        order = self.client.post(
            "/api/orders/",
            {
                "delivery_type": "pickup",
                "pickup_point": self.point.id,
                "full_name": "Mijoz",
            },
            format="json",
        )
        self.assertEqual(order.status_code, 201, order.data)
        self.assertEqual(order.data["order"]["delivery_type"], "pickup")
        self.assertEqual(order.data["order"]["pickup_point"]["id"], self.point.id)

        token = self._login("+998900000021", "Punkt#12345")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        lst = self.client.get("/api/pickup/orders/")
        self.assertEqual(lst.status_code, 200)
        oid = order.data["order"]["id"]
        self.assertTrue(any(o["id"] == oid for o in lst.data))

        ready = self.client.post(f"/api/pickup/orders/{oid}/ready/")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.data["order"]["status"], "ready")

        handed = self.client.post(f"/api/pickup/orders/{oid}/handed/")
        self.assertEqual(handed.status_code, 200)
        self.assertEqual(handed.data["order"]["status"], "delivered")
