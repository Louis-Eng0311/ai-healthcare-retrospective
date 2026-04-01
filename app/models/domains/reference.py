"""코드/권한 참조 데이터 관련 Healthcare 모델 파일."""

from typing import Any

from tortoise import fields, models


class CodeGroup(models.Model):
    id = fields.BigIntField(primary_key=True)
    group_code = fields.CharField(max_length=20, unique=True)
    group_name = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "code_groups"


class Code(models.Model):
    id = fields.BigIntField(primary_key=True)
    group_code = fields.ForeignKeyField("models.CodeGroup", to_field="group_code", related_name="codes")
    code = fields.CharField(max_length=50)
    value = fields.CharField(max_length=50)
    display_name = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    sort_order = fields.IntField(default=0)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "codes"
        unique_together = (("group_code", "code"), ("group_code", "value"))
        indexes = [("group_code", "is_active", "sort_order")]


class Role(models.Model):
    id = fields.BigIntField(primary_key=True)
    code = fields.CharField(max_length=9, unique=True)
    name = fields.CharField(max_length=30, unique=True)
    description = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "roles"

    async def save(self, *args: Any, **kwargs: Any) -> None:
        # Tests may create Role(name=...) without passing code.
        if not self.code and self.name:
            self.code = self.name
        await super().save(*args, **kwargs)


class UserRole(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="user_roles")
    role = fields.ForeignKeyField("models.Role", related_name="user_roles")
    assigned_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_roles"
        unique_together = (("user", "role"),)
