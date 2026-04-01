# app/dtos/users.py
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.dtos.base import BaseSerializerModel
from app.models.users import Gender
from app.validators.common import optional_after_validator
from app.validators.user_validators import validate_birthday, validate_email_format, validate_phone_number


class UserUpdateRequest(BaseModel):
    name: Annotated[str | None, Field(None, min_length=2, max_length=20)]
    email: Annotated[
        str | None,
        Field(None, max_length=40),
    ]
    phone_number: Annotated[
        str | None,
        Field(None, description="Available Format: +8201011112222, 01011112222, 010-1111-2222"),
        optional_after_validator(validate_phone_number),
    ]
    birthday: Annotated[
        date | None,
        Field(None, description="Date Format: YYYY-MM-DD"),
        optional_after_validator(validate_birthday),
    ]
    gender: Annotated[
        Gender | None,
        Field(None, description="'MALE' or 'FEMALE'"),
    ]

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_email_format(v)


class UserInfoResponse(BaseSerializerModel):
    id: int
    name: str
    email: str
    phone_number: str
    birthday: date
    gender: Gender
    created_at: datetime
    patient_id: int | None = None


class UserDeviceRegisterRequest(BaseModel):
    device_id: Annotated[str, Field(min_length=8, max_length=500)]
    platform: Annotated[str | None, Field(default=None, max_length=30)]


class UserDeviceCountResponse(BaseSerializerModel):
    linked_device_count: int
    last_login_at: datetime | None = None
