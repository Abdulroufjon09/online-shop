# ============================================================
#  JWT autentifikatsiyasi — faqat faol (verified) foydalanuvchilar
# ============================================================
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings


class ActiveUserJWTAuthentication(JWTAuthentication):
    """
    Standart JWT autentifikatsiyasining qat'riyroq varianti:
    token egasi o'chirilgan / tasdiqlanmagan bo'lsa ham so'rov rad etiladi.
    """

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken("Token tarkibida foydalanuvchi identifikatori yo'q.") from exc

        try:
            user = self.user_model.objects.get(pk=user_id)
        except self.user_model.DoesNotExist as exc:
            raise AuthenticationFailed("Foydalanuvchi topilmadi.", code="user_not_found") from exc

        if not user.is_active:
            raise AuthenticationFailed(
                "Hisob faol emas yoki tasdiqlanmagan.", code="user_inactive"
            )
        return user
