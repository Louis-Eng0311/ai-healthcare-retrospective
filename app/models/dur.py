from tortoise import fields, models


class DurCheck(models.Model):
    id = fields.BigIntField(primary_key=True)
    patient = fields.ForeignKeyField("models.Patient", related_name="dur_checks", on_delete=fields.CASCADE)
    trigger_type = fields.CharField(max_length=50)
    triggered_by_user = fields.ForeignKeyField(
        "models.User", related_name="triggered_dur_checks", null=True, on_delete=fields.SET_NULL
    )
    status = fields.CharField(max_length=30)
    error_code = fields.CharField(max_length=100, null=True)
    error_message = fields.TextField(null=True)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "dur_checks"
        indexes = (("patient_id", "created_at"), ("status", "created_at"), ("trigger_type", "created_at"))


class DurAlert(models.Model):
    id = fields.BigIntField(primary_key=True)
    dur_check = fields.ForeignKeyField("models.DurCheck", related_name="alerts", on_delete=fields.CASCADE)
    patient = fields.ForeignKeyField("models.Patient", related_name="dur_alerts", on_delete=fields.CASCADE)
    patient_med = fields.ForeignKeyField("models.PatientMed", related_name="dur_alerts", on_delete=fields.CASCADE)
    related_patient_med = fields.ForeignKeyField(
        "models.PatientMed", related_name="related_dur_alerts", null=True, on_delete=fields.SET_NULL
    )
    alert_type = fields.CharField(max_length=50)
    level = fields.CharField(max_length=30)
    basis_json = fields.TextField(null=True)
    message = fields.TextField(null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "dur_alerts"
        indexes = (
            ("patient_id", "created_at"),
            ("patient_med_id", "created_at"),
            ("alert_type", "level"),
            ("dur_check_id",),
        )
