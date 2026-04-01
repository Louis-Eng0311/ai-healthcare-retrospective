from tortoise import fields, models


class DrugCatalog(models.Model):
    id = fields.BigIntField(primary_key=True)
    mfds_item_seq = fields.CharField(max_length=100, unique=True, null=True)
    name = fields.CharField(max_length=255)
    manufacturer = fields.CharField(max_length=255, null=True)
    ingredients = fields.TextField(null=True)
    warnings = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "drug_catalog"
        indexes = (("name",),)


class DrugInfoCache(models.Model):
    id = fields.BigIntField(primary_key=True)
    mfds_item_seq = fields.CharField(max_length=100, unique=True, null=True)
    drug_name_display = fields.CharField(max_length=255, null=True)
    manufacturer = fields.CharField(max_length=255, null=True)
    efficacy = fields.TextField(null=True)
    dosage_info = fields.TextField(null=True)
    precautions = fields.TextField(null=True)
    interactions = fields.TextField(null=True)
    side_effects = fields.TextField(null=True)
    storage_method = fields.CharField(max_length=255, null=True)
    expires_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "drug_info_cache"
        indexes = (("expires_at",), ("drug_name_display",))


class PatientMed(models.Model):
    id = fields.BigIntField(primary_key=True)
    patient = fields.ForeignKeyField("models.Patient", related_name="patient_meds", on_delete=fields.CASCADE)
    source_document_id = fields.BigIntField(null=True)
    source_ocr_job_id = fields.BigIntField(null=True)
    source_extracted_med_id = fields.BigIntField(null=True)
    drug_catalog = fields.ForeignKeyField(
        "models.DrugCatalog", related_name="patient_meds", null=True, on_delete=fields.SET_NULL
    )
    drug_info_cache = fields.ForeignKeyField(
        "models.DrugInfoCache", related_name="patient_meds", null=True, on_delete=fields.SET_NULL
    )
    display_name = fields.CharField(max_length=255)
    dosage = fields.CharField(max_length=255, null=True)
    route = fields.CharField(max_length=100, null=True)
    notes = fields.TextField(null=True)
    is_active = fields.BooleanField(default=True)
    confirmed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "patient_meds"
        indexes = (("patient_id", "is_active"), ("drug_catalog_id",), ("drug_info_cache_id",))
