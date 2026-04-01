from tortoise import fields, models


class ChatSession(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="chat_sessions", on_delete=fields.CASCADE)
    patient = fields.ForeignKeyField(
        "models.Patient", related_name="chat_sessions", null=True, on_delete=fields.SET_NULL
    )
    mode = fields.CharField(max_length=30, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "chat_sessions"
        indexes = (("user_id", "created_at"), ("patient_id", "created_at"))


class ChatMessage(models.Model):
    id = fields.BigIntField(primary_key=True)
    session = fields.ForeignKeyField("models.ChatSession", related_name="messages", on_delete=fields.CASCADE)
    role = fields.CharField(max_length=20)
    content = fields.TextField()
    status = fields.CharField(max_length=20, default="completed")
    error_message = fields.TextField(null=True)
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "chat_messages"
        indexes = (("session_id", "created_at"), ("session_id", "status", "created_at"))


class ChatSessionMemory(models.Model):
    id = fields.BigIntField(primary_key=True)
    session = fields.OneToOneField("models.ChatSession", related_name="memory", on_delete=fields.CASCADE)
    recent_topic = fields.CharField(max_length=50, null=True)
    recent_drug_name = fields.CharField(max_length=255, null=True)
    recent_external_drug_name = fields.CharField(max_length=255, null=True)
    recent_profile_focus = fields.CharField(max_length=255, null=True)
    recent_hospital_focus = fields.CharField(max_length=100, null=True)
    pending_clarification = fields.CharField(max_length=100, null=True)
    clarification_question = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "chat_session_memory"
        indexes = (("recent_topic", "updated_at"),)


class ChatFeedback(models.Model):
    id = fields.BigIntField(primary_key=True)
    session = fields.ForeignKeyField("models.ChatSession", related_name="feedbacks", on_delete=fields.CASCADE)
    assistant_message = fields.ForeignKeyField(
        "models.ChatMessage",
        related_name="feedbacks",
        on_delete=fields.CASCADE,
    )
    user = fields.ForeignKeyField("models.User", related_name="chat_feedbacks", on_delete=fields.CASCADE)
    helpful = fields.BooleanField()
    feedback_type = fields.CharField(max_length=50, null=True)
    comment = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "chat_feedback"
        indexes = (("session_id", "created_at"), ("assistant_message_id", "created_at"), ("user_id", "created_at"))
