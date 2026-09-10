# ============================================================
#  Auth API testlari — ro'yxatdan o'tish, tasdiqlash, login
# ============================================================
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase

PHONE = "+998901112233"
PASSWORD = "KuchliParol#123"


class NoThrottleMixin:
    """Testlarda rate-limit to'sqinlik qilmasligi uchun cheklovlarni yuqori qiladi."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Testlarda ham dev rejimidagi kabi dev_code ko'rinishi uchun
        settings.DEBUG = True
        for scope in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]:
            settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][scope] = "100000/min"


class AuthFlowTests(NoThrottleMixin, APITestCase):
    def test_register_returns_code_in_dev(self):
        resp = self.client.post(
            "/api/auth/register/",
            {"phone": PHONE, "password": PASSWORD, "full_name": "Ali"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("dev_code", resp.data)  # DEBUG rejimida ko'rinadi
        self.assertEqual(len(resp.data["dev_code"]), 6)

    def test_register_with_invalid_phone(self):
        resp = self.client.post(
            "/api/auth/register/", {"phone": "abc", "password": PASSWORD}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_completes_registration_and_returns_tokens(self):
        reg = self.client.post(
            "/api/auth/register/", {"phone": PHONE, "password": PASSWORD}, format="json"
        )
        code = reg.data["dev_code"]

        # noto'g'ri kod
        bad = self.client.post(
            "/api/auth/verify/", {"phone": PHONE, "code": "000000"}, format="json"
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

        ok = self.client.post(
            "/api/auth/verify/", {"phone": PHONE, "code": code}, format="json"
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertIn("access", ok.data)
        self.assertIn("refresh", ok.data)
        self.assertTrue(ok.data["user"]["is_verified"])

    def test_user_is_inactive_until_verified(self):
        self.client.post(
            "/api/auth/register/", {"phone": PHONE, "password": PASSWORD}, format="json"
        )
        # tasdiqlanmagan foydalanuvchi kirish mumkin emas
        resp = self.client.post(
            "/api/auth/login/", {"phone": PHONE, "password": PASSWORD}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_logout_me_flow(self):
        self._register_and_verify()
        tokens = self._login()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["phone"], PHONE)

        # PATCH profil
        patch = self.client.patch(
            "/api/auth/me/", {"full_name": "Ali Valiyev"}, format="json"
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.data["full_name"], "Ali Valiyev")

        # logout — refresh blacklist
        out = self.client.post(
            "/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(out.status_code, 200)

    def test_unauthenticated_me_returns_401(self):
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_wrong_password_generic_error(self):
        self._register_and_verify()
        resp = self.client.post(
            "/api/auth/login/", {"phone": PHONE, "password": "NotoGri123!"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # enumeration himoyasi: bir xil xato
        resp2 = self.client.post(
            "/api/auth/login/", {"phone": "+998999999999", "password": "x"}, format="json"
        )
        self.assertIn("detail", resp2.data)

    def _register_and_verify(self):
        reg = self.client.post(
            "/api/auth/register/", {"phone": PHONE, "password": PASSWORD}, format="json"
        )
        self.client.post(
            "/api/auth/verify/",
            {"phone": PHONE, "code": reg.data["dev_code"]},
            format="json",
        )

    def _login(self):
        resp = self.client.post(
            "/api/auth/login/", {"phone": PHONE, "password": PASSWORD}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data
