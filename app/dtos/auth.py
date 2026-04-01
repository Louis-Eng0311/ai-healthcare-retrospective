from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

from app.models.users import Gender
from app.validators.user_validators import (
    validate_birthday,
    validate_email_format,
    validate_password,
    validate_phone_number,
)


class SignUpRequest(BaseModel):
    email: Annotated[
        str,
        Field(max_length=40),
    ]
    password: Annotated[str, Field(min_length=8), AfterValidator(validate_password)]
    name: Annotated[str, Field(max_length=20)]
    gender: Gender
    birth_date: Annotated[date, AfterValidator(validate_birthday)]
    phone_number: Annotated[str, AfterValidator(validate_phone_number)]
    role: str = Field(default="PATIENT", description="회원가입 역할: PATIENT, CAREGIVER, ADMIN")

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: str) -> str:
        return validate_email_format(v)


class LoginRole(StrEnum):
    PATIENT = "PATIENT"
    CAREGIVER = "CAREGIVER"
    GUARDIAN = "GUARDIAN"
    ADMIN = "ADMIN"


class SocialProvider(StrEnum):
    KAKAO = "kakao"
    NAVER = "naver"


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8)]
    role: LoginRole = Field(
        default=LoginRole.PATIENT,
        description="로그인 역할 선택: PATIENT(복약자), CAREGIVER/GUARDIAN(보호자)",
    )


class LoginResponse(BaseModel):
    access_token: str
    login_role: LoginRole


class TokenRefreshResponse(BaseModel):
    access_token: str


class SocialLoginStartResponse(BaseModel):
    provider: SocialProvider
    authorize_url: str


class FindEmailRequest(BaseModel):
    name: Annotated[str, Field(max_length=20)]
    phone_number: Annotated[str, AfterValidator(validate_phone_number)]


class FindEmailResponse(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    name: Annotated[str, Field(max_length=20)]
    phone_number: Annotated[str, AfterValidator(validate_phone_number)]
    new_password: Annotated[str, Field(min_length=8), AfterValidator(validate_password)]
