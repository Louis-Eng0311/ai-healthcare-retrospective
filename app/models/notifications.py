from tortoise import fields, models


class UserDevice(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="devices", on_delete=fields.CASCADE)
    platform = fields.CharField(max_length=30, null=True)
    push_token = fields.CharField(max_length=500)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_devices"
        indexes = (("user_id", "is_active"),)


class Notification(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="notifications", on_delete=fields.CASCADE)
    patient = fields.ForeignKeyField(
        "models.Patient", related_name="notifications", null=True, on_delete=fields.SET_NULL
    )
    reminder = fields.ForeignKeyField(
        "models.Reminder", related_name="notifications", null=True, on_delete=fields.SET_NULL
    )
    type = fields.CharField(max_length=50)
    title = fields.CharField(max_length=255, null=True)
    body = fields.TextField(null=True)
    payload_json = fields.TextField(null=True)
    sent_at = fields.DatetimeField(null=True)
    read_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "notifications"
        indexes = (("user_id", "created_at"), ("user_id", "read_at"))
