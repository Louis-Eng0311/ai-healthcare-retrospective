from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

_UNKNOWN = {"모름", "몰라", "잘모르겠음", "무응답", "unknown", "n/a"}
_NONE_LIKE = {"해당없음", "없음", "no", "none", "null", "-"}


def _coerce_none_or_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.lower() in {x.lower() for x in _UNKNOWN}:
            return None
    return v


def _coerce_decimal(v: Any) -> Any:
    v = _coerce_none_or_value(v)
    if v is None:
        return None

    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))

    if isinstance(v, str):
        s = v.strip().replace(",", "")
        try:
            return Decimal(s)
        except InvalidOperation:
            return v

    return v


def _coerce_non_negative_decimal(v: Any) -> Any:
    v = _coerce_decimal(v)
    if isinstance(v, Decimal) and v < 0:
        raise ValueError("음수는 입력할 수 없습니다.")
    return v


def _coerce_non_negative_int(v: Any) -> Any:
    v = _coerce_none_or_value(v)
    if v is None:
        return None

    if isinstance(v, bool):
        return v

    if isinstance(v, (int, float)):
        iv = int(v)
        if iv < 0:
            raise ValueError("음수는 입력할 수 없습니다.")
        return iv

    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            return int(s)

    return v


def _coerce_bool(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if v == 1:
            return True
        if v == 0:
            return False
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"true", "t", "1", "y", "yes", "네", "예", "응", "흡연", "입원", "입원중"}:
            return True
        if s in {"false", "f", "0", "n", "no", "아니", "아니요", "비흡연", "금연", "퇴원", "미입원"}:
            return False
    return v


def _coerce_date_or_none(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.lower() in {x.lower() for x in _UNKNOWN.union(_NONE_LIKE)}:
            return None
    return v


def _coerce_list(v: Any) -> list[str]:
    if v is None:
        return []

    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]

    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []

        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if x is not None and str(x).strip()]
            except Exception:
                pass

        parts = [p.strip() for chunk in s.splitlines() for p in chunk.split(",")]
        return [p for p in parts if p]

    raise ValueError("리스트 형식으로 입력해주세요.")


class PatientProfileUpsertIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    sex: str | None = None

    height_cm: Decimal | None = Field(default=None, gt=0, le=300)
    weight_kg: Decimal | None = Field(default=None, gt=0, le=500)

    # 🔴 CHANGED: 프론트 친화적 리스트 구조 + 기존 conditions 입력도 수용
    conditions: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("conditions", "underlying_diseases", "underlying_conditions"),
    )
    allergies: list[str] = Field(default_factory=list)
    meds: list[str] = Field(default_factory=list, validation_alias=AliasChoices("meds", "medications"))

    is_smoker: bool | None = None
    is_hospitalized: bool | None = None
    discharge_date: date | None = None
    notes: str | None = None

    avg_sleep_hours_per_day: Decimal | None = Field(
        default=None,
        ge=0,
        le=24,
        examples=[7.0],
        description="하루 평균 수면 시간(시간 단위)",
    )
    avg_cig_packs_per_week: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        examples=[0.0],
        description="주간 평균 흡연량(갑 단위)",
    )

    avg_alcohol_bottles_per_week: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        examples=[1.0],
        description="주간 평균 음주량(병 단위)",
    )

    avg_exercise_minutes_per_day: int | None = Field(
        default=None,
        ge=0,
        le=1440,
        examples=[30],
        description="하루 평균 운동 시간(분 단위)",
    )

    @field_validator(
        "height_cm",
        "weight_kg",
        "avg_sleep_hours_per_day",
        "avg_cig_packs_per_week",
        "avg_alcohol_bottles_per_week",
        mode="before",
    )
    @classmethod
    def _v_decimal(cls, v: Any) -> Any:
        return _coerce_non_negative_decimal(v)

    @field_validator("avg_exercise_minutes_per_day", mode="before")
    @classmethod
    def _v_int(cls, v: Any) -> Any:
        return _coerce_non_negative_int(v)

    @field_validator("is_smoker", "is_hospitalized", mode="before")
    @classmethod
    def _v_bool(cls, v: Any) -> Any:
        return _coerce_bool(v)

    @field_validator("discharge_date", mode="before")
    @classmethod
    def _v_date(cls, v: Any) -> Any:
        return _coerce_date_or_none(v)

    @field_validator("conditions", "allergies", "meds", mode="before")
    @classmethod
    def _v_list(cls, v: Any) -> list[str]:
        return _coerce_list(v)

    @field_validator("notes", mode="before")
    @classmethod
    def _v_notes(cls, v: Any) -> Any:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class PatientProfileOut(BaseModel):
    patient_id: int
    birth_year: int | None = None
    sex: str | None = None

    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None

    # 🔴 CHANGED: BMI 상태 + 정중한 코멘트
    bmi_status: str | None = None
    bmi_comment: str | None = None

    conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    meds: list[str] = Field(default_factory=list)

    is_smoker: bool | None = None
    is_hospitalized: bool | None = None
    discharge_date: date | None = None
    notes: str | None = None

    avg_sleep_hours_per_day: float | None = None
    avg_cig_packs_per_week: float | None = None
    avg_alcohol_bottles_per_week: float | None = None
    avg_exercise_minutes_per_day: int | None = None
