# 20260303 알림설정 HYJ
from tortoise import fields
from tortoise.models import Model


class NotificationSettings(Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="notification_settings", on_delete=fields.CASCADE, unique=True
    )

    intake_reminder = fields.BooleanField(default=True)
    missed_alert = fields.BooleanField(default=True)
    hospital_schedule_reminder = fields.BooleanField(default=True)
    ocr_done = fields.BooleanField(default=True)
    guide_ready = fields.BooleanField(default=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "notification_settings"
