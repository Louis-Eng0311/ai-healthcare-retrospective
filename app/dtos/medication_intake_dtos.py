# app/dtos/medication_intake_dtos.py
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# 복약 상태 enum 성격의 타입
IntakeStatus = Literal["taken", "missed", "pending", "skipped"]


# ----------------------------
# 조회 응답 DTO
# ----------------------------
class IntakeItem(BaseModel):
    schedule_id: int
    schedule_time_id: int
    patient_med_id: int
    medication_name: str | None = None
    scheduled_at: datetime
    status: IntakeStatus
    taken_at: datetime | None = None
    note: str | None = None


class DailyIntakeStatus(BaseModel):
    day: date
    items: list[IntakeItem]


class AdherenceSummary(BaseModel):
    expected_total: int
    taken: int
    missed: int
    pending: int
    skipped: int
    overall_rate: float
    completed_rate: float | None = None


class IntakeStatusResponse(BaseModel):
    patient_id: int
    date_from: date
    date_to: date
    days: list[DailyIntakeStatus]
    summary: AdherenceSummary


class AdherenceResponse(BaseModel):
    patient_id: int
    date_from: date
    date_to: date
    summary: AdherenceSummary


# ----------------------------
# 복약 체크 / 취소 요청 DTO
# ----------------------------
class IntakeCheckRequest(BaseModel):
    # 어떤 시간 슬롯을 체크하는지
    schedule_time_id: int = Field(..., description="복약 시간 슬롯 ID")

    # scheduled_at 전체 datetime을 직접 받지 않고,
    # scheduled_date + schedule_time.time_of_day 로 조합한다.
    scheduled_date: date = Field(..., description="해당 복약 슬롯의 날짜")

    # 실제 복용 시각. 없으면 서버 현재시각으로 처리
    taken_at: datetime | None = Field(None, description="실제 복용 시각")

    # 메모
    note: str | None = Field(None, description="복약 메모")

    # 현재는 인증 연동 전 임시 방식
    # 추후 current_user.id 로 대체 가능
    recorded_by_user_id: int | None = Field(
        None,
        description="기록한 사용자 ID(임시 개발용)",
    )


class IntakeUndoRequest(BaseModel):
    schedule_time_id: int = Field(..., description="복약 시간 슬롯 ID")
    scheduled_date: date = Field(..., description="취소할 복약 슬롯 날짜")


# ----------------------------
# 복약 체크 / 취소 응답 DTO
# ----------------------------
class IntakeCheckResponse(BaseModel):
    message: str
    intake_log_id: int
    patient_id: int
    patient_med_id: int
    schedule_id: int
    schedule_time_id: int
    scheduled_at: datetime
    taken_at: datetime
    status: IntakeStatus
    note: str | None = None


class IntakeUndoResponse(BaseModel):
    message: str
    deleted_intake_log_id: int
    schedule_id: int
    schedule_time_id: int
    scheduled_at: datetime


# ----------------------------
# 복약 체크 / skip
# ----------------------------
class IntakeSkipRequest(BaseModel):
    schedule_time_id: int = Field(..., description="복약 시간 슬롯 ID")
    scheduled_date: date = Field(..., description="해당 복약 슬롯 날짜")
    note: str | None = Field(None, description="건너뛴 사유 메모")
    recorded_by_user_id: int | None = Field(
        None,
        description="기록한 사용자 ID(임시 개발용)",
    )


class IntakeSkipResponse(BaseModel):
    message: str
    intake_log_id: int
    patient_id: int
    patient_med_id: int
    schedule_id: int
    schedule_time_id: int
    scheduled_at: datetime
    status: IntakeStatus
    note: str | None = None
