# app/dtos/hospital_calendar_dtos.py

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HospitalScheduleCreateRequest(BaseModel):
    """
    병원 일정 생성 요청 DTO
    """

    patient_id: int = Field(..., description="환자 ID")
    title: str = Field(..., max_length=100, description="일정 제목")
    scheduled_at: datetime = Field(..., description="예약/방문 일시")

    description: str | None = Field(default=None, description="설명/메모")
    hospital_name: str | None = Field(default=None, max_length=100, description="병원명")
    location: str | None = Field(default=None, max_length=255, description="장소")


class HospitalScheduleUpdateRequest(BaseModel):
    """
    병원 일정 수정 요청 DTO
    PATCH 기준이므로 전부 optional
    """

    title: str | None = Field(default=None, max_length=100, description="일정 제목")
    scheduled_at: datetime | None = Field(default=None, description="예약/방문 일시")

    description: str | None = Field(default=None, description="설명/메모")
    hospital_name: str | None = Field(default=None, max_length=100, description="병원명")
    location: str | None = Field(default=None, max_length=255, description="장소")


class HospitalScheduleResponse(BaseModel):
    """
    병원 일정 응답 DTO
    """

    id: int
    patient_id: int
    title: str
    description: str | None
    hospital_name: str | None
    location: str | None
    scheduled_at: datetime
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class HospitalScheduleListResponse(BaseModel):
    """
    병원 일정 목록 응답 DTO
    """

    items: list[HospitalScheduleResponse]
