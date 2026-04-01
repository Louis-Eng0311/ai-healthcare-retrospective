from tortoise import fields, models


class Document(models.Model):
    id = fields.BigIntField(primary_key=True)
    patient = fields.ForeignKeyField("models.Patient", related_name="documents", on_delete=fields.CASCADE)
    uploaded_by_user = fields.ForeignKeyField(
        "models.User", related_name="uploaded_documents", on_delete=fields.CASCADE
    )
    file_url = fields.CharField(max_length=500)
    original_filename = fields.CharField(max_length=255, null=True)
    file_type = fields.CharField(max_length=30, null=True)
    file_size = fields.BigIntField(null=True)
    checksum = fields.CharField(max_length=255, null=True)
    status = fields.CharField(max_length=30)
    created_at = fields.DatetimeField(auto_now_add=True)
    deleted_at = fields.DatetimeField(null=True)

    class Meta:
        table = "documents"
        indexes = (("patient_id", "created_at"), ("uploaded_by_user_id", "created_at"))


class OcrJob(models.Model):
    id = fields.BigIntField(primary_key=True)
    document = fields.ForeignKeyField("models.Document", related_name="ocr_jobs", on_delete=fields.CASCADE)
    patient = fields.ForeignKeyField("models.Patient", related_name="ocr_jobs", on_delete=fields.CASCADE)
    status = fields.CharField(max_length=30)
    retry_count = fields.IntField(default=0)
    error_code = fields.CharField(max_length=100, null=True)
    error_message = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_jobs"
        indexes = (("patient_id", "status"), ("document_id",))


class OcrRawText(models.Model):
    id = fields.BigIntField(primary_key=True)
    ocr_job = fields.OneToOneField("models.OcrJob", related_name="raw_text", on_delete=fields.CASCADE)
    raw_text = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ocr_raw_texts"


class ExtractedMed(models.Model):
    id = fields.BigIntField(primary_key=True)
    ocr_job = fields.ForeignKeyField("models.OcrJob", related_name="extracted_meds", on_delete=fields.CASCADE)
    patient = fields.ForeignKeyField("models.Patient", related_name="extracted_meds", on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    dosage_text = fields.CharField(max_length=255, null=True)
    frequency_text = fields.CharField(max_length=255, null=True)
    duration_text = fields.CharField(max_length=255, null=True)
    confidence = fields.DecimalField(max_digits=5, decimal_places=4, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "extracted_meds"
        indexes = (("patient_id",), ("ocr_job_id",))
