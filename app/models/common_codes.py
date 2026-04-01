from tortoise import fields, models


class CodeGroup(models.Model):
    id = fields.BigIntField(primary_key=True)
    group_code = fields.CharField(max_length=100, unique=True)
    group_name = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "code_groups"


class Code(models.Model):
    id = fields.BigIntField(primary_key=True)
    group_code = fields.CharField(max_length=100)
    code = fields.CharField(max_length=100)
    value = fields.CharField(max_length=100)
    display_name = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    sort_order = fields.IntField(default=0)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "codes"
        unique_together = (("group_code", "code"), ("group_code", "value"))
        indexes = (("group_code", "is_active", "sort_order"),)
