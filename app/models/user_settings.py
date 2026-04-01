from tortoise import fields, models


class UserSettings(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="settings", on_delete=fields.CASCADE, unique=True)

    # 앱 설정
    dark_mode = fields.BooleanField(default=False)
    language = fields.CharField(max_length=10, default="ko")
    push_notifications = fields.BooleanField(default=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_settings"
