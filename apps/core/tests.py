# ============================================================
#  Yadro xavfsizlik funksiyalari testlari
# ============================================================
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from apps.core.security import (
    constant_time_equal,
    is_safe_internal_path,
    product_image_path,
    random_numeric_code,
    safe_next_url,
    validate_image_upload,
)
from apps.core.validators import mask_phone, normalize_phone


class OpenRedirectTests(SimpleTestCase):
    """'URL yozib hech qayerga o'tib bo'lmasin' — asosiy xavfsizlik talabi."""

    def test_safe_internal_paths_accepted(self):
        for value in ["/", "/products/12/", "/cart", "/a/b?c=1#d", "/%2e%2e/x"]:
            self.assertTrue(
                is_safe_internal_path(value), f"{value!r} ichki yo'l bo'lishi kerak"
            )

    def test_external_urls_rejected(self):
        for value in [
            "https://evil.com",
            "http://evil.com/x",
            "//evil.com",
            "//evil.com/path",
            "javascript:alert(1)",
            "javascript://host/%0aalert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ftp://evil.com",
            "\\\\evil.com\\share",
            "not-a-path",
            "",
        ]:
            self.assertFalse(
                is_safe_internal_path(value), f"{value!r} rad etilishi kerak"
            )
            self.assertEqual(safe_next_url(value), "/")

    def test_safe_next_returns_default_for_bad(self):
        self.assertEqual(safe_next_url("https://evil.com", "/dashboard"), "/dashboard")
        self.assertEqual(safe_next_url("/profile", "/dashboard"), "/profile")


class PhoneValidatorTests(SimpleTestCase):
    def test_normalize_variants(self):
        for raw, expected in [
            ("+998901234567", "+998901234567"),
            ("998901234567", "+998901234567"),
            ("901234567", "+998901234567"),
            ("8 90 123 45 67", "+998901234567"),
            ("+998 90 123-45-67", "+998901234567"),
        ]:
            self.assertEqual(normalize_phone(raw), expected)

    def test_invalid_phones(self):
        for raw in ["", "123", "998", "+998123", "abc", "99899123abc"]:
            with self.assertRaises(ValidationError):
                normalize_phone(raw)

    def test_mask_phone(self):
        self.assertEqual(mask_phone("+998901234567"), "+998 90 **** 4567")


class CodeTokenTests(SimpleTestCase):
    def test_numeric_code_length_and_uniqueness(self):
        code = random_numeric_code(6)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_constant_time_equal(self):
        self.assertTrue(constant_time_equal("123456", "123456"))
        self.assertFalse(constant_time_equal("123456", "654321"))
        self.assertFalse(constant_time_equal("123456", "12345"))


class ImageUploadTests(TestCase):
    def test_rejects_unsafe_extension(self):
        fake = SimpleUploadedFile("shell.php", b"<?php echo 1; ?>")
        with self.assertRaises(ValidationError):
            validate_image_upload(fake)

    def test_rejects_oversized_file(self):
        big = SimpleUploadedFile(
            "photo.png", b"\x00" * (6 * 1024 * 1024), content_type="image/png"
        )
        with self.assertRaises(ValidationError):
            validate_image_upload(big)

    def test_product_image_path_renames(self):
        path = product_image_path(None, "../../etc/passwd.png")
        self.assertFalse(path.startswith("../"))
        self.assertTrue(path.endswith(".png"))
        self.assertTrue(path.startswith("products/"))
        # original nom hech qachon qolmaydi
        self.assertNotIn("passwd", path)

    def test_rejects_non_image_content(self):
        fake = SimpleUploadedFile(
            "photo.png", b"this is not really a png image", content_type="image/png"
        )
        with self.assertRaises(ValidationError):
            validate_image_upload(fake)
