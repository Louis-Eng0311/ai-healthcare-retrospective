"""인증/계정 관련 Healthcare 모델 파일."""

from tortoise import fields, models


class PhoneVerification(models.Model):
    id = fields.BigIntField(primary_key=True)
    phone = fields.CharField(max_length=30)
    token = fields.CharField(max_length=100, unique=True)
    verified_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "phone_verifications"
        indexes = [("phone", "expires_at")]


class AuthAccount(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="auth_accounts")
    provider = fields.CharField(max_length=20)
    provider_user_id = fields.CharField(max_length=120, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "auth_accounts"
        unique_together = (("provider", "provider_user_id"),)


class RefreshToken(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="refresh_tokens")
    token_hash = fields.CharField(max_length=255)
    expires_at = fields.DatetimeField()
    revoked_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "refresh_tokens"
        indexes = [("user_id", "expires_at")]
