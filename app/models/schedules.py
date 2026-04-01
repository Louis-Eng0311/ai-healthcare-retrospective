from tortoise import fields, models


class MedSchedule(models.Model):
    id = fields.BigIntField(primary_key=True)
    patient = fields.ForeignKeyField("models.Patient", related_name="med_schedules", on_delete=fields.CASCADE)
    patient_med = fields.ForeignKeyField("models.PatientMed", related_name="schedules", on_delete=fields.CASCADE)
    start_date = fields.DateField(null=True)
    end_date = fields.DateField(null=True)
    status = fields.CharField(max_length=30)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "med_schedules"
        indexes = (("patient_id", "status"), ("patient_med_id",))


class MedScheduleTime(models.Model):
    id = fields.BigIntField(primary_key=True)
    schedule = fields.ForeignKeyField("models.MedSchedule", related_name="times", on_delete=fields.CASCADE)
    time_of_day = fields.TimeField()
    days_of_week = fields.CharField(max_length=100, null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "med_schedule_times"
        indexes = (("schedule_id", "is_active"), ("time_of_day",))


class IntakeLog(models.Model):
    id = fields.BigIntField(primary_key=True)
    patient = fields.ForeignKeyField("models.Patient", related_name="intake_logs", on_delete=fields.CASCADE)
    schedule = fields.ForeignKeyField(
        "models.MedSchedule", related_name="intake_logs", null=True, on_delete=fields.SET_NULL
    )
    schedule_time = fields.ForeignKeyField(
        "models.MedScheduleTime", related_name="intake_logs", null=True, on_delete=fields.SET_NULL
    )
    patient_med = fields.ForeignKeyField("models.PatientMed", related_name="intake_logs", on_delete=fields.CASCADE)
    recorded_by_user = fields.ForeignKeyField(
        "models.User", related_name="recorded_intakes", null=True, on_delete=fields.SET_NULL
    )
    scheduled_at = fields.DatetimeField(null=True)
    taken_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=30)
    note = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "intake_logs"
        indexes = (("patient_id", "scheduled_at"), ("patient_med_id", "scheduled_at"))


class Reminder(models.Model):
    id = fields.BigIntField(primary_key=True)
    patient = fields.ForeignKeyField("models.Patient", related_name="reminders", on_delete=fields.CASCADE)
    schedule = fields.ForeignKeyField(
        "models.MedSchedule", related_name="reminders", null=True, on_delete=fields.SET_NULL
    )
    schedule_time = fields.ForeignKeyField(
        "models.MedScheduleTime", related_name="reminders", null=True, on_delete=fields.SET_NULL
    )
    type = fields.CharField(max_length=30)
    channel = fields.CharField(max_length=30, null=True)
    remind_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=30, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "reminders"
        indexes = (("patient_id", "remind_at"), ("status", "remind_at"))
