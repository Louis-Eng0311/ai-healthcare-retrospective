from tortoise import fields, models


class PhoneVerification(models.Model):
    id = fields.BigIntField(primary_key=True)
    phone = fields.CharField(max_length=20)
    token = fields.CharField(max_length=255, unique=True)
    verified_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "phone_verifications"
        indexes = (("phone", "expires_at"),)


class AuthAccount(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="auth_accounts", on_delete=fields.CASCADE)
    provider = fields.CharField(max_length=50)
    provider_user_id = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "auth_accounts"
        unique_together = (("provider", "provider_user_id"),)


class RefreshToken(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="refresh_tokens", on_delete=fields.CASCADE)
    token_hash = fields.CharField(max_length=255)
    expires_at = fields.DatetimeField()
    revoked_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "refresh_tokens"
        indexes = (("user_id", "expires_at"),)


class Role(models.Model):
    id = fields.BigIntField(primary_key=True)
    name = fields.CharField(max_length=30, unique=True)

    class Meta:
        table = "roles"


class UserRole(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="user_roles", on_delete=fields.CASCADE)
    role = fields.ForeignKeyField("models.Role", related_name="user_roles", on_delete=fields.CASCADE)
    assigned_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_roles"
        unique_together = (("user", "role"),)
